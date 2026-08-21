"""
Transport-level authentication for the Report Generation Service.

The service renders PHI into downloadable documents, so it must never be an
open endpoint on the deployment network. It is protected by a shared bearer
token issued to the OpenMRS `medreport` module; the OpenMRS side is what
performs *user*-level authorization (privileges, ownership) before it ever
calls here. This module only answers "is the caller the medreport module?".
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from app.config import settings

log = logging.getLogger(__name__)

_HEADER = "X-Medreport-Token"
_warned_anonymous = False


def require_token(
    x_medreport_token: str | None = Header(default=None, alias=_HEADER),
    authorization: str | None = Header(default=None),
) -> None:
    """
    FastAPI dependency enforcing the shared token.

    Accepts either `X-Medreport-Token: <token>` or `Authorization: Bearer <token>`.
    """
    global _warned_anonymous

    if not settings.auth_token:
        if settings.allow_anonymous:
            if not _warned_anonymous:
                log.warning(
                    "Running with no MEDREPORT_RGS_TOKEN and "
                    "MEDREPORT_RGS_ALLOW_ANONYMOUS=true - acceptable for local "
                    "development only, never for a deployment holding PHI."
                )
                _warned_anonymous = True
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Service is not configured: set MEDREPORT_RGS_TOKEN (or "
                "MEDREPORT_RGS_ALLOW_ANONYMOUS=true for local development)."
            ),
        )

    presented = x_medreport_token
    if not presented and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:]

    # compare_digest keeps the check constant-time so the token cannot be
    # recovered by timing the response.
    if not presented or not hmac.compare_digest(presented.strip(), settings.auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing service token.",
        )
