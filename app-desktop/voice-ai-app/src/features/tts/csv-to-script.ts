// Chuyen file CSV (xuat tu Excel) thanh kich ban "Tao hang loat": moi dong mot muc [P1], [P2]...
//
// Cot noi dung: cot co tieu de "Nội dung" / "noi dung" / "text" / "content"; khong co tieu de
// thi lay cot dau tien. Dong dau duoc coi la tieu de neu khop mot ten tren.

const CONTENT_HEADERS = new Set([
  "nội dung",
  "noi dung",
  "text",
  "content",
  "văn bản",
  "van ban",
]);
const NEWLINES = /\r\n?/g;

/** Tach CSV: dau phay hoac cham phay (Excel Viet Nam), ho tro "..." co dau phay va xuong dong. */
export function parseCsv(input: string): string[][] {
  const text = input.replace(/^﻿/, "").replace(NEWLINES, "\n");
  const firstLine = text.split("\n", 1)[0] ?? "";
  const sep =
    firstLine.split(";").length > firstLine.split(",").length ? ";" : ",";
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === sep) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

export interface CsvScript {
  items: number;
  script: string;
}

export function csvToScript(input: string): CsvScript {
  const rows = parseCsv(input);
  if (rows.length === 0) {
    return { items: 0, script: "" };
  }
  let col = 0;
  let start = 0;
  const header = rows[0].map((c) => c.trim().toLowerCase());
  const found = header.findIndex((h) => CONTENT_HEADERS.has(h));
  if (found >= 0) {
    col = found;
    start = 1;
  }
  const parts: string[] = [];
  for (const r of rows.slice(start)) {
    const content = (r[col] ?? "").trim();
    if (content) {
      parts.push(`[P${parts.length + 1}]\n${content}`);
    }
  }
  return { items: parts.length, script: parts.join("\n\n") };
}
