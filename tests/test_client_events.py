"""POST /client-events and /csp-report (15.10): what goes wrong on the phones
becomes a warning in the log -- without a login, scrubbed, size-capped."""
import json
import logging

import httpx
import pytest

from app.main import app
from app.routers import client_events


@pytest.fixture(autouse=True)
def _fresh_throttle():
    client_events.throttle.reset()
    yield
    client_events.throttle.reset()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_client_event_is_logged_as_a_warning_without_login(caplog):
    caplog.set_level(logging.WARNING, logger="app.client_events")
    async with _client() as client:
        response = await client.post(
            "/client-events",
            json={
                "kind": "sw_register_failed",
                "message": "SecurityError: refresh_token=abc.def leaked",
                "path": "/",
                "app_version": "123",
            },
        )
    assert response.status_code == 204
    record = next(r for r in caplog.records if r.name == "app.client_events")
    assert record.levelno == logging.WARNING
    assert "client:sw_register_failed" in record.getMessage()
    assert "abc.def" not in record.getMessage()


@pytest.mark.asyncio
async def test_client_event_rejects_unknown_kind_and_long_text():
    async with _client() as client:
        unknown = await client.post("/client-events", json={"kind": "anything", "message": "x"})
        long = await client.post("/client-events", json={"kind": "app_error", "message": "x" * 501})
    assert unknown.status_code == 422
    assert long.status_code == 422


@pytest.mark.asyncio
async def test_csp_report_in_both_browser_formats(caplog):
    caplog.set_level(logging.WARNING, logger="app.client_events")
    legacy = {
        "csp-report": {
            "document-uri": "https://icelevel.ru/",
            "violated-directive": "img-src",
            "blocked-uri": "https://evil.example/x.png",
        }
    }
    reporting_api = [
        {"type": "csp-violation", "body": {"documentURL": "https://icelevel.ru/team", "effectiveDirective": "script-src", "blockedURL": "inline"}}
    ]
    async with _client() as client:
        first = await client.post(
            "/csp-report", content=json.dumps(legacy), headers={"Content-Type": "application/csp-report"}
        )
        second = await client.post(
            "/csp-report", content=json.dumps(reporting_api), headers={"Content-Type": "application/reports+json"}
        )
        garbage = await client.post("/csp-report", content=b"not json", headers={"Content-Type": "text/plain"})
    assert (first.status_code, second.status_code, garbage.status_code) == (204, 204, 204)
    messages = [r.getMessage() for r in caplog.records if r.name == "app.client_events"]
    assert any("img-src blocked https://evil.example/x.png" in m for m in messages)
    assert any("script-src blocked inline" in m for m in messages)



@pytest.mark.asyncio
async def test_extension_and_browser_noise_is_dropped(caplog):
    """15.10 follow-up: what an extension or the browser itself caused never
    reaches the log or GlitchTip."""
    caplog.set_level(logging.WARNING, logger="app.client_events")
    noise = [
        {"csp-report": {"violated-directive": "script-src", "blocked-uri": "chrome-extension://abc/inject.js"}},
        {"csp-report": {"violated-directive": "img-src", "blocked-uri": "data"}},
        {"csp-report": {"violated-directive": "frame-src", "blocked-uri": "about"}},
        {"csp-report": {"violated-directive": "script-src", "blocked-uri": "inline", "source-file": "moz-extension://x/c.js"}},
        {"csp-report": {"violated-directive": "style-src", "blocked-uri": "safari-extension://y"}},
    ]
    async with _client() as client:
        for report in noise:
            await client.post("/csp-report", content=json.dumps(report), headers={"Content-Type": "application/csp-report"})
        await client.post(
            "/client-events",
            json={"kind": "app_error", "message": "TypeError: x", "detail": "at chrome-extension://abc/content.js:1:2"},
        )
    assert [r for r in caplog.records if r.name == "app.client_events"] == []


@pytest.mark.asyncio
async def test_a_repeat_is_logged_once_and_glitchtip_is_capped(caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger="app.client_events")
    sent = []
    monkeypatch.setattr(client_events.sentry_sdk, "capture_message", lambda *args, **kwargs: sent.append(args))
    async with _client() as client:
        for _ in range(3):
            await client.post("/client-events", json={"kind": "app_error", "message": "same thing"})
        for number in range(client_events.SENTRY_EVENTS_PER_MINUTE + 5):
            await client.post("/client-events", json={"kind": "app_error", "message": f"distinct {number}"})
    logged = [r.getMessage() for r in caplog.records if r.name == "app.client_events"]
    assert sum("same thing" in m for m in logged) == 1
    assert len(logged) == 1 + client_events.SENTRY_EVENTS_PER_MINUTE + 5  # the log keeps every distinct one
    assert len(sent) == client_events.SENTRY_EVENTS_PER_MINUTE
