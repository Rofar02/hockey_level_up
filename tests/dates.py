"""Calendar-day helpers for tests.

Services compute "today" in the user's own timezone
(`datetime.now(ZoneInfo(user.timezone)).date()`), and test users default to
`timezone="UTC"`. Fixtures that used Python's naive `date.today()` read the
*machine's* local day instead, so for a few hours around local midnight
(any time the machine isn't on UTC) the two disagreed and ~17 tests failed
for no real reason (reproduced 2026-09-28 by running the suite with
TZ=Etc/GMT+12). Use this instead of `date.today()` in tests.
"""
from datetime import date, datetime, timezone


def utc_today() -> date:
    """"Today" as the app sees it for a default (timezone="UTC") user."""
    return datetime.now(timezone.utc).date()

