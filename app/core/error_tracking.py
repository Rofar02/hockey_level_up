"""GlitchTip (Sentry protocol) setup, shared by the API (app/main.py) and
the background worker (app/background.py)."""
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


def init_error_tracking(settings: Settings) -> None:
    if not settings.glitchtip_dsn:
        return
    # traces_sample_rate=0 -- error tracking only, not APM/performance
    # tracing (a single-VM, low-traffic app has nothing that budget would
    # usefully surface right now). No request bodies, headers or user IPs
    # in reports.
    sentry_sdk.init(
        dsn=settings.glitchtip_dsn,
        environment=settings.environment,
        traces_sample_rate=0.0,
        send_default_pii=False,
        max_request_body_size="never",
        event_scrubber=EventScrubber(denylist=[*DEFAULT_DENYLIST, *EXTRA_DENYLIST]),
    )
