/** Màn hình khởi động trong suốt của bản Windows (cửa sổ riêng, do Python vẽ).
 *  Giao diện chỉ báo tiến độ qua pywebview; ở trình duyệt/Mac/Linux các hàm này không làm gì. */
type SplashApi = {
  splash_update?: (
    message: string,
    status: string,
    progress: number
  ) => Promise<boolean> | boolean;
};

const getApi = (): SplashApi | undefined =>
  // biome-ignore lint/suspicious/noExplicitAny: API do pywebview gắn vào window
  (window as any).pywebview?.api;

/** Trả true nếu màn hình khởi động trong suốt đang lo phần "đang tải" (khi đó đừng vẽ màn hình tải của web). */
export async function splashUpdate(
  message: string,
  status: "starting" | "downloading" | "ready" | "failed",
  progress: number
): Promise<boolean> {
  const api = getApi();
  if (typeof api?.splash_update !== "function") {
    return false;
  }
  try {
    return Boolean(await api.splash_update(message, status, progress));
  } catch {
    return false;
  }
}
