"""What goes wrong on the phones, where we can see it (15.10).

The service worker failing to register, workout actions the offline queue
gave up on, a screen the error boundary caught, a Content-Security-Policy
violation -- all of it used to stay in the phone's console. Each becomes a
warning in the backend log and a warning-level event in GlitchTip.

No login needed (a broken install may never get that far) and nothing about
the player is stored: the text is short, scrubbed of anything token- or
password-like, and nginx rate-limits both routes.

Noise stays out (15.10 follow-up): reports caused by browser extensions or
the browser itself (chrome-extension:, moz-extension:, safari-extension:,
about:, data:) are dropped; the same kind + message goes through at most once
per REPEAT_WINDOW in this process, and GlitchTip gets at most
SENTRY_EVENTS_PER_MINUTE of them (the log keeps the rest).
"""
import json
import logging
import threading
import time
from enum import StrEnum

import sentry_sdk
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.core.error_tracking import scrub_text

logger = logging.getLogger("app.client_events")

router = APIRouter(tags=["client-events"])

CSP_REPORT_MAX_BYTES = 8 * 1024

REPEAT_WINDOW_SECONDS = 10 * 60
SENTRY_EVENTS_PER_MINUTE = 30
# Kept bounded: a flood of distinct messages can't grow the map forever.
MAX_REMEMBERED_KEYS = 2000

# A violation or an error that comes from an extension or the browser's own
# pages, not from the app.
NOISE_PREFIXES = (
    "chrome-extension:",
    "moz-extension:",
    "safari-extension:",
    "safari-web-extension:",
    "ms-browser-extension:",
    "about",
    "data",
)
NOISE_MARKERS = ("chrome-extension://", "moz-extension://", "safari-extension://", "safari-web-extension://")


def is_noise(*values: str | None) -> bool:
    for value in values:
        if not value:
            continue
        text = value.strip().lower()
        if text.startswith(NOISE_PREFIXES) or any(marker in text for marker in NOISE_MARKERS):
            return True
    return False


class _Throttle:
    """Per-process: one (kind, message) per REPEAT_WINDOW_SECONDS, and at
    most SENTRY_EVENTS_PER_MINUTE GlitchTip events a minute."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self._last_seen: dict[tuple[str, str], float] = {}
        self._minute_start = 0.0
        self._sent_this_minute = 0

    def first_in_window(self, kind: str, message: str) -> bool:
        now = time.monotonic()
        key = (kind, message)
        with self._lock:
            last = self._last_seen.get(key)
            if last is not None and now - last < REPEAT_WINDOW_SECONDS:
                return False
            if len(self._last_seen) >= MAX_REMEMBERED_KEYS:
                self._last_seen = {
                    k: seen for k, seen in self._last_seen.items() if now - seen < REPEAT_WINDOW_SECONDS
                }
                if len(self._last_seen) >= MAX_REMEMBERED_KEYS:
                    return False
            self._last_seen[key] = now
            return True

    def sentry_slot(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._minute_start >= 60:
                self._minute_start = now
                self._sent_this_minute = 0
            if self._sent_this_minute >= SENTRY_EVENTS_PER_MINUTE:
                return False
            self._sent_this_minute += 1
            return True


throttle = _Throttle()


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
    if not throttle.first_in_window(title, clean.get("message", "")):
        return
    logger.warning("%s %s", title, json.dumps(clean, ensure_ascii=False))
    if not throttle.sentry_slot():
        return
    with sentry_sdk.new_scope() as scope:
        for key, value in clean.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(f"{title}: {clean.get('message', '')}"[:200], level="warning")


@router.post("/client-events", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_event(body: ClientEventCreate) -> None:
    if is_noise(body.message, body.detail):
        return
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
        source = report.get("source-file") or report.get("sourceFile")
        if is_noise(str(blocked) if blocked else None, str(source) if source else None):
            continue
        _warn(
            "csp-violation",
            {
                "message": f"{directive} blocked {blocked}",
                "path": str(page)[:300] if page else None,
                "detail": str(source or "")[:300] or None,
            },
        )
