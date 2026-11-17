"""Kiểm tra bản mới từ máy chủ của Mr.Huỳnh (active.mrhuynh.net). Chỉ BÁO, không tự tải hay tự cài.

- Có bản mới: giao diện bật hộp thoại (tên các nhóm thay đổi lấy từ tiêu đề `###`
  của ghi chú phát hành). "Để sau" ghi `skipped` = bản đó, hộp thoại không bật lại
  cho tới bản kế tiếp; thanh báo nhỏ và nút kiểm tra tay vẫn còn.

- Lúc mở app, giao diện gọi GET /api/app/update. Server hỏi máy chủ phát hành tối đa một lần
  mỗi 5 phút (kết quả lưu ở %LOCALAPPDATA%\\VoiceAIMrHuynh\\update-check.json), chờ tối
  đa 5 giây; mất mạng thì trả `error`, giao diện im lặng.
- MẶC ĐỊNH BẬT (để người dùng biết có bản mới và biểu phí mới). Tắt được bằng
  PUT /api/app/update-check; khi tắt, chỉ nút kiểm tra tay (force=1) mới hỏi máy chủ.
- Chỉ gửi một GET tới máy chủ phát hành, không kèm văn bản, audio hay thông tin máy.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps import update_installer
from apps.app_version import APP_VERSION
from apps.remote_access import require_this_machine
from apps.runtime_paths import https_context

# Máy chủ phát hành: trả JSON {"version", "url", "highlights"} (file version.json trên hosting).
UPDATE_URL = os.environ.get("VOICEAI_UPDATE_URL", "https://active.mrhuynh.net/api/app/version")
RELEASES_PAGE = "https://zalo.me/0979007367"
CHECK_INTERVAL_SECONDS = 5 * 60
TIMEOUT_SECONDS = 5
MAX_HIGHLIGHTS = 6
_MARKDOWN = re.compile(r"[*_`]|\[([^\]]*)\]\([^)]*\)")

_lock = threading.Lock()


def config_path() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / "VoiceAIMrHuynh" / "update-check.json"


def parse_version(text: str) -> tuple[int, ...]:
    """"v1.0.1", "1.0.1", "Voice AI - Mr.Huỳnh 1.2" -> (1, 0, 1) / (1, 2, 0). Không có số -> ()."""
    numbers = [int(n) for n in re.findall(r"\d+", text or "")[:3]]
    return tuple(numbers + [0] * (3 - len(numbers))) if numbers else ()


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    new, old = parse_version(latest), parse_version(current)
    return bool(new) and new > old


def _read() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(state: dict) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            json.dump(state, file)
        os.replace(file.name, path)
    except OSError:
        pass  # Không ghi được: lần mở sau hỏi lại GitHub, không sao.


def is_enabled() -> bool:
    return _read().get("enabled") is not False


def highlights(body: str) -> list[str]:
    """Các mục `### Tiêu đề` của ghi chú phát hành, bỏ ký hiệu markdown: hộp thoại
    "Có bản mới" chỉ liệt kê tên nhóm thay đổi, chi tiết xem trên trang Releases."""
    out = []
    for line in (body or "").splitlines():
        if line.startswith("### "):
            title = _MARKDOWN.sub(lambda m: m.group(1) or "", line[4:]).strip()
            if title:
                out.append(title[:80])
        if len(out) == MAX_HIGHLIGHTS:
            break
    return out


def fetch_latest() -> dict:
    """{"version", "url", "published_at", "highlights"} của bản mới nhất theo máy chủ phát hành."""
    if not UPDATE_URL:
        raise RuntimeError("Chưa cấu hình máy chủ phát hành")
    request = urllib.request.Request(UPDATE_URL, headers={
        "Accept": "application/json",
        "User-Agent": f"Voice-AI-MrHuynh/{APP_VERSION}",
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS,
                                context=https_context() if UPDATE_URL.startswith("https") else None) as response:
        body = json.loads(response.read().decode("utf-8"))
    url = str(body.get("url") or "")
    version = str(body.get("version") or "")
    if sys.platform == "darwin":
        # macOS: bản Windows (.zip/.exe) vô dụng. Dùng link .dmg riêng (url_mac); chưa có thì
        # coi như chưa có bản mới cho Mac. Mở link để tải thủ công, không tự cài đè.
        url = str(body.get("url_mac") or "")
        if not url.startswith("https://"):
            version = ""
    # Chỉ mở liên kết https; link lạ thì dùng trang liên hệ mặc định.
    if not url.startswith("https://"):
        url = RELEASES_PAGE
    notes = body.get("highlights")
    return {"version": version, "url": url,
            "sha256": str(body.get("sha256") or "")[:64], "signature": str(body.get("signature") or "")[:128],
            "published_at": None,
            "highlights": [str(n)[:80] for n in notes][:MAX_HIGHLIGHTS] if isinstance(notes, list) else []}


def _result(latest: dict | None, *, checked_at: float | None, error: str | None = None) -> dict:
    version = (latest or {}).get("version") or None
    notes = (latest or {}).get("highlights")
    return {
        "current": APP_VERSION,
        "enabled": is_enabled(),
        "latest": version,
        "newer": bool(version) and is_newer(version),
        "url": (latest or {}).get("url") or RELEASES_PAGE,
        "published_at": (latest or {}).get("published_at"),
        "checked_at": checked_at,
        "error": error,
        "highlights": [str(n) for n in notes][:MAX_HIGHLIGHTS] if isinstance(notes, list) else [],
        # Người dùng bấm "Để sau" ở hộp thoại của đúng bản này: không bật hộp thoại
        # nữa (thanh báo nhỏ vẫn hiện) cho tới khi có bản mới hơn.
        "skipped": bool(version) and _read().get("skipped") == version,
        # Cập nhật tự động chỉ khi version.json có đủ sha256 + chữ ký + link .exe và đang chạy bản đã cài.
        "auto_install": bool(
            latest and latest.get("sha256") and latest.get("signature")
            and update_installer.is_installer_url(str(latest.get("url") or ""))
            and update_installer.can_auto_install()
        ),
    }


def check(force: bool = False) -> dict:
    with _lock:
        state = _read()
        cached = state.get("latest") if isinstance(state.get("latest"), dict) else None
        checked_at = state.get("checked_at") if isinstance(state.get("checked_at"), (int, float)) else None
        if not force:
            if state.get("enabled") is False:
                return _result(None, checked_at=None)
            if cached and checked_at and time.time() - checked_at < CHECK_INTERVAL_SECONDS:
                return _result(cached, checked_at=checked_at)
        try:
            latest = fetch_latest()
        except Exception:
            return _result(cached, checked_at=checked_at,
                           error="Không kiểm tra được bản mới (máy chưa có mạng hoặc máy chủ không phản hồi).")
        now = time.time()
        _write({**state, "latest": latest, "checked_at": now})
        return _result(latest, checked_at=now)


router = APIRouter()


@router.get("/api/app/update")
def get_update(force: bool = False):
    return check(force)


class UpdateCheckSettings(BaseModel):
    enabled: bool


@router.put("/api/app/update-check")
def set_update_check(settings: UpdateCheckSettings):
    with _lock:
        _write({**_read(), "enabled": settings.enabled})
    return {"enabled": is_enabled()}


class UpdateSkip(BaseModel):
    version: str


@router.put("/api/app/update-skip", dependencies=[Depends(require_this_machine)])
def skip_update(body: UpdateSkip):
    with _lock:
        _write({**_read(), "skipped": body.version[:40]})
    return {"skipped": body.version[:40]}


@router.post("/api/app/update-install", dependencies=[Depends(require_this_machine)])
def install_update():
    """Bắt đầu tải bản mới (đã kiểm chữ ký); tiến trình xem ở GET cùng đường dẫn."""
    from fastapi import HTTPException
    if not update_installer.can_auto_install():
        raise HTTPException(400, "Cập nhật tự động chỉ dùng được với bản đã cài trên Windows.")
    state = _read()
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else None
    if not latest or not is_newer(str(latest.get("version") or "")):
        raise HTTPException(400, "Chưa có bản mới để cập nhật.")
    try:
        return update_installer.start_download(latest)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/app/update-install", dependencies=[Depends(require_this_machine)])
def install_update_status():
    return update_installer.status()


@router.post("/api/app/update-launch", dependencies=[Depends(require_this_machine)])
def launch_update():
    from fastapi import HTTPException
    try:
        update_installer.launch_installer()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"launching": True}
