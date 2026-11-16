import pytest

from apps import announcement as an


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def _srv(monkeypatch, body):
    monkeypatch.setattr(an, "_fetch", lambda: an.clean(body))


def test_tat_hoac_thieu_id_thi_khong_hien(monkeypatch):
    _srv(monkeypatch, {"enabled": False})
    assert an.current(1000) is None
    _srv(monkeypatch, {"enabled": True})
    assert an.current(5000) is None


def test_hien_va_dong_roi_khong_hien_lai(monkeypatch):
    _srv(monkeypatch, {"enabled": True, "id": "7", "title": "T", "body": "B", "button_text": "Xem",
                       "button_url": "https://zalo.me/1", "badge": "-20%", "secondary_text": "Để sau"})
    a = an.current(1000)
    assert a and a["title"] == "T" and a["badge"] == "-20%" and a["button_url"] == "https://zalo.me/1" and a["secondary_text"] == "Để sau"
    an.dismiss_announcement(an.DismissBody(id="7"))
    assert an.current(1001) is None
    _srv(monkeypatch, {"enabled": True, "id": "8", "title": "Mới"})
    assert an.current(1000 + an.CHECK_INTERVAL_SECONDS + 5)["id"] == "8"  # id mới thì hiện lại


def test_het_han_link_la_va_doi_tuong_la_bi_loai(monkeypatch):
    _srv(monkeypatch, {"enabled": True, "id": "1", "title": "x", "button_url": "javascript:alert(1)",
                       "expires_at": 500})
    assert an.current(1000) is None  # hết hạn
    _srv(monkeypatch, {"enabled": True, "id": "2", "title": "x", "button_url": "http://a.b", "secondary_text": ""})
    a = an.current(1000 + an.CHECK_INTERVAL_SECONDS + 5)
    assert a["button_url"] == "" and a["secondary_text"] == ""  # chữ nút phụ rỗng = ẩn nút


def test_mat_mang_dung_ban_da_luu(monkeypatch):
    _srv(monkeypatch, {"enabled": True, "id": "3", "title": "luu"})
    assert an.current(1000)["title"] == "luu"

    def boom():
        raise OSError("offline")
    monkeypatch.setattr(an, "_fetch", boom)
    assert an.current(1000 + an.CHECK_INTERVAL_SECONDS + 5)["title"] == "luu"


def test_duong_dan_mo_khi_chua_kich_hoat():
    from apps import license as lic
    assert not lic._is_gated("/api/app/announcement")
    assert not lic._is_gated("/api/app/announcement/dismiss")
