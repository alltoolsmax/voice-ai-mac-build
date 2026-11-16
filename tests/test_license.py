import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import _ed25519 as ed  # noqa: E402
from apps import license as lic  # noqa: E402
from apps import license_codec as codec  # noqa: E402

SEED = bytes(range(32))
HOUR = 3600


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEAI_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("VOICEAI_MACHINE_ID_RAW", "machine-A")
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", ed.public_key(SEED).hex())
    lic._licensed_cache.clear()
    lic.invalidate_cache()
    return tmp_path


def test_rfc8032_vector():
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert ed.public_key(seed).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    sig = ed.sign(seed, b"")
    assert sig.hex().startswith("e5564300c360ac729086e2cc806e828a")
    assert ed.verify(ed.public_key(seed), b"", sig)
    assert not ed.verify(ed.public_key(seed), b"x", sig)


def test_machine_id_format_and_stable():
    mid = lic.machine_id()
    assert mid.startswith("MH-") and len(mid) == 22
    assert lic.machine_id() == mid


def test_trial_starts_and_expires():
    t0 = 1_800_000_000
    s = lic.status(t0)
    assert s["state"] == "trial" and 3 * 86400 - 10 <= s["remaining_seconds"] <= 3 * 86400
    s = lic.status(t0 + 71 * HOUR)
    assert s["state"] == "trial" and 0 < s["remaining_seconds"] <= HOUR
    s = lic.status(t0 + 73 * HOUR)
    assert s["state"] == "expired"
    # hết hạn thì mãi hết hạn, dù đồng hồ về đúng giờ cũ
    assert lic.status(t0 + 74 * HOUR)["state"] == "expired"


def test_clock_rollback_detected():
    t0 = 1_800_000_000
    lic.status(t0)
    lic.status(t0 + 5 * HOUR)
    assert lic.status(t0 + HOUR)["state"] == "expired"


def test_tampered_state_expires(env):
    t0 = 1_800_000_000
    lic.status(t0)
    for f in env.rglob("trial.dat"):
        f.write_text("rac-roi.deadbeef")
    s = lic.status(t0 + 60)
    assert s["state"] == "expired" and s["reason"] == "tamper"


def test_one_store_deleted_is_restored(env):
    t0 = 1_800_000_000
    lic.status(t0)
    lic.status(t0 + 2 * HOUR)
    next(env.rglob("trial.dat")).unlink()
    s = lic.status(t0 + 3 * HOUR)
    assert s["state"] == "trial" and s["remaining_seconds"] <= 69 * HOUR


def test_state_copied_to_other_machine_is_invalid(env, monkeypatch):
    t0 = 1_800_000_000
    lic.status(t0)
    monkeypatch.setenv("VOICEAI_MACHINE_ID_RAW", "machine-B")
    assert lic.status(t0 + 60)["state"] == "expired"


def test_valid_key_activates_forever():
    key = codec.make_key(SEED, lic.machine_bytes())
    ok, _ = lic.activate(key)
    assert ok
    assert lic.status(1_800_000_000)["state"] == "licensed"
    assert lic.status(1_800_000_000 + 900 * 86400)["state"] == "licensed"
    lic._licensed_cache.clear()  # đọc lại từ đĩa
    assert lic.status(1_900_000_000)["state"] == "licensed"


def test_key_input_is_forgiving():
    key = codec.make_key(SEED, lic.machine_bytes())
    messy = "  " + key.lower().replace("-", " ") + "\n"
    assert lic.activate(messy)[0]


def test_key_for_other_machine_rejected(monkeypatch):
    other = codec.make_key(SEED, b"\x01" * 8)
    ok, msg = lic.activate(other)
    assert not ok and "máy khác" in msg


def test_wrong_signer_and_garbage_rejected():
    forged = codec.make_key(bytes(32), lic.machine_bytes())
    assert not lic.activate(forged)[0]
    assert not lic.activate("MH1-ABC")[0]
    assert not lic.activate("")[0]
    key = codec.make_key(SEED, lic.machine_bytes())
    flipped = key[:-3] + ("AAA" if key[-3:] != "AAA" else "BBB")
    assert not lic.activate(flipped)[0]


def test_middleware_blocks_when_expired_and_opens_with_key(monkeypatch):
    app = FastAPI()
    app.add_middleware(lic.LicenseMiddleware)
    app.include_router(lic.router)

    @app.get("/api/tts/generate")
    def gen():
        return {"ok": True}

    @app.get("/")
    def index():
        return {"page": True}

    c = TestClient(app)
    base = {"t": 1_800_000_000.0}
    real_status = lic.status
    monkeypatch.setattr(lic.time, "time", lambda: base["t"])
    assert c.get("/api/tts/generate").status_code == 200
    base["t"] += 73 * HOUR
    lic.invalidate_cache()
    r = c.get("/api/tts/generate")
    assert r.status_code == 402 and r.json()["license_required"] is True
    assert c.get("/").status_code == 200
    st = c.get("/api/license/status").json()
    assert st["state"] == "expired" and st["machine_id"] == lic.machine_id()
    assert c.post("/api/license/activate", json={"key": "sai"}).status_code == 400
    key = codec.make_key(SEED, lic.machine_bytes())
    r = c.post("/api/license/activate", json={"key": key})
    assert r.status_code == 200 and r.json()["state"] == "licensed"
    assert c.get("/api/tts/generate").status_code == 200
    assert real_status is lic.status


