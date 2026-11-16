import {
  AlertCircle,
  CheckCircle2,
  Download,
  Loader2,
  Play,
  Sparkles,
  Waves,
} from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createDesignVoice,
  fetchHardware,
  fetchVoicePreview,
  type HardwareModel,
  supportsVoiceDesign,
} from "../api";
import type { VoiceOption } from "../types";
import { useModelDownload } from "./useModelDownload";

const MODEL_ID_PREFIX = "VoxCPM2";

interface Group {
  key: string;
  label: string;
  /** Nhiều lựa chọn cùng lúc (phong cách). */
  multi?: boolean;
  options: string[];
}

const GROUPS: Group[] = [
  { key: "gender", label: "Giới tính", options: ["Nữ", "Nam"] },
  {
    key: "age",
    label: "Độ tuổi",
    options: ["Trẻ em", "Thiếu niên", "Thanh niên", "Trung niên", "Cao tuổi"],
  },
  { key: "pitch", label: "Tông giọng", options: ["Trầm", "Vừa", "Cao"] },
  { key: "pace", label: "Tốc độ nói", options: ["Chậm", "Vừa phải", "Nhanh"] },
  {
    key: "style",
    label: "Phong cách",
    multi: true,
    options: [
      "Ấm áp",
      "Tin tức",
      "Kể chuyện",
      "Nhẹ nhàng",
      "Nghiêm túc",
      "Vui tươi",
      "Truyền cảm",
      "Năng động",
    ],
  },
  {
    key: "region",
    label: "Vùng miền",
    options: ["Miền Bắc", "Miền Trung", "Miền Nam"],
  },
];

type Picked = Record<string, string[]>;

function describe(p: Picked): string {
  const g = (k: string) => p[k] ?? [];
  const parts: string[] = [];
  const who = [
    g("gender")[0] ? g("gender")[0].toLowerCase() : "",
    g("age")[0] ? g("age")[0].toLowerCase() : "",
  ].filter(Boolean);
  if (who.length) {
    parts.push(`Giọng ${who.join(" ")}`);
  }
  if (g("pitch")[0]) {
    parts.push(`tông ${g("pitch")[0].toLowerCase()}`);
  }
  if (g("pace")[0]) {
    parts.push(`nói ${g("pace")[0].toLowerCase()}`);
  }
  if (g("style").length) {
    parts.push(
      `phong cách ${g("style")
        .map((s) => s.toLowerCase())
        .join(", ")}`
    );
  }
  if (g("region")[0]) {
    parts.push(`giọng ${g("region")[0].toLowerCase()}`);
  }
  return parts.join(", ");
}

interface Props {
  apiUrl: string;
  onDesigned: (voiceId: string) => Promise<void>;
  voices: VoiceOption[];
}

