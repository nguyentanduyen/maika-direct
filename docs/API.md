# Tài liệu API MAIKA Direct

Tài liệu này mô tả **mọi lời gọi mạng** mà MAIKA Direct thực hiện, và API websocket nội bộ
mà panel dùng. Không có SDK chính thức: MAIKA không công bố API. Các endpoint dưới đây là
những gì app Android **MAIKA Virtual Assistant 3.2.3** (`olli.ai.com.maika`) gọi, được ghi
lại công khai trong
[API_RESEARCH.md](https://github.com/trankhanhduy2929-beep/loa-maika-home-assistant/blob/main/docs/API_RESEARCH.md).
Integration chỉ dùng `aiohttp` (session dùng chung của Home Assistant).

> Endpoint không có cam kết ổn định. Khi app MAIKA cập nhật, header hoặc JSON có thể đổi.

## Mục lục
- [Tổng quan máy chủ](#tổng-quan-máy-chủ)
- [Header chung](#header-chung)
- [Xác thực](#xác-thực)
- [REST – users.iviet.com](#rest--usersivietcom)
- [Gửi lệnh – POST /stream](#gửi-lệnh--post-stream)
- [Luồng sự kiện – GET /connect](#luồng-sự-kiện--get-connect)
- [Danh sách lệnh](#danh-sách-lệnh)
- [Websocket nội bộ của integration](#websocket-nội-bộ-của-integration)
- [Action và event của Home Assistant](#action-và-event-của-home-assistant)

## Tổng quan máy chủ

| Máy chủ | Vai trò | Dùng bởi MAIKA Direct |
|---|---|---|
| `https://users.iviet.com` | Đăng nhập, danh sách/chi tiết loa, cài đặt, giọng đọc | ✅ |
| `https://chatbot.iviet.com` | Gửi lệnh (`/stream`) và nhận sự kiện (`/connect`) | ✅ |
| `https://smarthome.iviet.com` | Liên kết nhà thông minh của app | ❌ |
| `https://content-gateway.maika.ai` | Chat/TTS xem trước trong app | ❌ |
| `https://core.ocs.iviet.com/v1/graphql` | Kho nội dung (GraphQL) | ❌ (chưa dùng) |

## Header chung

Mọi request gửi kèm:

| Header | Giá trị |
|---|---|
| `device-type` | `android` |
| `version-info` | `3.2.3` |
| `timezone` | `Asia/Ho_Chi_Minh` |
| `language-code` | `vi-VN` |

**Hai kiểu `Authorization` khác nhau – dùng sai sẽ bị 401:**

| Máy chủ | Header |
|---|---|
| `users.iviet.com` | `Authorization: Bearer <access_token>` |
| `chatbot.iviet.com` | `Authorization: <access_token>` (không có `Bearer`) |

## Xác thực

### Số điện thoại
```http
POST https://users.iviet.com/v1/auth/otp/login
Content-Type: application/json

{"phone_number": "+84912345678", "password": "<mật khẩu>"}
```
Số điện thoại được chuẩn hoá về dạng `+84…` (`0912…`, `84912…`, `0084912…` đều được).

### Email
```http
POST https://users.iviet.com/v1/auth/login
Content-Type: application/json

{"device_id": "<client_id>", "email": "ban@example.com", "password": "<mật khẩu MAIKA>"}
```

### Phản hồi
```json
{"data": {"access_token": "…", "refresh_token": "…", "id": 1001, "expire_time": 86400}}
```
- `id` là **user id**, dùng cho header `user-id` của `/stream`.
- Integration chỉ giữ `access_token` trong bộ nhớ, **không lưu refresh token**. Hết hạn
  hoặc gặp 401 thì đăng nhập lại bằng mật khẩu (thử lại tối đa 1 lần mỗi request).
- `client_id` và `session_id` là UUID sinh một lần khi thêm tích hợp, lưu trong config entry.

## REST – users.iviet.com

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/v1/user-device?type=speaker&page=1&limit=100&organization_code=MAIKA` | Danh sách loa |
| `GET` | `/v1/user-device/{id}` | Chi tiết một loa |
| `PUT` | `/v1/user-device/{id}` | Cập nhật cài đặt |
| `GET` | `/v1/user/tts_speaker_voices` | Danh sách giọng đọc |

`{id}` là **id nội bộ** (số) trong bản ghi loa; `device_id` là **serial** loa (ví dụ
`A0123456789`) – serial mới là định danh dùng cho mọi lệnh.

### Bản ghi loa (rút gọn)
```json
{
  "id": 12345,
  "device_id": "A0123456789",
  "name": "A0123456789",
  "calling_name": "Maika phòng khách",
  "address": "",
  "model": "MK100B",
  "firmware_version": "2.64",
  "online": true,
  "wifi": [{"ssid": "…", "connected": true}],
  "volume": 70,
  "mute": false,
  "wakeword_sensitivity_level": "high",
  "wakeword_response_type": "wakeword_response_default",
  "tts_voice": "vn_south",
  "current_playback": {"status": "start", "payload": {"playbackAttributes": {"song": "…", "artist": "…"}}}
}
```
Trường có thể ở dạng camelCase (`deviceId`, `currentPlayback`…); integration chuẩn hoá về snake_case.

### PUT cài đặt
```http
PUT https://users.iviet.com/v1/user-device/12345
Authorization: Bearer <token>

{"id": 12345, "device_id": "A0123456789", "calling_name": "Maika phòng khách"}
```
Chỉ các trường sau được phép ghi:

| Trường | Giá trị |
|---|---|
| `name` | chuỗi |
| `calling_name` | chuỗi |
| `address` | chuỗi |
| `wakeword_sensitivity_level` | `low` · `medium` · `high` |
| `wakeword_response_type` | `wakeword_response_default` · `wakeword_response_ringtone` · `wakeword_response_silent` |
| `tts_voice` | `code` lấy từ `/v1/user/tts_speaker_voices` |

### Giọng đọc
```json
{"data": [{"code": "vn_north", "name": "Giọng Bắc"}, {"code": "vn_south", "name": "Giọng Nam"}]}
```

## Gửi lệnh – POST /stream

```http
POST https://chatbot.iviet.com/stream
Authorization: <token>
Content-Type: application/octet-stream
device-id: <client_id hoặc serial loa>
olli-session-id: <session_id hoặc serial loa>
user-id: <user id>
source: android
client-version: 3.2.3
meta: <Base64(JSON)>

(body rỗng)
```

Lệnh nằm trong header `meta`, là JSON mã hoá Base64:

```json
{
  "event": {
    "header": {
      "dialogRequestId": "<uuid>",
      "messageId": "messageId-<uuid>",
      "name": "SetVolume",
      "namespace": "SystemControl"
    },
    "payload": {"deviceId": "A0123456789", "volume": 50}
  }
}
```

- Với lệnh thông thường, loa đích nằm trong `payload.deviceId` (hoặc `toDeviceId`),
  header `device-id`/`olli-session-id` mang `client_id`/`session_id` của integration.
- Với `Recognize` (gửi câu chữ), header `device-id` **và** `olli-session-id` phải là
  **serial loa**.
- Phản hồi 2xx là thành công; nếu body là JSON có `"status": false` thì coi là bị từ chối.

## Luồng sự kiện – GET /connect

```http
GET https://chatbot.iviet.com/connect
Authorization: <token>
device-id: <client_id>
olli-session-id: <session_id>
source: android
```

Kết nối giữ mở lâu dài. Dữ liệu là văn bản UTF-8 gồm các khung:

```
$START_JSON
{ ... JSON ... }
$END_JSON
```

- Khung đầu tiên có `session_id` = bắt tay thành công.
- Directive có thể nằm ở gốc hoặc bọc trong `directive`, `event`, `message`, `response`, `data`.
- Integration dùng bộ giải mã UTF-8 tăng dần (không vỡ tiếng Việt khi byte bị cắt giữa
  hai chunk), buffer tối đa 1 MiB, tự nối lại với backoff 1 → 60 giây, đăng nhập lại khi 401.

Các directive được xử lý:

| Directive | Dùng cho |
|---|---|
| `ClientInformation / DeviceInfo` | Âm lượng, `mute` (micro), `current_playback`, `latest_playlist` |
| `header.type = speakerConversationResponse`, `header.rawSpeech` | Câu người dùng vừa nói → sensor + event `maika_direct_voice_command` (chống trùng 5 phút theo `messageId`). Header còn có `namespace`/`name` của hành động loa chọn, ví dụ "tắt đi" → `PlaybackController / PauseCommandIssued` |
| namespace `SpeechSynthesizer` / `TextToSpeech` có `text` | Câu loa trả lời → sensor + event `maika_direct_speaker_response` |

Để cloud gửi `speakerConversationResponse`, integration gửi `Conversation/StartListening`
cho từng loa sau mỗi lần bắt tay `/connect`, và `StopListening` khi gỡ tích hợp.

## Danh sách lệnh

| Chức năng | `namespace` / `name` | `payload` |
|---|---|---|
| Đặt âm lượng | `SystemControl` / `SetVolume` | `deviceId`, `volume` (0–100) |
| Tắt micro | `Recording` / `Mute` | `deviceId` |
| Bật micro | `Recording` / `Unmute` | `deviceId` |
| Tạm dừng | `PlaybackController` / `PauseCommandIssued` | `deviceId` |
| Phát tiếp | `PlaybackController` / `ResumeCommandIssued` | `deviceId` |
| Bài tiếp | `PlaybackController` / `NextCommandIssued` | `deviceId` |
| Bài trước | `PlaybackController` / `PreviousCommandIssued` | `deviceId` |
| Khởi động lại | `SystemControl` / `Reboot` | `toDeviceId` |
| Lấy trạng thái | `ClientInformation` / `GetDeviceInfo` | `deviceId`, `fields`: `current_playback,volume,latest_playlist,device_id,mute` |
| Bắt đầu nghe hội thoại | `Conversation` / `StartListening` | `deviceId`, `type`: `conversation` hoặc `media_control` |
| Dừng nghe hội thoại | `Conversation` / `StopListening` | `deviceId`, `type`: `conversation` |
| Gửi câu chữ | `SpeechRecognizer` / `Recognize` | không có payload; `header.rawSpeech` = câu chữ |
| Phát URL | `SystemControl` / `CommandHandOver` | xem dưới |

**Không triển khai:** `SystemControl / Reset` (khôi phục cài đặt gốc).

### Phát URL (CommandHandOver)
```json
{
  "event": {
    "header": {"messageId": "messageId-<uuid>", "name": "CommandHandOver", "namespace": "SystemControl"},
    "payload": {
      "fromDeviceId": "<client_id>",
      "toDeviceId": ["A0123456789"],
      "messageInfo": {
        "eventHeader": {
          "dialogRequestId": "<uuid>", "messageId": "messageId-<uuid>",
          "name": "Play", "namespace": "AudioPlayer"
        },
        "mediaCard": {"format": "AUDIO_MPEG", "url": "http://192.168.1.20:8123/api/tts_proxy/….mp3", "type": "audio", "title": "…"},
        "mediaOffset": 0
      }
    }
  }
}
```
Loa **tự tải** `url`, nên URL phải truy cập được từ loa (LAN hoặc Internet). Chỉ link đi
qua cloud, nội dung âm thanh không đi qua cloud MAIKA.

**Hành vi quan sát được (MK100B, firmware 2.64):** sau `CommandHandOver`, `DeviceInfo` báo
`current_playback.status = "paused"` với `playbackAttributes.url` = URL mới – loa đã nạp nhưng
chưa phát. Gửi `PlaybackController / ResumeCommandIssued` thì loa phát (`status = "start"`).
Nếu URL trùng bài đang tạm dừng, loa tiếp tục từ `offsetInMilliseconds` cũ.

Ví dụ `DeviceInfo` sau khi cast:
```json
{"header": {"namespace": "ClientInformation", "name": "DeviceInfo"},
 "payload": {"device_id": "A0123456789", "volume": 70, "mute": false,
   "current_playback": {"status": "paused", "payload": {
     "playbackAttributes": {"url": "http://192.168.1.20:8123/api/tts_proxy/….mp3", "type": "audio", "format": "AUDIO_MPEG"},
     "offsetInMilliseconds": "0"}}}}
```

## Websocket nội bộ của integration

Panel gọi qua `hass.callWS(...)`. Mọi lệnh yêu cầu người dùng HA đã đăng nhập; panel chỉ
hiện với quản trị viên.

| `type` | Tham số | Kết quả |
|---|---|---|
| `maika_direct/info` | – | `{accounts: [{entry_id, title, stream_connected, last_update_ok, options, speakers: [{serial, name, model, firmware, online, entities, last_command, last_response}]}]}` |
| `maika_direct/settings/get` | `serial` | `{writable, values: {name, calling_name, address, wakeword_sensitivity_level, wakeword_response_type, tts_voice}, voices: [{value, label}]}` |
| `maika_direct/settings/set` | `serial`, `changes: {field: value}` | `{ok: true}` – chỉ các trường được phép ghi |
| `maika_direct/options/set` | `entry_id`, `media_base_url`, `scan_interval` | `{ok: true}` – tích hợp tự tải lại |
| `maika_direct/send_text` | `serial`, `text` (≤ 500 ký tự) | `{ok: true}` |
| `maika_direct/cast` | `serial`, `url` (http/https) | `{ok: true}` |

Ví dụ trong console trình duyệt:
```js
const hass = document.querySelector("home-assistant").hass;
await hass.callWS({ type: "maika_direct/info" });
await hass.callWS({ type: "maika_direct/send_text", serial: "A0123456789", text: "mấy giờ rồi" });
```

## Action và event của Home Assistant

### Action `maika_direct.send_text`
```yaml
action: maika_direct.send_text
data:
  entity_id: media_player.a0123456789   # một hoặc nhiều media player MAIKA Direct
  text: "bật nhạc Trịnh Công Sơn"
```

### Các action media_player chuẩn
`volume_set`, `volume_mute`, `volume_up/down`, `media_play`, `media_pause`, `media_stop`
(= tạm dừng), `media_next_track`, `media_previous_track`, `play_media` (URL http/https hoặc
`media-source://…`), `browse_media` (chỉ nguồn âm thanh).

### Event
| Event | `data` |
|---|---|
| `maika_direct_voice_command` | `device_id` (serial hoặc `null`), `text` |
| `maika_direct_speaker_response` | `device_id`, `text` |
