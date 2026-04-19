# MDAPI Metadata Enrichment — Implementation Plan

> **For agentic workers:** Implement task-by-task with verification after each task. Steps use checkbox (`- [ ]`) syntax. **All XML parsing** uses `xml.etree.ElementTree` with `ns = {'md': 'http://soap.sforce.com/2006/04/metadata'}`. **`raw_xml_hash`** uses `hashlib.sha256(xml_bytes).hexdigest()` (64-char hex).

**References:** `docs/superpowers/specs/2026-04-19-mdapi-metadata-enrichment-design.md`, `backend/app/models/metadata.py` (`Base` from `app.core.database`), `backend/app/services/salesforce/metadata.py`, `backend/app/services/sync_progress.py`, `backend/app/workers/metadata_sync.py`.

**Implementation order:** Complete **Task 13 Step 1** (`PHASES` in `sync_progress.py`) before wiring `_progress("mdapi_retrieve", ...)` / `_progress("mdapi_parse", ...)` in Task 12, otherwise Redis hashes omit those keys.

**Note:** `simple_salesforce` exposes `sf.mdapi.retrieve()` as broken; use the zeep `ServiceProxy.retrieve()` workaround from the spec. `check_retrieve_status` and `retrieve_zip` on `sf.mdapi` work.

---

## Phase 1: Foundation

### Task 1: Add MetadataDependency model

**Files:**
- Modify: `backend/app/models/metadata.py`
- Modify: `backend/app/models/__init__.py` (export `MetadataDependency` in imports and `__all__`)
- Create: `backend/tests/models/test_metadata_models.py`

- [ ] **Step 1: Append `MetadataDependency` after `MetadataComponent` in `metadata.py`**

Add `TYPE_CHECKING` import for nothing new if already present. Add the class exactly as below (relationships optional; match existing style).

```python
class MetadataDependency(Base):
    __tablename__ = "metadata_dependencies"
    __table_args__ = (
        Index("ix_metadata_deps_source", "connection_id", "source_type", "source_api_name"),
        Index("ix_metadata_deps_target", "connection_id", "target_type", "target_api_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["PlatformConnection"] = relationship("PlatformConnection")
```

- [ ] **Step 2: Export the model from `backend/app/models/__init__.py`**

Add to the metadata import line:

```python
from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataDependency, MetadataField, MetadataObject, RecordTelemetry
```

Add `"MetadataDependency"` to `__all__`.

- [ ] **Step 3: Create `backend/tests/models/test_metadata_models.py`**

```python
import uuid

from app.models.metadata import MetadataDependency


def test_metadata_dependency_instantiation():
    row = MetadataDependency(
        org_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        source_type="flow",
        source_api_name="My_Flow",
        target_type="object",
        target_api_name="Account",
        relationship_type="triggers_on",
        metadata_json={"edge_detail": "test"},
    )
    assert row.source_api_name == "My_Flow"
    assert row.metadata_json["edge_detail"] == "test"
```

- [ ] **Step 4: Run pytest**

Command:

```bash
cd backend && python -m pytest tests/models/test_metadata_models.py -v
```

