"""Cài gói `voxcpm` (VoxCPM2) vào venv GPU của máy người dùng, CHỈ khi họ bấm Tải về mô hình.

Gói này kéo theo nhiều thư viện nên không đóng gói trong bản .exe. Dùng lại venv và PyTorch/CUDA
của `apps/gpu_installer.py` (bước cài GPU chạy TRƯỚC bước này trong worker tải mô hình); ở đây
chỉ `uv pip install voxcpm` với ràng buộc giữ nguyên bản torch đã cài, rồi kiểm tra import.

KHÔNG giữ `model_lock` - chỉ được gọi từ thread nền của `apps/model_downloader.py`.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from apps import gpu_installer

VOXCPM_VERSION = "2.0.3"
_MARKER_NAME = ".voxcpm_ready"


def _marker_value() -> str:
    return json.dumps({"voxcpm": VOXCPM_VERSION, "schema": 1})


def deps_ready() -> bool:
    """Gói đã cài ở lần trước (và venv GPU còn nguyên) chưa."""
    try:
        return (gpu_installer.gpu_deps_ready()
                and (gpu_installer.gpu_venv_dir() / _MARKER_NAME).read_text(encoding="utf-8") == _marker_value())
    except OSError:
        return False


def available() -> bool:
    """Máy cài được gói này: có công cụ `uv` đi kèm app."""
    return gpu_installer.find_uv() is not None


def activate() -> bool:
    return deps_ready() and gpu_installer.activate_gpu_venv()


def install_deps(on_progress: Optional[Callable[[str], None]] = None,
                 check_cancel: Optional[Callable[[], None]] = None) -> None:
    report = on_progress or (lambda message: None)
    check = check_cancel or (lambda: None)
    check()
    if not gpu_installer.gpu_deps_ready():
        raise RuntimeError("Bộ hỗ trợ GPU chưa cài xong. Hãy bấm Tải về lại để ứng dụng cài.")
    if deps_ready():
        gpu_installer.activate_gpu_venv()
        return
    uv = gpu_installer.find_uv()
    if not uv:
        raise RuntimeError("Bản ứng dụng thiếu công cụ cài đặt. Hãy cập nhật hoặc cài lại bản mới nhất.")
    venv = gpu_installer.gpu_venv_dir()
    py = str(gpu_installer._venv_python(venv))
    marker = venv / _MARKER_NAME
    marker.unlink(missing_ok=True)
    constraints = venv.parent / "voxcpm-constraints.txt"
    # Giữ nguyên PyTorch đã cài (+cu128): uv không được thay bằng bản CPU trên PyPI.
    constraints.write_text(
        f"torch=={gpu_installer._TORCH_VERSION}\ntorchaudio=={gpu_installer._TORCHAUDIO_VERSION}\n",
        encoding="utf-8")
    report("Đang cài gói VoxCPM (vài trăm MB, có thể mất vài phút)...")
    gpu_installer._run(
        [uv, "pip", "install", "--python", py, f"voxcpm=={VOXCPM_VERSION}",
         "--constraint", str(constraints), "--index-url", "https://pypi.org/simple"],
        check, what="gói VoxCPM", hint="Kiểm tra mạng và dung lượng ổ đĩa rồi thử lại.")
    report("Đang kiểm tra gói VoxCPM...")
    gpu_installer._run([py, "-c", "import voxcpm"], check, timeout=180, what="gói VoxCPM",
                       hint="Hãy bấm Tải về lại; nếu vẫn lỗi, báo cho Mr.Huỳnh.")
    check()
    marker.write_text(_marker_value(), encoding="utf-8")
    gpu_installer.activate_gpu_venv()
