"""Giấy phép Voice AI - Mr.Huỳnh: dùng thử 3 ngày, sau đó cần key (1 tháng, 3 tháng, 1 năm
hoặc vĩnh viễn) gắn với máy. Mua trực tiếp trong app (chuyển khoản/SePay) hoặc nhập key thủ công.

- Mã máy: băm từ định danh máy (Windows MachineGuid...), dạng MH-XXXX-XXXX-XXXX-XXXX.
- Key: chữ ký Ed25519 của Mr.Huỳnh trên Mã máy. App chỉ giữ khoá công khai nên chỉ
  kiểm tra được key, không tự tạo được key. Key của máy này không chạy trên máy khác.
- Dùng thử: mốc bắt đầu được ký (HMAC gắn với máy) và lưu ở nhiều nơi; phát hiện
  chỉnh đồng hồ lùi và file bị sửa. Xoá sạch mọi nơi lưu thì đặt lại được; đây là giới
  hạn của mọi cơ chế kiểm tra offline.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps import license_codec as codec
from apps.license_pubkey import PUBLIC_KEY_HEX

TRIAL_SECONDS = 3 * 24 * 3600
CLOCK_SLACK = 300  # cho phép lệch đồng hồ 5 phút
CONTACT = {
    "zalo": "https://zalo.me/0979007367",
    "zalo_label": "Mr Huỳnh",
    "facebook": "https://facebook.com/mr.huynhxuyenson",
    "facebook_label": "Facebook",
}
# Máy chủ bán gói (PHP trên hosting của Mr.Huỳnh). Đổi bằng biến môi trường khi thử nghiệm.
SERVER_URL = os.environ.get("VOICEAI_LICENSE_SERVER", "https://active.mrhuynh.net").rstrip("/")
SERVER_TIMEOUT = 12
_STATE_SECRET = b"VoiceAI-MrHuynh-trial-state-v1"
_REG_PATH = r"Software\VoiceAIMrHuynh"
_lock = threading.Lock()
_licensed_cache: dict[str, bool] = {}


# ---------------------------------------------------------------- Mã máy

def _raw_machine_id() -> str:
    override = os.environ.get("VOICEAI_MACHINE_ID_RAW")
    if override:
        return override
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            ) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if Path(p).is_file():
                v = Path(p).read_text().strip()
                if v:
                    return v
        if sys.platform == "darwin":
            import subprocess

            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, timeout=5
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
    except Exception:
        pass
    return "node-%012x" % uuid.getnode()


def machine_bytes() -> bytes:
    return hashlib.sha256(b"VoiceAI-MrHuynh|" + _raw_machine_id().encode()).digest()[:8]


def machine_id() -> str:
    return codec.format_machine_id(machine_bytes())


# ---------------------------------------------------------------- Nơi lưu trạng thái

def _dirs() -> list[Path]:
    override = os.environ.get("VOICEAI_LICENSE_DIR")
    if override:
        return [Path(override) / "a", Path(override) / "b"]
    primary = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "VoiceAIMrHuynh"
    if sys.platform == "win32":
        second = Path(os.getenv("PROGRAMDATA") or r"C:\ProgramData") / "VoiceAIMrHuynh"
    else:
        second = Path.home() / ".config" / "voiceai-mrhuynh"
    return [primary, second]


def _sign(blob: bytes) -> str:
    key = _STATE_SECRET + machine_bytes()
    return hmac.new(key, blob, hashlib.sha256).hexdigest()


def _pack(obj: dict) -> str:
    blob = base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode())
    return blob.decode() + "." + _sign(blob)


def _unpack(text: str):
    """Trả dict, hoặc None nếu hỏng/bị sửa/của máy khác."""
    try:
        blob, mac = text.strip().rsplit(".", 1)
        if not hmac.compare_digest(mac, _sign(blob.encode())):
            return None
        return json.loads(base64.urlsafe_b64decode(blob.encode()))
    except Exception:
        return None


def _read_all(name: str) -> list[str]:
    out: list[str] = []
    for d in _dirs():
        try:
            f = d / name
            if f.is_file():
                out.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    if sys.platform == "win32" and not os.environ.get("VOICEAI_LICENSE_DIR"):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
                out.append(str(winreg.QueryValueEx(k, name)[0]))
        except Exception:
            pass
    return out


def _write_all(name: str, text: str) -> None:
    for d in _dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(text, encoding="utf-8")
        except Exception:
            pass
    if sys.platform == "win32" and not os.environ.get("VOICEAI_LICENSE_DIR"):
        try:
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, text)
        except Exception:
            pass


# ---------------------------------------------------------------- Key

def _inspect(key: str):
    return codec.inspect_key(bytes.fromhex(PUBLIC_KEY_HEX), key, machine_bytes())


def _norm(key: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (key or "").upper())


def _stored_valid_key() -> str | None:
    for text in _read_all("license.key"):
        data = _unpack(text)
        key = (data or {}).get("key")
        if not key:
            continue
        if key in _licensed_cache:
            if _licensed_cache[key]:
                return key
            continue
        ok, _, info = _inspect(key)
        ok = ok and info["type"] == codec.TYPE_LIFETIME
        _licensed_cache[key] = ok
        if ok:
            return key
    return None


def _ent_load():
    """Gói có thời hạn đã kích hoạt: (dict | None, bị_sửa: bool)."""
    states, tampered = [], False
    for text in _read_all("entitlement.dat"):
        data = _unpack(text)
        if (
            isinstance(data, dict)
            and data.get("m") == machine_id()
            and isinstance(data.get("exp"), (int, float))
            and isinstance(data.get("last"), (int, float))
        ):
            states.append(data)
        else:
            tampered = True
    if not states:
        return None, tampered
    return {
        "exp": max(s["exp"] for s in states),
        "last": max(s["last"] for s in states),
        "pt": max(states, key=lambda s: s["exp"]).get("pt"),
        "used": sorted({u for s in states for u in (s.get("used") or [])}),
    }, tampered


def _ent_save(ent: dict) -> None:
    _write_all("entitlement.dat", _pack({"m": machine_id(), **ent}))


def _fmt_date(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def activate(key: str, now: float | None = None):
    """Kiểm tra và lưu key. Gói có thời hạn được CỘNG DỒN vào hạn hiện tại. Trả (ok, thông báo)."""
    now = time.time() if now is None else now
    with _lock:
        ok, msg, info = _inspect(key)
        if not ok:
            return False, msg
        if info["type"] == codec.TYPE_LIFETIME:
            _licensed_cache[key] = True
            _write_all("license.key", _pack({"key": key, "t": int(now)}))
            return True, "Kích hoạt thành công. Cảm ơn bạn đã ủng hộ Voice AI - Mr.Huỳnh!"
        if _stored_valid_key():
            return False, "Máy này đã có bản quyền vĩnh viễn, không cần thêm gói."
        age = (datetime.date.fromtimestamp(now) - info["issued"]).days
        if age > codec.ACTIVATION_WINDOW_DAYS:
            return False, f"Key đã quá hạn kích hoạt (quá {codec.ACTIVATION_WINDOW_DAYS} ngày kể từ ngày cấp). Vui lòng liên hệ Mr.Huỳnh."
        ent, tampered = _ent_load()
        ent = ent or {"exp": 0.0, "last": now, "used": []}
        if now < ent["last"] - CLOCK_SLACK:
            return False, "Đồng hồ máy đang bị lùi. Vui lòng chỉnh đúng giờ rồi thử lại."
        tag = hashlib.sha256(_norm(key).encode()).hexdigest()[:16]
        if tag in ent["used"]:
            return False, "Key này đã được kích hoạt trên máy này rồi."
        base = max(now, ent["exp"])
        ent["exp"] = base + info["days"] * 86400
        ent["last"] = max(ent["last"], now)
        ent["pt"] = info["type"]  # loại gói gần nhất, để app hiện "Đang dùng: Gói ..."
        ent["used"] = (ent["used"] + [tag])[-50:]
        _ent_save(ent)
        return True, f"Đã kích hoạt gói {codec.PLAN_NAMES[info['type']]}. Hạn sử dụng đến {_fmt_date(ent['exp'])}."


# ---------------------------------------------------------------- Dùng thử

def _trial(now: float) -> dict:
    states = []
    tampered = False
    for text in _read_all("trial.dat"):
        data = _unpack(text)
        if (
            isinstance(data, dict)
            and data.get("m") == machine_id()
            and isinstance(data.get("first"), (int, float))
            and isinstance(data.get("last"), (int, float))
        ):
            states.append(data)
        else:
            tampered = True
    if not states:
        if tampered:
            return {"expired": True, "remaining": 0, "reason": "tamper"}
        first = last = now
    else:
        first = min(s["first"] for s in states)
        last = max(s["last"] for s in states)
    if now < last - CLOCK_SLACK:
        return {"expired": True, "remaining": 0, "reason": "clock"}
    last = max(last, now)
    _write_all("trial.dat", _pack({"m": machine_id(), "first": first, "last": last}))
    remaining = TRIAL_SECONDS - (last - first)
    return {"expired": remaining <= 0, "remaining": max(0, int(remaining)), "reason": "time"}


def status(now: float | None = None) -> dict:
    """state: licensed | trial | expired. Gói có thời hạn có thêm plan/expires_at."""
    now = time.time() if now is None else now
    base = {"machine_id": machine_id(), "contact": CONTACT, "trial_seconds": TRIAL_SECONDS}
    with _lock:
        if _stored_valid_key():
            return {**base, "state": "licensed", "plan": "lifetime", "plan_name": codec.PLAN_NAMES[codec.TYPE_LIFETIME], "remaining_seconds": None}
        ent, tampered = _ent_load()
        if ent:
            if now < ent["last"] - CLOCK_SLACK:
                return {**base, "state": "expired", "remaining_seconds": 0, "reason": "clock", "plan": "timed"}
            if now > ent["last"]:
                ent["last"] = now
                _ent_save(ent)
            left = int(ent["exp"] - now)
            if left > 0:
                return {**base, "state": "licensed", "plan": "timed", "remaining_seconds": left, "expires_at": int(ent["exp"]),
                        "plan_name": codec.PLAN_NAMES.get(ent.get("pt"))}
            return {**base, "state": "expired", "remaining_seconds": 0, "reason": "plan_expired", "plan": "timed"}
        if tampered:
            return {**base, "state": "expired", "remaining_seconds": 0, "reason": "tamper"}
        t = _trial(now)
    if t["expired"]:
        return {**base, "state": "expired", "remaining_seconds": 0, "reason": t["reason"]}
    return {**base, "state": "trial", "remaining_seconds": t["remaining"]}


# ---------------------------------------------------------------- API + chặn

router = APIRouter()


class ActivateBody(BaseModel):
    key: str


@router.get("/api/license/status")
def license_status():
    return status()


_CODE_RE = re.compile(r"^VAI[A-Z0-9]{8}$")


class OrderBody(BaseModel):
    plan: str


def _remote(method: str, path: str, body: dict | None = None):
    """Gọi máy chủ bán gói. Ném HTTPException 503 nếu không có mạng/máy chủ không phản hồi."""
    from apps.runtime_paths import https_context

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        SERVER_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "User-Agent": "VoiceAI-MrHuynh"},
    )
    try:
        ctx = https_context() if SERVER_URL.startswith("https") else None
        with urllib.request.urlopen(req, timeout=SERVER_TIMEOUT, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        raise HTTPException(status_code=400, detail=detail or "Máy chủ từ chối yêu cầu.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Không kết nối được máy chủ. Kiểm tra Internet hoặc nhập key thủ công.",
        ) from exc


@router.get("/api/license/plans")
def license_plans():
    return _remote("GET", "/api/plans")


@router.post("/api/license/order")
def license_order(body: OrderBody):
    return _remote("POST", "/api/orders", {"machine_id": machine_id(), "plan": body.plan})


@router.get("/api/license/order/{code}")
def license_order_status(code: str):
    """Hỏi trạng thái đơn; khi đã thanh toán thì tự kích hoạt key nhận được."""
    if not _CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Mã đơn không hợp lệ.")
    order = _remote("GET", f"/api/orders/{code}?machine_id={machine_id()}")
    key = order.get("key")
    if order.get("status") == "paid" and key:
        ok, msg = activate(key)
        invalidate_cache()
        # Đã dùng key này rồi (hỏi lại sau khi đã kích hoạt) vẫn coi là thành công.
        if ok or "đã được kích hoạt" in msg or "vĩnh viễn" in msg:
            return {"status": "activated", "message": msg if ok else "Đã kích hoạt.", **status()}
        return {"status": "error", "message": msg}
    return {"status": order.get("status", "pending"), "expires_at": order.get("expires_at")}


@router.post("/api/license/activate")
def license_activate(body: ActivateBody):
    ok, msg = activate(body.key)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    invalidate_cache()
    return {"ok": True, "message": msg, **status()}


_cache_state: dict = {"at": 0.0, "ok": True}
_CACHE_TTL = 5.0
_OPEN_PREFIXES = ("/api/license/", "/api/app/announcement")
_OPEN_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/voice-ai-mrhuynh.md"})


def _is_gated(path: str) -> bool:
    if path in _OPEN_PATHS or path.startswith(_OPEN_PREFIXES):
        return False
    # Chỉ chặn nơi tạo/đọc dữ liệu; file giao diện (/, /assets) vẫn mở để hiện màn hình kích hoạt.
    return path.startswith(("/api/", "/stream", "/voices"))


def allowed() -> bool:
    now = time.monotonic()
    if now - _cache_state["at"] > _CACHE_TTL:
        _cache_state["ok"] = status()["state"] != "expired"
        _cache_state["at"] = now
    return bool(_cache_state["ok"])


def invalidate_cache() -> None:
    _cache_state["at"] = 0.0


class LicenseMiddleware:
    """ASGI: khi hết hạn dùng thử và chưa có key, mọi API trả 402."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and _is_gated(scope.get("path", "")) and scope.get("method") != "OPTIONS":
            if not allowed():
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                body = json.dumps(
                    {"detail": "Hết thời gian dùng thử. Vui lòng nhập key để tiếp tục.", "license_required": True},
                    ensure_ascii=False,
                ).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 402,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode()),
                        (b"access-control-allow-origin", b"*"),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
