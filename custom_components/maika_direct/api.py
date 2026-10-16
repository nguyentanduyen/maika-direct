"""Minimal client for the MAIKA cloud used by the official Android app.

Endpoints, headers and envelopes follow docs/API_RESEARCH.md of
trankhanhduy2929-beep/loa-maika-home-assistant (MIT). No licence server.
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import aiohttp

from .const import (
    APP_DEVICE_TYPE,
    APP_LANGUAGE,
    APP_ORGANIZATION_CODE,
    APP_TIMEZONE,
    APP_VERSION,
    CHATBOT_BASE_URL,
    DEVICE_INFO_FIELDS,
    USERS_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
STREAM_TIMEOUT = aiohttp.ClientTimeout(
    total=None, connect=30, sock_connect=30, sock_read=180
)
FRAME_START = "$START_JSON"
FRAME_END = "$END_JSON"
MAX_BUFFER = 1024 * 1024
WRAPPER_KEYS = ("directive", "event", "message", "response", "data")
WRITABLE_FIELDS = frozenset(
    {
        "name",
        "calling_name",
        "address",
        "wakeword_sensitivity_level",
        "wakeword_response_type",
        "tts_voice",
    }
)

_ALIASES = {
    "deviceId": "device_id",
    "deviceID": "device_id",
    "serialNumber": "device_id",
    "serial_number": "device_id",
    "serial": "device_id",
    "isOnline": "online",
    "is_online": "online",
    "callingName": "calling_name",
    "firmwareVersion": "firmware_version",
    "currentPlayback": "current_playback",
    "latestPlaylist": "latest_playlist",
    "ttsVoice": "tts_voice",
    "wakeWordSensitivityLevel": "wakeword_sensitivity_level",
    "wakeWordResponseType": "wakeword_response_type",
}


class MaikaError(Exception):
    """Base error."""


class MaikaAuthError(MaikaError):
    """Bad credentials or expired token."""


class MaikaConnectionError(MaikaError):
    """Network / server error."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def is_email(identifier: str) -> bool:
    return "@" in identifier


def normalize_login(identifier: str) -> str:
    """Emails stay as typed; VN phones become +84xxxxxxxxx (format the app sends)."""
    value = identifier.strip()
    if is_email(value):
        return value
    p = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if p.startswith("00"):
        p = "+" + p[2:]
    if p.startswith("+840"):
        return "+84" + p[4:]
    if p.startswith("+84"):
        return p
    if p.startswith("840"):
        return "+84" + p[3:]
    if p.startswith("84"):
        return "+" + p
    if p.startswith("0"):
        return "+84" + p[1:]
    return p


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return None


