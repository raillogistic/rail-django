"""
Unit tests for MFA manager utilities.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from rail_django.extensions.mfa import MFADevice, MFABackupCode, MFAManager

pytestmark = pytest.mark.unit


class _DeviceManager:
    def __init__(self, devices):
        self._devices = list(devices)

    def filter(self, **kwargs):
        devices = self._devices
        if "is_active" in kwargs:
            devices = [
                device for device in devices if device.is_active == kwargs["is_active"]
            ]
        if "id" in kwargs:
            devices = [device for device in devices if device.id == kwargs["id"]]
        return _DeviceManager(devices)

    def __iter__(self):
        return iter(self._devices)


class _Device:
    def __init__(self, user, device_id, *, device_type="sms", is_active=True):
        self.user = user
        self.user_id = user.id
        self.id = device_id
        self.device_type = device_type
        self.phone_number = "+123456789"
        self.is_active = is_active
        self.last_used = None

    def verify_token(self, token, **kwargs):
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
    sent = {}

    def send(phone, token):
        sent["token"] = token
        return True

    manager._send_sms = send

    user = _User(1, [])
    device = _Device(user, 10)
    user.mfa_devices = _DeviceManager([device])
    key = manager._sms_cache_key(user.id, device.id)
    cache.delete(key)

    assert manager.send_sms_token(device) is True
    assert cache.get(key) is not None
    assert manager.verify_mfa_token(user, sent["token"], device_id=device.id) is True
    assert cache.get(key) is None


@pytest.mark.django_db
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
def test_backup_codes_are_hashed_and_single_use():
    user = get_user_model().objects.create_user(username="mfa-user")
    device = MFADevice.objects.create(
        user=user,
        device_name="authenticator",
        device_type="totp",
        secret_key="secret",
        is_active=True,
    )
    manager = MFAManager()
    manager.backup_codes_count = 1

    code = manager.generate_backup_codes(device)[0]
    stored = MFABackupCode.objects.get(device=device)

    assert stored.code != code
    assert manager.verify_mfa_token(user, code, device_id=device.id) is True
    assert manager.verify_mfa_token(user, code, device_id=device.id) is False
