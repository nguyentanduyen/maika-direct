"""Sidebar panel + websocket API for MAIKA Direct."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .api import WRITABLE_FIELDS, MaikaError
from .const import CONF_MEDIA_BASE_URL, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "maika-direct"
STATIC_URL = "/maika_direct_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
_REGISTERED = f"{DOMAIN}_panel"
ENTITY_KEYS = ("media_player", "mic_mute", "restart", "refresh", "online", "last_command", "last_response")


async def async_setup_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(_REGISTERED + "_static"):
        hass.data[_REGISTERED + "_static"] = True
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), False)]
        )
        for cmd in (ws_info, ws_get_settings, ws_set_settings, ws_set_options, ws_send_text, ws_cast):
            websocket_api.async_register_command(hass, cmd)
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    version = int((FRONTEND_DIR / "maika-direct-panel.js").stat().st_mtime)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="maika-direct-panel",
        frontend_url_path=PANEL_URL,
        sidebar_title="MAIKA",
        sidebar_icon="mdi:speaker-message",
        module_url=f"{STATIC_URL}/maika-direct-panel.js?v={version}",
        require_admin=True,
        config={},
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    # static path + websocket commands stay registered (cannot be removed); drop sidebar only
    if hass.data.pop(_REGISTERED, None):
        from homeassistant.components import frontend

        frontend.async_remove_panel(hass, PANEL_URL)


# ----------------------------------------------------------------- helpers
def _entries(hass: HomeAssistant):
    return [
        e
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(e, "runtime_data", None) is not None
    ]


def _find(hass: HomeAssistant, serial: str):
    for entry in _entries(hass):
        coord = entry.runtime_data
        if serial in (coord.data or {}):
            return entry, coord
    raise HomeAssistantError(f"Không tìm thấy loa {serial}")


def _voice_options(voices: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for v in voices:
        code = v.get("code") or v.get("id") or v.get("value")
        if code:
            out.append({"value": str(code), "label": str(v.get("name") or v.get("display_name") or code)})
    return out


def _current_voice(dev: dict[str, Any]) -> str | None:
    v = dev.get("tts_voice")
    if isinstance(v, dict):
        return v.get("code")
    return v if isinstance(v, str) else None


# ---------------------------------------------------------------- commands
@websocket_api.websocket_command({vol.Required("type"): "maika_direct/info"})
@callback
def ws_info(hass: HomeAssistant, connection, msg) -> None:
    registry = er.async_get(hass)
    accounts = []
    for entry in _entries(hass):
        coord = entry.runtime_data
        speakers = []
        for serial, dev in (coord.data or {}).items():
            entities = {
                key: registry.async_get_entity_id(
                    _platform(key), DOMAIN, f"{serial}__{key}"
                )
                for key in ENTITY_KEYS
            }
            speakers.append(
                {
                    "serial": serial,
                    "name": (dev.get("name") if dev.get("name") not in (None, "", serial) else None)
                    or dev.get("calling_name")
                    or serial,
                    "calling_name": dev.get("calling_name"),
                    "model": dev.get("model"),
                    "firmware": dev.get("firmware_version"),
                    "online": dev.get("online"),
                    "entities": entities,
                    "last_command": coord.last_command.get(serial),
                    "last_response": coord.last_response.get(serial),
                }
            )
        accounts.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "stream_connected": coord.client.connected.is_set(),
                "last_update_ok": coord.last_update_success,
                "options": {
                    CONF_MEDIA_BASE_URL: entry.options.get(CONF_MEDIA_BASE_URL, ""),
                    CONF_SCAN_INTERVAL: entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
                "speakers": speakers,
            }
        )
    connection.send_result(msg["id"], {"accounts": accounts, "now": time.time()})


def _platform(key: str) -> str:
    return {
        "media_player": "media_player",
        "mic_mute": "switch",
        "restart": "button",
        "refresh": "button",
        "online": "binary_sensor",
    }.get(key, "sensor")


@websocket_api.websocket_command(
    {vol.Required("type"): "maika_direct/settings/get", vol.Required("serial"): str}
)
@websocket_api.async_response
async def ws_get_settings(hass: HomeAssistant, connection, msg) -> None:
    _, coord = _find(hass, msg["serial"])
    dev = dict(coord.data[msg["serial"]])
    client = coord.client
    try:
        if dev.get("id") is not None:
            dev.update(await client.async_get_speaker(dev["id"]))
        voices = _voice_options(await client.async_get_tts_voices())
    except MaikaError as err:
        connection.send_error(msg["id"], "maika_error", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "writable": dev.get("id") is not None,
            "values": {
                "name": dev.get("name") or "",
                "calling_name": dev.get("calling_name") or "",
                "address": dev.get("address") or "",
                "wakeword_sensitivity_level": dev.get("wakeword_sensitivity_level"),
                "wakeword_response_type": dev.get("wakeword_response_type"),
                "tts_voice": _current_voice(dev),
            },
            "voices": voices,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "maika_direct/settings/set",
        vol.Required("serial"): str,
        vol.Required("changes"): {vol.In(sorted(WRITABLE_FIELDS)): vol.Any(str, None)},
    }
)
@websocket_api.async_response
async def ws_set_settings(hass: HomeAssistant, connection, msg) -> None:
    serial = msg["serial"]
    _, coord = _find(hass, serial)
    dev = coord.data[serial]
    changes = {k: v.strip() for k, v in msg["changes"].items() if isinstance(v, str) and v.strip()}
    if dev.get("id") is None:
        connection.send_error(msg["id"], "not_writable", "Loa chưa có ID nội bộ từ REST")
        return
    if not changes:
        connection.send_result(msg["id"], {"ok": True})
        return
    try:
        await coord.client.async_update_speaker(dev["id"], serial, changes)
    except (MaikaError, ValueError) as err:
        connection.send_error(msg["id"], "maika_error", str(err))
        return
    await coord.async_request_refresh()
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "maika_direct/options/set",
        vol.Required("entry_id"): str,
        vol.Required(CONF_MEDIA_BASE_URL): str,
        vol.Required(CONF_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
    }
)
@callback
def ws_set_options(hass: HomeAssistant, connection, msg) -> None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Không tìm thấy tài khoản")
        return
    base = msg[CONF_MEDIA_BASE_URL].strip().rstrip("/")
    if base and not base.startswith(("http://", "https://")):
        connection.send_error(msg["id"], "invalid_url", "URL phải bắt đầu bằng http:// hoặc https://")
        return
    # triggers the update listener -> entry reload
    hass.config_entries.async_update_entry(
        entry, options={CONF_MEDIA_BASE_URL: base, CONF_SCAN_INTERVAL: msg[CONF_SCAN_INTERVAL]}
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "maika_direct/send_text",
        vol.Required("serial"): str,
        vol.Required("text"): vol.All(str, vol.Length(min=1, max=500)),
    }
)
@websocket_api.async_response
async def ws_send_text(hass: HomeAssistant, connection, msg) -> None:
    _, coord = _find(hass, msg["serial"])
    try:
        await coord.client.async_send_text(msg["serial"], msg["text"].strip())
    except MaikaError as err:
        connection.send_error(msg["id"], "maika_error", str(err))
        return
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "maika_direct/cast",
        vol.Required("serial"): str,
        vol.Required("url"): str,
    }
)
@websocket_api.async_response
async def ws_cast(hass: HomeAssistant, connection, msg) -> None:
    url = msg["url"].strip()
    if not url.startswith(("http://", "https://")):
        connection.send_error(msg["id"], "invalid_url", "Chỉ hỗ trợ URL http(s)")
        return
    _, coord = _find(hass, msg["serial"])
    try:
        await coord.client.async_cast(msg["serial"], url)
    except MaikaError as err:
        connection.send_error(msg["id"], "maika_error", str(err))
        return
    connection.send_result(msg["id"], {"ok": True})
