import numpy as np
import pytest

from apps import voxcpm_engine as ve


class FakeModel:
    class tts_model:
        sample_rate = 48000

    def __init__(self):
        self.calls = []

    def generate(self, text, **kw):
        self.calls.append((text, kw))
        return np.ones(480, dtype=np.float32) * 0.1


def make(tmp_path=None):
    m = FakeModel()
    return ve.VoxCPM2TTS(model=m, custom_path=(tmp_path / "custom.json") if tmp_path else None), m


def test_giong_thiet_ke_dat_mo_ta_trong_ngoac():
    eng, m = make()
    wav = eng.infer("Xin chào các bạn.", voice="MC nữ chuyên nghiệp")
    assert len(wav) == 480
    text, kw = m.calls[0]
    assert text.startswith("(a young woman") and text.endswith(")Xin chào các bạn.")
    assert kw["cfg_value"] == ve.CFG_VALUE and "reference_wav_path" not in kw


def test_mo_ta_tu_do_va_lam_sach_ngoac():
    eng, m = make()
    assert eng.resolve_voice_name("thiết kế: giọng nữ (trẻ) ấm") is not None
    assert eng.resolve_voice_name("thiết kế:   ") is None
    eng.infer("Chào.", voice="thiết kế: giọng nữ (trẻ) ấm")
    assert m.calls[0][0].startswith("(giọng nữ trẻ ấm)Chào")


def test_giong_khong_ton_tai():
    eng, _ = make()
    assert eng.resolve_voice_name("Không có") is None
    with pytest.raises(ValueError):
        eng.infer("Chào.", voice="Không có")


def test_bo_the_cam_xuc_va_chia_cau():
    eng, m = make()
    eng.infer("Xin chào [cười] bạn. " + "Câu dài. " * 60)
    assert "[" not in m.calls[0][0]
    assert len(m.calls) > 1


def test_nhan_ban_giong_luu_va_nap_lai(tmp_path):
    ref = tmp_path / "mau.wav"
    ref.write_bytes(b"RIFFxxxx")
    eng, m = make(tmp_path)
    eng.add_voice("Giọng của tôi", str(ref), save=True, authorization={"confirmed": True})
    assert eng._preset_voices["Giọng của tôi"]["is_custom"]
    eng.infer("Chào.", voice="Giọng của tôi")
    text, kw = m.calls[-1]
    assert text == "Chào." and kw["reference_wav_path"].endswith(".wav")
    eng2, _ = make(tmp_path)
    assert "Giọng của tôi" in eng2._preset_voices
    eng2.remove_voice("Giọng của tôi", save=True)
    eng3, _ = make(tmp_path)
    assert "Giọng của tôi" not in eng3._preset_voices
    with pytest.raises(ValueError):
        eng3.remove_voice("MC nữ chuyên nghiệp")


def test_sample_rate_theo_mo_hinh():
    eng, _ = make()
    assert eng.sample_rate == 48000 and len(eng.list_preset_voices()) == len(ve.PRESETS)


def test_giong_tu_thiet_ke_luu_nap_lai_va_xoa(tmp_path):
    eng, m = make(tmp_path)
    eng.add_design_voice("Cô Lan", "giọng nữ (miền Nam) ấm áp", save=True)
    eng.infer("Chào.", voice="Cô Lan")
    assert m.calls[-1][0] == "(giọng nữ miền Nam ấm áp)Chào."
    eng2, _ = make(tmp_path)
    assert eng2._preset_voices["Cô Lan"]["is_custom"]
    with pytest.raises(ValueError):
        eng.add_design_voice("X", "   ")
    eng2.remove_voice("Cô Lan", save=True)
    eng3, _ = make(tmp_path)
    assert "Cô Lan" not in eng3._preset_voices


def test_model_catalog_voxcpm():
    from apps import model_catalog as mc
    spec = mc.get(mc.VOXCPM2_ID)
    assert spec and mc.is_voxcpm(spec.id) and not mc.is_kokoro(spec.id)
    assert set(spec.requires) == {"torch", "cuda"} and "gpu" not in spec.id.lower().replace("gpu nvidia", "")
    ok, _ = mc.compatible(spec, has_torch=True, has_cuda=False)
    assert not ok
    ok, _ = mc.compatible(spec, has_torch=True, has_cuda=True)
    assert ok


def test_api_thiet_ke_giong(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from apps import web_stream as ws
    eng, _ = make(tmp_path)
    monkeypatch.setattr(ws, "vieneu", eng)
    monkeypatch.setattr(ws, "_custom_voices_path", lambda: tmp_path / "custom.json")
    c = TestClient(ws.app)
    assert c.get("/health").json()["supports_design"] is True
    r = c.post("/api/voices/design", json={"name": "Cô Lan", "description": "nữ trẻ ấm"})
    assert r.status_code == 200 and "Cô Lan" in eng._preset_voices
    assert c.post("/api/voices/design", json={"name": "Cô Lan", "description": "x"}).status_code == 409
    assert c.post("/api/voices/design", json={"name": "Mới", "description": "  "}).status_code == 400
    assert any(v["id"] == "Cô Lan" for v in c.get("/voices").json())


def test_clone_co_loi_mau_dung_ultimate_cloning(tmp_path):
    ref = tmp_path / "mau.wav"
    ref.write_bytes(b"RIFFxxxx")
    eng, m = make(tmp_path)
    eng.add_voice("Có lời", str(ref), save=True, prompt_text="  Xin chào,\n tôi là   Huỳnh.  ")
    eng.add_voice("Không lời", str(ref), save=True)
    eng.infer("Chào.", voice="Có lời")
    _, kw = m.calls[-1]
    assert kw["reference_wav_path"] == kw["prompt_wav_path"]
    assert kw["prompt_text"] == "Xin chào, tôi là Huỳnh."
    eng.infer("Chào.", voice="Không lời")
    _, kw = m.calls[-1]
    assert "prompt_wav_path" not in kw and "prompt_text" not in kw   # như trước: chỉ tông giọng
    # lời mẫu được lưu cùng giọng và nạp lại sau khi mở app
    eng2, m2 = make(tmp_path)
    eng2.infer("Chào.", voice="Có lời")
    assert m2.calls[-1][1]["prompt_text"] == "Xin chào, tôi là Huỳnh."
    # giọng nhân bản cũ (json chưa có trường prompt_text) vẫn đọc được
    assert eng2._preset_voices["Không lời"]["prompt_text"] == ""


def test_loi_mau_qua_dai_bi_cat():
    assert len(ve.clean_prompt_text("a " * 400)) <= ve.MAX_PROMPT_TEXT_CHARS
    assert ve.clean_prompt_text(None) == ""
