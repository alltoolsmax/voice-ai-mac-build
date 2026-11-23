import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps import app_update as au
from apps.app_version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "config_path", lambda: tmp_path / "update-check.json")
    calls = []

    def fake_fetch():
        calls.append(1)
        return {"version": "9.0.0", "url": "https://mrhuynh.net/releases/tag/9.0.0",
                "published_at": "2026-10-01T00:00:00Z"}

    monkeypatch.setattr(au, "fetch_latest", fake_fetch)
    app = FastAPI()
    app.include_router(au.router)
    c = TestClient(app)
    c.calls = calls
    return c


def test_installer_version_matches_app_version():
    iss = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")
    assert re.search(r'#define AppVersion\s+"([^"]+)"', iss).group(1) == APP_VERSION


def test_parse_and_compare_versions():
    assert au.parse_version("v1.0.1") == (1, 0, 1)
    assert au.parse_version("1.2") == (1, 2, 0)
    assert au.parse_version("Voice AI - Mr.Huỳnh 2.0.0") == (2, 0, 0)
    assert au.parse_version("latest") == ()
    assert au.is_newer("1.0.10", "1.0.9")
    assert au.is_newer("v1.1.0", "1.0.1")
    assert not au.is_newer("1.0.0", "1.0.1")
    assert not au.is_newer("1.0.1", "1.0.1")
    assert not au.is_newer("", "1.0.1")


def test_always_on_cannot_be_turned_off(client):
    """Bắt buộc cập nhật (giống Video AI): không còn công tắc tắt kiểm tra bản mới."""
    body = client.get("/api/app/update").json()
    assert body["enabled"] is True and body["latest"] == "9.0.0"
    assert client.put("/api/app/update-check", json={"enabled": False}).json() == {"enabled": True}
    au._write({**au._read(), "enabled": False, "checked_at": 0})      # cấu hình cũ đã tắt
    body = client.get("/api/app/update").json()
    assert body["enabled"] is True and body["newer"] is True


def test_reports_newer_release(client):
    client.put("/api/app/update-check", json={"enabled": True})
    body = client.get("/api/app/update").json()
    assert body["current"] == APP_VERSION
    assert body["latest"] == "9.0.0"
    assert body["newer"] is True
    assert body["url"].endswith("/tag/9.0.0")
    assert body["error"] is None


def test_checks_github_at_most_once_a_day(client):
    client.put("/api/app/update-check", json={"enabled": True})
    client.get("/api/app/update")
    client.get("/api/app/update")
    assert len(client.calls) == 1
    client.get("/api/app/update?force=true")
    assert len(client.calls) == 2


def test_offline_returns_error_not_500(client, monkeypatch):
    def offline():
        raise OSError("no network")

    monkeypatch.setattr(au, "fetch_latest", offline)
    client.put("/api/app/update-check", json={"enabled": True})
    response = client.get("/api/app/update")
    assert response.status_code == 200
    body = response.json()
    assert body["newer"] is False and body["error"]


def test_same_version_is_not_newer(client, monkeypatch):
    monkeypatch.setattr(au, "fetch_latest", lambda: {"version": APP_VERSION, "url": au.RELEASES_PAGE,
                                                     "published_at": None})
    assert client.get("/api/app/update?force=true").json()["newer"] is False


def test_foreign_release_url_is_replaced(monkeypatch):
    monkeypatch.setattr(au, "UPDATE_URL", "https://active.example/api/app/version")
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"version": "2.0.0", "url": "http://evil.example/x"}'

    monkeypatch.setattr(au.urllib.request, "urlopen", lambda *a, **k: Response())
    assert au.fetch_latest()["url"] == au.RELEASES_PAGE


def test_update_endpoints_are_internal():
    from apps import web_stream

    paths = web_stream.app.openapi()["paths"]
    assert "/api/app/update" not in paths and "/api/app/update-check" not in paths
    assert any(getattr(r, "path", "") == "/api/app/update" for r in web_stream.app.routes)


