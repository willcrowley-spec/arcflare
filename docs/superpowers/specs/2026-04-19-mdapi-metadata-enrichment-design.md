# Salesforce Metadata API Migration + Dependency Graph

**Date**: 2026-04-19
**Status**: Draft
**Scope**: Replace Tooling API metadata retrieval with Metadata API retrieve, add deterministic XML parsing with JSONB storage, build a metadata dependency graph, and enrich the vectorizer for dramatically better process discovery quality.

---

## Context & Problem Statement

The current metadata sync in `backend/app/services/salesforce/metadata.py` uses REST Describe + Tooling SOQL + REST composite endpoints via `simple_salesforce`. This captures catalog-level data only:

- **Flows**: `Id, MasterLabel, ProcessType, Status, Description` — no element graph, no decisions, no DML operations, no connected objects. `related_objects` is always empty.
- **Apex Classes**: `Id, Name, ApiVersion, Status, LengthWithoutComments` — no source code, no method signatures, no DML/SOQL targets.
- **Apex Triggers**: events and related object, but no trigger body.
- **Validation Rules**: `ValidationName, Active, Description, ErrorMessage` — no `ErrorConditionFormula`.
- **Workflow Rules**: `Name, TableEnumOrId` — no criteria formula, no associated actions.
- **Approval Processes**: name and description from REST — no entry criteria, no steps, no assignees.

The process discovery pipeline can see THAT automations exist but not WHAT they do. The vectorizer (`backend/app/services/metadata_vectorizer.py`) generates thin descriptions like "Salesforce Automation: Update Account Rating / Type: flow / Status: Active" because that is all the data it has.

No Metadata API (`sf.mdapi`) calls exist in the codebase. A repo-wide search for `listMetadata`, `readMetadata`, `mdapi`, `MetadataService` returns zero matches outside docstrings.

---

## Research Summary

### Sources Consulted

- **arxiv 2601.08773** (Jan 2026) — AST-derived graphs vs LLM-extracted knowledge graphs for code RAG
- **Meta FAIR code2seq** — structured AST path representations for code understanding
- **Meta FAIR AST-T5** (2024) — structure-aware pretraining for code generation and transpilation
- **MIT SPIRAL** (2025) — iterative subgraph expansion for knowledge-graph-based RAG
- **Google DeepMind QUEST-LOFT** — structured output formats improve multi-document RAG
- **Practical GraphRAG at Scale** (arxiv 2507.03226) — hybrid retrieval fusing vector similarity + graph traversal
- **TrailMeta** — 7-tier Salesforce metadata extraction with two-pass Gemini analysis, 4+ unified SF APIs
- **Salesforce DescribeFlow prompt template** — Flow XML to human-readable documentation
- **ServiceNow DeepCodeSeek** (2025) — platform metadata + multi-stage retrieval for code generation (87.86% top-40 accuracy)

### Key Findings

| Finding | Source | Impact |
|---------|--------|--------|
| Deterministic AST-derived graphs achieve 0.902 corpus coverage vs 0.641 for LLM-extracted, at 2.25x cost of vector-only (vs 19.75x for LLM-extracted) | arxiv 2601.08773 | Validates deterministic parsing over LLM extraction for metadata graph |
| Vector-only search fails on multi-hop architectural queries (controller→service→repository chains) | arxiv 2601.08773 | Process discovery asks inherently multi-hop questions; graph traversal required |
| Structured AST path representations outperform raw token sequences for code understanding | Meta FAIR code2seq, AST-T5 | Method-boundary chunking for Apex, not raw source embedding. ANTLR4 Apex grammar (`apex-dev-tools/apex-parser`) available with Python target for full AST-based static analysis |
| KG-based RAG achieves 0.95 triple recall with compact subgraphs, sub-second inference on million-edge graphs | MIT SPIRAL (2025) | Dependency graph is viable at our scale |
| RAG with structured output + reasoning significantly outperforms long-context approaches on multi-document questions | Google DeepMind QUEST-LOFT | Supports "parse into structure, describe as text, embed" pattern |
| Hybrid retrieval fusing vector similarity + graph traversal via Reciprocal Rank Fusion achieves best results | Practical GraphRAG at Scale | Extend existing community-filtered vector search to metadata |
| Tools like Gearset and Copado use Metadata API as primary retrieval mechanism for org configuration | Industry consensus | Validates MDAPI as the right tool for complete definitions |
| Salesforce MDAPI CustomObject XML includes fields, validation rules with formulas, record types, field sets, list views, web links, compact layouts | Salesforce developer docs | Single retrieve gives richer data than multiple Tooling SOQL calls |
| For standard objects, MDAPI returns custom fields only (not standard fields like Account.Name) | SF StackExchange 108451 | LLM native knowledge covers standard fields for process discovery |

