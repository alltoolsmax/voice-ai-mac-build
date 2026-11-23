"""Báo số máy đang dùng cho trang quản trị: chỉ mã máy (đã băm), phiên bản, hệ điều hành, trạng thái bản quyền."""
from urllib.parse import parse_qs, urlparse

from apps import app_update, usage_ping
from apps.app_version import APP_VERSION


def test_ping_sends_only_hashed_machine_version_os_state(monkeypatch, tmp_path):
    monkeypatch.setattr(app_update, "config_path", lambda: tmp_path / "update-check.json")
    seen = []

    class R:
        def read(self, n=-1): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=0, context=None):
        seen.append(req.full_url)
        return R()
    monkeypatch.setattr(usage_ping.urllib.request, "urlopen", fake_open)
    assert usage_ping.ping("open")
    u = urlparse(seen[-1])
    q = parse_qs(u.query)
    assert u.netloc == "active.mrhuynh.net" and u.path.endswith("/v1/app/ping")
    assert set(q) == {"p", "m", "v", "os", "tier", "k"}
    assert q["p"] == ["voice"] and q["v"] == [APP_VERSION] and q["k"] == ["open"]
    assert q["m"][0].startswith("MH-") and q["tier"][0] in ("licensed", "trial", "expired")
    # không còn công tắc: đặt enabled=false kiểu cũ vẫn báo
    app_update._write({"enabled": False})
    assert usage_ping.ping()


def test_ping_network_error_is_silent(monkeypatch, tmp_path):
    monkeypatch.setattr(app_update, "config_path", lambda: tmp_path / "update-check.json")

    def boom(*a, **k):
        raise OSError("mất mạng")
    monkeypatch.setattr(usage_ping.urllib.request, "urlopen", boom)
    assert usage_ping.ping() is False


def test_start_disabled_in_tests():
    assert usage_ping.start() is None
