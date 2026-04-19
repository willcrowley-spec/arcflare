"""Salesforce Metadata API retrieve using zeep (simple_salesforce mdapi.retrieve is broken)."""

from __future__ import annotations

import io
import logging
import time
import zipfile
from typing import Any

from simple_salesforce import Salesforce

logger = logging.getLogger(__name__)

METADATA_TYPES = [
    "Flow",
    "ApexClass",
    "ApexTrigger",
    "CustomObject",
    "Workflow",
    "ApprovalProcess",
    "FlexiPage",
]

MDAPI_XML_NS = "http://soap.sforce.com/2006/04/metadata"


class MDAPIInsufficientAccessError(RuntimeError):
    """Raised when the connected user cannot use the Metadata API (typically lacks Modify All Data)."""

    def __init__(self) -> None:
        super().__init__(
            "Metadata API retrieve failed with INSUFFICIENT_ACCESS. "
            "The connected Salesforce user must have the Modify All Data permission "
            "to use the Metadata API retrieve operation."
        )


class MDAPIRetrieveError(RuntimeError):
    """Generic retrieve failure after polling completes."""


def check_mdapi_access(sf: Salesforce) -> bool:
    """Return True if describe_metadata succeeds (proxy for MDAPI permission)."""
    try:
        sf.mdapi.describe_metadata()
        return True
    except Exception as exc:
        logger.warning("mdapi_describe_metadata_failed error=%s", exc)
        return False


def _build_unpackaged(sf: Salesforce, types: list[str], api_version: str) -> Any:
    client = sf.mdapi._client
    PackageTypeMembers = client.get_type(f"{{{MDAPI_XML_NS}}}PackageTypeMembers")
    Package = client.get_type(f"{{{MDAPI_XML_NS}}}Package")
    members = [PackageTypeMembers(members=["*"], name=t) for t in types]
    return Package(types=members, version=api_version)


def _submit_retrieve(sf: Salesforce, types: list[str], api_version: str) -> str:
    client = sf.mdapi._client
    RetrieveRequest = client.get_type(f"{{{MDAPI_XML_NS}}}RetrieveRequest")
    unpackaged = _build_unpackaged(sf, types, api_version)
    request = RetrieveRequest(
        apiVersion=api_version,
        singlePackage=True,
        unpackaged=unpackaged,
    )
    result = sf.mdapi._service.retrieve(request, _soapheaders=[sf.mdapi._session_header])
    async_id = getattr(result, "id", None)
    if not async_id:
        raise MDAPIRetrieveError("retrieve() SOAP response missing async process id")
    return str(async_id)


def _poll_retrieve(sf: Salesforce, async_process_id: str, timeout: int = 300) -> None:
    deadline = time.monotonic() + timeout
    delay = 1.0
    max_delay = 8.0
    last_state = ""
    while time.monotonic() < deadline:
        state, error_message, _messages = sf.mdapi.check_retrieve_status(async_process_id)
        last_state = state or ""
        if state in ("Succeeded", "Completed"):
            return
        if state in ("Failed", "Error", "Canceled", "Canceling"):
            msg = (error_message or "").strip()
            if "INSUFFICIENT_ACCESS" in msg or "insufficient access" in msg.lower():
                raise MDAPIInsufficientAccessError()
            if "LIMIT_EXCEEDED" in msg or "limit exceeded" in msg.lower():
                raise MDAPIRetrieveError(f"LIMIT_EXCEEDED: {msg}")
            raise MDAPIRetrieveError(msg or f"retrieve failed state={state}")
        time.sleep(delay)
        delay = min(delay * 2, max_delay)
    raise MDAPIRetrieveError(f"retrieve timed out after {timeout}s (last_state={last_state})")


def _extract_zip(zip_bytes: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if ".." in name or name.startswith("/") or name.startswith("\\"):
                logger.warning("zip_entry_rejected path=%s", name)
                continue
            out[name] = zf.read(name)
    return out


def _retrieve_zip_bytes(sf: Salesforce, async_process_id: str) -> bytes:
    state, error_message, _messages, zip_bytes = sf.mdapi.retrieve_zip(async_process_id)
    if state not in ("Succeeded", "Completed"):
        msg = (error_message or "").strip()
        if "INSUFFICIENT_ACCESS" in msg or "insufficient access" in msg.lower():
            raise MDAPIInsufficientAccessError()
        raise MDAPIRetrieveError(msg or f"retrieve_zip bad state={state}")
    if not zip_bytes:
        raise MDAPIRetrieveError("retrieve_zip returned empty payload")
    return zip_bytes


def _single_retrieve(sf: Salesforce, types: list[str], api_version: str) -> dict[str, bytes]:
    async_id = _submit_retrieve(sf, types, api_version)
    _poll_retrieve(sf, async_id)
    raw = _retrieve_zip_bytes(sf, async_id)
    return _extract_zip(raw)


def retrieve_metadata(sf: Salesforce, api_version: str | None = None) -> dict[str, bytes]:
    """Full MDAPI retrieve; returns relative_path -> file bytes."""
    ver = api_version or getattr(sf.mdapi, "_api_version", None) or "62.0"
    try:
        return _single_retrieve(sf, METADATA_TYPES, ver)
    except MDAPIRetrieveError as exc:
        err = str(exc)
        if "LIMIT_EXCEEDED" not in err:
            raise
        logger.warning("mdapi_limit_exceeded_fallback_per_type error=%s", err)
        merged: dict[str, bytes] = {}
        for t in METADATA_TYPES:
            part = _single_retrieve(sf, [t], ver)
            for path, data in part.items():
                merged[path] = data
        return merged


def retrieve_metadata_safe(sf: Salesforce, api_version: str | None = None) -> dict[str, bytes]:
    """Same as retrieve_metadata but maps INSUFFICIENT_ACCESS to MDAPIInsufficientAccessError only."""
    return retrieve_metadata(sf, api_version=api_version)