**Expected:** 1 passed (`test_metadata_dependency_instantiation`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/metadata.py backend/app/models/__init__.py backend/tests/models/test_metadata_models.py
git commit -m "Add MetadataDependency model and instantiation test."
```

---

### Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<revision>_add_metadata_dependencies_table.py` (exact filename from autogenerate)
- Verify: `backend/alembic/env.py` imports all models (so autogenerate sees `MetadataDependency`)

- [ ] **Step 1: Ensure `MetadataDependency` is imported in Alembic env**

In `backend/alembic/env.py`, confirm the metadata model import path includes the new model (often `from app.models import ...` or `import app.models` side-effect import). If missing, add:

```python
from app.models import metadata  # noqa: F401
```

(or equivalent already used for other tables).

- [ ] **Step 2: Generate migration**

```bash
cd backend && alembic revision --autogenerate -m "add metadata_dependencies table"
```

- [ ] **Step 3: Verify the migration**

Open the new revision file and confirm:
- `op.create_table('metadata_dependencies', ...)`
- Columns: `id`, `org_id`, `connection_id`, `source_type`, `source_api_name`, `target_type`, `target_api_name`, `relationship_type`, `metadata_json`
- Foreign keys to `organizations.id` and `platform_connections.id` with `ondelete='cascade'`
- Indexes `ix_metadata_deps_source` and `ix_metadata_deps_target`

Manually fix autogenerate if it drops unrelated objects (never commit a migration that drops tables unintentionally).

- [ ] **Step 4: Apply migration**

```bash
cd backend && alembic upgrade head
```

**Expected:** Alembic reports success; Postgres contains `metadata_dependencies`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "Add Alembic migration for metadata_dependencies table."
```

---

### Task 3: Add antlr4-python3-runtime dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add dependency line**

Append (or insert with other libs):

```
antlr4-python3-runtime==4.13.2
```

- [ ] **Step 2: Install in the active environment**

```bash
cd backend && pip install antlr4-python3-runtime==4.13.2
```

**Expected:** `pip show antlr4-python3-runtime` shows version 4.13.2.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "Add antlr4-python3-runtime for Apex ANTLR parsing."
```

---

## Phase 2: MDAPI Retrieve

### Task 4: Create `mdapi_retrieve.py`

**Files:**
- Create: `backend/app/services/salesforce/mdapi_retrieve.py`
- Create: `backend/tests/services/salesforce/test_mdapi_retrieve.py`

- [ ] **Step 1: Create `backend/app/services/salesforce/mdapi_retrieve.py`**

```python
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
```

- [ ] **Step 2: Create `backend/tests/services/salesforce/test_mdapi_retrieve.py`**

```python
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
```

- [ ] **Step 3: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_retrieve.py -v
```

**Expected:** All tests pass (6 tests).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/salesforce/mdapi_retrieve.py backend/tests/services/salesforce/test_mdapi_retrieve.py
git commit -m "Add MDAPI retrieve module with zeep workaround and unit tests."
```

---

### Task 5: Create test package layout and `conftest.py`

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/models/__init__.py` (empty file: `# tests package`)
- Create: `backend/tests/services/__init__.py`
- Create: `backend/tests/services/salesforce/__init__.py`

- [ ] **Step 1: Create empty package markers**

`backend/tests/__init__.py`:

```python
# Test package root for pytest collection.
```

`backend/tests/models/__init__.py`:

```python
# Model tests package.
```

`backend/tests/services/__init__.py` and `backend/tests/services/salesforce/__init__.py`:

```python
# Service tests package.
```

- [ ] **Step 2: Create `backend/tests/conftest.py`**

```python
import os
import sys

import pytest

# Ensure `app` imports resolve when pytest cwd is backend/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def any_uuid_str() -> str:
    return "11111111-1111-1111-1111-111111111111"
```

- [ ] **Step 3: Run full metadata-related tests**

```bash
cd backend && python -m pytest tests/models/test_metadata_models.py tests/services/salesforce/test_mdapi_retrieve.py -v
```

**Expected:** All pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/__init__.py backend/tests/conftest.py backend/tests/models/__init__.py backend/tests/services/__init__.py backend/tests/services/salesforce/__init__.py
git commit -m "Add pytest package layout and conftest for backend tests."
```

---

## Phase 3: XML Parsers

### Task 6: Flow parser — `mdapi_parser.py`

**Files:**
- Create: `backend/app/services/salesforce/mdapi_parser.py` (initial file; extend in Tasks 7–9)
- Create: `backend/tests/services/salesforce/fixtures/sample_record_triggered_flow.flow-meta.xml`
- Create: `backend/tests/services/salesforce/test_mdapi_parser_flow.py`

- [ ] **Step 1: Add fixture XML `backend/tests/services/salesforce/fixtures/sample_record_triggered_flow.flow-meta.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
  <apiVersion>62.0</apiVersion>
  <description>Sample flow for tests</description>
  <processType>RecordTriggeredFlow</processType>
  <status>Active</status>
  <start>
    <locationX>0</locationX>
    <locationY>0</locationY>
    <connector>
      <targetReference>Update_Rating</targetReference>
    </connector>
    <object>Account</object>
    <recordTriggerType>CreateAndUpdate</recordTriggerType>
    <triggerType>RecordAfterSave</triggerType>
  </start>
  <recordUpdates>
    <name>Update_Rating</name>
    <label>Update Rating</label>
    <locationX>0</locationX>
    <locationY>0</locationY>
    <connector>
      <targetReference>Create_Task</targetReference>
    </connector>
    <filterLogic>and</filterLogic>
    <filters>
      <field>Industry</field>
      <operator>EqualTo</operator>
      <value>
        <stringValue>Healthcare</stringValue>
      </value>
    </filters>
    <inputAssignments>
      <field>Rating</field>
      <value>
        <stringValue>Hot</stringValue>
      </value>
    </inputAssignments>
    <object>Account</object>
  </recordUpdates>
  <recordCreates>
    <name>Create_Task</name>
    <label>Create Task</label>
    <locationX>0</locationX>
    <locationY>0</locationY>
    <inputAssignments>
      <field>Subject</field>
      <value>
        <stringValue>Follow up</stringValue>
      </value>
    </inputAssignments>
    <inputAssignments>
      <field>WhatId</field>
      <value>
        <elementReference>$Record.Id</elementReference>
      </value>
    </inputAssignments>
    <object>Task</object>
  </recordCreates>
  <decisions>
    <name>Check_Industry</name>
    <label>Check Industry</label>
    <defaultConnectorLabel>Default</defaultConnectorLabel>
    <rules>
      <name>Healthcare</name>
      <conditionLogic>and</conditionLogic>
      <conditions>
        <leftValueReference>$Record.Industry</leftValueReference>
        <operator>EqualTo</operator>
        <rightValue>
          <stringValue>Healthcare</stringValue>
        </rightValue>
      </conditions>
      <connector>
        <targetReference>Update_Rating</targetReference>
      </connector>
    </rules>
  </decisions>
  <variables>
    <name>varCurrentAccount</name>
    <dataType>SObject</dataType>
    <isCollection>false</isCollection>
    <isInput>true</isInput>
    <isOutput>false</isOutput>
    <objectType>Account</objectType>
  </variables>
  <formulas>
    <name>f_score</name>
    <dataType>Number</dataType>
    <expression>1 + 1</expression>
  </formulas>
</Flow>
```

- [ ] **Step 2: Create `backend/app/services/salesforce/mdapi_parser.py` with `parse_flow`**

```python
"""Deterministic parsers for Salesforce MDAPI XML (metadata namespace)."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any

MD_NS = "http://soap.sforce.com/2006/04/metadata"
NS = {"md": MD_NS}


def _text(elem: ET.Element | None, path: str) -> str | None:
    if elem is None:
        return None
    child = elem.find(path, NS)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _collect_objects_from_record_nodes(container: ET.Element, tag: str) -> list[str]:
    out: list[str] = []
    for node in container.findall(f"md:{tag}", NS):
        obj = _text(node, "md:object")
        if obj:
            out.append(obj)
    return out


def parse_flow(xml_bytes: bytes, filename: str) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    process_type = _text(root, "md:processType")
    trigger_type = _text(root, "md:triggerType")
    status = _text(root, "md:status")
    description = _text(root, "md:description")

    start = root.find("md:start", NS)
    trigger_object: str | None = None
    if start is not None:
        trigger_object = _text(start, "md:object")
        if trigger_type is None:
            trigger_type = _text(start, "md:triggerType")

    decisions: list[dict[str, Any]] = []
    for dec in root.findall("md:decisions", NS):
        rules_out: list[dict[str, Any]] = []
        for rule in dec.findall("md:rules", NS):
            conds: list[dict[str, str | None]] = []
            for cond in rule.findall("md:conditions", NS):
                conds.append(
                    {
                        "field": _text(cond, "md:leftValueReference"),
                        "operator": _text(cond, "md:operator"),
                        "value": _text(cond, "md:rightValue/md:stringValue"),
                    }
                )
            tgt = rule.find("md:connector/md:targetReference", NS)
            connector = tgt.text.strip() if tgt is not None and tgt.text else None
            rules_out.append(
                {
                    "name": _text(rule, "md:name"),
                    "conditions": conds,
                    "connector": connector,
                }
            )
        def_tgt = dec.find("md:defaultConnector/md:targetReference", NS)
        default_connector = def_tgt.text.strip() if def_tgt is not None and def_tgt.text else None
        decisions.append(
            {
                "name": _text(dec, "md:name"),
                "label": _text(dec, "md:label"),
                "rules": rules_out,
                "default_connector": default_connector,
            }
        )

    def _record_fields(node: ET.Element) -> list[dict[str, str | None]]:
        fields: list[dict[str, str | None]] = []
        for ia in node.findall("md:inputAssignments", NS):
            fields.append(
                {
                    "field": _text(ia, "md:field"),
                    "value": _text(ia, "md:value/md:stringValue")
                    or _text(ia, "md:value/md:elementReference"),
                }
            )
        return fields

    record_lookups: list[dict[str, Any]] = []
    for node in root.findall("md:recordLookups", NS):
        record_lookups.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "connector": _text(node.find("md:connector", NS), "md:targetReference")
                if node.find("md:connector", NS) is not None
                else None,
            }
        )

    record_creates: list[dict[str, Any]] = []
    for node in root.findall("md:recordCreates", NS):
        record_creates.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "fields": _record_fields(node),
            }
        )

    record_updates: list[dict[str, Any]] = []
    for node in root.findall("md:recordUpdates", NS):
        record_updates.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
                "fields": _record_fields(node),
            }
        )

    record_deletes: list[dict[str, Any]] = []
    for node in root.findall("md:recordDeletes", NS):
        record_deletes.append(
            {
                "name": _text(node, "md:name"),
                "object": _text(node, "md:object"),
            }
        )

    assignments: list[dict[str, Any]] = []
    for node in root.findall("md:assignments", NS):
        assignments.append({"name": _text(node, "md:name")})

    screens: list[dict[str, Any]] = []
    for node in root.findall("md:screens", NS):
        screens.append({"name": _text(node, "md:name")})

    subflows: list[dict[str, Any]] = []
    for node in root.findall("md:subflows", NS):
        subflows.append(
            {
                "name": _text(node, "md:name"),
                "flow_name": _text(node, "md:flowName"),
            }
        )

    loops: list[dict[str, Any]] = []
    for node in root.findall("md:loops", NS):
        loops.append(
            {
                "name": _text(node, "md:name"),
                "collection": _text(node, "md:collectionReference"),
            }
        )

    action_calls: list[dict[str, Any]] = []
    for node in root.findall("md:actionCalls", NS):
        action_calls.append(
            {
                "name": _text(node, "md:name"),
                "action_type": _text(node, "md:actionType"),
                "action_name": _text(node, "md:actionName"),
            }
        )

    waits: list[dict[str, Any]] = []
    for node in root.findall("md:waits", NS):
        waits.append({"name": _text(node, "md:name")})

    variables: list[dict[str, Any]] = []
    for node in root.findall("md:variables", NS):
        variables.append(
            {
                "name": _text(node, "md:name"),
                "data_type": _text(node, "md:dataType"),
                "object_type": _text(node, "md:objectType"),
                "is_input": (_text(node, "md:isInput") or "").lower() == "true",
            }
        )

    formulas: list[dict[str, Any]] = []
    for node in root.findall("md:formulas", NS):
        formulas.append(
            {
                "name": _text(node, "md:name"),
                "expression": _text(node, "md:expression"),
                "data_type": _text(node, "md:dataType"),
            }
        )

    elements = {
        "decisions": decisions,
        "record_lookups": record_lookups,
        "record_creates": record_creates,
        "record_updates": record_updates,
        "record_deletes": record_deletes,
        "assignments": assignments,
        "screens": screens,
        "subflows": subflows,
        "loops": loops,
        "action_calls": action_calls,
        "waits": waits,
    }

    element_count = sum(len(v) for v in elements.values())
    branch_bonus = sum(len(d.get("rules", [])) for d in decisions)
    loop_bonus = len(loops) * 2
    complexity_score = element_count + branch_bonus + loop_bonus

    objects_touched: set[str] = set()
    if trigger_object:
        objects_touched.add(trigger_object)
    for tag in ("recordLookups", "recordCreates", "recordUpdates", "recordDeletes"):
        for obj in _collect_objects_from_record_nodes(root, tag):
            objects_touched.add(obj)
    for var in variables:
        ot = var.get("object_type")
        if ot:
            objects_touched.add(ot)

    raw_xml_hash = hashlib.sha256(xml_bytes).hexdigest()

    return {
        "process_type": process_type,
        "trigger_type": trigger_type,
        "trigger_object": trigger_object,
        "status": status,
        "description": description,
        "elements": elements,
        "variables": variables,
        "formulas": formulas,
        "element_count": element_count,
        "objects_touched": sorted(objects_touched),
        "complexity_score": complexity_score,
        "raw_xml_hash": raw_xml_hash,
        "source_filename": filename,
    }
```

- [ ] **Step 3: Create `backend/tests/services/salesforce/test_mdapi_parser_flow.py`**

```python
import pathlib

from app.services.salesforce.mdapi_parser import parse_flow


def test_parse_flow_sample_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_record_triggered_flow.flow-meta.xml"
    data = path.read_bytes()
    out = parse_flow(data, "sample_record_triggered_flow.flow-meta.xml")
    assert out["process_type"] == "RecordTriggeredFlow"
    assert out["trigger_object"] == "Account"
    assert "Account" in out["objects_touched"]
    assert "Task" in out["objects_touched"]
    assert out["element_count"] >= 4
    assert len(out["raw_xml_hash"]) == 64
    assert out["elements"]["record_updates"][0]["object"] == "Account"
    assert out["elements"]["decisions"][0]["rules"][0]["name"] == "Healthcare"
```

- [ ] **Step 4: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_parser_flow.py -v
```

**Expected:** 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/salesforce/mdapi_parser.py backend/tests/services/salesforce/fixtures/sample_record_triggered_flow.flow-meta.xml backend/tests/services/salesforce/test_mdapi_parser_flow.py
git commit -m "Add MDAPI Flow XML parser and fixture test."
```

---

### Task 7: CustomObject parser

**Files:**
- Modify: `backend/app/services/salesforce/mdapi_parser.py`
- Create: `backend/tests/services/salesforce/fixtures/sample_custom_object.object-meta.xml`
- Create: `backend/tests/services/salesforce/test_mdapi_parser_custom_object.py`

- [ ] **Step 1: Add fixture `backend/tests/services/salesforce/fixtures/sample_custom_object.object-meta.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <sharingModel>ReadWrite</sharingModel>
  <validationRules>
    <fullName>Require_Amount</fullName>
    <active>true</active>
    <description>Amount required</description>
    <errorConditionFormula>ISBLANK(Amount__c)</errorConditionFormula>
    <errorMessage>Amount is required</errorMessage>
    <errorDisplayField>Amount__c</errorDisplayField>
  </validationRules>
  <fields>
    <fullName>Expected_Revenue__c</fullName>
    <formula>Amount__c * Probability__c / 100</formula>
    <formulaTreatBlanksAs>BlankAsZero</formulaTreatBlanksAs>
  </fields>
  <recordTypes>
    <fullName>Enterprise</fullName>
    <active>true</active>
    <label>Enterprise</label>
    <description>Enterprise deals</description>
  </recordTypes>
  <fieldSets>
    <fullName>Quick_Create</fullName>
    <description>QC</description>
    <displayedFields>
      <field>Name</field>
    </displayedFields>
    <displayedFields>
      <field>Amount__c</field>
    </displayedFields>
  </fieldSets>
  <listViews>
    <fullName>My_Open</fullName>
    <label>My Open</label>
    <filterScope>Mine</filterScope>
    <columns>NAME</columns>
    <columns>AMOUNT</columns>
  </listViews>
  <webLinks>
    <fullName>Google_Maps</fullName>
    <url>http://maps.google.com</url>
  </webLinks>
</CustomObject>
```

- [ ] **Step 2: Append `parse_custom_object` to `mdapi_parser.py`**

```python
def parse_custom_object(xml_bytes: bytes, filename: str) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    sharing_model = _text(root, "md:sharingModel")

    validation_rules: list[dict[str, Any]] = []
    for vr in root.findall("md:validationRules", NS):
        validation_rules.append(
            {
                "name": _text(vr, "md:fullName"),
                "active": (_text(vr, "md:active") or "").lower() == "true",
                "description": _text(vr, "md:description"),
                "error_condition_formula": _text(vr, "md:errorConditionFormula"),
                "error_message": _text(vr, "md:errorMessage"),
                "error_display_field": _text(vr, "md:errorDisplayField"),
            }
        )

    formula_fields: list[dict[str, str | None]] = []
    for field in root.findall("md:fields", NS):
        formula = _text(field, "md:formula")
        if formula:
            formula_fields.append(
                {
                    "api_name": _text(field, "md:fullName"),
                    "formula": formula,
                    "formula_treat_blanks_as": _text(field, "md:formulaTreatBlanksAs"),
                }
            )

    record_types: list[dict[str, Any]] = []
    for rt in root.findall("md:recordTypes", NS):
        record_types.append(
            {
                "developer_name": _text(rt, "md:fullName"),
                "label": _text(rt, "md:label"),
                "active": (_text(rt, "md:active") or "").lower() == "true",
                "description": _text(rt, "md:description"),
            }
        )

    field_sets: list[dict[str, Any]] = []
    for fs in root.findall("md:fieldSets", NS):
        field_names = [_text(df, "md:field") for df in fs.findall("md:displayedFields", NS)]
        field_sets.append(
            {
                "label": _text(fs, "md:fullName"),
                "description": _text(fs, "md:description"),
                "fields": [f for f in field_names if f],
            }
        )

    list_views: list[dict[str, Any]] = []
    for lv in root.findall("md:listViews", NS):
        cols = [_text(c, "md:field") or (c.text or "").strip() for c in lv.findall("md:columns", NS)]
        cols = [c for c in cols if c]
        list_views.append(
            {
                "developer_name": _text(lv, "md:fullName"),
                "label": _text(lv, "md:label"),
                "filter_scope": _text(lv, "md:filterScope"),
                "filters": [],
                "columns": cols,
            }
        )

    web_links: list[dict[str, Any]] = []
    for wl in root.findall("md:webLinks", NS):
        web_links.append(
            {
                "name": _text(wl, "md:fullName"),
                "link_type": "url",
                "url_or_page": _text(wl, "md:url"),
            }
        )

    return {
        "validation_rules": validation_rules,
        "formula_fields": formula_fields,
        "record_types": record_types,
        "field_sets": field_sets,
        "list_views": list_views,
        "web_links": web_links,
        "sharing_model": sharing_model,
        "raw_xml_hash": hashlib.sha256(xml_bytes).hexdigest(),
        "source_filename": filename,
    }
```

- [ ] **Step 3: Create `backend/tests/services/salesforce/test_mdapi_parser_custom_object.py`**

```python
import pathlib

from app.services.salesforce.mdapi_parser import parse_custom_object


def test_parse_custom_object_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_custom_object.object-meta.xml"
    out = parse_custom_object(path.read_bytes(), "sample_custom_object.object-meta.xml")
    assert out["sharing_model"] == "ReadWrite"
    assert out["validation_rules"][0]["error_condition_formula"] == "ISBLANK(Amount__c)"
    assert out["formula_fields"][0]["api_name"] == "Expected_Revenue__c"
    assert "Name" in out["field_sets"][0]["fields"]
    assert len(out["raw_xml_hash"]) == 64
```

- [ ] **Step 4: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_parser_custom_object.py -v
```

**Expected:** 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/salesforce/mdapi_parser.py backend/tests/services/salesforce/fixtures/sample_custom_object.object-meta.xml backend/tests/services/salesforce/test_mdapi_parser_custom_object.py
git commit -m "Add CustomObject MDAPI XML parser and tests."
```

---

### Task 8: Workflow parser

**Files:**
- Modify: `backend/app/services/salesforce/mdapi_parser.py`
- Create: `backend/tests/services/salesforce/fixtures/sample_opportunity.workflow-meta.xml`
- Create: `backend/tests/services/salesforce/test_mdapi_parser_workflow.py`

- [ ] **Step 1: Add fixture `backend/tests/services/salesforce/fixtures/sample_opportunity.workflow-meta.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Workflow xmlns="http://soap.sforce.com/2006/04/metadata">
  <rules>
    <fullName>Big_Deal</fullName>
    <active>true</active>
    <description>Big deal rule</description>
    <formula>AND(ISPICKVAL(StageName, &quot;Closed Won&quot;), Amount &gt; 100000)</formula>
    <triggerType>onCreateOrTriggeringUpdate</triggerType>
    <actions>
      <name>Set_Priority</name>
      <type>FieldUpdate</type>
    </actions>
    <actions>
      <name>Notify_Manager</name>
      <type>Alert</type>
    </actions>
  </rules>
  <fieldUpdates>
    <fullName>Set_Priority</fullName>
    <field>Priority__c</field>
    <literalValue>High</literalValue>
  </fieldUpdates>
  <alerts>
    <fullName>Notify_Manager</fullName>
    <template>Big_Deal_Alert</template>
  </alerts>
  <outboundMessages>
    <fullName>Notify_ERP</fullName>
    <endpointUrl>https://example.com/om</endpointUrl>
    <fields>Id</fields>
  </outboundMessages>
  <tasks>
    <fullName>Create_Follow_Up</fullName>
    <subject>Follow up</subject>
    <assignedToType>owner</assignedToType>
    <offsetFromField>CloseDate</offsetFromField>
  </tasks>
</Workflow>
```

- [ ] **Step 2: Append `parse_workflow` to `mdapi_parser.py`**

```python
def parse_workflow(xml_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """Return one dict per workflow rule (automation row shape)."""
    root = ET.fromstring(xml_bytes)
    related_object = filename.split("/")[-1].replace(".workflow-meta.xml", "")

    field_updates_by_name: dict[str, dict[str, Any]] = {}
    for fu in root.findall("md:fieldUpdates", NS):
        name = _text(fu, "md:fullName")
        if name:
            field_updates_by_name[name] = {
                "name": name,
                "field": _text(fu, "md:field"),
                "value": _text(fu, "md:literalValue"),
                "formula": _text(fu, "md:formula"),
                "target_object": related_object,
            }

    email_alerts: dict[str, dict[str, Any]] = {}
    for al in root.findall("md:alerts", NS):
        name = _text(al, "md:fullName")
        if name:
            email_alerts[name] = {
                "name": name,
                "template": _text(al, "md:template"),
                "recipients": [],
            }

    outbound_messages: dict[str, dict[str, Any]] = {}
    for om in root.findall("md:outboundMessages", NS):
        name = _text(om, "md:fullName")
        if name:
            fields = [_text(f, "md:field") for f in om.findall("md:fields", NS)]
            fields = [f for f in fields if f]
            outbound_messages[name] = {
                "name": name,
                "endpoint_url": _text(om, "md:endpointUrl"),
                "fields": fields,
            }

    tasks: dict[str, dict[str, Any]] = {}
    for tk in root.findall("md:tasks", NS):
        name = _text(tk, "md:fullName")
        if name:
            tasks[name] = {
                "name": name,
                "subject": _text(tk, "md:subject"),
                "assignee": _text(tk, "md:assignedToType"),
                "due_date_offset": _text(tk, "md:offsetFromField"),
            }

    results: list[dict[str, Any]] = []
    for rule in root.findall("md:rules", NS):
        rule_name = _text(rule, "md:fullName")
        actions_out: dict[str, list[dict[str, str | None]]] = {
            "field_updates": [],
            "email_alerts": [],
            "outbound_messages": [],
            "tasks": [],
        }
        linkages: list[dict[str, str | None]] = []
        for act in rule.findall("md:actions", NS):
            an = _text(act, "md:name")
            at = _text(act, "md:type")
            linkages.append({"name": an, "type": at})
            if at == "FieldUpdate" and an in field_updates_by_name:
                actions_out["field_updates"].append(field_updates_by_name[an])
            elif at in ("Alert", "EmailAlert") and an in email_alerts:
                actions_out["email_alerts"].append(email_alerts[an])
            elif at == "OutboundMessage" and an in outbound_messages:
                actions_out["outbound_messages"].append(outbound_messages[an])
            elif at == "Task" and an in tasks:
                actions_out["tasks"].append(tasks[an])

        criteria_items: list[dict[str, str | None]] = []
        for crit in rule.findall("md:criteriaItems", NS):
            criteria_items.append(
                {
                    "field": _text(crit, "md:field"),
                    "operation": _text(crit, "md:operation"),
                    "value": _text(crit, "md:value"),
                }
            )

        results.append(
            {
                "automation_subtype": "workflow_rule",
                "api_name": rule_name,
                "active": (_text(rule, "md:active") or "").lower() == "true",
                "description": _text(rule, "md:description"),
                "criteria": {
                    "formula": _text(rule, "md:formula"),
                    "trigger_type": _text(rule, "md:triggerType"),
                    "criteria_items": criteria_items,
                },
                "actions": actions_out,
                "rule_action_linkages": linkages,
                "related_object": related_object,
                "raw_xml_hash": hashlib.sha256(xml_bytes).hexdigest(),
                "source_filename": filename,
            }
        )
    return results
```

- [ ] **Step 3: Create `backend/tests/services/salesforce/test_mdapi_parser_workflow.py`**

```python
import pathlib

from app.services.salesforce.mdapi_parser import parse_workflow


def test_parse_workflow_rules():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_opportunity.workflow-meta.xml"
    rows = parse_workflow(path.read_bytes(), "workflows/Opportunity.workflow-meta.xml")
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["related_object"] == "Opportunity"
    assert r0["criteria"]["formula"].startswith("AND(")
    assert r0["actions"]["field_updates"][0]["field"] == "Priority__c"
    assert r0["actions"]["email_alerts"][0]["template"] == "Big_Deal_Alert"
    assert len(r0["raw_xml_hash"]) == 64
```

- [ ] **Step 4: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_parser_workflow.py -v
```

**Expected:** 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/salesforce/mdapi_parser.py backend/tests/services/salesforce/fixtures/sample_opportunity.workflow-meta.xml backend/tests/services/salesforce/test_mdapi_parser_workflow.py
git commit -m "Add Workflow MDAPI XML parser and tests."
```

---

### Task 9: ApprovalProcess parser

**Files:**
- Modify: `backend/app/services/salesforce/mdapi_parser.py`
- Create: `backend/tests/services/salesforce/fixtures/sample_deal_approval.approvalProcess-meta.xml`
- Create: `backend/tests/services/salesforce/test_mdapi_parser_approval.py`

- [ ] **Step 1: Add fixture `backend/tests/services/salesforce/fixtures/sample_deal_approval.approvalProcess-meta.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ApprovalProcess xmlns="http://soap.sforce.com/2006/04/metadata">
  <fullName>Deal_Approval</fullName>
  <active>true</active>
  <entryCriteria>
    <formula>Amount &gt; 50000</formula>
  </entryCriteria>
  <recordEditability>AdminOnly</recordEditability>
  <approvalStep>
    <allowDelegate>false</allowDelegate>
    <approvalActions>
      <action>
        <name>Set_Approved</name>
        <type>FieldUpdate</type>
      </action>
    </approvalActions>
    <assignedApprover>
      <approver>
        <type>relatedUserField</type>
        <relatedUserField>Manager__c</relatedUserField>
      </approver>
    </assignedApprover>
    <label>Manager</label>
    <name>Step_1</name>
    <rejectionActions>
      <action>
        <name>Set_Rejected</name>
        <type>FieldUpdate</type>
      </action>
    </rejectionActions>
  </approvalStep>
  <finalApprovalActions>
    <action>
      <name>Mark_Approved</name>
      <type>FieldUpdate</type>
    </action>
    <action>
      <name>Approval_Notification</name>
      <type>Alert</type>
    </action>
  </finalApprovalActions>
  <finalRejectionActions>
    <action>
      <name>Mark_Rejected</name>
      <type>FieldUpdate</type>
    </action>
  </finalRejectionActions>
</ApprovalProcess>
```

- [ ] **Step 2: Append `parse_approval_process` to `mdapi_parser.py`**

```python
def _approval_actions(container: ET.Element | None) -> list[dict[str, str | None]]:
    if container is None:
        return []
    out: list[dict[str, str | None]] = []
    for act in container.findall(".//md:action", NS):
        out.append(
            {
                "type": (_text(act, "md:type") or "").lower(),
                "name": _text(act, "md:name"),
            }
        )
    return out


def parse_approval_process(xml_bytes: bytes, filename: str) -> dict[str, Any]:
    root = ET.fromstring(xml_bytes)
    parts = filename.replace(".approvalProcess-meta.xml", "").split("/")
    related_object = parts[-2] if len(parts) >= 2 else parts[-1]

    entry = root.find("md:entryCriteria", NS)
    entry_formula = _text(entry, "md:formula") if entry is not None else None

    steps: list[dict[str, Any]] = []
    for idx, st in enumerate(root.findall("md:approvalStep", NS), start=1):
        assignee_type = _text(st, "md:assignedApprover/md:approver/md:type")
        assignee = _text(st, "md:assignedApprover/md:approver/md:relatedUserField")
        steps.append(
            {
                "number": idx,
                "assignee_type": assignee_type,
                "assignee": assignee,
                "approval_actions": _approval_actions(st.find("md:approvalActions", NS)),
                "rejection_actions": _approval_actions(st.find("md:rejectionActions", NS)),
            }
        )

    return {
        "api_name": _text(root, "md:fullName"),
        "active": (_text(root, "md:active") or "").lower() == "true",
        "entry_criteria_formula": entry_formula,
        "record_editability": _text(root, "md:recordEditability"),
        "steps": steps,
        "final_approval_actions": _approval_actions(root.find("md:finalApprovalActions", NS)),
        "final_rejection_actions": _approval_actions(root.find("md:finalRejectionActions", NS)),
        "initial_submission_actions": _approval_actions(root.find("md:initialSubmissionActions", NS)),
        "related_object": related_object,
        "raw_xml_hash": hashlib.sha256(xml_bytes).hexdigest(),
        "source_filename": filename,
    }
```

- [ ] **Step 3: Create `backend/tests/services/salesforce/test_mdapi_parser_approval.py`**

```python
import pathlib

from app.services.salesforce.mdapi_parser import parse_approval_process


def test_parse_approval_process_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_deal_approval.approvalProcess-meta.xml"
    out = parse_approval_process(
        path.read_bytes(),
        "approvalProcesses/Opportunity.Deal_Approval.approvalProcess-meta.xml",
    )
    assert out["entry_criteria_formula"] == "Amount > 50000"
    assert out["record_editability"] == "AdminOnly"
    assert out["steps"][0]["assignee_type"] == "relatedUserField"
    assert any(a["name"] == "Mark_Approved" for a in out["final_approval_actions"])
    assert len(out["raw_xml_hash"]) == 64
```

- [ ] **Step 4: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_parser_approval.py -v
```

**Expected:** 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/salesforce/mdapi_parser.py backend/tests/services/salesforce/fixtures/sample_deal_approval.approvalProcess-meta.xml backend/tests/services/salesforce/test_mdapi_parser_approval.py
git commit -m "Add ApprovalProcess MDAPI XML parser and tests."
```

---

## Phase 4: ANTLR4 Apex Parser

### Task 10: Generate ANTLR4 Python parser from apex-dev-tools grammars

**Files:**
- Create: `backend/app/services/salesforce/apex_parser/ApexLexer.g4` (copy from upstream, renamed)
- Create: `backend/app/services/salesforce/apex_parser/ApexParser.g4` (copy from upstream, renamed + `options { tokenVocab=ApexLexer; }`)
- Create: `backend/app/services/salesforce/apex_parser/__init__.py`
- Create (generated, committed): `backend/app/services/salesforce/apex_parser/ApexLexer.py`, `ApexLexer.tokens`, `ApexParser.py`, `ApexParserVisitor.py`, `ApexParserListener.py` (exact set produced by ANTLR 4.13.x)
- Create: `backend/tests/services/salesforce/apex_parser/test_apex_parser_smoke.py`

- [ ] **Step 1: Download Base grammars (PowerShell)**

```powershell
New-Item -ItemType Directory -Force -Path backend/app/services/salesforce/apex_parser | Out-Null
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/apex-dev-tools/apex-parser/main/antlr/BaseApexLexer.g4" -OutFile "backend/app/services/salesforce/apex_parser/ApexLexer.g4"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/apex-dev-tools/apex-parser/main/antlr/BaseApexParser.g4" -OutFile "backend/app/services/salesforce/apex_parser/ApexParser.g4"
```

- [ ] **Step 2: Edit `ApexLexer.g4` and `ApexParser.g4`**

1. Open `ApexLexer.g4` copied from `BaseApexLexer.g4`. Ensure the first line is exactly `lexer grammar ApexLexer;` (rename the grammar name from `BaseApexLexer` if the upstream file still declares `lexer grammar BaseApexLexer;`).
2. Open `ApexParser.g4`. Keep `parser grammar ApexParser;` as the first line. Insert immediately after it:

```antlr
options { tokenVocab=ApexLexer; }
```

3. Confirm `ApexParser.g4` contains **no** `lexer grammar` header (lexer lives only in `ApexLexer.g4`).

- [ ] **Step 3: Generate Python targets (run from directory containing the `.g4` files)**

```bash
cd backend/app/services/salesforce/apex_parser && antlr4 -Dlanguage=Python3 -visitor ApexLexer.g4 && antlr4 -Dlanguage=Python3 -visitor ApexParser.g4
```

**Expected:** `ApexLexer.py`, `ApexParser.py`, `ApexParserVisitor.py`, `ApexParserListener.py`, and token files are created with no ANTLR errors.

- [ ] **Step 4: Create `backend/app/services/salesforce/apex_parser/__init__.py`**

```python
"""ANTLR4-generated Apex parser helpers."""

from antlr4 import InputStream


class CaseInsensitiveInputStream(InputStream):
    """Lowercases Apex source before lexing (Apex is case-insensitive)."""

    def __init__(self, data: str) -> None:
        super().__init__(data.lower())


__all__ = ["CaseInsensitiveInputStream"]
```

- [ ] **Step 5: Create smoke test `backend/tests/services/salesforce/apex_parser/test_apex_parser_smoke.py`**

```python
from antlr4 import CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener

from app.services.salesforce.apex_parser import CaseInsensitiveInputStream
from app.services.salesforce.apex_parser.ApexLexer import ApexLexer
from app.services.salesforce.apex_parser.ApexParser import ApexParser


class _ThrowingErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise SyntaxError(f"line {line}:{column} {msg}")


def test_parse_minimal_class_no_errors():
    src = "public class HelloWorld {\n}\n"
    lexer = ApexLexer(CaseInsensitiveInputStream(src))
    stream = CommonTokenStream(lexer)
    parser = ApexParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(_ThrowingErrorListener())
    tree = parser.compilationUnit()
    assert tree is not None
    assert stream.tokens[-1].type == ApexParser.EOF
```

- [ ] **Step 6: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/apex_parser/test_apex_parser_smoke.py -v
```

**Expected:** 1 passed.

- [ ] **Step 7: Commit grammars + generated Python**

```bash
git add backend/app/services/salesforce/apex_parser/
git commit -m "Add Apex ANTLR4 grammars and generated Python parser runtime."
```

---

### Task 11: Apex source analyzer (`analyzer.py`)

**Files:**
- Create: `backend/app/services/salesforce/apex_parser/analyzer.py`
- Create: `backend/tests/services/salesforce/apex_parser/test_analyzer.py`
- Create: `backend/tests/services/salesforce/apex_parser/fixtures/AccountService.cls`
- Create: `backend/tests/services/salesforce/apex_parser/fixtures/AccountRating.trigger`

- [ ] **Step 1: Fixture `backend/tests/services/salesforce/apex_parser/fixtures/AccountService.cls`**

```apex
public class AccountService {
    @InvocableMethod(label='Update')
    public static void updateRatings(List<Account> accounts) {
        for (Account a : accounts) {
            a.Rating = 'Hot';
        }
        update accounts;
        List<Contact> cs = [SELECT Id FROM Contact WHERE AccountId IN :accounts];
        insert cs;
    }
}
```

- [ ] **Step 2: Fixture `backend/tests/services/salesforce/apex_parser/fixtures/AccountRating.trigger`**

```apex
trigger AccountRating on Account (after update) {
    AccountService.updateRatings(Trigger.new);
}
```

- [ ] **Step 3: Create `backend/app/services/salesforce/apex_parser/analyzer.py`**

Uses ANTLR4 `XPath` to find `methodDeclaration` / DML / `soqlLiteral` nodes (visitor pattern via generated `ApexParserVisitor` is optional; XPath is deterministic on the same AST).

```python
"""Static summaries of Apex classes and triggers using ANTLR4 parse trees + XPath."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any

from antlr4 import CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import ParseTree
from antlr4.xpath import XPath

from app.services.salesforce.apex_parser import CaseInsensitiveInputStream
from app.services.salesforce.apex_parser.ApexLexer import ApexLexer
from app.services.salesforce.apex_parser.ApexParser import ApexParser

MD_NS = {"md": "http://soap.sforce.com/2006/04/metadata"}


class _SilentErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        return


def _parse_tree(source: str, rule: str) -> tuple[ApexParser, ParseTree]:
    lexer = ApexLexer(CaseInsensitiveInputStream(source))
    stream = CommonTokenStream(lexer)
    parser = ApexParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(_SilentErrorListener())
    if rule == "trigger":
        tree = parser.triggerUnit()
    else:
        tree = parser.compilationUnit()
    return parser, tree


def _api_version_from_meta(meta_xml: bytes | None) -> str | None:
    if not meta_xml:
        return None
    root = ET.fromstring(meta_xml)
    v = root.find("md:apiVersion", MD_NS)
    if v is not None and v.text:
        return v.text.strip()
    return None


def _soql_objects(soql_text: str) -> list[str]:
    out: list[str] = []
    m = re.search(r"\bfrom\s+([a-zA-Z0-9_]+)\b", soql_text, re.IGNORECASE)
    if m:
        out.append(m.group(1))
    return out


def _dml_objects_from_snippets(snippets: list[str]) -> list[str]:
    objs: set[str] = set()
    for sn in snippets:
        m = re.search(r"(insert|update|delete|undelete|upsert)\s*([a-zA-Z0-9_]+)", sn, re.IGNORECASE)
        if m:
            objs.add(m.group(2))
    return sorted(objs)


def _collect_dml_soql(parser: ApexParser, tree: ParseTree) -> tuple[list[str], list[str]]:
    dml_snippets: list[str] = []
    for xp in (
        "//insertStatement",
        "//updateStatement",
        "//deleteStatement",
        "//upsertStatement",
        "//undeleteStatement",
    ):
        for ctx in XPath.findAll(tree, xp, parser):
            dml_snippets.append(ctx.getText())
    soql_literals = [ctx.getText() for ctx in XPath.findAll(tree, "//soqlLiteral", parser)]
    return dml_snippets, soql_literals


def analyze_apex_class(source: str, meta_xml: bytes | None = None) -> dict[str, Any]:
    parser, tree = _parse_tree(source, "class")
    dml_snippets, soql_literals = _collect_dml_soql(parser, tree)

    methods: list[dict[str, Any]] = []
    for md in XPath.findAll(tree, "//methodDeclaration", parser):
        name = md.id().getText() if md.id() else None
        ret = md.typeRef().getText() if md.typeRef() else "void"
        params = md.formalParameters().getText() if md.formalParameters() else "()"
        methods.append(
            {
                "name": name,
                "return_type": ret,
                "parameters": params,
                "annotations": [],
                "has_dml": bool(dml_snippets),
                "has_soql": bool(soql_literals),
                "has_callout": bool(
                    re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
                    or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
                ),
            }
        )

    callout_detected = any(m["has_callout"] for m in methods) or bool(
        re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
        or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
    )
    for m in methods:
        m["has_callout"] = callout_detected

    soql_objs: list[str] = []
    for lit in soql_literals:
        soql_objs.extend(_soql_objects(lit))

    return {
        "source_body": source,
        "methods": methods,
        "class_annotations": [],
        "dml_objects": _dml_objects_from_snippets(dml_snippets),
        "soql_objects": sorted(set(soql_objs)),
        "callout_detected": callout_detected,
        "api_version": _api_version_from_meta(meta_xml),
        "line_count": source.count("\n") + 1,
        "raw_xml_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "parse_error": parser.getNumberOfSyntaxErrors() > 0,
    }


def analyze_apex_trigger(source: str, meta_xml: bytes | None = None) -> dict[str, Any]:
    parser, tree = _parse_tree(source, "trigger")
    dml_snippets, soql_literals = _collect_dml_soql(parser, tree)
    m = re.search(r"trigger\s+\w+\s+on\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)", source, re.IGNORECASE)
    trigger_object = m.group(1) if m else None
    trigger_events = [p.strip() for p in m.group(2).split(",")] if m else []
    soql_objs: list[str] = []
    for lit in soql_literals:
        soql_objs.extend(_soql_objects(lit))
    callout_detected = bool(
        re.search(r"\bHttpRequest\b|\bHttp\.send\b", source)
        or re.search(r"@future\s*\([^)]*callout\s*=\s*true", source, re.IGNORECASE)
    )
    return {
        "source_body": source,
        "methods": [],
        "class_annotations": [],
        "dml_objects": _dml_objects_from_snippets(dml_snippets),
        "soql_objects": sorted(set(soql_objs)),
        "callout_detected": callout_detected,
        "api_version": _api_version_from_meta(meta_xml),
        "line_count": source.count("\n") + 1,
        "raw_xml_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "parse_error": parser.getNumberOfSyntaxErrors() > 0,
        "trigger_object": trigger_object,
        "trigger_events": trigger_events,
    }
```

- [ ] **Step 4: Create `backend/tests/services/salesforce/apex_parser/test_analyzer.py`**

```python
import pathlib

from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger


def test_analyze_apex_class_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountService.cls"
    out = analyze_apex_class(path.read_text(encoding="utf-8"), None)
    assert "updateRatings" in {m["name"] for m in out["methods"]}
    assert "accounts" in out["dml_objects"]
    assert "Contact" in out["soql_objects"]
    assert out["line_count"] >= 5


def test_analyze_apex_trigger_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountRating.trigger"
    out = analyze_apex_trigger(path.read_text(encoding="utf-8"), None)
    assert out["trigger_object"] == "Account"
    assert any("update" in e.lower() for e in out["trigger_events"])
```

- [ ] **Step 5: Run pytest**

```bash
cd backend && python -m pytest tests/services/salesforce/apex_parser/test_analyzer.py -v
```

**Expected:** 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/salesforce/apex_parser/analyzer.py backend/tests/services/salesforce/apex_parser/
git commit -m "Add Apex static analyzer using ANTLR visitor and fixtures."
```

---

## Phase 5: Pipeline Integration

### Task 12: MDAPI orchestration in `metadata.py` (keep `_legacy_*` fallbacks)

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py`
- Modify: `backend/app/models/metadata.py` (only if `MetadataDependency` delete import needed — already present)

- [ ] **Step 1: Extend imports at top of `metadata.py`**

Add `import asyncio` if not already present. Extend the existing `app.models.metadata` import to include `MetadataDependency` alongside `MetadataAutomation`, `MetadataComponent`, `MetadataField`, and `MetadataObject`. Append these new imports:

```python
from app.services.salesforce.mdapi_parser import (
    parse_approval_process,
    parse_custom_object,
    parse_flow,
    parse_workflow,
)
from app.services.salesforce.mdapi_retrieve import (
    MDAPIInsufficientAccessError,
    MDAPIRetrieveError,
    retrieve_metadata,
)
from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger
```

- [ ] **Step 2: Rename legacy pull functions (exact renames)**

In `metadata.py`, rename each definition and every internal call site:

| Old name | New name |
|----------|----------|
| `pull_flows` | `_legacy_pull_flows` |
| `pull_apex_triggers` | `_legacy_pull_apex_triggers` |
| `pull_workflow_rules` | `_legacy_pull_workflow_rules` |
| `pull_approval_processes` | `_legacy_pull_approval_processes` |
| `pull_validation_rules_bulk` | `_legacy_pull_validation_rules_bulk` |
| `pull_apex_classes` | `_legacy_pull_apex_classes` |
| `pull_page_layouts` | `_legacy_pull_page_layouts` |
| `pull_flexipages` | `_legacy_pull_flexipages` |
| `pull_business_processes` | `_legacy_pull_business_processes` |
| `pull_all_automations` | `_legacy_pull_all_automations` |
| `pull_all_ui_components` | `_legacy_pull_all_ui_components` |

Replace `pull_all_automations` body with:

```python
def _legacy_pull_all_automations(sf: Salesforce) -> list[AutomationMeta]:
    automations: list[AutomationMeta] = []
    automations.extend(_legacy_pull_flows(sf))
    automations.extend(_legacy_pull_apex_triggers(sf))
    automations.extend(_legacy_pull_workflow_rules(sf))
    automations.extend(_legacy_pull_approval_processes(sf))
    logger.info("sf_all_automations_complete total=%d", len(automations))
    return automations
```

Replace `pull_all_ui_components` similarly calling `_legacy_pull_page_layouts` and `_legacy_pull_flexipages`.

- [ ] **Step 3: Add MDAPI ingestion helper (append near bottom of `metadata.py`, before `sync_metadata`)**

Add `import hashlib` next to the existing `import json` at the top of `metadata.py` if not already present.

```python
def _query_flow_definition_versions(sf: Salesforce) -> dict[str, dict[str, str | None]]:
    rows = _tooling_query_all(
        sf,
        "SELECT DeveloperName, ActiveVersionId, LatestVersionId FROM FlowDefinitionView",
    )
    out: dict[str, dict[str, str | None]] = {}
    for row in rows:
        name = row.get("DeveloperName") or ""
        out[name] = {
            "active_version_id": row.get("ActiveVersionId"),
            "latest_version_id": row.get("LatestVersionId"),
        }
    return out


async def _mdapi_retrieve_files(sf: Salesforce) -> dict[str, bytes]:
    return await asyncio.to_thread(retrieve_metadata, sf)


def _persist_mdapi_zip_results(
    connection_id: UUID,
    org_id: UUID,
    files: dict[str, bytes],
    flow_versions: dict[str, dict[str, str | None]],
    db: AsyncSession,
) -> dict[str, Any]:
    """Parse zip paths into pending ORM rows; returns counters and object XML patches."""
    counts = {"flows": 0, "apex_classes": 0, "apex_triggers": 0, "objects": 0, "workflows": 0, "approvals": 0, "flexi": 0}
    pending_automations: list[MetadataAutomation] = []
    pending_components: list[MetadataComponent] = []
    pending_objects_patch: dict[str, dict] = {}

    for path, raw in files.items():
        lower = path.lower()
        if lower.endswith(".flow-meta.xml"):
            parsed = parse_flow(raw, path)
            dev_name = path.split("/")[-1].replace(".flow-meta.xml", "")
            fv = flow_versions.get(dev_name, {})
            parsed["flow_definition_view"] = fv
            if fv.get("active_version_id") and fv.get("latest_version_id"):
                parsed["active_matches_latest"] = fv["active_version_id"] == fv["latest_version_id"]
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="flow",
                    api_name=dev_name,
                    label=dev_name,
                    status=parsed.get("status"),
                    related_object=parsed.get("trigger_object"),
                    complexity_score=parsed.get("complexity_score"),
                    metadata_json=parsed,
                )
            )
            counts["flows"] += 1
        elif lower.endswith(".cls") and not lower.endswith("-meta.xml"):
            name = path.split("/")[-1].replace(".cls", "")
            meta_key = path.replace(".cls", ".cls-meta.xml")
            meta_xml = files.get(meta_key)
            src = raw.decode("utf-8", errors="replace")
            analyzed = analyze_apex_class(src, meta_xml=meta_xml)
            pending_components.append(
                MetadataComponent(
                    org_id=org_id,
                    connection_id=connection_id,
                    component_category="apex_class",
                    api_name=name,
                    label=name,
                    status="Active",
                    metadata_json=analyzed,
                )
            )
            counts["apex_classes"] += 1
        elif lower.endswith(".trigger") and not lower.endswith("-meta.xml"):
            name = path.split("/")[-1].replace(".trigger", "")
            meta_key = path.replace(".trigger", ".trigger-meta.xml")
            meta_xml = files.get(meta_key)
            src = raw.decode("utf-8", errors="replace")
            analyzed = analyze_apex_trigger(src, meta_xml=meta_xml)
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="trigger",
                    api_name=name,
                    label=name,
                    status="Active",
                    related_object=analyzed.get("trigger_object"),
                    metadata_json=analyzed,
                )
            )
            counts["apex_triggers"] += 1
        elif lower.endswith(".object-meta.xml"):
            parsed = parse_custom_object(raw, path)
            api_name = path.split("/")[-1].replace(".object-meta.xml", "")
            pending_objects_patch[api_name] = parsed
            counts["objects"] += 1
        elif lower.endswith(".workflow-meta.xml"):
            for row in parse_workflow(raw, path):
                pending_automations.append(
                    MetadataAutomation(
                        connection_id=connection_id,
                        org_id=org_id,
                        automation_type="workflow_rule",
                        api_name=row.get("api_name") or "",
                        label=row.get("api_name"),
                        status="Active" if row.get("active") else "Inactive",
                        related_object=row.get("related_object"),
                        metadata_json=row,
                    )
                )
                counts["workflows"] += 1
        elif lower.endswith(".approvalprocess-meta.xml"):
            parsed = parse_approval_process(raw, path)
            pending_automations.append(
                MetadataAutomation(
                    connection_id=connection_id,
                    org_id=org_id,
                    automation_type="approval_process",
                    api_name=parsed.get("api_name") or "",
                    label=parsed.get("api_name"),
                    status="Active" if parsed.get("active") else "Inactive",
                    related_object=parsed.get("related_object"),
                    metadata_json=parsed,
                )
            )
            counts["approvals"] += 1
        elif lower.endswith(".flexipage-meta.xml"):
            name = path.split("/")[-1].replace(".flexipage-meta.xml", "")
            pending_components.append(
                MetadataComponent(
                    org_id=org_id,
                    connection_id=connection_id,
                    component_category="flexipage",
                    api_name=name,
                    label=name,
                    metadata_json={"raw_xml_hash": hashlib.sha256(raw).hexdigest(), "source_path": path},
                )
            )
            counts["flexi"] += 1

    for auto in pending_automations:
        db.add(auto)
    for comp in pending_components:
        db.add(comp)

    return {"counts": counts, "object_patches": pending_objects_patch}
