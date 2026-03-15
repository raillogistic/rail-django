"""Progressive loading helpers for table bootstrapping."""

from __future__ import annotations

from .user_state import DEFAULT_TABLE_PAGE_SIZE


def build_minimal_bootstrap(payload: dict) -> dict:
    table_config = payload.get("tableConfig") or {}
    return {
        "configVersion": payload.get("configVersion", "1"),
        "essentialConfig": {
            "columns": table_config.get("columns", []),
            "defaultSort": table_config.get("defaultSort", []),
            "quickSearchFields": table_config.get("quickSearchFields", []),
            "pagination": table_config.get(
                "pagination",
                {"defaultPageSize": DEFAULT_TABLE_PAGE_SIZE},
            ),
        },
        "initialState": payload.get("initialState", {}),
        "permissions": payload.get("permissions", {}),
    }
