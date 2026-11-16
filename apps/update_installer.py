"""Tự cập nhật: tải bộ cài từ máy chủ phát hành, kiểm chữ ký, chạy cài đè rồi thoát app.

An toàn: file chỉ được chạy khi
  1. link là https và kết thúc bằng .exe,
  2. SHA-256 của file tải về khớp `sha256` trong version.json,
  3. chữ ký Ed25519 của Mr.Huỳnh trên "<version>|<sha256>" hợp lệ (cùng khoá công khai với
     key kích hoạt, nhưng tiền tố miền riêng nên không dùng lẫn được).
Ai chiếm được hosting cũng không ký được file giả vì không có khoá riêng.
"""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import shutil
import threading
import urllib.request
import zipfile
from pathlib import Path

from apps import _ed25519 as ed
from apps.license_pubkey import PUBLIC_KEY_HEX
from apps.runtime_paths import https_context

DOMAIN = b"VoiceAI-MrHuynh-update-v1"
MAX_BYTES = 4 * 1024 ** 3
CHUNK = 1024 * 256
INSTALLER_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]

_lock = threading.Lock()
_state: dict = {"state": "idle", "percent": 0, "message": "", "version": None, "path": None,
                "kind": None, "stage": None}


def update_message(version: str, sha256_hex: str) -> bytes:
    return DOMAIN + f"{version}|{sha256_hex.lower()}".encode()


def verify_signature(version: str, sha256_hex: str, signature_b64: str,
                     public_key: bytes | None = None) -> bool:
    try:
        sig = base64.b64decode(signature_b64, validate=True)
        pub = public_key or bytes.fromhex(PUBLIC_KEY_HEX)
        return len(sig) == 64 and ed.verify(pub, update_message(version, sha256_hex), sig)
    except Exception:
        return False


def can_auto_install() -> bool:
    """Chỉ bản .exe đã cài trên Windows mới tự cài đè; chạy từ mã nguồn thì mở link tải."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def is_installer_url(url: str) -> bool:
    """Link tải trực tiếp: .exe (bộ cài Inno) hoặc .zip (bản di động: exe + thư mục _internal)."""
    return url.startswith("https://") and url.lower().split("?")[0].endswith((".exe", ".zip"))


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _writable(folder: Path) -> bool:
    try:
        probe = folder / ".update-write-test"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def extract_package(zip_path: Path, stage: Path, exe_name: str) -> Path:
    """Giải nén gói .zip vào `stage` (chặn đường dẫn thoát ra ngoài) và trả về thư mục gốc
    của bản mới: nơi chứa `exe_name` (ngay ở gốc zip hoặc trong một thư mục con duy nhất)."""
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    root = stage.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (stage / info.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("Gói cập nhật chứa đường dẫn không an toàn, đã huỷ.")
        z.extractall(stage)
    for candidate in [stage, *[d for d in stage.iterdir() if d.is_dir()]]:
        if (candidate / exe_name).is_file():
            return candidate
    raise RuntimeError(f"Gói cập nhật không chứa {exe_name}. Có thể sai file, đã huỷ.")


KEEP_DIRS = ("models", "gpu_venv", "addons")  # dữ liệu người dùng/mô hình đã tải: giữ nguyên


def build_swap_script(pid: int, app: Path, source: Path, exe_name: str, stage: Path) -> str:
    """Script .bat: chờ app thoát, thay `_internal` và file mới, mở lại app. Hỏng thì khôi phục.

    Chờ bằng PowerShell (WaitForExit, tối đa 90 giây) thay vì vòng tasklist/timeout: `timeout` lỗi khi
    script chạy không có console, còn tasklist có thể treo. Mỗi bước ghi vào update-swap.log cạnh app.
    """
    keep = " ".join(KEEP_DIRS)
    log = f'"{app}\\update-swap.log"'
    return f"""@echo off
