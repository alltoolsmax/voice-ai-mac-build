import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Copy,
  FileCheck,
  FileText,
  ListOrdered,
  Loader2,
  MessagesSquare,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { extractPdfText, parseSrt, type SrtCue, splitChapters } from "../api";
import { LanguageSelect } from "../model-caps";
import { readTextFile } from "../read-text-file";
import { cleanExtractedText, describeCleanup } from "../text-cleanup";
import type { HistoryEntry, PdfExtractionResult, VoiceOption } from "../types";
import { SrtDubbing } from "./SrtDubbing";

const FORMATS = ["PDF", "DOCX", "EPUB", "TXT"];
const DUB_FORMATS = ["SRT", "VTT"];

interface DropzoneProps {
  accept: string;
  busy: boolean;
  formats: string[];
  onFile: (file: File) => void;
}

/** Vùng thả file: cả khung là nút chọn file (input phủ kín, trong suốt). */
function DocDropzone({ accept, busy, formats, onFile }: DropzoneProps) {
  return (
    <div
      className="doc-dropzone"
      data-busy={busy || undefined}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files?.[0];
        if (file) {
          onFile(file);
        }
      }}
    >
      <input
        accept={accept}
        aria-label="Chọn file"
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            onFile(file);
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
        {busy ? "Đang đọc tài liệu..." : "Kéo thả file vào đây"}
      </p>
      {!busy && (
        <p className="doc-dropzone-hint">
          hoặc <span className="doc-dropzone-link">bấm để chọn file</span>
        </p>
      )}
      <div className="doc-formats">
        {formats.map((f) => (
          <span key={f}>{f}</span>
        ))}
      </div>
    </div>
  );
}

const STEPS = [
  ["Chọn file", "PDF, Word, EPUB hoặc TXT."],
  ["Kiểm tra nội dung", "Sửa chữ, bấm Làm sạch nếu cần."],
  ["Tạo giọng đọc", "Gửi sang Đọc văn bản hoặc Hội thoại."],
];

