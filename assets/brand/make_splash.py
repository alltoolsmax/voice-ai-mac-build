"""Ve man hinh cho (--splash) luc dong goi: anh tinh HINH TRON (ngoai dia trong suot), khong gia lap tien trinh.

Chu dung Be Vietnam Pro nhu tieu de trong app (lay tu node_modules, vi npm build da
chay truoc buoc nay); thieu thi lui ve Segoe UI. Fontsource tach font theo bo ky tu,
nen moi ky tu duoc ve bang file chua no (tieng Viet / latin).
"""
from pathlib import Path
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.app_version import APP_VERSION

SCALE = 3
WIDTH, HEIGHT = 520, 520  # màn hình chờ hình tròn, ngoài đĩa trong suốt
FONT_DIR = ROOT / "app-desktop" / "voice-ai-app" / "node_modules" / "@fontsource" / "be-vietnam-pro" / "files"
# unicode-range cua bo "vietnamese" trong @fontsource/be-vietnam-pro.
VI_RANGES = (
    (0x0102, 0x0103), (0x0110, 0x0111), (0x0128, 0x0129), (0x0168, 0x0169),
    (0x01A0, 0x01A1), (0x01AF, 0x01B0), (0x0300, 0x0309), (0x0323, 0x0323),
    (0x1EA0, 0x1EF9), (0x20AB, 0x20AB),
)


def _is_vi(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in VI_RANGES)


def _fonts(weight: int, size: int):
    """(font latin, font tieng Viet) cho mot co chu."""
    px = size * SCALE
    latin = FONT_DIR / f"be-vietnam-pro-latin-{weight}-normal.woff"
    vi = FONT_DIR / f"be-vietnam-pro-vietnamese-{weight}-normal.woff"
    try:
        return ImageFont.truetype(str(latin), px), ImageFont.truetype(str(vi), px)
    except OSError:
        name = "segoeuib.ttf" if weight >= 600 else "segoeui.ttf"
        font = ImageFont.truetype("C:/Windows/Fonts/" + name, px)
        return font, font


def _text(draw, x, y, value, size, color, weight=400, anchor_right=False):
    latin, vi = _fonts(weight, size)
    runs = [(ch, vi if _is_vi(ch) else latin) for ch in value]
    total = sum(font.getlength(ch) for ch, font in runs)
    cx = x * SCALE - (total if anchor_right else 0)
    for ch, font in runs:
        # Neo theo baseline de hai file font khop dong.
        draw.text((cx, y * SCALE), ch, font=font, fill=color, anchor="ls")
        cx += font.getlength(ch)


def _logo(canvas: Image.Image, x: int, y: int, size: int) -> None:
    logo = Image.open(ROOT / "assets" / "brand" / "logo.png").convert("RGBA")
    logo = logo.resize((size * SCALE, size * SCALE), Image.Resampling.LANCZOS)
    canvas.alpha_composite(logo, (x * SCALE, y * SCALE))


def _text_center(draw, cx, y, value, size, color, weight=400):
    latin, vi = _fonts(weight, size)
    runs = [(ch, vi if _is_vi(ch) else latin) for ch in value]
    total = sum(font.getlength(ch) for ch, font in runs)
    x = cx * SCALE - total / 2
    for ch, font in runs:
        draw.text((x, y * SCALE), ch, font=font, fill=color, anchor="ls")
        x += font.getlength(ch)


def _hue(a: float) -> tuple[int, int, int]:
    import colorsys
    h = (190 + 140 * (0.5 + 0.5 * math.sin(a))) / 360
    r, g, b = colorsys.hls_to_rgb(h, 0.64, 0.95)
    return round(r * 255), round(g * 255), round(b * 255)


def _disc_background() -> Image.Image:
    h = w = WIDTH * SCALE
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / SCALE
    d = np.hypot((xx - 260) / 0.85, (yy - 150) / 0.85) / 300.0  # tâm hơi cao, nền sáng nhất ở đỉnh
    d = np.clip(d, 0, 1)[..., None]
    c0, c1, c2 = np.array([18, 92, 120]), np.array([9, 42, 68]), np.array([5, 13, 24])
    rgb = np.where(d < 0.5, c0 + (c1 - c0) * (d / 0.5), c1 + (c2 - c1) * ((d - 0.5) / 0.5))
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")


