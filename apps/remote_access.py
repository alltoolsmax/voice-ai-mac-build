"""Cho máy khác (LAN / Internet) gọi API tạo giọng, có khoá API. Mặc định TẮT.

Quy tắc:
- Request từ chính máy này (loopback, không qua proxy) không bị đụng tới - giao diện
  của app và phần mềm cục bộ vẫn chạy như cũ, không cần khoá.
- Request từ máy khác, hoặc mang header chuyển tiếp của proxy/tunnel (ngrok,
  Cloudflare Tunnel, nginx... đều kết nối từ 127.0.0.1 nên phải nhận ra bằng header):
    * tính năng đang tắt       -> 403
    * không phải API công khai -> 404 (API nội bộ: lịch sử, cài đặt, khoá... không lộ ra)
    * thiếu/sai khoá           -> 401
- Tắt có hiệu lực ngay. Bật thì cần mở lại app: lúc khởi động server mới chọn lắng
  nghe 0.0.0.0 (mọi mạng) thay vì 127.0.0.1 (chỉ máy này).
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# Khớp danh sách API công khai trong voice-ai-mrhuynh.md / tests/test_public_api_docs.py.
PUBLIC_PATHS = frozenset({
    "/health",
    "/voices",
    "/stream",
    "/api/tts/generate",
    "/api/tts/generate-with-subtitles",
    "/api/tts/conversation",
})
# Tài liệu chỉ mô tả API công khai, đọc không cần khoá (Swagger tự tải openapi.json).
DOC_PATHS = frozenset({"/voice-ai-mrhuynh.md", "/docs", "/docs/oauth2-redirect", "/openapi.json"})

_FORWARD_HEADERS = (b"x-forwarded-for", b"forwarded", b"x-real-ip", b"cf-connecting-ip", b"x-forwarded-host")
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}
LISTEN_ENV = "VOICEAI_LISTEN_HOST"

_lock = threading.Lock()
_state: dict | None = None


def config_path() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / "VoiceAIMrHuynh" / "remote-access.json"


def new_key() -> str:
    return "voiceai_" + secrets.token_urlsafe(24)


def new_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _write(state: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(state, file)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def current() -> dict:
    """{"enabled": bool, "api_key": str}. Lần đầu tự sinh khoá và lưu lại."""
    global _state
    with _lock:
        if _state is None:
            state = {"enabled": False, "api_key": "", "phone_enabled": False, "phone_pin": "", "phone_secret": ""}
            try:
                data = json.loads(config_path().read_text(encoding="utf-8"))
                state["enabled"] = data.get("enabled") is True
                state["phone_enabled"] = data.get("phone_enabled") is True
                if isinstance(data.get("api_key"), str) and len(data["api_key"]) >= 20:
                    state["api_key"] = data["api_key"]
                pin = data.get("phone_pin")
                if isinstance(pin, str) and pin.isdigit() and len(pin) == 6:
                    state["phone_pin"] = pin
                if isinstance(data.get("phone_secret"), str) and len(data["phone_secret"]) >= 20:
                    state["phone_secret"] = data["phone_secret"]
            except (OSError, ValueError, AttributeError):
                pass
            dirty = False
            if not state["api_key"]:
                state["api_key"] = new_key()
                dirty = True
            if not state["phone_pin"] or not state["phone_secret"]:
                state["phone_pin"] = new_pin()
                state["phone_secret"] = secrets.token_urlsafe(32)
                dirty = True
            if dirty:
                try:
                    _write(state)
                except OSError:
                    pass  # Không ghi được: dùng khoá trong phiên này.
            _state = state
        return dict(_state)


def _update(**changes) -> dict:
    global _state
    state = {**current(), **changes}
    _write(state)  # Lỗi ghi thì giữ nguyên trạng thái cũ.
    with _lock:
        _state = state
    return dict(state)


def reset_cache() -> None:
    global _state
    with _lock:
        _state = None
    _attempts.clear()


def listen_host() -> str:
    """Địa chỉ server nên lắng nghe khi khởi động."""
    return "0.0.0.0" if current()["enabled"] else "127.0.0.1"


def mark_listening(host: str) -> None:
    os.environ[LISTEN_ENV] = host


def is_listening_all() -> bool:
    return os.environ.get(LISTEN_ENV) == "0.0.0.0"


def primary_address() -> str | None:
    """IPv4 của card mạng chính (card hệ điều hành dùng để ra mạng). Các IP khác
    thường là card ảo (VirtualBox 192.168.56.1, Hyper-V, VPN) - máy khác không tới được."""
    try:
        # Không gửi gói nào: connect UDP chỉ để hệ điều hành chọn card theo bảng định tuyến.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return None if addr.is_loopback or addr.is_unspecified or addr.is_link_local else ip


def lan_addresses() -> list[str]:
    """IPv4 của máy trong mạng LAN, card chính đứng đầu."""
    found: list[str] = []
    primary = primary_address()
    if primary:
        found.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    result = []
    for ip in found:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not (addr.is_loopback or addr.is_link_local or addr.is_unspecified) and ip not in result:
            result.append(ip)
    return result


def _is_loopback(host: str | None) -> bool:
    if host == "testclient":  # Máy khách giả của Starlette TestClient; socket thật luôn là IP.
        return True
    try:
        addr = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_loopback


def is_remote(scope) -> bool:
    client = scope.get("client")
    if not _is_loopback(client[0] if client else None):
        return True
    return any(name in _FORWARD_HEADERS for name, _ in scope.get("headers", []))


def _key_from(scope) -> str:
    headers = {name: value.decode("latin-1") for name, value in scope.get("headers", [])}
    key = headers.get(b"x-api-key", "").strip()
    if key:
        return key
    auth = headers.get(b"authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    # Cho thẻ <audio src="/stream?...&api_key=..."> - thẻ này không gửi được header.
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    return (query.get("api_key") or [""])[0].strip()


# ---- Chế độ điện thoại: mở giao diện qua mã PIN (cookie), tách khỏi khoá API ----

PHONE_COOKIE = "va_phone"
PHONE_COOKIE_AGE = 30 * 24 * 3600
# File tĩnh của PWA: công khai (trình duyệt tải manifest không kèm cookie ở vài máy).
_PHONE_OPEN = frozenset({"/manifest.webmanifest", "/pwa-192.png", "/pwa-512.png", "/apple-touch-icon.png", "/favicon.ico"})
# (phương thức, mẫu đường dẫn) điện thoại ĐÃ nhập PIN được gọi. Không có: cài đặt, khoá API,
# khởi động lại, cập nhật, mở thư mục, nạp/tải mô hình, kích hoạt key, bộ nhớ GPU.
_PHONE_ALLOWED = tuple(
    (methods, re.compile(pattern))
    for methods, pattern in (
        (("GET", "HEAD"), r"/|/assets/.+|/health|/voices|/stream|/api/models|/api/hardware|/api/history(/.*)?"
                          r"|/api/license/(status|plans|order/[^/]+)|/api/ui/prefs|/api/terms|/api/pronunciations"
                          r"|/api/voices/.+|/api/app/(announcement|update)"),
        (("POST",), r"/stream|/api/tts/.+|/api/srt/parse|/api/pdf/extract|/api/text/chapters|/api/audio/mp3"
                    r"|/api/history|/api/voices/(design|custom)|/api/pronunciations/preview|/api/license/order"
                    r"|/api/terms/accept"),
        (("PUT",), r"/api/ui/prefs|/api/pronunciations"),
        (("DELETE",), r"/api/history/[^/]+|/api/voices/custom/[^/]+"),
    )
)

_attempts: dict[str, tuple[int, float]] = {}
_MAX_FAILS = 5
_LOCK_SECONDS = 600


def phone_token(state: dict) -> str:
    return hmac.new(state["phone_secret"].encode(), b"voiceai-phone-session", "sha256").hexdigest()


def _cookie_from(scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in value.decode("latin-1").split(";"):
                key, _, val = part.strip().partition("=")
                if key == PHONE_COOKIE:
                    return val
    return ""


def phone_session_ok(scope, state: dict) -> bool:
    cookie = _cookie_from(scope)
    return bool(cookie) and hmac.compare_digest(cookie.encode(), phone_token(state).encode())


def phone_path_allowed(method: str, path: str) -> bool:
    return any(method in methods and rx.fullmatch(path) for methods, rx in _PHONE_ALLOWED)


def _client_ip(scope) -> str:
    client = scope.get("client")
    return client[0] if client else "?"


def _locked(ip: str, now: float) -> int:
    fails, until = _attempts.get(ip, (0, 0.0))
    if until > now:
        return int(until - now) + 1
    if until and until <= now:
        _attempts.pop(ip, None)
    return 0


def _register_fail(ip: str, now: float) -> None:
    fails, _ = _attempts.get(ip, (0, 0.0))
    fails += 1
    _attempts[ip] = (fails, now + _LOCK_SECONDS if fails >= _MAX_FAILS else 0.0)


def phone_login_page(error: str = "") -> bytes:
    msg = f'<p class="e">{error}</p>' if error else ""
    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0aa889"><title>Voice AI - Mr.Huỳnh</title>
<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#163039;
background:radial-gradient(circle at 50% 30%,#e1f6f1,#f3f8f8 60%)}}
.c{{width:min(100%,360px);text-align:center}}img{{width:76px;height:76px;border-radius:50%}}
h1{{font-size:22px;margin:14px 0 4px}}p{{color:#527079;font-size:14px;margin:0 0 20px;line-height:1.5}}
input{{width:100%;font-size:30px;letter-spacing:.5em;text-align:center;padding:14px 10px 14px 24px;
border:2px solid #cfe3e0;border-radius:14px;background:#fff;color:#163039}}input:focus{{outline:none;border-color:#0aa889}}
button{{width:100%;margin-top:14px;padding:14px;font-size:16px;font-weight:700;color:#fff;background:#0aa889;
border:0;border-radius:14px}}.e{{color:#c0334d;font-weight:600;margin:12px 0 0}}</style></head>
<body><form class="c" method="post" action="/phone/login">
<img src="/pwa-192.png" alt=""><h1>Voice AI - Mr.Huỳnh</h1>
<p>Nhập mã PIN 6 số đang hiện trong phần Cài đặt của app trên máy tính.</p>
<input name="pin" inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" autofocus required>
{msg}<button type="submit">Vào dùng</button></form></body></html>"""
    return html.encode("utf-8")


