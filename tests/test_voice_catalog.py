from apps import voice_catalog as vc
from apps import model_catalog as mc


def rows(*ids):
    return [{"id": i, "downloaded": True, "compatible": True, "sample_rate": 48000} for i in ids]


def entries_of(engine, rate):
    return [{"id": n, "name": n, **({"language": v["language"]} if v.get("language") else {})}
            for n, v in engine._preset_voices.items()]


def test_family_of():
    assert vc.family_of("VieNeu-TTS-v3-Turbo (GPU)") == "turbo"
    assert vc.family_of(vc.NANO_ID) == "nano"
    assert vc.family_of(mc.SUPERTONIC_ID) == "supertonic"
    assert vc.family_of(mc.KOKORO_GPU_ID) == "kokoro"
    assert vc.family_of(mc.VOXCPM2_ID) == "voxcpm2"
    assert vc.family_of("x") is None


def test_pick_model_prefers_last_used_and_downloaded():
    r = rows("VieNeu-TTS-v3-Turbo (int8)", "VieNeu-TTS-v3-Turbo (GPU)")
    assert vc.pick_model("turbo", r, "VieNeu-TTS-v3-Turbo (GPU)") == "VieNeu-TTS-v3-Turbo (GPU)"
    assert vc.pick_model("turbo", r, None) == "VieNeu-TTS-v3-Turbo (int8)"
    r[0]["downloaded"] = False
    assert vc.pick_model("turbo", r, None) == "VieNeu-TTS-v3-Turbo (GPU)"
    assert vc.pick_model("kokoro", r, None) is None


def test_collect_merges_turbo_and_supertonic(monkeypatch):
    monkeypatch.setattr(vc, "custom_voices_path", lambda name: __import__("pathlib").Path("/nonexistent/x.json"))
    out = vc.collect(active_name="VieNeu-TTS-v3-Turbo (int8)", active_engine=None, active_sample_rate=48000,
                     rows=rows("VieNeu-TTS-v3-Turbo (int8)", mc.SUPERTONIC_ID), preferred=None,
                     entries_of=entries_of)
    fam = {v["family"] for v in out["voices"]}
    assert fam == {"supertonic"}  # engine đang chạy là None -> bỏ qua, không lỗi
    assert out["active_family"] == "turbo"
    assert all(v["model"] == mc.SUPERTONIC_ID for v in out["voices"])
    assert {l["code"] for l in out["languages"]} >= {"vi", "en"}
    assert out["languages"][0]["code"] == "vi"


def test_collect_reads_turbo_file_when_not_active(monkeypatch):
    monkeypatch.setattr(vc, "custom_voices_path", lambda name: __import__("pathlib").Path("/nonexistent/x.json"))
    out = vc.collect(active_name=mc.SUPERTONIC_ID, active_engine=vc._supertonic_table(), active_sample_rate=44100,
                     rows=rows("VieNeu-TTS-v3-Turbo (int8)", mc.SUPERTONIC_ID), preferred=None,
                     entries_of=entries_of)
    turbo = [v for v in out["voices"] if v["family"] == "turbo"]
    assert len(turbo) >= 20 and turbo[0]["languages"] == ["vi"]
    assert turbo[0]["model"] == "VieNeu-TTS-v3-Turbo (int8)"
    assert [v["family"] for v in out["voices"]][0] == "turbo"


def test_endpoint_all_voices(monkeypatch):
    import asyncio
    from unittest.mock import patch

    import apps.web_stream as ws

    class Fake:
        _default_voice = "A"
        _preset_voices = {"A": {"gender": "female", "description": "Nữ · Bắc · Ấm"}}

        def list_preset_voices(self):
            return [("A", "A")]

    monkeypatch.setattr(vc, "custom_voices_path", lambda name: __import__("pathlib").Path("/nonexistent/x.json"))
    monkeypatch.setattr(ws, "vieneu", Fake())
    monkeypatch.setattr(ws, "current_model_info", {"name": "VieNeu-TTS-v3-Turbo (int8)", "sample_rate": 48000})
    with patch.object(mc, "is_downloaded", return_value=True):
        out = asyncio.run(ws.all_voices())
    assert out["active_family"] == "turbo"
    first = out["voices"][0]
    assert first["id"] == "A" and first["model"] == "VieNeu-TTS-v3-Turbo (int8)" and first["languages"] == ["vi"]
    assert {v["family"] for v in out["voices"]} >= {"turbo", "supertonic"}
