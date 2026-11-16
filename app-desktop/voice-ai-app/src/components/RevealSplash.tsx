import { useEffect } from "react";
import { splashUpdate } from "@/lib/splash";

/** Gắn vào màn hình nào hiện ra TRƯỚC khi giao diện chính nạp xong (điều khoản, hết hạn...):
 *  tắt màn hình khởi động trong suốt để người dùng thấy và bấm được. */
export const RevealSplash = () => {
  useEffect(() => {
    splashUpdate("", "ready", 1);
  }, []);
  return null;
};
