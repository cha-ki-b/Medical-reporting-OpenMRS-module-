# How to install Medreport — step by step

This guide installs the **report system** onto the hospital server.

You do not need to understand the code. You need to be able to copy a line, paste it into a
black window, and press Enter. Every command below is safe to run more than once.

**Time needed:** about 30 minutes the first time.

---

## What you are installing

Two separate things that talk to each other:

| Piece | What it is | Where it goes |
| --- | --- | --- |
| **medreport** | A plug-in for OpenMRS. Adds the report buttons and screens. | Into OpenMRS |
| **report-generation-service** | A small helper program that turns data into a nice Word/PDF document. | Its own container next to OpenMRS |

Think of it like a printer: **medreport** decides *what* to print and *who is allowed* to
print it. The **report-generation-service** is the printer that makes the actual page.

They must be able to talk to each other, and they must share a **password** so nobody else can
use the printer. Most installation problems are one of those two things.

---

## Before you start — collect 3 things

Open a terminal on the server (or connect with AnyDesk / SSH) and run these. Write the answers
on paper.

### 1. Is Docker working?

```bash
docker ps
```

You should see a table of running containers. If you see an error instead, Docker is not
running — start it and try again before going further.

### 2. What is the OpenMRS container called?

```bash
docker ps --format "{{.Names}}"
```

Look for the one that is OpenMRS. On this project it is **`openmrs-app`**. Write it down.

---

## Step 1 — Put the files on the server

Copy the two folders onto the server, for example into `/home/server/`:

- `report-generation-service`
- `Medreport-module`

If you are copying from Windows with WinSCP or a USB stick, just copy the whole folders.

Then go into the service folder:

```bash
cd /home/server/report-generation-service
```

> **Are there two copies?** On this server the folders exist both in your home directory and
> inside `openmrs-orthanc-integration/`. Pick one and always use that one. The commands below
> assume `~/report-generation-service`.

---

## Step 2 — Let the script write the settings

There are exactly two settings, and both are easy to get wrong by hand. A script works them
out for you:

```bash
sh scripts/setup-env.sh
```

It prints something like:

```
OpenMRS container : openmrs-app
Docker network    : openmrs-orthanc-integration_default
Shared token      : generated a new one

Wrote /home/server/report-generation-service/.env
```

and then shows you the password to paste into OpenMRS in Step 6. **Keep that line on screen,
or get it back any time with `grep MEDREPORT_RGS_TOKEN .env`.**

If your OpenMRS container is not called `openmrs-app`, pass its name:

```bash
sh scripts/setup-env.sh my-openmrs-container
```

Re-running the script is safe: it keeps the password you already have and only refreshes the
network name.

<details>
<summary>Doing it by hand instead (only if the script cannot run)</summary>

```bash
# the network NAME - not the ID
docker inspect -f '{{range $name, $conf := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' openmrs-app

# a random password
openssl rand -hex 32
```

Then create `.env` with those two values:

```
MEDREPORT_RGS_TOKEN=<the random password>
OPENMRS_NETWORK=<the network name>
```

No spaces around `=`, no quotes.

**The network must be the NAME** (`openmrs-orthanc-integration_default`), never the long
hexadecimal ID that `docker network ls` shows in its first column. Docker Compose only ever
looks networks up by name, so an ID produces the confusing error
`network <64-hex> declared as external, but could not be found`.

</details>

---

## Step 3 — Start the printer

```bash
docker compose up --build -d
```

The first time this takes 5–10 minutes, because it downloads LibreOffice (the part that makes
PDFs). Later starts take seconds.

When it finishes, check it is alive:

```bash
docker compose ps
```

You want to see `medreport-rgs` with status **running** or **healthy**.

Now ask it how it feels:

```bash
docker exec medreport-rgs curl -fsS http://127.0.0.1:8300/health
```

You should get back something like:

```json
{"status":"ok","version":"2.0.0","pdf_available":true,"templates":4,
 "formats":["docx","html","pdf","odt"]}
```

