"""Restart / refresh buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import MaikaError
from .entity import MaikaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    entities = []
    for s in c.data:
        entities += [MaikaRestart(c, s), MaikaRefresh(c, s)]
    async_add_entities(entities)


class MaikaRestart(MaikaEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "restart")

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.async_reboot(self.serial)
        except MaikaError as err:
            raise HomeAssistantError(f"MAIKA: {err}") from err


class MaikaRefresh(MaikaEntity, ButtonEntity):
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