chcp 65001 >nul
echo [%date% %time%] Bat dau cap nhat, cho app (PID {pid}) thoat >> {log}
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ if (-not $p.WaitForExit(90000)) {{ exit 1 }} }}; exit 0" >nul 2>&1
if errorlevel 1 goto fail
ping -n 3 127.0.0.1 >nul
echo [%date% %time%] App da thoat, dang thay file >> {log}
:swap
if exist "{app}\\_internal.old" rmdir /s /q "{app}\\_internal.old"
if exist "{app}\\_internal" move "{app}\\_internal" "{app}\\_internal.old" >nul
robocopy "{source}" "{app}" /E /XD {keep} /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto restore
if exist "{app}\\_internal.old" rmdir /s /q "{app}\\_internal.old"
echo [%date% %time%] Thay file xong >> {log}
goto done
:restore
echo [%date% %time%] Loi khi chep, khoi phuc ban cu >> {log}
if exist "{app}\\_internal" rmdir /s /q "{app}\\_internal"
if exist "{app}\\_internal.old" move "{app}\\_internal.old" "{app}\\_internal" >nul
goto done
:fail
echo [%date% %time%] App khong thoat sau 90 giay, huy cap nhat >> {log}
:done
rmdir /s /q "{stage}" 2>nul
start "" "{app}\\{exe_name}"
(goto) 2>nul & del "%~f0"
"""


def status() -> dict:
    with _lock:
        return {k: v for k, v in _state.items() if k not in ("path", "stage")}


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def _download(url: str, version: str, sha256_hex: str, signature: str, dest_dir: Path) -> None:
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = os.path.basename(url.split("?")[0]) or f"Voice-AI-update-{version}.exe"
        target = dest_dir / name
        part = target.with_suffix(".part")
        digest = hashlib.sha256()
        request = urllib.request.Request(url, headers={"User-Agent": "Voice-AI-MrHuynh-updater"})
        with urllib.request.urlopen(request, timeout=30, context=https_context()) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            if total > MAX_BYTES:
                raise RuntimeError("File cập nhật lớn bất thường, đã huỷ.")
            done = 0
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_BYTES:
                    raise RuntimeError("File cập nhật lớn bất thường, đã huỷ.")
                digest.update(chunk)
                out.write(chunk)
                if total:
                    _set(percent=min(99, int(done * 100 / total)),
                         message=f"Đang tải {done // 1048576}/{total // 1048576} MB")
        _set(message="Đang kiểm tra chữ ký...")
        if digest.hexdigest().lower() != sha256_hex.lower():
            raise RuntimeError("File tải về không khớp mã kiểm tra, đã huỷ để an toàn.")
        if not verify_signature(version, sha256_hex, signature):
            raise RuntimeError("Chữ ký của file cập nhật không hợp lệ, đã huỷ để an toàn.")
        os.replace(part, target)
        if target.suffix.lower() == ".zip":
            _set(message="Đang giải nén...")
            exe_name = Path(sys.executable).name
            stage = app_dir() / "_update_staging" if can_auto_install() else dest_dir / "stage"
            source = extract_package(target, stage, exe_name)
            target.unlink(missing_ok=True)
            _set(state="ready", percent=100, message="Đã tải xong, sẵn sàng cài.",
                 path=str(source), kind="zip", stage=str(stage))
        else:
            _set(state="ready", percent=100, message="Đã tải xong, sẵn sàng cài.", path=str(target), kind="exe")
    except Exception as exc:  # mọi lỗi mạng/ghi file đều báo tiếng Việt, không để thread chết im
        message = str(exc) if isinstance(exc, RuntimeError) else "Không tải được bản cập nhật. Kiểm tra mạng rồi thử lại."
        _set(state="error", message=message, path=None)


def start_download(latest: dict, dest_dir: Path | None = None) -> dict:
    """latest = {"version","url","sha256","signature"} lấy từ kết quả kiểm tra cập nhật."""
    version, url = str(latest.get("version") or ""), str(latest.get("url") or "")
    sha, sig = str(latest.get("sha256") or ""), str(latest.get("signature") or "")
    if not (version and is_installer_url(url) and sha and sig):
        raise ValueError("Bản này chưa hỗ trợ cập nhật tự động. Hãy dùng nút tải bản mới.")
    if not verify_signature(version, sha, sig):
        raise ValueError("Chữ ký của bản cập nhật không hợp lệ.")
    if url.lower().split("?")[0].endswith(".zip") and can_auto_install() and not _writable(app_dir()):
        raise ValueError("Thư mục cài đặt không cho ghi (ví dụ Program Files). Hãy tải thủ công và giải nén lại.")
    with _lock:
        if _state["state"] == "downloading":
            return {k: v for k, v in _state.items() if k not in ("path", "stage")}
        _state.update(state="downloading", percent=0, message="Đang bắt đầu tải...", version=version, path=None)
    folder = dest_dir or Path(tempfile.gettempdir()) / "VoiceAIMrHuynh-update"
    threading.Thread(target=_download, args=(url, version, sha, sig, folder), daemon=True).start()
    return status()


def launch_installer(exit_after: bool = True) -> None:
    """Chạy bộ cài im lặng (.exe) hoặc script thay file (.zip) rồi thoát app để ghi đè."""
    with _lock:
        ready = _state["state"] == "ready"
        path, kind, stage = _state.get("path"), _state.get("kind"), _state.get("stage")
    if not ready or not path or not Path(path).exists():
        raise ValueError("Chưa có bản cập nhật đã tải xong.")
    win = sys.platform == "win32"
    if kind == "zip":
        app = app_dir()
        script = Path(tempfile.gettempdir()) / "VoiceAIMrHuynh-swap.bat"
        script.write_text(build_swap_script(os.getpid(), app, Path(path), Path(sys.executable).name,
                                            Path(stage)), encoding="utf-8")
        kwargs: dict = {}
        if win:  # console mới nhưng ẩn: script cần có console để chạy ổn định
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = 0  # SW_HIDE
            kwargs = {"startupinfo": info, "creationflags": 0x00000010 | 0x00000200}  # NEW_CONSOLE | NEW_GROUP
        subprocess.Popen(["cmd.exe", "/c", str(script)], close_fds=True, **kwargs)
    else:
        flags = 0x00000008 | 0x00000200 if win else 0
        subprocess.Popen([path, *INSTALLER_ARGS], creationflags=flags, close_fds=True)
    if exit_after:
        threading.Timer(1.2, lambda: os._exit(0)).start()