```

- [ ] **Step 4: Wire `sync_metadata` MDAPI path with fallback**

Inside `sync_metadata`, **before** deleting rows, after building `usage` / `objects` as today:

1. Call `_progress("mdapi_retrieve", "pulling", 0)` (requires Task 13 `PHASES` update first — if implementing Task 12 before Task 13, temporarily use existing phase strings, then switch).

2. Wrap MDAPI in:

```python
mdapi_files: dict[str, bytes] | None = None
try:
    mdapi_files = await _mdapi_retrieve_files(sf)
    _progress("mdapi_retrieve", "done", len(mdapi_files))
except (MDAPIInsufficientAccessError, MDAPIRetrieveError, Exception) as exc:
    logger.warning("mdapi_retrieve_failed falling_back_to_legacy error=%s", exc)
    mdapi_files = None
```

3. If `mdapi_files` is not `None`, run:

```python
_progress("mdapi_parse", "pulling", 0)
flow_versions = _query_flow_definition_versions(sf)
patch = _persist_mdapi_zip_results(connection_id, org_id, mdapi_files, flow_versions, db)
await db.flush()
_progress("mdapi_parse", "done", sum(patch["counts"].values()))
object_patches = patch["object_patches"]
```

4. When building each `MetadataObject` from `objects`, if `obj.api_name` in `object_patches`, merge `object_patches[obj.api_name]` keys (`validation_rules`, `formula_fields`, `record_types`, `field_sets`, `list_views`, `web_links`, `sharing_model`, `raw_xml_hash`, `source_filename`) into that row’s `metadata_json` alongside the existing REST describe payload.

5. If `mdapi_files` is `None`, call `_legacy_pull_all_automations`, `_legacy_pull_validation_rules_bulk`, `_legacy_pull_apex_classes`, `_legacy_pull_all_ui_components` exactly as the current `sync_metadata` body does today for automations/code/ui.

6. Add `await db.execute(delete(MetadataDependency).where(MetadataDependency.connection_id == connection_id))` alongside other deletes when `MetadataDependency` exists.

- [ ] **Step 5: Run pytest (no live Salesforce)**

```bash
cd backend && python -m pytest tests/services/salesforce/test_mdapi_parser_flow.py tests/services/salesforce/apex_parser/test_analyzer.py -q
```

**Expected:** green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/salesforce/metadata.py
git commit -m "Integrate MDAPI retrieve and parsers into metadata sync with legacy fallback."
```

