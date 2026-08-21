"""
Self-contained HTML rendering of the same DocumentContext.

Two jobs:

  * it is an output format in its own right, and
  * it is the *always-available preview*. PDF preview needs LibreOffice, which
    is an optional dependency on Windows and macOS developer machines. Rather
    than making preview a feature that only works on the deployment box, the
    service falls back to HTML preview, which is pure Python and therefore
    works everywhere. The clinician always gets to see the report before
    downloading it (a hard requirement of use case 2).

The markup carries its own inline CSS and no external asset, so it renders
identically inside an OpenMRS iframe with no network access.
"""

from __future__ import annotations

from html import escape
from typing import List

from app.i18n import t
from app.schemas import DocField, DocRecord, DocSection, DocumentContext, FieldType
from app.templates_registry import TemplateProfile


def _c(value: str) -> str:
    value = (value or "").lstrip("#")
    return f"#{value}"


class HtmlLayout:
    def __init__(self, context: DocumentContext, profile: TemplateProfile) -> None:
        self.ctx = context
        self.profile = profile
        self.style = profile.resolved_style()
        self.lang = context.language.value
        self.rtl = context.direction == "rtl"

    # -- helpers -----------------------------------------------------------

    def _visible(self, fields: List[DocField]) -> List[DocField]:
        if self.ctx.options.show_empty_fields:
            return fields
        return [f for f in fields if f.value is not None and str(f.value).strip() != ""]

    def _value(self, field: DocField) -> str:
        value = field.value
        if value is None or str(value).strip() == "":
            return t(self.lang, "not_recorded")
        text = str(value).strip()
        if field.type == FieldType.boolean:
            key = "yes" if text.lower() in {"true", "1", "yes", "oui", "y"} else "no"
            return t(self.lang, key)
        if field.unit:
            return f"{text} {field.unit}"
        return text

    # -- blocks ------------------------------------------------------------

    @staticmethod
    def _emphasis_attr(field: DocField) -> str:
        return ' class="em"' if field.emphasis else ""

    def _fields_html(self, fields: List[DocField]) -> str:
        visible = self._visible(fields)
        if not visible:
            return ""
        short = [f for f in visible if f.type != FieldType.longtext]
        long = [f for f in visible if f.type == FieldType.longtext]

        parts: List[str] = []
        if short:
            # The emphasis attribute is built outside the f-string on purpose. Before PEP 701
            # (i.e. on Python 3.11 and earlier) an f-string *expression* may not contain a
            # backslash, so an inline `" class=\"em\"" if ... else ""` is a hard SyntaxError
            # there - and a SyntaxError in this module takes the whole service down at import,
            # not just this one line. Keeping quotes out of the expression keeps the file
            # parseable on every supported interpreter. See tests/test_compat.py.
            rows = "".join(
                "<tr>"
                f'<th scope="row">{escape(f.label)}</th>'
                f"<td{self._emphasis_attr(f)}>{escape(self._value(f))}</td>"
                "</tr>"
                for f in short
            )
            parts.append(f'<table class="kv">{rows}</table>')
        for field in long:
            body = "".join(
                f"<p>{escape(line)}</p>" for line in self._value(field).splitlines() or [""]
            )
            parts.append(
                f'<div class="longtext"><h4>{escape(field.label)}</h4>{body}</div>'
            )
        return "".join(parts)

    def _records_html(self, records: List[DocRecord]) -> str:
        if not records:
            return ""
        blocks: List[str] = []
        for index, record in enumerate(records, start=1):
            title = escape(record.title or f"#{index}")
            subtitle = (
                f'<div class="rec-sub">{escape(record.subtitle)}</div>'
                if record.subtitle
                else ""
            )
            blocks.append(
                f'<div class="record"><div class="rec-title">{title}</div>'
                f"{subtitle}{self._fields_html(record.fields)}</div>"
            )
        return "".join(blocks)

    def _section_html(self, section: DocSection, level: int = 1) -> str:
        tag = "h2" if level == 1 else "h3"
        description = (
            f'<p class="sec-desc">{escape(section.description)}</p>'
            if section.description
            else ""
        )
        note = f'<p class="sec-note">{escape(section.note)}</p>' if section.note else ""
        subs = "".join(self._section_html(s, level + 1) for s in section.subsections)
        return (
            f'<section class="sec lvl{level}">'
            f"<{tag}>{escape(section.title)}</{tag}>{description}"
            f"{self._fields_html(section.fields)}{self._records_html(section.records)}"
            f"{subs}{note}</section>"
        )

    def _banner_html(self) -> str:
        patient = self.ctx.patient
        entries = []
        for key, value in (
            ("patient", patient.display_name),
            ("identifier", patient.identifier),
            ("birthdate", patient.birthdate),
            ("age", patient.age),
            ("gender", patient.gender),
            ("author", self.ctx.author.full_name),
            ("generated_at", self.ctx.generated_at),
            ("reference", self.ctx.reference),
        ):
            if value:
                entries.append(
                    f'<div class="bi"><span>{escape(t(self.lang, key))}</span>'
                    f"<strong>{escape(str(value))}</strong></div>"
                )
        if not entries:
            return ""
        return f'<div class="banner">{"".join(entries)}</div>'

    def _observations_html(self) -> str:
        if not self.ctx.image_observations:
            return ""
        blocks = []
        for observation in self.ctx.image_observations:
            meta = "  ·  ".join(
                bit
                for bit in (
                    observation.modality,
                    observation.study_date,
                    observation.author,
                    observation.observed_at,
                )
                if bit
            )
            body = "".join(
                f"<p>{escape(line)}</p>"
                for line in (observation.text or "").splitlines() or [""]
            )
            blocks.append(
                '<div class="obs">'
                f'<div class="obs-id">{escape(observation.image_label or observation.study_uid or "")}</div>'
                + (f'<div class="obs-meta">{escape(meta)}</div>' if meta else "")
                + f'<div class="obs-body">{body}</div></div>'
            )
        return (
            f'<section class="sec lvl1"><h2>{escape(t(self.lang, "image_observations"))}</h2>'
            f'{"".join(blocks)}</section>'
        )

    def _doctor_observation_html(self) -> str:
        """The clinician's own closing text, verbatim and last (see layout_docx)."""
        text = (self.ctx.doctor_observation or "").strip()
        if not text:
            return ""
        body = "".join(f"<p>{escape(line)}</p>" for line in text.splitlines() or [""])
        return (
            f'<section class="sec lvl1"><h2>{escape(t(self.lang, "doctor_observation"))}</h2>'
            f'<div class="doctor-note">{body}</div></section>'
        )

    def _toc_html(self) -> str:
        if not self.ctx.options.include_table_of_contents or not self.ctx.sections:
            return ""
        items = "".join(
            f"<li>{escape(s.title)}"
            + (
                "<ul>" + "".join(f"<li>{escape(x.title)}</li>" for x in s.subsections) + "</ul>"
                if s.subsections
                else ""
            )
            + "</li>"
            for s in self.ctx.sections
        )
        return (
            f'<nav class="toc"><h2>{escape(t(self.lang, "table_of_contents"))}</h2>'
            f"<ol>{items}</ol></nav>"
        )

    # -- entry point -------------------------------------------------------

    def build(self) -> str:
        accent = _c(self.style["accent"])
        accent_soft = _c(self.style["accent_soft"])
        rule = _c(self.style["rule"])
        zebra = _c(self.style["zebra"])
        muted = _c(self.style["muted"])
        text_color = _c(self.style["text"])
        base = float(self.style["base_size"])
        family = (
            "'Segoe UI', 'Noto Naskh Arabic', 'Arial', sans-serif"
            if self.rtl
            else "'Segoe UI', 'Calibri', 'Helvetica Neue', Arial, sans-serif"
        )

        header = self.profile.header_text.get(self.lang) or self.ctx.facility or ""
        footer_bits = [
            bit
            for bit in (
                self.profile.footer_text.get(self.lang),
                t(self.lang, "generated_footer")
                if self.ctx.options.include_generation_footer
                else None,
            )
            if bit
        ]
        body_sections = "".join(self._section_html(s) for s in self.ctx.sections)
        has_note = bool((self.ctx.doctor_observation or "").strip())
        if not body_sections and not self.ctx.image_observations and not has_note:
            body_sections = f'<p class="empty">{escape(t(self.lang, "no_data"))}</p>'

        confidential = (
            f'<div class="confidential">{escape(t(self.lang, "confidential"))}</div>'
            if self.ctx.options.confidentiality_notice
            else ""
        )
        signature = (
            f'<div class="signature"><span>{escape(t(self.lang, "signature"))}</span>'
            f'<div class="sig-line"></div>'
            f"<em>{escape(self.ctx.author.full_name)}</em></div>"
            if self.ctx.options.include_signature_block
            else ""
        )

        return f"""<!doctype html>
<html lang="{self.lang}" dir="{'rtl' if self.rtl else 'ltr'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(self.ctx.title or t(self.lang, 'report_title'))}</title>
<style>
  :root {{
    --accent: {accent}; --accent-soft: {accent_soft}; --rule: {rule};
    --zebra: {zebra}; --muted: {muted}; --text: {text_color};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0 0 3rem; background: #eef1f5; color: var(--text);
    font-family: {family}; font-size: {base}pt; line-height: 1.55;
  }}
  .sheet {{
    max-width: 21cm; margin: 1.2rem auto; background: #fff; padding: 1.6cm 1.8cm 1.2cm;
    box-shadow: 0 2px 16px rgba(0,0,0,.12); border-top: 6px solid var(--accent);
  }}
  .brand {{ font-size: .82em; font-weight: 700; color: var(--accent);
            letter-spacing: .04em; margin-bottom: .6rem; }}
  h1 {{ font-size: 1.85em; color: var(--accent); text-align: center;
        margin: .2rem 0 .1rem; }}
  .subtitle {{ text-align: center; color: var(--muted); font-style: italic;
               margin: 0 0 1rem; }}
  .banner {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
             gap: .1rem .8rem; background: var(--accent-soft);
             padding: .7rem .9rem; border-radius: 4px; margin-bottom: 1.2rem; }}
  .bi {{ display: flex; gap: .4rem; font-size: .88em; }}
  .bi span {{ color: var(--accent); font-weight: 600; }}
  .bi span::after {{ content: " :"; }}
  .toc {{ border: 1px solid var(--rule); border-radius: 4px; padding: .4rem 1rem 1rem;
          margin-bottom: 1.4rem; }}
  .toc ol {{ margin: 0; padding-{'right' if self.rtl else 'left'}: 1.2rem; }}
  .sec {{ margin: 0 0 1.1rem; break-inside: avoid; }}
  .sec h2 {{ font-size: 1.12em; color: var(--accent); text-transform: uppercase;
             letter-spacing: .03em; border-bottom: 2px solid var(--accent);
             padding-bottom: .18rem; margin: 1.3rem 0 .5rem; }}
  .sec h3 {{ font-size: 1em; color: var(--accent); margin: .9rem 0 .35rem; }}
  .sec-desc, .sec-note {{ color: var(--muted); font-style: italic; font-size: .88em;
                          margin: .2rem 0 .5rem; }}
  table.kv {{ width: 100%; border-collapse: collapse; margin: 0 0 .5rem; }}
  table.kv tr:nth-child(even) {{ background: var(--zebra); }}
  table.kv th, table.kv td {{ text-align: {'right' if self.rtl else 'left'};
      padding: .3rem .55rem; border-bottom: 1px solid var(--rule);
      vertical-align: top; font-weight: 400; }}
  table.kv th {{ width: {self.style['label_column_percent']}%; color: var(--muted);
                 font-weight: 600; }}
  table.kv th::after {{ content: " :"; }}
  table.kv td.em {{ font-weight: 700; }}
  .longtext {{ margin: .5rem 0 .7rem; }}
  .longtext h4 {{ margin: 0 0 .2rem; font-size: .95em; color: var(--muted); }}
  .longtext h4::after {{ content: " :"; }}
  .longtext p {{ margin: 0 0 .25rem; }}
  .record {{ border-{'right' if self.rtl else 'left'}: 3px solid var(--accent-soft);
             padding-{'right' if self.rtl else 'left'}: .7rem; margin: .5rem 0 .8rem; }}
  .rec-title {{ font-weight: 700; background: var(--accent-soft);
                padding: .2rem .5rem; border-radius: 3px; display: inline-block;
                margin-bottom: .3rem; }}
  .rec-sub {{ color: var(--muted); font-style: italic; font-size: .87em;
              margin-bottom: .3rem; }}
  .obs {{ border: 1px solid var(--rule); border-radius: 4px; padding: .6rem .8rem;
          margin: 0 0 .7rem; }}
  .obs-id {{ font-weight: 700; color: var(--accent); }}
  .obs-meta {{ color: var(--muted); font-size: .85em; font-style: italic;
               margin-bottom: .35rem; }}
  .obs-body p {{ margin: 0 0 .25rem; }}
  .signature {{ margin-top: 2.2rem; text-align: {'left' if self.rtl else 'right'}; }}
  .signature span {{ color: var(--muted); font-weight: 600; font-size: .88em; }}
  .sig-line {{ border-bottom: 1px solid var(--muted); width: 7cm; height: 2.2rem;
               margin-{'right' if self.rtl else 'left'}: auto; }}
  .signature em {{ font-size: .88em; color: var(--muted); }}
  .confidential {{ margin-top: 1.4rem; background: var(--accent-soft); color: var(--muted);
                   font-style: italic; font-size: .84em; text-align: center;
                   padding: .5rem .8rem; border-radius: 4px; }}
  .page-footer {{ text-align: center; color: var(--muted); font-size: .8em;
                  margin-top: 1rem; }}
  .doctor-note {{ border-{'right' if self.rtl else 'left'}: 3px solid var(--accent);
                  padding-{'right' if self.rtl else 'left'}: .8rem; }}
  .doctor-note p {{ margin: 0 0 .3rem; }}
  .empty {{ text-align: center; color: var(--muted); font-style: italic;
            padding: 2.5rem 0; }}
  @media print {{
    body {{ background: #fff; }}
    .sheet {{ box-shadow: none; margin: 0; max-width: none; padding: 0; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  {f'<div class="brand">{escape(header)}</div>' if header else ''}
  <h1>{escape(self.ctx.title or t(self.lang, 'report_title'))}</h1>
  {f'<p class="subtitle">{escape(self.ctx.subtitle)}</p>' if self.ctx.subtitle else ''}
  {self._banner_html()}
  {self._toc_html()}
  {body_sections}
  {self._observations_html()}
  {self._doctor_observation_html()}
  {signature}
  {confidential}
  {f'<div class="page-footer">{escape("  ·  ".join(footer_bits))}</div>' if footer_bits else ''}
</div>
</body>
</html>"""


def render_html(context: DocumentContext, profile: TemplateProfile) -> str:
    return HtmlLayout(context, profile).build()
