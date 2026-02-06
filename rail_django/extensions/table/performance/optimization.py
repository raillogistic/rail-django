"""Optimization hints for row resolver."""


def build_query_hints(page_size: int) -> dict:
    return {
        "prefetchNextPage": page_size <= 100,
        "recommendedPageSize": min(max(page_size, 25), 100),
    }