---

### Task 13: Progress phases + graph pipeline in worker

**Files:**
- Modify: `backend/app/services/sync_progress.py`
- Create: `backend/app/services/metadata_graph.py`
- Create: `backend/tests/services/test_metadata_graph.py`
- Modify: `backend/app/workers/metadata_sync.py`

- [ ] **Step 1: Extend `PHASES` in `backend/app/services/sync_progress.py`**

Replace the `PHASES` list with:

```python
PHASES = [
    "objects",
    "mdapi_retrieve",
    "mdapi_parse",
    "automations",
    "code",
    "permissions",
    "ui_components",
    "installed_packages",
    "licensing",
    "user_velocity",
    "entities",
    "graph_build",
    "classification",
    "vectorization",
]
```

- [ ] **Step 2: Create `backend/app/services/metadata_graph.py`**

```python
"""Dependency edges and Leiden communities over parsed Salesforce metadata."""

from __future__ import annotations

import logging
from uuid import UUID

import igraph
import leidenalg
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Community
from app.models.metadata import MetadataAutomation, MetadataComponent, MetadataDependency, MetadataObject

logger = logging.getLogger(__name__)

LEIDEN_RESOLUTION = 1.0
LEIDEN_SEED = 42


async def build_dependency_graph(connection_id: UUID, org_id: UUID, db: AsyncSession) -> int:
    await db.execute(delete(MetadataDependency).where(MetadataDependency.connection_id == connection_id))
    edges: set[tuple[str, str, str, str, str, str]] = set()

    auto_rows = (await db.execute(select(MetadataAutomation).where(MetadataAutomation.connection_id == connection_id))).scalars().all()
    for row in auto_rows:
        mj = row.metadata_json or {}
        if row.automation_type == "flow":
            tobj = mj.get("trigger_object")
            if tobj:
                edges.add(("flow", row.api_name, "object", tobj, "triggers_on", "{}"))
            for o in mj.get("objects_touched", []) or []:
                edges.add(("flow", row.api_name, "object", o, "touches", "{}"))
        elif row.automation_type == "trigger":
            tobj = mj.get("trigger_object")
            if tobj:
                edges.add(("trigger", row.api_name, "object", tobj, "triggers_on", "{}"))
        elif row.automation_type == "workflow_rule":
            robj = mj.get("related_object") or row.related_object
            if robj:
                edges.add(("workflow_rule", row.api_name, "object", robj, "triggers_on", "{}"))

    comp_rows = (await db.execute(select(MetadataComponent).where(MetadataComponent.connection_id == connection_id))).scalars().all()
    for row in comp_rows:
        mj = row.metadata_json or {}
        if row.component_category == "apex_class":
            for o in mj.get("dml_objects", []) or []:
                edges.add(("apex_class", row.api_name, "object", o, "writes", "{}"))
            for o in mj.get("soql_objects", []) or []:
                edges.add(("apex_class", row.api_name, "object", o, "reads", "{}"))

    obj_rows = (await db.execute(select(MetadataObject).where(MetadataObject.connection_id == connection_id))).scalars().all()
    for row in obj_rows:
        mj = row.metadata_json or {}
        for rel in mj.get("relationships", []) or []:
            for tgt in rel.get("targets", []) or []:
                edges.add(("object", row.api_name, "object", tgt, rel.get("relationship_type", "lookup").lower(), "{}"))

    for src_type, src_name, tgt_type, tgt_name, rel_type, _ in edges:
        db.add(
            MetadataDependency(
                org_id=org_id,
                connection_id=connection_id,
                source_type=src_type,
                source_api_name=src_name,
                target_type=tgt_type,
                target_api_name=tgt_name,
                relationship_type=rel_type,
                metadata_json={},
            )
        )
    await db.flush()
    return len(edges)


async def detect_metadata_communities(org_id: UUID, db: AsyncSession) -> list[UUID]:
    await db.execute(
        delete(Community).where(
            Community.org_id == org_id,
            Community.metadata_json.contains({"source": "metadata_graph"}),
        )
    )

    dep_rows = (
        await db.execute(select(MetadataDependency).where(MetadataDependency.org_id == org_id))
    ).scalars().all()
    vertices: set[str] = set()
    edge_pairs: list[tuple[str, str]] = []
    for d in dep_rows:
        a = f"{d.source_type}:{d.source_api_name}"
        b = f"{d.target_type}:{d.target_api_name}"
        if a == b:
            continue
        vertices.add(a)
        vertices.add(b)
        edge_pairs.append((a, b))

    if len(vertices) < 2:
        await db.flush()
        return []

    vid = {v: i for i, v in enumerate(sorted(vertices))}
    unique_e: set[tuple[int, int]] = set()
    for x, y in edge_pairs:
        if x not in vid or y not in vid:
            continue
        i, j = vid[x], vid[y]
        if i == j:
            continue
        unique_e.add((i, j) if i < j else (j, i))
    if len(unique_e) < 1:
        await db.flush()
        return []

    g = igraph.Graph(n=len(vid), directed=False)
    g.add_edges(list(unique_e))
    g.es["weight"] = [1.0] * g.ecount()

    partition = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        weights=g.es["weight"],
        resolution_parameter=LEIDEN_RESOLUTION,
        seed=LEIDEN_SEED,
    )

    idx_to_v = {i: v for v, i in vid.items()}
    new_ids: list[UUID] = []
    for members in partition:
        if len(members) < 2:
            continue
        member_keys = [idx_to_v[i] for i in members]
        comm = Community(
            org_id=org_id,
            level=0,
            label=f"metadata_cluster_{len(new_ids)}",
            member_concept_ids=member_keys,
            metadata_json={"source": "metadata_graph"},
        )
        db.add(comm)
        await db.flush()
        new_ids.append(comm.id)
    return new_ids
```

