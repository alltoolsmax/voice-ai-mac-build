"""Màn hình khởi động NỀN TRONG SUỐT, có hiệu ứng động, cho Windows.

Cửa sổ "layered" của Windows (`UpdateLayeredWindow`) nhận ảnh BGRA có alpha từng điểm ảnh,
nên chỉ logo + sóng + chữ hiện ra, hình nền máy hiện xuyên qua - khác hẳn `--splash` của
PyInstaller (ảnh tĩnh, trong suốt kiểu 1-bit).

Một cửa sổ duy nhất chạy từ lúc mở app tới khi cửa sổ chính sẵn sàng:
  phase 0 (khởi động)  ->  phase 1 (nạp thư viện / mô hình), chuyển mượt.

An toàn: mọi lỗi (thiếu Pillow, không tạo được cửa sổ...) chỉ làm splash tự tắt, app vẫn
chạy như cũ. Cửa sổ không nhận chuột (click xuyên qua) và không chiếm tiêu điểm.
"""
from __future__ import annotations

import sys
import threading
import time

FPS = 30
FADE_SECONDS = 0.28


def _dpi_scale() -> float:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        try:
            dpi = user32.GetDpiForSystem()
        except AttributeError:
            hdc = user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            user32.ReleaseDC(0, hdc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


class NativeSplash:
    def __init__(self, logo_path=None):
        self._logo_path = logo_path
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._alive = False
        self._lock = threading.Lock()
        self._phase_target = 0.0
        self._status = "Đang khởi động"
        self._progress = 0.12
        self._t0 = time.monotonic()

    # ---- API an toàn đa luồng ----
    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        self._thread = threading.Thread(target=self._run, name="va-splash", daemon=True)
        self._thread.start()
        self._ready.wait(5.0)
        return self._alive

    @property
    def active(self) -> bool:
        return self._alive and not self._stop.is_set()

    def set_phase(self, phase: float) -> None:
        with self._lock:
            self._phase_target = float(phase)

    def set_status(self, text: str, progress: float | None = None) -> None:
        with self._lock:
            if text:
                self._status = text
            if progress is not None:
                self._progress = max(0.0, min(1.0, float(progress)))

    def close(self, wait: float = 1.5) -> None:
        self._stop.set()
        th = self._thread
        if th is not None and th.is_alive() and th is not threading.current_thread():
            th.join(wait)

    # ---- vòng lặp trong luồng riêng (cửa sổ + hàng đợi tin nhắn phải cùng một luồng) ----
    def _run(self) -> None:
        try:
            self._loop()
        except Exception:
            pass
        finally:
            self._alive = False
            self._ready.set()

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        from apps.splash_render import SplashRenderer, to_premultiplied_bgra

        scale = _dpi_scale()
        renderer = SplashRenderer(scale, self._logo_path)
        W, H = renderer.w, renderer.h

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HANDLE), ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HANDLE), ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                        ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                               ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                               ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                               ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                        wintypes.UINT, wintypes.UINT]
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

        def wndproc(hwnd, msg, wparam, lparam):
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = WNDPROC(wndproc)  # giữ tham chiếu để không bị thu hồi
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW()
        cls.lpfnWndProc = proc
        cls.hInstance = hinst
        cls.lpszClassName = "VoiceAIMrHuynhSplash"
        user32.RegisterClassW(ctypes.byref(cls))

        WS_POPUP = 0x80000000
        ex = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000 | 0x00000020  # LAYERED|TOPMOST|TOOLWINDOW|NOACTIVATE|TRANSPARENT
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x, y = max(0, (sw - W) // 2), max(0, (sh - H) // 2)
        hwnd = user32.CreateWindowExW(ex, cls.lpszClassName, "Voice AI", WS_POPUP, x, y, W, H,
                                      None, None, hinst, None)
        if not hwnd:
            return

        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = W
        bmi.bmiHeader.biHeight = -H  # từ trên xuống
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not hbm or not bits.value:
            user32.DestroyWindow(hwnd)
            return
        old = gdi32.SelectObject(hdc_mem, hbm)

        pt_dst, pt_src, size = wintypes.POINT(x, y), wintypes.POINT(0, 0), wintypes.SIZE(W, H)
        blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, alpha từng điểm ảnh

        def present(img, opacity: int = 255) -> None:
            data = to_premultiplied_bgra(img)
            ctypes.memmove(bits, data, len(data))
            blend.SourceConstantAlpha = opacity
            user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(size),
                                       hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), 2)

        def pump() -> None:
            msg = wintypes.MSG()
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        present(renderer.render(0.0, 0.0, 0.12, self._status))  # khung đầu trước khi hiện
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        self._alive = True
        self._ready.set()

        phase = 0.0
        shown_progress = 0.12
        last = time.monotonic()
        period = 1.0 / FPS
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                dt = now - last
                last = now
                with self._lock:
                    target, status, prog = self._phase_target, self._status, self._progress
                # chuyển cảnh mượt (~0.7 giây) và thanh tiến trình tiến dần, không giật
                step = dt / 0.7
                phase += max(-step, min(step, target - phase))
                shown_progress += (prog - shown_progress) * min(1.0, dt * 3.0)
                t = now - self._t0
                present(renderer.render(t, phase, shown_progress, status))
                pump()
                spent = time.monotonic() - now
                if spent < period:
                    time.sleep(period - spent)
            # mờ dần rồi tắt
            end = time.monotonic() + FADE_SECONDS
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    break
                present(renderer.render(time.monotonic() - self._t0, phase, shown_progress, status),
                        int(255 * left / FADE_SECONDS))
                pump()
                time.sleep(0.02)
        finally:
            user32.ShowWindow(hwnd, 0)
            user32.DestroyWindow(hwnd)
            gdi32.SelectObject(hdc_mem, old)
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_screen)
