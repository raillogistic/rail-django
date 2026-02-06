"""Cache invalidation helpers."""


def invalidation_tags(app: str, model: str) -> list[str]:
    return [f"table:{app}:{model}"]
