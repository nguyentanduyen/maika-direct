"""MAIKA Direct – control MAIKA speakers through the MAIKA cloud, no licence server."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaikaAuthError, MaikaClient, MaikaError
from .const import (
    ATTR_TEXT,
    CONF_CLIENT_ID,
    CONF_LOGIN,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_SEND_TEXT,
)
from .coordinator import MaikaCoordinator
from .panel import async_remove_panel, async_setup_panel

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

type MaikaConfigEntry = ConfigEntry[MaikaCoordinator]

SEND_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(min=1, max=500)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: MaikaConfigEntry) -> bool:
    client = MaikaClient(
        async_get_clientsession(hass),
        entry.data[CONF_LOGIN],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_SESSION_ID],
    )
    try:
        await client.async_login()
    except MaikaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except MaikaError as err:
        raise ConfigEntryNotReady(str(err)) from err

    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = MaikaCoordinator(hass, entry, client, interval)
    entry.runtime_data = coordinator

    listener = entry.async_create_background_task(
        hass, client.async_listen_forever(), f"{DOMAIN}_stream"
    )

    async def _stop(*_: object) -> None:
        client.stop()
        listener.cancel()

    entry.async_on_unload(_stop)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))

    await async_setup_panel(hass)

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TEXT):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_TEXT, _make_send_text(hass), schema=SEND_TEXT_SCHEMA
        )
    return True


def _make_send_text(hass: HomeAssistant):
    async def _send_text(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        for entity_id in call.data[ATTR_ENTITY_ID]:
            ent = registry.async_get(entity_id)
            if ent is None or ent.platform != DOMAIN or ent.config_entry_id is None:
                raise HomeAssistantError(f"{entity_id} is not a MAIKA Direct entity")
            entry = hass.config_entries.async_get_entry(ent.config_entry_id)
            if entry is None or not hasattr(entry, "runtime_data"):
                raise HomeAssistantError(f"{entity_id} is not loaded")
            serial = ent.unique_id.rsplit("__", 1)[0]
            try:
                await entry.runtime_data.client.async_send_text(serial, call.data[ATTR_TEXT])
            except MaikaError as err:
                raise HomeAssistantError(f"MAIKA: {err}") from err

    return _send_text


async def _reload_on_options(hass: HomeAssistant, entry: MaikaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MaikaConfigEntry) -> bool:
    coordinator = entry.runtime_data
    for serial in list(coordinator.data or {}):
        try:
            await coordinator.client.async_stop_listening(serial)
        except MaikaError:
            pass
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id != entry.entry_id]
    if unloaded and not others:
        hass.services.async_remove(DOMAIN, SERVICE_SEND_TEXT)
        async_remove_panel(hass)
    return unloaded
