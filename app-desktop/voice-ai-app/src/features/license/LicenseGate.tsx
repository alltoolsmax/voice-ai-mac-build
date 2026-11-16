import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  ExternalLink,
  Hourglass,
  KeyRound,
  Loader2,
  Star,
  X,
} from "lucide-react";
import QRCode from "qrcode";
import type React from "react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import logo from "../../assets/logo.png";
import { AnnouncementPopup } from "../tts/components/AnnouncementPopup";

// Giấy phép: dùng thử 3 ngày, sau đó mua gói (quét QR, tự kích hoạt) hoặc nhập key thủ công
// (apps/license.py). Backend chặn API bằng 402; component này hiện thanh trạng thái và hộp thoại.

interface LicenseStatus {
  contact: {
    facebook: string;
    facebook_label: string;
    zalo: string;
    zalo_label: string;
  };
  expires_at?: number;
  machine_id: string;
  plan?: "lifetime" | "timed";
  plan_name?: string;
  reason?: string;
  remaining_seconds: number | null;
  state: "licensed" | "trial" | "expired";
}

// Số ngày của từng gói (để vẽ thanh còn lại); gói cộng dồn chỉ mang tính tham khảo.
const PLAN_TOTAL_DAYS: Record<string, number> = {
  "1 tháng": 30,
  "3 tháng": 90,
  "6 tháng": 180,
  "1 năm": 365,
  "Dùng thử 7 ngày": 7,
  "Trải nghiệm 10 ngày": 10,
};

interface Plan {
  code: string;
  days: number;
  name: string;
  price: number;
}

interface Order {
  amount: number;
  bank: { account: string; holder: string; name: string };
  code: string;
  content: string;
  expires_at: number;
  plan_name: string;
  qr_payload: string;
}

const money = (n: number) => `${n.toLocaleString("vi-VN")}đ`;

const apiBase = (): string => {
  if (
    !import.meta.env.DEV &&
    typeof window !== "undefined" &&
    window.location.origin &&
    !window.location.origin.startsWith("file:")
  ) {
    return window.location.origin;
  }
  return "http://127.0.0.1:8001";
};

const pad = (n: number) => String(n).padStart(2, "0");

export const formatRemaining = (seconds: number): string => {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) {
    return `${h} giờ ${m} phút`;
  }
  return `${m} phút ${pad(s % 60)} giây`;
};

const copyText = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
};

const REASONS: Record<string, string> = {
  clock:
    "Phát hiện đồng hồ máy bị chỉnh lùi. Vui lòng mua gói hoặc nhập key để tiếp tục.",
  plan_expired:
    "Gói của bạn đã hết hạn. Chọn gói để gia hạn (thời gian được cộng thêm).",
  tamper:
    "Dữ liệu dùng thử bị thay đổi. Vui lòng mua gói hoặc nhập key để tiếp tục.",
};

const ContactLinks: React.FC<{ contact: LicenseStatus["contact"] }> = ({
  contact,
}) => (
  <div className="relative flex w-full gap-2">
    <a
      className="flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl bg-[#0068ff] px-2 py-2.5 font-bold text-white text-xs hover:opacity-90"
      href={contact.zalo}
      rel="noreferrer"
      target="_blank"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {contact.zalo_label}
    </a>
    <a
      className="flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl bg-[#1877f2] px-2 py-2.5 font-bold text-white text-xs hover:opacity-90"
      href={contact.facebook}
      rel="noreferrer"
      target="_blank"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {contact.facebook_label}
    </a>
  </div>
);

const QrImage: React.FC<{ payload: string }> = ({ payload }) => {
  const [src, setSrc] = useState("");
  useEffect(() => {
    QRCode.toDataURL(payload, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 360,
    }).then(setSrc, () => setSrc(""));
  }, [payload]);
  return src ? (
    <img
      alt="Mã QR thanh toán"
      className="h-52 w-52 rounded-xl bg-white p-1.5"
      height={208}
      src={src}
      width={208}
    />
  ) : (
    <div className="h-52 w-52 rounded-xl bg-muted" />
  );
};

