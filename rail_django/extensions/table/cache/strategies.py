"""Cache strategy metadata."""


def stale_while_revalidate(max_age: int = 30, stale_window: int = 120) -> dict:
    return {"maxAge": max_age, "staleWhileRevalidate": stale_window}