def _ring(canvas: Image.Image, cx: int, cy: int) -> None:
    """Vòng phổ âm thanh quanh logo (cùng công thức với màn hình chờ trong app, đóng băng ở một khung đẹp)."""
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bars = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd, bd = ImageDraw.Draw(glow), ImageDraw.Draw(bars)
    n = 84
    for i in range(n):
        a = i / n * math.tau - math.pi / 2
        w = math.sin(a * 3 + 1.9) * 0.5 + math.sin(a * 5 - 2.2) * 0.35 + math.sin(a * 2 + 0.9) * 0.3
        length = 10 + abs(w) * 34 + 5 * math.sin(i * 0.7) ** 2
        color = _hue(a + 0.8)
        p0 = ((cx + math.cos(a) * 72) * SCALE, (cy + math.sin(a) * 72) * SCALE)
        p1 = ((cx + math.cos(a) * (72 + length)) * SCALE, (cy + math.sin(a) * (72 + length)) * SCALE)
        gd.line((*p0, *p1), fill=color + (150,), width=round(8 * SCALE))
        bd.line((*p0, *p1), fill=color + (255,), width=round(3.4 * SCALE))
        for px, py in (p0, p1):  # đầu bo tròn
            r = 1.7 * SCALE
            bd.ellipse((px - r, py - r, px + r, py + r), fill=color + (255,))
    from PIL import ImageFilter
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7 * SCALE)))
    canvas.alpha_composite(bars)


def render(output: Path = ROOT / "assets" / "splash.png") -> Path:
    s = SCALE
    size = WIDTH * s
    canvas = _disc_background()
    draw = ImageDraw.Draw(canvas)
    # Viền đĩa: vòng xanh mờ + vòng tối ngoài cùng.
    draw.ellipse((6 * s, 6 * s, size - 6 * s, size - 6 * s), outline=(34, 211, 238, 110), width=2 * s)
    _ring(canvas, 260, 186)
    _logo(canvas, 260 - 56, 186 - 56, 112)
    draw = ImageDraw.Draw(canvas)
    _text_center(draw, 260, 334, "Voice AI - Mr. Huỳnh", 27, "#ffffff", 700)
    _text_center(draw, 260, 356, "Chuyển văn bản thành giọng nói tiếng Việt", 12, "#9fc3cf", 400)
    # Thanh tiến trình (tĩnh) + trạng thái + phiên bản.
    draw.rounded_rectangle((180 * s, 392 * s, 340 * s, 397 * s), radius=3 * s, fill=(30, 52, 71, 255))
    for x in range(180 * s, round((180 + 160 * 0.46) * s)):
        u = (x - 180 * s) / (160 * 0.46 * s)
        col = (round(34 + 134 * u), round(211 - 128 * u), round(238 - 55 * u)) if u < 0.5 else (round(168 + 87 * (u - .5) * 2), round(85 - 6 * (u - .5) * 2), round(247 - 84 * (u - .5) * 2))
        draw.line((x, 392 * s, x, 397 * s), fill=col)
    _text_center(draw, 260, 421, "Đang khởi động…", 12, "#d7eef3", 600)
    _text_center(draw, 260, 445, f"v{APP_VERSION}  ·  Mr.Huỳnh", 11, "#7fa3b0", 500)

    # Cắt hình tròn: ngoài đĩa trong suốt hẳn. Trộn viền vào màu tối của đĩa trước khi nhị phân hóa alpha
    # (splash của PyInstaller trên Windows chỉ hiểu trong suốt hoặc đặc, nên không để viền mờ nửa trong suốt).
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).ellipse((2 * s, 2 * s, size - 2 * s, size - 2 * s), fill=255)
    rim = Image.new("RGBA", canvas.size, (11, 31, 51, 255))
    rim.paste(canvas, (0, 0), mask)
    # PyInstaller chỉ cho splash cao tối đa 480 px (mặc định max_img_size), nên xuất 480x480 để khỏi bị co lại.
    final = (480, 480)
    out = rim.resize(final, Image.Resampling.LANCZOS)
    alpha = mask.resize(final, Image.Resampling.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    out.putalpha(alpha)
    out.save(output)
    return output


if __name__ == "__main__":
    print(render())
