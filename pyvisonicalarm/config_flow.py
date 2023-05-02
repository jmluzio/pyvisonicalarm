"""
Config Flow for Visonic Alarm.
@msp1974
"""
from typing import Any
import uuid
import voluptuous as vol
from pyvisonicalarm import alarm as VisonicAlarm
from pyvisonicalarm.exceptions import LoginTemporaryBlockedError

from homeassistant import config_entries, exceptions
from homeassistant.helpers.selector import selector
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_CODE,
    CONF_UUID,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_PANEL_ID,
    CONF_PARTITION,
    CONF_PIN_REQUIRED_ARM,
    CONF_PIN_REQUIRED_DISARM,
    DOMAIN,
    DEFAUL_SCAN_INTERVAL,
)

import logging

_LOGGER = logging.getLogger(__name__)

USER_DATA_SCHEMA = {
    vol.Required(CONF_HOST, default=""): str,
    vol.Required(CONF_EMAIL, default=""): str,
    vol.Required(CONF_PASSWORD): str,
}


def get_unique_id(wiser_id: str):
    return str(f"{DOMAIN}-{wiser_id}")


@config_entries.HANDLERS.register(DOMAIN)
class VisonicAlarmFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Visonic Alarm configuration method.
    The schema version of the entries that it creates
    Home Assistant will call your migrate method if the version changes
    (this is not implemented yet)
    """

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the wiser flow."""
        self.discovery_info = {}
        self.user_session = None
        self.alarm: VisonicAlarm = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VisonicAlarmOptionsFlowHandler(config_entry)

    async def validate_user_login(self, data):
        """Validate the user input allows us to connect.
        Data has the keys from DATA_SCHEMA with values provided by the user.
        """
        print(f"USER - {data}")
        self.alarm = VisonicAlarm.Setup(
            data[CONF_HOST],
            data[CONF_UUID],
        )

        try:
            user_token = await self.hass.async_add_executor_job(
                self.alarm.authenticate,
                data[CONF_EMAIL],
                data[CONF_PASSWORD],
            )
            return user_token
        except Exception as ex:
            raise Exception(f"Alarm cannot connect. Error is {ex}")

    async def validate_panel_login(self, data):
        print(f"PANEL - {data}")
        session_token = await self.hass.async_add_executor_job(
            self.alarm.panel_login, data[CONF_PANEL_ID], data[CONF_CODE]
        )
        return session_token

    async def async_step_user(self, user_input=None):
        """
        Handle a Wiser Heat Hub config flow start.
        Manage device specific parameters.
        """
        errors = {}
        if user_input is not None:
            try:
                user_input[
                    CONF_UUID
                ] = "a11e5472-def1-11ed-b5ea-0242ac120002"  # str(uuid.uuid4())
                self.user_session = await self.validate_user_login(user_input)
            except LoginTemporaryBlockedError as ex:
                errors["base"] = "temporary_block"
            except:
                # TODO - Improve errors
                errors["base"] = "unknown"
                _LOGGER.error(f"Unable to connect - {ex}")

            if "base" not in errors:
                self.user_pass = user_input
                return await self.async_step_panel()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(USER_DATA_SCHEMA),
            errors=errors,
        )

    async def async_step_panel(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input:
            try:
                # Validate panel login
                session_token = await self.validate_panel_login(user_input)
                user_input["partition"] = -1
                print(f"USER INPUT PANEL FORM - {user_input}")
            except LoginTemporaryBlockedError as ex:
                errors["base"] = "temporary_block"
            except:
                # TODO - Improve errors
                errors["base"] = "unknown"
                _LOGGER.error(f"Unable to connect - {ex}")

            if "base" not in errors:
                await self.async_set_unique_id(
                    f"{self.user_pass[CONF_EMAIL]}-{user_input[CONF_PANEL_ID]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_PANEL_ID],
                    data=({**self.user_pass, **user_input}),
                )
        else:
            # Get panels
            panels = await self.hass.async_add_executor_job(self.alarm.get_panels)
            option_list = []
            for panel in panels:
                option = {
                    "label": f"{panel.alias}({panel.panel_serial})",
                    "value": panel.panel_serial,
                }
                option_list.append(option)

            data_schema = {
                vol.Required(CONF_PANEL_ID, default=panels[0].panel_serial): selector(
                    {"select": {"options": option_list}}
                ),
                vol.Required(CONF_CODE, default="0000"): str,
            }

            return self.async_show_form(
                step_id="panel",
                data_schema=vol.Schema(data_schema),
            )


class VisonicAlarmOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for wiser hub."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        """Handle options flow."""
        if user_input is not None:
            options = self.config_entry.options | user_input
            return self.async_create_entry(title="", data=options)

        data_schema = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAUL_SCAN_INTERVAL
                ),
            ): selector(
                {
                    "number": {
                        "min": 5,
                        "max": 600,
                        "step": 1,
                        "unit_of_measurement": "s",
                        "mode": "box",
                    }
                }
            ),
            vol.Required(
                CONF_PIN_REQUIRED_ARM,
                default=self.config_entry.options.get(CONF_PIN_REQUIRED_ARM, True),
            ): bool,
            vol.Required(
                CONF_PIN_REQUIRED_DISARM,
                default=self.config_entry.options.get(CONF_PIN_REQUIRED_DISARM, True),
            ): bool,
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(data_schema))