def normalize_device(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map REST/stream speaker records to snake_case with a serial `device_id`."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        out[_ALIASES.get(str(key), str(key))] = value
    serial = str(out.get("device_id") or "").strip()
    if not serial:
        return None
    out["device_id"] = serial
    for key in ("online", "mute"):
        if key in out:
            b = to_bool(out[key])
            if b is not None:
                out[key] = b
    return out


def extract_frames(buffer: str) -> tuple[list[dict[str, Any]], str]:
    """Split `$START_JSON ... $END_JSON` frames out of a text buffer."""
    frames: list[dict[str, Any]] = []
    while True:
        start = buffer.find(FRAME_START)
        if start < 0:
            buffer = buffer[-len(FRAME_START) :] if len(buffer) > len(FRAME_START) else buffer
            break
        end = buffer.find(FRAME_END, start + len(FRAME_START))
        if end < 0:
            buffer = buffer[start:]
            break
        raw = buffer[start + len(FRAME_START) : end].strip()
        buffer = buffer[end + len(FRAME_END) :]
        if not raw:
            continue
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(frame, dict):
            frames.append(frame)
    if len(buffer) > MAX_BUFFER:
        buffer = buffer[-MAX_BUFFER:]
    return frames, buffer


def unwrap_directive(frame: dict[str, Any]) -> dict[str, Any]:
    """Find the first nested object that has a `header` dict."""
    pending: list[dict[str, Any]] = [frame]
    while pending:
        cand = pending.pop(0)
        if isinstance(cand.get("header"), dict):
            return cand
        for key in WRAPPER_KEYS:
            nested = cand.get(key)
            if isinstance(nested, dict):
                pending.append(nested)
            elif isinstance(nested, list):
                pending.extend(i for i in nested if isinstance(i, dict))
    return frame


def find_device_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pending: list[Any] = [payload]
    while pending:
        cand = pending.pop(0)
        if not isinstance(cand, dict):
            continue
        if any(k in cand for k in ("device_id", "deviceId", "serial_number", "serialNumber")):
            return cand
        for key in ("device", "deviceInfo", "device_info", "speaker", "data"):
            nested = cand.get(key)
            if isinstance(nested, dict):
                pending.append(nested)
            elif isinstance(nested, list):
                pending.extend(nested)
    return payload


class MaikaClient:
    """Talks to users.iviet.com (REST) and chatbot.iviet.com (/stream, /connect)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        login: str,
        password: str,
        client_id: str,
        session_id: str,
    ) -> None:
        self._session = session
        self._login = normalize_login(login)
        self._password = password
        self.client_id = client_id
        self._session_id = session_id
        self._token: str | None = None
        self._token_until = 0.0
        self.user_id: int | None = None
        self._auth_lock = asyncio.Lock()
        self._stopping = False
        self.connected = asyncio.Event()
        self.on_frame: Callable[[dict[str, Any]], None] | None = None

    # ------------------------------------------------------------------ auth
    async def async_login(self) -> None:
        if is_email(self._login):
            path = "/v1/auth/login"
            body = {"device_id": self.client_id, "email": self._login, "password": self._password}
        else:
            path = "/v1/auth/otp/login"
            body = {"phone_number": self._login, "password": self._password}
        try:
            async with self._session.post(
                f"{USERS_BASE_URL}{path}",
                json=body,
                headers=self._rest_headers(auth=False),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                raw = await resp.read()
                if resp.status in (400, 401, 403, 404):
                    raise MaikaAuthError(f"Login rejected (HTTP {resp.status})")
                if resp.status >= 400:
                    raise MaikaConnectionError(f"Login HTTP {resp.status}", resp.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MaikaConnectionError("Cannot reach MAIKA login") from err
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise MaikaConnectionError("Login returned non-JSON") from err
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("access_token"):
            raise MaikaAuthError("Login returned no token")
        self._token = str(data["access_token"])
        try:
            self.user_id = int(data["id"])
        except (KeyError, TypeError, ValueError) as err:
            raise MaikaAuthError("Login returned no user id") from err
        try:
            ttl = int(data.get("expire_time", 86400))
        except (TypeError, ValueError):
            ttl = 86400
        # expire_time may be a duration or an epoch; treat huge values as epoch
        if ttl > 10**9:
            ttl = max(60, ttl - int(time.time()))
        self._token_until = time.monotonic() + max(60, ttl - 60)

    async def _ensure_auth(self) -> None:
        async with self._auth_lock:
            if self._token is None or time.monotonic() >= self._token_until:
                await self.async_login()

    def _drop_auth(self) -> None:
        self._token = None
        self._token_until = 0.0

    # --------------------------------------------------------------- headers
    def _rest_headers(self, auth: bool = True) -> dict[str, str]:
        h = {
            "device-type": APP_DEVICE_TYPE,
            "version-info": APP_VERSION,
            "timezone": APP_TIMEZONE,
            "language-code": APP_LANGUAGE,
        }
        if auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _chatbot_headers(self, device_id: str | None = None) -> dict[str, str]:
        assert self._token is not None
        return {
            "Authorization": self._token,  # raw token, no "Bearer"
            "device-id": device_id or self.client_id,
            "device-type": APP_DEVICE_TYPE,
            "version-info": APP_VERSION,
            "olli-session-id": device_id or self._session_id,
            "timezone": APP_TIMEZONE,
            "source": APP_DEVICE_TYPE,
            "Content-Type": "application/octet-stream",
            "client-version": APP_VERSION,
            "user-id": str(self.user_id),
            "language-code": APP_LANGUAGE,
        }

    # ------------------------------------------------------------------ REST
    async def _rest(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> Any:
        await self._ensure_auth()
        try:
            async with self._session.request(
                method,
                f"{USERS_BASE_URL}{path}",
                params=params,
                json=body,
                headers=self._rest_headers(),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                raw = await resp.read()
                if resp.status == 401 and retry:
                    self._drop_auth()
                    return await self._rest(method, path, params=params, body=body, retry=False)
                if resp.status in (401, 403):
                    raise MaikaAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise MaikaConnectionError(f"{path} HTTP {resp.status}", resp.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MaikaConnectionError(f"Cannot reach {path}") from err
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise MaikaConnectionError(f"{path} returned non-JSON") from err

    async def async_list_speakers(self) -> list[dict[str, Any]]:
        resp = await self._rest(
            "GET",
            "/v1/user-device",
            params={
                "type": "speaker",
                "page": 1,
                "limit": 100,
                "organization_code": APP_ORGANIZATION_CODE,
            },
        )
        rows: list[Any] = []
        pending: list[Any] = [resp]
        while pending:
            cand = pending.pop(0)
            if isinstance(cand, list):
                rows = cand
                break
            if isinstance(cand, dict):
                for key in ("data", "devices", "items", "list", "results"):
                    if isinstance(cand.get(key), (dict, list)):
                        pending.append(cand[key])
        speakers = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = row.get("type") or row.get("device_type")
            if kind is not None and str(kind).lower() not in {"speaker", "maika"}:
                continue
            dev = normalize_device(row)
            if dev:
                speakers.append(dev)
        return speakers

    async def async_get_speaker(self, internal_id: Any) -> dict[str, Any]:
        resp = await self._rest("GET", f"/v1/user-device/{internal_id}")
        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict):
            return {}
        return normalize_device(data) or {}

    async def async_get_tts_voices(self) -> list[dict[str, Any]]:
        resp = await self._rest("GET", "/v1/user/tts_speaker_voices")
        data = resp.get("data") if isinstance(resp, dict) else None
        return [v for v in data if isinstance(v, dict)] if isinstance(data, list) else []

    async def async_update_speaker(
        self, internal_id: Any, serial: str, changes: dict[str, Any]
    ) -> None:
        bad = set(changes) - WRITABLE_FIELDS
        if bad:
            raise ValueError(f"Field not writable: {bad}")
        await self._rest(
            "PUT",
            f"/v1/user-device/{internal_id}",
            body={"id": internal_id, "device_id": serial, **changes},
        )

    # --------------------------------------------------------------- /stream
    async def async_send_meta(
        self, meta: dict[str, Any], *, device_id: str | None = None, retry: bool = True
    ) -> None:
        await self._ensure_auth()
        encoded = base64.b64encode(
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode()
        headers = {**self._chatbot_headers(device_id), "meta": encoded}
        try:
            async with self._session.post(
                f"{CHATBOT_BASE_URL}/stream",
                headers=headers,
                data=b"",
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                body = await resp.read()
                if resp.status == 401 and retry:
                    self._drop_auth()
                    await self.async_send_meta(meta, device_id=device_id, retry=False)
                    return
                if resp.status in (401, 403):
                    raise MaikaAuthError("Command auth failed")
                if resp.status >= 400:
                    raise MaikaConnectionError(f"Command HTTP {resp.status}", resp.status)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MaikaConnectionError("Cannot send MAIKA command") from err
        _LOGGER.debug(
            "MAIKA /stream %s/%s -> HTTP %s, %d bytes: %r",
            meta.get("event", {}).get("header", {}).get("namespace"),
            meta.get("event", {}).get("header", {}).get("name"),
            resp.status,
            len(body),
            body[:300],
        )
        if body:
            try:
                result = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if isinstance(result, dict) and result.get("status") is False:
                raise MaikaConnectionError("MAIKA rejected the command")

    async def async_command(
        self, name: str, namespace: str, payload: dict[str, Any]
    ) -> None:
        await self.async_send_meta(
            {
                "event": {
                    "header": {
                        "dialogRequestId": str(uuid4()),
                        "messageId": f"messageId-{uuid4()}",
                        "name": name,
                        "namespace": namespace,
                    },
                    "payload": payload,
                }
            }
        )

    async def async_set_volume(self, serial: str, volume: int) -> None:
        await self.async_command(
            "SetVolume", "SystemControl", {"deviceId": serial, "volume": max(0, min(100, volume))}
        )

    async def async_set_mic_mute(self, serial: str, muted: bool) -> None:
        await self.async_command("Mute" if muted else "Unmute", "Recording", {"deviceId": serial})

    async def async_playback(self, serial: str, command: str) -> None:
        """command: Pause / Resume / Next / Previous."""
        await self.async_command(f"{command}CommandIssued", "PlaybackController", {"deviceId": serial})

    async def async_reboot(self, serial: str) -> None:
        await self.async_command("Reboot", "SystemControl", {"toDeviceId": serial})

    async def async_request_info(self, serial: str) -> None:
        await self.async_command(
            "GetDeviceInfo", "ClientInformation", {"deviceId": serial, "fields": DEVICE_INFO_FIELDS}
        )

    async def async_start_listening(self, serial: str, kind: str = "conversation") -> None:
        """kind: conversation (voice mirror) or media_control (playback events)."""
        await self.async_command("StartListening", "Conversation", {"deviceId": serial, "type": kind})

    async def async_stop_listening(self, serial: str, kind: str = "conversation") -> None:
        await self.async_command("StopListening", "Conversation", {"deviceId": serial, "type": kind})

    async def async_send_text(self, serial: str, text: str) -> None:
        """Make the speaker handle `text` as if it had heard it."""
        await self.async_send_meta(
            {
                "event": {
                    "header": {
                        "dialogRequestId": str(uuid4()),
                        "messageId": f"messageId-{uuid4()}",
                        "name": "Recognize",
                        "namespace": "SpeechRecognizer",
                        "rawSpeech": text,
                    }
                }
            },
            device_id=serial,
        )

    async def async_cast(
        self, serial: str, url: str, title: str | None = None, offset_ms: int = 0
    ) -> None:
        """Hand a direct audio URL to the speaker (CommandHandOver / AudioPlayer.Play)."""
        card: dict[str, Any] = {"format": "AUDIO_MPEG", "url": url, "type": "audio"}
        if title:
            card["title"] = title
        await self.async_send_meta(
            {
                "event": {
                    "header": {
                        "messageId": f"messageId-{uuid4()}",
                        "name": "CommandHandOver",
                        "namespace": "SystemControl",
                    },
                    "payload": {
                        "fromDeviceId": self.client_id,
                        "messageInfo": {
                            "eventHeader": {
                                "dialogRequestId": str(uuid4()),
                                "messageId": f"messageId-{uuid4()}",
                                "name": "Play",
                                "namespace": "AudioPlayer",
                            },
                            "mediaCard": card,
                            "mediaOffset": max(0, offset_ms),
                        },
                        "toDeviceId": [serial],
                    },
                }
            }
        )

    # -------------------------------------------------------------- /connect
    async def async_listen_forever(self) -> None:
        delay = 1
        while not self._stopping:
            try:
                self.connected.clear()
                await self._ensure_auth()
                headers = self._chatbot_headers()
                headers.pop("client-version", None)
                headers.pop("user-id", None)
                async with self._session.get(
                    f"{CHATBOT_BASE_URL}/connect", headers=headers, timeout=STREAM_TIMEOUT
                ) as resp:
                    if resp.status == 401:
                        self._drop_auth()
                        raise MaikaAuthError("stream 401")
                    if resp.status >= 400:
                        raise MaikaConnectionError(f"stream HTTP {resp.status}", resp.status)
                    delay = 1
                    buffer = ""
                    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                    async for chunk in resp.content.iter_any():
                        if self._stopping:
                            return
                        buffer += decoder.decode(chunk)
                        frames, buffer = extract_frames(buffer)
                        for frame in frames:
                            self._handle(frame)
            except asyncio.CancelledError:
                raise
            except (MaikaError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("MAIKA stream disconnected: %s", err)
            self.connected.clear()
            if not self._stopping:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    def _handle(self, frame: dict[str, Any]) -> None:
        if frame.get("session_id") or (
            "connected" in frame and isinstance(frame.get("header"), dict)
        ):
            self.connected.set()
        if self.on_frame is not None:
            try:
                self.on_frame(unwrap_directive(frame))
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error handling MAIKA frame")

    def stop(self) -> None:
        self._stopping = True
        self.connected.clear()
