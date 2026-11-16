#!/usr/bin/env bash
# Bấm đúp file này trên máy Mac để build Voice AI - Mr.Huỳnh ra file .dmg.
# Cần: macOS, kết nối Internet. Script tự kiểm tra và cài Homebrew/uv/Node nếu thiếu.
cd "$(dirname "$0")" || exit 1
set -e
echo "=== Build Voice AI - Mr.Huỳnh cho macOS ==="
if ! command -v brew >/dev/null 2>&1; then
    echo "[!] Chưa có Homebrew. Cài theo hướng dẫn tại https://brew.sh rồi chạy lại file này."
    read -r -p "Bấm Enter để đóng..." _; exit 1
fi
command -v uv   >/dev/null 2>&1 || { echo "[+] Cài uv...";   brew install uv; }
command -v node >/dev/null 2>&1 || { echo "[+] Cài Node...";  brew install node; }
chmod +x scripts/build_macos.sh
# Giao diện đã được build sẵn trong source nên bỏ qua Node nếu thư mục dist có sẵn.
if [[ -f app-desktop/voice-ai-app/dist/index.html ]]; then
    ./scripts/build_macos.sh --skip-frontend
else
    ./scripts/build_macos.sh
fi
echo
echo "XONG. File .dmg nằm trong thư mục dist/."
open dist
read -r -p "Bấm Enter để đóng..." _
