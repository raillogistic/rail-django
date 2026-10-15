import pytest

from rail_django.http.views.audit import LogViewerAPIView

pytestmark = pytest.mark.unit


def test_log_tail_reads_only_requested_suffix(tmp_path):
    log_path = tmp_path / "django.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert LogViewerAPIView()._tail(log_path, 2) == ["two\n", "three\n"]
