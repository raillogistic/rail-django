"""Feature flags and extension settings for table v3."""

from django.conf import settings


def is_table_v3_enabled() -> bool:
    return bool(getattr(settings, "TABLE_V3_ENABLED", True))


def table_v3_realtime_enabled() -> bool:
    return bool(getattr(settings, "TABLE_V3_REALTIME_ENABLED", True))
