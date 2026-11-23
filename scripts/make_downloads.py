"""Tạo gói tải lên trang tải mrhuynh.net/downloads cho Voice AI (giống Video AI).

Windows (BUILD-EXE.bat tự gọi sau khi có bộ cài Setup):
    python scripts/make_downloads.py [dist/Voice-AI-MrHuynh-v<ver>-win-x86_64.exe]
  → dist/downloads-voice-upload.zip gồm:
      voice_ai_mrhuynh_win.exe   bộ cài (phần mềm TỰ CẬP NHẬT tải file này)
      voice_ai_mrhuynh_win.zip   cho khách tải (bên trong 1 tệp .exe)
      voice_win.json             phiên bản + SHA-256 (trang quản trị đọc khi bấm Phát hành)

macOS (GitHub Actions tự gọi, không cần làm gì): tạo voice_ai_mrhuynh_mac.zip (2 bộ cài chip Apple M + Intel) đưa lên
GitHub Releases với TÊN CỐ ĐỊNH – link khách tải lần đầu không đổi:
    https://github.com/alltoolsmax/voice-ai-mac-build/releases/latest/download/voice_ai_mrhuynh_mac.zip
    python scripts/make_downloads.py --mac apple=<arm64.dmg> intel=<x86_64.dmg>
  → dist/downloads-voice-mac-upload.zip gồm:
      voice_ai_mrhuynh_mac_apple.dmg / voice_ai_mrhuynh_mac_intel.dmg   (cập nhật: phần mềm mở đúng file theo chip)
      voice_ai_mrhuynh_mac.zip   cho khách tải (bên trong 2 tệp .dmg)
      voice_mac.json             phiên bản + SHA-256 từng chip

Gói KHÔNG chứa index.html / .htaccess để không đè trang tải của Video AI trong cùng thư mục.
Chữ ký cập nhật do máy chủ tạo lúc bấm Phát hành (khóa nằm trong config.php của Voice AI).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN_EXE = "voice_ai_mrhuynh_win.exe"
WIN_ZIP = "voice_ai_mrhuynh_win.zip"
WIN_JSON = "voice_win.json"
MAC_DMG = {"apple": "voice_ai_mrhuynh_mac_apple.dmg", "intel": "voice_ai_mrhuynh_mac_intel.dmg"}
MAC_ZIP = "voice_ai_mrhuynh_mac.zip"
MAC_JSON = "voice_mac.json"
MAC_NAME_IN_ZIP = {"apple": "voice_ai_mrhuynh_mac_apple.dmg", "intel": "voice_ai_mrhuynh_mac_intel.dmg"}


def app_version() -> str:
    iss = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")
    m = re.search(r'#define AppVersion\s+"([^"]+)"', iss)
    if not m:
        raise SystemExit("Không đọc được AppVersion trong scripts/installer.iss")
    return m.group(1)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _zip(dest: Path, files: dict[str, Path], store: bool = False) -> None:
    mode = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(dest, "w", mode) as zf:
        for name, src in files.items():
            zf.write(src, name)


def main_win(setup: Path | None = None) -> Path:
    ver = app_version()
    setup = Path(setup) if setup else ROOT / "dist" / f"Voice-AI-MrHuynh-v{ver}-win-x86_64.exe"
    if not setup.is_file():
        raise SystemExit(f"Không thấy bộ cài {setup} (cần cài Inno Setup 6 để BUILD-EXE.bat tạo file Setup).")
    out = ROOT / "dist" / "downloads-voice"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    exe = out / WIN_EXE
    shutil.copy2(setup, exe)
    _zip(out / WIN_ZIP, {WIN_EXE: exe})
    info = {"version": ver, "sha256": sha256(exe), "size": exe.stat().st_size}
    (out / WIN_JSON).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    pkg = ROOT / "dist" / "downloads-voice-upload.zip"
    _zip(pkg, {n: out / n for n in (WIN_EXE, WIN_ZIP, WIN_JSON)}, store=True)
    print(f"[OK] {pkg}  (Voice AI {ver}, SHA-256 {info['sha256'][:16]}…)")
    return pkg


def main_mac(apple: Path, intel: Path) -> Path:
    ver = app_version()
    out = ROOT / "dist" / "downloads-voice-mac"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    info: dict = {"version": ver}
    for arch, src in (("apple", Path(apple)), ("intel", Path(intel))):
        if not src.is_file():
            raise SystemExit(f"Không thấy {src}")
        dst = out / MAC_DMG[arch]
        shutil.copy2(src, dst)
        info[arch] = {"file": MAC_DMG[arch], "sha256": sha256(dst), "size": dst.stat().st_size}
    _zip(out / MAC_ZIP, {MAC_NAME_IN_ZIP[a]: out / MAC_DMG[a] for a in ("apple", "intel")}, store=True)
    (out / MAC_JSON).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    pkg = ROOT / "dist" / "downloads-voice-mac-upload.zip"
    _zip(pkg, {n: out / n for n in (MAC_DMG["apple"], MAC_DMG["intel"], MAC_ZIP, MAC_JSON)}, store=True)
    print(f"[OK] {pkg}  (Voice AI {ver} macOS)")
    return pkg


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--mac":
        kv = dict(a.split("=", 1) for a in args[1:] if "=" in a)
        if set(kv) != {"apple", "intel"}:
            raise SystemExit("Dùng: make_downloads.py --mac apple=<arm64.dmg> intel=<x86_64.dmg>")
        main_mac(Path(kv["apple"]), Path(kv["intel"]))
    else:
        main_win(Path(args[0]) if args else None)
