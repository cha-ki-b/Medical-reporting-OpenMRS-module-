# Report Generation Service (v2.1.0)

Stateless rendering service behind the OpenMRS **`medreport`** module. It turns a
JSON description of a report into a **DOCX / PDF / HTML / ODT** document in
**French, English or Arabic**, and hands back an opaque artifact id the module
can preview and download.

It is the single renderer for both medreport use cases (ADR-8): the per-image
observation report and the personalised full patient report.

---

## 1. What this service is and is not

| | |
| --- | --- |
| **Owns** | page layout, typography, direction (LTR/RTL), pagination, template profiles, output formats |
| **Does not own** | who may see what. It has no notion of a patient record, a privilege, or a user |

The `medreport` OpenMRS module decides which data a given clinician is allowed
to include, resolves it, translates the labels, and posts a finished
`DocumentContext`. This service renders whatever it is given. Keeping the
authorization decision entirely on the OpenMRS side means there is exactly one
place where privileges are enforced — see the module's README §Security.

Consequently **this service must never be reachable from the clinical LAN**. It
listens only on the private container network and additionally requires a
shared token (§4).

---

## 2. Why the context is generic

v1 declared one Pydantic model per template (`NeuroReportContext`,
`ImagingReportContext`). Use case 2 lets the clinician pick which *sets* and
which *individual fields* go into a report, and lets any OpenMRS module declare
new sets — so the document's structure is only known at request time. A fixed
schema would have to be edited here every time a contributing module added a
field, which would re-couple this service to OpenMRS internals.

The contract is therefore a self-describing tree:

```
DocumentContext
├── language / title / patient / author / options
├── sections[]            ← "Démographiques", "Antécédents", …
│   ├── fields[]          ← { label, value, type, unit, emphasis }  → "Label : value"
│   ├── records[]         ← repeating occurrences (lab draws, follow-up visits)
│   └── subsections[]     ← recursive
├── image_observations[]  ← "image id : observation" from use case 1
└── doctor_observation    ← the clinician's own closing text, rendered LAST
```

`doctor_observation` is a top-level string rather than a trailing `Section` on purpose:
sections all render *before* the imaging observations, and this has to come after everything
the report drew from the record. Its heading is localised (page furniture); its body is
reproduced exactly as typed and never translated.

Labels arrive already translated. Clinical vocabulary lives in the OpenMRS
message bundles and concept dictionary; duplicating it here would create a
second source of truth. Only the page furniture (`Page 3 of 7`, `Signature and
stamp`, `Not recorded`) is translated locally, in `app/i18n.py`.

---

## 3. Portability

Everything except PDF/ODT is pure Python, so the service runs unchanged on
Linux, Windows and macOS.

| Format | Engine | Requires LibreOffice |
| --- | --- | --- |
| `docx` | python-docx / docxtpl | no |
| `html` | built-in | no |
| `pdf`  | LibreOffice headless | **yes** |
| `odt`  | LibreOffice headless | **yes** |

**LibreOffice is optional and its absence is not an error.** When it is
missing:

- `GET /health` reports `pdf_available: false` and omits `pdf`/`odt` from `formats`;
- a `format: "pdf"` request is served as `docx` with an explicit `warnings[]` entry
  rather than failing;
- **preview still works** — it falls back to an HTML rendition. Previewing before
  download is a hard requirement of use case 2, so it must not depend on an
  optional native dependency.

LibreOffice is discovered from `PATH`, then from the standard install location
for the host OS (`/Applications/LibreOffice.app/...` on macOS, `C:\Program
Files\LibreOffice\program\soffice.exe` on Windows, `/usr/bin/soffice` and the
snap/opt paths on Linux). Override with `MEDREPORT_SOFFICE_PATH`.

Each conversion runs against a **private, throwaway LibreOffice user profile**.
Concurrent conversions otherwise contend on the shared `~/.config/libreoffice`
profile and fail intermittently under load.

### Running natively (Windows / macOS / Linux dev machine)

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt  # macOS/Linux

