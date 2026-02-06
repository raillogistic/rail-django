"""Progressive loading helpers for table bootstrapping."""

from __future__ import annotations


def build_minimal_bootstrap(payload: dict) -> dict:
    table_config = payload.get("tableConfig") or {}
    return {
        "configVersion": payload.get("configVersion", "1"),
        "essentialConfig": {
            "columns": table_config.get("columns", []),
            "defaultSort": table_config.get("defaultSort", []),
            "quickSearchFields": table_config.get("quickSearchFields", []),
            "pagination": table_config.get("pagination", {"defaultPageSize": 25}),
        },
        "permissions": payload.get("permissions", {}),
    }
