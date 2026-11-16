import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Download,
  FileArchive,
  Loader2,
  Play,
  Square,
  Upload,
} from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { extractPdfText, splitChapters, synthesizeSpeech } from "../api";
import { downloadBlobAsFile } from "../audio-engine";
import type { VoiceOption } from "../types";
import { groupVoices, voiceOptionLabel } from "../voice-label";
import { createZip } from "../zip";

type Format = "mp3" | "wav";
type Status = "idle" | "running" | "done" | "error";

interface Chapter {
  blob?: Blob;
  chars: number;
  duration?: number;
  error?: string;
  status: Status;
  text: string;
  title: string;
  url?: string;
  voiceId: string; // "" = giọng mặc định
}

interface AudiobookTabProps {
  apiUrl: string;
  defaultVoiceId: string;
  voices: VoiceOption[];
}

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const safe = (s: string) =>
  s
    .replace(/[\\/:*?"<>|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
const pad = (n: number, w = 2) => String(n).padStart(w, "0");

/** Ghép nhiều WAV PCM cùng định dạng thành một file (giữ header của file đầu). */
async function concatWav(blobs: Blob[]): Promise<Blob> {
  const bufs = await Promise.all(blobs.map((b) => b.arrayBuffer()));
  const pcm: Uint8Array[] = [];
  let header: Uint8Array | null = null;
  for (const buf of bufs) {
    const v = new DataView(buf);
    let pos = 12;
    let dataStart = -1;
    let dataLen = 0;
    while (pos + 8 <= buf.byteLength) {
      const id = String.fromCharCode(
        v.getUint8(pos),
        v.getUint8(pos + 1),
        v.getUint8(pos + 2),
        v.getUint8(pos + 3)
      );
      const len = v.getUint32(pos + 4, true);
      if (id === "data") {
        dataStart = pos + 8;
        dataLen = Math.min(len, buf.byteLength - dataStart);
        break;
      }
      pos += 8 + len + (len % 2);
    }
    if (dataStart < 0) {
      throw new Error("File WAV không hợp lệ, không ghép được.");
    }
    if (!header) {
      header = new Uint8Array(buf.slice(0, dataStart));
    }
    pcm.push(new Uint8Array(buf, dataStart, dataLen));
  }
  if (!header) {
    throw new Error("Chưa có file nào để ghép.");
  }
  const total = pcm.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(header.length + total);
  out.set(header, 0);
  let off = header.length;
  for (const p of pcm) {
    out.set(p, off);
    off += p.length;
  }
  const dv = new DataView(out.buffer);
  dv.setUint32(4, out.length - 8, true);
  dv.setUint32(header.length - 4, total, true);
  return new Blob([out], { type: "audio/wav" });
}

const STATUS_LABEL: Record<Status, string> = {
  done: "Đã xong",
  error: "Lỗi",
  idle: "Chờ",
  running: "Đang đọc...",
};

export const AudiobookTab: React.FC<AudiobookTabProps> = ({
  apiUrl,
  defaultVoiceId,
  voices,
}) => {
  const [bookName, setBookName] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [voiceId, setVoiceId] = useState(defaultVoiceId);
  const [format, setFormat] = useState<Format>("mp3");
  const [perChapter, setPerChapter] = useState(true);
  const [merged, setMerged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const urlsRef = useRef<string[]>([]);

  useEffect(() => {
    if (!voiceId && defaultVoiceId) {
      setVoiceId(defaultVoiceId);
    }
  }, [defaultVoiceId, voiceId]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      for (const u of urlsRef.current) {
        URL.revokeObjectURL(u);
      }
    },
    []
  );

  const loadBook = async (file: File) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await extractPdfText(apiUrl, file, file.name);
      const split = await splitChapters(apiUrl, res.text);
      const parts = split.script
        .split(/(?:^|\n\n)\[P\d+\]\n/)
        .filter((p) => p.trim().length > 0);
      const next: Chapter[] = split.chapters.map((c, i) => ({
        chars: c.chars,
        status: "idle",
        text: parts[i] ?? "",
        title: c.title || `Chương ${i + 1}`,
        voiceId: "",
      }));
      if (next.length === 0 || next.every((c) => !c.text)) {
        throw new Error("Không tìm thấy nội dung để đọc trong file này.");
      }
      for (const u of urlsRef.current) {
        URL.revokeObjectURL(u);
      }
      urlsRef.current = [];
      setBookName(file.name.replace(/\.[^.]+$/, ""));
      setChapters(next);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const patch = (i: number, p: Partial<Chapter>) =>
    setChapters((cs) => cs.map((c, k) => (k === i ? { ...c, ...p } : c)));

  const start = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError(null);
    setNotice(null);
    for (let i = 0; i < chapters.length; i++) {
      if (controller.signal.aborted) {
        break;
      }
      const ch = chapters[i];
      if (ch.status === "done") {
        continue;
      }
      patch(i, { error: undefined, status: "running" });
      try {
        const res = await synthesizeSpeech(
          apiUrl,
          { format, text: ch.text, voiceId: ch.voiceId || voiceId },
          controller.signal
        );
        const url = URL.createObjectURL(res.blob);
        urlsRef.current.push(url);
        patch(i, {
          blob: res.blob,
          duration: res.durationSeconds,
          status: "done",
          url,
        });
      } catch (e) {
        if (controller.signal.aborted) {
          patch(i, { status: "idle" });
          break;
        }
        patch(i, { error: errorText(e), status: "error" });
      }
    }
    setRunning(false);
    abortRef.current = null;
  };

  const stop = () => abortRef.current?.abort();

  const done = chapters.filter((c) => c.status === "done");
  const doneCount = done.length;
  const total = chapters.length;
  const percent = total ? Math.round((doneCount / total) * 100) : 0;
  const totalSeconds = done.reduce((n, c) => n + (c.duration ?? 0), 0);
  const fileName = (i: number) =>
    `${pad(i + 1, 3)} - ${safe(chapters[i].title) || `Chương ${i + 1}`}.${format}`;

  const exportAll = async () => {
    setError(null);
    setNotice(null);
    try {
      const files: { data: Uint8Array; name: string }[] = [];
      if (perChapter) {
        for (let i = 0; i < chapters.length; i++) {
          const b = chapters[i].blob;
          if (chapters[i].status === "done" && b) {
            files.push({
              data: new Uint8Array(await b.arrayBuffer()),
              name: fileName(i),
            });
          }
        }
      }
      if (merged) {
        const blobs = chapters.flatMap((c) =>
          c.status === "done" && c.blob ? [c.blob] : []
        );
        const mergedBlob =
          format === "wav"
            ? await concatWav(blobs)
            : new Blob(blobs, { type: "audio/mpeg" });
        files.push({
          data: new Uint8Array(await mergedBlob.arrayBuffer()),
          name: `${safe(bookName) || "sach-noi"} (toan bo).${format}`,
        });
      }
      if (files.length === 0) {
        setError(
          "Hãy tick ít nhất một kiểu xuất và tạo xong ít nhất một chương."
        );
        return;
      }
      if (files.length === 1) {
        const f = files[0];
        const ok = await downloadBlobAsFile(
          new Blob([f.data as BlobPart], {
            type: format === "wav" ? "audio/wav" : "audio/mpeg",
          }),
          f.name
        );
        if (ok) {
          setNotice(`Đã lưu ${f.name}.`);
        }
        return;
      }
      const ok = await downloadBlobAsFile(
        createZip(files),
        `${safe(bookName) || "sach-noi"}.zip`
      );
      if (ok) {
        setNotice(
          `Đã lưu file zip gồm ${files.length} file ${format.toUpperCase()}.`
        );
      }
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <div className="studio-tab-grid studio-document-layout fade-in-50 animate-in duration-300">
      <div className="studio-span-5 flex flex-col gap-4">
        <div className="studio-tab-card doc-card">
          <div className="doc-card-head">
            <h3>Sách nói</h3>
            <p>Biến sách thành file audio theo từng chương.</p>
          </div>
          <div className="doc-dropzone" data-busy={busy || undefined}>
            <input
              accept=".pdf,.docx,.doc,.epub,.txt"
              aria-label="Chọn sách"
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              disabled={busy || running}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  loadBook(f);
                }
                e.target.value = "";
              }}
              type="file"
            />
            <span aria-hidden="true" className="doc-dropzone-icon">
              {busy ? (
                <Loader2 className="animate-spin" size={26} />
              ) : (
                <Upload size={26} />
              )}
            </span>
            <p className="doc-dropzone-title">
              {busy ? "Đang đọc sách..." : "Bấm để chọn sách"}
            </p>
            <div className="doc-formats">
              {["PDF", "DOCX", "EPUB", "TXT"].map((f) => (
                <span key={f}>{f}</span>
              ))}
            </div>
          </div>

          {chapters.length > 0 && (
            <div className="doc-file">
              <BookOpen aria-hidden="true" size={20} />
              <div className="min-w-0">
                <p className="truncate font-semibold">{bookName}</p>
                <p className="text-muted-foreground">
                  {total} chương ·{" "}
                  {chapters
                    .reduce((n, c) => n + c.chars, 0)
                    .toLocaleString("vi-VN")}{" "}
                  ký tự
                </p>
              </div>
            </div>
          )}

          <label className="space-y-1 text-xs">
            <span className="font-semibold text-foreground/90">
              Giọng mặc định
            </span>
            <select
              className="w-full rounded-lg border border-border/80 bg-background px-2.5 py-1.5 outline-none focus:border-brand-500"
              disabled={running}
              onChange={(e) => setVoiceId(e.target.value)}
              value={voiceId}
            >
              {groupVoices(voices).map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {voiceOptionLabel(v)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <div className="space-y-1 text-xs">
            <span className="font-semibold text-foreground/90">
              Định dạng xuất
            </span>
            <div className="flex gap-2">
              {(["mp3", "wav"] as Format[]).map((f) => (
                <button
                  aria-pressed={format === f}
                  className={`rounded-lg border px-4 py-1.5 font-semibold ${
                    format === f
                      ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-300"
                      : "border-border/80 bg-background"
                  }`}
                  disabled={running || doneCount > 0}
                  key={f}
                  onClick={() => setFormat(f)}
                  type="button"
                >
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
            {doneCount > 0 && (
              <p className="text-muted-foreground">
                Đã có chương tạo xong nên không đổi định dạng được. Muốn đổi,
                hãy chọn lại sách.
              </p>
            )}
          </div>

          <div className="space-y-1.5 text-xs">
            <span className="font-semibold text-foreground/90">Kiểu xuất</span>
            <label className="flex items-center gap-2">
              <input
                checked={perChapter}
                onChange={(e) => setPerChapter(e.target.checked)}
                type="checkbox"
              />
              Mỗi chương một file
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={merged}
                onChange={(e) => setMerged(e.target.checked)}
                type="checkbox"
              />
              Thêm một file ghép toàn bộ
            </label>
          </div>

          {error && (
            <div className="doc-error" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {notice && (
            <div className="doc-notice" role="status">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{notice}</span>
            </div>
          )}
        </div>
      </div>

      <div className="studio-span-7 flex flex-col">
        <div className="studio-tab-card doc-editor">
          <div className="doc-editor-head">
            <h3>
              <BookOpen size={18} />
              Danh sách chương
            </h3>
          </div>

          {chapters.length === 0 ? (
            <div
              className="doc-empty"
              style={{ position: "static", padding: "48px 0" }}
            >
              <BookOpen size={34} />
              <p>Chưa có sách</p>
              <span>
                1. Chọn file sách bên trái. 2. Chọn giọng đọc. 3. Bấm "Bắt đầu
                tạo sách nói".
              </span>
            </div>
          ) : (
            <div className="max-h-[52vh] overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="p-2">#</th>
                    <th className="p-2">Chương</th>
                    <th className="p-2">Giọng đọc</th>
                    <th className="p-2">Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {chapters.map((c, i) => (
                    <tr
                      className="border-border/60 border-t"
                      key={`${i}-${c.title}`}
                    >
                      <td className="p-2 tabular-nums">{i + 1}</td>
                      <td className="p-2">
                        <div className="font-semibold">{c.title}</div>
                        <div className="text-muted-foreground">
                          {c.chars.toLocaleString("vi-VN")} ký tự
                        </div>
                      </td>
                      <td className="p-2">
                        <select
                          aria-label={`Giọng cho ${c.title}`}
                          className="max-w-[180px] rounded-lg border border-border/80 bg-background px-2 py-1"
                          disabled={running || c.status === "done"}
                          onChange={(e) =>
                            patch(i, { voiceId: e.target.value })
                          }
                          value={c.voiceId}
                        >
                          <option value="">Giọng mặc định</option>
                          {groupVoices(voices).map((g) => (
                            <optgroup key={g.label} label={g.label}>
                              {g.voices.map((v) => (
                                <option key={v.id} value={v.id}>
                                  {voiceOptionLabel(v)}
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                      </td>
                      <td className="p-2">
                        {c.status === "done" && c.url ? (
                          <audio
                            controls
                            preload="none"
                            src={c.url}
                            style={{ height: 30, width: 190 }}
                          >
                            <track kind="captions" />
                          </audio>
                        ) : (
                          <span title={c.error}>
                            {STATUS_LABEL[c.status]}
                            {c.status === "error" && c.error
                              ? `: ${c.error.slice(0, 60)}`
                              : ""}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {chapters.length > 0 && (
            <div className="doc-footer">
              <div className="min-w-0 flex-1 text-xs">
                <div className="mb-1 flex justify-between text-muted-foreground">
                  <span>
                    Đã xong {doneCount}/{total} chương
                    {totalSeconds > 0
                      ? ` · ${Math.round(totalSeconds / 60)} phút audio`
                      : ""}
                  </span>
                  <span>{percent}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-brand-500 transition-all"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
              <div className="doc-send">
                {running ? (
                  <button
                    className="doc-send-secondary"
                    onClick={stop}
                    type="button"
                  >
                    <Square size={16} />
                    Tạm dừng
                  </button>
                ) : (
                  <button
                    className="studio-primary doc-send-primary"
                    disabled={doneCount === total}
                    onClick={start}
                    type="button"
                  >
                    <Play size={16} />
                    {doneCount > 0 ? "Tiếp tục tạo" : "Bắt đầu tạo sách nói"}
                  </button>
                )}
                <button
                  className="doc-send-secondary"
                  disabled={doneCount === 0 || running}
                  onClick={exportAll}
                  type="button"
                >
                  {perChapter && merged ? (
                    <FileArchive size={16} />
                  ) : (
                    <Download size={16} />
                  )}
                  Tải về
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
