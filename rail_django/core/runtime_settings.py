"""
Shared runtime settings for security and performance.

This module consolidates security and performance configuration into a single
dataclass so callers can rely on one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config_proxy import get_settings_proxy


@dataclass
class RuntimeSettings:
    # Security settings
    enable_authentication: bool = True
    enable_authorization: bool = True
    enable_rate_limiting: bool = False
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000
    enable_query_depth_limiting: bool = True
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_csrf_protection: bool = True
    enable_cors: bool = True
    enable_field_permissions: bool = True
    enable_object_permissions: bool = True
    enable_input_validation: bool = True
    enable_sql_injection_protection: bool = True
    enable_xss_protection: bool = True
    input_allow_html: bool = False
    input_allowed_html_tags: List[str] = field(
        default_factory=lambda: [
            "p",
            "br",
            "strong",
            "em",
            "u",
            "ol",
            "ul",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
        ]
    )
    input_allowed_html_attributes: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "*": ["class"],
            "a": ["href", "title"],
            "img": ["src", "alt", "width", "height"],
        }
    )
    input_max_string_length: Optional[int] = None
    input_truncate_long_strings: bool = False
    input_failure_severity: str = "high"
    input_pattern_scan_limit: int = 10000
    session_timeout_minutes: int = 30
    max_file_upload_size: int = 10 * 1024 * 1024
    allowed_file_types: List[str] = field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".pdf", ".txt"]
    )

    # Performance settings
    enable_query_optimization: bool = True
    enable_select_related: bool = True
    enable_prefetch_related: bool = True
    enable_only_fields: bool = True
    enable_defer_fields: bool = False
    enable_dataloader: bool = True
    dataloader_batch_size: int = 100
    max_query_depth: int = 10
    max_query_complexity: int = 1000
    enable_query_cost_analysis: bool = False
    query_timeout: int = 30

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "RuntimeSettings":
        proxy = get_settings_proxy(schema_name)
        security_settings = proxy.get("security_settings", {}) or {}
        performance_settings = proxy.get("performance_settings", {}) or {}

        merged: Dict[str, Any] = {}
        if isinstance(security_settings, dict):
            merged.update(security_settings)
        if isinstance(performance_settings, dict):
            merged.update(performance_settings)

        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged.items() if k in valid_fields}
        return cls(**filtered_settings)
