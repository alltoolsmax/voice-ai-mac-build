"""
VoxCPM2 (OpenBMB, Apache-2.0): giọng đọc 30 ngôn ngữ (có tiếng Việt), 48 kHz, chạy GPU NVIDIA.

Gói `voxcpm` KHÔNG nằm trong bản cài: nó được `apps/voxcpm_installer.py` cài vào venv GPU của
máy người dùng khi họ bấm Tải về, cùng PyTorch/CUDA. File này chỉ là lớp nối cùng giao diện
engine mà web_stream đã dùng cho VieNeu/Supertonic/Kokoro (`infer`, `infer_stream`,
`list_preset_voices`, `_preset_voices`, `add_voice`...), nên không import `voxcpm` ở đầu file.

Hai cách chọn giọng:
  * Giọng thiết kế: mô tả bằng chữ đặt trong ngoặc đơn ở đầu câu, vd "(giọng nữ trẻ, ấm)Xin chào".
    Danh sách PRESETS bên dưới là các mô tả do chính app đặt; người dùng có thể gõ mô tả riêng
    bằng voice_id dạng ``thiết kế: <mô tả>``.
  * Giọng nhân bản: một đoạn tiếng mẫu 3-15 giây, truyền qua ``reference_wav_path``.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import numpy as np

SAMPLE_RATE = 48_000
CFG_VALUE = 2.0
INFERENCE_TIMESTEPS = 10
MAX_CHUNK_CHARS = 280
CHUNK_SILENCE_S = 0.12
DESIGN_PREFIX = "thiết kế:"
MAX_DESIGN_CHARS = 200

# (id hiển thị, giới tính, mô tả tiếng Việt cho thẻ giọng, mô tả đưa cho mô hình)
PRESETS: List[tuple] = [
    ("Người dẫn chuyện nữ", "female", "Nữ · Trung niên · Trầm ấm, kể chuyện",
     "a middle-aged woman, low warm voice, calm storyteller, slow and clear"),
    ("Người dẫn chuyện nam", "male", "Nam · Trung niên · Trầm, tài liệu",
     "a middle-aged man, deep steady voice, documentary narrator"),
    ("Giọng nữ nhẹ nhàng", "female", "Nữ · Trẻ · Nhẹ nhàng, thư giãn",
     "a young woman, soft gentle voice, relaxed and soothing"),
    ("Giọng nam trẻ trung", "male", "Nam · Trẻ · Năng động",
     "a young man, bright energetic voice, friendly and lively"),
    ("MC nữ chuyên nghiệp", "female", "Nữ · Trẻ · Rõ ràng, tin tức",
     "a young woman, clear confident voice, professional news presenter"),
    ("MC nam chuyên nghiệp", "male", "Nam · Trẻ · Rõ ràng, tin tức",
     "a man in his thirties, clear confident voice, professional host"),
    ("Giọng ông lão", "male", "Nam · Cao tuổi · Chậm, trầm",
     "an elderly man, low slow voice, wise and gentle"),
    ("Giọng bà cụ", "female", "Nữ · Cao tuổi · Chậm, ấm",
     "an elderly woman, warm slow voice, kind grandmother"),
    ("Giọng bé gái", "female", "Nữ · Trẻ em · Cao, vui vẻ",
     "a little girl, high cheerful voice, playful"),
    ("Giọng bé trai", "male", "Nam · Trẻ em · Cao, tinh nghịch",
     "a little boy, high lively voice, mischievous"),
    ("Giọng quảng cáo nữ", "female", "Nữ · Quảng cáo · Tươi sáng",
     "a woman, bright upbeat voice, enthusiastic advertisement"),
    ("Giọng quảng cáo nam", "male", "Nam · Quảng cáo · Mạnh mẽ",
     "a man, strong powerful voice, energetic commercial announcer"),
    ("Giọng thì thầm", "female", "Nữ · Thì thầm, bí ẩn",
     "a woman whispering softly, mysterious and intimate"),
    ("Giảng viên nữ", "female", "Nữ · Trung niên · Giảng bài",
     "a woman teacher, clear moderate-pitched voice, patient and explanatory"),
    ("Giảng viên nam", "male", "Nam · Trung niên · Giảng bài",
     "a man lecturer, steady moderate-pitched voice, clear and authoritative"),
    ("Giọng hoạt hình", "neutral", "Hoạt hình · Vui nhộn",
     "an animated cartoon character, exaggerated playful voice, comedic"),
]

_BRACKET_TAG = re.compile(r"\[[^\]]*\]")
_PARAGRAPHS = re.compile(r"\n\s*\n+")
_SENTENCES = re.compile(r"(?<=[.!?…。！？])\s+")


def chunk_text(text: str, max_len: int = MAX_CHUNK_CHARS) -> List[str]:
    """Chia theo đoạn rồi theo câu, mỗi mảnh ≤ ``max_len`` ký tự khi có thể."""
    chunks: List[str] = []
    for para in (p.strip() for p in _PARAGRAPHS.split(text.strip())):
        if not para:
            continue
        cur = ""
        for sent in (s for s in _SENTENCES.split(para) if s.strip()):
            if cur and len(cur) + len(sent) + 1 > max_len:
                chunks.append(cur.strip())
                cur = sent
            else:
                cur = f"{cur} {sent}" if cur else sent
        if cur.strip():
            chunks.append(cur.strip())
    return chunks


def _clean_design(description: str) -> str:
    """Mô tả giọng do người dùng gõ: bỏ ngoặc (sẽ làm hỏng cú pháp), gọn khoảng trắng, giới hạn độ dài."""
    text = re.sub(r"[()（）\[\]\n\r]", " ", description)
    return re.sub(r"\s+", " ", text).strip()[:MAX_DESIGN_CHARS]


class VoxCPM2TTS:
    """VoxCPM2 qua gói ``voxcpm``. ``model`` truyền sẵn dùng cho kiểm thử (khỏi nạp 4,6 GB)."""

    backend = "pytorch"
    precision = "bf16"
    device = "cuda"
    sample_rate = SAMPLE_RATE
    languages: Dict[str, str] = {}   # tự nhận ngôn ngữ từ chữ, không có ô chọn

    def __init__(self, model_dir=None, custom_path=None, model=None):
        if model is None:
            model = self._load(model_dir)
        self._model = model
        try:
            self.sample_rate = int(model.tts_model.sample_rate)
        except Exception:
            self.sample_rate = SAMPLE_RATE
        self._default_voice = PRESETS[0][0]
        self._preset_voices: Dict[str, dict] = {
            name: {"gender": gender, "description": mota, "prompt": prompt}
            for name, gender, mota, prompt in PRESETS
        }
        self._custom_path = Path(custom_path) if custom_path else None
        if self._custom_path:
            self._load_custom()

    @staticmethod
    def _load(model_dir):
        from voxcpm import VoxCPM  # chỉ có sau khi voxcpm_installer cài vào venv GPU

        return VoxCPM.from_pretrained(str(model_dir), load_denoiser=False)

    # --- giọng nhân bản: lưu file mẫu cạnh file json ----------------------------------
    def _audio_dir(self) -> Path:
        return self._custom_path.with_name(self._custom_path.stem + "_audio")

    def _load_custom(self) -> None:
        try:
            data = json.loads(self._custom_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, item in (data.get("voices") or {}).items():
            wav = self._audio_dir() / str(item.get("wav", ""))
            if wav.is_file() and name not in self._preset_voices:
                self._preset_voices[name] = {
                    "gender": "neutral", "description": "Giọng nhân bản", "is_custom": True,
                    "ref": str(wav), "authorization": item.get("authorization"),
                }
        for name, prompt in (data.get("designs") or {}).items():
            if name not in self._preset_voices and _clean_design(str(prompt)):
                self._preset_voices[name] = {
                    "gender": "neutral", "description": "Giọng tự thiết kế",
                    "is_custom": True, "prompt": _clean_design(str(prompt)),
                }

    def _save_custom(self) -> None:
        if not self._custom_path:
            return
        voices = {
            n: {"wav": Path(p["ref"]).name, "authorization": p.get("authorization")}
            for n, p in self._preset_voices.items() if p.get("is_custom") and p.get("ref")
        }
        designs = {n: p["prompt"] for n, p in self._preset_voices.items()
                   if p.get("is_custom") and not p.get("ref")}
        self._custom_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._custom_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"voices": voices, "designs": designs}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self._custom_path)

    def add_voice(self, name, ref_audio_path, denoise=False, save=True, save_path=None,
                  authorization=None, **_):
        if save_path:
            self._custom_path = Path(save_path)
        if not self._custom_path:
            raise ValueError("Chưa có nơi lưu giọng nhân bản.")
        self._audio_dir().mkdir(parents=True, exist_ok=True)
        dest = self._audio_dir() / f"{abs(hash(name)) % 10**10}-{re.sub(r'[^0-9A-Za-z]+', '', name)[:20] or 'voice'}.wav"
        shutil.copyfile(ref_audio_path, dest)
        self._preset_voices[name] = {
            "gender": "neutral", "description": "Giọng nhân bản", "is_custom": True,
            "ref": str(dest), "authorization": authorization,
        }
        if save:
            self._save_custom()
        return name

    def add_design_voice(self, name, description, save=True, save_path=None):
        """Lưu một giọng thiết kế từ mô tả bằng chữ, dùng như giọng thường (nghe thử, chọn, xoá)."""
        prompt = _clean_design(description)
        if not prompt:
            raise ValueError("Hãy mô tả giọng bằng vài từ.")
        if save_path:
            self._custom_path = Path(save_path)
        self._preset_voices[name] = {
            "gender": "neutral", "description": "Giọng tự thiết kế", "is_custom": True, "prompt": prompt,
        }
        if save:
            self._save_custom()
        return name

    def remove_voice(self, name, save=True, save_path=None, **_):
        item = self._preset_voices.get(name)
        if not item or not item.get("is_custom"):
            raise ValueError("Không phải giọng tuỳ chỉnh.")
        del self._preset_voices[name]
        if item.get("ref"):
            Path(item["ref"]).unlink(missing_ok=True)
        if save_path:
            self._custom_path = Path(save_path)
        if save:
            self._save_custom()

    # --- danh sách giọng (cùng kiểu engine VieNeu) -------------------------------------
    def list_preset_voices(self) -> List[tuple]:
        return [(name, name) for name in self._preset_voices]

    def resolve_voice_name(self, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        key = str(name).strip()
        if key.lower().startswith(DESIGN_PREFIX):
            return key if _clean_design(key[len(DESIGN_PREFIX):]) else None
        return key if key in self._preset_voices else None

    # --- đọc ---------------------------------------------------------------------------
    def _generate(self, text: str, voice: str) -> np.ndarray:
        kwargs = {"cfg_value": CFG_VALUE, "inference_timesteps": INFERENCE_TIMESTEPS}
        if voice.lower().startswith(DESIGN_PREFIX):
            prompt = _clean_design(voice[len(DESIGN_PREFIX):])
            text = f"({prompt}){text}"
        else:
            item = self._preset_voices[voice]
            if item.get("ref"):
                kwargs["reference_wav_path"] = item["ref"]
            else:
                text = f"({item['prompt']}){text}"
        wav = self._model.generate(text=text, **kwargs)
        return np.asarray(wav, dtype=np.float32).reshape(-1)

    def _chunks(self, text: str, voice: Optional[str]) -> Iterator[np.ndarray]:
        name = self.resolve_voice_name(voice or self._default_voice)
        if name is None:
            raise ValueError(f"Voice '{voice}' not found")
        text = re.sub(r"\s+", " ", _BRACKET_TAG.sub(" ", text)).strip()  # thẻ cảm xúc app: bỏ
        for part in chunk_text(text):
            wav = self._generate(part, name)
            if len(wav):
                yield wav

    def infer_stream(self, text: str, voice: Optional[str] = None, **_) -> Iterator[np.ndarray]:
        silence = np.zeros(int(self.sample_rate * CHUNK_SILENCE_S), dtype=np.float32)
        for i, wav in enumerate(self._chunks(text, voice)):
            yield np.concatenate([silence, wav]) if i else wav

    def infer(self, text: str, voice: Optional[str] = None, **_) -> np.ndarray:
        """Đọc cả văn bản. Tốc độ do web_stream chỉnh sau (``_apply_speed``); tham số riêng
        của VieNeu (temperature, lang...) bị bỏ qua."""
        parts = list(self.infer_stream(text, voice=voice))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def close(self) -> None:
        self._model = None