- [ ] **Step 3: Add test `backend/tests/services/test_metadata_graph.py`**

```python
def test_metadata_graph_exports():
    from app.services.metadata_graph import build_dependency_graph, detect_metadata_communities

    assert callable(build_dependency_graph)
    assert callable(detect_metadata_communities)
```

**Optional (Postgres integration):** After migrations, add a second test that uses the project’s configured async engine and inserts real `MetadataAutomation` rows, then asserts `MetadataDependency` row count increases. Keep the import-only test as the default so CI without Postgres JSON fixtures still passes.

- [ ] **Step 4: Modify `backend/app/workers/metadata_sync.py`**

After `await sync_metadata(...)` succeeds, insert:

```python
from app.services.metadata_graph import build_dependency_graph, detect_metadata_communities

# ...

update_phase(connection_id, "graph_build", "pulling", 0, r)
try:
    async with factory() as session:
        conn = await session.get(PlatformConnection, UUID(connection_id))
        if conn:
            edge_count = await build_dependency_graph(UUID(connection_id), conn.org_id, session)
            await detect_metadata_communities(conn.org_id, session)
            await session.commit()
        else:
            edge_count = 0
    update_phase(connection_id, "graph_build", "done", edge_count, r)
except Exception:
    logger.exception("graph_build_failed connection=%s", connection_id)
    update_phase(connection_id, "graph_build", "done", 0, r)
```

