from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_project_template_nginx_has_edge_rate_limits():
    repo_root = Path(__file__).resolve().parents[2]
    nginx_config = (
        repo_root / "rail_django/scaffolding/project_template/deploy/nginx/default.conf"
    )

    contents = nginx_config.read_text(encoding="utf-8")

    assert "limit_req_zone $binary_remote_addr zone=rail_graphql_per_ip" in contents
    assert "limit_conn_zone $binary_remote_addr zone=rail_conn_per_ip" in contents
    assert "limit_req_status 429;" in contents
    assert "limit_req zone=rail_graphql_per_ip burst=40 nodelay;" in contents
    assert "limit_conn rail_conn_per_ip 20;" in contents
