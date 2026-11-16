"""Định dạng key kích hoạt (dùng chung cho app và công cụ cấp key).

Key = "MH1-" + base32( payload 12 byte + chữ ký Ed25519 64 byte ), chia nhóm 6 ký tự.
payload = phiên bản(1) + loại(1) + mã máy(8) + ngày cấp(2, số ngày từ 2024-01-01).
Chữ ký phủ cả tiền tố miền để không dùng lẫn với chữ ký khác.
"""
from __future__ import annotations

import base64
import datetime
import re

try:
    from apps import _ed25519 as ed
except ImportError:  # công cụ cấp key đặt file cạnh nhau
    import _ed25519 as ed  # type: ignore

PREFIX = "MH1-"
DOMAIN = b"VoiceAI-MrHuynh-license-v1"
VERSION = 1
TYPE_LIFETIME = 1
TYPE_1M = 2
TYPE_3M = 3
TYPE_1Y = 4
TYPE_6M = 5
TYPE_TRIAL7 = 6   # key dùng thử 7 ngày (chỉ cấp tay, không bán)
TYPE_EXP10 = 7    # key trải nghiệm 10 ngày (chỉ cấp tay, không bán)
# Số ngày của mỗi gói có thời hạn (vĩnh viễn: None). Thứ tự = thứ tự hiển thị.
PLAN_DAYS = {TYPE_1M: 30, TYPE_3M: 90, TYPE_6M: 180, TYPE_1Y: 365, TYPE_LIFETIME: None, TYPE_TRIAL7: 7, TYPE_EXP10: 10}
PLAN_NAMES = {TYPE_1M: "1 tháng", TYPE_3M: "3 tháng", TYPE_6M: "6 tháng", TYPE_1Y: "1 năm", TYPE_LIFETIME: "Vĩnh viễn",
              TYPE_TRIAL7: "Dùng thử 7 ngày", TYPE_EXP10: "Trải nghiệm 10 ngày"}
PLAN_CODES = {"1m": TYPE_1M, "3m": TYPE_3M, "6m": TYPE_6M, "1y": TYPE_1Y, "life": TYPE_LIFETIME, "t7": TYPE_TRIAL7, "x10": TYPE_EXP10}
# Key có thời hạn phải được kích hoạt trong vòng này kể từ ngày cấp (chống để dành/dùng lại sau nhiều tháng).
ACTIVATION_WINDOW_DAYS = 30
EPOCH = datetime.date(2024, 1, 1)
_MID_RE = re.compile(r"^MH-([0-9A-F]{4})-([0-9A-F]{4})-([0-9A-F]{4})-([0-9A-F]{4})$")


def format_machine_id(raw8: bytes) -> str:
    h = raw8.hex().upper()
    return f"MH-{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"


def parse_machine_id(text: str) -> bytes:
    t = (text or "").strip().upper().replace(" ", "")
    m = _MID_RE.match(t)
    if not m:
        raise ValueError("Mã máy phải có dạng MH-XXXX-XXXX-XXXX-XXXX")
    return bytes.fromhex("".join(m.groups()))


def make_key(seed: bytes, machine: bytes, key_type: int = TYPE_LIFETIME, issued: datetime.date | None = None) -> str:
    issued = issued or datetime.date.today()
    days = (issued - EPOCH).days
    payload = bytes([VERSION, key_type]) + machine + days.to_bytes(2, "big")
    sig = ed.sign(seed, DOMAIN + payload)
    raw = base64.b32encode(payload + sig).decode().rstrip("=")
    return PREFIX + "-".join(raw[i:i + 6] for i in range(0, len(raw), 6))


def parse_key(key: str):
    """Trả (payload, chữ ký) hoặc ném ValueError nếu hỏng định dạng."""
    t = re.sub(r"[\s\-_]", "", (key or "").upper())
    if t.startswith("MH1"):
        t = t[3:]
    else:
        raise ValueError("Key không đúng định dạng")
    try:
        raw = base64.b32decode(t + "=" * (-len(t) % 8))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Key không đúng định dạng") from exc
    if len(raw) != 76:
        raise ValueError("Key không đúng định dạng")
    return raw[:12], raw[12:]


def key_info(payload: bytes) -> dict:
    return {
        "type": payload[1],
        "days": PLAN_DAYS.get(payload[1]),
        "issued": EPOCH + datetime.timedelta(days=int.from_bytes(payload[10:12], "big")),
    }


def verify_key(pubkey: bytes, key: str, machine: bytes):
    """Trả (ok, thông báo). ok=True nếu key hợp lệ cho đúng máy này."""
    ok, msg, _ = inspect_key(pubkey, key, machine)
    return ok, msg


def inspect_key(pubkey: bytes, key: str, machine: bytes):
    """Trả (ok, thông báo, thông tin key). Thông tin gồm loại gói, số ngày, ngày cấp."""
    try:
        payload, sig = parse_key(key)
    except ValueError as exc:
        return False, str(exc), None
    if not ed.verify(pubkey, DOMAIN + payload, sig):
        return False, "Key không hợp lệ.", None
    if payload[0] != VERSION or payload[1] not in PLAN_DAYS:
        return False, "Key không được hỗ trợ ở phiên bản này.", None
    if payload[2:10] != machine:
        return False, "Key này được cấp cho máy khác.", None
    return True, "OK", key_info(payload)
