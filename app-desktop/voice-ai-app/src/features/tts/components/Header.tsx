import { Moon, PlayCircle, RefreshCw, Sun } from "lucide-react";
import type React from "react";
import { useEffect, useState } from "react";
import logo from "../../../assets/logo.png";
import type { ConnectionStatus } from "../types";

const GPU_ENGINE = /GPU|CUDA|pytorch/i;
const CONNECTION_LABELS = {
  connected: "Sẵn sàng · Đổi mô hình",
  connecting: "Đang kết nối · Đổi mô hình",
  disconnected: "Mất kết nối · Đổi mô hình",
  error: "Mất kết nối · Đổi mô hình",
};
const CONNECTION_COLORS = {
  connected: "bg-green-600",
  connecting: "bg-amber-500",
  disconnected: "bg-rose-500",
  error: "bg-rose-500",
};
interface HeaderProps {
  apiUrl: string;
  engineName: string;
  isDark: boolean;
  onOpenSettings: () => void;
  onRefresh: () => void;
  onToggleDark: () => void;
  sampleRate: number;
  status: ConnectionStatus;
}

const VIDEO_REFRESH_MS = 5 * 60_000;

/** Nút "Xem Video hướng dẫn": link do admin đặt trên máy chủ; chưa đặt thì ẩn. */
const VideoGuideButton: React.FC<{ apiUrl: string }> = ({ apiUrl }) => {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch(`${apiUrl.replace(/\/+$/, "")}/api/app/video`)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (alive && data && typeof data.url === "string") {
            setUrl(data.url.startsWith("https://") ? data.url : "");
          }
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, VIDEO_REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [apiUrl]);
  if (!url) {
    return null;
  }
  return (
    <a
      className="studio-video-guide"
      href={url}
      rel="noopener noreferrer"
      target="_blank"
      title="Mở video hướng dẫn trên YouTube (tab mới)"
    >
      <PlayCircle aria-hidden="true" size={16} />
      <span>Xem Video hướng dẫn</span>
    </a>
  );
};

export const Header: React.FC<HeaderProps> = ({
  apiUrl,
  engineName,
  isDark,
  onOpenSettings,
  onRefresh,
  onToggleDark,
  sampleRate,
  status,
}) => (
  <header className="studio-header">
    <div className="flex items-center gap-2.5">
      <img
        alt="Voice AI - Mr. Huỳnh"
        className="h-9 w-9 shrink-0 rounded-[10px]"
        height={36}
        src={logo}
        width={36}
      />
      <h1 className="font-bold text-sm tracking-tight">Voice AI - Mr. Huỳnh</h1>
      <a
        className="border-border border-l pl-2.5 font-bold text-[13px] text-brand-600 underline-offset-4 hover:underline dark:text-brand-400"
        href="https://zalo.me/0979007367"
        rel="noopener noreferrer"
        target="_blank"
        title="Zalo Huỳnh Xuyên Sơn (mở tab mới)"
      >
        0979.007.367
      </a>
    </div>
    <VideoGuideButton apiUrl={apiUrl} />
    <div className="flex min-w-0 items-center gap-2">
      <button
        className="studio-model"
        onClick={onOpenSettings}
        title={CONNECTION_LABELS[status]}
        type="button"
      >
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${CONNECTION_COLORS[status]}`}
        />
        <span className="truncate font-semibold">{engineName}</span>
        <span className="hidden whitespace-nowrap tabular-nums sm:inline">
          · {GPU_ENGINE.test(engineName) ? "GPU" : "CPU"} · {sampleRate / 1000}{" "}
          kHz
        </span>
        <span className="studio-model-action">⇄ Đổi mô hình</span>
      </button>
      {status !== "connected" && (
        <button
          aria-label="Thử kết nối lại"
          className="studio-icon-button"
          onClick={onRefresh}
          type="button"
        >
          <RefreshCw size={16} />
        </button>
      )}
      <button
        aria-label={
          isDark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"
        }
        className="studio-icon-button"
        onClick={onToggleDark}
        type="button"
      >
        {isDark ? <Sun size={17} /> : <Moon size={17} />}
      </button>
    </div>
  </header>
);
