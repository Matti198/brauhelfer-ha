"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import brauhelfer_db as db
from .const import (
    CONF_BACKUPS,
    CONF_INTERVAL,
    CONF_MAX_AGE,
    CONF_PATH,
    DEFAULT_BACKUPS,
    DEFAULT_INTERVAL,
    DEFAULT_MAX_AGE,
    DEFAULT_PATH,
    DOMAIN,
)


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    def sug(key: str) -> dict[str, Any]:
        return {"suggested_value": options[key]} if options.get(key) else {}

    return vol.Schema(
        {
            vol.Required(CONF_INTERVAL, default=options.get(CONF_INTERVAL, DEFAULT_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=1440, step=15, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MAX_AGE, default=options.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=1440, step=15, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_BACKUPS, default=options.get(CONF_BACKUPS, DEFAULT_BACKUPS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=200, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    out = dict(user_input)
    for key in (CONF_INTERVAL, CONF_MAX_AGE, CONF_BACKUPS):
        if key in out:
            out[key] = int(out[key])
    return out


class BrauhelferConfigFlow(ConfigFlow, domain=DOMAIN):
    """Datenbankpfad abfragen und prüfen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            path = user_input[CONF_PATH].strip()
            await self.async_set_unique_id(path)
            self._abort_if_unique_id_configured()
            try:
                version = await self.hass.async_add_executor_job(db.validate, path)
            except db.SchemaError as err:
                errors["base"] = "schema"
                placeholders["error"] = str(err)
            except db.BrauhelferError as err:
                errors[CONF_PATH] = "not_found" if "nicht gefunden" in str(err) else "invalid"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(
                    title="Kleiner Brauhelfer",
                    data={CONF_PATH: path},
                    options={"db_version_at_setup": version},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PATH, default=(user_input or {}).get(CONF_PATH, DEFAULT_PATH)): str}
            ),
            errors=errors,
            description_placeholders=placeholders or {"error": ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BrauhelferOptionsFlow()


class BrauhelferOptionsFlow(OptionsFlow):
    """RAPT-Pill-Entitäten, Intervall und Sicherungen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(_clean(user_input))
            return self.async_create_entry(data=options)
        return self.async_show_form(step_id="init", data_schema=_options_schema(dict(self.config_entry.options)))