Ensure `PlatformConnection` is already imported in that scope.

- [ ] **Step 5: Run pytest**

```bash
cd backend && python -m pytest tests/services/test_metadata_graph.py -v
```

**Expected:** At least one assertion passes (import-only or async test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync_progress.py backend/app/services/metadata_graph.py backend/app/workers/metadata_sync.py backend/tests/services/test_metadata_graph.py
git commit -m "Add MDAPI progress phases and metadata dependency graph build."
```

---

## Phase 6: Dependency Graph

### Task 14: `metadata_graph.py` — edge extraction

**Files:**
- Create: `backend/app/services/metadata_graph.py`
- Create: `backend/tests/services/test_metadata_graph.py`

- [ ] **Step 1: Create `backend/app/services/metadata_graph.py`**

Full implementation with streaming queries (AP-12), target-object validation (AP-11), deduplication, and batch insert. See the complete module below — it contains `build_dependency_graph`, all `_edges_from_*` helpers, `_dedupe_edges`, and `_filter_edge_for_objects`.

```python
"""Build metadata dependency edges and run graph-derived community detection."""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Community
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataObject,
)

logger = logging.getLogger(__name__)

YIELD_PER = 200
METADATA_LEIDEN_SEED = 42
METADATA_LEIDEN_N_ITERATIONS = -1
METADATA_CPM_RESOLUTION = 0.05
METADATA_MIN_COMMUNITY_SIZE = 2


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict] = []
    for e in edges:
        key = (e["source_type"], e["source_api_name"], e["relationship_type"],
               e["target_type"], e["target_api_name"])
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _as_str_list(val: object) -> list[str]:
    if not isinstance(val, list):
        return []
    return [x.strip() for x in val if isinstance(x, str) and x.strip()]


