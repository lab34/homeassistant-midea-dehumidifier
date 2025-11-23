"""
Custom integation based on humidifer and sensor platforms for EVA II PRO WiFi Smart Dehumidifier appliance by Midea/Inventor.
For more details please refer to the documentation at
https://github.com/barban-dev/midea_inventor_dehumidifier
"""
VERSION = '1.05'

DOMAIN = "midea_dehumidifier"
MIDEA_API_CLIENT = "midea_api_client"
MIDEA_TARGET_DEVICE = "midea_target_device"


import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

import asyncio
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

CONF_SHA256_PASSWORD = 'sha256password'
CONF_DEVICEID = 'deviceId'
CONF_SERVER_REGION = 'server_region'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SHA256_PASSWORD): cv.string,
        vol.Optional(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_SERVER_REGION, default='china'): vol.In(['china', 'europe', 'usa'])
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up client for Midea API based on configuration entries."""
    _LOGGER.info("midea_dehumidifier: initializing platform...")
    _LOGGER.debug("midea_dehumidifier: starting async_setup")

    if DOMAIN not in config:
        _LOGGER.error("midea_dehumi: cannot find midea_dehumi platform on configuration.yaml")
        return False

    from midea_inventor_lib import MideaClient

    username = config[DOMAIN].get(CONF_USERNAME)
    password = config[DOMAIN].get(CONF_PASSWORD)
    sha256password = config[DOMAIN].get(CONF_SHA256_PASSWORD)
    deviceId = config[DOMAIN].get(CONF_DEVICEID)
    server_region = config[DOMAIN].get(CONF_SERVER_REGION, 'china')

    # Auto-generate SHA256 password if plain password is provided
    if password and not sha256password:
        import hashlib
        sha256password = hashlib.sha256(password.encode('utf-8')).hexdigest()
        _LOGGER.info("midea_dehumi: auto-generated SHA256 password from plain password")

    # Apply server region configuration via monkey-patching
    if server_region == 'europe':
        _LOGGER.info("midea_dehumi: configuring for European server")
        MideaClient.SERVER_URL = "https://mp-eu-prod.appsmb.com"
        MideaClient.APP_ID = 1010
        MideaClient.APP_KEY = "ac21b9f9cbfe4ca5a88562ef25e2b768"
        # Override the login endpoint for European server
        MideaClient.LOGIN_ID_ENDPOINT = "/mas/v5/app/proxy?alias=/v1/user/login/id/get/new"
        MideaClient.LOGIN_ENDPOINT = "/mas/v5/app/proxy?alias=/mj/user/login"
    elif server_region == 'usa':
        _LOGGER.info("midea_dehumi: configuring for US server")
        # TODO: Add US server configuration when available
        MideaClient.SERVER_URL = "https://mapp.appsmb.com"
        MideaClient.APP_ID = 1017
        MideaClient.APP_KEY = "3742e9e5842d4ad59c2db887e12449f9"
    else:  # china (default)
        _LOGGER.info("midea_dehumi: configuring for Chinese server (default)")
        # Keep default values from the library
        pass
	
    #_LOGGER.debug("midea_dehumi: CONFIG PARAMS: username=%s, password=%s, sha256password=%s, deviceId=%s", username, password, sha256password, deviceId)

    if not password and not sha256password:
        _LOGGER.error("midea_dehumi: either plain-text password or password's sha256 hash should be specified in config entries.")
        return False

    # Try to use fixed client first for European server
    client = None
    use_fixed_client = (server_region == 'europe')

    if use_fixed_client:
        _LOGGER.info("midea_dehumi: using fixed client for European server")
        try:
            from .midea_client_fixed import MideaClientFixed
            client = MideaClientFixed(username, password, sha256password)
            _LOGGER.info("midea_dehumi: created fixed Midea client")
        except Exception as e:
            _LOGGER.warning(f"midea_dehumi: failed to create fixed client, falling back to original: {e}")
            use_fixed_client = False

    if not client:
        # Create original client
        client = MideaClient(username, password, sha256password)

    #Log-in to the Midea cloud Web Service and get the list of configured Midea/Inventor appliances for the user.
    _LOGGER.info("midea_dehumi: logging into Midea API Web Service...")

    if use_fixed_client:
        _LOGGER.info("midea_dehumi: using fixed client (European server)")
    else:
        _LOGGER.info("midea_dehumi: server URL=%s, APP_ID=%s", getattr(MideaClient, 'SERVER_URL', 'default'), getattr(MideaClient, 'APP_ID', 'default'))

    #res = client.login()
    res = await hass.async_add_executor_job(client.login)
    if res == -1:
        _LOGGER.error("midea-dehumi: login error - check server configuration and credentials")
        return False
    else:
        if use_fixed_client:
            sessionId = client.session_id
            _LOGGER.info("midea-dehumi: login success (fixed client), sessionId=%s", sessionId)
        else:
            sessionId = client.current["sessionId"]
            _LOGGER.info("midea-dehumi: login success, sessionId=%s", sessionId)

    appliances = {}

    #appliances = client.listAppliances()
    appliances = await hass.async_add_executor_job(client.listAppliances)
    
    appliancesStr = ""
    for a in appliances:
        appliancesStr = "[id="+a["id"]+" type="+a["type"]+" name="+a["name"]+"]"
        if a["onlineStatus"] == "1":
            appliancesStr += " is online,"
        else:
            appliancesStr += " is offline,"
        if a["activeStatus"] == "1":
            appliancesStr += " is active.\n"
        else:
            appliancesStr += " is not active.\n"
		
    _LOGGER.info("midea-dehumi: "+appliancesStr)
    
    #The first appliance having type="0xA1" is returned for default (TODO: otherwise, 'deviceId' configuration option can be used)
    targetDevice = None
    if not deviceId:
        if appliances is not None:
            for a in appliances:
                if a["type"] == "0xA1":
                    deviceId = str(a["id"])
                    targetDevice = a
    else:
        if appliances is not None:
            for a in appliances:
                if a["type"] == "0xA1" and deviceId == str(a["id"]):
                    targetDevice = a


    if targetDevice:
        _LOGGER.info("midea-dehumidifier: device type 0xA1 found.")

        hass.data[MIDEA_API_CLIENT] = client
        _LOGGER.info("midea-dehumidifier: loading humidifier entity sub-component...")
        load_platform(hass, 'humidifier', DOMAIN, {MIDEA_TARGET_DEVICE: targetDevice}, config)

        _LOGGER.info("midea-dehumidifier: loading sensor entity sub-component...")
        load_platform(hass, 'sensor', DOMAIN, {MIDEA_TARGET_DEVICE: targetDevice}, config)

        _LOGGER.info("midea_dehumidifier: platform successfuly initialized.")
        return True
    else:
        _LOGGER.warning("midea-dehumidifier: device type 0xA1 not found with API.")

        # Fallback: try to create a simple device for testing
        if server_region == 'europe':
            _LOGGER.info("midea-dehumidifier: creating fallback device for European server testing...")

            # Create a mock device for basic functionality
            try:
                from .__init__simple import SimpleMideaDevice
                mock_device = SimpleMideaDevice("fallback-device", "Midea Dehumidifier (Fallback)")

                # Create a simple target device structure
                targetDevice = {
                    "id": "fallback-device",
                    "name": "Midea Dehumidifier (Fallback)",
                    "type": "0xA1",
                    "onlineStatus": "1",
                    "activeStatus": "1",
                    "is_fallback": True
                }

                # Create a mock client
                class MockClient:
                    def __init__(self):
                        self.current = {"sessionId": "fallback-session"}
                    def listAppliances(self):
                        return [targetDevice]

                hass.data[MIDEA_API_CLIENT] = MockClient()

                _LOGGER.info("midea-dehumidifier: loading humidifier entity sub-component (fallback)...")
                load_platform(hass, 'humidifier', DOMAIN, {MIDEA_TARGET_DEVICE: targetDevice}, config)

                _LOGGER.info("midea-dehumidifier: loading sensor entity sub-component (fallback)...")
                load_platform(hass, 'sensor', DOMAIN, {MIDEA_TARGET_DEVICE: targetDevice}, config)

                _LOGGER.info("midea_dehumidifier: platform initialized with fallback device.")
                _LOGGER.warning("midea_dehumidifier: FALLBACK MODE - Device control may not work. Check API configuration.")
                return True

            except Exception as e:
                _LOGGER.error(f"midea-dehumidifier: failed to create fallback device: {e}")
                return False
        else:
            _LOGGER.error("midea-dehumidifier: device type 0xA1 not found and no fallback available.")
            return False
