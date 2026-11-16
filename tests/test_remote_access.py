import json

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from apps import remote_access as ra

LAN = ("192.168.1.20", 50000)
LOCAL = ("127.0.0.1", 50000)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "remote-access.json"
    monkeypatch.setattr(ra, "config_path", lambda: path)
    monkeypatch.delenv(ra.LISTEN_ENV, raising=False)
    ra.reset_cache()
    yield path
    ra.reset_cache()


def _app():
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(ra.RemoteAccessMiddleware)
    app.include_router(ra.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/tts/generate")
    def generate():
        return {"ok": True}

    @app.get("/api/history")
    def history():
        return []

    @app.get("/openapi-like")
    def other():
        return {}

    return app


def _client(peer, **kw):
    return TestClient(_app(), client=peer, base_url="http://127.0.0.1:8001", **kw)


def _enable():
    return ra._update(enabled=True)


def test_first_read_creates_key_and_defaults_off(cfg):
    state = ra.current()
    assert state["enabled"] is False
    assert state["api_key"].startswith("voiceai_") and len(state["api_key"]) > 30
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved == state
    ra.reset_cache()
    assert ra.current()["api_key"] == state["api_key"]  # khoa giu nguyen sau khi mo lai app


def test_corrupt_file_falls_back_to_off(cfg):
    cfg.write_text("{hong", encoding="utf-8")
    assert ra.current()["enabled"] is False


def test_local_requests_untouched_without_key(cfg):
    c = _client(LOCAL)
    assert c.get("/health").status_code == 200
    assert c.get("/api/history").status_code == 200


def test_remote_blocked_when_disabled(cfg):
    r = _client(LAN).get("/health")
    assert r.status_code == 403
    assert "đang tắt" in r.json()["detail"]


def test_remote_needs_key(cfg):
    key = _enable()["api_key"]
    c = _client(LAN)
    assert c.get("/health").status_code == 401
    assert c.get("/health", headers={"X-API-Key": "sai"}).status_code == 401
    assert c.get("/health", headers={"X-API-Key": key}).status_code == 200
    assert c.get("/health", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert c.get(f"/health?api_key={key}").status_code == 200
    assert c.post("/api/tts/generate", headers={"X-API-Key": key}).status_code == 200


def test_remote_cannot_reach_internal_api_even_with_key(cfg):
    key = _enable()["api_key"]
    c = _client(LAN)
    for path in ("/api/history", "/api/remote-access", "/", "/openapi-like"):
        assert c.get(path, headers={"X-API-Key": key}).status_code == 404, path
    assert c.post("/api/remote-access/regenerate-key", headers={"X-API-Key": key}).status_code == 404


def test_proxy_forwarded_request_counts_as_remote(cfg):
    # ngrok / Cloudflare Tunnel ket noi tu 127.0.0.1 nhung mang header chuyen tiep.
    c = _client(LOCAL)
    assert c.get("/health", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403
    key = _enable()["api_key"]
    assert c.get("/api/history", headers={"X-Forwarded-For": "8.8.8.8", "X-API-Key": key}).status_code == 404
    assert c.get("/health", headers={"Forwarded": "for=1.2.3.4", "X-API-Key": key}).status_code == 200


def test_ipv4_mapped_loopback_is_local(cfg):
    assert _client(("::ffff:127.0.0.1", 1)).get("/api/history").status_code == 200
    assert _client(("::1", 1)).get("/api/history").status_code == 200


def test_cors_preflight_passes_without_key(cfg):
    _enable()
    r = _client(LAN).options(
        "/api/tts/generate",
        headers={"Origin": "http://192.168.1.20:3000", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"]


def test_error_responses_readable_by_browsers(cfg):
    r = _client(LAN).get("/health")
    assert r.headers["access-control-allow-origin"] == "*"


def test_disable_takes_effect_immediately(cfg):
    key = _enable()["api_key"]
    c = _client(LAN)
    assert c.get("/health", headers={"X-API-Key": key}).status_code == 200
    assert _client(LOCAL).put("/api/remote-access", json={"enabled": False}).status_code == 200
    assert c.get("/health", headers={"X-API-Key": key}).status_code == 403


def test_settings_api_toggle_and_regenerate(cfg):
    c = _client(LOCAL)
    body = c.get("/api/remote-access").json()
    assert body["enabled"] is False and body["listening_all"] is False
    assert body["port"] == 8001 and isinstance(body["addresses"], list)
    old = body["api_key"]
    assert c.put("/api/remote-access", json={"enabled": True}).json()["enabled"] is True
    new = c.post("/api/remote-access/regenerate-key").json()["api_key"]
    assert new != old
    lan = _client(LAN)
    assert lan.get("/health", headers={"X-API-Key": old}).status_code == 401
    assert lan.get("/health", headers={"X-API-Key": new}).status_code == 200
    ra.reset_cache()
    assert (ra.current()["enabled"], ra.current()["api_key"]) == (True, new)


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "http://192.168.1.50:8001"},
        {"Host": "evil.example:8001"},  # DNS rebinding
    ],
)
def test_foreign_web_pages_cannot_read_or_change_key(cfg, headers):
    c = _client(LOCAL)
    assert c.get("/api/remote-access", headers=headers).status_code == 403
    assert c.put("/api/remote-access", json={"enabled": True}, headers=headers).status_code == 403
    assert ra.current()["enabled"] is False


@pytest.mark.parametrize(
    "origin", ["http://127.0.0.1:8001", "http://localhost:1420"]
)
def test_app_origins_allowed(cfg, origin):
    assert _client(LOCAL).get("/api/remote-access", headers={"Origin": origin}).status_code == 200


def test_listen_host_follows_setting(cfg):
    assert ra.listen_host() == "127.0.0.1"
    _enable()
    assert ra.listen_host() == "0.0.0.0"
    ra.mark_listening("0.0.0.0")
    assert ra.is_listening_all()


def test_public_paths_match_openapi():
    from apps.web_stream import app

    documented = set(app.openapi()["paths"]) - {"/voice-ai-mrhuynh.md"}
    assert documented == set(ra.PUBLIC_PATHS)


# ---- Chế độ điện thoại (PIN + cookie) ----

def _phone_client():
    ra._update(enabled=True, phone_enabled=True)
    return _client(LAN, follow_redirects=False)


def _login(c):
    pin = ra.current()["phone_pin"]
    return c.post("/phone/login", data={"pin": pin})


def test_phone_off_by_default_and_state_has_pin(cfg):
    st = ra.current()
    assert st["phone_enabled"] is False
    assert len(st["phone_pin"]) == 6 and st["phone_pin"].isdigit()
    ra._update(enabled=True)
    assert _client(LAN).get("/phone").status_code == 404


def test_phone_root_redirects_to_login_without_cookie(cfg):
    c = _phone_client()
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/phone"
    assert "PIN" in c.get("/phone").text


def test_phone_wrong_pin_rejected_and_locks_after_five(cfg):
    c = _phone_client()
    for _ in range(5):
        assert c.post("/phone/login", data={"pin": "000000" if ra.current()["phone_pin"] != "000000" else "111111"}).status_code == 401
    assert _login(c).status_code == 429


def test_phone_pin_login_grants_ui_but_not_settings(cfg):
    c = _phone_client()
    r = _login(c)
    assert r.status_code == 303 and "va_phone=" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert c.get("/api/history").status_code == 200
    assert c.post("/api/tts/generate").status_code == 200
    # cài đặt / khoá API không bao giờ mở cho điện thoại
    assert c.get("/api/remote-access").status_code == 404
    assert c.put("/api/remote-access", json={"enabled": False}).status_code == 404
    assert c.post("/api/app/restart").status_code == 404
    assert c.delete("/api/history").status_code == 404


def test_phone_cookie_dies_when_pin_regenerated_or_feature_off(cfg):
    c = _phone_client()
    _login(c)
    assert c.get("/api/history").status_code == 200
    ra._update(phone_pin=ra.new_pin(), phone_secret="x" * 32)
    assert c.get("/api/history").status_code == 404
    _login(c)
    ra._update(phone_enabled=False)
    assert c.get("/api/history").status_code == 404


def test_phone_mode_keeps_api_key_flow(cfg):
    c = _phone_client()
    key = ra.current()["api_key"]
    assert c.get("/health", headers={"X-API-Key": key}).status_code == 200
    assert c.get("/health").status_code == 401


def test_phone_settings_endpoints_local_only(cfg):
    c = _client(LOCAL)
    r = c.put("/api/remote-access", json={"phone_enabled": True})
    assert r.status_code == 200 and r.json()["phone_enabled"] is True and len(r.json()["phone_pin"]) == 6
    old = r.json()["phone_pin"]
    r2 = c.post("/api/remote-access/regenerate-pin")
    assert r2.status_code == 200 and r2.json()["phone_pin"] != old or len(r2.json()["phone_pin"]) == 6