def _filter_edge_for_objects(e: dict, valid_objects: set[str]) -> bool:
    if e["target_type"] != "object":
        return True
    return e["target_api_name"] in valid_objects


def _edges_from_flow(api: str, meta: dict) -> list[dict]:
    edges: list[dict] = []
    trig = meta.get("trigger_object")
    if isinstance(trig, str) and trig:
        edges.append({"source_type": "flow", "source_api_name": api,
                       "relationship_type": "triggers_on", "target_type": "object",
                       "target_api_name": trig, "metadata_json": {}})
    elems = meta.get("elements") or {}
    for rl in elems.get("record_lookups") or []:
        obj = rl.get("object") if isinstance(rl, dict) else None
        if obj:
            edges.append({"source_type": "flow", "source_api_name": api,
                           "relationship_type": "reads", "target_type": "object",
                           "target_api_name": obj, "metadata_json": {}})
    for key in ("record_creates", "record_updates", "record_deletes"):
        for el in elems.get(key) or []:
            obj = el.get("object") if isinstance(el, dict) else None
            if obj:
                edges.append({"source_type": "flow", "source_api_name": api,
                               "relationship_type": "writes", "target_type": "object",
                               "target_api_name": obj, "metadata_json": {}})
    for sf in elems.get("subflows") or []:
        name = sf.get("flow_name") if isinstance(sf, dict) else None
        if name:
            edges.append({"source_type": "flow", "source_api_name": api,
                           "relationship_type": "calls_subflow", "target_type": "flow",
                           "target_api_name": name, "metadata_json": {}})
    for ac in elems.get("action_calls") or []:
        if not isinstance(ac, dict):
            continue
        if ac.get("action_type") == "apex":
            edges.append({"source_type": "flow", "source_api_name": api,
                           "relationship_type": "invokes_apex", "target_type": "apex_class",
                           "target_api_name": ac.get("action_name", ""), "metadata_json": {}})
        elif ac.get("action_type") == "emailAlert":
            edges.append({"source_type": "flow", "source_api_name": api,
                           "relationship_type": "sends_email", "target_type": "email_template",
                           "target_api_name": ac.get("action_name", ""), "metadata_json": {}})
    return edges


def _edges_from_apex_class(api: str, meta: dict) -> list[dict]:
    edges: list[dict] = []
    for obj in _as_str_list(meta.get("soql_objects")):
        edges.append({"source_type": "apex_class", "source_api_name": api,
                       "relationship_type": "reads", "target_type": "object",
                       "target_api_name": obj, "metadata_json": {}})
    for obj in _as_str_list(meta.get("dml_objects")):
        edges.append({"source_type": "apex_class", "source_api_name": api,
                       "relationship_type": "writes", "target_type": "object",
                       "target_api_name": obj, "metadata_json": {}})
    return edges


def _edges_from_object_relationships(api: str, rels: list) -> list[dict]:
    edges: list[dict] = []
    for r in rels:
        if not isinstance(r, dict):
            continue
        ref = r.get("referenceTo") or r.get("references_to") or []
        rtype = r.get("relationshipType", r.get("type", "lookup")).lower()
        rel = "master_detail" if "master" in rtype else "lookup"
        targets = ref if isinstance(ref, list) else [ref]
        for t in targets:
            if isinstance(t, str) and t:
                edges.append({"source_type": "object", "source_api_name": api,
                               "relationship_type": rel, "target_type": "object",
                               "target_api_name": t, "metadata_json": {}})
    return edges


async def build_dependency_graph(connection_id: UUID, org_id: UUID, db: AsyncSession) -> int:
    await db.execute(delete(MetadataDependency).where(
        MetadataDependency.connection_id == connection_id))
    await db.flush()

    valid_objects: set[str] = set()
    res = await db.execute(select(MetadataObject.api_name).where(
        MetadataObject.connection_id == connection_id))
    valid_objects.update(r[0] for r in res.all())

    all_edges: list[dict] = []

    auto_stmt = select(MetadataAutomation).where(
        MetadataAutomation.connection_id == connection_id
    ).execution_options(yield_per=YIELD_PER)
    stream = await db.stream(auto_stmt)
    async for part in stream.partitions(YIELD_PER):
        for auto in part:
            meta = auto.metadata_json or {}
            t = auto.automation_type
            if t == "flow":
                all_edges.extend(_edges_from_flow(auto.api_name, meta))
            elif t in ("trigger", "apex_trigger"):
                obj = meta.get("trigger_object") or auto.related_object
                if obj:
                    all_edges.append({"source_type": "apex_trigger", "source_api_name": auto.api_name,
                                       "relationship_type": "triggers_on", "target_type": "object",
                                       "target_api_name": obj, "metadata_json": {}})
            elif t == "validation_rule" and auto.related_object:
                all_edges.append({"source_type": "validation_rule", "source_api_name": auto.api_name,
                                   "relationship_type": "validates", "target_type": "object",
                                   "target_api_name": auto.related_object, "metadata_json": {}})
            elif t == "workflow_rule" and auto.related_object:
                all_edges.append({"source_type": "workflow_rule", "source_api_name": auto.api_name,
                                   "relationship_type": "triggers_on", "target_type": "object",
                                   "target_api_name": auto.related_object, "metadata_json": {}})
            elif t == "approval_process" and auto.related_object:
                all_edges.append({"source_type": "approval_process", "source_api_name": auto.api_name,
                                   "relationship_type": "triggers_on", "target_type": "object",
                                   "target_api_name": auto.related_object, "metadata_json": {}})

    comp_stmt = select(MetadataComponent).where(
        MetadataComponent.connection_id == connection_id,
        MetadataComponent.component_category == "apex_class",
    ).execution_options(yield_per=YIELD_PER)
    comp_stream = await db.stream(comp_stmt)
    async for part in comp_stream.partitions(YIELD_PER):
        for comp in part:
            all_edges.extend(_edges_from_apex_class(comp.api_name, comp.metadata_json or {}))

    obj_stmt = select(MetadataObject).where(
        MetadataObject.connection_id == connection_id
    ).execution_options(yield_per=YIELD_PER)
    obj_stream = await db.stream(obj_stmt)
    async for part in obj_stream.partitions(YIELD_PER):
        for obj in part:
            rels = (obj.metadata_json or {}).get("relationships") or []
            all_edges.extend(_edges_from_object_relationships(obj.api_name, rels))

    filtered = [e for e in _dedupe_edges(all_edges)
                if _filter_edge_for_objects(e, valid_objects)]
    if not filtered:
        return 0

    for i in range(0, len(filtered), 500):
        rows = [{"org_id": org_id, "connection_id": connection_id, **e} for e in filtered[i:i+500]]
        await db.execute(pg_insert(MetadataDependency), rows)
    await db.flush()
    logger.info("build_dependency_graph connection=%s edges=%d", connection_id, len(filtered))
    return len(filtered)
```

- [ ] **Step 2: Write tests**

Create `backend/tests/services/test_metadata_graph.py`:

```python
import pytest
from app.services.metadata_graph import (
    _edges_from_flow, _edges_from_apex_class,
    _edges_from_object_relationships, _filter_edge_for_objects, _dedupe_edges,
)


def test_edges_from_flow():
    meta = {
        "trigger_object": "Account",
        "elements": {
            "record_lookups": [{"object": "Contact"}],
            "record_creates": [{"object": "Task"}],
            "record_updates": [],
            "record_deletes": [],
            "subflows": [{"flow_name": "Sub_Flow"}],
            "action_calls": [
                {"action_type": "apex", "action_name": "MyService"},
                {"action_type": "emailAlert", "action_name": "WelcomeEmail"},
            ],
        },
    }
    edges = _edges_from_flow("Test_Flow", meta)
    rels = {(e["relationship_type"], e["target_api_name"]) for e in edges}
    assert ("triggers_on", "Account") in rels
    assert ("reads", "Contact") in rels
    assert ("writes", "Task") in rels
    assert ("calls_subflow", "Sub_Flow") in rels
    assert ("invokes_apex", "MyService") in rels
    assert ("sends_email", "WelcomeEmail") in rels


def test_edges_from_apex_class():
    edges = _edges_from_apex_class("Svc", {"soql_objects": ["Account"], "dml_objects": ["Case"]})
    assert len(edges) == 2
    assert edges[0]["relationship_type"] == "reads"
    assert edges[1]["relationship_type"] == "writes"