Two things to check in that answer:

- `"status":"ok"` → the printer works.
- `"pdf_available":true` → it can make PDFs. If this says `false`, everything still works but
  PDF and ODT are unavailable; you will only be able to download Word and HTML files.

> **If this step fails,** jump to *Problem 1* at the bottom.

---

## Step 4 — Check the two programs can actually see each other

This is the step that catches the most common mistake. Ask **OpenMRS** to call the printer:

```bash
docker exec openmrs-app curl -fsS http://medreport-rgs:8300/health
```

- If you get the same `{"status":"ok"...}` answer → **perfect, they can talk.**
- If you get `Could not resolve host` → they are on different networks. Go to *Problem 2*.

Do not continue until this works. Nothing else will function if this fails.

---

## Step 5 — Install the plug-ins into OpenMRS

You need three `.omod` files. They are here after building (see the end of this guide if you
need to build them):

```
Medreport-module/omod/target/medreport1.0.0.omod
neuro-patientview/omod/target/patientview1.2.1.omod
custom-imaging-openmrs/omod/target/imaging-1.1.1-SNAPSHOT.omod
```

Install them through the OpenMRS web page — that is the easy and safe way:

1. Open OpenMRS in your browser and log in as **admin**.
2. Go to **System Administration → Manage Modules**.
3. Click **Add or Upgrade Module**.
4. Choose `medreport1.0.0.omod`, then click **Upload**.
5. Do the same for `patientview1.2.1.omod` and `imaging-1.1.1-SNAPSHOT.omod`.
6. Wait until all three show a green **Started** mark.

> **Important — order matters a little.** If medreport starts *before* patientview, it will not
> see the neurosurgery data yet. Fix it in ten seconds: after all three are started, open
> `https://YOUR-OPENMRS/openmrs/medreport/settings.page?refresh=true`. That rescans and picks
> everything up. No restart needed.

> **Warning about this server.** The `openmrs-app` container has no storage volume, so
> **everything you upload is erased if the container is ever recreated** (`docker compose down`,
> an image update, etc.). Keep the three `.omod` files somewhere safe and be ready to upload
> them again. Ask your system administrator to add a volume for
> `/usr/local/tomcat/.OpenMRS/modules` when they get a chance.

---

## Step 6 — Tell OpenMRS the password

Right now OpenMRS knows where the printer is, but not the password, so it will refuse to print.

1. In OpenMRS go to **System Administration → Advanced Settings**.
2. In the search box type `medreport`.
3. Find **`medreport.renderService.token`** and paste the long password from Step 2.
4. Check **`medreport.renderService.baseUrl`** says exactly:
   `http://medreport-rgs:8300`
5. Scroll to the bottom and click **Save**.

> **Do not leave the token empty.** An empty token is the single most common reason a fresh
> install cannot produce a document.

While you are here you can also set, if you like:

| Setting | What it does |
| --- | --- |
| `medreport.defaultLanguage` | `fr`, `en` or `ar` — the language pre-selected for new reports |
| `medreport.facilityName` | The hospital name printed at the top of every report |
| `medreport.departmentName` | The department name printed under it |

---

## Step 7 — Give people permission

Nobody can use the system until you say who is allowed to do what.

Go to **System Administration → Manage Roles**, open a role, and tick the privileges it needs.

