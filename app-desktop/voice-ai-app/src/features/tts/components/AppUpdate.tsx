import { AlertCircle, Download, Loader2, RefreshCw, X } from "lucide-react";
import type React from "react";
import { useEffect, useId, useRef, useState } from "react";
import logo from "../../../assets/logo.png";
import {
  type AppUpdateInfo,
  fetchUpdateInstall,
  launchUpdate,
  skipAppUpdate,
  startUpdateInstall,
  type UpdateInstallState,
} from "../api";

// Kiem tra ban moi: bao, va (khi version.json co sha256 + chu ky) tai bo cai da ky roi cai de.

/** Thanh bao "Da co ban moi" duoi thanh tab. Chi hien khi co ban moi hon. */
export const UpdateBanner: React.FC<{
  info: AppUpdateInfo | null;
  onDismiss: () => void;
}> = ({ info, onDismiss }) => {
  if (!info?.newer) {
    return null;
  }
  return (
    <div className="slide-in-from-top-2 mx-6 mt-3 flex animate-in items-center justify-between gap-3 rounded-xl border border-brand-500/30 bg-brand-500/10 p-3 text-brand-700 text-xs shadow-sm dark:text-brand-300">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <Download className="h-4 w-4 shrink-0" />
        <span>
          Đã có <strong>bản {info.latest}</strong> (bạn đang dùng bản{" "}
          {info.current}).
        </span>
        <a
          className="font-bold underline underline-offset-2 hover:text-brand-500"
          href={info.url}
          rel="noreferrer"
          target="_blank"
        >
          Xem thay đổi &amp; tải về
        </a>
      </div>
      <button
        className="shrink-0 rounded-lg p-1 transition-colors hover:bg-brand-500/20"
        onClick={onDismiss}
        title="Để sau"
        type="button"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

/** Hộp thoại "Có bản mới" giữa màn hình, hiện một lần cho mỗi bản. "Để sau" ghi
 *  nhớ bản đó ở máy chủ nên lần mở sau không bật lại (thanh báo nhỏ vẫn còn);
 *  nút X chỉ đóng trong phiên này. Chỉ mở trang tải, không tự tải/tự cài. */
export const UpdateDialog: React.FC<{
  apiUrl: string;
  info: AppUpdateInfo;
  onClose: () => void;
}> = ({ apiUrl, info, onClose }) => {
  const titleId = useId();
  const primaryRef = useRef<HTMLAnchorElement>(null);
  const [install, setInstall] = useState<UpdateInstallState | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const downloading = install?.state === "downloading";
  const busy = downloading || launching;

  const runInstall = async () => {
    setInstallError(null);
    try {
      setInstall(await startUpdateInstall(apiUrl));
    } catch (e) {
      setInstallError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    if (!downloading) {
      return;
    }
    const t = setInterval(async () => {
      try {
        setInstall(await fetchUpdateInstall(apiUrl));
      } catch {
        // mất kết nối tạm thời, thử lại ở nhịp sau
      }
    }, 1000);
    return () => clearInterval(t);
  }, [downloading, apiUrl]);

  useEffect(() => {
    if (install?.state === "error") {
      setInstallError(install.message);
    }
    if (install?.state === "ready" && !launching) {
      setLaunching(true);
      launchUpdate(apiUrl).catch((e) => {
        setLaunching(false);
        setInstallError(e instanceof Error ? e.message : String(e));
      });
    }
  }, [install, launching, apiUrl]);

  useEffect(() => {
    primaryRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, busy]);

  const handleLater = () => {
    if (info.latest) {
      skipAppUpdate(apiUrl, info.latest).catch(() => undefined);
    }
    onClose();
  };

  return (
    <div
      aria-labelledby={titleId}
      aria-modal="true"
      className="update-dialog-overlay fixed inset-0 z-[70]"
      role="dialog"
    >
      <div className="update-dialog fade-in-50 zoom-in-95 animate-in">
        <div className="flex items-start gap-3">
          <img
            alt=""
            className="h-12 w-12 shrink-0 rounded-xl"
            height={48}
            src={logo}
            width={48}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-bold text-base text-foreground" id={titleId}>
                Voice AI - Mr. Huỳnh
              </h2>
              <span className="update-dialog-badge">Cập nhật</span>
            </div>
            <p className="mt-0.5 font-mono text-muted-foreground text-xs">
              {info.current} → {info.latest}
            </p>
          </div>
          <button
            aria-label="Đóng"
            className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={onClose}
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-4 text-foreground/80 text-sm">
          Đã có bản <strong>{info.latest}</strong> với tính năng mới và sửa lỗi.
          Cài đè lên bản cũ, giọng đã nhân bản, các bản đã tạo và cài đặt được
          giữ nguyên.
        </p>
        {info.highlights && info.highlights.length > 0 && (
          <ul className="update-dialog-list">
            {info.highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}

        {(downloading || launching) && (
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-brand-500 transition-all"
                style={{
                  width: `${launching ? 100 : (install?.percent ?? 0)}%`,
                }}
              />
            </div>
            <p className="mt-1.5 flex items-center gap-1.5 text-muted-foreground text-xs">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {launching
                ? "Đang cài bản mới. App sẽ tự đóng và mở lại sau ít giây..."
                : install?.message || "Đang tải..."}
            </p>
          </div>
        )}
        {installError && (
          <p
            className="mt-3 flex items-start gap-1.5 text-rose-600 text-xs dark:text-rose-400"
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{installError} Bạn có thể bấm "Tải thủ công".</span>
          </p>
        )}
        {info.auto_install && !busy && (
          <p className="mt-3 text-muted-foreground text-xs">
            Hãy lưu công việc đang làm. App sẽ tự đóng và mở lại khi cài xong.
          </p>
        )}

        <div className="update-dialog-footer">
          <a
            className="font-medium text-foreground text-sm underline underline-offset-4 hover:text-brand-600"
            href={info.url}
            rel="noreferrer"
            target="_blank"
          >
            {info.auto_install ? "Tải thủ công" : "Có gì mới"}
          </a>
          <div className="flex gap-2">
            <button
              className="rounded-lg border border-border px-4 py-2 font-semibold text-foreground text-xs transition-colors hover:bg-secondary disabled:opacity-50"
              disabled={busy}
              onClick={handleLater}
              type="button"
            >
              Để sau
            </button>
            {info.auto_install ? (
              <button
                className="studio-primary inline-flex items-center gap-1.5 rounded-lg px-4 py-2 font-semibold text-xs"
                disabled={busy}
                onClick={runInstall}
                type="button"
              >
                {installError ? (
                  <RefreshCw className="h-3.5 w-3.5" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                {installError ? "Thử lại" : "Cập nhật ngay"}
              </button>
            ) : (
              <a
                className="studio-primary inline-flex items-center gap-1.5 rounded-lg px-4 py-2 font-semibold text-xs"
                href={info.url}
                onClick={onClose}
                ref={primaryRef}
                rel="noreferrer"
                target="_blank"
              >
                <Download className="h-3.5 w-3.5" />
                Tải bản mới
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

/** Ban nay khong co kho phat hanh de hoi, nen nut "Kiem tra cap nhat" duoc an. */
export const UpdateCheckButton: React.FC<{
  apiUrl: string;
  info: AppUpdateInfo | null;
  onChecked: (info: AppUpdateInfo) => void;
  variant?: "default" | "sidebar";
}> = () => null;

/** Phiên bản từ backend, dùng chung trạng thái cập nhật với Thông tin và Cài đặt. */
export const SidebarFooter: React.FC<{
  apiUrl: string;
  info: AppUpdateInfo | null;
  onChecked: (info: AppUpdateInfo) => void;
}> = ({ apiUrl, info, onChecked }) => (
  <footer className="studio-sidebar-footer">
    <div className="studio-sidebar-credit">
      <a
        className="studio-sidebar-version underline-offset-4 hover:underline"
        href="https://zalo.me/0979007367"
        rel="noopener noreferrer"
        target="_blank"
        title="Zalo Huỳnh Xuyên Sơn (mở tab mới)"
      >
        By. Huỳnh Xuyên Sơn
      </a>
    </div>
    <UpdateCheckButton
      apiUrl={apiUrl}
      info={info}
      onChecked={onChecked}
      variant="sidebar"
    />
  </footer>
);

/** Ban nay khong tu ket noi Internet de kiem tra cap nhat nen cong tac duoc an. */
export const UpdateCheckToggle: React.FC<{
  apiUrl: string;
  isOpen: boolean;
  onChecked?: (info: AppUpdateInfo) => void;
}> = () => null;
