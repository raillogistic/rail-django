import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.unit


def test_profile_graphql_queries_reads_jsonl(tmp_path):
    query_file = tmp_path / "queries.jsonl"
    query_file.write_text(
        json.dumps(
            {
                "operationName": "NestedUsers",
                "query": "{ users { users { id } } }",
                "count": 7,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = StringIO()
    call_command(
        "profile_graphql_queries",
        query_file=[str(query_file)],
        format="json",
        stdout=out,
    )

    report = json.loads(out.getvalue())
    assert report["total_queries"] == 1
    assert report["total_observations"] == 7
    assert report["n_plus_one_risk_count"] == 1
    assert report["entries"][0]["operation_name"] == "NestedUsers"


def test_profile_graphql_queries_fail_on_risk():
    with pytest.raises(CommandError, match="Detected 1 query sample"):
        call_command(
            "profile_graphql_queries",
            query=["{ users { users { id } } }"],
            fail_on_risk=True,
            stdout=StringIO(),
        )
