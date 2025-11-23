"""
Simple fallback configuration for Midea integration
Provides basic functionality when main authentication fails
"""

import logging

_LOGGER = logging.getLogger(__name__)

class SimpleMideaDevice:
    """
    Simple mock device for basic functionality when API is unavailable
    """

    def __init__(self, device_id, name="Midea Dehumidifier"):
        self.device_id = device_id
        self.name = name
        self.is_on = False
        self.target_humidity = 50
        self.current_humidity = 45
        self.mode = "auto"
        self.fan_speed = "medium"

    def turn_on(self):
        self.is_on = True
        return True

    def turn_off(self):
        self.is_on = False
        return True

    def set_humidity(self, humidity):
        self.target_humidity = humidity
        return True

    def set_mode(self, mode):
        self.mode = mode
        return True

    def set_fan_speed(self, speed):
        self.fan_speed = speed
        return True

def create_simple_device():
    """Create a simple mock device for testing"""
    return SimpleMideaDevice("test-device", "Test Midea Dehumidifier")