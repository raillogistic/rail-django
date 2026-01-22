"""
Unit tests for virus scanning helpers using the mock scanner.
"""

import tempfile
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from rail_django.extensions.virus_scanner import ThreatDetected, VirusScanner

pytestmark = pytest.mark.unit


def _settings(**overrides):
    base = {
        "VIRUS_SCANNING_ENABLED": True,
        "VIRUS_SCANNER_TYPE": "mock",
        "MOCK_SCANNER_SIMULATE_THREATS": False,
        "MOCK_SCANNER_THREAT_PATTERNS": ["virus"],
        "QUARANTINE_PATH": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_mock_scanner_allows_clean_file():
    scanner = VirusScanner(_settings())
    upload = SimpleUploadedFile("clean.txt", b"hello", content_type="text/plain")

    result = scanner.scan_uploaded_file(upload)
    assert result.is_clean is True


def test_mock_scanner_quarantines_threat():
    with tempfile.TemporaryDirectory() as temp_dir:
        scanner = VirusScanner(
            _settings(
                MOCK_SCANNER_SIMULATE_THREATS=True,
                QUARANTINE_PATH=temp_dir,
            )
        )
        upload = SimpleUploadedFile("virus_file.txt", b"malware", content_type="text/plain")

        with pytest.raises(ThreatDetected):
            scanner.scan_uploaded_file(upload)

        quarantine_files = scanner.get_quarantine_files()
        assert quarantine_files

        removed = scanner.delete_quarantine_file(quarantine_files[0]["quarantine_path"])
        assert removed is True


