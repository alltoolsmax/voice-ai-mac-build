import {
  CheckCircle2,
  Cpu,
  Download,
  HardDrive,
  Loader2,
  MemoryStick,
  MonitorPlay,
  Zap,
} from "lucide-react";
import type React from "react";
import { useEffect, useState } from "react";
import {
  fetchHardware,
  type HardwareModel,
  type HardwareReport,
  switchModel,
} from "../api";
import { useModelDownload } from "./useModelDownload";

const BADGE: Record<string, { cls: string; label: string }> = {
  no: {
    cls: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
    label: "Chưa đủ cấu hình",
  },
  ok: {
    cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    label: "Phù hợp",
  },
  weak: {
    cls: "bg-amber-500/20 text-amber-700 dark:text-amber-300",
    label: "Hơi sát",
  },
};

const size = (b?: number) => {
  if (!b) {
    return "";
  }
  return b >= 1024 ** 3
    ? `${(b / 1024 ** 3).toFixed(1)} GB`
    : `${Math.round(b / 1024 ** 2)} MB`;
};

interface Props {
  apiUrl: string;
  onModelSwitched?: (name: string) => void;
}

export const ModelsTab: React.FC<Props> = ({ apiUrl, onModelSwitched }) => {
  const [rep, setRep] = useState<HardwareReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);

  const load = async () => {
    try {
      setRep(await fetchHardware(apiUrl));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const dl = useModelDownload(apiUrl, load);

  useEffect(() => {
    load();
    // biome-ignore lint/correctness/useExhaustiveDependencies: nạp khi mở tab
  }, [apiUrl]);

  const use = async (m: HardwareModel) => {
    setSwitching(m.id);
    setErr(null);
    try {
      await switchModel(apiUrl, m.id);
      onModelSwitched?.(m.id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSwitching(null);
    }
  };

  const hw = rep?.hardware;
  const currentName = rep?.current?.name;
  const rank = (m: HardwareModel) =>
    m.id === rep?.recommended
      ? 0
      : m.fit.level === "ok"
        ? 1
        : m.fit.level === "weak"
          ? 2
          : 3;
  const models = [...(rep?.models ?? [])].sort((a, b) => rank(a) - rank(b));

  return (
    <div className="fade-in-50 animate-in space-y-4 duration-300">
      <div className="studio-tab-card doc-card">
        <div className="doc-card-head">
          <h3>Mô hình</h3>
          <p>
            App đã kiểm tra máy của bạn và gợi ý mô hình phù hợp. Bấm "Dùng mô
            hình này" để chuyển.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
          {[
            {
              icon: Cpu,
              label: "CPU",
              value: hw?.cpu_cores ? `${hw.cpu_cores} luồng` : "Không rõ",
            },
            {
              icon: MemoryStick,
              label: "RAM",
              value: hw?.ram_gb ? `${hw.ram_gb} GB` : "Không rõ",
            },
            {
              icon: MonitorPlay,
              label: "Card đồ họa",
              value: hw?.gpu
                ? `${hw.gpu.name} · ${hw.gpu.vram_gb} GB`
                : "Không có NVIDIA",
            },
            {
              icon: HardDrive,
              label: "Ổ đĩa trống",
              value: hw?.disk_free_gb ? `${hw.disk_free_gb} GB` : "Không rõ",
            },
          ].map((x) => (
            <div
              className="flex items-center gap-2 rounded-xl border border-border/70 bg-secondary/30 p-2.5"
              key={x.label}
            >
              <x.icon
                aria-hidden="true"
                className="h-5 w-5 shrink-0 text-brand-600"
              />
              <div className="min-w-0">
                <div className="text-muted-foreground">{x.label}</div>
                <div className="truncate font-semibold">{x.value}</div>
              </div>
            </div>
          ))}
        </div>
        {!(rep || err) && (
          <p className="flex items-center gap-2 text-muted-foreground text-xs">
            <Loader2 className="h-4 w-4 animate-spin" /> Đang kiểm tra cấu hình
            máy...
          </p>
        )}
        {err && (
          <p className="text-rose-600 text-xs dark:text-rose-400">{err}</p>
        )}
        {dl.error && (
          <p className="text-rose-600 text-xs dark:text-rose-400">{dl.error}</p>
        )}
      </div>

      <div className="space-y-3">
        {models.map((m) => {
          const badge = BADGE[m.fit.level];
          const isCurrent = currentName === m.id || currentName === m.name;
          const downloading = dl.busy && dl.state?.model_id === m.id;
          return (
            <div className="studio-tab-card doc-card" key={m.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-bold text-sm">{m.name}</h4>
                    {m.id === rep?.recommended && (
                      <span className="flex items-center gap-1 rounded-full bg-brand-500 px-2 py-0.5 font-bold text-[11px] text-white">
                        <Zap className="h-3 w-3" /> Gợi ý cho máy bạn
                      </span>
                    )}
                    <span
                      className={`rounded-full px-2 py-0.5 font-bold text-[11px] ${badge.cls}`}
                    >
                      {badge.label}
                    </span>
                    {isCurrent && (
                      <span className="flex items-center gap-1 text-[11px] text-emerald-700 dark:text-emerald-300">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Đang dùng
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-muted-foreground text-xs">
                    {m.description}
                  </p>
                  <p className="mt-1 text-xs">
                    {m.device === "cuda"
                      ? "Chạy bằng GPU NVIDIA"
                      : "Chạy bằng CPU"}{" "}
                    ·{" "}
                    {m.downloaded
                      ? "Đã tải"
                      : `Cần tải ${size(m.approx_bytes)}`}{" "}
                    ·{" "}
                    {m.supports_cloning
                      ? "Có nhân bản giọng"
                      : "Không nhân bản giọng"}
                  </p>
                  <p className="mt-0.5 text-[12px] text-muted-foreground">
                    {m.fit.reason}
                  </p>
                  {m.note && (
                    <p className="mt-0.5 text-[12px] text-muted-foreground">
                      {m.note}
                    </p>
                  )}
                  {downloading && (
                    <div className="mt-2">
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-brand-500 transition-all"
                          style={{ width: `${dl.state?.percent ?? 0}%` }}
                        />
                      </div>
                      <p className="mt-1 text-muted-foreground text-xs">
                        {dl.state?.message} (
                        {Math.round(dl.state?.percent ?? 0)}%)
                      </p>
                    </div>
                  )}
                </div>
                <div className="shrink-0">
                  {isCurrent ? null : m.downloaded ? (
                    <button
                      className="studio-primary rounded-lg px-3 py-2 font-bold text-xs"
                      disabled={
                        m.fit.level === "no" || switching !== null || dl.busy
                      }
                      onClick={() => use(m)}
                      type="button"
                    >
                      {switching === m.id
                        ? "Đang chuyển..."
                        : "Dùng mô hình này"}
                    </button>
                  ) : (
                    <button
                      className="studio-primary flex items-center gap-1.5 rounded-lg px-3 py-2 font-bold text-xs"
                      disabled={m.fit.level === "no" || dl.busy}
                      onClick={() => dl.start(m.id)}
                      type="button"
                    >
                      {downloading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                      Tải và dùng
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