| Privilege | Give it to | Lets them |
| --- | --- | --- |
| `App: medreport.dashboardGenerate` | everyone who writes reports | Use the "Générer le rapport" button |
| `App: medreport.imaging.view` | nurses, surgeons, radiologists | **Read** imaging reports (anyone's) and download them |
| `App: medreport.imaging.manage` | surgeons, radiologists | **Write** reports, and edit/remove **their own** |
| `App: medreport.admin` | head of department / IT admin only | See a report's full history and undo a deletion |

**A suggested setup:**

- **Nurse** → `dashboardGenerate` + `imaging.view`
- **Surgeon / Radiologist** → `dashboardGenerate` + `imaging.view` + `imaging.manage`
- **Head of department** → all four

Two rules the system enforces on its own, so you do not have to worry about them:

- `imaging.manage` lets someone write reports, but **never** lets them touch a colleague's
  report — only the author can edit or delete their own.
- A doctor can only put data in a report if they are already allowed to see that data.
  Anything they cannot see does not even appear as a choice.

---

## Step 8 — Try it

### Test A — a full patient report

1. Open any patient.
2. Click **Générer le rapport**.
3. You should see a list of data on the left ("Données démographiques", "Diagnostic
   neurochirurgical", …) and language/format choices on the right.
4. Tick a few boxes, click **Générer le rapport**.
5. A preview window opens. Click **Télécharger**.

> **If the left side is empty and no button reacts**, see *Problem 3*.

### Test B — an imaging report

1. Open a patient, go to the **Imagerie** tab.
2. Below the list of studies you will see **Comptes rendus d'imagerie**.
3. Click **Nouveau compte rendu**.
4. Tick one **or several** studies, write your observations, click **Enregistrer**.
5. The report appears in the list, showing your name and the date.
6. Use the **Comptes rendus sur** dropdown to see all reports about one particular image.
7. Tick **Uniquement mes comptes rendus** to see only your own.
8. On your own reports you get **Modifier** and **Supprimer**. On a colleague's report those
   buttons are greyed out — hover over one and it tells you why.

---

## Step 9 — Check it is healthy

Log in as an administrator and open:

```
https://YOUR-OPENMRS/openmrs/medreport/settings.page
```

This page tells you, in one screen:

- whether the printer is reachable and whether it can make PDFs,
- which report templates exist,
- which modules are supplying clinical data (you should see `core` and `patientview`),
- the recent activity log — who created, edited or deleted which report, and when.

---

# Problems and how to fix them

### Problem 1 — `docker compose up` fails

#### "network `2cc97378…` declared as external, but could not be found"

The image builds fine, then this appears and `docker compose ps` shows **nothing running**.

That long string is a network **ID**. Compose only looks networks up by **name**, so it
searched for a network literally called `2cc97378…` and found none.

It means `OPENMRS_NETWORK` in `.env` holds an ID — usually copied from the first column of
`docker network ls`. Fix it in one command:

```bash
sh scripts/setup-env.sh
```

Then start again:

```bash
docker compose up --build -d
```

To confirm before starting, `cat .env` should show a readable name:

```
OPENMRS_NETWORK=openmrs-orthanc-integration_default     ← correct (a name)
OPENMRS_NETWORK=2cc97378c8ed50a1...                     ← wrong (an ID)
```

You can also just delete the `OPENMRS_NETWORK` line: the built-in default is already
`openmrs-orthanc-integration_default`, which is the network this server uses.

#### "set MEDREPORT_RGS_TOKEN in .env"

`.env` is missing or the line is misspelled. Run `sh scripts/setup-env.sh` and check with
`cat .env`.

#### It hangs while downloading

The server may not reach the internet properly. Ask your network administrator; on this server
`deb.debian.org` currently resolves only to IPv6 addresses, which can make downloads fail.

---

### Problem 2 — `Could not resolve host: medreport-rgs`

OpenMRS and the printer are on different networks. Fix it:

```bash
docker network connect $(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' openmrs-app) medreport-rgs
```

Then test again:

```bash
docker exec openmrs-app curl -fsS http://medreport-rgs:8300/health
```

To make it permanent, correct `OPENMRS_NETWORK` in `.env` and run `docker compose up -d` again.

---

### Problem 3 — the report screen is empty / buttons do nothing

Almost always one of these:

1. **Old files.** Your browser kept the previous version of the page. Press `Ctrl+Shift+R` to
   force a reload.
2. **medreport started before patientview.** Open
   `.../openmrs/medreport/settings.page?refresh=true` and look at "Sources de données
   cliniques". If `patientview` is missing there, that is the cause — the refresh fixes it.
3. **The user lacks `App: medreport.dashboardGenerate`.** Go back to Step 7.

To see the real reason: in your browser press `F12`, click the **Console** tab, reload the page,
and read the first red line. Send that line to whoever maintains the module.

---

### Problem 4 — "The Report Generation Service token is not configured"

You skipped Step 6, or the password does not match. Compare the two:

```bash
grep MEDREPORT_RGS_TOKEN /home/server/report-generation-service/.env
```

against **Advanced Settings → `medreport.renderService.token`** in OpenMRS. They must be
character-for-character identical.

---

### Problem 5 — PDF is greyed out, only Word works

LibreOffice is not available inside the container. Check:

```bash
docker exec medreport-rgs curl -fsS http://127.0.0.1:8300/health
```

If `"pdf_available":false`, rebuild the container:

```bash
cd /home/server/report-generation-service
docker compose up --build -d --force-recreate
```

Nothing is broken meanwhile — Word (`.docx`) and HTML keep working, and the preview falls back
to HTML automatically.

---

### Problem 6 — a doctor deleted a report by mistake

Nothing is ever really deleted. An administrator (`App: medreport.admin`) opens the patient's
Imagerie tab, finds the report — administrators still see removed ones, marked **Supprimé** —
and clicks **Restaurer**.

---

# Daily operations

### See what people have been doing

`.../openmrs/medreport/settings.page` → "Activité récente". Every creation, edit, deletion,
restoration and refused attempt is recorded with the user, the time and the IP address.

### Add a new report design

You do not need a programmer. Create a small text file on the server:

```bash
cd /home/server/report-generation-service/templates/profiles
nano clinique_es_salem.json
```

Paste and adapt:

```json
{
  "id": "clinique_es_salem",
  "label": { "fr": "Clinique Es-Salem", "en": "Es-Salem Clinic", "ar": "عيادة السلام" },
  "engine": "builtin",
  "style": { "accent": "B71C1C", "accent_soft": "FBE9E7" },
  "header_text": { "fr": "Clinique Es-Salem — Alger" }
}
```

`accent` is the main colour in hexadecimal, without the `#`. Save, and it appears in the
template list immediately — **no restart**.

### Back up

Back up as usual:

- the **OpenMRS MySQL database** (all reports and their history live there),
- the OpenMRS **complex obs folder** (the Word files themselves).

You do **not** need to back up the printer container: it keeps nothing. Documents there are
deleted automatically after 30 minutes.

### Restart the printer

```bash
cd /home/server/report-generation-service
docker compose restart
```

Safe at any time. Nothing is lost.

---

# Appendix — building the `.omod` files yourself

Only needed if you changed the source code. Requires Java 8 and Maven.

```bash
cd Medreport-module        && mvn clean install
cd ../neuro-patientview    && mvn clean install
cd ../custom-imaging-openmrs && mvn clean install
```

Each ends with `BUILD SUCCESS`, and the file you need is in that project's `omod/target/`
folder, ending in `.omod`.

If a build fails with a strange XML error, run `mvn clean` first — a leftover file from an
older build is the usual cause.

To run the tests too:

```bash
cd report-generation-service
python -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests -q
```

---

# One-page summary

```bash
cd /home/server/report-generation-service

# 1. work out the settings and write .env
sh scripts/setup-env.sh

# 2. start the printer
docker compose up --build -d

# 3. prove OpenMRS can reach it   <-- do not skip
docker exec openmrs-app curl -fsS http://medreport-rgs:8300/health

# 4. show the password again for Step 6
grep MEDREPORT_RGS_TOKEN .env
```

Then, in the OpenMRS web interface:

5. Upload the three `.omod` files (System Administration → Manage Modules)
6. Paste the same token into `medreport.renderService.token` (Advanced Settings)
7. Give out the four `App: medreport.*` privileges (Manage Roles)
8. Open a patient and click **Générer le rapport**