---

## Decision Summary

- **Primary retrieval**: Salesforce Metadata API `retrieve()` for all logic-bearing types
- **Keep REST/SOQL for**: record counts, velocity, licensing, limits, global object list, permission sets, profiles
- **Standard object standard fields**: rely on LLM native knowledge (defer shared platform knowledge base to a separate spec)
- **Parsing**: deterministic XML parsing into structured JSONB (no LLM enrichment at parse time). Apex source parsed via ANTLR4 AST for accurate DML/SOQL/method extraction.
- **Graph**: deterministic dependency graph extracted from parsed JSONB, with Leiden community detection
- **No pre-embed LLM enrichment**: the discovery pipeline's LLM stages handle business-intent interpretation at query time
- **Vectorization**: same pipeline as today (`vectorize_chunks` → Gemini embedding → pgvector), but with dramatically richer `_describe_*` templates consuming the MDAPI-parsed JSONB

---

## Architecture

### Pipeline Overview

```
Salesforce Org
       │
       ├── Metadata API retrieve() ──────────────────────────────────┐
       │   (Flow, ApexClass, ApexTrigger, CustomObject,              │
       │    Workflow, ApprovalProcess, FlexiPage)                    │
       │                                                             │
       │        ┌────────────────────────────────────────────────┐   │
       │        │              MDAPI Retrieve                    │   │
       │        │  1. Build package.xml                          │   │
       │        │  2. sf.mdapi.retrieve() (async)                │   │
       │        │  3. Poll check_retrieve_status()               │   │
       │        │  4. Download + extract zip                     │   │
       │        └──────────────┬─────────────────────────────────┘   │
       │                       │                                     │
       │                       ▼                                     │
       │        ┌────────────────────────────────────────────────┐   │
       │        │              XML Parsing                       │   │
       │        │  - .flow-meta.xml → Flow element graph         │   │
       │        │  - .cls / .trigger → Apex source + signatures  │   │
       │        │  - .object-meta.xml → VR formulas, fields      │   │
       │        │  - Workflow XML → criteria + actions            │   │
       │        │  - Approval XML → steps + criteria             │   │
       │        └──────────────┬─────────────────────────────────┘   │
       │                       │                                     │
       │                       ▼                                     │
       │        ┌──────────────────────────────┐                     │
       │        │  Store in metadata_json JSONB │                     │
       │        │  (MetadataAutomation,         │                     │
       │        │   MetadataComponent,          │                     │
       │        │   MetadataObject)             │                     │
       │        └──────────┬───────────────────┘                     │
       │                   │                                         │
       │          ┌────────┴────────┐                                │
       │          │                 │                                 │
       │          ▼                 ▼                                 │
       │  ┌─────────────┐  ┌───────────────┐                        │
       │  │ Dependency   │  │ Vectorizer    │                        │
       │  │ Graph +      │  │ (richer       │                        │
       │  │ Communities  │  │ _describe_*)  │                        │
       │  └─────────────┘  └───────────────┘                        │
       │                                                             │
       ├── REST sf.describe() ── global object list (kept)           │
       ├── SOQL COUNT() ── record counts, velocity (kept)            │
       ├── SOQL ── permission sets, profiles (kept)                  │
       ├── REST limits/ ── API limits (kept)                         │
       └── SOQL ── licensing, user velocity (kept)                   │
```

### New Modules

| Module | Purpose |
|--------|---------|
| `backend/app/services/salesforce/mdapi_retrieve.py` | MDAPI retrieve orchestration: build package.xml, async retrieve, poll, download, extract |
| `backend/app/services/salesforce/mdapi_parser.py` | Deterministic XML parsers per metadata type |
| `backend/app/services/metadata_graph.py` | Dependency edge extraction + Leiden community detection |

### Modified Modules

| Module | Changes |
|--------|---------|
| `backend/app/services/salesforce/metadata.py` | Remove `pull_flows`, `pull_apex_triggers`, `pull_apex_classes`, `pull_validation_rules_bulk`, `pull_workflow_rules`, `pull_approval_processes`, `pull_business_processes`, `pull_page_layouts`, `pull_flexipages`. Add MDAPI orchestration call. Update `sync_metadata` to use parsed MDAPI data. Keep `pull_installed_packages` (platform limitation — no MDAPI equivalent), permission/profile pulls, usage data, object describes. |
| `backend/app/services/metadata_vectorizer.py` | Richer `_describe_automation`, `_describe_component`, `_describe_object` using MDAPI-parsed JSONB. Method-boundary chunking for Apex. |
| `backend/app/models/metadata.py` | Add `MetadataDependency` model |
| `backend/app/workers/metadata_sync.py` | Add graph-building and community-detection phases to the pipeline |

