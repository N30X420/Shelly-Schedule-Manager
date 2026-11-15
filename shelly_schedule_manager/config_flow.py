"""Add one Shelly through the UI. Repeat flow to add more devices."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .api import ShellyAPIError, ShellyClient
from .const import DOMAIN


class ShellyScheduleFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input["host"]).strip().removeprefix("http://").rstrip("/")
            # Prevent arbitrary URL / path injection; support DNS names, IPv4 and host:port.
            if not host or any(c in host for c in "/?#@ "):
                errors["host"] = "invalid_host"
            else:
                client = ShellyClient(host, user_input["username"], user_input["password"])
                try:
                    await self.hass.async_add_executor_job(client.list_jobs)
                except ShellyAPIError:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(host.lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input["name"],
                        data={**user_input, "host": host},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=""): str,
                    vol.Required("host", default=""): str,
                    vol.Required("username", default="admin"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )
