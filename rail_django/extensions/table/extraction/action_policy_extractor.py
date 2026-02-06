"""Action policy extraction."""


def extract_action_policies(model_cls) -> list[dict]:
    _ = model_cls
    return [
        {"id": "create", "enabled": True},
        {"id": "update", "enabled": True},
        {"id": "delete", "enabled": True},
        {"id": "bulkEdit", "enabled": True},
    ]
