"""Vẽ khung hình màn hình khởi động Voice AI (nền TRONG SUỐT, có kênh alpha).

Chỉ phụ thuộc Pillow + numpy, không đụng tới Windows: kiểm thử được trên mọi hệ điều hành.
`apps/splash_native.py` lấy từng khung ở đây và đưa lên cửa sổ trong suốt của Windows.

Hai cảnh chạy chung một cửa sổ, chuyển mượt bằng `phase` (0 -> 1):
  - phase 0 "khởi động": logo + sóng ngang hai bên.
  - phase 1 "nạp thư viện": vòng sóng quanh logo + vòng mảnh xoay + dòng phụ.
"""
from __future__ import annotations

import colorsys
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LOGICAL_W, LOGICAL_H = 960, 600
TITLE = "Voice AI - Mr. Huỳnh"
SUBTITLE = "Chuyển văn bản thành giọng nói tiếng Việt"
CYAN, VIOLET, PINK = (34, 211, 238), (168, 85, 247), (255, 79, 163)
ICE, LILAC = (126, 233, 255), (240, 171, 252)

_FONT_CANDIDATES_SEMI = (
    "C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_FONT_CANDIDATES_BOLD = (
    "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(candidates, size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _mix(a, b, k: float):
    k = min(1.0, max(0.0, k))
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _noise(i: float, t: float) -> float:
    return 0.5 + 0.5 * math.sin(i * 1.7 + t * 3.1) * math.sin(i * 0.43 - t * 1.9 + 1.3)


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def default_logo_path() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    roots = [here]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.insert(0, Path(meipass))
    for root in roots:
        for rel in ("assets/brand/logo.png", "assets/icons/icon.png"):
            if (root / rel).is_file():
                return root / rel
    return None


class SplashRenderer:
    """`render(t, phase, progress, status)` -> ảnh RGBA. Cửa sổ xanh tối bo góc, ngoài góc trong suốt.

    phase 0 = màn "khởi động" (ảnh 2), phase 1 = màn "nạp thư viện" (ảnh 1); chuyển mượt ở giữa."""

    def __init__(self, scale: float = 1.0, logo_path: Path | str | None = None):
        self.s = max(0.75, min(3.0, float(scale)))
        self.w = int(LOGICAL_W * self.s)
        self.h = int(LOGICAL_H * self.s)
        rnd = random.Random(7)
        self.parts = [(rnd.random() * 6.283, 90 + rnd.random() * 190, 0.15 + rnd.random() * 0.5,
                       1 + rnd.random() * 2.2, rnd.random()) for _ in range(40)]
        self.stars = [(rnd.random(), rnd.random(), 4 + rnd.random() * 18, rnd.random() * 6.28,
                       0.8 + rnd.random() * 1.2, rnd.random() > 0.35) for _ in range(70)]
        path = Path(logo_path) if logo_path else default_logo_path()
        self.logo = None
        if path and Path(path).is_file():
            try:
                self.logo = Image.open(path).convert("RGBA")
            except OSError:
                self.logo = None
        try:
            from apps.app_version import APP_VERSION
        except Exception:
            APP_VERSION = ""
        self.version = f"v{APP_VERSION} · Mr.Huỳnh" if APP_VERSION else "Mr.Huỳnh"
        sz = self.s
        self.f_title = _font(_FONT_CANDIDATES_SEMI, int(34 * sz))
        self.f_title_g = _font(_FONT_CANDIDATES_BOLD, int(36 * sz))
        self.f_sub = _font(_FONT_CANDIDATES, int(15 * sz))
        self.f_stat = _font(_FONT_CANDIDATES, int(13 * sz))
        self.f_ver = _font(_FONT_CANDIDATES, int(11 * sz))
        self._text_cache: dict = {}
        self._bg_a = self._make_bg((22, 27, 92), (14, 18, 68), (8, 10, 38))      # khởi động: xanh tím
        self._bg_b = self._make_bg((12, 32, 56), (7, 22, 42), (3, 10, 20))       # nạp: xanh đen
        self._mask = self._rounded_mask()
        self._glow_cache: dict = {}

    # ---------- nền + khung bo góc ----------
    def _make_bg(self, c0, c1, c2) -> Image.Image:
        W, H = self.w, self.h
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.45) / (W * 0.62)) ** 2)
        d = np.clip(d, 0, 1)[..., None]
        c0, c1, c2 = (np.array(c, np.float32) for c in (c0, c1, c2))
        near = np.clip(d / 0.55, 0, 1)
        far = np.clip((d - 0.55) / 0.45, 0, 1)
        rgb = np.where(d < 0.55, c0 + (c1 - c0) * near, c1 + (c2 - c1) * far)
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")

    def _rounded_mask(self) -> Image.Image:
        k = 3  # vẽ phóng to rồi thu nhỏ để mép bo mịn
        m = Image.new("L", (self.w * k, self.h * k), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, self.w * k - 1, self.h * k - 1], radius=int(22 * self.s * k), fill=255)
        return m.resize((self.w, self.h), Image.LANCZOS)

    # ---------- chữ ----------
    def _text(self, text: str, font, key: str):
        ck = (text, key)
        if ck not in self._text_cache:
            if len(self._text_cache) > 60:
                self._text_cache.clear()
            probe = ImageDraw.Draw(Image.new("L", (4, 4)))
            box = probe.textbbox((0, 0), text, font=font)
            pad = int(10 * self.s)
            m = Image.new("L", (box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2), 0)
            ImageDraw.Draw(m).text((pad - box[0], pad - box[1]), text, font=font, fill=255)
            self._text_cache[ck] = m
        return self._text_cache[ck]

    def _put(self, canvas, mask, cx, cy, alpha, color=None, gradient=None):
        if alpha <= 0.01:
            return
        layer = gradient.copy() if gradient is not None else Image.new("RGBA", mask.size, tuple(color) + (0,))
        layer.putalpha(mask.point(lambda v: int(v * alpha)))
        canvas.alpha_composite(layer, (int(cx - mask.width / 2), int(cy - mask.height / 2)))

    def _title_gradient(self, mask: Image.Image, t: float, pink: bool) -> Image.Image:
        w, h = mask.size
        xs = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        p = (t * 0.22) % 1.5 - 0.25
        if pink:
            base0, base1, hot = np.array((246, 231, 255), np.float32), np.array((233, 213, 255), np.float32), np.array((255, 184, 240), np.float32)
        else:
            base0, base1, hot = np.array((255, 255, 255), np.float32), np.array((230, 236, 255), np.float32), np.array((207, 224, 255), np.float32)
        base = base0 + (base1 - base0) * xs
        k = np.clip(1 - np.abs(xs - p - 0.12) / 0.25, 0, 1)
        rgb = np.broadcast_to(base + (hot - base) * k, (h, w, 3))
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    # ---------- quầng sáng ----------
    def _radial(self, rgb, radius: int) -> Image.Image:
        key = (rgb, radius)
        if key not in self._glow_cache:
            n = radius * 2
            yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
            d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
            a = np.clip(1 - d, 0, 1) ** 1.7
            arr = np.zeros((n, n, 4), np.uint8)
            arr[..., 0], arr[..., 1], arr[..., 2] = rgb
            arr[..., 3] = (a * 255).astype(np.uint8)
            self._glow_cache[key] = Image.fromarray(arr, "RGBA")
        return self._glow_cache[key]

    def _gl(self, canvas, rgb, cx, cy, radius, alpha):
        if alpha <= 0.01 or radius < 4:
            return
        img = self._radial(rgb, int(radius)).copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
        canvas.alpha_composite(img, (int(cx - radius), int(cy - radius)))

    # ---------- khung hình ----------
    def render(self, t: float, phase: float = 0.0, progress: float = 0.2, status: str = "") -> Image.Image:
        s, W, H = self.s, self.w, self.h
        p = _smooth(phase)
        q = 1 - p
        cx = W / 2
        canvas = Image.blend(self._bg_a, self._bg_b, p).convert("RGBA")
        glow = Image.new("RGBA", (W // 2, H // 2), (0, 0, 0, 0))
        crisp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)

        LS = (196 - 32 * p) * s
        cy = H * (0.385 + 0.005 * p)
        wy = H * 0.525  # đường sóng ngang (cảnh 1)

        # ===== cảnh 2: sao nhỏ, sóng đáy, nhãn phiên bản =====
        if p > 0.02:
            for (u, v, sp, ph, z, blue) in self.stars:
                px, py = (u * W + t * sp * s) % W, (v * H + math.sin(t * 0.4 + ph) * 8 * s) % H
                al = int(255 * p * (0.25 + 0.25 * math.sin(t * 1.3 + ph * 3)))
                col = ((120, 140, 255) if blue else (220, 120, 255)) + (max(0, al),)
                zz = z * s * 0.8
                cd.ellipse([px - zz, py - zz, px + zz, py + zz], fill=col)
            pts, pts2 = [], []
            for px in range(0, W + 1, max(3, int(4 * s))):
                y = H - 22 * s + math.sin(px / s * 0.03 + t * 3) * 5 * s * math.sin(px / s * 0.004 + t * 0.5)
                pts.append((px, y))
            for i in range(len(pts) - 1):
                u = i / len(pts)
                col = (_mix(CYAN, VIOLET, u * 2) if u < 0.5 else _mix(VIOLET, PINK, (u - 0.5) * 2)) + (int(200 * p),)
                cd.line([pts[i], pts[i + 1]], fill=col, width=max(1, int(2 * s)))

        # ===== cảnh 1: quầng màu, hai đường sóng mảnh, cột sóng =====
        if q > 0.02:
            for i, col in enumerate(((255, 79, 163), (245, 158, 11), (168, 85, 247), (34, 211, 238))):
                a = t * 0.6 + i * 1.57
                r = (44 + 10 * math.sin(t * 1.3 + i)) * s
                self._gl(canvas, col, cx + math.cos(a) * r, cy + math.sin(a * 1.2) * r * 0.7, 70 * s, 0.62 * q)
            for ph, amp, c0, c1, yo in ((0.0, 13, (56, 189, 248), (251, 146, 60), 0), (2.1, 9, (129, 140, 248), (244, 114, 182), 3)):
                prev = None
                for px in range(0, W + 1, max(3, int(4 * s))):
                    e = 0.35 + 0.65 * math.exp(-(((px - cx) / (340 * s)) ** 2))
                    y = wy + yo * s + (math.sin(px / s * 0.012 + t * 2.2 + ph) * amp + math.sin(px / s * 0.031 - t * 3 + ph) * amp * 0.25) * e * s
                    if prev is not None:
                        u = px / W
                        col = (_mix(c0, (192, 132, 252), u * 2) if u < 0.5 else _mix((192, 132, 252), c1, (u - 0.5) * 2)) + (int(230 * q),)
                        cd.line([prev, (px, y)], fill=col, width=max(1, int(2 * s)))
                    prev = (px, y)
            reveal = min(1.0, t / 1.1)
            for side in (-1, 1):
                for i in range(20):
                    d = i / 20
                    if d > reveal:
                        continue
                    env = (1 - d) ** 1.1
                    amp = (6 + 34 * _noise(i * side + (5 if side > 0 else 0), t * 1.1)) * env * (0.35 + 0.65 * math.sin(t * 2 - d * 6) ** 2) * s
                    px = cx + side * (LS / 2 - 8 * s + i * 15 * s)
                    hot = ((56, 189, 248), (192, 132, 252)) if side < 0 else ((251, 113, 133), (251, 191, 36))
                    al = int(255 * q)
                    wd = max(3, int(5 * s))
                    cd.line([(px, wy - amp), (px, wy)], fill=hot[0] + (al,), width=wd)
                    cd.line([(px, wy), (px, wy + amp)], fill=hot[1] + (al,), width=wd)
                    for yy_, cc in ((wy - amp, hot[0]), (wy + amp, hot[1])):
                        cd.ellipse([px - wd / 2, yy_ - wd / 2, px + wd / 2, yy_ + wd / 2], fill=cc + (al,))
                    gd.line([(px / 2, (wy - amp) / 2), (px / 2, (wy + amp) / 2)], fill=hot[0] + (int(140 * q),), width=max(3, wd // 2 + 3))

        # ===== cảnh 2: vòng mảnh + vòng phổ =====
        if p > 0.02:
            R = LS / 2 + 22 * s
            for rr in (R + 92 * s, R + 138 * s):
                cd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(120, 160, 255, int(72 * p)), width=max(1, int(1.3 * s)))
            for k in range(2):
                ph = ((t / 3) + k / 2) % 1
                rr = R + 10 * s + ph * 130 * s
                cd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(103, 232, 249, int(56 * (1 - ph) * p)), width=max(1, int(2 * s)))
            N = 120
            for i in range(N):
                a = i / N * 6.2832 - 1.5708
                w_ = math.sin(a * 3 + t * 2.2) * 0.5 + math.sin(a * 5 - t * 3.1) * 0.35 + math.sin(a * 2 + t * 1.3) * 0.3
                ln = (14 + abs(w_) * 62 + 10 * math.sin(t * 3 + i * 0.7) ** 2) * s * (0.3 + 0.7 * min(1, p * 1.5))
                hue = (215 + 110 * (0.5 + 0.5 * math.sin(a + t * 0.6 + 1.2))) / 360
                col = tuple(int(255 * c) for c in colorsys.hls_to_rgb(hue % 1, 0.62, 0.92))
                c1, s1 = math.cos(a), math.sin(a)
                x0, y0, x1, y1 = cx + c1 * R, cy + s1 * R, cx + c1 * (R + ln), cy + s1 * (R + ln)
                wd = max(3, int(5.4 * s))
                al = int(255 * p)
                cd.line([(x0, y0), (x1, y1)], fill=col + (al,), width=wd)
                cd.ellipse([x1 - wd / 2, y1 - wd / 2, x1 + wd / 2, y1 + wd / 2], fill=col + (al,))
                gd.line([(x0 / 2, y0 / 2), (x1 / 2, y1 / 2)], fill=col + (int(150 * p),), width=max(3, wd // 2 + 4))

        # ===== hạt sáng =====
        for (a0, r0, sp, z, h) in self.parts:
            ang = a0 + t * sp * 0.4
            r = r0 + math.sin(t * sp * 2 + a0) * 12
            px, py = cx + math.cos(ang) * r * 1.35 * s, cy + math.sin(ang) * r * 0.62 * s
            al = (0.7 * q + 0.45 * p) * (0.55 + 0.45 * math.sin(t * 2 + a0 * 3))
            col = (CYAN if h > 0.5 else LILAC) + (int(255 * max(0.0, al)),)
            zz = z * s
            cd.ellipse([px - zz, py - zz, px + zz, py + zz], fill=col)

        # ===== thanh tiến trình =====
        pw = (244 - 12 * p) * s
        py_prog = H * (0.775 + 0.085 * p)
        x0, x1 = cx - pw / 2, cx + pw / 2
        lw = max(4, int(5 * s))
        cd.line([(x0, py_prog), (x1, py_prog)], fill=(255, 255, 255, 26), width=lw)
        fw = max(8 * s, pw * min(1.0, max(0.0, progress)))
        for k in range(28):
            xa, xb = x0 + fw * k / 28, x0 + fw * (k + 1) / 28 + 1
            u = k / 28
            col = _mix(CYAN, VIOLET, u * 2) if u < 0.5 else _mix(VIOLET, PINK, (u - 0.5) * 2)
            cd.line([(xa, py_prog), (xb, py_prog)], fill=col + (255,), width=lw)
            gd.line([(xa / 2, py_prog / 2), (xb / 2, py_prog / 2)], fill=col + (160,), width=max(3, lw // 2 + 3))
        for xx_ in (x0, x0 + fw):
            cd.ellipse([xx_ - lw / 2, py_prog - lw / 2, xx_ + lw / 2, py_prog + lw / 2], fill=CYAN + (255,) if xx_ == x0 else PINK + (255,))

        glow = glow.filter(ImageFilter.GaussianBlur(5 * s / 2 * 1.5)).resize((W, H), Image.BILINEAR)
        canvas.alpha_composite(glow)
        canvas.alpha_composite(crisp)

        # ===== logo =====
        for rgb, wgt in (((124, 58, 237), q), ((34, 211, 238), p)):
            self._gl(canvas, rgb, cx, cy + math.sin(t * 1.6) * 4 * s, LS * 0.95, 0.6 * wgt)
        if self.logo is not None:
            size = max(8, int(LS * (1 + 0.012 * math.sin(t * 2.4))))
            lg = self.logo.resize((size, size), Image.LANCZOS)
            canvas.alpha_composite(lg, (int(cx - size / 2), int(cy + math.sin(t * 1.6) * 4 * s - size / 2)))

        # ===== chữ =====
        ty = H * (0.675 + 0.085 * p)
        tm1 = self._text(TITLE, self.f_title, "t1")
        self._put(canvas, tm1, cx, ty, min(1.0, t / 0.8) * q, color=(230, 234, 255))
        tm2 = self._text(TITLE, self.f_title_g, "t2")
        self._put(canvas, tm2, cx, ty, p, gradient=self._title_gradient(tm2, t, True))
        sub = self._text(SUBTITLE, self.f_sub, "sub")
        self._put(canvas, sub, cx, H * 0.81, p, color=(184, 196, 222))
        if status:
            txt = status.rstrip(".… ") + "." * (1 + int(t * 2.5) % 3)
            sm = self._text(txt, self.f_stat, "st")
            sy = H * (0.73 + 0.175 * p)
            self._put(canvas, sm, cx, sy, 1.0, color=(159, 176, 216) if p < 0.5 else (211, 222, 239))
            if p > 0.02:
                dx = cx - sm.width / 2 - 8 * s
                self._gl(canvas, CYAN, dx, sy, 11 * s, 0.9 * p)
                d2 = ImageDraw.Draw(canvas)
                r_ = 3.6 * s
                d2.ellipse([dx - r_, sy - r_, dx + r_, sy + r_], fill=CYAN + (int(255 * p),))
        if p > 0.02:
            vm = self._text(self.version, self.f_ver, "ver")
            self._put(canvas, vm, W - 16 * s - vm.width / 2, H - 14 * s, p * 0.85, color=(125, 144, 168))

        # ===== cắt theo khung bo góc: ngoài góc trong suốt =====
        canvas.putalpha(self._mask)
        return canvas


def to_premultiplied_bgra(img: Image.Image) -> bytes:
    """RGBA thẳng -> BGRA nhân sẵn alpha: định dạng UpdateLayeredWindow yêu cầu."""
    arr = np.asarray(img, dtype=np.uint16)
    a = arr[..., 3:4]
    rgb = (arr[..., :3] * a + 127) // 255
    out = np.empty(arr.shape, dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = rgb[..., 2], rgb[..., 1], rgb[..., 0]
    out[..., 3] = a[..., 0]
    return out.tobytes()
