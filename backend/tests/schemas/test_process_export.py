import pytest
from pydantic import ValidationError

from app.schemas.process import ProcessExportRequest


def test_process_export_request_accepts_mermaid_format():
    assert ProcessExportRequest(format="mermaid").format == "mermaid"


def test_process_export_request_rejects_yaml_for_now():
    with pytest.raises(ValidationError):
        ProcessExportRequest(format="yaml")
