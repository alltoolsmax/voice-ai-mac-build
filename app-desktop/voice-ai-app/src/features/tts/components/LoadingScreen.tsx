import { AlertTriangle, RefreshCw, Settings } from "lucide-react";
import type React from "react";
import { useEffect, useRef } from "react";
import logo from "../../../assets/logo.png";

interface LoadingScreenProps {
  isDark: boolean;
  message: string;
  onOpenSettings: () => void;
  onRetry: () => void;
  status: "starting" | "downloading" | "ready" | "failed";
}

const SIZE = 520; // vùng vẽ (px) quanh logo
const BARS = 96;
const PERIOD = 3; // giây: mọi chuyển động lặp trong 3 giây

interface Particle {
  a: number;
  h: number;
  r: number;
  s: number;
  z: number;
}

const hue = (a: number) =>
  `hsl(${190 + 140 * (0.5 + 0.5 * Math.sin(a))},95%,64%)`;

/** Vòng phổ âm thanh + sóng lan + hạt sáng quanh logo (canvas, dừng khi người dùng giảm chuyển động). */
const VoiceOrb: React.FC<{ frozen: boolean }> = ({ frozen }) => {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!(canvas && ctx)) {
      return;
    }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    ctx.scale(dpr, dpr);
    const reduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    const parts: Particle[] = Array.from({ length: 46 }, () => ({
      a: Math.random() * 6.283,
      h: Math.random(),
      r: 110 + Math.random() * 130,
      s: 0.2 + Math.random() * 0.6,
      z: 1 + Math.random() * 2,
    }));
    const C = SIZE / 2;
    const W = 6.283 / PERIOD;

    const draw = (t: number) => {
      ctx.clearRect(0, 0, SIZE, SIZE);
      for (let k = 0; k < 3; k++) {
        const ph = (t / PERIOD + k / 3) % 1;
        ctx.beginPath();
        ctx.arc(C, C, 92 + ph * 160, 0, 6.283);
        ctx.strokeStyle = `rgba(103,232,249,${0.34 * (1 - ph)})`;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.lineCap = "round";
      for (let i = 0; i < BARS; i++) {
        const a = (i / BARS) * 6.283 - 1.5708;
        const w =
          Math.sin(a * 3 + t * W * 2) * 0.5 +
          Math.sin(a * 5 - t * W * 3) * 0.35 +
          Math.sin(a * 2 + t * W) * 0.3;
        const h =
          16 + Math.abs(w) * 48 + 10 * Math.sin(t * W * 3 + i * 0.7) ** 2;
        const col = hue(a + t * W);
        ctx.beginPath();
        ctx.moveTo(C + Math.cos(a) * 96, C + Math.sin(a) * 96);
        ctx.lineTo(C + Math.cos(a) * (96 + h), C + Math.sin(a) * (96 + h));
        ctx.strokeStyle = col;
        ctx.shadowColor = col;
        ctx.shadowBlur = 12;
        ctx.lineWidth = 4.2;
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
      for (const p of parts) {
        const a = p.a + t * W * (p.s > 0.5 ? 1 : -1) * 0.12;
        const rr = p.r + Math.sin(t * W * 2 + p.h * 9) * 10;
        ctx.beginPath();
        ctx.arc(C + Math.cos(a) * rr, C + Math.sin(a) * rr, p.z, 0, 6.283);
        ctx.fillStyle = `hsla(${190 + p.h * 140},95%,70%,${0.25 + 0.5 * Math.abs(Math.sin(t * W + p.h * 7))})`;
        ctx.fill();
      }
    };

    if (reduced || frozen) {
      draw(0.9);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const loop = (now: number) => {
      draw(((now - start) / 1000) % PERIOD);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [frozen]);

  return (
    <canvas
      aria-hidden="true"
      className="va-orb-canvas"
      ref={ref}
      style={{ height: SIZE, width: SIZE }}
    />
  );
};

export const LoadingScreen: React.FC<LoadingScreenProps> = ({
  status,
  message,
  onRetry,
  onOpenSettings,
}) => {
  const failed = status === "failed";
  const progress =
    status === "ready" ? 100 : status === "downloading" ? 62 : 34;
  return (
    <div className="va-splash2 fixed inset-0 z-50 flex select-none flex-col items-center justify-center overflow-hidden px-4">
      <div className="va-orb">
        <VoiceOrb frozen={failed} />
        <img
          alt="Voice AI - Mr. Huỳnh"
          className="va-orb-logo"
          height={150}
          src={logo}
          width={150}
        />
      </div>

      <h1 className="va-splash2-title">Voice AI - Mr. Huỳnh</h1>
      <p className="va-splash2-sub">
        Chuyển văn bản thành giọng nói tiếng Việt
      </p>

      {failed ? (
        <div className="va-splash2-fail">
          <p className="flex items-start gap-2 text-left text-[13px] text-rose-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="break-words">
              {message || "Không kết nối được dịch vụ giọng nói."}
            </span>
          </p>
          <div className="mt-3 flex gap-2">
            <button
              className="va-splash2-btn primary"
              onClick={onRetry}
              type="button"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Thử kết nối lại
            </button>
            <button
              className="va-splash2-btn"
              onClick={onOpenSettings}
              type="button"
            >
              <Settings className="h-3.5 w-3.5" />
              Mở cài đặt
            </button>
          </div>
        </div>
      ) : (
        <div className="va-splash2-prog">
          <div className="va-splash2-track">
            <i style={{ width: `${progress}%` }} />
          </div>
          <div className="va-splash2-step">
            <span className="va-splash2-dot" />
            <span>{message || "Đang chuẩn bị mô hình giọng nói..."}</span>
          </div>
        </div>
      )}
    </div>
  );
};
