"""Thông báo popup do Mr.Huỳnh soạn trên máy chủ (admin.php). App lấy tối đa 1 lần/phút.

Máy chủ trả {"enabled": false} khi tắt hoặc hết hạn. Người dùng đóng thông báo nào thì id đó
được ghi vào %LOCALAPPDATA%/VoiceAIMrHuynh/announcement.json và không hiện lại cho tới khi id đổi.
Đường dẫn /api/app/announcement mở cả khi chưa kích hoạt, để người dùng thử/hết hạn vẫn thấy tin.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.remote_access import require_this_machine
from apps.runtime_paths import https_context

ANNOUNCE_URL = os.environ.get("VOICEAI_ANNOUNCE_URL", "https://active.mrhuynh.net/api/app/announcement")
CHECK_INTERVAL_SECONDS = 60
TIMEOUT_SECONDS = 8
_lock = threading.Lock()
router = APIRouter()


def _path() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / "VoiceAIMrHuynh" / "announcement.json"


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(state: dict) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            json.dump(state, f)
        os.replace(f.name, path)
    except OSError:
        pass


def _fetch() -> dict:
    request = urllib.request.Request(ANNOUNCE_URL, headers={"Accept": "application/json", "User-Agent": "Voice-AI-MrHuynh"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS,
                                context=https_context() if ANNOUNCE_URL.startswith("https") else None) as response:
        body = json.loads(response.read().decode("utf-8"))
    return clean(body)


def clean(body: object) -> dict:
    """Chỉ giữ các trường biết trước, cắt độ dài; link chỉ nhận https."""
    if not isinstance(body, dict) or not body.get("enabled") or not body.get("id"):
        return {"enabled": False}
    url = str(body.get("button_url") or "")
    secondary = body.get("secondary_text")
    return {
        "enabled": True,
        "id": str(body["id"])[:40],
        "badge": str(body.get("badge") or "")[:24],
        "title": str(body.get("title") or "")[:80],
        "body": str(body.get("body") or "")[:600],
        "button_text": str(body.get("button_text") or "")[:30],
        "button_url": url if url.startswith("https://") else "",
        "secondary_text": ("Để sau" if secondary is None else str(secondary))[:20],
        "expires_at": int(body.get("expires_at") or 0),
    }


def current(now: float | None = None) -> dict | None:
    """Thông báo đang hiệu lực mà người dùng chưa đóng, hoặc None."""
    now = time.time() if now is None else now
    with _lock:
        state = _read()
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else None
        checked = state.get("checked_at") if isinstance(state.get("checked_at"), (int, float)) else 0
        if latest is None or now - checked >= CHECK_INTERVAL_SECONDS or checked > now:
            try:
                latest = _fetch()
                state = {**state, "latest": latest, "checked_at": now}
                _write(state)
            except Exception:
                pass  # mất mạng: dùng bản đã lưu (nếu có)
        if not latest or not latest.get("enabled"):
            return None
        if latest["expires_at"] and latest["expires_at"] < now:
            return None
        if latest["id"] in (state.get("dismissed") or []):
            return None
        return latest


VIDEO_URL = os.environ.get("VOICEAI_VIDEO_URL", "https://active.mrhuynh.net/api/app/video")
VIDEO_CHECK_SECONDS = 300
_video_cache: dict = {"url": "", "at": 0.0}


def video_url(now: float | None = None) -> str:
    """Link video hướng dẫn do admin đặt (chỉ https); rỗng nếu chưa đặt hoặc mất mạng lần đầu."""
    now = time.time() if now is None else now
    with _lock:
        if now - _video_cache["at"] >= VIDEO_CHECK_SECONDS or _video_cache["at"] > now:
            try:
                request = urllib.request.Request(VIDEO_URL, headers={"Accept": "application/json", "User-Agent": "Voice-AI-MrHuynh"})
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS,
                                            context=https_context() if VIDEO_URL.startswith("https") else None) as response:
                    body = json.loads(response.read().decode("utf-8"))
                url = str(body.get("url") or "") if isinstance(body, dict) else ""
                _video_cache.update(url=url if url.startswith("https://") else "", at=now)
            except Exception:
                _video_cache["at"] = now - VIDEO_CHECK_SECONDS + 30  # lỗi mạng: thử lại sau 30 giây, giữ link cũ
        return _video_cache["url"]


@router.get("/api/app/video")
def get_video():
    return {"url": video_url()}


class DismissBody(BaseModel):
    id: str


@router.get("/api/app/announcement")
def get_announcement():
    return {"announcement": current()}


@router.post("/api/app/announcement/dismiss", dependencies=[Depends(require_this_machine)])
def dismiss_announcement(body: DismissBody):
    with _lock:
        state = _read()
        dismissed = [str(i) for i in (state.get("dismissed") or [])][-49:]
        if body.id not in dismissed:
            dismissed.append(body.id[:40])
        _write({**state, "dismissed": dismissed})
    return {"ok": True}
