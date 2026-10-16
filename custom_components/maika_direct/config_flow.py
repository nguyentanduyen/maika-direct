"""Config flow for MAIKA Direct."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import MaikaAuthError, MaikaClient, MaikaError, normalize_login
from .const import (
    CONF_CLIENT_ID,
    CONF_LOGIN,
    CONF_MEDIA_BASE_URL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class MaikaDirectConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _try_login(self, login: str, password: str, client_id: str, session_id: str):
        client = MaikaClient(
            async_get_clientsession(self.hass), login, password, client_id, session_id
        )
        await client.async_login()
        speakers = await client.async_list_speakers()
        return client, speakers

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            login = normalize_login(user_input[CONF_LOGIN])
            client_id, session_id = str(uuid4()), str(uuid4())
            try:
                client, speakers = await self._try_login(
                    login, user_input[CONF_PASSWORD], client_id, session_id
                )
            except MaikaAuthError:
                errors["base"] = "invalid_auth"
            except MaikaError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(client.user_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"MAIKA ({login}) – {len(speakers)} loa",
                    data={
                        CONF_LOGIN: login,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_CLIENT_ID: client_id,
                        CONF_SESSION_ID: session_id,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOGIN): str,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._try_login(
                    entry.data[CONF_LOGIN],
                    user_input[CONF_PASSWORD],
                    entry.data[CONF_CLIENT_ID],
                    entry.data[CONF_SESSION_ID],
                )
            except MaikaAuthError:
                errors["base"] = "invalid_auth"
            except MaikaError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"login": entry.data[CONF_LOGIN]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MaikaDirectOptionsFlow()


class MaikaDirectOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base = (user_input.get(CONF_MEDIA_BASE_URL) or "").strip().rstrip("/")
            if base and not base.startswith(("http://", "https://")):
                errors[CONF_MEDIA_BASE_URL] = "invalid_url"
            else:
                return self.async_create_entry(
                    data={
                        CONF_MEDIA_BASE_URL: base,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    }
                )
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MEDIA_BASE_URL,
                        description={"suggested_value": opts.get(CONF_MEDIA_BASE_URL, "")},
                    ): str,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
                }
            ),
            errors=errors,
        )