def test_https_context_tin_ca_bo_chung_chi_certifi(monkeypatch):
    """Máy Windows thiếu gốc USERTrust ECC (chuỗi mới của api.github.com) vẫn kiểm tra
    được cập nhật: context nạp thêm certifi, và fetch_latest dùng context đó."""
    import certifi

    from apps.runtime_paths import https_context

    monkeypatch.setattr(au, "UPDATE_URL", "https://active.example/api/app/version")

    loaded = []
    monkeypatch.setattr("ssl.SSLContext.load_verify_locations",
                        lambda self, cafile=None, **k: loaded.append(cafile))
    https_context()
    assert certifi.where() in loaded  # cùng với kho chứng chỉ của hệ điều hành

    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"version": "9.9.9"}'

    def fake_urlopen(request, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(au.urllib.request, "urlopen", fake_urlopen)
    au.fetch_latest()
    assert seen.get("context") is not None


def test_highlights_lay_tieu_de_nhom_thay_doi():
    body = (
        "## Voice AI - Mr.Huỳnh 1.0.5\n\n**Cập nhật:** cài đè.\n\n"
        "### Giới hạn **VRAM** cho card 4 GB\n- chi tiết\n"
        "### [Lưu file](https://x) và mở file\n### Sửa lỗi\n#### không lấy\n"
        + "".join(f"### Mục {i}\n" for i in range(10))
    )
    assert au.highlights(body) == [
        "Giới hạn VRAM cho card 4 GB", "Lưu file và mở file", "Sửa lỗi",
        "Mục 0", "Mục 1", "Mục 2",
    ]
    assert au.highlights("") == []


def test_de_sau_khong_con_bo_qua_duoc_ban_moi(client):
    """Bắt buộc cập nhật: dù gọi update-skip (giao diện cũ), bản mới vẫn bắt cập nhật."""
    local = TestClient(client.app, base_url="http://127.0.0.1:8001")
    assert local.put("/api/app/update-skip", json={"version": "9.0.0"}).status_code == 200
    body = client.get("/api/app/update").json()
    assert body["newer"] is True and body["skipped"] is False


def test_trang_web_la_khong_bo_qua_duoc_cap_nhat(client):
    local = TestClient(client.app, base_url="http://127.0.0.1:8001")
    r = local.put("/api/app/update-skip", json={"version": "9.0.0"},
                  headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_no_release_repo_means_no_network(monkeypatch):
    """Ban doi ten chua co kho phat hanh rieng: khong duoc hoi may chu nao."""
    monkeypatch.setattr(au, "UPDATE_URL", "")
    monkeypatch.setattr(au.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("khong duoc ket noi mang"))
    with pytest.raises(RuntimeError):
        au.fetch_latest()


def _fake_urlopen(payload):
    import io, json as _json

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return lambda *a, **k: R(_json.dumps(payload).encode())


def test_mac_uses_url_mac_and_ignores_windows_zip(monkeypatch):
    body = {"version": "9.0.0", "url": "https://x.test/a.zip", "url_mac": "https://x.test/a.dmg", "sha256": "a" * 64, "signature": "b" * 80}
    monkeypatch.setattr(au.sys, "platform", "darwin")
    monkeypatch.setattr(au, "UPDATE_URL", "http://x.test/v")
    monkeypatch.setattr(au.urllib.request, "urlopen", _fake_urlopen(body))
    got = au.fetch_latest()
    assert got["version"] == "9.0.0" and got["url"] == "https://x.test/a.dmg"


def test_mac_without_dmg_link_reports_no_update(monkeypatch):
    body = {"version": "9.0.0", "url": "https://x.test/a.zip"}
    monkeypatch.setattr(au.sys, "platform", "darwin")
    monkeypatch.setattr(au, "UPDATE_URL", "http://x.test/v")
    monkeypatch.setattr(au.urllib.request, "urlopen", _fake_urlopen(body))
    assert au.fetch_latest()["version"] == ""


def test_windows_ignores_url_mac(monkeypatch):
    body = {"version": "9.0.0", "url": "https://x.test/a.zip", "url_mac": "https://x.test/a.dmg"}
    monkeypatch.setattr(au.sys, "platform", "win32")
    monkeypatch.setattr(au, "UPDATE_URL", "http://x.test/v")
    monkeypatch.setattr(au.urllib.request, "urlopen", _fake_urlopen(body))
    assert au.fetch_latest()["url"] == "https://x.test/a.zip"
