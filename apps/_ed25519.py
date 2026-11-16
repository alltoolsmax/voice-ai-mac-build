"""Ed25519 (RFC 8032) thuần Python, không cần thư viện ngoài.

Chỉ dùng cho giấy phép: kiểm tra chữ ký (app) và ký key (công cụ cấp key). Chậm vài
trăm mili giây mỗi lần, đủ cho việc kiểm tra key một lần.
"""
from __future__ import annotations

import hashlib

_p = 2**255 - 19
_l = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _p - 2, _p)


_d = -121665 * _inv(121666) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_p + 3) // 8, _p)
    if (x * x - xx) % _p != 0:
        x = (x * _I) % _p
    if x % 2 != 0:
        x = _p - x
    return x


_By = 4 * _inv(5)
_B = (_xrecover(_By) % _p, _By % _p)


def _add(P, Q):
    x1, y1 = P
    x2, y2 = Q
    t = _d * x1 * x2 * y1 * y2
    return ((x1 * y2 + x2 * y1) * _inv(1 + t) % _p, (y1 * y2 + x1 * x2) * _inv(1 - t) % _p)


def _mul(P, e: int):
    Q = (0, 1)
    while e:
        if e & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        e >>= 1
    return Q


def _enc(P) -> bytes:
    x, y = P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _on_curve(P) -> bool:
    x, y = P
    return (-x * x + y * y - 1 - _d * x * x * y * y) % _p == 0


def _dec(s: bytes):
    if len(s) != 32:
        raise ValueError("điểm sai độ dài")
    n = int.from_bytes(s, "little")
    y = n & ((1 << 255) - 1)
    if y >= _p:
        raise ValueError("điểm không hợp lệ")
    x = _xrecover(y)
    if (x & 1) != (n >> 255):
        x = _p - x
    P = (x, y)
    if not _on_curve(P):
        raise ValueError("điểm không nằm trên đường cong")
    return P


def _h(m: bytes) -> int:
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_scalar(seed: bytes):
    h = hashlib.sha512(seed).digest()
    a = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _secret_scalar(seed)
    return _enc(_mul(_B, a))


def sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _secret_scalar(seed)
    A = _enc(_mul(_B, a))
    r = _h(prefix + msg) % _l
    R = _enc(_mul(_B, r))
    S = (r + _h(R + A + msg) * a) % _l
    return R + S.to_bytes(32, "little")


def verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if len(sig) != 64 or len(pub) != 32:
            return False
        R = _dec(sig[:32])
        A = _dec(pub)
        S = int.from_bytes(sig[32:], "little")
        if S >= _l:
            return False
        h = _h(sig[:32] + pub + msg) % _l
        return _mul(_B, S) == _add(R, _mul(A, h))
    except Exception:
        return False
