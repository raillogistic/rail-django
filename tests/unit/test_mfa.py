"""
Unit tests for MFA manager utilities.
"""

import pytest

from rail_django.extensions.mfa import MFAManager

pytestmark = pytest.mark.unit


class _DeviceManager:
    def __init__(self, devices):
        self._devices = list(devices)

    def filter(self, **kwargs):
        devices = self._devices
        if "is_active" in kwargs:
            devices = [device for device in devices if device.is_active == kwargs["is_active"]]
        if "id" in kwargs:
            devices = [device for device in devices if device.id == kwargs["id"]]
        return _DeviceManager(devices)

    def __iter__(self):
        return iter(self._devices)


class _Device:
    def __init__(self, user, device_id, *, device_type="sms", is_active=True):
        self.user = user
        self.id = device_id
        self.device_type = device_type
        self.phone_number = "+123456789"
        self.is_active = is_active
        self.last_used = None

    def verify_token(self, token):
        return False

    def save(self):
        return None


class _User:
    def __init__(self, user_id, devices):
        self.id = user_id
        self.mfa_devices = _DeviceManager(devices)
        self.is_staff = False
        self.is_superuser = False


def test_generate_device_fingerprint_is_stable():
    manager = MFAManager()
    first = manager.generate_device_fingerprint("127.0.0.1", "agent")
    second = manager.generate_device_fingerprint("127.0.0.1", "agent")
    assert first == second
    assert manager.generate_device_fingerprint("127.0.0.1", "agent2") != first


def test_sms_token_verification_round_trip():
    manager = MFAManager()
    manager._send_sms = lambda phone, token: True

    user = _User(1, [])
    device = _Device(user, 10)
    user.mfa_devices = _DeviceManager([device])

    assert manager.send_sms_token(device) is True
    token, _expires = manager._sms_tokens[f"sms_token_{user.id}_{device.id}"]
    assert manager.verify_mfa_token(user, token, device_id=device.id) is True
    assert f"sms_token_{user.id}_{device.id}" not in manager._sms_tokens

