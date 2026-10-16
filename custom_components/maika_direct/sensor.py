"""Sensors: last voice command, last speaker reply, firmware, Wi-Fi."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory

from .entity import MaikaEntity


def _wifi_ssid(dev: dict[str, Any]) -> str | None:
    wifi = dev.get("wifi")
    if isinstance(wifi, dict):
        wifi = [wifi]
    if not isinstance(wifi, list):
        return None
    items = [w for w in wifi if isinstance(w, dict)]
    pick = next((w for w in items if w.get("connected")), items[0] if items else None)
    return pick.get("ssid") if pick else None


@dataclass(frozen=True, kw_only=True)
class DeviceSensorDesc(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


DEVICE_SENSORS = (
    DeviceSensorDesc(
        key="firmware",
        translation_key="firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmware_version"),
    ),
    DeviceSensorDesc(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_wifi_ssid,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    entities: list[SensorEntity] = []
    for s in c.data:
        entities += [MaikaDeviceSensor(c, s, d) for d in DEVICE_SENSORS]
        entities += [MaikaTextSensor(c, s, "last_command"), MaikaTextSensor(c, s, "last_response")]
    async_add_entities(entities)


class MaikaDeviceSensor(MaikaEntity, SensorEntity):
    entity_description: DeviceSensorDesc

    def __init__(self, coordinator, serial: str, desc: DeviceSensorDesc) -> None:
        super().__init__(coordinator, serial, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)


class MaikaTextSensor(MaikaEntity, SensorEntity):
    """Latest utterance heard by the speaker / latest reply it spoke."""

    def __init__(self, coordinator, serial: str, kind: str) -> None:
        super().__init__(coordinator, serial, kind)
        self._kind = kind
        self._attr_translation_key = kind
        self._attr_icon = "mdi:account-voice" if kind == "last_command" else "mdi:speaker-message"

    def _info(self) -> dict[str, Any]:
        store = (
            self.coordinator.last_command if self._kind == "last_command" else self.coordinator.last_response
        )
        return store.get(self.serial, {})

    @property
    def native_value(self) -> str | None:
        text = self._info().get("text")
        return text[:255] if text else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self._info()
        if not info:
            return {}
        attrs = {"full_text": info.get("text"), "timestamp": info.get("time")}
        if info.get("assist"):
            attrs["assist"] = info["assist"]
        return attrs
