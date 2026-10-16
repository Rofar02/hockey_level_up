"""GlitchTip (Sentry protocol) setup, shared by the API (app/main.py) and
the background worker (app/background.py)."""
import re
from typing import Any

import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

from app.core.config import Settings

# Step 8 (security, 6): the default denylist matches exact names only
# ("password", "token") -- these are the app's own secret-bearing names, so
# they never reach an error report through stack-frame variables either.
EXTRA_DENYLIST = [
    "access_token",
    "refresh_token",
    "raw_token",
    "token_hash",
    "jti",
    "current_jti",
    "previous_jti",
    "password_hash",
    "plain_password",
    "current_password",
    "new_password",
    "delete_password",
    "p256dh",
    "p256dh_key",
    "auth_key",
    "vapid_private_key",
    "jwt_secret_key",
    "zai_api_key",
    "resend_api_key",
]


# 2026-10-13 (А3): the denylist only sees variable/key *names*. A secret can
# still ride inside a string -- an exception message, a breadcrumb, a URL --
# so every string in the event is also run through these before it leaves.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_SECRET_KEY = r"(?:[a-z_]*password|[a-z_]*token|secret|api_key|p256dh|auth_key)"
# Review 14.10 (9): a quoted value is filtered up to its closing quote -- a
# password with spaces in it must not leak its second half. pydantic's
# "input_value='...'" in validation errors carries the raw input of any
# field (a password among them), so it always goes.
_QUOTED_VALUE_RE = re.compile(
    r"(?i)((?:" + _SECRET_KEY + r"['\"]?\s*[=:]|input_value\s*=)\s*)(['\"])((?:\\.|(?!\2).)*)\2"
)
_KEY_VALUE_RE = re.compile(r"(?i)((?:" + _SECRET_KEY + r"['\"]?\s*[=:]|input_value\s*=)\s*)([^'\"&\s,;)}][^&\s,;)}]*)")
FILTERED = "[Filtered]"


def scrub_text(text: str) -> str:
    text = _JWT_RE.sub(FILTERED, text)
    text = _QUOTED_VALUE_RE.sub(lambda match: match.group(1) + match.group(2) + FILTERED + match.group(2), text)
    return _KEY_VALUE_RE.sub(lambda match: match.group(1) + FILTERED, text)


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    return value


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    return _scrub(event)


def sentry_options(settings: Settings) -> dict[str, Any]:
    # traces_sample_rate=0 -- error tracking only, not APM/performance
    # tracing (a single-VM, low-traffic app has nothing that budget would
    # usefully surface right now). No request bodies, headers or user IPs
    # in reports. No stack-frame locals either (А3): a password passed
    # positionally sits in a frame under whatever name the function gave it.
    return {
        "dsn": settings.glitchtip_dsn,
        "environment": settings.environment,
        "traces_sample_rate": 0.0,
        "send_default_pii": False,
        "max_request_body_size": "never",
        "include_local_variables": False,
        "event_scrubber": EventScrubber(denylist=[*DEFAULT_DENYLIST, *EXTRA_DENYLIST]),
        "before_send": scrub_event,
        "before_breadcrumb": scrub_event,
    }


def init_error_tracking(settings: Settings) -> None:
    if not settings.glitchtip_dsn:
        return
    sentry_sdk.init(**sentry_options(settings))
