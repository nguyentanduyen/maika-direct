"""Coordinator: REST polling + live /connect stream."""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MaikaAuthError, MaikaClient, MaikaError, find_device_payload, normalize_device
from .const import DOMAIN, EVENT_SPEAKER_RESPONSE, EVENT_VOICE_COMMAND

_LOGGER = logging.getLogger(__name__)
LIVE_FIELDS = ("volume", "mute", "current_playback", "latest_playlist")


class MaikaCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds one dict per speaker serial."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MaikaClient, interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.live: dict[str, dict[str, Any]] = {}
        self.last_command: dict[str, dict[str, Any]] = {}
        self.last_response: dict[str, dict[str, Any]] = {}
        self._seen_messages: dict[str, float] = {}
        self._listening_registered = False
        client.on_frame = self._on_frame_threadsafe

    # ------------------------------------------------------------- polling
    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            speakers = await self.client.async_list_speakers()
        except MaikaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MaikaError as err:
            if self.data:
                _LOGGER.debug("Speaker list failed, keeping cached data: %s", err)
                speakers = list(self.data.values())
            else:
                raise UpdateFailed(str(err)) from err

        result: dict[str, dict[str, Any]] = {}
        for dev in speakers:
            serial = dev["device_id"]
            merged = {**(self.data or {}).get(serial, {}), **dev}
            merged.update(self.live.get(serial, {}))
            result[serial] = merged

        # ask each speaker to push fresh volume/playback over /connect
        for serial in result:
            self.hass.async_create_task(self._safe(self.client.async_request_info(serial)))
        if self.client.connected.is_set() and not self._listening_registered:
            self._listening_registered = True
            for serial in result:
                self.hass.async_create_task(self._safe(self.client.async_start_listening(serial)))
        return result

    async def _safe(self, coro: Any) -> None:
        try:
            await coro
        except MaikaError as err:
            _LOGGER.debug("Background MAIKA command failed: %s", err)

    async def async_refresh_live(self, serial: str, delay: float = 1.5) -> None:
        await asyncio.sleep(delay)
        await self._safe(self.client.async_request_info(serial))

    @callback
    def async_patch(self, serial: str, changes: dict[str, Any]) -> None:
        """Optimistic local update."""
        if not self.data or serial not in self.data:
            return
        self.live.setdefault(serial, {}).update(deepcopy(changes))
        new = dict(self.data)
        new[serial] = {**new[serial], **deepcopy(changes)}
        self.async_set_updated_data(new)

    # -------------------------------------------------------------- stream
    def _on_frame_threadsafe(self, frame: dict[str, Any]) -> None:
        # called from the event loop (aiohttp task) – safe to touch hass directly
        self._on_frame(frame)

    @callback
    def _on_frame(self, frame: dict[str, Any]) -> None:
        header = frame.get("header")
        if not isinstance(header, dict):
            # connection handshake: (re)register conversation mirroring
            if frame.get("session_id"):
                self._listening_registered = False
                if self.data:
                    self._listening_registered = True
                    for serial in self.data:
                        self.hass.async_create_task(
                            self._safe(self.client.async_start_listening(serial))
                        )
            return
        payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}
        name = str(header.get("name", ""))
        namespace = str(header.get("namespace", ""))

        if name.lower() == "deviceinfo" and namespace.lower() == "clientinformation":
            dev = normalize_device(find_device_payload(payload))
            if dev:
                self._merge_live(dev)
            return

        if header.get("type") == "speakerConversationResponse":
            text = header.get("rawSpeech")
            msg_id = str(header.get("messageId") or header.get("sessionId") or text)
            if not isinstance(text, str) or not text.strip() or self._dup(msg_id):
                return
            serial = self._serial_from(header, payload)
            info = {"text": text.strip(), "time": time.time(), "message_id": msg_id}
            if serial:
                self.last_command[serial] = info
            self.hass.bus.async_fire(
                EVENT_VOICE_COMMAND, {"device_id": serial, "text": text.strip()}
            )
            self.async_update_listeners()
            return

        if namespace in ("SpeechSynthesizer", "TextToSpeech"):
            text = payload.get("text") or payload.get("rawText") or header.get("text")
            if isinstance(text, str) and text.strip():
                serial = self._serial_from(header, payload)
                if serial:
                    self.last_response[serial] = {"text": text.strip(), "time": time.time()}
                self.hass.bus.async_fire(
                    EVENT_SPEAKER_RESPONSE, {"device_id": serial, "text": text.strip()}
                )
                self.async_update_listeners()

    def _merge_live(self, dev: dict[str, Any]) -> None:
        serial = dev["device_id"]
        live = self.live.setdefault(serial, {})
        for key in LIVE_FIELDS:
            if key in dev:
                live[key] = dev[key]
        if self.data and serial in self.data:
            new = dict(self.data)
            new[serial] = {**new[serial], **live}
            self.async_set_updated_data(new)

    def _serial_from(self, header: dict[str, Any], payload: dict[str, Any]) -> str | None:
        for src in (header, payload):
            for key in ("deviceId", "device_id", "fromDeviceId", "serial"):
                val = src.get(key)
                if isinstance(val, str) and self.data and val in self.data:
                    return val
        if self.data and len(self.data) == 1:
            return next(iter(self.data))
        return None

    def _dup(self, msg_id: str) -> bool:
        now = time.time()
        self._seen_messages = {k: v for k, v in self._seen_messages.items() if now - v < 300}
        if msg_id in self._seen_messages:
            return True
        self._seen_messages[msg_id] = now
        return False