export const DesignVoiceTab: React.FC<Props> = ({ apiUrl, onDesigned }) => {
  const [canDesign, setCanDesign] = useState(false);
  const [model, setModel] = useState<HardwareModel | null>(null);
  const [picked, setPicked] = useState<Picked>({});
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<"" | "preview" | "save">("");
  const [msg, setMsg] = useState<{ error?: boolean; text: string } | null>(
    null
  );
  const [nudge, setNudge] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const bannerRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    setCanDesign(await supportsVoiceDesign(apiUrl));
    try {
      const hw = await fetchHardware(apiUrl);
      setModel(hw.models.find((m) => m.id.startsWith(MODEL_ID_PREFIX)) ?? null);
    } catch {
      setModel(null);
    }
  };
  const dl = useModelDownload(apiUrl, refresh);

  useEffect(() => {
    refresh();
    // biome-ignore lint/correctness/useExhaustiveDependencies: chỉ nạp khi mở tab
  }, [apiUrl]);

  useEffect(
    () => () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    },
    [previewUrl]
  );

  const auto = useMemo(() => describe(picked), [picked]);
  const [edited, setEdited] = useState(false);
  useEffect(() => {
    if (!edited) {
      setText(auto);
    }
  }, [auto, edited]);

  const touch = () => {
    if (!canDesign) {
      setNudge(true);
      bannerRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      setTimeout(() => setNudge(false), 1600);
    }
  };

  const toggle = (g: Group, opt: string) => {
    touch();
    setEdited(false);
    setPicked((p) => {
      const cur = p[g.key] ?? [];
      if (g.multi) {
        return {
          ...p,
          [g.key]: cur.includes(opt)
            ? cur.filter((x) => x !== opt)
            : [...cur, opt],
        };
      }
      return { ...p, [g.key]: cur[0] === opt ? [] : [opt] };
    });
  };

  const run = async (mode: "preview" | "save") => {
    if (!canDesign) {
      touch();
      return;
    }
    if (!text.trim()) {
      setMsg({
        error: true,
        text: "Hãy chọn vài đặc điểm giọng ở trên hoặc tự gõ mô tả.",
      });
      return;
    }
    const nm =
      name.trim() || `Giọng thiết kế ${new Date().toLocaleTimeString("vi-VN")}`;
    setBusy(mode);
    setMsg(null);
    try {
      const id = await createDesignVoice(apiUrl, nm, text.trim());
      await onDesigned(id);
      if (mode === "preview") {
        const blob = await fetchVoicePreview(apiUrl, id);
        setPreviewUrl(URL.createObjectURL(blob));
        setMsg({
          text: `Đã tạo giọng "${nm}". Giọng đã được lưu; chưa ưng thì chỉnh chip, thử lại, và xoá giọng thừa ở Thư viện giọng.`,
        });
      } else {
        setMsg({
          text: `Đã lưu "${nm}". Giọng này có trong danh sách giọng ở mọi mục.`,
        });
      }
    } catch (e) {
      setMsg({ error: true, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy("");
    }
  };

  const gb = model?.approx_bytes
    ? (model.approx_bytes / 1024 ** 3).toFixed(1)
    : "5";
  const cannot = model?.fit.level === "no";

  return (
    <div className="studio-tab-grid studio-document-layout fade-in-50 animate-in duration-300">
      <div className="studio-span-5 flex flex-col gap-4">
        <div className="studio-tab-card doc-card">
          <div className="doc-card-head">
            <h3>Thiết kế giọng</h3>
            <p>Chọn đặc điểm, app tự viết mô tả và tạo ra giọng mới.</p>
          </div>

          <div
            className={`rounded-xl border p-3 text-xs ${
              canDesign
                ? "border-emerald-500/40 bg-emerald-500/10"
                : "border-amber-500/50 bg-amber-500/10"
            } ${nudge ? "ring-2 ring-amber-500" : ""}`}
            ref={bannerRef}
          >
            {canDesign ? (
              <p className="flex items-center gap-2 font-semibold text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" /> VoxCPM2 đang chạy.
                Bạn có thể thiết kế giọng.
              </p>
            ) : (
              <div className="space-y-2">
                <p className="flex items-start gap-2 font-semibold">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  Tính năng này cần mô hình VoxCPM2 (khoảng {gb} GB, chỉ tải một
                  lần).
                </p>
                {model && (
                  <p
                    className={
                      cannot
                        ? "text-rose-600 dark:text-rose-400"
                        : "text-muted-foreground"
                    }
                  >
                    {model.fit.reason}
                  </p>
                )}
                {dl.busy && (
                  <div>
                    <div className="h-2 overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full bg-brand-500 transition-all"
                        style={{ width: `${dl.state?.percent ?? 0}%` }}
                      />
                    </div>
                    <p className="mt-1 text-muted-foreground">
                      {dl.state?.message} ({Math.round(dl.state?.percent ?? 0)}
                      %)
                    </p>
                  </div>
                )}
                {dl.error && (
                  <p className="text-rose-600 dark:text-rose-400">{dl.error}</p>
                )}
                <button
                  className="studio-primary flex items-center gap-2 rounded-lg px-3 py-2 font-bold"
                  disabled={!model || cannot || dl.busy}
                  onClick={() => model && dl.start(model.id)}
                  type="button"
                >
                  {dl.busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  {model?.downloaded ? "Bật VoxCPM2" : "Tải VoxCPM2"}
                </button>
                <p className="text-muted-foreground">
                  Bạn vẫn chọn thử các chip bên dưới được. Tải xong mới tạo được
                  giọng.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-1 text-xs">
            <span className="font-semibold text-foreground/90">
              1. Đặt tên giọng (không bắt buộc)
            </span>
            <input
              className="w-full rounded-lg border border-border/80 bg-background px-2.5 py-1.5 outline-none focus:border-brand-500"
              maxLength={40}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ví dụ: MC bản tin sáng"
              value={name}
            />
          </div>
        </div>
      </div>

      <div className="studio-span-7 flex flex-col">
        <div className="studio-tab-card doc-editor">
          <div className="doc-editor-head">
            <h3>
              <Waves size={18} />
              2. Chọn đặc điểm giọng
            </h3>
            <div className="doc-editor-tools">
              <button
                onClick={() => {
                  setPicked({});
                  setEdited(false);
                  setPreviewUrl(null);
                }}
                type="button"
              >
                Chọn lại
              </button>
            </div>
          </div>

          <div className="space-y-3 text-xs">
            {GROUPS.map((g) => (
              <div key={g.key}>
                <div className="mb-1 font-semibold text-foreground/90">
                  {g.label}
                  {g.multi && (
                    <span className="ml-1 font-normal text-muted-foreground">
                      (chọn được nhiều)
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {g.options.map((o) => {
                    const on = (picked[g.key] ?? []).includes(o);
                    return (
                      <button
                        aria-pressed={on}
                        className={`rounded-full border px-3 py-1 font-medium transition-colors ${
                          on
                            ? "border-brand-500 bg-brand-500 text-white"
                            : "border-border/80 bg-background hover:border-brand-500/60"
                        }`}
                        key={o}
                        onClick={() => toggle(g, o)}
                        type="button"
                      >
                        {o}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-1 text-xs">
            <span className="font-semibold text-foreground/90">
              3. Mô tả giọng (có thể sửa tay)
            </span>
            <textarea
              className="h-16 w-full rounded-lg border border-border/80 bg-background px-2.5 py-1.5 outline-none focus:border-brand-500"
              maxLength={200}
              onChange={(e) => {
                setEdited(true);
                setText(e.target.value);
              }}
              placeholder="Chọn chip phía trên, mô tả sẽ tự hiện ở đây."
              value={text}
            />
          </div>

          {msg && (
            <div
              className={msg.error ? "doc-error" : "doc-notice"}
              role="status"
            >
              {msg.error ? (
                <AlertCircle className="h-4 w-4 shrink-0" />
              ) : (
                <CheckCircle2 className="h-4 w-4 shrink-0" />
              )}
              <span>{msg.text}</span>
            </div>
          )}
          {previewUrl && (
            <audio autoPlay controls src={previewUrl} style={{ width: "100%" }}>
              <track kind="captions" />
            </audio>
          )}

          <div className="doc-footer">
            <span className="doc-stats">
              Tạo giọng xong, giọng được lưu và dùng được ở mọi mục.
            </span>
            <div className="doc-send">
              <button
                className="doc-send-secondary"
                disabled={busy !== ""}
                onClick={() => run("preview")}
                type="button"
              >
                {busy === "preview" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play size={16} />
                )}
                Nghe thử
              </button>
              <button
                className="studio-primary doc-send-primary"
                disabled={busy !== ""}
                onClick={() => run("save")}
                type="button"
              >
                {busy === "save" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles size={16} />
                )}
                Lưu giọng này
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
