# Changelog

## 0.3.1 – 2026-10-16
- **Phát URL/TTS đã kiểm chứng trên loa thật** (MK100B, firmware 2.64): sau `CommandHandOver` loa
  nạp bài ở trạng thái *paused*; integration tự đọc lại trạng thái và gửi `ResumeCommandIssued`.
- Đổi host cho mọi URL trỏ về cổng của Home Assistant (kể cả IP bridge Docker/OrbStack như
  `192.168.97.x`) sang *Địa chỉ Home Assistant cho loa*.
- Đăng ký thêm `Conversation/StartListening` loại `media_control`.
- Log debug: in khung `/connect` và phản hồi `/stream` (bật `custom_components.maika_direct: debug`).

## 0.3.0 – 2026-10-16
- Panel **MAIKA** trên sidebar: điều khiển, trò chuyện, phát TTS/URL, cài đặt loa, cấu hình tích hợp.
- Websocket API `maika_direct/*` cho panel.
- Đọc/ghi cài đặt loa (tên, tên gọi, địa chỉ, độ nhạy, phản hồi, giọng đọc) và danh sách giọng.
- Chỉ đổi host cho URL trỏ về chính Home Assistant; giữ nguyên URL của máy chủ LAN khác
  (Music Assistant, radio…). Sửa lỗi mạng dải `172.16.x` bị coi là Docker.
- Hiển thị tên gọi thay cho serial khi loa chưa đặt tên.

## 0.1.0 – 2026-10-16
- Bản đầu: đăng nhập SĐT/email, media player, tắt micro, khởi động lại, sensor câu lệnh/phản hồi,
  event `maika_direct_voice_command`, action `maika_direct.send_text`, luồng `/connect` thời gian thực.