function DocGuide() {
  return (
    <div className="studio-tab-card doc-guide">
      <h4>Cách dùng</h4>
      <ol>
        {STEPS.map(([title, desc], i) => (
          <li key={title}>
            <span className="doc-step">{i + 1}</span>
            <span>
              <strong>{title}</strong>
              {desc}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface PdfReaderTabProps {
  apiUrl: string;
  defaultVoiceId: string;
  /** "read" = Đọc file (tài liệu); "dub" = Lồng tiếng (phụ đề SRT/VTT). */
  mode?: "read" | "dub";
  onAddHistory: (entry: HistoryEntry) => void;
  onSendToBatch: (script: string) => void;
  onSendToConversation: (text: string) => void;
  onSendToTts: (text: string) => void;
  voices: VoiceOption[];
}

interface SrtFile {
  cues: SrtCue[];
  durationSeconds: number;
  name: string;
  text: string;
}

const SUBTITLE_FILE = /\.(srt|vtt)$/i;

export const PdfReaderTab: React.FC<PdfReaderTabProps> = ({
  apiUrl,
  mode = "read",
  defaultVoiceId,
  onAddHistory,
  onSendToTts,
  onSendToBatch,
  onSendToConversation,
  voices,
}) => {
  const [srtFile, setSrtFile] = useState<SrtFile | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [extractResult, setExtractResult] =
    useState<PdfExtractionResult | null>(null);
  const [cleanedText, setCleanedText] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copySuccess, setCopySuccess] = useState<boolean>(false);
  const [cleanNotice, setCleanNotice] = useState<string | null>(null);

  // Handle File selection
  const handleFileSelect = async (file: File) => {
    setIsExtracting(true);
    setErrorMessage(null);
    setCleanNotice(null);

    const isSubtitle = SUBTITLE_FILE.test(file.name);
    if (mode === "read" && isSubtitle) {
      setErrorMessage(
        "File phụ đề (SRT/VTT) dùng ở mục Lồng tiếng. Hãy chuyển sang mục đó."
      );
      setIsExtracting(false);
      return;
    }
    if (mode === "dub" && !isSubtitle) {
      setErrorMessage(
        "Lồng tiếng cần file phụ đề .srt hoặc .vtt. Tài liệu PDF/Word/EPUB hãy dùng mục Đọc file."
      );
      setIsExtracting(false);
      return;
    }
    // File phu de: chuyen sang che do long tieng theo moc thoi gian.
    if (isSubtitle) {
      try {
        const text = await readTextFile(file);
        const parsed = await parseSrt(apiUrl, text);
        setSrtFile({ ...parsed, name: file.name, text });
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Không đọc được file phụ đề."
        );
      } finally {
        setIsExtracting(false);
      }
      return;
    }

    setSelectedFile(file);
    setExtractResult(null);
    try {
      const res = await extractPdfText(apiUrl, file, file.name);
      setExtractResult(res);
      setCleanedText(res.text);
    } catch (err: any) {
      setErrorMessage(
        err.message || "Không thể trích xuất văn bản từ tài liệu này."
      );
    } finally {
      setIsExtracting(false);
    }
  };

  // Lam sach: bo dong trong, gach dau dong, cho trong de dien; noi dong bi ngat
  // giua cau. Giu nguyen cong thuc - xem text-cleanup.ts.
  const handleCleanFormatting = () => {
    if (!cleanedText) {
      return;
    }
    const { text, stats } = cleanExtractedText(cleanedText);
    setCleanedText(text);
    setCleanNotice(
      describeCleanup(stats) || "Văn bản đã sạch, không có gì cần sửa."
    );
  };

  // Tach chuong -> kich ban [P1], [P2]... sang "Tao hang loat" (moi chuong mot file audio).
  const handleSendToBatch = async () => {
    setErrorMessage(null);
    try {
      const { script, chapters } = await splitChapters(apiUrl, cleanedText);
      onSendToBatch(script);
      setCleanNotice(
        `Đã tách ${chapters.length} phần và gửi sang Tạo hàng loạt.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Không tách được chương."
      );
    }
  };

  // Copy text
  const handleCopy = () => {
    if (cleanedText) {
      navigator.clipboard.writeText(cleanedText);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  const wordCount = cleanedText.trim()
    ? cleanedText.trim().split(/\s+/).length
    : 0;

  if (srtFile) {
    return (
      <SrtDubbing
        apiUrl={apiUrl}
        cues={srtFile.cues}
        defaultVoiceId={defaultVoiceId}
        durationSeconds={srtFile.durationSeconds}
        fileName={srtFile.name}
        onAddHistory={onAddHistory}
        onClose={() => setSrtFile(null)}
        srt={srtFile.text}
        voices={voices}
      />
    );
  }

  const hasText = Boolean(cleanedText);

  if (mode === "dub") {
    return (
      <div className="studio-tab-grid studio-document-layout fade-in-50 animate-in duration-300">
        <div className="studio-span-5 flex flex-col gap-4">
          <div className="studio-tab-card doc-card">
            <div className="doc-card-head">
              <h3>Lồng tiếng</h3>
              <p>Đọc phụ đề thành giọng nói, đúng mốc thời gian từng câu.</p>
            </div>
            <DocDropzone
              accept=".srt,.vtt"
              busy={isExtracting}
              formats={DUB_FORMATS}
              onFile={handleFileSelect}
            />
            {errorMessage && (
              <div className="doc-error" role="alert">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}
          </div>
        </div>
        <div className="studio-span-7 flex flex-col">
          <div className="studio-tab-card doc-guide">
            <h4>Cách lồng tiếng</h4>
            <ol>
              {[
                [
                  "Chọn file phụ đề",
                  "File .srt hoặc .vtt (xuất từ CapCut, Premiere, YouTube...).",
                ],
                [
                  "Chọn giọng và tốc độ",
                  "Câu dài sẽ được đọc nhanh hơn cho vừa mốc thời gian.",
                ],
                [
                  "Tạo và tải về",
                  "Nhận file audio khớp thời gian và phụ đề đã căn chỉnh. Ghép vào video bằng phần mềm dựng của bạn.",
                ],
              ].map(([title, desc], i) => (
                <li key={title}>
                  <span className="doc-step">{i + 1}</span>
                  <span>
                    <strong>{title}</strong>
                    {desc}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="studio-tab-grid studio-document-layout fade-in-50 animate-in duration-300">
      {/* Cột trái: chọn file, thông tin file, hướng dẫn */}
      <div className="studio-span-5 flex flex-col gap-4">
        <div className="studio-tab-card doc-card">
          <div className="doc-card-head">
            <h3>Đọc file</h3>
            <p>Lấy chữ từ tài liệu rồi đọc thành giọng nói.</p>
          </div>
          <DocDropzone
            accept=".pdf,.docx,.doc,.epub,.txt"
            busy={isExtracting}
            formats={FORMATS}
            onFile={handleFileSelect}
          />

          <LanguageSelect disabled={isExtracting} />

          {extractResult && selectedFile && (
            <div className="doc-file">
              <FileCheck aria-hidden="true" size={20} />
              <div className="min-w-0">
                <p className="truncate font-semibold">{selectedFile.name}</p>
                <p className="text-muted-foreground">
                  {extractResult.page_count
                    ? `${extractResult.page_count} trang · `
                    : ""}
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>
          )}

          {errorMessage && (
            <div className="doc-error" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}
        </div>
        {!hasText && <DocGuide />}
      </div>

      {/* Cột phải: nội dung trích xuất, sửa được trước khi đọc */}
      <div className="studio-span-7 flex flex-col">
        <div className="studio-tab-card doc-editor">
          <div className="doc-editor-head">
            <h3>
              <FileText size={18} />
              Nội dung
            </h3>
            <div className="doc-editor-tools">
              <button
                disabled={!hasText}
                onClick={handleCleanFormatting}
                title="Bỏ dòng trống, gạch đầu dòng, chỗ trống để điền (....., ___); nối dòng bị ngắt giữa câu. Giữ nguyên công thức như 1 + 1."
                type="button"
              >
                <Sparkles size={15} />
                Làm sạch
              </button>
              <button
                disabled={!hasText}
                onClick={handleCopy}
                title="Sao chép toàn bộ"
                type="button"
              >
                <Copy size={15} />
                {copySuccess ? "Đã chép!" : "Sao chép"}
              </button>
              <button
                aria-label="Xoá nội dung"
                className="doc-danger"
                disabled={!hasText}
                onClick={() => {
                  setCleanedText("");
                  setCleanNotice(null);
                }}
                title="Xoá nội dung"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>

          {cleanNotice && (
            <div aria-live="polite" className="doc-notice" role="status">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{cleanNotice}</span>
            </div>
          )}

          <div className="doc-textarea-wrap">
            <textarea
              aria-label="Nội dung trích xuất"
              onChange={(e) => {
                setCleanedText(e.target.value);
                setCleanNotice(null);
              }}
              value={cleanedText}
            />
            {!hasText && (
              <div aria-hidden="true" className="doc-empty">
                <FileText size={34} />
                <p>Chưa có nội dung</p>
                <span>Chọn file bên trái, hoặc dán văn bản vào đây.</span>
              </div>
            )}
          </div>

          <div className="doc-footer">
            <span className="doc-stats">
              {cleanedText.length.toLocaleString("vi-VN")} ký tự ·{" "}
              {wordCount.toLocaleString("vi-VN")} từ · ~
              {Math.ceil(wordCount / 2.5)} giây audio
            </span>
            <div className="doc-send">
              <button
                className="doc-send-secondary"
                disabled={!hasText}
                onClick={() => onSendToConversation(cleanedText)}
                type="button"
              >
                <MessagesSquare size={16} />
                Sang Hội thoại
              </button>
              <button
                className="doc-send-secondary"
                disabled={!hasText}
                onClick={handleSendToBatch}
                title="Tách theo Chương/Chapter/Hồi, mỗi chương một file audio"
                type="button"
              >
                <ListOrdered size={16} />
                Sang Tạo hàng loạt
              </button>
              <button
                className="studio-primary doc-send-primary"
                disabled={!hasText}
                onClick={() => onSendToTts(cleanedText)}
                type="button"
              >
                Đọc văn bản này
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
