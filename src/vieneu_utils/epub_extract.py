"""
Trích văn bản từ sách điện tử .epub - chỉ dùng thư viện chuẩn (zipfile, ElementTree, html.parser).

.epub là file zip: ``META-INF/container.xml`` trỏ tới file OPF; OPF liệt kê các tệp XHTML theo
thứ tự đọc (spine). Mỗi tệp thường là một chương. Trả về danh sách chương (tiêu đề, nội dung);
mỗi đoạn văn một dòng, cách nhau một dòng trống - cùng quy ước với ``docx_extract``.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import unquote

MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_FILES = 3000

_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section"}
_HEADING = {"h1", "h2", "h3"}
_SKIP = {"script", "style", "head", "nav"}


class EpubError(ValueError):
    """File không phải .epub hợp lệ - thông báo tiếng Việt, hiển thị thẳng cho người dùng."""


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_heading = False
        self._heading_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
            if tag in _HEADING and not self.title:
                self._in_heading = True
                self._heading_buf = []

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")
            if self._in_heading and tag in _HEADING:
                self._in_heading = False
                self.title = " ".join("".join(self._heading_buf).split())

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._in_heading:
            self._heading_buf.append(data)


def _html_to_text(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8", errors="ignore")
    parser = _Text()
    parser.feed(text)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).split("\n")]
    paragraphs = [line for line in lines if line]
    return parser.title, "\n\n".join(paragraphs)


def _read(zf: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_MEMBER_BYTES:
        raise EpubError("File .epub có phần quá lớn, không đọc được.")
    return zf.read(info)


def extract_epub(content: bytes) -> list[dict]:
    """[{"title": str, "text": str}, ...] theo thứ tự đọc; bỏ chương không có chữ."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise EpubError("File này không phải .epub hợp lệ.") from exc
    if len(zf.namelist()) > MAX_FILES:
        raise EpubError("File .epub có quá nhiều phần, không đọc được.")
    container = _read(zf, "META-INF/container.xml")
    if container is None:
        raise EpubError("File này không phải .epub hợp lệ (thiếu container.xml).")
    try:
        root = ET.fromstring(container)
        rootfile = next(e for e in root.iter() if e.tag.endswith("rootfile"))
        opf_path = unquote(rootfile.attrib["full-path"])
        opf = ET.fromstring(_read(zf, opf_path) or b"")
    except (ET.ParseError, StopIteration, KeyError) as exc:
        raise EpubError("Không đọc được mục lục của file .epub.") from exc

    base = posixpath.dirname(opf_path)
    manifest: dict[str, str] = {}
    for item in opf.iter():
        if item.tag.endswith("}item") or item.tag == "item":
            media = item.attrib.get("media-type", "")
            if "html" in media:
                manifest[item.attrib.get("id", "")] = unquote(item.attrib.get("href", ""))
    order = [ref.attrib.get("idref", "") for ref in opf.iter() if ref.tag.endswith("itemref")]

    chapters: list[dict] = []
    for idref in order:
        href = manifest.get(idref)
        if not href:
            continue
        raw = _read(zf, posixpath.normpath(posixpath.join(base, href)))
        if raw is None:
            continue
        title, text = _html_to_text(raw)
        if len(re.sub(r"\s+", "", text)) < 20:  # trang bìa, trang trắng
            continue
        chapters.append({"title": title or f"Phần {len(chapters) + 1}", "text": text})
    if not chapters:
        raise EpubError("File .epub không có chữ để đọc.")
    return chapters
