"""Tách văn bản dài thành các chương theo dòng tiêu đề ("Chương 1", "Chapter 2", "Hồi 3"...)."""

from __future__ import annotations

import re

_HEADING = re.compile(
    r"^\s*(chương|chuong|chapter|hồi|hoi|phần|phan|tập|tap)\s+([0-9]{1,4}|[ivxlc]{1,8}|[a-zà-ỹ]{2,12})\b[^\n]{0,80}$",
    re.IGNORECASE,
)
MIN_CHAPTER_CHARS = 40


def split_chapters(text: str) -> list[dict]:
    """[{"title", "text"}]. Không tìm thấy tiêu đề nào thì trả một mục chứa cả văn bản."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chapters: list[dict] = []
    title = "Mở đầu"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            chapters.append({"title": title, "text": body})

    found = False
    for line in lines:
        if _HEADING.match(line) and len(line.strip()) <= 90:
            flush()
            buf = []
            found = True
            title = " ".join(line.split())
            buf.append(line.strip())
        else:
            buf.append(line)
    flush()
    if not found:
        body = text.strip()
        return [{"title": "Toàn bộ", "text": body}] if body else []
    # Gộp mục quá ngắn (tiêu đề đứng một mình) vào mục sau nó.
    merged: list[dict] = []
    carry = ""
    for ch in chapters:
        t = (carry + "\n" + ch["text"]).strip() if carry else ch["text"]
        if len(t) < MIN_CHAPTER_CHARS and ch is not chapters[-1]:
            carry = t
            continue
        merged.append({"title": ch["title"], "text": t})
        carry = ""
    return merged


def to_batch_script(chapters: list[dict]) -> str:
    """Kịch bản cho tab Tạo hàng loạt: [P1] chương 1, [P2] chương 2..."""
    return "\n\n".join(f"[P{i}]\n{c['text']}" for i, c in enumerate(chapters, 1))
