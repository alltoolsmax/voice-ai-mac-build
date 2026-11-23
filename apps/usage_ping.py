"""Báo máy chủ của Mr.Huỳnh "phần mềm đang mở" để trang quản trị đếm số máy đã cài / đang hoạt động.

- Gửi một GET tới active.mrhuynh.net: mã máy (MH-XXXX…, đã băm từ định danh máy, không chứa
  thông tin cá nhân), phiên bản, hệ điều hành, trạng thái bản quyền (licensed / trial / expired).
- Lúc mở ứng dụng (sau 20 giây) và mỗi 30 phút khi ứng dụng còn mở.
- Không gửi văn bản, audio hay thông tin cá nhân. Lỗi mạng: bỏ qua, không thử lại dồn dập.
- Đi cùng công tắc "Kiểm tra bản mới" trong Cài đặt: tắt công tắc đó thì không báo.
"""
from __future__ import annotations

import os
import sys
import threading
import urllib.parse
import urllib.request

from apps.app_version import APP_VERSION

USAGE_URL = os.environ.get("VOICEAI_USAGE_URL", "https://active.mrhuynh.net/video/v1/app/ping")
FIRST_DELAY_SECONDS = 20
INTERVAL_SECONDS = 30 * 60
TIMEOUT_SECONDS = 8

_started = False
_lock = threading.Lock()


def _os_name() -> str:
    return "mac" if sys.platform == "darwin" else "win"


def build_url(kind: str = "") -> str:
    from apps import license as lic
    try:
        st = lic.status()
        state = str(st.get("state") or "")
        machine = str(st.get("machine_id") or "")
    except Exception:
        state = ""
        machine = lic.machine_id()
    q = {"p": "voice", "m": machine, "v": APP_VERSION, "os": _os_name(), "tier": state}
    if kind:
        q["k"] = kind
    return USAGE_URL + ("&" if "?" in USAGE_URL else "?") + urllib.parse.urlencode(q)


def ping(kind: str = "") -> bool:
    """Gửi 1 lần. Trả True nếu máy chủ nhận."""
    if not USAGE_URL.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        return False
    from apps import app_update
    if not app_update.is_enabled():
        return False
    try:
        from apps.runtime_paths import https_context
        ctx = https_context() if USAGE_URL.startswith("https") else None
        req = urllib.request.Request(build_url(kind), headers={"User-Agent": f"Voice-AI-MrHuynh/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as r:
            r.read(200)
        return True
    except Exception:
        return False


def _loop(stop: threading.Event) -> None:
    if stop.wait(FIRST_DELAY_SECONDS):
        return
    ping("open")                         # lần mở phần mềm
    while not stop.wait(INTERVAL_SECONDS):
        ping()


def start() -> threading.Event | None:
    """Chạy luồng nền (gọi 1 lần lúc khởi động). Test đặt VOICEAI_NO_USAGE_PING=1 để tắt."""
    global _started
    if os.getenv("VOICEAI_NO_USAGE_PING") == "1":
        return None
    with _lock:
        if _started:
            return None
        _started = True
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="usage-ping", daemon=True).start()
    return stop
