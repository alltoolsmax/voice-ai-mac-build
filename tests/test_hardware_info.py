from apps import hardware_info as h

GPU8 = {"gpu": {"name": "RTX 3060", "vram_gb": 12.0}, "ram_gb": 16.0, "disk_free_gb": 100.0}
NOGPU = {"gpu": None, "ram_gb": 8.0, "disk_free_gb": 100.0}


def test_cpu_model_ok_without_gpu():
    assert h.assess("VieNeu-TTS-v3-Turbo (int8)", "cpu", 300_000_000, False, NOGPU)["level"] == "ok"


def test_gpu_model_needs_nvidia():
    r = h.assess("VoxCPM2 (GPU NVIDIA)", "cuda", 5_000_000_000, False, NOGPU)
    assert r["level"] == "no" and "NVIDIA" in r["reason"]


def test_vram_levels():
    low = {"gpu": {"name": "x", "vram_gb": 4.0}, "ram_gb": 16, "disk_free_gb": 100}
    edge = {"gpu": {"name": "x", "vram_gb": 6.5}, "ram_gb": 16, "disk_free_gb": 100}
    assert h.assess("VoxCPM2 (GPU)", "cuda", 0, True, low)["level"] == "no"
    assert h.assess("VoxCPM2 (GPU)", "cuda", 0, True, edge)["level"] == "weak"
    assert h.assess("VoxCPM2 (GPU)", "cuda", 0, True, GPU8)["level"] == "ok"


def test_low_disk_blocks_download_but_not_downloaded():
    hw = {"gpu": None, "ram_gb": 8, "disk_free_gb": 1.0}
    assert h.assess("Kokoro (CPU)", "cpu", 2_000_000_000, False, hw)["level"] == "no"
    assert h.assess("Kokoro (CPU)", "cpu", 2_000_000_000, True, hw)["level"] == "ok"


def test_recommend_prefers_gpu_build_when_card_big_enough():
    rows = [{"id": "VieNeu-TTS-v3-Turbo (GPU)", "fit": {"level": "ok"}},
            {"id": "VieNeu-TTS-v3-Turbo (int8)", "fit": {"level": "ok"}}]
    assert h.recommend(GPU8, rows) == "VieNeu-TTS-v3-Turbo (GPU)"
    assert h.recommend(NOGPU, rows) == "VieNeu-TTS-v3-Turbo (int8)"


def test_detect_never_raises():
    d = h.detect()
    assert set(d) == {"cpu_cores", "ram_gb", "gpu", "disk_free_gb"}
