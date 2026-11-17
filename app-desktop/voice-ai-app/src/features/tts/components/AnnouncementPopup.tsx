import { X } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

// Thông báo popup do Mr.Huỳnh soạn trên máy chủ (admin.php), không liên quan tới cập nhật phiên bản.
// App chỉ hiện khi đúng đối tượng; người dùng đóng xong thì không hiện lại cho tới khi nội dung đổi.
// Hỏi lại backend mỗi 30 giây (backend lại hỏi máy chủ tối đa mỗi 60 giây) nên Mr.Huỳnh bấm Lưu xong
// thì khoảng 1 phút sau người đang mở app cũng thấy popup, không cần mở lại app.
const POLL_MS = 30_000;

interface Announcement {
  badge: string;
  body: string;
  button_text: string;
  button_url: string;
  id: string;
  secondary_text: string;
  title: string;
}

interface LicenseState {
  plan?: "lifetime" | "timed";
  plan_name?: string;
  remaining_seconds: number | null;
  state: "licensed" | "trial" | "expired";
}

const clean = (url: string) => url.replace(/\/+$/, "");

// Tên gói của key dùng thử / trải nghiệm (apps/license_codec.py).
const TRIAL_PLANS = ["Dùng thử 7 ngày", "Trải nghiệm 10 ngày"];

/** Chỉ người đang dùng thử, dùng key thử/trải nghiệm hoặc đã hết hạn thấy popup; người đã mua gói thì không. */
const eligible = (s: LicenseState | null): boolean => {
  if (!s) {
    return false;
  }
  if (s.state === "trial" || s.state === "expired") {
    return true;
  }
  return (
    s.state === "licensed" &&
    s.plan === "timed" &&
    TRIAL_PLANS.includes(s.plan_name ?? "")
  );
};

// Dải phổ âm thanh trang trí ở đầu popup: chiều cao cố định, nhịp nhấp nhô bằng CSS.
const BARS = Array.from({ length: 44 }, (_, i) => ({
  id: `b${i}`,
  delay: -((i * 0.13) % 2.2),
  height: 8 + Math.abs(Math.sin(i * 0.55) * 34 + Math.sin(i * 1.3) * 14),
}));

export const AnnouncementPopup: React.FC<{
  apiUrl: string;
  /** Chưa kết nối xong backend, hoặc đang có hộp thoại khác (cập nhật): đợi. */
  waiting: boolean;
}> = ({ apiUrl, waiting }) => {
  const titleId = useId();
  const [item, setItem] = useState<Announcement | null>(null);
  // Id đã đóng trong lần chạy này: chặn hiện lại trước khi máy ghi nhận xong lệnh đóng.
  const closedIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (waiting) {
      return;
    }
    const controller = new AbortController();
    const base = clean(apiUrl);
    const check = async () => {
      try {
        const [annRes, licRes] = await Promise.all([
          fetch(`${base}/api/app/announcement`, { signal: controller.signal }),
          fetch(`${base}/api/license/status`, {
            signal: controller.signal,
          }).catch(() => null),
        ]);
        if (!annRes.ok) {
          return;
        }
        const ann: Announcement | null =
          (await annRes.json()).announcement ?? null;
        const lic: LicenseState | null = licRes?.ok
          ? await licRes.json()
          : null;
        if (
          ann &&
          (ann.title || ann.body) &&
          eligible(lic) &&
          !closedIds.current.has(ann.id)
        ) {
          // Nội dung đổi (id mới) thì thay luôn popup đang mở.
          setItem((prev) => (prev?.id === ann.id ? prev : ann));
        } else {
          setItem(null);
        }
      } catch {
        // mất mạng hoặc backend cũ: im lặng
      }
    };
    check();
    const timer = window.setInterval(check, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        check();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [apiUrl, waiting]);

  const close = useCallback(() => {
    const current = item;
    setItem(null);
    if (current) {
      closedIds.current.add(current.id);
      fetch(`${clean(apiUrl)}/api/app/announcement/dismiss`, {
        body: JSON.stringify({ id: current.id }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      }).catch(() => undefined);
    }
  }, [item, apiUrl]);

  useEffect(() => {
    if (!item) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, close]);

  if (!item || waiting) {
    return null;
  }
  return (
    <div
      className="announce-overlay"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
      role="presentation"
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="announce-dialog"
        role="dialog"
      >
        <div aria-hidden="true" className="announce-head">
          <div className="announce-eq">
            {BARS.map((b) => (
              <i
                key={b.id}
                style={{
                  animationDelay: `${b.delay.toFixed(2)}s`,
                  height: b.height,
                }}
              />
            ))}
          </div>
        </div>
        <button
          aria-label="Đóng"
          className="announce-close"
          onClick={close}
          type="button"
        >
          <X className="h-4 w-4" />
        </button>
        {item.badge && <span className="announce-badge">{item.badge}</span>}
        {item.title && (
          <h2 className="announce-title" id={titleId}>
            {item.title}
          </h2>
        )}
        {item.body && <p className="announce-body">{item.body}</p>}
        {(item.secondary_text || item.button_url) && (
          <div className="announce-actions">
            {item.secondary_text && (
              <button className="announce-later" onClick={close} type="button">
                {item.secondary_text}
              </button>
            )}
            {item.button_url && (
              <a
                className="announce-cta"
                href={item.button_url}
                onClick={close}
                rel="noreferrer"
                target="_blank"
              >
                {item.button_text || "Xem chi tiết"}
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
