<div align="center">

<img src="assets/brand/logo.png" width="120" alt="Logo Voice AI - Mr.Huỳnh">

# Voice AI - Mr.Huỳnh

**Chuyển văn bản thành giọng nói tự nhiên ngay trên máy tính của bạn: tiếng Việt và hơn 30 ngôn ngữ khác.**

Không cần tài khoản · Không cần Internet sau khi cài · Văn bản và giọng nói không rời khỏi máy

Tác giả: [Mr.Huỳnh](https://mrhuynh.net)

</div>

---

## Tính năng

- **Giọng đọc tiếng Việt** nhiều vùng miền, âm thanh 48 kHz.
- **Nhân bản giọng nói**: thu micro 3 đến 8 giây hoặc nhập file MP3/WAV/M4A.
- **Giọng nước ngoài** (tải thêm khi cần): Supertonic 3 (31 ngôn ngữ) và Kokoro (giọng bản xứ).
- **Hội thoại / Podcast**: mỗi nhân vật một giọng, ghép thành một file âm thanh.
- **Lồng tiếng theo phụ đề**: nhập file `.srt`, giọng đọc khớp đúng mốc thời gian của video.
- **Tạo hàng loạt**, **đọc file PDF/DOCX**, **từ điển phát âm**, **lịch sử bản đã tạo**.
- **API cục bộ** tại `http://127.0.0.1:8001` để gọi từ script hoặc phần mềm khác (xem `docs/voice-ai-mrhuynh.md`).

## Giấy phép sử dụng (dùng thử và key)

- Lần đầu mở, app tự cho **dùng thử 3 ngày**. Hết hạn, app hiện màn hình kích hoạt với **Mã máy**; gửi Mã máy cho Mr.Huỳnh ([Zalo 0979 007 367](https://zalo.me/0979007367) hoặc [Telegram @mrhuynh1985](https://t.me/mrhuynh1985)) để nhận key vĩnh viễn rồi dán vào ô kích hoạt.
- Key chỉ chạy trên đúng máy đã đăng ký và không cần Internet.
- Mr.Huỳnh cấp key bằng công cụ riêng `cap_key.py` (thư mục `keygen-private`, **không** phát hành cho khách). App chỉ chứa khoá công khai nên không tự tạo được key.

## Cấu hình máy

| | Tối thiểu | Khuyến nghị |
|---|---|---|
| Hệ điều hành | Windows 10/11 64-bit, Ubuntu/Debian 64-bit, macOS 14 (chip Apple) | giống nhau |
| CPU | 4 nhân | 6 nhân trở lên |
| RAM | 8 GB | 16 GB trở lên |
| Ổ đĩa trống | 3 GB | 5 GB |
| Card đồ họa | Không bắt buộc | NVIDIA nếu hay tạo văn bản dài |

## Chạy từ mã nguồn trên Windows

1. Cài [uv](https://docs.astral.sh/uv/).
2. Giao diện đã được build sẵn trong `app-desktop\voice-ai-app\dist`. Chỉ khi bạn sửa giao diện mới cần cài [Node.js](https://nodejs.org) 20+ rồi chạy `npm ci` và `npm run build` trong thư mục `app-desktop\voice-ai-app`.
3. Bấm đúp **`run_desktop_app.bat`**. Lần đầu app tự cài thư viện và tải mô hình giọng nói (khoảng 312 MB) nên cần có mạng.
   - Máy có card NVIDIA: dùng `run_gpu.bat`.
   - Tắt app: `stop.bat`.

Chạy trực tiếp bằng lệnh:

```bash
uv sync --group desktop
uv run python -m apps.desktop_app
```

## Tạo file `.exe` (Windows)

Cách dễ nhất: bấm đúp **`BUILD-EXE.bat`** (cần cài [uv](https://docs.astral.sh/uv/) trước; chạy một lần, mất khoảng 10 đến 25 phút, cần có mạng). Script tự cài thư viện, tải sẵn mô hình giọng nói, rồi đóng gói. Kết quả:

- `dist\Voice-AI-MrHuynh\Voice-AI-MrHuynh.exe`: bấm đúp là chạy, không cần cài Python. Muốn gửi cho người khác, nén cả thư mục `dist\Voice-AI-MrHuynh` thành `.zip`.
- Nếu máy có [Inno Setup](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`), script tạo thêm file cài một file `dist\Voice-AI-MrHuynh-v*-win-x86_64.exe`.

Không có máy Windows? Đưa thư mục này lên một repo GitHub của bạn rồi chạy workflow **Build Windows exe** (tab Actions); file `.exe` nằm ở mục Artifacts.

Với Linux và macOS dùng `scripts/build_linux.sh` và `scripts/build_macos.sh` trên đúng hệ điều hành đó.

## Chạy trên máy chủ (không màn hình) bằng Docker

```bash
docker compose -f packaging/docker/compose.yaml up -d --build
```

Dữ liệu (mô hình, lịch sử, cài đặt, khóa API) nằm trong volume `voiceai-data`. Bản GPU dùng thêm `packaging/docker/compose.gpu.yaml`.

## API cho phần mềm khác

Sau khi mở app, tài liệu API tương tác ở `http://127.0.0.1:8001/docs`, tài liệu Markdown đầy đủ ở `http://127.0.0.1:8001/voice-ai-mrhuynh.md`. Có sẵn bộ Postman trong `docs/postman/`.

Cho phép máy khác trong mạng LAN gọi vào: bật trong **Cài đặt → Mạng**, app tạo khóa API bắt đầu bằng `voiceai_`.

## Dữ liệu lưu ở đâu

| Hệ điều hành | Thư mục |
|---|---|
| Windows | `%LOCALAPPDATA%\VoiceAIMrHuynh` |
| Linux | `~/VoiceAIMrHuynh` |
| macOS | `~/Library/Application Support/Voice AI MrHuynh` |

File nhật ký `voice-ai-mrhuynh.log` nằm cạnh app (hoặc trong thư mục dữ liệu). Khi gặp lỗi, đặt biến môi trường `VOICEAI_DEBUG=1` rồi mở lại app để xem chi tiết.

## Sử dụng có trách nhiệm

- Chỉ nhân bản giọng của chính bạn hoặc giọng được chủ giọng cho phép.
- Không giả mạo giọng người khác để lừa đảo, bôi nhọ hay gây hiểu lầm.
- Nội dung mô phỏng giọng người thật khi đăng công khai phải ghi rõ "giọng đọc được tạo bằng AI".
- Văn bản (sách, truyện, báo) phải là của bạn hoặc đã được phép sử dụng.

Chi tiết xem [DIEU-KHOAN.md](DIEU-KHOAN.md) và [PRIVACY.md](PRIVACY.md).

## Giấy phép

Mã nguồn theo giấy phép **Apache-2.0**, xem [LICENSE](LICENSE). Các thông báo bản quyền và thành phần bên thứ ba nằm trong [NOTICE](NOTICE) và [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md); hãy giữ các file này khi bạn phân phối lại.
