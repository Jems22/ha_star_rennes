import logging
import requests
import urllib.parse
import voluptuous as vol

from typing import Any
from pprint import pprint
from .const import DOMAIN, STOP_NAME_KEY, LINE_KEY, LINE_NAME_KEY, DESTINATION_KEY, ICON_URL_KEY, SENS_KEY


from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import selector
from homeassistant.util import Throttle
from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)
SERVICE_URL_BASE = "https://data.explore.star.fr/api/explore/v2.1/catalog/datasets/"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    # Store received data from service
    _receivedLineList: dict = {}
    _receivedStopList: dict = {}
    _receivedDestinationList: dict = {}
    _user_inputs: dict = {}

    # Initial step
    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            # Get the line list
            lineList = await self.hass.async_add_executor_job(self._getLineList)
            data_schema = {
                vol.Required(LINE_KEY): selector({
                    "select": {
                        "options": lineList,
                        "mode": "dropdown"
                    }
                }),
            }

            return self.async_show_form(step_id="user", data_schema=vol.Schema(data_schema))

        self._user_inputs.update(user_input)
        return await self.async_step_stop()

    # Second step: Bus stop
    async def async_step_stop(self, user_input: dict | None = None) -> FlowResult:
        if (STOP_NAME_KEY not in self._user_inputs):
            lineName = self._user_inputs[LINE_KEY]
            lineId = self._receivedLineList[lineName]
            lineList = await self.hass.async_add_executor_job(self._getStopList, lineId)
            data_schema = {
                vol.Required(STOP_NAME_KEY): selector({
                    "select": {
                        "options": lineList,
                        "mode": "dropdown"
                    }
                }),
            }
            return self.async_show_form(step_id="user", data_schema=vol.Schema(data_schema))

        return await self.async_step_destination()

    # Last step: Destination
    async def async_step_destination(self, user_input: dict | None = None) -> FlowResult:
        if (DESTINATION_KEY not in self._user_inputs):
            lineName = self._user_inputs[LINE_KEY]
            lineId = self._receivedLineList[lineName]
            destinationList = await self.hass.async_add_executor_job(self._getDestinationList, lineId)
            data_schema = vol.Schema(
                {
                    vol.Required(DESTINATION_KEY): selector({
                        "select": {
                            "options": destinationList,
                            "mode": "dropdown"
                        }
                    }),
                }
            )
            return self.async_show_form(step_id="user", data_schema=data_schema)

        try:
            self.hass.data.setdefault(DOMAIN, {})
            lineName = self._user_inputs[LINE_KEY]
            lineId = self._receivedLineList[lineName]
            icon_url = await self.hass.async_add_executor_job(self._getIconUrl, lineId)
            sensor_data = {
                LINE_KEY: self._receivedLineList[self._user_inputs[LINE_KEY]],
                LINE_NAME_KEY: self._user_inputs[LINE_KEY],
                DESTINATION_KEY: self._user_inputs[DESTINATION_KEY],
                SENS_KEY: self._receivedDestinationList[self._user_inputs[DESTINATION_KEY]],
                STOP_NAME_KEY: self._user_inputs[STOP_NAME_KEY],
                ICON_URL_KEY: icon_url
            }
            return self.async_create_entry(title=self._user_inputs[LINE_KEY]+" ↦ "+self._user_inputs[DESTINATION_KEY], data=sensor_data)
        except Exception:
            _LOGGER.exception("Unexpected exception")

    # --
    # Get information from STAR services
    # --

    # Get the line list

    def _getLineList(self):
        self._receivedLineList.clear()
        lineList = []
        offset = 0
        limit = 100
        URL_BASE = SERVICE_URL_BASE + "tco-bus-topologie-lignes-td/records?"
        while True:
            URL_PARAM = {
                "select": "id,nomcourt",
                "offset": offset,
                "order_by": "id ASC",
                "limit": limit,
            }
            response = requests.get(
                URL_BASE + urllib.parse.urlencode(URL_PARAM))
            if response.status_code != 200:
                _LOGGER.warning("Invalid response from service API.")
                break
            else:
                resultList = response.json()["results"]

                for result in resultList:
                    lineList.append(result["nomcourt"])
                    self._receivedLineList[result["nomcourt"]] = result["id"]

                if len(resultList) < limit:
                    break
                offset += limit

        return lineList

    # Get the bus stop list
    def _getStopList(self, idLine):
        self._receivedStopList.clear()
        stopList = []
        offset = 0
        limit = 100
        URL_BASE = SERVICE_URL_BASE + "tco-bus-topologie-dessertes-td/records?"

        while True:
            URL_PARAM = {
                "select": "idarret,nomarret",
                "where": "idligne=\""+idLine+"\"",
                "offset": offset,
                "order_by": "nomarret ASC",
                "limit": limit,
            }

            response = requests.get(
                URL_BASE + urllib.parse.urlencode(URL_PARAM))
            if response.status_code != 200:
                _LOGGER.warning("Invalid response from service API.")
                break
            else:
                resultList = response.json()["results"]

                for result in resultList:
                    if not result["nomarret"] in stopList:
                        stopList.append(result["nomarret"])
                        self._receivedStopList[result["nomarret"]
                                               ] = result["idarret"]

                if len(resultList) < limit:
                    break
                offset += limit

        return stopList

    # Get the destination list
    def _getDestinationList(self, idLine):
        self._receivedDestinationList.clear()
        destinationList = []
        offset = 0
        limit = 100
        URL_BASE = SERVICE_URL_BASE + "tco-bus-topologie-parcours-td/records?"

        while True:
            URL_PARAM = {
                "select": "idarretarrivee,nomarretarrivee,sens",
                "where": "idligne=\""+idLine+"\"",
                "offset": offset,
                "order_by": "nomarretarrivee ASC",
                "limit": limit,
            }

            response = requests.get(
                URL_BASE + urllib.parse.urlencode(URL_PARAM))
            if response.status_code != 200:
                _LOGGER.warning("Invalid response from service API.")
                break
            else:
                resultList = response.json()["results"]

                for result in resultList:
                    if not result["nomarretarrivee"] in destinationList:
                        destinationList.append(result["nomarretarrivee"])
                        self._receivedDestinationList[result["nomarretarrivee"]
                                                      ] = result[SENS_KEY]

                if len(resultList) < limit:
                    break
                offset += limit

        return destinationList

    # Get the icon url for the selected line
    def _getIconUrl(self, idLine):
        image_url = ""
        limit = 1
        URL_BASE = SERVICE_URL_BASE + "tco-bus-lignes-pictogrammes-dm/records?"
        URL_PARAM = {
            "select": "idligne,image",
            "where": "idligne=\""+idLine+"\"",
            "limit": limit,
        }

        response = requests.get(
            URL_BASE + urllib.parse.urlencode(URL_PARAM))
        if response.status_code != 200:
            _LOGGER.warning("Invalid response from service API.")
        else:
            resultList = response.json()["results"]
            if (len(resultList) > 0):
                image_url = resultList[0]["image"]["url"]

        return image_url

# Query Star API.


class StarServiceData(object):

    def __init__(self):
        self.data = None

    async def update(self):
        URL_BASE = SERVICE_URL_BASE + "tco-bus-topologie-lignes-td/records"
        response = requests.get(URL_BASE)
        if response.status_code != 200:
            _LOGGER.warning("Invalid response from service API.")
        else:
            resultList = response.json()["results"]
            lineList = []
            for result in resultList:
                lineList.append(result["nomlong"])

            self.data = lineList
