"""Media player for MAIKA speakers."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import MaikaError
from .const import CONF_MEDIA_BASE_URL
from .entity import MaikaEntity

_LOGGER = logging.getLogger(__name__)

PLAYING = {"start", "started", "resume", "resumed", "playing", "play"}
PAUSED = {"pause", "paused", "stop", "stopped"}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MaikaMediaPlayer(coordinator, serial, entry.options.get(CONF_MEDIA_BASE_URL, ""))
        for serial in coordinator.data
    )


class MaikaMediaPlayer(MaikaEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, coordinator, serial: str, media_base_url: str) -> None:
        super().__init__(coordinator, serial, "media_player")
        self._media_base_url = media_base_url
        self._volume_before_mute = 0.3

    # ------------------------------------------------------------- state
    @property
    def _playback(self) -> dict[str, Any]:
        cp = self.device.get("current_playback")
        return cp if isinstance(cp, dict) else {}

    @property
    def _attrs(self) -> dict[str, Any]:
        payload = self._playback.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("playbackAttributes"), dict):
            return payload["playbackAttributes"]
        return {}

    @staticmethod
    def _first(*vals: Any) -> str | None:
        return next((v for v in vals if isinstance(v, str) and v), None)

    @property
    def state(self) -> MediaPlayerState:
        if self.device.get("online") is False:
            return MediaPlayerState.OFF
        status = str(self._playback.get("status") or "").lower()
        if status in PLAYING:
            return MediaPlayerState.PLAYING
        if status in PAUSED:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        try:
            return max(0.0, min(1.0, float(self.device["volume"]) / 100))
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def is_volume_muted(self) -> bool | None:
        v = self.volume_level
        return None if v is None else v == 0

    @property
    def media_title(self) -> str | None:
        a = self._attrs
        return self._first(a.get("song"), a.get("title"), a.get("name"))

    @property
    def media_artist(self) -> str | None:
        a = self._attrs
        return self._first(a.get("artist"), a.get("narrator"))

    @property
    def media_image_url(self) -> str | None:
        a = self._attrs
        url = self._first(a.get("imageURL"), a.get("image_url"))
        if url:
            return url
        img = a.get("image")
        return self._first(img.get("url"), img.get("src")) if isinstance(img, dict) else None

    @property
    def media_duration(self) -> float | None:
        payload = self._playback.get("payload")
        if not isinstance(payload, dict):
            return None
        try:
            v = float(payload.get("durationInMilliseconds") or payload.get("durationInMillis")) / 1000
        except (TypeError, ValueError):
            return None
        return v if v > 0 else None

    # ---------------------------------------------------------- commands
    async def _run(self, coro) -> None:
        try:
            await coro
        except MaikaError as err:
            raise HomeAssistantError(f"MAIKA: {err}") from err
        self.hass.async_create_task(self.coordinator.async_refresh_live(self.serial))

    async def async_set_volume_level(self, volume: float) -> None:
        target = round(max(0.0, min(1.0, volume)) * 100)
        if target:
            self._volume_before_mute = target / 100
        await self._run(self.coordinator.client.async_set_volume(self.serial, target))
        self.coordinator.async_patch(self.serial, {"volume": target})

    async def async_mute_volume(self, mute: bool) -> None:
        if mute:
            if self.volume_level:
                self._volume_before_mute = self.volume_level
            await self.async_set_volume_level(0)
        else:
            await self.async_set_volume_level(self._volume_before_mute or 0.3)

    async def _set_status(self, status: str) -> None:
        cp = dict(self._playback)
        cp["status"] = status
        self.coordinator.async_patch(self.serial, {"current_playback": cp})

    async def async_media_play(self) -> None:
        await self._run(self.coordinator.client.async_playback(self.serial, "Resume"))
        await self._set_status("resume")

    async def async_media_pause(self) -> None:
        await self._run(self.coordinator.client.async_playback(self.serial, "Pause"))
        await self._set_status("pause")

    async def async_media_stop(self) -> None:
        # no verified Stop directive – pause instead
        await self.async_media_pause()

    async def async_media_next_track(self) -> None:
        await self._run(self.coordinator.client.async_playback(self.serial, "Next"))

    async def async_media_previous_track(self) -> None:
        await self._run(self.coordinator.client.async_playback(self.serial, "Previous"))

    async def async_browse_media(
        self, media_content_type: MediaType | str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        title = None
        if media_source.is_media_source_id(media_id):
            item = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            media_id = item.url
        media_id = async_process_play_media_url(self.hass, media_id)
        media_id = self._rewrite_for_speaker(media_id)
        if not media_id.startswith(("http://", "https://")):
            raise HomeAssistantError("MAIKA chỉ phát được URL http(s)")
        extra = kwargs.get("extra") or {}
        if isinstance(extra, dict):
            meta = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
            title = meta.get("title") or extra.get("title")
        _LOGGER.debug("Casting %s to MAIKA %s", media_id, self.serial)
        try:
            await self.coordinator.async_cast(self.serial, media_id, title)
        except MaikaError as err:
            raise HomeAssistantError(f"MAIKA: {err}") from err

    def _rewrite_for_speaker(self, url: str) -> str:
        """Point HA-hosted URLs at an address the speaker can reach on the LAN."""
        if not self._media_base_url:
            return url
        parts = urlsplit(url)
        base = urlsplit(self._media_base_url)
        host = (parts.hostname or "").lower()
        if host == (base.hostname or "").lower():
            return url  # already reachable
        own = {"localhost", "127.0.0.1", "::1", "homeassistant", "homeassistant.local", "supervisor", "hassio"}
        ha_port = getattr(getattr(self.hass, "http", None), "server_port", None) or 8123
        internal_host = (urlsplit(self.hass.config.internal_url or "").hostname or "").lower()
        # Only rewrite URLs that point at *this* Home Assistant (its port / names),
        # never third-party LAN servers such as Music Assistant on :8097.
        # Any URL on HA's own port is HA itself (Docker/OrbStack bridge IPs such as
        # 172.17.x or 192.168.97.x are not reachable from the speaker).
        is_ha = (
            host in own
            or (internal_host and host == internal_host)
            or parts.port == ha_port
            or (_is_container_ip(host) and parts.port is None)
        )
        if is_ha:
            return urlunsplit((base.scheme, base.netloc, parts.path, parts.query, parts.fragment))
        return url


def _is_container_ip(host: str) -> bool:
    """Docker/OrbStack bridge addresses (not reachable from the LAN)."""
    import ipaddress

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        ip in ipaddress.ip_network(net)
        for net in ("172.17.0.0/16", "172.18.0.0/15", "172.20.0.0/14", "192.168.97.0/24", "192.168.215.0/24", "198.19.0.0/16")
    )