MEDREPORT_RGS_TOKEN=dev-token ./.venv/Scripts/python -m uvicorn app.main:app --port 8300
```

### Running in Docker (the deployment target)

```bash
echo "MEDREPORT_RGS_TOKEN=$(openssl rand -hex 32)" > .env
docker compose up --build -d
```

The image installs `libreoffice-writer` (not the full suite) plus `fonts-noto-core`
for Arabic glyph coverage, runs as a non-root uid, and mounts the output
directory as a **tmpfs** so rendered PHI never touches the host disk.

---

## 4. Security

| Concern | Handling |
| --- | --- |
| **Caller authentication** | Shared token via `X-Medreport-Token` or `Authorization: Bearer`, compared with `hmac.compare_digest` (constant time). Absent token ⇒ every route except `/health` returns 503 at startup-config level, or 401 per request. |
| **Arbitrary file read** | v1's `GET /download?path=…` let a caller read any file the process could reach. Removed. Downloads now resolve an opaque 32-hex `artifact_id` validated by regex *before* it is used in a path, and the resolved path is re-checked to be inside the output directory. Covered by `test_artifact_ids_are_opaque_and_paths_cannot_be_traversed`. |
| **PHI retention** | Every artifact carries an expiry. A background sweep deletes expired directories (`MEDREPORT_ARTIFACT_TTL_MINUTES`, default 30). An unreadable manifest falls back to mtime so nothing can linger by corrupting its metadata. The module can also `DELETE /artifacts/{id}` the moment it has persisted the Complex Obs. |
| **Preview caching** | `Cache-Control: no-store, private`, `X-Content-Type-Options: nosniff`, and a restrictive `Content-Security-Policy` on the preview response. |
| **Template upload** | `.docx` extension *and* zip magic-byte check, size cap, filename derived from a validated id (never from the upload), stored under a confined uploads directory whose resolved path is re-verified. |
| **Filename injection** | `filename_hint` is NFKD-folded, stripped to `[A-Za-z0-9._-]`, and truncated. |
| **Built-in templates** | Cannot be deleted through the API. |

---

## 5. API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness + capability report (public) |
| `GET` | `/templates` | List template profiles |
| `POST` | `/templates` | Register a style-profile template (JSON body) |
| `POST` | `/templates/upload` | Register a `.docx` letterhead template (multipart) |
| `DELETE` | `/templates/{id}` | Remove a custom template |
| `POST` | `/render` | Render a document, returns an artifact |
| `GET` | `/artifacts/{id}/preview` | Inline rendition (PDF, else HTML) |
| `GET` | `/artifacts/{id}/download` | The document itself |
| `DELETE` | `/artifacts/{id}` | Drop an artifact early |

`POST /render`:

```jsonc
{
  "template": "chu_blida_neuro",
  "format": "pdf",
  "include_preview": true,
  "filename_hint": "Rapport_BENALI",
  "document": {
    "language": "fr",
    "title": "Rapport médical complet",
    "patient":  { "family_name": "BENALI", "given_name": "Yacine", "identifier": "CHU-2026-00412" },
    "author":   { "full_name": "Dr. Amina Kaci" },
    "sections": [
      { "id": "diagnosis", "title": "Diagnostic neurochirurgical",
        "fields": [ { "label": "Diagnostic", "value": "Méningiome frontal", "emphasis": true },
                    { "label": "Taille", "value": "32", "unit": "mm" } ] }
    ],
    "image_observations": [
      { "image_label": "IRM 14/08/2026", "study_uid": "1.2.840…", "text": "Lésion extra-axiale." }
    ],
    "options": { "include_table_of_contents": true, "show_empty_fields": false }
  }
}
```

The v1 body (`{"template": …, "data": {…}}`) is still accepted and adapted
internally, so existing SF2/SF3 callers keep working.

---

## 6. Templates

A template is a JSON **style profile** in `templates/profiles/<id>.json`, read
fresh on every request — drop a file in and it is live, no restart.

```json
{
  "id": "clinique_es_salem",
  "label":  { "fr": "Clinique Es-Salem", "en": "Es-Salem Clinic", "ar": "عيادة السلام" },
  "engine": "builtin",
  "style":  { "accent": "B71C1C", "accent_soft": "FBE9E7", "base_size": 10.5 },
  "header_text": { "fr": "Clinique Es-Salem — Alger" }
}
```

Two engines:

- **`builtin`** — the document is laid out programmatically (`app/layout_docx.py`)
  from the style profile. A new corporate look is the ~15 lines above, with no
  binary asset to maintain and Arabic RTL handled as a property rather than a
  second copy of every template.
- **`docxtpl`** — the profile points at an uploaded `.docx` carrying a real
  letterhead with jinja2 placeholders, for when a JSON style is not enough. The
  template receives the full context plus `sections`, so it can loop over
  whatever the clinician selected.

Shipped profiles: `generic_clinical`, `chu_blida_neuro`, `chu_blida_imaging`,
`compact_summary`. They are written to disk on first start so an administrator
can read one as a worked example. They cannot be deleted via the API.

---

## 7. Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `MEDREPORT_RGS_TOKEN` | *(none)* | **Required.** Shared token. |
| `MEDREPORT_RGS_ALLOW_ANONYMOUS` | `false` | Local development escape hatch. Never enable where PHI is rendered. |
| `MEDREPORT_TEMPLATES_DIR` | `./templates` | Profiles + uploads. |
| `MEDREPORT_OUTPUT_DIR` | `./output` | Transient artifacts. |
| `MEDREPORT_ARTIFACT_TTL_MINUTES` | `30` | PHI retention window. |
| `MEDREPORT_CLEANUP_INTERVAL_SECONDS` | `300` | Sweep frequency. |
| `MEDREPORT_PDF_TIMEOUT_SECONDS` | `60` | LibreOffice conversion timeout. |
| `MEDREPORT_SOFFICE_PATH` | *(auto)* | Override LibreOffice discovery. |
| `MEDREPORT_MAX_TEMPLATE_UPLOAD_BYTES` | `10485760` | Upload cap. |

---

## 8. Tests

```bash
./.venv/Scripts/python -m pytest tests -q
```

**55 tests**, in four files:

| File | Tests | Covers |
| --- | --- | --- |
| `test_render.py` | 27 | token enforcement (missing / wrong / bearer), template CRUD and built-in protection, DOCX content, unit and boolean formatting, empty-field handling, all three languages with direction assertions, Arabic RTL + complex-script font in the DOCX XML, the empty-document case, preview availability, PDF graceful degradation, both v1 payload shapes, path-traversal rejection, artifact deletion, TTL sweeping, filename sanitisation, preview cache headers |
| `test_conversion.py` | 15 | the LibreOffice path: command construction, per-conversion private profile, output discovery, failure / timeout / silent-non-production, PDF end-to-end, preview fallback |
| `test_compat.py` | 4 | the interpreter floor (§3), including a self-checking detector for the f-string regression described below |
| `test_doctor_observation.py` | 9 | verbatim reproduction, **position last in the document**, localised heading with an untranslated body, HTML escaping, blank and observation-only documents |

The suite passes with **and without** LibreOffice installed — `test_render.py`
branches on `renderer.pdf_available()`, and `test_conversion.py` fakes the
process spawn, so the same suite validates both deployment shapes.

### Python floor: 3.11

`layout_html.py` once contained a backslash inside an f-string *expression*.
PEP 701 legalised that in 3.12, but on 3.11 it is a `SyntaxError` — and a
SyntaxError in that module takes the **whole service** down at import rather
than degrading one feature. On a 3.11 sandbox the entire suite collapsed to
"40 errors, 2 failures" from that one line.

`test_compat.py` guards it, and the guard is itself checked: it runs the
detector against the exact offending line, because two obvious detection
approaches silently do not work (`ast.parse(feature_version=…)` does not reject
it, and scanning `tokenize` output does not either, since on 3.12 an f-string is
no longer a single token).

---

## 9. Release history

### 2.1.0 — current

- **`doctor_observation`** added to `DocumentContext` (§2): the clinician's own free text,
  rendered last in both the DOCX and HTML layouts. Heading localised in fr/en/ar; body
  reproduced verbatim.
- `/health` now reports `"version": "2.1.0"`.
- **Backward compatible.** The field is optional, so a medreport 1.0.0 caller that never sends
  it behaves exactly as before. Conversely medreport 1.1.0 talking to a 2.0.0 service simply
  loses the observation block — no error, since the service ignores unknown fields. Upgrading
  both is still recommended.
- Added a `.dockerignore` so `.env` (the shared token) and `output/` (rendered PHI) can never
  reach an image layer. The Dockerfile only copies `app/` and `templates/`, so this is defence
  in depth against a future `COPY . .`.
- `docker-compose.yml`: the OpenMRS network is now `${OPENMRS_NETWORK:-openmrs-orthanc-integration_default}`
  instead of a hard-coded `openmrs-net` that did not exist on the deployment host, and
  `scripts/setup-env.sh` writes it correctly by looking it up.

### 2.0.0

Rewrite of the v1 renderer. Generic self-describing `DocumentContext` instead of one Pydantic
model per template, four output formats, three languages with RTL, the template-profile
registry, opaque artifact ids (v1's `GET /download?path=…` was an arbitrary-file-read), TTL
retention, and the shared-token guard.

**Post-release fix, before 2.1.0:** `layout_html.py` contained a backslash inside an f-string
expression — legal on Python 3.12 (PEP 701), a `SyntaxError` on 3.11. Because it broke
*import*, the whole service and its entire test suite went down from that one line on a 3.11
host. The interpreter floor is now documented as 3.11 and enforced by `test_compat.py`.
