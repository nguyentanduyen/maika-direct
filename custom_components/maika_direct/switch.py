"""Microphone mute switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .api import MaikaError
from .entity import MaikaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    async_add_entities(MaikaMicMute(c, s) for s in c.data)


class MaikaMicMute(MaikaEntity, SwitchEntity):
    _attr_translation_key = "mic_mute"
    _attr_icon = "mdi:microphone-off"

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "mic_mute")

    @property
    def is_on(self) -> bool | None:
        v = self.device.get("mute")
        return v if isinstance(v, bool) else None

    async def _set(self, muted: bool) -> None:
        try:
            await self.coordinator.client.async_set_mic_mute(self.serial, muted)
        except MaikaError as err:
            raise HomeAssistantError(f"MAIKA: {err}") from err
        self.coordinator.async_patch(self.serial, {"mute": muted})
        self.hass.async_create_task(self.coordinator.async_refresh_live(self.serial))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