# ---------------------------------------------------------------- Gói có thời hạn

DAY = 86400
T0 = 1_800_000_000.0


def _key(kind, issued=None):
    import datetime

    return codec.make_key(SEED, lic.machine_bytes(), kind, issued or datetime.date.fromtimestamp(T0))


def test_timed_plan_activates_and_expires():
    ok, msg = lic.activate(_key(codec.TYPE_1M), T0)
    assert ok and "1 tháng" in msg
    s = lic.status(T0 + DAY)
    assert s["state"] == "licensed" and s["plan"] == "timed"
    assert 28 * DAY < s["remaining_seconds"] <= 29 * DAY
    assert lic.status(T0 + 29 * DAY)["state"] == "licensed"
    s = lic.status(T0 + 31 * DAY)
    assert s["state"] == "expired" and s["reason"] == "plan_expired"


@pytest.mark.parametrize("kind,days", [(codec.TYPE_1M, 30), (codec.TYPE_3M, 90), (codec.TYPE_6M, 180), (codec.TYPE_1Y, 365), (codec.TYPE_TRIAL7, 7), (codec.TYPE_EXP10, 10)])
def test_each_plan_length(kind, days):
    assert lic.activate(_key(kind), T0)[0]
    assert lic.status(T0 + (days - 1) * DAY)["state"] == "licensed"
    assert lic.status(T0 + (days + 1) * DAY)["state"] == "expired"


def test_renewal_stacks_on_remaining_time():
    lic.activate(_key(codec.TYPE_1M), T0)
    # còn ~20 ngày thì mua thêm 3 tháng: tổng ~110 ngày
    ok, msg = lic.activate(_key(codec.TYPE_3M), T0 + 10 * DAY)
    assert ok
    s = lic.status(T0 + 10 * DAY)
    assert 109 * DAY < s["remaining_seconds"] <= 110 * DAY


def test_renewal_after_expiry_counts_from_now():
    lic.activate(_key(codec.TYPE_1M), T0)
    later = T0 + 40 * DAY
    assert lic.status(later)["state"] == "expired"
    assert lic.activate(_key(codec.TYPE_1M, issued=__import__("datetime").date.fromtimestamp(later)), later)[0]
    s = lic.status(later)
    assert 29 * DAY < s["remaining_seconds"] <= 30 * DAY


def test_same_key_cannot_be_added_twice():
    k = _key(codec.TYPE_1M)
    assert lic.activate(k, T0)[0]
    ok, msg = lic.activate(k, T0 + DAY)
    assert not ok and "đã được kích hoạt" in msg
    assert lic.status(T0 + DAY)["remaining_seconds"] < 30 * DAY


def test_old_key_beyond_activation_window_rejected():
    import datetime

    old = _key(codec.TYPE_1M, issued=datetime.date.fromtimestamp(T0) - datetime.timedelta(days=45))
    ok, msg = lic.activate(old, T0)
    assert not ok and "quá hạn kích hoạt" in msg


def test_lifetime_blocks_timed_and_stays_forever():
    assert lic.activate(_key(codec.TYPE_LIFETIME), T0)[0]
    ok, msg = lic.activate(_key(codec.TYPE_1M), T0)
    assert not ok and "vĩnh viễn" in msg
    assert lic.status(T0 + 5000 * DAY)["state"] == "licensed"


def test_timed_plan_clock_rollback_and_tamper(env):
    lic.activate(_key(codec.TYPE_1M), T0)
    lic.status(T0 + 5 * DAY)
    assert lic.status(T0 + DAY)["reason"] == "clock"
    for f in env.rglob("entitlement.dat"):
        f.write_text("rac.roi")
    assert lic.status(T0 + 6 * DAY)["reason"] == "tamper"


def test_timed_key_for_other_machine_rejected():
    other = codec.make_key(SEED, b"\x09" * 8, codec.TYPE_3M)
    ok, msg = lic.activate(other, T0)
    assert not ok and "máy khác" in msg


def test_status_contact_has_two_links():
    c = lic.status(T0)["contact"]
    assert c["zalo"] == "https://zalo.me/0979007367" and c["zalo_label"] == "Mr Huỳnh"
    assert c["facebook"] == "https://facebook.com/mr.huynhxuyenson" and c["facebook_label"] == "Facebook"
    assert "telegram" not in c


def test_status_reports_plan_name():
    assert lic.activate(_key(codec.TYPE_6M), T0)[0]
    s = lic.status(T0 + DAY)
    assert s["state"] == "licensed" and s["plan_name"] == "6 tháng" and s["expires_at"] > T0
    assert lic.activate(_key(codec.TYPE_EXP10, issued=__import__("datetime").date.fromtimestamp(T0)), T0 + DAY)[0]
    assert lic.status(T0 + 2 * DAY)["plan_name"] == "Trải nghiệm 10 ngày"  # hiện loại gói kích hoạt gần nhất
