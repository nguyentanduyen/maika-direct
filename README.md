# MAIKA Direct cho Home Assistant

[![Validate](https://github.com/nguyentanduyen/maika-direct/actions/workflows/validate.yml/badge.svg)](https://github.com/nguyentanduyen/maika-direct/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Custom integration **mã nguồn mở, miễn phí, không cần license key** để điều khiển loa
thông minh **OLLI MAIKA** từ Home Assistant. Integration đăng nhập bằng chính tài khoản
MAIKA của bạn và gọi thẳng cloud MAIKA – cùng các endpoint mà app MAIKA trên điện thoại
đang dùng. Không có máy chủ trung gian, không gửi dữ liệu cho bên thứ ba.

> ⚠️ Đây là dự án cộng đồng **không chính thức**, không liên quan tới OLLI Technology.
> MAIKA không công bố API công khai; endpoint có thể thay đổi bất cứ lúc nào. Xem
> [NOTICE.md](NOTICE.md).

**English summary:** Free, open-source Home Assistant integration for OLLI MAIKA smart
speakers. Talks directly to the MAIKA cloud with your own account — no licence server.
Media player, mic mute, restart, voice-command sensor/events, "send text to speaker",
TTS/URL casting and a sidebar management panel. API reference: [docs/API.md](docs/API.md).

---

## Tính năng

| Nhóm | Chi tiết |
|---|---|
| **Media player** | Âm lượng, tắt tiếng, phát/tạm dừng, bài trước/tiếp, phát URL MP3, TTS và file trong Media của HA |
| **Điều khiển** | Công tắc tắt micro, nút khởi động lại loa, nút làm mới |
| **Giọng nói → HA** | Cảm biến *Câu lệnh gần nhất*, *Phản hồi gần nhất*; event `maika_direct_voice_command` để viết automation |
| **HA → giọng nói** | Action `maika_direct.send_text`: loa xử lý câu chữ như vừa nghe bạn nói |
| **Cài đặt loa** | Tên, tên gọi, địa chỉ, độ nhạy từ đánh thức, kiểu phản hồi, giọng đọc |
| **Panel MAIKA** | Mục riêng trên sidebar: điều khiển, trò chuyện, phát TTS/URL, cài đặt loa, cấu hình tích hợp |
| **Thời gian thực** | Giữ kết nối luồng sự kiện cloud (`/connect`), tự kết nối lại |

Không triển khai lệnh **khôi phục cài đặt gốc** (`Reset`) để tránh mất dữ liệu loa.

## Yêu cầu

- Home Assistant **2025.6** trở lên (đã chạy trên 2026.10.1, bản Docker).
- Tài khoản MAIKA đăng nhập bằng **số điện thoại hoặc email + mật khẩu**. Tài khoản chỉ
  đăng nhập bằng Google cần đặt mật khẩu MAIKA trong app trước.
- Home Assistant có Internet. Muốn phát TTS/file từ HA lên loa thì loa phải truy cập được
  HA trong mạng LAN.

## Cài đặt

### Qua HACS (khuyên dùng)
1. **HACS → ⋮ → Custom repositories**, dán `https://github.com/nguyentanduyen/maika-direct`, loại **Integration**.
2. Tìm **MAIKA Direct** → **Download** → khởi động lại Home Assistant.

### Thủ công
Chép thư mục `custom_components/maika_direct` vào `<config>/custom_components/`, rồi khởi
động lại Home Assistant.

### Thêm tích hợp
**Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp → MAIKA Direct**, nhập số điện thoại
(hoặc email) và mật khẩu MAIKA. Mỗi loa trong tài khoản thành một thiết bị.

## Cấu hình sau khi cài

Mở **MAIKA** trên sidebar → khối **Cấu hình tích hợp** (hoặc nút *Cấu hình* của tích hợp):

| Tùy chọn | Ý nghĩa |
|---|---|
| **Địa chỉ Home Assistant cho loa** | URL LAN của HA, ví dụ `http://192.168.1.20:8123`. **Bắt buộc** nếu HA chạy Docker hoặc URL nội bộ là `localhost`, `homeassistant.local`… – loa không phân giải được các tên này. Chỉ URL trỏ về chính HA mới bị đổi, URL của máy chủ khác (Music Assistant, radio) giữ nguyên. |
| **Chu kỳ làm mới** | 15–3600 giây (mặc định 60) cho danh sách loa; trạng thái phát/âm lượng vẫn cập nhật trực tiếp qua luồng sự kiện. |

## Thực thể của mỗi loa

| Thực thể | Loại |
|---|---|
| `media_player.<loa>` | Media player |
| `switch.<loa>_microphone_mute` | Tắt/bật micro vật lý |
| `button.<loa>_restart` / `button.<loa>_refresh` | Khởi động lại loa / làm mới dữ liệu |
| `binary_sensor.<loa>_connectivity` | Trực tuyến |
| `sensor.<loa>_last_command` | Câu bạn nói gần nhất (thuộc tính `full_text`, `timestamp`) |
| `sensor.<loa>_last_response` | Câu loa trả lời gần nhất |
| `sensor.<loa>_firmware`, `sensor.<loa>_wi_fi` | Chẩn đoán |

`<loa>` lấy từ tên loa lúc thêm tích hợp (ví dụ serial `a0123456789`); tên hiển thị theo ngôn ngữ HA.

## Điều khiển nhà bằng giọng nói (Assist)

Bật **MAIKA → Cấu hình tích hợp → Chuyển câu nói với loa sang Assist**. Mỗi câu bạn nói với loa
(ví dụ *"Maika ơi, bật đèn hành lang"*) được gửi sang Assist tiếng Việt của Home Assistant; Assist
điều khiển thiết bị đã bật **Cài đặt → Trợ lý giọng nói → Chia sẻ**. Tuỳ chọn:

- **Từ mở đầu**: ví dụ `nhà ơi` → chỉ câu *"nhà ơi bật đèn cửa"* mới gửi sang Assist.
- **Đọc kết quả bằng TTS**: chọn một dịch vụ TTS để loa đọc câu trả lời của Assist.

Loa vẫn tự trả lời theo cách của MAIKA (có thể nói "chưa hiểu") vì câu lệnh cũng đi tới trợ lý
MAIKA; thiết bị vẫn được bật/tắt bởi Assist.

Không muốn dùng tuỳ chọn có sẵn? Automation tương đương:

```yaml
triggers:
  - trigger: event
    event_type: maika_direct_voice_command
actions:
  - action: conversation.process
    data:
      text: "{{ trigger.event.data.text }}"
      language: vi
```

## Ví dụ automation

**Nói với loa → bật đèn trong HA**

```yaml
automation:
  - alias: "MAIKA: bật đèn phòng khách"
    trigger:
      - platform: event
        event_type: maika_direct_voice_command
    condition:
      - "{{ 'bật đèn phòng khách' in trigger.event.data.text | lower }}"
    action:
      - action: light.turn_on
        target:
          entity_id: light.phong_khach
```

Loa vẫn tự trả lời theo cách của nó (có thể nói "chưa hiểu") vì câu lệnh cũng đi tới trợ
lý MAIKA – integration chỉ *nghe* song song.

**Bảo loa làm việc gì đó**

```yaml
action: maika_direct.send_text
data:
  entity_id: media_player.a0123456789
  text: "mở nhạc thư giãn"
```

**Đọc thông báo bằng TTS của Home Assistant**

```yaml
action: tts.speak
target:
  entity_id: tts.google_translate_vi_com
data:
  media_player_entity_id: media_player.a0123456789
  message: "Đến giờ ăn cơm rồi"
```

## Panel MAIKA

Panel nằm trong sidebar (chỉ tài khoản quản trị), không cần cài thêm card. Panel có:
điều khiển phát và âm lượng, micro, khởi động lại; **trò chuyện** (gõ câu gửi tới loa, xem
câu lệnh/phản hồi gần nhất); **phát lên loa** (TTS, URL MP3); **cài đặt loa** (lưu lên cloud
MAIKA); **cấu hình tích hợp**. Giao diện theo theme sáng/tối của HA, dùng được trên điện thoại.

Panel gọi các lệnh websocket `maika_direct/*` – xem [docs/API.md](docs/API.md#websocket-nội-bộ-của-integration).

## Dùng cùng Music Assistant

Media player MAIKA hỗ trợ `play_media`, nên [Music Assistant](https://www.music-assistant.io/)
có thể phát tới loa qua player provider **Home Assistant MediaPlayers** (radio, thư viện MP3,
YouTube Music/Spotify nếu có tài khoản). Loa phải truy cập được cổng luồng nhạc của Music
Assistant (mặc định `8097`) trong LAN. Tính năng này **thử nghiệm**.

## Giới hạn đã biết

- Cast âm thanh (`CommandHandOver`) đã chạy trên MK100B firmware 2.64 (TTS và MP3 qua HTTP/HTTPS).
  Loa nạp bài ở trạng thái tạm dừng, integration tự gửi lệnh phát tiếp sau ~3–6 giây. Phát lại
  **đúng URL cũ** sẽ tiếp tục từ vị trí đã dừng. Định dạng luôn khai báo `AUDIO_MPEG`.
- Không có lệnh *Stop* riêng – nút dừng = tạm dừng.
- Không có tua theo giây, không đổi playlist trên loa.
- Câu phản hồi của loa (`SpeechSynthesizer`) có thể không phải lúc nào cũng được cloud gửi về.
- Hoàn toàn phụ thuộc cloud MAIKA (`iot_class: cloud_push`).

## Khắc phục sự cố

- **Sai tài khoản/mật khẩu**: số điện thoại được tự đổi sang dạng `+84…`. Tài khoản Google
  cần đặt mật khẩu MAIKA.
- **TTS/nhạc từ HA không phát**: điền *Địa chỉ Home Assistant cho loa* bằng IP LAN; thử mở
  URL đó từ điện thoại trong cùng Wi-Fi.
- **Bật log chi tiết**:
  ```yaml
  logger:
    logs:
      custom_components.maika_direct: debug
  ```

## Phát triển

```bash
pip install aiohttp pytest
pytest tests/
```

Cấu trúc:

```
custom_components/maika_direct/
├── api.py            # client cloud MAIKA (REST + /stream + /connect)
├── coordinator.py    # polling REST + xử lý luồng sự kiện
├── media_player.py, switch.py, button.py, sensor.py, binary_sensor.py
├── config_flow.py    # đăng nhập, reauth, options
├── panel.py          # sidebar panel + websocket API
└── frontend/maika-direct-panel.js   # giao diện panel (JS thuần, không build)
```

## Ghi công

Giao thức cloud được ghi lại công khai trong
[docs/API_RESEARCH.md của trankhanhduy2929-beep/loa-maika-home-assistant](https://github.com/trankhanhduy2929-beep/loa-maika-home-assistant/blob/main/docs/API_RESEARCH.md)
(MIT). MAIKA Direct là bản viết lại độc lập, gọn hơn, không có cơ chế license.

## Giấy phép

[MIT](LICENSE). MAIKA, OLLI là nhãn hiệu của chủ sở hữu tương ứng.
