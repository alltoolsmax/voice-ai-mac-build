import { Check, Loader2, Play, Search, Square, Star } from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createDesignVoice,
  fetchVoicePreview,
  supportsVoiceDesign,
} from "../api";
import { useModelCaps } from "../model-caps";
import type { VoiceOption } from "../types";
import { voiceDetail } from "../voice-label";

// Thu vien giong: cac giong that co san cua mo hinh dang chay (+ giong nhan ban), co tim kiem,
// loc theo gioi tinh / ngon ngu / vung mien / yeu thich, nghe thu va chon dung.

type Filter = "all" | "favorite" | "female" | "male" | "cloned";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "female", label: "Nữ" },
  { id: "male", label: "Nam" },
  { id: "cloned", label: "Giọng của tôi" },
  { id: "favorite", label: "Yêu thích" },
];

const FAVORITES_KEY = "voice-ai-favorite-voices";

const loadFavorites = (): string[] => {
  try {
    const raw = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
};

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");

const strip = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();

interface VoiceLibraryTabProps {
  apiUrl: string;
  /** Goi sau khi luu giong thiet ke moi: nap lai danh sach giong va chon giong do. */
  onDesigned?: (voiceId: string) => Promise<void>;
  onUseVoice: (voiceId: string) => void;
  selectedVoiceId: string;
  voices: VoiceOption[];
}

export const VoiceLibraryTab: React.FC<VoiceLibraryTabProps> = ({
  apiUrl,
  voices,
  selectedVoiceId,
  onUseVoice,
  onDesigned,
}) => {
  const [canDesign, setCanDesign] = useState(false);
  const [designName, setDesignName] = useState("");
  const [designText, setDesignText] = useState("");
  const [designBusy, setDesignBusy] = useState(false);
  const [designMsg, setDesignMsg] = useState("");
  useEffect(() => {
    supportsVoiceDesign(apiUrl).then(setCanDesign);
  }, [apiUrl, voices.length]);

  const saveDesign = async () => {
    if (designBusy || !designName.trim() || !designText.trim()) {
      return;
    }
    setDesignBusy(true);
    setDesignMsg("");
    try {
      const id = await createDesignVoice(
        apiUrl,
        designName.trim(),
        designText.trim()
      );
      await onDesigned?.(id);
      setDesignName("");
      setDesignText("");
      setDesignMsg("Đã lưu giọng. Bấm nghe thử ở thẻ giọng bên dưới.");
    } catch (e) {
      setDesignMsg(
        e instanceof Error ? e.message : "Không lưu được giọng thiết kế."
      );
    } finally {
      setDesignBusy(false);
    }
  };
  const { languages } = useModelCaps();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [lang, setLang] = useState("all");
  const [region, setRegion] = useState("all");
  const [favorites, setFavorites] = useState<string[]>(loadFavorites);
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = () => {
    abortRef.current?.abort();
    audioRef.current?.pause();
    audioRef.current = null;
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    setPlaying(null);
    setLoading(null);
  };

  useEffect(() => stop, []);

  const toggleFavorite = (id: string) => {
    setFavorites((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
      try {
        localStorage.setItem(FAVORITES_KEY, JSON.stringify(next));
      } catch {
        // khong luu duoc (che do rieng tu): van dung trong phien nay
      }
      return next;
    });
  };

  const preview = async (voice: VoiceOption) => {
    const same = playing === voice.id || loading === voice.id;
    stop();
    if (same) {
      return;
    }
    setError("");
    setLoading(voice.id);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const blob = await fetchVoicePreview(apiUrl, voice.id, controller.signal);
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying(null);
      setLoading(null);
      setPlaying(voice.id);
      await audio.play();
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(
          e instanceof Error ? e.message : "Không nghe thử được giọng này."
        );
        setLoading(null);
        setPlaying(null);
      }
    }
  };

  // Ngon ngu co trong danh sach giong hien tai (Kokoro, Supertonic...). VieNeu khong co.
  const voiceLanguages = useMemo(() => {
    const codes = [
      ...new Set(voices.map((v) => v.language).filter(Boolean)),
    ] as string[];
    return codes.map((code) => ({
      code,
      name: languages.find((l) => l.code === code)?.name ?? code,
    }));
  }, [voices, languages]);
  const hasRegions = voices.some((v) => v.region && !v.language);

  const shown = useMemo(() => {
    const q = strip(query.trim());
    return voices.filter((v) => {
      if (filter === "female" && v.gender !== "female") {
        return false;
      }
      if (filter === "male" && v.gender !== "male") {
        return false;
      }
      if (filter === "cloned" && !v.isCloned) {
        return false;
      }
      if (filter === "favorite" && !favorites.includes(v.id)) {
        return false;
      }
      if (lang !== "all" && v.language !== lang) {
        return false;
      }
      if (region !== "all" && v.region !== region) {
        return false;
      }
      return !q || strip(`${v.name} ${voiceDetail(v)}`).includes(q);
    });
  }, [voices, filter, lang, region, favorites, query]);

  return (
    <div className="studio-tab-card fade-in-50 animate-in space-y-4 p-5 duration-300">
      <div>
        <h3 className="font-bold text-foreground text-lg">Thư viện giọng</h3>
        <p className="text-muted-foreground text-sm">
          Chọn giọng, nghe thử rồi dùng ngay. Danh sách là các giọng của mô hình
          đang chạy; đổi mô hình (nút "Đổi mô hình" ở trên) để xem giọng và ngôn
          ngữ khác.
        </p>
      </div>

      {canDesign && (
        <div className="space-y-2 rounded-2xl border border-border/70 bg-secondary/20 p-3">
          <p className="font-semibold text-foreground text-sm">
            Thiết kế giọng từ mô tả
          </p>
          <p className="text-muted-foreground text-xs">
            Mô tả giọng bằng vài từ, ví dụ "nữ trẻ, giọng ấm, nói chậm" hoặc
            "nam trung niên, trầm, tin tức". Lưu lại để dùng như các giọng khác.
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="Tên giọng"
              className="w-40 rounded-xl border border-border/80 bg-background px-3 py-2 text-sm outline-none focus:border-brand-500"
              maxLength={40}
              onChange={(e) => setDesignName(e.target.value)}
              placeholder="Tên giọng"
              value={designName}
            />
            <input
              aria-label="Mô tả giọng"
              className="min-w-[220px] flex-1 rounded-xl border border-border/80 bg-background px-3 py-2 text-sm outline-none focus:border-brand-500"
              maxLength={200}
              onChange={(e) => setDesignText(e.target.value)}
              placeholder="Mô tả giọng (tiếng Việt hoặc tiếng Anh)"
              value={designText}
            />
            <button
              className="rounded-xl bg-brand-600 px-4 py-2 font-semibold text-sm text-white hover:bg-brand-700 disabled:opacity-50"
              disabled={designBusy || !designName.trim() || !designText.trim()}
              onClick={saveDesign}
              type="button"
            >
              {designBusy ? "Đang lưu..." : "Lưu giọng"}
            </button>
          </div>
          {designMsg && (
            <p className="text-muted-foreground text-xs" role="status">
              {designMsg}
            </p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[200px] flex-1">
          <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            aria-label="Tìm giọng"
            className="w-full rounded-xl border border-border/80 bg-secondary/20 py-2 pr-3 pl-9 text-sm outline-none focus:border-brand-500"
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm theo tên giọng..."
            value={query}
          />
        </label>
        {voiceLanguages.length > 0 && (
          <select
            aria-label="Ngôn ngữ"
            className="rounded-xl border border-border/80 bg-secondary/20 px-3 py-2 text-sm"
            onChange={(e) => setLang(e.target.value)}
            value={lang}
          >
            <option value="all">Mọi ngôn ngữ</option>
            {voiceLanguages.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </select>
        )}
        {hasRegions && (
          <select
            aria-label="Vùng miền"
            className="rounded-xl border border-border/80 bg-secondary/20 px-3 py-2 text-sm"
            onChange={(e) => setRegion(e.target.value)}
            value={region}
          >
            <option value="all">Mọi vùng miền</option>
            <option value="North">Miền Bắc</option>
            <option value="Central">Miền Trung</option>
            <option value="South">Miền Nam</option>
          </select>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            aria-pressed={filter === f.id}
            className={`rounded-full border px-3 py-1 font-semibold text-xs transition ${
              filter === f.id
                ? "border-brand-500 bg-brand-500/15 text-brand-700 dark:text-brand-300"
                : "border-border/80 text-muted-foreground hover:bg-secondary/60"
            }`}
            key={f.id}
            onClick={() => setFilter(f.id)}
            type="button"
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="font-medium text-rose-600 text-xs" role="alert">
          {error}
        </p>
      )}

      {shown.length === 0 ? (
        <p className="py-10 text-center text-muted-foreground text-sm">
          {voices.length === 0
            ? "Chưa có giọng nào. Hãy đợi mô hình nạp xong."
            : "Không có giọng phù hợp bộ lọc."}
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((v) => {
            const fav = favorites.includes(v.id);
            const active = v.id === selectedVoiceId;
            const detail = voiceDetail(v);
            return (
              <div
                className={`flex flex-col gap-3 rounded-2xl border p-3 ${
                  active
                    ? "border-brand-500 bg-brand-500/5"
                    : "border-border/70 bg-secondary/20"
                }`}
                key={v.id}
              >
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-500/15 font-bold text-brand-700 text-xs dark:text-brand-300"
                  >
                    {initials(v.name)}
                  </span>
                  <span
                    className="min-w-0 flex-1 truncate font-bold text-foreground text-sm"
                    title={v.name}
                  >
                    {v.name}
                  </span>
                  <button
                    aria-label={
                      fav ? `Bỏ yêu thích ${v.name}` : `Yêu thích ${v.name}`
                    }
                    aria-pressed={fav}
                    className="rounded-lg p-1 text-muted-foreground hover:bg-secondary"
                    onClick={() => toggleFavorite(v.id)}
                    type="button"
                  >
                    <Star
                      className={`h-4 w-4 ${fav ? "fill-amber-400 text-amber-400" : ""}`}
                    />
                  </button>
                </div>
                <p className="min-h-[2.2em] text-muted-foreground text-xs leading-snug">
                  {[
                    detail,
                    v.language
                      ? (languages.find((l) => l.code === v.language)?.name ??
                        v.language)
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Giọng đọc có sẵn"}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    aria-label={
                      playing === v.id ? `Dừng ${v.name}` : `Nghe thử ${v.name}`
                    }
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-border/80 hover:bg-secondary"
                    onClick={() => preview(v)}
                    type="button"
                  >
                    {loading === v.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : playing === v.id ? (
                      <Square className="h-3.5 w-3.5" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-brand-600 px-3 py-1.5 font-semibold text-white text-xs hover:bg-brand-700"
                    onClick={() => onUseVoice(v.id)}
                    type="button"
                  >
                    {active && <Check className="h-3.5 w-3.5" />}
                    {active ? "Đang dùng" : "Sử dụng giọng nói"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
