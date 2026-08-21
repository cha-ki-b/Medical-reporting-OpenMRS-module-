# Report Generation Service — Linux/Docker image (the CHU Blida deployment target).
#
# On Windows and macOS the service runs the same way straight from a virtualenv
# (see README "Running natively"); this image only exists to give the Linux
# deployment a reproducible LibreOffice install, which is the one dependency
# that is not pip-installable.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEDREPORT_OUTPUT_DIR=/var/lib/medreport/output \
    MEDREPORT_TEMPLATES_DIR=/var/lib/medreport/templates

# libreoffice-writer alone (not the full suite) keeps the image ~400MB smaller;
# fonts-dejavu covers Latin, fonts-noto covers the Arabic output.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-dejavu-core \
        fonts-noto-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates-seed

# Run as a non-root user: the service accepts uploads and writes PHI to disk.
RUN useradd --system --create-home --uid 10001 medreport \
    && mkdir -p /var/lib/medreport/output /var/lib/medreport/templates \
    && cp -r ./templates-seed/. /var/lib/medreport/templates/ 2>/dev/null || true \
    && chown -R medreport:medreport /var/lib/medreport /srv/app

USER medreport

EXPOSE 8300

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8300/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300"]