const CopyRow: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => {
  const [done, setDone] = useState(false);
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      <button
        className="inline-flex items-center gap-1 font-mono font-semibold text-foreground text-xs hover:text-brand-600"
        onClick={async () => {
          if (await copyText(value)) {
            setDone(true);
            setTimeout(() => setDone(false), 1200);
          }
        }}
        title="Bấm để chép"
        type="button"
      >
        {value}
        {done ? (
          <CheckCircle2 className="h-3 w-3 text-emerald-600" />
        ) : (
          <Copy className="h-3 w-3 opacity-60" />
        )}
      </button>
    </div>
  );
};

// Màn hình thanh toán: hiện QR, hỏi máy chủ mỗi 3 giây; backend tự kích hoạt khi đã thanh toán.
const PayView: React.FC<{
  onBack: () => void;
  onDone: () => void;
  order: Order;
}> = ({ order, onBack, onDone }) => {
  const [state, setState] = useState<
    "pending" | "activated" | "expired" | "error"
  >("pending");
  const [message, setMessage] = useState("");
  const [left, setLeft] = useState(() =>
    Math.max(0, order.expires_at - Math.floor(Date.now() / 1000))
  );

  useEffect(() => {
    if (state !== "pending") {
      return;
    }
    let stop = false;
    const tick = async () => {
      try {
        const res = await fetch(
          `${apiBase()}/api/license/order/${order.code}`,
          { cache: "no-store" }
        );
        const data = await res.json().catch(() => ({}));
        if (stop || !res.ok) {
          return;
        }
        if (data.status === "activated") {
          setMessage(data.message || "Đã kích hoạt.");
          setState("activated");
        } else if (data.status === "expired") {
          setState("expired");
        } else if (data.status === "error") {
          setMessage(
            data.message || "Không kích hoạt được. Vui lòng liên hệ Mr.Huỳnh."
          );
          setState("error");
        }
      } catch {
        // mất mạng thoáng qua: thử lại ở lần sau
      }
    };
    const poll = setInterval(tick, 3000);
    const clock = setInterval(
      () =>
        setLeft(Math.max(0, order.expires_at - Math.floor(Date.now() / 1000))),
      1000
    );
    return () => {
      stop = true;
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [order.code, order.expires_at, state]);

  if (state === "activated") {
    return (
      <div className="relative flex w-full flex-col items-center gap-3 py-4">
        <CheckCircle2 className="h-14 w-14 text-emerald-500" />
        <p className="font-bold text-foreground text-lg">
          Thanh toán thành công
        </p>
        <p className="text-muted-foreground text-sm">{message}</p>
        <button
          className="mt-2 rounded-xl bg-gradient-to-r from-brand-700 to-brand-500 px-8 py-3 font-bold text-sm text-white"
          onClick={onDone}
          type="button"
        >
          Bắt đầu sử dụng
        </button>
      </div>
    );
  }

  const mm = pad(Math.floor(left / 60));
  const ss = pad(left % 60);
  return (
    <div className="relative flex w-full flex-col items-center gap-2">
      <p className="font-bold text-foreground text-sm">
        {order.plan_name} · {money(order.amount)}
      </p>
      {state === "pending" && <QrImage payload={order.qr_payload} />}
      <div className="w-full rounded-xl border border-border/80 bg-muted/40 px-3 py-1.5 text-left">
        <CopyRow label="Ngân hàng" value={order.bank.name} />
        <CopyRow label="Số tài khoản" value={order.bank.account} />
        <div className="flex items-center justify-between gap-2 py-1">
          <span className="text-muted-foreground text-xs">Chủ tài khoản</span>
          <span className="font-semibold text-foreground text-xs">
            {order.bank.holder}
          </span>
        </div>
        <CopyRow label="Số tiền" value={String(order.amount)} />
        <CopyRow label="Nội dung" value={order.content} />
      </div>
      {state === "pending" && (
        <p className="flex items-center gap-1.5 text-muted-foreground text-xs">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Đang chờ thanh toán… ({mm}:{ss}). Giữ nguyên nội dung chuyển khoản để
          tự kích hoạt.
        </p>
      )}
      {state === "expired" && (
        <p className="font-medium text-rose-600 text-xs">
          Đơn đã hết hạn. Hãy tạo đơn mới.
        </p>
      )}
      {state === "error" && (
        <p className="font-medium text-rose-600 text-xs">{message}</p>
      )}
      <button
        className="mt-1 inline-flex items-center gap-1 text-muted-foreground text-xs hover:text-foreground"
        onClick={onBack}
        type="button"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Chọn gói khác
      </button>
    </div>
  );
};

const ActivationCard: React.FC<{
  onActivated: () => void;
  onClose?: () => void;
  status: LicenseStatus;
}> = ({ status, onActivated, onClose }) => {
  const [view, setView] = useState<"plans" | "pay" | "key">("plans");
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [order, setOrder] = useState<Order | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const expired = status.state === "expired";

  useEffect(() => {
    let alive = true;
    fetch(`${apiBase()}/api/license/plans`)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error("offline");
        }
        const data = await res.json();
        if (alive) {
          setPlans(data.plans);
        }
      })
      .catch(() => {
        if (alive) {
          setOffline(true);
          setView("key");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const buy = async (plan: Plan) => {
    if (busy) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${apiBase()}/api/license/order`, {
        body: JSON.stringify({ plan: plan.code }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail || "Không tạo được đơn hàng.");
        if (res.status === 503) {
          setOffline(true);
          setView("key");
        }
        return;
      }
      setOrder(data);
      setView("pay");
    } catch {
      setError("Không kết nối được máy chủ. Hãy nhập key thủ công.");
      setView("key");
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    if (!key.trim() || busy) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${apiBase()}/api/license/activate`, {
        body: JSON.stringify({ key: key.trim() }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail || "Key không hợp lệ.");
        return;
      }
      onActivated();
    } catch {
      setError("Không kết nối được máy chủ. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  };

  const title =
    view === "pay"
      ? "Quét mã QR để thanh toán"
      : view === "key"
        ? "Nhập key kích hoạt"
        : expired
          ? (status.reason && REASONS[status.reason]) ||
            "Thời gian dùng thử 3 ngày đã kết thúc. Chọn gói để tiếp tục."
          : status.plan === "timed"
            ? "Đổi gói / Gia hạn: thời gian mua thêm được cộng dồn vào thời gian còn lại, không mất ngày."
            : "Chọn gói sử dụng. Thanh toán xong ứng dụng tự kích hoạt.";

  return (
    <div className="fixed inset-0 z-[100] flex select-none items-center justify-center bg-background/90 px-4 backdrop-blur-xl">
      <div
        className={`relative flex max-h-[96vh] w-full ${view === "plans" ? "max-w-5xl" : "max-w-lg"} flex-col items-center overflow-y-auto overflow-x-hidden rounded-3xl border border-border/80 bg-card p-7 text-center shadow-2xl`}
      >
        <div className="pointer-events-none absolute -top-20 -left-20 h-48 w-48 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -right-20 -bottom-20 h-48 w-48 rounded-full bg-cyan-500/20 blur-3xl" />
        {onClose && (
          <button
            aria-label="Đóng"
            className="absolute top-4 right-4 rounded-full p-1.5 text-muted-foreground hover:bg-muted"
            onClick={onClose}
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        )}
        <img
          alt="Voice AI - Mr.Huỳnh"
          className="relative mb-3 h-16 w-16 rounded-2xl shadow-md"
          height={64}
          src={logo}
          width={64}
        />
        <h2 className="relative mb-1 flex items-center gap-2 font-bold text-foreground text-xl tracking-tight">
          <span>Voice AI - Mr. Huỳnh</span>
        </h2>
        <p className="relative mb-3 text-muted-foreground text-xs">{title}</p>
        {view === "plans" &&
          status.state === "licensed" &&
          status.plan === "timed" &&
          status.plan_name && (
            <div className="relative mb-3 inline-flex flex-wrap items-center justify-center gap-x-3 rounded-2xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-emerald-800 text-sm dark:border-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200">
              <b>✓ Đang dùng: {status.plan_name}</b>
              <span>
                còn {Math.ceil((status.remaining_seconds ?? 0) / 86_400)} ngày
                {status.expires_at
                  ? ` (đến ${new Date(status.expires_at * 1000).toLocaleDateString("vi-VN")})`
                  : ""}
              </span>
            </div>
          )}

        {view === "plans" && (
          <div className="relative mb-2 flex w-full flex-col gap-4">
            {!plans && (
              <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
            )}
            <div className="grid w-full grid-cols-2 gap-4 pt-3 md:grid-cols-3 lg:grid-cols-5">
              {plans?.map((plan) => {
                const life = plan.days <= 0;
                const popular = !life && plan.days >= 365;
                const perMonth =
                  !life && plan.days > 0
                    ? Math.round(plan.price / (plan.days / 30))
                    : 0;
                const base = plans.find((p) => p.days > 0 && p.days <= 31);
                const save =
                  base && !life && plan.days > 31
                    ? Math.round(
                        (1 - plan.price / (base.price * (plan.days / 30))) * 100
                      )
                    : 0;
                const current =
                  status.state === "licensed" &&
                  status.plan === "timed" &&
                  status.plan_name === plan.name;
                const tone = current
                  ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10"
                  : life
                    ? "border-amber-500 bg-gradient-to-b from-amber-50 to-amber-100 dark:from-amber-500/10 dark:to-amber-500/20"
                    : popular
                      ? "border-brand-600 bg-brand-500/10 shadow-brand-500/20 shadow-lg"
                      : "border-border bg-muted/40";
                const btn = life
                  ? "bg-gradient-to-r from-amber-500 to-orange-600 shadow-orange-500/40"
                  : "bg-brand-600 shadow-brand-500/40 hover:bg-brand-700";
                return (
                  <div
                    className={`relative flex flex-col items-center gap-1.5 rounded-2xl border-2 px-3 pt-6 pb-4 ${tone}`}
                    key={plan.code}
                  >
                    {current && (
                      <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-emerald-600 px-3 py-0.5 font-extrabold text-[11px] text-white">
                        ĐANG DÙNG
                      </span>
                    )}
                    {!current && (life || popular) && (
                      <span
                        className={`absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-3 py-0.5 font-extrabold text-[11px] text-white ${
                          life ? "bg-amber-600" : "bg-brand-600"
                        }`}
                      >
                        {life ? "TRỌN ĐỜI" : "PHỔ BIẾN NHẤT"}
                      </span>
                    )}
                    <span className="font-bold text-base text-foreground/80">
                      {plan.name}
                    </span>
                    <span
                      className={`font-extrabold text-3xl tracking-tight ${
                        life
                          ? "text-amber-700 dark:text-amber-400"
                          : "text-brand-600 dark:text-brand-400"
                      }`}
                    >
                      {plan.price.toLocaleString("vi-VN")}
                      <small className="text-base">đ</small>
                    </span>
                    <span className="min-h-[18px] text-muted-foreground text-xs">
                      {life
                        ? "Trả một lần, dùng mãi"
                        : `≈ ${perMonth.toLocaleString("vi-VN")}đ / tháng`}
                    </span>
                    <span className="mb-2 flex h-[24px] items-center">
                      {(save > 0 || life) && (
                        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-bold text-[11px] text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                          {life ? "Không cần gia hạn" : `Tiết kiệm ${save}%`}
                        </span>
                      )}
                    </span>
                    <span className="mb-1 text-foreground/70 text-xs">
                      Dùng đủ tính năng
                    </span>
                    <button
                      className={`mt-auto w-full rounded-xl py-3 font-extrabold text-sm text-white shadow-md transition active:scale-95 disabled:opacity-50 ${btn}`}
                      disabled={busy}
                      onClick={() => buy(plan)}
                      type="button"
                    >
                      {current ? "Gia hạn thêm" : "Mua gói này"}
                    </button>
                  </div>
                );
              })}
            </div>
            {error && (
              <p className="font-medium text-rose-600 text-xs">{error}</p>
            )}
            <button
              className="inline-flex items-center justify-center gap-1.5 text-muted-foreground text-xs hover:text-foreground"
              onClick={() => {
                setError("");
                setView("key");
              }}
              type="button"
            >
              <KeyRound className="h-3.5 w-3.5" />
              Đã có key? Nhập key thủ công
            </button>
          </div>
        )}

        {view === "pay" && order && (
          <PayView
            onBack={() => {
              setOrder(null);
              setView("plans");
            }}
            onDone={onActivated}
            order={order}
          />
        )}

        {view === "key" && (
          <>
            {offline && (
              <p className="relative mb-3 rounded-xl bg-amber-500/10 px-3 py-2 text-amber-700 text-xs dark:text-amber-300">
                Không kết nối được máy chủ thanh toán. Bạn vẫn có thể kích hoạt
                bằng key thủ công (liên hệ Mr.Huỳnh).
              </p>
            )}
            <div className="relative mb-3 w-full rounded-2xl border border-border/80 bg-muted/40 p-3 text-left">
              <div className="mb-1.5 font-bold text-[12px] text-brand-700 dark:text-brand-400">
                1. Mã máy của bạn (gửi cho Mr.Huỳnh để nhận key)
              </div>
              <div className="flex items-center justify-between gap-2">
                <code className="select-text font-mono text-base text-foreground">
                  {status.machine_id}
                </code>
                <button
                  className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-1.5 font-semibold text-white text-xs hover:bg-brand-700"
                  onClick={async () => {
                    if (await copyText(status.machine_id)) {
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }
                  }}
                  type="button"
                >
                  {copied ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  {copied ? "Đã chép" : "Sao chép"}
                </button>
              </div>
            </div>
            <div className="relative mb-3 w-full rounded-2xl border border-border/80 bg-muted/40 p-3 text-left">
              <label
                className="mb-1.5 block font-bold text-[12px] text-brand-700 dark:text-brand-400"
                htmlFor="license-key"
              >
                2. Nhập key kích hoạt
              </label>
              <textarea
                autoComplete="off"
                className="h-16 w-full select-text resize-none rounded-xl border-2 border-brand-500/60 bg-background p-2.5 font-mono text-foreground text-xs outline-none focus:border-brand-500"
                id="license-key"
                onChange={(e) => setKey(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    activate();
                  }
                }}
                placeholder="Dán key vào đây (bắt đầu bằng MH1-...)"
                spellCheck={false}
                value={key}
              />
              {error && (
                <p className="mt-1.5 font-medium text-rose-600 text-xs">
                  {error}
                </p>
              )}
            </div>
            <button
              className="relative mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-700 to-brand-500 py-3 font-bold text-sm text-white shadow-md transition hover:opacity-95 disabled:opacity-50"
              disabled={busy || !key.trim()}
              onClick={activate}
              type="button"
            >
              <KeyRound className="h-4 w-4" />
              {busy ? "Đang kiểm tra..." : "Kích hoạt"}
            </button>
            {!offline && (
              <button
                className="relative mb-3 inline-flex items-center gap-1 text-muted-foreground text-xs hover:text-foreground"
                onClick={() => {
                  setError("");
                  setView("plans");
                }}
                type="button"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Quay lại chọn gói
              </button>
            )}
          </>
        )}

        <p className="relative mb-2 text-muted-foreground text-xs">
          Cần hỗ trợ? Liên hệ
        </p>
        <ContactLinks contact={status.contact} />
      </div>
    </div>
  );
};

export const LicenseGate: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [phase, setPhase] = useState<"checking" | "ready" | "unreachable">(
    "checking"
  );
  const [showCard, setShowCard] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const deadline = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/api/license/status`, {
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(String(res.status));
      }
      const data: LicenseStatus = await res.json();
      deadline.current =
        data.remaining_seconds == null
          ? null
          : Date.now() + data.remaining_seconds * 1000;
      setStatus(data);
      setPhase("ready");
    } catch {
      // Backend chưa lên / bản cũ không có API giấy phép: để app tự xử lý màn hình chờ.
      setPhase((p) => (p === "ready" ? p : "unreachable"));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, phase === "unreachable" ? 2000 : 20_000);
    return () => clearInterval(id);
  }, [refresh, phase]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const remaining =
    deadline.current == null
      ? null
      : Math.max(0, (deadline.current - now) / 1000);

  useEffect(() => {
    if (status && status.state !== "expired" && remaining === 0) {
      refresh();
    }
  }, [status?.state, remaining, refresh]);

  // Có API nào trả 402 (hết hạn giữa chừng) thì cập nhật ngay.
  useEffect(() => {
    const original = window.fetch;
    window.fetch = async (...args) => {
      const res = await original(...args);
      if (res.status === 402) {
        refresh();
      }
      return res;
    };
    return () => {
      window.fetch = original;
    };
  }, [refresh]);

  // Hết hạn thì app chính không được dựng nên không ai gỡ màn hình khởi động (index.html).
  const isExpired = phase === "ready" && !!status && status.state === "expired";
  useEffect(() => {
    if (isExpired) {
      document.getElementById("bootstrap-screen")?.remove();
    }
  }, [isExpired]);

  if (phase === "checking") {
    return <div className="fixed inset-0 bg-background" />;
  }
  if (phase === "unreachable" || !status) {
    return <>{children}</>;
  }

  const expired =
    status.state === "expired" ||
    (status.state !== "licensed" && remaining === 0);
  if (expired) {
    return (
      <div className="fixed inset-0 bg-background">
        <ActivationCard
          onActivated={refresh}
          status={{ ...status, state: "expired" }}
        />
        {/* Người hết hạn dùng thử vẫn thấy popup thông báo (khung chính không được dựng nên phải gắn ở đây). */}
        <AnnouncementPopup apiUrl={apiBase()} waiting={false} />
      </div>
    );
  }

  const isTrial = status.state === "trial";
  const isLife = status.plan === "lifetime";
  const daysLeft = Math.ceil((remaining ?? 0) / 86_400);
  const soon = !(isTrial || isLife) && daysLeft <= 7;
  const totalDays = PLAN_TOTAL_DAYS[status.plan_name ?? ""];
  const pct = totalDays
    ? Math.max(4, Math.min(100, Math.round((daysLeft / totalDays) * 100)))
    : 0;
  const tone = isLife
    ? "border-amber-300 bg-gradient-to-r from-amber-50 to-amber-100 text-amber-900 dark:border-amber-700/60 dark:from-amber-950/60 dark:to-amber-900/40 dark:text-amber-200"
    : soon
      ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-200"
      : "border-emerald-300/70 bg-emerald-50 text-emerald-800 dark:border-emerald-800/60 dark:bg-emerald-950/60 dark:text-emerald-200";
  return (
    <div className="license-wrap fixed inset-0 flex flex-col">
      <div
        className={`flex shrink-0 items-center justify-between gap-3 border-b px-4 py-1.5 text-xs ${tone}`}
      >
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
          {isLife ? (
            <Star className="h-3.5 w-3.5" />
          ) : (
            <Hourglass className="h-3.5 w-3.5" />
          )}
          {isTrial ? (
            <>
              <b>Dùng thử:</b> còn {formatRemaining(remaining ?? 0)}. Hết hạn
              cần mua gói để tiếp tục.
            </>
          ) : isLife ? (
            <>
              <b>Đang dùng:</b>
              <span className="rounded-full bg-white/80 px-2 py-0.5 font-bold dark:bg-white/10">
                Vĩnh viễn
              </span>
              Bản quyền không giới hạn thời gian. Cảm ơn bạn đã ủng hộ!
            </>
          ) : (
            <>
              <b>Đang dùng:</b>
              {status.plan_name && (
                <span className="rounded-full bg-white/80 px-2 py-0.5 font-bold dark:bg-white/10">
                  {status.plan_name}
                </span>
              )}
              {soon ? `chỉ còn ${daysLeft} ngày` : `còn ${daysLeft} ngày`}
              {status.expires_at
                ? ` · hết hạn ${new Date(status.expires_at * 1000).toLocaleDateString("vi-VN")}`
                : ""}
              {pct > 0 && (
                <span className="hidden h-1.5 w-32 overflow-hidden rounded-full bg-black/10 sm:inline-block">
                  <i
                    className={`block h-full rounded-full ${soon ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${pct}%` }}
                  />
                </span>
              )}
            </>
          )}
        </span>
        {!isLife && (
          <button
            className={
              isTrial || soon
                ? "shrink-0 rounded-full bg-brand-600 px-3 py-1 font-semibold text-white hover:bg-brand-700"
                : "shrink-0 rounded-full border-[1.5px] border-brand-600 bg-white px-3 py-1 font-semibold text-brand-700 hover:bg-brand-50 dark:bg-transparent dark:text-brand-300"
            }
            onClick={() => setShowCard(true)}
            type="button"
          >
            {isTrial ? "Mua gói / Nhập key" : soon ? "Gia hạn ngay" : "Đổi gói"}
          </button>
        )}
      </div>
      <div className="license-body relative min-h-0 flex-1">{children}</div>
      {showCard && (
        <ActivationCard
          onActivated={() => {
            setShowCard(false);
            refresh();
          }}
          onClose={() => setShowCard(false)}
          status={status}
        />
      )}
    </div>
  );
};
