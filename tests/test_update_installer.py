import base64
import hashlib
import sys
import types
from pathlib import Path

import pytest

from apps import _ed25519 as ed
from apps import update_installer as ui

SEED = bytes(range(32))
PUB = ed.public_key(SEED)


def sign(version, sha):
    return base64.b64encode(ed.sign(SEED, ui.update_message(version, sha))).decode()


def test_chu_ky_dung_va_sai():
    sha = hashlib.sha256(b"abc").hexdigest()
    sig = sign("1.5.0", sha)
    assert ui.verify_signature("1.5.0", sha, sig, PUB)
    assert not ui.verify_signature("1.5.1", sha, sig, PUB)           # đổi phiên bản
    assert not ui.verify_signature("1.5.0", "0" * 64, sig, PUB)     # đổi nội dung
    assert not ui.verify_signature("1.5.0", sha, "###", PUB)         # rác
    assert not ui.verify_signature("1.5.0", sha, sig)                # khoá công khai thật không khớp khoá thử


def test_chu_ky_key_kich_hoat_khong_dung_lai_duoc():
    from apps import license_codec as codec
    payload = bytes([1, 1]) + b"12345678" + (5).to_bytes(2, "big")
    sig = ed.sign(SEED, codec.DOMAIN + payload)
    assert not ui.verify_signature("1.5.0", "a" * 64, base64.b64encode(sig).decode(), PUB)


def test_chi_nhan_link_exe_https():
    assert ui.is_installer_url("https://a.b/x.exe")
    assert ui.is_installer_url("https://a.b/x.exe?t=1")
    assert not ui.is_installer_url("http://a.b/x.exe")
    assert ui.is_installer_url("https://a.b/app.zip")
    assert not ui.is_installer_url("https://a.b/app.rar")
    assert not ui.is_installer_url("https://drive.google.com/file/d/1/view")


def test_khong_tu_cai_khi_chay_tu_ma_nguon():
    assert ui.can_auto_install() is False


def test_start_download_tu_choi_thieu_chu_ky(monkeypatch):
    with pytest.raises(ValueError):
        ui.start_download({"version": "1.5.0", "url": "https://a.b/x.exe", "sha256": "", "signature": ""})


def _fake_urlopen(payload: bytes):
    class R:
        headers = {"Content-Length": str(len(payload))}
        def __init__(self): self.b = payload
        def read(self, n):
            out, self.b = self.b[:n], self.b[n:]
            return out
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return lambda *a, **k: R()


def _run(monkeypatch, tmp_path, payload, sha, version="1.5.0", url_name="Voice.exe"):
    monkeypatch.setattr(ui, "PUBLIC_KEY_HEX", PUB.hex())
    monkeypatch.setattr(ui.urllib.request, "urlopen", _fake_urlopen(payload))
    ui._state.update(state="idle", percent=0, message="", version=None, path=None)
    ui._download(f"https://a.b/{url_name}", version, sha, sign(version, sha), tmp_path)
    return ui.status()


def test_tai_dung_file_thi_san_sang(monkeypatch, tmp_path):
    data = b"installer-bytes" * 1000
    st = _run(monkeypatch, tmp_path, data, hashlib.sha256(data).hexdigest())
    assert st["state"] == "ready"
    assert (tmp_path / "Voice.exe").read_bytes() == data


def test_file_bi_tráo_thi_huy(monkeypatch, tmp_path):
    good = b"installer-bytes"
    st = _run(monkeypatch, tmp_path, b"EVIL", hashlib.sha256(good).hexdigest())
    assert st["state"] == "error"
    assert not (tmp_path / "Voice.exe").exists()


def test_launch_can_file_da_tai(monkeypatch):
    ui._state.update(state="idle", path=None)
    with pytest.raises(ValueError):
        ui.launch_installer(exit_after=False)


def test_launch_chay_bo_cai_im_lang(monkeypatch, tmp_path):
    exe = tmp_path / "s.exe"
    exe.write_bytes(b"x")
    ui._state.update(state="ready", path=str(exe))
    calls = []
    monkeypatch.setattr(ui.subprocess, "Popen", lambda args, **k: calls.append(args))
    ui.launch_installer(exit_after=False)
    assert calls[0][0] == str(exe) and "/SILENT" in calls[0] and "/CLOSEAPPLICATIONS" in calls[0]


import zipfile


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


def test_giai_nen_goc_zip_hoac_thu_muc_con(tmp_path):
    _zip(tmp_path / "a.zip", {"Voice.exe": b"x", "_internal/lib.dll": b"y"})
    assert ui.extract_package(tmp_path / "a.zip", tmp_path / "s1", "Voice.exe") == tmp_path / "s1"
    _zip(tmp_path / "b.zip", {"Voice-AI/Voice.exe": b"x", "Voice-AI/_internal/lib.dll": b"y"})
    assert ui.extract_package(tmp_path / "b.zip", tmp_path / "s2", "Voice.exe") == tmp_path / "s2" / "Voice-AI"


def test_zip_khong_co_exe_hoac_duong_dan_doc_hai_bi_huy(tmp_path):
    _zip(tmp_path / "c.zip", {"readme.txt": b"x"})
    with pytest.raises(RuntimeError):
        ui.extract_package(tmp_path / "c.zip", tmp_path / "s3", "Voice.exe")
    _zip(tmp_path / "d.zip", {"../evil.exe": b"x", "Voice.exe": b"x"})
    with pytest.raises(RuntimeError):
        ui.extract_package(tmp_path / "d.zip", tmp_path / "s4", "Voice.exe")
    assert not (tmp_path / "evil.exe").exists()


def test_script_thay_file_giu_du_lieu_va_co_khoi_phuc():
    bat = ui.build_swap_script(4242, Path("C:/App"), Path("C:/App/_update_staging/X"), "Voice.exe",
                               Path("C:/App/_update_staging"))
    assert "4242" in bat and "_internal.old" in bat and "/XD models gpu_venv addons" in bat
    assert "if errorlevel 8 goto restore" in bat and 'start "" "' in bat
    assert "WaitForExit(90000)" in bat and "tasklist" not in bat and "timeout" not in bat and "update-swap.log" in bat


def test_zip_tai_ve_thanh_cong_va_san_sang(monkeypatch, tmp_path):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Voice.exe", b"x")
        z.writestr("_internal/a.dll", b"y")
    data = buf.getvalue()
    monkeypatch.setattr(ui.sys, "executable", str(tmp_path / "Voice.exe"))
    st = _run(monkeypatch, tmp_path, data, hashlib.sha256(data).hexdigest(), url_name="Pack.zip")
    assert st["state"] == "ready" and st["kind"] == "zip"
