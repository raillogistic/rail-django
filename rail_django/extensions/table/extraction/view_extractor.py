"""Saved view extraction for default presets."""


def extract_default_view(table_config: dict) -> dict:
    return {
        "name": "Default",
        "isDefault": True,
        "isPublic": False,
        "config": {
            "columns": [column.get("id") for column in table_config.get("columns", [])],
            "ordering": table_config.get("defaultSort", []),
        },
    }
