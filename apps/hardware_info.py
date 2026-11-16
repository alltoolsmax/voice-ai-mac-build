"""Nhận biết cấu hình máy (CPU, RAM, card NVIDIA, ổ đĩa) và gợi ý mô hình phù hợp.

Chỉ đọc thông tin, không cài gì. Mọi hàm dò đều nuốt lỗi và trả về "không rõ" để màn
Mô hình luôn mở được dù máy lạ.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

GB = 1024 ** 3

# Mức tối thiểu để mô hình chạy ổn (VRAM cho mô hình GPU, RAM cho mô hình CPU).
MIN_VRAM_GB: Dict[str, float] = {
    "VoxCPM2": 8.0,          # theo hướng dẫn của VoxCPM2
    "VieNeu-TTS-v3-Turbo (GPU)": 4.0,
    "Kokoro": 2.0,
}
MIN_RAM_GB = 4.0
DISK_MARGIN = 1.3  # cần trống ít nhất 130% dung lượng cần tải


def _ram_gb() -> Optional[float]:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("tot", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av2", ctypes.c_ulonglong),
                            ("ext", ctypes.c_ulonglong)]
            m = MEM()
            m.l = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.tot / GB, 1)
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) * 1024 / GB, 1)
    except Exception:
        pass
    return None


def _nvidia() -> Optional[Dict[str, Any]]:
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6, creationflags=flags,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        name, mem = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",", 1)]
        return {"name": name, "vram_gb": round(float(mem) / 1024, 1)}
    except Exception:
        return None


def _disk_free_gb(path: Path) -> Optional[float]:
    try:
        p = path
        while not p.exists() and p != p.parent:
            p = p.parent
        return round(shutil.disk_usage(p).free / GB, 1)
    except Exception:
        return None


def detect(models_dir: Optional[Path] = None) -> Dict[str, Any]:
    return {
        "cpu_cores": os.cpu_count() or None,
        "ram_gb": _ram_gb(),
        "gpu": _nvidia(),
        "disk_free_gb": _disk_free_gb(models_dir or Path.home()),
    }


def _min_vram(model_id: str) -> float:
    for key, val in MIN_VRAM_GB.items():
        if model_id.startswith(key):
            return val
    return 4.0


def assess(model_id: str, device: str, approx_bytes: int, downloaded: bool,
           hw: Dict[str, Any]) -> Dict[str, str]:
    """level: ok (phù hợp) | weak (chạy được nhưng sát) | no (chưa đủ), kèm lý do tiếng Việt."""
    gpu, ram, disk = hw.get("gpu"), hw.get("ram_gb"), hw.get("disk_free_gb")
    if device == "cuda":
        if not gpu:
            return {"level": "no", "reason": "Cần card đồ họa NVIDIA, máy này chưa thấy."}
        need = _min_vram(model_id)
        have = gpu["vram_gb"]
        if have < need * 0.75:
            return {"level": "no", "reason": f"Cần khoảng {need:g} GB VRAM, card của bạn có {have:g} GB."}
        if have < need:
            return {"level": "weak", "reason": f"Card {have:g} GB hơi sát mức {need:g} GB, có thể chậm hoặc lỗi."}
    elif ram is not None and ram < MIN_RAM_GB:
        return {"level": "weak", "reason": f"RAM {ram:g} GB hơi ít, nên có từ {MIN_RAM_GB:g} GB."}
    if not downloaded and approx_bytes and disk is not None and disk < approx_bytes / GB * DISK_MARGIN:
        return {"level": "no", "reason": f"Ổ đĩa còn trống {disk:g} GB, chưa đủ để tải."}
    return {"level": "ok", "reason": "Phù hợp với máy của bạn."}


def recommend(hw: Dict[str, Any], rows: list) -> Optional[str]:
    """Mô hình tiếng Việt nên dùng: bản GPU khi card >= 4 GB, nếu không thì bản CPU int8."""
    gpu = hw.get("gpu")
    prefer = []
    if gpu and gpu["vram_gb"] >= 4:
        prefer.append("VieNeu-TTS-v3-Turbo (GPU)")
    prefer.append("VieNeu-TTS-v3-Turbo (int8)")
    ids = {r["id"]: r for r in rows}
    for mid in prefer:
        if mid in ids and ids[mid]["fit"]["level"] != "no":
            return mid
    return None
