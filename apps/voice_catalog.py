"""Danh sách giọng gộp của MỌI mô hình đã tải (cho ô "Giọng đọc" ở giao diện).

Mô hình đang chạy thì lấy giọng trực tiếp từ engine; mô hình chưa nạp thì đọc thẳng từ file
giọng (không nạp mô hình, không tốn RAM). Mỗi giọng kèm:
  family    - nhóm mô hình (turbo, nano, kokoro, supertonic, voxcpm2)
  model     - id mô hình cần nạp để đọc bằng giọng này (giao diện không hiển thị)
  languages - các ngôn ngữ giọng đọc được ("*" = mọi ngôn ngữ)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from apps import model_catalog

FAMILIES = ("turbo", "nano", "kokoro", "supertonic", "voxcpm2")
NANO_ID = "VieNeu-TTS-v3-Nano (preview)"
VI = "vi"


def family_of(model_id: Optional[str]) -> Optional[str]:
    if not model_id:
        return None
    if model_catalog.is_voxcpm(model_id):
        return "voxcpm2"
    if model_id == model_catalog.SUPERTONIC_ID:
        return "supertonic"
    if model_catalog.is_kokoro(model_id):
        return "kokoro"
    if model_id == NANO_ID:
        return "nano"
    if model_id.startswith("VieNeu-TTS-v3-Turbo"):
        return "turbo"
    return None


def custom_voices_path(model_name: Optional[str]) -> Path:
    """File JSON giọng do người dùng lưu (khác file giọng có sẵn trong gói cài đặt)."""
    from apps.runtime_paths import _is_writable, app_root

    name = (model_name or "").lower()
    if model_catalog.is_voxcpm(model_name):
        filename = "custom_voices_voxcpm2.json"   # khác định dạng với giọng VieNeu
    else:
        filename = "custom_voices_v3_nano.json" if "nano" in name else "custom_voices_v3_turbo.json"
    d = app_root() / "models"
    if _is_writable(d):
        return d / filename
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    p = Path(base) / "VoiceAIMrHuynh" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class _Table:
    """Engine giả chỉ có bảng giọng: đủ cho `_voice_entries` ở web_stream."""

    def __init__(self, presets: Dict[str, dict], default: Optional[str]):
        self._preset_voices = presets
        self._default_voice = default

    def list_preset_voices(self) -> list:
        return [(n, n) for n in self._preset_voices]


def _assets_dir() -> Path:
    import importlib.util

    spec = importlib.util.find_spec("vieneu")
    root = Path(next(iter(spec.submodule_search_locations))) if spec and spec.submodule_search_locations else Path()
    return root / "assets"


def _featured(v: dict) -> Optional[int]:
    try:
        r = int(v.get("featured"))
    except (TypeError, ValueError):
        return None
    return r if r > 0 else None


def _read_vieneu_voices(path: Path, presets: Dict[str, dict], *, custom: bool) -> Optional[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for name, v in (data.get("presets") or {}).items():
        if custom and name in presets:
            continue
        presets[name] = {
            "description": v.get("description", ""),
            "gender": v.get("gender", ""),
            "is_custom": custom or bool(v.get("is_custom", False)),
            "featured": None if custom else _featured(v),
        }
    return data.get("default_voice") if not custom else None


def _vieneu_table(family: str) -> _Table:
    builtin = _assets_dir() / ("voices_v3_nano.json" if family == "nano" else "voices_v3_turbo.json")
    presets: Dict[str, dict] = {}
    default = _read_vieneu_voices(builtin, presets, custom=False)
    # Giọng có sẵn: giọng nổi bật lên trước (như engine thật), còn lại giữ thứ tự file.
    ordered = sorted(presets.items(), key=lambda kv: (kv[1].get("featured") is None, kv[1].get("featured") or 0))
    presets = dict(ordered)
    _read_vieneu_voices(custom_voices_path(NANO_ID if family == "nano" else "VieNeu-TTS-v3-Turbo"), presets, custom=True)
    return _Table(presets, default or next(iter(presets), None))


def _kokoro_table() -> Optional[_Table]:
    from huggingface_hub import hf_hub_download

    from apps import kokoro_installer
    from apps.kokoro_engine import voice_keys, voice_table

    try:
        heart = hf_hub_download(model_catalog.KOKORO_REPO, "voices/af_heart.bin",
                                revision=model_catalog.KOKORO_REVISION, local_files_only=True)
    except Exception:
        return None
    langs = set(kokoro_installer.ready_languages()) or set(kokoro_installer.BASE_LANGUAGES)
    keys = voice_keys(Path(heart).parent, langs)
    if not keys:
        return None
    names, presets = voice_table(keys)
    return _Table(presets, next(iter(names)))


def _supertonic_table() -> _Table:
    from apps.supertonic_engine import DEFAULT_VOICE, preset_table

    return _Table(preset_table(), DEFAULT_VOICE)


def _voxcpm_table() -> _Table:
    from apps.voxcpm_engine import PRESETS, VoxCPM2TTS

    engine = VoxCPM2TTS(model=object(), custom_path=custom_voices_path(model_catalog.VOXCPM2_ID))
    return _Table(engine._preset_voices, PRESETS[0][0])


def _languages_of(family: str, entry: dict) -> List[str]:
    if family == "kokoro":
        return [entry["language"]] if entry.get("language") else []
    if family == "supertonic":
        from apps.supertonic_engine import LANGUAGES
        return list(LANGUAGES)
    if family == "voxcpm2":
        return ["*"]
    return [VI]


def language_names() -> Dict[str, str]:
    names: Dict[str, str] = {}
    try:
        from apps.supertonic_engine import LANGUAGES as sup
        names.update(sup)
    except Exception:
        pass
    try:
        from apps.kokoro_engine import LANGUAGES as kok
        names.update(kok)
    except Exception:
        pass
    names[VI] = "Tiếng Việt"
    return names


def pick_model(family: str, rows: Iterable[dict], preferred: Optional[str]) -> Optional[str]:
    """Mô hình nạp để dùng nhóm `family`: ưu tiên mô hình dùng gần nhất, rồi theo thứ tự danh mục.
    Chỉ nhận mô hình đã tải và chạy được trên máy này."""
    ok = [r["id"] for r in rows if family_of(r["id"]) == family and r.get("downloaded") and r.get("compatible")]
    if preferred in ok:
        return preferred
    return ok[0] if ok else None


def collect(
    *,
    active_name: Optional[str],
    active_engine,
    active_sample_rate: int,
    rows: List[dict],
    preferred: Optional[str],
    entries_of: Callable[[object, int], list],
) -> dict:
    """Gộp giọng. `entries_of` = web_stream._voice_entries (giữ một nơi định dạng giọng)."""
    active_family = family_of(active_name)
    sample_rates = {r["id"]: r.get("sample_rate", 48_000) for r in rows}
    builders = {
        "turbo": lambda: _vieneu_table("turbo"),
        "nano": lambda: _vieneu_table("nano"),
        "kokoro": _kokoro_table,
        "supertonic": _supertonic_table,
        "voxcpm2": _voxcpm_table,
    }
    voices: List[dict] = []
    seen = set()
    order = ([active_family] if active_family else []) + [f for f in FAMILIES if f != active_family]
    by_family: Dict[str, list] = {}
    for family in order:
        model = active_name if family == active_family else pick_model(family, rows, preferred)
        if not model:
            continue
        try:
            if family == active_family:
                engine, rate = active_engine, active_sample_rate
            else:
                engine, rate = builders[family](), sample_rates.get(model, 48_000)
            if engine is None:
                continue
            entries = entries_of(engine, rate)
        except Exception:
            continue
        for e in entries:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            e["family"] = family
            e["model"] = model
            e["languages"] = _languages_of(family, e)
            by_family.setdefault(family, []).append(e)
    # Thứ tự hiển thị cố định theo họ; mô hình đang chạy không làm danh sách nhảy.
    for family in FAMILIES:
        voices.extend(by_family.get(family, []))

    names = language_names()
    codes = {c for v in voices for c in v["languages"] if c != "*"}
    if any("*" in v["languages"] for v in voices):
        codes |= set(names)   # VoxCPM2 tự nhận ngôn ngữ: coi như đọc được mọi thứ tiếng trong danh sách
    ordered_codes = ([VI] if VI in codes else []) + sorted((c for c in codes if c != VI), key=lambda c: names.get(c, c))
    return {
        "active_family": active_family,
        "voices": voices,
        "languages": [{"code": c, "name": names.get(c, c)} for c in ordered_codes],
    }
