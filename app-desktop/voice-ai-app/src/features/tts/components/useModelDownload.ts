import { useCallback, useEffect, useRef, useState } from "react";
import { fetchDownloadStatus, startModelDownload } from "../api";
import type { DownloadState } from "../types";

/** Tải một mô hình rồi theo dõi tiến trình (dùng chung cho Thiết kế giọng và Mô hình). */
export function useModelDownload(apiUrl: string, onFinished?: () => void) {
  const [state, setState] = useState<DownloadState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(() => {
    stop();
    timer.current = setInterval(async () => {
      try {
        const s = await fetchDownloadStatus(apiUrl);
        setState(s);
        if (
          s.state === "ready" ||
          s.state === "error" ||
          s.state === "cancelled" ||
          s.state === "idle"
        ) {
          stop();
          if (s.state === "error") {
            setError(s.message || "Tải mô hình bị lỗi.");
          }
          if (s.state === "ready") {
            finished.current?.();
          }
        }
      } catch {
        // mất kết nối tạm thời: thử lại ở lần sau
      }
    }, 1500);
  }, [apiUrl, stop]);

  useEffect(() => stop, [stop]);

  const start = useCallback(
    async (modelId: string) => {
      setError(null);
      try {
        await startModelDownload(apiUrl, modelId, true);
        setState({
          current_file: "",
          done_bytes: 0,
          message: "Đang bắt đầu...",
          model_id: modelId,
          percent: 0,
          state: "downloading",
          total_bytes: 0,
        });
        poll();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [apiUrl, poll]
  );

  const busy = state?.state === "downloading" || state?.state === "applying";
  return { busy, error, start, state };
}