---

## 1. MDAPI Retrieve

### package.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>*</members>
        <name>Flow</name>
    </types>
    <types>
        <members>*</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>*</members>
        <name>ApexTrigger</name>
    </types>
    <types>
        <members>*</members>
        <name>CustomObject</name>
    </types>
    <types>
        <members>*</members>
        <name>Workflow</name>
    </types>
    <types>
        <members>*</members>
        <name>ApprovalProcess</name>
    </types>
    <types>
        <members>*</members>
        <name>FlexiPage</name>
    </types>
    <version>62.0</version>
</Package>
```

The `Workflow` type bundles WorkflowRule, WorkflowFieldUpdate, WorkflowAlert, WorkflowOutboundMessage, and WorkflowTask under a single per-object XML file. This is more efficient than pulling each sub-type separately.

### Retrieve Pattern

New module: `backend/app/services/salesforce/mdapi_retrieve.py`

```python
async def retrieve_metadata(sf: Salesforce, api_version: str = "62.0") -> dict[str, bytes]:
    """Retrieve metadata via MDAPI, return mapping of relative_path -> file_bytes."""
```

Steps:
1. Build `package.xml` string with the types above
2. Call `sf.mdapi.retrieve(package_xml)` — returns an async job ID
3. Poll `sf.mdapi.check_retrieve_status(job_id)` with exponential backoff (1s, 2s, 4s, max 8s intervals, timeout 300s)
4. On completion, the response includes a base64-encoded zip
5. Decode and extract the zip in memory using `zipfile.ZipFile(io.BytesIO(...))`
6. Return a dict mapping relative path (e.g., `flows/Update_Account_Rating.flow-meta.xml`) to raw bytes

Error handling:
- If retrieve fails (insufficient permissions, timeout), fall back to the existing Tooling SOQL approach for that sync run and log a warning. This preserves backward compatibility during rollout.
- Rate limit: MDAPI retrieve counts against org limits. One retrieve per sync is well within bounds.

### OAuth Scope

Current scope is `api refresh_token` (line 35 of `oauth.py`). The `api` scope grants access to the Metadata API — no scope change required.

### Functions Removed from metadata.py

| Function | Replacement |
|----------|-------------|
| `pull_flows()` | MDAPI Flow type |
| `pull_apex_triggers()` | MDAPI ApexTrigger type |
| `pull_apex_classes()` | MDAPI ApexClass type |
| `pull_validation_rules_bulk()` | MDAPI CustomObject type (VRs included in object XML) |
| `pull_workflow_rules()` | MDAPI Workflow type |
| `pull_approval_processes()` | MDAPI ApprovalProcess type |
| `pull_business_processes()` | MDAPI CustomObject type (business processes included) |
| `pull_page_layouts()` | MDAPI CustomObject type (layouts included) |
| `pull_flexipages()` | MDAPI FlexiPage type |

### Functions Kept

| Function | Reason |
|----------|--------|
| `pull_object_list()` | Global describe for the full object list including standard objects |
| `pull_object_describes()` | Runtime field properties, picklist values, relationship details for standard object fields |
| `pull_usage_data()` | SOQL COUNT for record counts and velocity — runtime data not in MDAPI |
| `pull_permission_sets()` | SOQL-based, not logic-bearing for process discovery |
| `pull_profiles()` | SOQL-based, lightweight |
| `pull_installed_packages()` | Keep via Tooling SOQL — `InstalledSubscriberPackage` has no MDAPI equivalent (platform limitation confirmed by SFDX, Gearset, Salesforce Inspector all using Tooling for this) |
| `_tooling_query_all()` | Still needed for `pull_installed_packages` |
| `_rest_query_all()` | Still needed for permission sets, profiles, usage data |
| `get_sf_client()` | Unchanged |

---

## 2. XML Parsing + JSONB Storage

### New Module: `backend/app/services/salesforce/mdapi_parser.py`

Each parser takes raw XML bytes (from the zip) and returns structured dicts ready for JSONB storage. All parsing is deterministic — no LLM calls.

### Flow Parser

Input: `.flow-meta.xml` files

Extracts:
- `processType`: AutoLaunchedFlow, RecordTriggeredFlow, Screen, Schedule, PlatformEvent, etc.
- `triggerType`: RecordBeforeSave, RecordAfterSave, RecordBeforeDelete (for record-triggered)
- `triggerObject`: the sObject name the flow triggers on (from `<start>` element or `<processMetadataValues>`)
- `status`: Active, Draft, Obsolete
- `description`
- **All elements by type**:
  - `decisions`: name, label, conditions (field, operator, value), default connector
  - `recordLookups`: name, object, filters, stored output fields
  - `recordCreates`: name, object, field assignments
  - `recordUpdates`: name, object, field assignments, filter criteria
  - `recordDeletes`: name, object, filter criteria
  - `assignments`: name, variable assignments
  - `screens`: name, fields/components
  - `subflows`: name, referenced flow name, input/output assignments
  - `loops`: name, collection variable, loop variable
  - `actionCalls`: name, action type (apex, emailAlert, submit, etc.), action name
  - `waits`: name, conditions
- `variables`: name, dataType, isInput, isOutput, objectType
- `formulas`: name, expression, dataType
- `connectors` / `defaultConnector` / `faultConnector`: execution path graph
- Computed: `element_count`, `objects_touched` (union of all object references), `complexity_score` (element count + decision branches + loops)

Output JSONB shape:
```json
{
  "process_type": "RecordTriggeredFlow",
  "trigger_type": "RecordAfterSave",
  "trigger_object": "Account",
  "status": "Active",
  "description": "Updates account ratings based on industry and revenue",
  "elements": {
    "decisions": [
      {
        "name": "Check_Industry",
        "label": "Check Industry",
        "rules": [
          {
            "name": "Healthcare",
            "conditions": [
              {"field": "Account.Industry", "operator": "EqualTo", "value": "Healthcare"}
            ],
            "connector": "Check_Revenue"
          }
        ],
        "default_connector": "End"
      }
    ],
    "record_updates": [
      {
        "name": "Update_Rating",
        "object": "Account",
        "fields": [{"field": "Rating", "value": "Hot"}],
        "connector": "Create_Task"
      }
    ],
    "record_creates": [
      {
        "name": "Create_Task",
        "object": "Task",
        "fields": [
          {"field": "Subject", "value": "Follow up on hot lead"},
          {"field": "OwnerId", "type": "reference", "value": "$Record.OwnerId"}
        ]
      }
    ],
    "record_lookups": [],
    "record_deletes": [],
    "assignments": [],
    "screens": [],
    "subflows": [],
    "loops": [],
    "action_calls": [],
    "waits": []
  },
  "variables": [
    {"name": "varCurrentAccount", "data_type": "SObject", "object_type": "Account", "is_input": true}
  ],
  "formulas": [],
  "element_count": 5,
  "objects_touched": ["Account", "Task"],
  "complexity_score": 8,
  "raw_xml_hash": "sha256:a1b2c3..."
}
```

### Apex Parser

Input: `.cls` files (classes) and `.trigger` files (triggers)

Uses the ANTLR4 Apex grammar from `apex-dev-tools/apex-parser` (`BaseApexParser.g4`, `BaseApexLexer.g4`) compiled with the Python3 target (`antlr4 -Dlanguage=Python3`). This generates a real parser that builds a full AST from Apex source, enabling accurate static analysis rather than regex heuristics.

**New dependency**: `antlr4-python3-runtime` (pip package). The generated parser files are committed to the repo (no ANTLR4 tool needed at runtime).

Extracts via AST traversal:
- `source_body`: full source code (stored in JSONB for re-assessment without re-pulling)
- `methods`: list of `{name, return_type, parameters, annotations, line_range, has_dml, has_soql, has_callout}`
  - AST: `MethodDeclaration` nodes provide name, return type, formal parameters, modifiers
  - AST: `Annotation` nodes preceding method/class declarations give `@InvocableMethod`, `@AuraEnabled`, etc.
- `annotations`: class-level annotations (`@IsTest`, `@RestResource`, etc.)
- `dml_objects`: resolved from AST with full accuracy:
  - DML statement nodes (`insert`, `update`, `delete`, `upsert`, `merge`, `undelete`) identify the variable operand
  - Variable declaration nodes provide type bindings (`List<Account> accts` → `insert accts` resolves to Account)
  - Handles `new Account(...)` expressions, typed collection declarations, and SObject type references
  - The only unresolvable case is runtime polymorphism (method call on an interface variable where the implementing class is unknown at compile time) — this is an inherent limitation of all static analysis, not a parsing gap
- `soql_objects`: extracted from inline SOQL nodes (`[SELECT ... FROM ObjectName ...]`) — the AST parses SOQL as a sub-grammar and the FROM clause is a typed node
- `callout_detected`: boolean, true if `HttpRequest`, `Http.send`, or `@HttpCallout` / `callout=true` annotations found in AST
- `api_version`: from the corresponding `.cls-meta.xml`
- `line_count`: total lines of source

For triggers specifically:
- `trigger_object`: from `TriggerDeclaration` AST node — the object name is a direct child
- `trigger_events`: from the trigger event list node — `before insert`, `after update`, etc. are typed tokens

Output JSONB shape:
```json
{
  "source_body": "public class AccountService { ... }",
  "methods": [
    {
      "name": "updateRatings",
      "return_type": "void",
      "parameters": "List<Account> accounts",
      "annotations": ["InvocableMethod"],
      "has_dml": true,
      "has_soql": true,
      "has_callout": false
    }
  ],
  "class_annotations": ["IsTest"],
  "dml_objects": ["Account", "Task"],
  "soql_objects": ["Account", "Contact"],
  "callout_detected": false,
  "api_version": "62.0",
  "line_count": 245,
  "raw_xml_hash": "sha256:d4e5f6..."
}
```

### CustomObject Parser

Input: `.object-meta.xml` files

Extracts enrichments beyond what REST Describe provides:
- **Validation rules**: `{name, active, description, error_condition_formula, error_message, error_display_field}`
- **Field formulas**: for each `<fields>` element that contains a `<formula>` child: `{api_name, formula, formula_treat_blanks_as}`
- **Record types**: `{developer_name, label, active, description, picklist_values: {field: [values]}}`
- **Field sets**: `{label, description, fields: [api_names]}`
- **List views**: `{developer_name, label, filter_scope, filters: [{field, operation, value}], columns}`
- **Web links / buttons**: `{name, link_type, url_or_page}`
- **Sharing model**: the object's `sharingModel` attribute

These are merged into the existing `MetadataObject.metadata_json` alongside the REST Describe data already stored there (relationships, record types from describe, etc.).

Output JSONB additions to `MetadataObject.metadata_json`:
```json
{
  "validation_rules": [
    {
      "name": "Require_Close_Date_On_Won",
      "active": true,
      "error_condition_formula": "AND(ISPICKVAL(StageName, 'Closed Won'), ISBLANK(CloseDate))",
      "error_message": "Close Date is required when Stage is Closed Won",
      "error_display_field": "CloseDate"
    }
  ],
  "formula_fields": [
    {"api_name": "Expected_Revenue__c", "formula": "Amount * Probability / 100"}
  ],
  "field_sets": [
    {"label": "Quick Create", "fields": ["Name", "Amount", "CloseDate", "StageName"]}
  ],
  "list_views": [
    {
      "developer_name": "My_Open_Opps",
      "label": "My Open Opportunities",
      "filters": [{"field": "StageName", "operation": "notEqual", "value": "Closed Won"}]
    }
  ],
  "sharing_model": "ReadWrite"
}
```

### Workflow Parser

Input: `.workflow-meta.xml` files (one per object)

Extracts:
- **Rules**: `{name, active, description, criteria_items: [{field, operation, value}], formula, trigger_type}`
- **Field updates**: `{name, field, operation, value, formula, target_object}`
- **Email alerts**: `{name, template, recipients}`
- **Outbound messages**: `{name, endpoint_url, fields}`
- **Tasks**: `{name, subject, assignee, due_date_offset}`
- Rule-to-action linkages (which rule triggers which actions)

Output JSONB shape for `MetadataAutomation` rows:
```json
{
  "automation_subtype": "workflow_rule",
  "criteria": {
    "formula": "AND(StageName = 'Closed Won', Amount > 100000)",
    "trigger_type": "onCreateOrTriggeringUpdate"
  },
  "actions": {
    "field_updates": [
      {"name": "Set_Priority", "field": "Priority__c", "value": "High"}
    ],
    "email_alerts": [
      {"name": "Notify_Manager", "template": "Big_Deal_Alert"}
    ],
    "outbound_messages": [],
    "tasks": []
  },
  "related_object": "Opportunity",
  "raw_xml_hash": "sha256:g7h8i9..."
}
```

### Approval Process Parser

Input: `.approvalProcess-meta.xml` files

Extracts:
- `entry_criteria`: formula or criteria items
- `record_editability`: edit behavior during approval
- `steps`: ordered list of `{number, assignee_type, assignee, rejection_action, approval_action, criteria}`
- `final_approval_actions`: field updates, email alerts, outbound messages
- `final_rejection_actions`: same structure
- `initial_submission_actions`: same structure

Output JSONB shape:
```json
{
  "entry_criteria_formula": "Amount > 50000",
  "record_editability": "AdminOnly",
  "steps": [
    {
      "number": 1,
      "assignee_type": "relatedUserField",
      "assignee": "Manager",
      "approval_actions": [{"type": "field_update", "name": "Set_Approved"}],
      "rejection_actions": [{"type": "field_update", "name": "Set_Rejected"}]
    }
  ],
  "final_approval_actions": [
    {"type": "field_update", "name": "Mark_Approved"},
    {"type": "email_alert", "name": "Approval_Notification"}
  ],
  "final_rejection_actions": [
    {"type": "field_update", "name": "Mark_Rejected"}
  ],
  "related_object": "Opportunity",
  "raw_xml_hash": "sha256:j0k1l2..."
}
```

### Storage Strategy

All parsed data is stored in `metadata_json` JSONB on existing model rows:

| Metadata Type | Stored On | How |
|---------------|-----------|-----|
| Flow | `MetadataAutomation` | Full element graph in `metadata_json` |
| Apex Class | `MetadataComponent` (category `apex_class`) | Source + parsed signatures in `metadata_json` |
| Apex Trigger | `MetadataAutomation` (type `trigger`) | Source + parsed signatures in `metadata_json` |
| CustomObject enrichments | `MetadataObject` | VRs, formulas, field sets merged into existing `metadata_json` |
| Validation Rules | `MetadataAutomation` (type `validation_rule`) | Formula + error msg in `metadata_json` |
| Workflow Rules | `MetadataAutomation` (type `workflow_rule`) | Criteria + actions in `metadata_json` |
| Approval Processes | `MetadataAutomation` (type `approval_process`) | Steps + criteria in `metadata_json` |

No new tables for parsed data. Every row includes `raw_xml_hash` (SHA-256 of the source XML) for change detection on re-sync.

### Size Considerations

Apex source bodies can be large. A 2000-line class is ~60KB. For an org with 500 Apex classes, that's ~30MB in JSONB. This is fine for Postgres but the vectorizer must stream through classes rather than loading all JSONB into memory at once. The `_describe_component` function already processes one component at a time, so this is handled naturally.

---

## 3. Metadata Dependency Graph

### New Model: MetadataDependency

Added to `backend/app/models/metadata.py`:

```python
class MetadataDependency(Base):
    __tablename__ = "metadata_dependencies"
    __table_args__ = (
        Index("ix_metadata_deps_source", "connection_id", "source_type", "source_api_name"),
        Index("ix_metadata_deps_target", "connection_id", "target_type", "target_api_name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
```

### Relationship Types

| Source Type | Relationship | Target Type | Extracted From |
|-------------|-------------|-------------|----------------|
| flow | `triggers_on` | object | Flow XML `start` element: `triggerType` + `object` |
| flow | `reads` | object | `recordLookups` elements: `object` attribute |
| flow | `writes` | object | `recordCreates`, `recordUpdates`, `recordDeletes`: `object` attribute |
| flow | `calls_subflow` | flow | `subflows` elements: `flowName` attribute |
| flow | `invokes_apex` | apex_class | `actionCalls` with `actionType=apex`: `actionName` attribute |
| flow | `sends_email` | email_template | `actionCalls` with `actionType=emailAlert` |
| apex_trigger | `triggers_on` | object | Trigger source: `trigger Name on ObjectName` |
| apex_class | `reads` | object | SOQL: `FROM ObjectName` in inline queries |
| apex_class | `writes` | object | DML: `insert/update/delete/upsert` targets |
| apex_class | `calls` | apex_class | Best-effort: class name references in source (limited without full AST) |
| validation_rule | `validates` | object | Parent object from CustomObject XML path |
| workflow_rule | `triggers_on` | object | Parent object from Workflow XML path |
| workflow_rule | `updates_field` | object | Field update action target |
| approval_process | `triggers_on` | object | Parent object from ApprovalProcess XML path |
| object | `lookup` | object | Lookup relationship fields from REST Describe |
| object | `master_detail` | object | Master-detail relationship fields from REST Describe |

### New Module: `backend/app/services/metadata_graph.py`

```python
async def build_dependency_graph(connection_id: UUID, org_id: UUID, db: AsyncSession) -> int:
    """Extract dependency edges from parsed metadata JSONB and store in MetadataDependency."""

async def detect_metadata_communities(org_id: UUID, db: AsyncSession) -> list[UUID]:
    """Run Leiden community detection on the metadata dependency graph."""
```

#### Edge Extraction

`build_dependency_graph` reads all `MetadataAutomation`, `MetadataComponent`, and `MetadataObject` rows for the connection. For each row, it inspects `metadata_json` and extracts edges based on the relationship table above. Edges are inserted as `MetadataDependency` rows after clearing existing edges for the connection.

#### Community Detection

`detect_metadata_communities` builds an `igraph` graph from `MetadataDependency` edges, runs Leiden partitioning (same algorithm and parameters as `backend/app/services/documents/communities.py`), and stores results. Communities represent natural "domain clusters" — e.g., "Account management" (Account object + related flows + triggers + VRs + workflow rules).

Communities are stored in the existing `Community` model. A `source` key in `metadata_json` distinguishes metadata communities (`"source": "metadata_graph"`) from document communities (`"source": "concept_cooccurrence"` or absent for backward compatibility). The existing `member_concept_ids` JSONB array stores metadata node identifiers (formatted as `"{type}:{api_name}"`, e.g., `"flow:Update_Account_Rating"`) instead of concept UUIDs. This reuses the model without a new table while keeping the two community sets queryable separately.

#### Query-Time Usage

The discovery pipeline's `semantic_document_search` in `backend/app/services/processes/context.py` can be extended with a parallel `semantic_metadata_search` that:
1. Embeds the query
2. Finds matching metadata chunks via pgvector
3. Looks up matched components' community memberships
4. Traverses dependency edges from matched components to find related components
5. Returns both directly matched and graph-traversed components

This mirrors the existing community-filtered vector search pattern for documents but with explicit dependency edges enabling targeted traversal.

---

## 4. Vectorizer Updates

### Updated Module: `backend/app/services/metadata_vectorizer.py`

The `_describe_*` functions consume the richer MDAPI-parsed JSONB to produce significantly more informative text for embedding.

### Flow Descriptions (Before vs After)

**Before** (current):
```
Salesforce Automation: Update Account Rating
Type: flow
Status: Active
```

**After** (with MDAPI data):
```
Salesforce Record-Triggered Flow: Update Account Rating
Trigger: Fires after Account is created or updated
Status: Active
Description: Updates account ratings based on industry and revenue

Logic Path:
- Decision: Check_Industry — routes by Account.Industry (Healthcare vs Other)
- Decision: Check_Revenue — evaluates Account.AnnualRevenue > 1,000,000
- Record Update: Sets Account.Rating to "Hot" when both conditions met
- Record Create: Creates follow-up Task assigned to Account.OwnerId

Objects Touched: Account (read/write), Task (create)
Variables: 3 (varCurrentAccount, varIndustryMatch, varRevenueThreshold)
Complexity: 5 elements, 2 decision branches
```

### Apex Class Descriptions — Method-Boundary Chunking

Instead of one chunk per Apex class, produce **one chunk per significant method** (methods with DML, SOQL, annotations, or >10 lines). Small utility methods are grouped into a single "class overview" chunk.

**Class overview chunk:**
```
Salesforce Apex Class: AccountService
API Version: 62.0
Status: Active
Line Count: 245
Annotations: @IsTest
Methods: 8 total (3 with DML, 2 with SOQL, 1 @InvocableMethod)
DML Objects: Account, Task
SOQL Objects: Account, Contact
```

**Per-method chunk:**
```
Salesforce Apex Method: AccountService.updateRatings
Annotations: @InvocableMethod
Parameters: List<Account> accounts
Return Type: void
DML: UPDATE Account
SOQL: SELECT FROM Account WHERE AnnualRevenue > :threshold
Description: Bulk-updates Account ratings based on revenue thresholds
```

### Validation Rule Descriptions

**Before**: name + error message only.

**After**:
```
Salesforce Validation Rule: Require_Close_Date_On_Won
Object: Opportunity
Status: Active
Formula: AND(ISPICKVAL(StageName, 'Closed Won'), ISBLANK(CloseDate))
Error Message: "Close Date is required when Stage is Closed Won"
Error Display Field: CloseDate
```

### Object Descriptions — Enriched

**Additions** (appended to existing object description):
```
Validation Rules (3):
  - Require_Close_Date_On_Won: CloseDate required when Stage = Closed Won
  - Amount_Required_For_Stage3: Amount required at Proposal stage
  - Owner_Cannot_Approve_Own: Owner cannot be Approver

Formula Fields:
  - Expected_Revenue__c: Amount * Probability / 100
  - Days_In_Stage__c: TODAY() - LastStageChangeDate

Field Sets:
  - Quick Create: Name, Amount, CloseDate, StageName
```

### Workflow Rule Descriptions

```
Salesforce Workflow Rule: Big_Deal_Alert
Object: Opportunity
Status: Active
Criteria: StageName = 'Closed Won' AND Amount > 100,000
Trigger: On create or triggering update
Actions:
  - Field Update: Set Priority__c to "High"
  - Email Alert: Notify_Manager (template: Big_Deal_Alert)
```

### Approval Process Descriptions

```
Salesforce Approval Process: Large_Discount_Approval
Object: Opportunity
Entry Criteria: Discount__c > 20
Record Editability: Admin Only

Steps:
  1. Assigned to: Manager (related user field)
     - On Approval: Set Discount_Approved__c = true
     - On Rejection: Set Discount_Approved__c = false

Final Approval Actions:
  - Field Update: Mark_Approved
  - Email Alert: Approval_Notification
Final Rejection Actions:
  - Field Update: Mark_Rejected
```

---

## 5. Pipeline Integration

### Updated Sync Pipeline

The `sync_metadata` function in `metadata.py` and the worker in `metadata_sync.py` become:

1. **REST global describe** — get object list (kept, unchanged)
2. **MDAPI retrieve** — async retrieve of Flow, ApexClass, ApexTrigger, CustomObject, Workflow, ApprovalProcess, FlexiPage (new)
3. **Parse MDAPI zip** — run type-specific parsers on extracted XML files (new)
4. **REST describe** — per-object describe for runtime field properties, relationships (kept, runs in parallel with MDAPI where possible)
5. **SOQL usage data** — record counts, velocity (kept, unchanged)
6. **Store to DB** — objects with MDAPI enrichments merged, automations with full JSONB, components with source (enhanced)
7. **Build dependency graph** — extract edges from parsed JSONB (new)
8. **Detect metadata communities** — Leiden on dependency graph (new)
9. **Licensing/velocity snapshots** — kept, unchanged
10. **Classification** — kept, unchanged
11. **Vectorization** — richer `_describe_*` templates, method-boundary chunking for Apex (enhanced)

### Progress Reporting

New phases added to the progress callback:
- `mdapi_retrieve` (pulling / done)
- `mdapi_parse` (pulling / done)
- `graph_build` (pulling / done)

### Fallback Behavior

If the MDAPI retrieve fails (e.g., insufficient permissions, org doesn't support MDAPI, timeout), the pipeline falls back to the existing Tooling SOQL approach for that sync run. A warning is logged and the connection's `metadata_json` gets a `mdapi_fallback: true` flag so the UI can surface the limitation.

---

## 6. Migration Notes

### Database Migration (Alembic)

- **New table**: `metadata_dependencies` with columns as specified in section 3
- **New indexes**: composite indexes on (connection_id, source_type, source_api_name) and (connection_id, target_type, target_api_name)
- No changes to existing table schemas — all enrichment flows through existing `metadata_json` JSONB columns

### Backward Compatibility

- API response schemas (`MetadataAutomation`, `MetadataComponent`, `MetadataObject` in `backend/app/schemas/metadata.py`) are unchanged. JSONB enrichment is additive — consumers that don't read the new JSONB keys are unaffected.
- Frontend types in `frontend/src/types/index.ts` use `metadata_json: Record<string, unknown>` — no TypeScript changes needed.
- Existing MetadataAutomation/MetadataComponent/MetadataObject rows get richer `metadata_json` on next sync. Old rows with thin JSONB continue to work.

### Rollback

If MDAPI approach causes issues in production:
1. Remove the MDAPI retrieve call from `sync_metadata`
2. Restore Tooling SOQL functions (they remain in git history)
3. Next sync overwrites JSONB with thin data — no migration needed
4. `MetadataDependency` table can remain empty without side effects

---

## 7. Out of Scope

- **Shared platform knowledge base** (vectorized Salesforce developer guide for standard objects) — deferred to a separate spec. For now, LLM native knowledge covers standard field definitions.
- **Pre-embed LLM enrichment** — the discovery pipeline's LLM stages handle business-intent interpretation at query time. No LLM pass during metadata sync.
- **FlexiPage deep parsing** — FlexiPage XML is now retrieved via MDAPI but full region/component parsing is deferred. The current implementation stores the raw metadata; deep parsing of FlexiPage regions and component configurations can be added later.
- **Named Credentials / External Services / Platform Events** — not logic-bearing for process discovery. Can be added later.
- **Report / Dashboard metadata** — potentially valuable for understanding business KPIs but requires Report type in MDAPI. Deferred.

---

## References

- arxiv 2601.08773 — Reliable Graph-RAG for Codebases: AST-Derived Graphs vs LLM-Extracted Knowledge Graphs (Jan 2026)
- Meta FAIR code2seq — Generating Sequences from Structured Representations of Code
- Meta FAIR AST-T5 — Structure-Aware Pretraining for Code Generation and Understanding (2024)
- MIT SPIRAL — Iterative Subgraph Expansion for Knowledge-Graph Based RAG (2025)
- Google DeepMind QUEST-LOFT — Structured output improves multi-document RAG quality
- Practical GraphRAG at Scale (arxiv 2507.03226) — Hybrid retrieval with Reciprocal Rank Fusion
- TrailMeta — 7-tier Salesforce metadata extraction with two-pass Gemini analysis
- Salesforce DescribeFlow — Flow XML to human-readable documentation
- ServiceNow DeepCodeSeek (2025) — Platform metadata + multi-stage retrieval, 87.86% top-40 accuracy