async def _send_html(send, status: int, body: bytes, extra: list | None = None) -> None:
    headers = [
        (b"content-type", b"text/html; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ] + (extra or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _redirect(send, location: str, extra: list | None = None) -> None:
    headers = [(b"location", location.encode()), (b"content-length", b"0"), (b"cache-control", b"no-store")] + (extra or [])
    await send({"type": "http.response.start", "status": 303, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


async def _read_body(receive, limit: int = 2048) -> bytes:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if len(body) > limit:
            return b""
        if not message.get("more_body"):
            return body


async def _phone_login(scope, receive, send, state: dict) -> None:
    method = scope.get("method")
    if method != "POST":
        await _send_html(send, 200, phone_login_page())
        return
    ip = _client_ip(scope)
    wait = _locked(ip, time.time())
    if wait:
        await _send_html(send, 429, phone_login_page(f"Nhập sai nhiều lần. Thử lại sau {wait // 60 + 1} phút."))
        return
    form = parse_qs((await _read_body(receive)).decode("latin-1"))
    pin = (form.get("pin") or [""])[0].strip()
    if not hmac.compare_digest(pin.encode(), state["phone_pin"].encode()):
        _register_fail(ip, time.time())
        await _send_html(send, 401, phone_login_page("Sai mã PIN. Kiểm tra lại trên máy tính."))
        return
    _attempts.pop(ip, None)
    cookie = f"{PHONE_COOKIE}={phone_token(state)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={PHONE_COOKIE_AGE}"
    await _redirect(send, "/", [(b"set-cookie", cookie.encode())])


class RemoteAccessMiddleware:
    """Chặn request từ máy khác theo quy tắc ở đầu file. Phải là middleware ngoài cùng."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not is_remote(scope):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        state = current()
        if not state["enabled"]:
            await _deny(scope, send, 403, "Truy cập từ máy khác đang tắt. Bật trong Cài đặt của Voice AI - Mr.Huỳnh.")
            return
        method = scope.get("method", "GET")
        if state["phone_enabled"] and scope["type"] == "http":
            if path == "/phone" or path == "/phone/login":
                await _phone_login(scope, receive, send, state)
                return
            if path in _PHONE_OPEN and method in ("GET", "HEAD"):
                await self.app(scope, receive, send)
                return
            if phone_session_ok(scope, state):
                if phone_path_allowed(method, path):
                    await self.app(scope, receive, send)
                    return
            elif path == "/" and method in ("GET", "HEAD"):
                await _redirect(send, "/phone")
                return
        if path not in PUBLIC_PATHS and path not in DOC_PATHS:
            await _deny(scope, send, 404, "Không tìm thấy.")
            return
        # OPTIONS là preflight CORS của trình duyệt: không mang được khoá.
        if path in PUBLIC_PATHS and scope.get("method") != "OPTIONS":
            if not hmac.compare_digest(_key_from(scope).encode(), state["api_key"].encode()):
                await _deny(scope, send, 401, "Thiếu hoặc sai khoá API. Gửi header X-API-Key: <khoá>.")
                return
        await self.app(scope, receive, send)


async def _deny(scope, send, status: int, detail: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
        # Lỗi trả trước CORSMiddleware: thêm tay để trình duyệt đọc được thông báo.
        (b"access-control-allow-origin", b"*"),
    ]
    if status == 401:
        headers.append((b"www-authenticate", b'Bearer realm="Voice AI - Mr.Huynh"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


# ---- API cài đặt (chỉ giao diện trên máy này) ----

router = APIRouter()


def require_this_machine(request: Request) -> None:
    """Middleware đã chặn máy khác. Ở đây chặn thêm TRANG WEB LẠ mở trên chính máy này
    (CORS đang mở "*" nên trang nào cũng fetch được 127.0.0.1): kiểm tra Origin, và
    Host để chống DNS rebinding - nếu không, trang lạ đọc được khoá rồi gửi đi."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    if host not in _LOCAL_HOSTNAMES:
        raise HTTPException(status_code=403, detail="Chỉ đổi được từ ứng dụng trên máy này.")
    origin = request.headers.get("origin")
    if origin and origin != "null":
        parts = urlsplit(origin)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in _LOCAL_HOSTNAMES:
            raise HTTPException(status_code=403, detail="Chỉ đổi được từ ứng dụng trên máy này.")


def _status(request: Request) -> dict:
    state = current()
    return {
        "enabled": state["enabled"],
        "api_key": state["api_key"],
        "phone_enabled": state["phone_enabled"],
        "phone_pin": state["phone_pin"],
        "listening_all": is_listening_all(),
        "port": request.url.port or 80,
        "addresses": lan_addresses(),
        "primary_address": primary_address(),
    }


class RemoteAccessUpdate(BaseModel):
    enabled: bool | None = None
    phone_enabled: bool | None = None


@router.get("/api/remote-access")
def get_remote_access(request: Request):
    require_this_machine(request)
    return _status(request)


@router.put("/api/remote-access")
def set_remote_access(update: RemoteAccessUpdate, request: Request):
    require_this_machine(request)
    try:
        changes = {k: v for k, v in (("enabled", update.enabled), ("phone_enabled", update.phone_enabled)) if v is not None}
        if changes:
            _update(**changes)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Không lưu được cài đặt. Hãy kiểm tra quyền ghi cấu hình.") from error
    return _status(request)


@router.post("/api/remote-access/regenerate-key")
def regenerate_key(request: Request):
    require_this_machine(request)
    try:
        _update(api_key=new_key())
    except OSError as error:
        raise HTTPException(status_code=500, detail="Không lưu được khoá mới.") from error
    return _status(request)


@router.post("/api/remote-access/regenerate-pin")
def regenerate_pin(request: Request):
    """PIN mới + đổi khoá phiên: mọi điện thoại đang đăng nhập phải nhập lại."""
    require_this_machine(request)
    try:
        _update(phone_pin=new_pin(), phone_secret=secrets.token_urlsafe(32))
    except OSError as error:
        raise HTTPException(status_code=500, detail="Không lưu được mã PIN mới.") from error
    return _status(request)
