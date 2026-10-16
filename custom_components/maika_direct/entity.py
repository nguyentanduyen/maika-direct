"""Shared entity base."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaikaCoordinator


class MaikaEntity(CoordinatorEntity[MaikaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MaikaCoordinator, serial: str, key: str) -> None:
        super().__init__(coordinator)
        self.serial = serial
        self._attr_unique_id = f"{serial}__{key}"
        dev = self.device
        wifi = dev.get("wifi")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=(dev.get("name") if dev.get("name") not in (None, "", serial) else None)
            or dev.get("calling_name")
            or f"MAIKA {serial[-4:]}",
            manufacturer=dev.get("manufacturer") or "OLLI / MAIKA",
            model=dev.get("model") or "MAIKA Speaker",
            sw_version=dev.get("firmware_version"),
            serial_number=serial,
            connections=set(),
        )
        if isinstance(wifi, dict) and wifi.get("mac"):
            self._attr_device_info["connections"] = {("mac", str(wifi["mac"]).lower())}

    @property
    def device(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self.serial, {})

    @property
    def available(self) -> bool:
        return super().available and self.serial in (self.coordinator.data or {})
