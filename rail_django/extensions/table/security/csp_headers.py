"""CSP helper for table views."""

TABLE_CSP_POLICY = "default-src 'self'; object-src 'none'; frame-ancestors 'none'"


def csp_headers() -> dict[str, str]:
    return {"Content-Security-Policy": TABLE_CSP_POLICY}
