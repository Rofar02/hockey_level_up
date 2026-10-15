"""What goes wrong on the phones, where we can see it (15.10).

The service worker failing to register, workout actions the offline queue
gave up on, a screen the error boundary caught, a Content-Security-Policy
violation -- all of it used to stay in the phone's console. Each becomes a
warning in the backend log and a warning-level event in GlitchTip.

No login needed (a broken install may never get that far) and nothing about
the player is stored: the text is short, scrubbed of anything token- or
password-like, and nginx rate-limits both routes.
"""
import json
import logging
from enum import StrEnum

import sentry_sdk
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.core.error_tracking import scrub_text

logger = logging.getLogger("app.client_events")

router = APIRouter(tags=["client-events"])

CSP_REPORT_MAX_BYTES = 8 * 1024


class ClientEventKind(StrEnum):
    SW_REGISTER_FAILED = "sw_register_failed"
    QUEUE_ACTION_FAILED = "queue_action_failed"
    APP_ERROR = "app_error"


class ClientEventCreate(BaseModel):
    kind: ClientEventKind
    message: str = Field(max_length=500)
    detail: str | None = Field(default=None, max_length=2000)
    path: str | None = Field(default=None, max_length=300)
    app_version: str | None = Field(default=None, max_length=40)


def _warn(title: str, fields: dict[str, str | None]) -> None:
    clean = {key: scrub_text(value) for key, value in fields.items() if value}
    logger.warning("%s %s", title, json.dumps(clean, ensure_ascii=False))
    with sentry_sdk.new_scope() as scope:
        for key, value in clean.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(f"{title}: {clean.get('message', '')}"[:200], level="warning")


@router.post("/client-events", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_event(body: ClientEventCreate) -> None:
    _warn(
        f"client:{body.kind.value}",
        {"message": body.message, "detail": body.detail, "path": body.path, "app_version": body.app_version},
    )


@router.post("/csp-report", status_code=status.HTTP_204_NO_CONTENT)
async def report_csp_violation(request: Request) -> None:
    """The browser's own report (Content-Type application/csp-report, or
    application/reports+json from the Reporting API) -- read as raw bytes,
    since FastAPI wouldn't parse either content type as JSON."""
    raw = (await request.body())[:CSP_REPORT_MAX_BYTES]
    try:
        payload = json.loads(raw)
    except ValueError:
        return
    reports = payload if isinstance(payload, list) else [payload]
    for item in reports[:5]:
        if not isinstance(item, dict):
            continue
        report = item.get("csp-report") or item.get("body") or {}
        if not isinstance(report, dict):
            continue
        directive = report.get("violated-directive") or report.get("effectiveDirective") or report.get("effective-directive")
        blocked = report.get("blocked-uri") or report.get("blockedURL")
        page = report.get("document-uri") or report.get("documentURL")
        _warn(
            "csp-violation",
            {
                "message": f"{directive} blocked {blocked}",
                "path": str(page)[:300] if page else None,
                "detail": str(report.get("source-file") or report.get("sourceFile") or "")[:300] or None,
            },
        )
