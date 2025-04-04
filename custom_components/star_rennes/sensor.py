"""
Sensor for checking the status of NYC MTA Subway lines.
"""

import logging
import re
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import requests
import urllib.parse
from pprint import pprint
from inspect import getmembers
from datetime import datetime
import pytz

import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)

from homeassistant.util import Throttle

from .const import DOMAIN, STOP_NAME_KEY, ICON_URL_KEY, DESTINATION_KEY, LINE_NAME_KEY, LINE_KEY, SENS_KEY

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

DATASET_ID = "tco-bus-circulation-passages-tr"
URL_BASE = "https://data.explore.star.fr/api/explore/v2.1/catalog/datasets/" + \
    DATASET_ID+"/records?"
ICONS = "https://raw.githubusercontent.com/iicky/homeassistant-mta-subway/main/icons"


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(LINE_KEY): cv.string,
    vol.Required(SENS_KEY): cv.string,
    vol.Required(STOP_NAME_KEY): cv.string,
    vol.Required(LINE_NAME_KEY): cv.string,
    vol.Optional(DESTINATION_KEY): cv.string,
    vol.Optional(ICON_URL_KEY): cv.string
})


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
                            ):
    """Configuration des entités sensor à partir de la configuration
    ConfigEntry passée en argument"""

    _LOGGER.debug("Calling async_setup_entry entry=%s", entry)

    print("___________________________")

    pprint(entry.data)
    entity = MTASubwaySensor(
        entry.data[LINE_KEY], entry.data[LINE_NAME_KEY], entry.data[SENS_KEY], entry.data[STOP_NAME_KEY], entry.data[DESTINATION_KEY], entry.data[ICON_URL_KEY])

    async_add_entities([entity], True)

    platform = async_get_current_platform()


def setup_platform(hass, config, add_devices, discovery_info=None):
    sensors = [
        MTASubwaySensor(config.get(LINE_KEY),
                        config.get(LINE_NAME_KEY),
                        config.get(SENS_KEY),
                        config.get(STOP_NAME_KEY),
                        config.get(DESTINATION_KEY),
                        config.get(ICON_URL_KEY))

    ]
    for sensor in sensors:
        sensor.update()
    add_devices(sensors, True)


class MTASubwaySensor(Entity):
    def __init__(self, name, line_name, sens, stop, destination, icon_url):
        self._name = str(line_name)+" → "+str(destination)
        self._line = name
        self._line_name = line_name
        self._destination = destination
        self._sens = sens
        self._stop = stop
        self._icon_url = icon_url
        self._data = StarServiceData()
        self._next_departure = None
        self._state = None
        self.state_class = SensorStateClass.MEASUREMENT
        self.native_value = None
        self.device_class = SensorDeviceClass.TIMESTAMP

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def entity_picture(self):
        return self._icon_url

    @property
    def icon(self):
        return "mdi:subway"

    @property
    def extra_state_attributes(self):
        attrs = {}
        return attrs

    def update(self):
        self._data.update(self._line, self._sens, self._stop)
        result = self._data.data["results"]
        departure_list = []
        nextDt = None
        for departure_time in result:
            departure_date_string = (departure_time["depart"])
            nextDt = datetime.fromisoformat(departure_date_string).astimezone(
                pytz.timezone("Europe/Paris"))
            minute_left = (
                nextDt - datetime.now().astimezone(pytz.timezone("Europe/Paris"))).total_seconds() / 60
            departure_list.append(int(minute_left))

        self._next_departure = departure_list

        if (nextDt == None):
            self._state = None
        else:
            self._state = nextDt


class StarServiceData(object):
    def __init__(self):
        self.data = None

    @Throttle(SCAN_INTERVAL)
    def update(self, line, sens, stop):
        URL_PARAM = {
            "select": "depart",
            "where": "idligne=\""+str(line)+"\" AND sens=\""+str(sens)+"\" AND nomarret=\""+stop+"\"",
            "order_by": "departtheorique ASC",
            "limit": "1",
            "lang": "fr",
            "timezone": "Europe/Paris"
        }

        pprint("URL = "+URL_BASE + urllib.parse.urlencode(URL_PARAM))
        response = requests.get(URL_BASE + urllib.parse.urlencode(URL_PARAM))
        if response.status_code != 200:
            _LOGGER.warning("Invalid response from goodservice.io API.")
        else:
            self.data = response.json()
