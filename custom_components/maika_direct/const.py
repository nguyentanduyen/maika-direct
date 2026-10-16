"""Constants for MAIKA Direct."""

from __future__ import annotations

DOMAIN = "maika_direct"

APP_VERSION = "3.2.3"
APP_DEVICE_TYPE = "android"
APP_LANGUAGE = "vi-VN"
APP_TIMEZONE = "Asia/Ho_Chi_Minh"
APP_ORGANIZATION_CODE = "MAIKA"

USERS_BASE_URL = "https://users.iviet.com"
CHATBOT_BASE_URL = "https://chatbot.iviet.com"

CONF_LOGIN = "login"
CONF_PASSWORD = "password"
CONF_CLIENT_ID = "client_id"
CONF_SESSION_ID = "session_id"
CONF_MEDIA_BASE_URL = "media_base_url"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60

DEVICE_INFO_FIELDS = "current_playback,volume,latest_playlist,device_id,mute"

EVENT_VOICE_COMMAND = f"{DOMAIN}_voice_command"
EVENT_SPEAKER_RESPONSE = f"{DOMAIN}_speaker_response"

SERVICE_SEND_TEXT = "send_text"
ATTR_TEXT = "text"