def test_filter_edge_drops_unknown_object():
    valid = {"Account"}
    good = {"source_type": "flow", "source_api_name": "F", "relationship_type": "reads",
            "target_type": "object", "target_api_name": "Account", "metadata_json": {}}
    bad = {**good, "target_api_name": "Fake__c"}
    assert _filter_edge_for_objects(good, valid) is True
    assert _filter_edge_for_objects(bad, valid) is False


def test_dedupe_edges():
    e = {"source_type": "flow", "source_api_name": "F", "relationship_type": "reads",
         "target_type": "object", "target_api_name": "A", "metadata_json": {}}
    assert len(_dedupe_edges([e, e, e])) == 1
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/services/test_metadata_graph.py -v`
Expected: 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/metadata_graph.py backend/tests/services/test_metadata_graph.py
git commit -m "feat(metadata): dependency graph edge extraction with streaming and validation"
```

---

### Task 15: Community detection for metadata graph

**Files:**
- Modify: `backend/app/services/metadata_graph.py` (append)

- [ ] **Step 1: Add `detect_metadata_communities` to `metadata_graph.py`**

```python
import igraph
import leidenalg


def _node_id(t: str, name: str) -> str:
    return f"{t}:{name}"


async def detect_metadata_communities(
    connection_id: UUID, org_id: UUID, db: AsyncSession,
) -> int:
    dep_stmt = select(
        MetadataDependency.source_type, MetadataDependency.source_api_name,
        MetadataDependency.target_type, MetadataDependency.target_api_name,
    ).where(MetadataDependency.connection_id == connection_id)
    res = await db.execute(dep_stmt)

    nodes: set[str] = set()
    edge_pairs: list[tuple[str, str]] = []
    for st, sa, tt, ta in res.all():
        a, b = _node_id(st, sa), _node_id(tt, ta)
        nodes.add(a)
        nodes.add(b)
        if a != b:
            edge_pairs.append((a, b))

    await db.execute(delete(Community).where(
        Community.org_id == org_id,
        sa.cast(Community.metadata_json["source"], sa.String) == "metadata_graph",
    ))
    await db.flush()

    if len(nodes) < 2 or not edge_pairs:
        logger.info("detect_metadata_communities_skip connection=%s", connection_id)
        return 0

    index = {n: i for i, n in enumerate(sorted(nodes))}
    rev = {i: n for n, i in index.items()}
    g = igraph.Graph(n=len(index), directed=False)
    g.add_edges([(index[a], index[b]) for a, b in edge_pairs])

    partition = leidenalg.find_partition(
        g, leidenalg.CPMVertexPartition,
        resolution_parameter=METADATA_CPM_RESOLUTION,
        n_iterations=METADATA_LEIDEN_N_ITERATIONS, seed=METADATA_LEIDEN_SEED,
    )

    created = 0
    for members in partition:
        member_ids = [rev[m] for m in members]
        if len(member_ids) < METADATA_MIN_COMMUNITY_SIZE:
            continue
        top3 = sorted(member_ids, key=lambda x: x.split(":", 1)[1])[:3]
        label = ", ".join(n.split(":", 1)[1] for n in top3)
        db.add(Community(
            org_id=org_id, level=0, label=label[:512],
            member_concept_ids=member_ids,
            metadata_json={"source": "metadata_graph", "connection_id": str(connection_id),
                           "member_count": len(member_ids)},
        ))
        created += 1
    await db.flush()
    logger.info("detect_metadata_communities connection=%s communities=%d", connection_id, created)
    return created
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/metadata_graph.py
git commit -m "feat(metadata): Leiden CPM community detection on dependency graph"
```

---

## Phase 7: Vectorizer Updates

### Task 16: Enrich `_describe_automation` for rich MDAPI data

**Files:**
- Modify: `backend/app/services/metadata_vectorizer.py` (lines 68-82)

- [ ] **Step 1: Replace `_describe_automation`**

Replace the function at lines 68-82 with the version that branches on rich JSONB content — Flow elements, workflow criteria, approval steps, validation formulas. Full code in the `metadata_vectorizer.py` `_describe_automation` replacement (see spec section 4 for exact output formats).

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/metadata_vectorizer.py
git commit -m "feat(vectorizer): rich automation descriptions from MDAPI JSONB"
```

---

### Task 17: Method-boundary chunking for Apex components

**Files:**
- Modify: `backend/app/services/metadata_vectorizer.py`

- [ ] **Step 1: Add `describe_component_chunks` function**

Returns a list of `(suffix, content)` tuples — one overview chunk plus one per significant method for Apex classes with parsed methods in JSONB. Falls back to a single chunk for non-Apex or non-enriched components.

- [ ] **Step 2: Update the components loop in `vectorize_org_metadata`**

Replace the single-chunk-per-component pattern with iteration over `describe_component_chunks(comp)`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/metadata_vectorizer.py
git commit -m "feat(vectorizer): method-boundary chunking for Apex classes"
```

---

### Task 18: Enrich `_describe_object` with MDAPI data

**Files:**
- Modify: `backend/app/services/metadata_vectorizer.py` (lines 24-65)

- [ ] **Step 1: Append enrichment to `_describe_object`**

After existing content, check `metadata_json` for `validation_rules`, `formula_fields`, `field_sets`, `list_views`, `sharing_model` and append descriptions.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/metadata_vectorizer.py
git commit -m "feat(vectorizer): enriched object descriptions with VRs, formulas, field sets"
```

---

### Task 19: Vectorizer integration test

**Files:**
- Create: `backend/tests/services/test_metadata_vectorizer_rich.py`

- [ ] **Step 1: Write integration test**

Seed MetadataObject/Automation/Component rows with rich JSONB, mock `vectorize_chunks`, call `vectorize_org_metadata`, assert chunk count and content contains expected strings.

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/services/test_metadata_vectorizer_rich.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/test_metadata_vectorizer_rich.py
git commit -m "test(vectorizer): integration test for rich MDAPI vectorization"
```

---

## Phase 8: Custom Metadata Types

### Task 20: Pull Custom Metadata Types

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py`
- Create: `backend/tests/services/salesforce/test_custom_metadata_types.py`

- [ ] **Step 1: Add `pull_custom_metadata_types` to `metadata.py`**

```python
def pull_custom_metadata_types(sf: Salesforce, objects_list: list[dict]) -> list[dict]:
    """Pull Custom Metadata Type records for all __mdt objects in the org.

    Custom Metadata Types store org configuration (territory rules, routing
    configs, feature flags) that inform process discovery.

    Returns list of dicts: {"metadata_type": "MyConfig__mdt", "record_count": N,
    "records": [...], "fields": [...]}
    """
    cmdt_objects = [
        o["name"] for o in objects_list
        if o.get("name", "").endswith("__mdt") and o.get("queryable")
    ]
    if not cmdt_objects:
        return []

    results = []
    for cmdt_name in cmdt_objects:
        try:
            result = sf.query_all(f"SELECT FIELDS(ALL) FROM {cmdt_name} LIMIT 200")
            records = result.get("records", [])
            field_names = []
            if records:
                field_names = [k for k in records[0].keys()
                               if k != "attributes" and not k.startswith("_")]
            results.append({
                "metadata_type": cmdt_name,
                "record_count": len(records),
                "records": records,
                "fields": field_names,
            })
        except Exception:
            logger.debug("cmdt_query_skipped type=%s", cmdt_name)
    logger.info("pull_custom_metadata_types count=%d", len(results))
    return results
```

- [ ] **Step 2: Wire into `sync_metadata`**

After the installed_packages block in `sync_metadata`, add:

```python
_progress("custom_metadata_types", "pulling", 0)
objects_list_raw = pull_object_list(sf)
cmdts = pull_custom_metadata_types(sf, objects_list_raw)
for cmdt in cmdts:
    db.add(
        MetadataComponent(
            org_id=org_id,
            connection_id=connection_id,
            component_category="custom_metadata_type",
            api_name=cmdt["metadata_type"],
            label=cmdt["metadata_type"].replace("__mdt", "").replace("_", " "),
            metadata_json={
                "record_count": cmdt["record_count"],
                "fields": cmdt["fields"],
                "records": cmdt["records"][:50],
            },
        )
    )
_progress("custom_metadata_types", "done", len(cmdts))
```

- [ ] **Step 3: Add progress phase**

Add `"custom_metadata_types"` to `PHASES` in `backend/app/services/sync_progress.py`.

- [ ] **Step 4: Update vectorizer `_describe_component` for custom_metadata_type**

In the `describe_component_chunks` function (or `_describe_component`), add a branch:

```python
elif comp.component_category == "custom_metadata_type":
    lines.append(f"Custom Metadata Type: {comp.api_name}")
    rec_count = meta.get("record_count", 0)
    lines.append(f"Records: {rec_count}")
    fields = meta.get("fields", [])
    if fields:
        lines.append(f"Fields: {', '.join(str(f) for f in fields[:20])}")
    records = meta.get("records", [])
    if records:
        lines.append("Sample values:")
        for rec in records[:5]:
            vals = {k: v for k, v in rec.items()
                    if k != "attributes" and v is not None}
            lines.append(f"  {vals}")
```

- [ ] **Step 5: Write test**

Create `backend/tests/services/salesforce/test_custom_metadata_types.py`:

```python
from unittest.mock import MagicMock
from app.services.salesforce.metadata import pull_custom_metadata_types


def test_pull_custom_metadata_types_filters_mdt():
    sf = MagicMock()
    sf.query_all.return_value = {
        "records": [
            {"attributes": {"type": "Config__mdt"}, "Label": "Rule1", "Value__c": "X"}
        ]
    }
    objects_list = [
        {"name": "Account", "queryable": True},
        {"name": "Config__mdt", "queryable": True},
        {"name": "Hidden__mdt", "queryable": False},
    ]
    result = pull_custom_metadata_types(sf, objects_list)
    assert len(result) == 1
    assert result[0]["metadata_type"] == "Config__mdt"
    assert result[0]["record_count"] == 1
    sf.query_all.assert_called_once()


def test_pull_custom_metadata_types_empty_org():
    sf = MagicMock()
    result = pull_custom_metadata_types(sf, [{"name": "Account", "queryable": True}])
    assert result == []
    sf.query_all.assert_not_called()
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/services/salesforce/test_custom_metadata_types.py -v`
Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/salesforce/metadata.py backend/app/services/metadata_vectorizer.py backend/app/services/sync_progress.py backend/tests/services/salesforce/test_custom_metadata_types.py
git commit -m "feat(metadata): pull Custom Metadata Types for org configuration context"
```

---

## Final verification bundle

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

**Expected:** All tests pass.

---

## Closing commit

```bash
git add docs/superpowers/plans/2026-04-19-mdapi-metadata-enrichment.md
git commit -m "docs: MDAPI metadata enrichment implementation plan"
```
