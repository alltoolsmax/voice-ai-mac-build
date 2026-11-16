import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from vieneu_utils.chapters import split_chapters, to_batch_script
from vieneu_utils.epub_extract import EpubError, extract_epub


def make_epub(chapters, with_cover=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        items, refs = "", ""
        names = (["cover"] if with_cover else []) + [f"c{i}" for i in range(len(chapters))]
        for n in names:
            items += f'<item id="{n}" href="{n}.xhtml" media-type="application/xhtml+xml"/>'
            refs += f'<itemref idref="{n}"/>'
        z.writestr("OEBPS/content.opf",
                   '<package xmlns="http://www.idpf.org/2007/opf"><manifest>' + items +
                   "</manifest><spine>" + refs + "</spine></package>")
        if with_cover:
            z.writestr("OEBPS/cover.xhtml", "<html><body><img src='x.png'/></body></html>")
        for i, (title, paras) in enumerate(chapters):
            body = f"<h1>{title}</h1>" + "".join(f"<p>{p}</p>" for p in paras)
            z.writestr(f"OEBPS/c{i}.xhtml", f"<html><head><title>x</title></head><body>{body}</body></html>")
    return buf.getvalue()


def test_epub_theo_thu_tu_doc_va_bo_trang_bia():
    data = make_epub([("Chương 1", ["Xin chào các bạn, đây là đoạn đầu tiên.", "Đoạn hai &amp; hết."]),
                      ("Chương 2", ["Nội dung chương hai khá là dài để qua ngưỡng."])])
    ch = extract_epub(data)
    assert [c["title"] for c in ch] == ["Chương 1", "Chương 2"]
    assert "Đoạn hai & hết." in ch[0]["text"]
    assert "\n\n" in ch[0]["text"]


def test_epub_hong():
    with pytest.raises(EpubError):
        extract_epub(b"khong phai zip")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("a.txt", "x")
    with pytest.raises(EpubError):
        extract_epub(empty.getvalue())


def test_tach_chuong_theo_tieu_de():
    text = ("Lời tựa của tác giả, viết khá dài để vượt ngưỡng tối thiểu.\n"
            "Chương 1: Khởi đầu\nNội dung chương một, đủ dài để không bị gộp vào mục khác.\n"
            "CHAPTER 2\nNội dung chương hai, cũng đủ dài để không bị gộp vào mục khác.\n")
    ch = split_chapters(text)
    assert [c["title"] for c in ch] == ["Mở đầu", "Chương 1: Khởi đầu", "CHAPTER 2"]
    script = to_batch_script(ch)
    assert script.startswith("[P1]\n") and "[P3]\nCHAPTER 2" in script


def test_khong_co_tieu_de_thi_mot_muc():
    assert split_chapters("Chỉ có một đoạn văn thường.") == [{"title": "Toàn bộ", "text": "Chỉ có một đoạn văn thường."}]
    assert split_chapters("   ") == []


def test_endpoint_epub_va_chapters():
    from apps import web_stream
    c = TestClient(web_stream.app)
    data = make_epub([("Chương 1", ["Đoạn văn đủ dài để được giữ lại trong chương một."]),
                      ("Chương 2", ["Đoạn văn đủ dài để được giữ lại trong chương hai."])])
    r = c.post("/api/pdf/extract", files={"file": ("sach.epub", data)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["page_count"] == 2 and len(body["chapters"]) == 2
    r = c.post("/api/text/chapters", json={"text": body["text"]})
    assert r.status_code == 200 and r.json()["script"].count("[P") == 2
    assert c.post("/api/pdf/extract", files={"file": ("x.epub", b"zzz")}).status_code == 400
