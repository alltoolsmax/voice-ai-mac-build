import sys

import pytest

pytest.importorskip("PIL")
pytest.importorskip("numpy")

from apps import desktop_app
from apps.splash_native import NativeSplash
from apps.splash_render import SplashRenderer, to_premultiplied_bgra


@pytest.fixture(scope="module")
def renderer():
    return SplashRenderer(1.0)


def test_frame_is_rounded_dark_blue_window(renderer):
    img = renderer.render(3.0, 0.0, 0.4, "Đang khởi động")
    assert img.mode == "RGBA" and img.size == (renderer.w, renderer.h)
    # bốn góc ngoài khung bo tròn trong suốt; bên trong nền xanh tối đặc
    for xy in ((0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)):
        assert img.getpixel(xy)[3] == 0
    r, g, b, a = img.getpixel((60, 60))
    assert a == 255 and b > r and b > g and max(r, g, b) < 120  # xanh tối


@pytest.mark.parametrize("phase", [0.0, 0.5, 1.0])
def test_all_phases_render_and_move(renderer, phase):
    a = renderer.render(3.0, phase, 0.5, "Đang nạp thư viện giọng nói")
    b = renderer.render(3.4, phase, 0.5, "Đang nạp thư viện giọng nói")
    assert a.tobytes() != b.tobytes()  # có chuyển động thật


def test_logo_is_missing_safe():
    r = SplashRenderer(1.0, logo_path="/không/có/file.png")
    assert r.logo is None
    assert r.render(1.0, 0.0, 0.1, "x").size == (r.w, r.h)


def test_premultiplied_bgra_format(renderer):
    img = renderer.render(3.0, 1.0, 0.5, "Đang nạp")
    data = to_premultiplied_bgra(img)
    assert len(data) == img.width * img.height * 4
    r, g, b, a = img.getpixel((img.width // 2, img.height // 2))
    off = ((img.height // 2) * img.width + img.width // 2) * 4
    assert data[off + 3] == a
    assert abs(data[off + 2] - (r * a + 127) // 255) <= 1  # kênh đỏ nằm ở byte thứ 3 (BGRA)
    assert data[off] <= a and data[off + 1] <= a and data[off + 2] <= a  # nhân sẵn alpha


def test_scale_changes_size():
    assert SplashRenderer(1.5).w > SplashRenderer(1.0).w


@pytest.mark.skipif(sys.platform == "win32", reason="Windows có cửa sổ thật")
def test_native_splash_off_on_non_windows():
    assert NativeSplash().start() is False


def test_splash_update_without_native_splash_defers_to_web(monkeypatch):
    monkeypatch.setattr(desktop_app, "_NATIVE_SPLASH", None)
    assert desktop_app.DesktopApi().splash_update("x", "starting", 0.3) is False


def test_splash_update_drives_native_splash(monkeypatch):
    calls = []

    class Fake:
        active = True

        def set_phase(self, p):
            calls.append(("phase", p))

        def set_status(self, text, progress=None):
            calls.append(("status", text, progress))

    api = desktop_app.DesktopApi()
    revealed = []
    api.on_ready = lambda: revealed.append(1)
    monkeypatch.setattr(desktop_app, "_NATIVE_SPLASH", Fake())
    assert api.splash_update("Đang nạp mô hình", "starting", 0.34) is True
    assert ("status", "Đang nạp mô hình", 0.34) in calls and not revealed
    # xong hoặc lỗi: hiện cửa sổ chính, và giao diện tự vẽ phần còn lại
    assert api.splash_update("", "ready", 1) is False and revealed == [1]
    assert api.splash_update("lỗi", "failed", 0) is False and revealed == [1, 1]
