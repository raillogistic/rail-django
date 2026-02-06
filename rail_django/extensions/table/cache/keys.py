"""Cache key utilities."""


def table_bootstrap_key(app: str, model: str) -> str:
    return f"table:bootstrap:{app}:{model}"


def table_rows_key(app: str, model: str, page: int, page_size: int) -> str:
    return f"table:rows:{app}:{model}:{page}:{page_size}"
