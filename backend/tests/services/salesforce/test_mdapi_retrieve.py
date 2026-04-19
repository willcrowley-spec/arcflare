import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.salesforce.mdapi_retrieve import (
    MDAPIInsufficientAccessError,
    MDAPIRetrieveError,
    _extract_zip,
    _poll_retrieve,
    check_mdapi_access,
    retrieve_metadata,
)


def test_extract_zip_roundtrip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("flows/F.flow-meta.xml", b"<Flow/>")
        zf.writestr("nested/", b"")
    extracted = _extract_zip(buf.getvalue())
    assert extracted["flows/F.flow-meta.xml"] == b"<Flow/>"
    assert "nested/" not in extracted


def test_extract_zip_rejects_path_traversal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("good/file.txt", b"ok")
        zf.writestr("../evil.txt", b"bad")
        zf.writestr("/absolute.txt", b"bad")
    result = _extract_zip(buf.getvalue())
    assert "good/file.txt" in result
    assert "../evil.txt" not in result
    assert "/absolute.txt" not in result


def test_check_mdapi_access_true():
    sf = MagicMock()
    sf.mdapi.describe_metadata.return_value = {"metadataObjects": []}
    assert check_mdapi_access(sf) is True


def test_check_mdapi_access_false():
    sf = MagicMock()
    sf.mdapi.describe_metadata.side_effect = RuntimeError("no access")
    assert check_mdapi_access(sf) is False


def test_poll_retrieve_completed():
    sf = MagicMock()
    sf.mdapi.check_retrieve_status.return_value = ("Completed", "", [])
    _poll_retrieve(sf, "abc", timeout=5)
    sf.mdapi.check_retrieve_status.assert_called()


def test_poll_retrieve_insufficient_access():
    sf = MagicMock()
    sf.mdapi.check_retrieve_status.return_value = (
        "Failed",
        "INSUFFICIENT_ACCESS: ...",
        [],
    )
    with pytest.raises(MDAPIInsufficientAccessError):
        _poll_retrieve(sf, "abc", timeout=5)


def test_retrieve_metadata_success():
    sf = MagicMock()
    sf.mdapi._api_version = "62.0"
    sf.mdapi._session_header = object()

    async_id = "04xx0000000abcd"
    mock_result = MagicMock()
    mock_result.id = async_id
    sf.mdapi._service.retrieve.return_value = mock_result

    sf.mdapi.check_retrieve_status.return_value = ("Completed", "", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("classes/X.cls", b"public class X {}")
    sf.mdapi.retrieve_zip.return_value = ("Completed", "", [], buf.getvalue())

    with patch("app.services.salesforce.mdapi_retrieve._submit_retrieve", return_value=async_id):
        with patch("app.services.salesforce.mdapi_retrieve._poll_retrieve"):
            with patch("app.services.salesforce.mdapi_retrieve._retrieve_zip_bytes", return_value=buf.getvalue()):
                out = retrieve_metadata(sf, api_version="62.0")
    assert out["classes/X.cls"].startswith(b"public class")


def test_retrieve_metadata_limit_exceeded_fallback():
    sf = MagicMock()
    sf.mdapi._api_version = "62.0"
    sf.mdapi._session_header = object()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.cls", b"//")

    def fake_single(_sf, types, ver):
        if len(types) > 1:
            raise MDAPIRetrieveError("LIMIT_EXCEEDED: too big")
        return {f"{types[0]}.bin": b"x"}

    with patch("app.services.salesforce.mdapi_retrieve._single_retrieve", side_effect=fake_single):
        out = retrieve_metadata(sf, api_version="62.0")
    assert "Flow.bin" in out
    assert "ApexClass.bin" in out
