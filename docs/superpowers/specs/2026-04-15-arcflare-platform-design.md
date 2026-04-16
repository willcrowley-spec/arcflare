# Arcflare Platform — Design Specification

**Date**: 2026-04-15
**Status**: Draft → Pending Review
**Scope**: Full platform architecture, all subsystems, greenfield build

---

## 1. Vision

Arcflare is an enterprise platform that connects to client Salesforce orgs (and eventually other systems), ingests their metadata and operational telemetry, vectorizes their business documents, auto-generates process maps, and produces AI-driven automation recommendations with quantified business value in dollars.

The competitive moat: no other product connects raw platform metadata + document corpus + business entity profiling into a single recommendation engine that outputs actionable, ROI-quantified automation strategies tied to specific workflows and headcount impact.

**Target users**: Consultants, solutions architects, and operations leaders at mid-to-large enterprises running Salesforce.

**Multi-tenant from day one**: Multiple client organizations, each with their own connected systems, documents, processes, and users.

---

## 2. Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React 18 + TypeScript + Vite | Proven SPA stack, fast dev server, strong typing |
| Styling | TailwindCSS | Utility-first, matches demo aesthetic, no CSS-in-JS overhead |
| State | Zustand | Lightweight, no boilerplate, scales well |
| Graphs | React Flow | Drag-and-drop process maps matching the demo's node graph |
| Charts | Recharts | Composable, React-native charting (velocity graphs, efficiency bars, fleet charts) |
| Auth | Clerk | Built-in org-level multi-tenancy, SSO/SAML, MFA, React SDK + JWT verification |
| Backend | Python 3.12 + FastAPI | Async-native, auto OpenAPI docs, native to the AI/ML ecosystem |
| ORM | SQLAlchemy 2.0 + Alembic | Mature, async support, migration management |
| Tasks | Celery + Redis | Battle-tested async task queue for sync jobs, vectorization, analysis |
| Database | PostgreSQL 16 + pgvector | Single store for relational data + vector embeddings, no separate vector DB |
| File Storage | Railway Volume (S3-compatible migration path) | Document uploads, parseable file storage |
| Embeddings | OpenAI text-embedding-3-large (3072 dims) | Best price/performance for document vectorization |
| Reasoning | Anthropic Claude (default), model-agnostic abstraction | Structured analysis, recommendation generation |
| Deployment | Railway | Frontend, backend, worker, PostgreSQL, Redis as separate services |

### Why not Node.js gateway

FastAPI is async, handles OAuth flows, REST/WebSocket endpoints, and concurrent connections natively. The entire AI/ML/vectorization ecosystem is Python. A Node gateway would add a network hop, another Railway service, and another language — for zero real benefit.

---

## 3. Multi-Tenancy Model

```
Clerk Organization (1) ←→ (1) Arcflare Organization
    └── Users (many)
    └── Platform Connections (many) — e.g., 3 Salesforce orgs
    └── Documents (many)
    └── Business Processes (many)
    └── Recommendations (many)
    └── Agents (many)
    └── Business Entities (many)
```

Every database table carries an `org_id` foreign key. A SQLAlchemy session-scoped filter ensures queries never leak data across tenants. Clerk JWT contains the `org_id` claim; the FastAPI middleware extracts it and injects it into every request context.

---

## 4. Navigation & User Journey

Five top-level sections, following a natural left-to-right flow:

| Tab | Purpose | Primary Data |
|-----|---------|-------------|
| **Analysis** | "What's in your systems" | Metadata, record telemetry, documents, platform connection status |
| **Organization** | "Who are you" | Business entity hierarchy, departments, roles, cost modeling |
| **Processes** | "How do you work" | Auto-generated + manual process maps, efficiency scores, bottlenecks |
| **Recommendations** | "What should you change" | AI-generated recommendations, ROI estimates, action plans |
| **Agents** | "Execute the changes" | Deployed agents, fleet analytics, cost/token tracking |

### Analysis Page (matches demo)

- **Header**: Page title + subtitle
- **Filter tabs**: All | Metadata | Data Records | Business Docs
- **Connect button**: Triggers OAuth flow for new platform connections
- **Entity/Document table**: Sortable, paginated. Columns: Entity/Document Name, Type, Platform (badge), Status (CLEAN/ANALYZING/CONFLICT), Last Updated
- **Search bar** with source filter dropdown
- **Platform Sources panel**: Lists all connected platforms with entity count and connection status (CONNECTED/SYNCING/ERROR)

### Organization Page (new — not in demo)

- **Business Profile card**: Company name, industry, employee count, auto-populated from Salesforce org metadata
- **Org Hierarchy visualization**: Tree/org-chart view of departments, managers, and teams derived from Salesforce User records (ManagerId, Department, UserRole)
- **Cost Modeling panel**: Salary band inputs (manual or uploaded CSV), blended hourly rate calculator, headcount growth projections
- **Human Capital Cost Deflection summary**: Aggregate hours saved, dollar value, hires deflected — linked to specific recommendations

### Processes Page (matches demo)

- **KPI cards**: Total Active Workflows, Automation Coverage %, Critical Bottlenecks count
- **Process hierarchy list**: Expandable accordion with process name, sub-process count, managed assets, efficiency bar, automation level, status badge (OPTIMIZED/NEEDS ATTENTION/DRAFT)
- **Sub-process detail**: Shows individual steps with implementation type (Salesforce Flow, Apex Trigger, Manual Process), latency alerts, "Automate Now" CTA
- **Process Map view** (`/processes/map`): Interactive React Flow canvas with draggable nodes. Three node types:
  - **Documents** (orange accent): Business docs that govern/constrain processes
  - **Processes** (gray): Actual workflow steps with implementation type
  - **Data Records** (green): Salesforce objects/records that processes operate on
  - **Edges**: Labeled relationships (governs, constrains, configures, syncs to, converts to, feeds)
  - **Controls**: Zoom +/-, fit-to-screen, legend
  - **Persistence**: Node positions auto-saved per user

### Recommendations Page (matches demo)

- **Featured recommendation**: "Top Agent Strategy" card with headline, description, estimated ROI ($), analysis inputs list, required multi-step actions, "Initialize Deployment" and "Analysis Details" buttons
- **Multi-System Impact panel** (dark theme): Agent Coverage %, Data Consistency Gain, Manual Hours Reclaimed/mo, "Review Full Audit" button
- **Architecture Health bars**: Metadata Sync %, Process Optimization %
- **Recommendation cards grid**: Paginated. Each card shows: agent/bot name + icon, category tag (Automation/Security Patch/Process Change), title, description, platform tags, action CTA (Implement/Remediate/Apply Standards)
- **Filters**: Active | Implemented tabs, filter dropdown

### Agent Management Page (matches demo)

- **Agent detail cards**: For top 2 agents — name, model (GPT-4o, Claude 3.5 Sonnet), monthly cap bar with spend %, capability tags (API, LLM, DB, CSV), "Configure" CTA
- **"Deploy New Agent" button**
- **Fleet Efficiency panel** (dark theme): Bar chart of aggregated cost over time, Avg Accuracy %, Efficiency delta %
- **Agent table**: Paginated. Columns: Agent Name + Model, Status (Running/Idle), Tasks Completed, Accuracy Rate (bar + %), Usage Cost + token count, overflow menu

---

## 5. Subsystem Specifications

### 5.1 Salesforce Connector

**OAuth 2.0 Web Server Flow**:
1. Arcflare registers a Connected App in its own Salesforce developer org with callback URL pointing to `{BACKEND_URL}/api/v1/connections/salesforce/callback`
2. User clicks "Connect" → redirected to `https://login.salesforce.com/services/oauth2/authorize` with our `client_id`, `redirect_uri`, and `scope=api refresh_token`
3. User logs into their Salesforce org → Salesforce redirects back with authorization code
4. Backend exchanges code for access_token + refresh_token via `https://login.salesforce.com/services/oauth2/token`
5. Tokens stored encrypted (Fernet symmetric encryption, key in env var) in `platform_connections` table
6. Access token auto-refreshed on 401 responses using stored refresh_token

No setup required in the customer's Salesforce org. This is the same flow used by Dataloader, Workbench, Salesforce Inspector, and Cursor's Salesforce extension.

**Metadata Ingestion Pipeline** (Celery worker):
1. `GET /services/data/v{version}/sobjects/` → Describe Global: all sObjects
2. For each sObject: `GET /services/data/v{version}/sobjects/{name}/describe/` → fields, relationships, record types, validation rules
3. Tooling API queries:
   - `SELECT Id, MasterLabel, ProcessType, Status FROM Flow`
   - `SELECT Id, Name, Body FROM ApexClass`
   - `SELECT Id, Name, TableEnumOrId FROM ApexTrigger`
4. Results normalized and stored in `metadata_objects` + `metadata_fields`
5. Incremental sync: track `lastModifiedDate` per object, only re-fetch changed items

**Record Telemetry** (Celery periodic task):
- `SELECT COUNT() FROM {ObjectName}` for each object
- Snapshot stored in `record_telemetry` with timestamp
- Configurable polling interval (default: hourly, min: 15 minutes)
- Velocity calculated as: `(count_at_t2 - count_at_t1) / (t2 - t1)`
- On the frontend: sparkline per object in the Analysis table, full time-series chart when drilling into an object
- Dashboard aggregate: total records created/modified per hour across all objects, rendered as area chart

**Record Data Policy**:
- By default: schema and counts only. No actual record data pulled.
- Opt-in per object: pull 10-50 sample records for schema validation and pattern detection
- Full record sync: available as explicit action with data processing agreement acknowledgment
- All record data subject to the same org_id tenant isolation

### 5.2 Document Repository + Vectorization

**Upload Flow**:
1. User uploads file via drag-and-drop or file picker (accepted: PDF, DOCX, XLSX, PPTX, TXT, CSV)
2. File stored to Railway volume at `/{org_id}/documents/{uuid}.{ext}`
3. `documents` record created with status=`UPLOADING`
4. Celery task triggered:
   a. Parse with `unstructured` library (handles all supported formats)
   b. Split into chunks: 512 tokens, 50-token overlap, respecting section boundaries
   c. Generate embeddings via OpenAI `text-embedding-3-large` (3072 dimensions)
   d. Store chunks + embeddings in `document_chunks` table (pgvector)
   e. Update document status to `READY`
5. On failure: status set to `ERROR` with error message, retry up to 3 times

**RAG Pipeline**:
- Query interface: `search_documents(query: str, org_id: uuid, top_k: int = 10) -> List[ChunkResult]`
- Uses pgvector cosine similarity search: `ORDER BY embedding <=> query_embedding LIMIT top_k`
- Results include: chunk text, source document name, page number, relevance score
- Used internally by: Process Mining Engine (extract process descriptions), Recommendation Engine (business rules/SLAs), Entity Profiler (org structure from docs)

**Document Viewer**:
- PDF: rendered via pdf.js in-browser
- DOCX/PPTX: server-side conversion to HTML via `python-docx` / `python-pptx`, rendered in iframe
- Tagging: users assign business domain and process area tags to documents

### 5.3 Process Mining Engine

**Auto-Generation Sources**:

1. **Salesforce Flows**: Parse Flow metadata (from Tooling API) into directed graphs. Each Flow element becomes a node; connectors become edges. Flow types: Screen Flow, Record-Triggered, Autolaunched, Scheduled.
2. **Apex Triggers**: Map trigger → object → event (before insert, after update, etc.). Represent as event handler nodes connected to the object they operate on.
3. **Object Relationships**: Traverse lookup/master-detail relationships from `metadata_fields`. Chain: Lead → Contact → Account → Opportunity → Order represents a business process flow.
4. **Document Extraction**: LLM (Claude) reads uploaded business documents (SOPs, policies, process manuals). Prompt: "Extract all business processes described in this document as a list of sequential steps with actors, systems, and handoff points." Output parsed into process nodes/edges.

**Graph Storage**:
- `business_processes` table: top-level process (e.g., "Lead Management & Qualification")
- `process_nodes` table: individual steps/entities. Fields: `node_type` (metadata|data_record|document), `label`, `platform`, `position_json` (x,y for React Flow), `metadata_json` (implementation type, latency, success rate)
- `process_edges` table: connections between nodes. Fields: `source_node_id`, `target_node_id`, `relationship_label`

**Efficiency Scoring**:
- Automation coverage: % of process nodes that are automated (Flow/Trigger/Agent) vs manual
- Latency detection: flag processes with manual steps averaging >2h (configurable threshold)
- Bottleneck scoring: high record volume + low automation = high bottleneck score

**Process Map UI**:
- React Flow canvas with custom node components for each type (color-coded per demo)
- Drag-to-reposition with auto-save of positions
- Click node → side panel with detail (fields, record count, automation type, latency)
- Zoom, pan, fit-to-screen controls
- Legend: Metadata (dark), Data Records (green), Documents (orange)

**Export**:
- Primary: JSON export of full graph (nodes + edges + metadata) for re-import
- SVG/PNG: Screenshot export of current canvas view
- Lucidchart: Serialize graph to Lucidchart-compatible import format via their REST API. Requires Lucidchart OAuth — offered as optional integration. If unavailable, export as structured CSV (Lucidchart supports CSV import for org charts and flowcharts).

### 5.4 Recommendation Engine

The moat. Cross-references three data layers to produce actionable, dollar-quantified recommendations.

**Input Layers**:
1. **Metadata Layer**: Schema complexity scores, automation gaps (objects with no Flows/Triggers), redundant custom objects, inconsistent naming, field utilization rates
2. **Telemetry Layer**: Record velocity patterns, high-churn objects with no automation, stale objects (0 velocity for 90+ days), volume anomalies
3. **Document Layer**: Business rules, SLAs, compliance requirements, process documentation extracted via RAG

**Analysis Pipeline** (Celery worker):
1. **Data Gathering**: Collect all metadata, telemetry snapshots, and document chunks for the org
2. **Pattern Detection**: Identify automation gaps, manual bottlenecks, schema inconsistencies, compliance risks
3. **LLM Analysis**: Feed patterns + relevant document context to Claude with structured prompt:
   - "Given these metadata patterns and business documents, identify the top automation opportunities. For each, estimate hours saved, affected employees, implementation complexity, and business risk."
4. **Scoring**: Apply decision matrix weights to each recommendation:
   - `automation_potential` (0-100): manual steps identified, automation feasibility
   - `business_impact` (0-100): hours saved, error reduction, compliance risk
   - `technical_feasibility` (0-100): complexity, dependency count, integration points
   - `composite_score` = (automation_potential × 0.35) + (business_impact × 0.40) + (technical_feasibility × 0.25)
5. **ROI Calculation**:
   - `annual_hours_saved` = manual_hours_per_month × 12
   - `cost_deflection` = annual_hours_saved × blended_hourly_rate
   - `hires_deflected` = projected_headcount_need - headcount_with_automation
   - `hire_savings` = hires_deflected × avg_annual_compensation
   - `estimated_roi` = cost_deflection + hire_savings + compliance_risk_avoided
6. **Ranking**: Sort by composite_score, assign priority tier:
   - Critical Path: composite >= 85 AND estimated_roi >= $200k
   - High: composite >= 70
   - Medium: composite >= 50
   - Low: composite < 50

**Output Schema** (per recommendation):
```json
{
  "title": "Deploy Lead Enrichment & Scoring Agent",
  "description": "Analysis of 32 Managed Assets and HubSpot Lead Records reveals a 4.2h bottleneck...",
  "priority": "critical_path",
  "estimated_roi": 428500,
  "category": "lead_management",
  "analysis_inputs": ["salesforce_metadata", "hubspot_records", "word_docs_standards"],
  "actions": [
    {"type": "primary", "label": "Deploy Sylvanas-01 Agent"},
    {"type": "integration", "label": "Align 14 HubSpot/SFDC Fields"},
    {"type": "process_change", "label": "Deprecate Legacy v2 Flows"}
  ],
  "impact": {
    "agent_coverage": 64.2,
    "data_consistency_gain": 18.4,
    "manual_hours_reclaimed_monthly": 1240
  },
  "architecture_health": {
    "metadata_sync": 99.4,
    "process_optimization": 78.0
  }
}
```

**Decision Matrix Weights** are configurable per organization. Defaults optimized for operational efficiency; can be tuned toward compliance, cost reduction, or growth.

### 5.5 Business Entity Profiler

**Auto-Population from Salesforce**:
1. Query `User` object: `SELECT Id, Name, Email, Department, Title, ManagerId, UserRoleId, IsActive, Profile.Name FROM User WHERE IsActive = true`
2. Query `UserRole`: `SELECT Id, Name, ParentRoleId FROM UserRole`
3. Build org hierarchy tree from ManagerId relationships
4. Segment into departments from User.Department field
5. Map Permission Sets + Profiles → team capabilities and system access patterns

**Data Stored in `business_entities`**:
- `entity_type`: organization | department | team | individual
- `parent_id`: self-referencing FK for hierarchy
- `headcount`: count of users in this entity and children
- `cost_data_json`: salary band (manual), blended hourly rate, annual budget
- `metadata_json`: Salesforce-derived attributes (profiles, permission sets, login frequency)

**Human Capital Cost Deflection Model**:

All cost projections tie to specific recommendations and processes — never abstract:

| Metric | Formula | Display |
|--------|---------|---------|
| Hours Saved | (manual_hours - automated_hours) × affected_employees | "1,240 hours/month" |
| Cost Deflection | hours_saved × blended_hourly_rate | "$186,000/year" |
| Future Hires Deflected | projected_growth_headcount - headcount_needed_with_automation | "3.2 FTEs" |
| Total Business Value | cost_deflection + (hires_deflected × avg_annual_comp) + error_cost_avoidance | "$428,500/year" |

**Enrichment**:
- Manual entry or CSV upload for: salary bands per department/role, department budgets, growth projections
- Computed metrics: automation adoption rate per team, process ownership mapping, system access patterns

### 5.6 Agent Management

**Agent CRUD**:
- Create: name, model (GPT-4o, Claude 3.5, Custom Llama, etc.), monthly cost cap, capability tags (API, LLM, DB, CSV)
- Agents are org-scoped, can be linked to specific recommendations

**Token Usage Tracking**:
- Per-agent, per-task token logs: `agent_usage_logs` (agent_id, task_type, input_tokens, output_tokens, cost, timestamp)
- Aggregated into: daily spend, monthly spend, burn rate projection

**Fleet Analytics**:
- Aggregate accuracy: weighted average of per-agent accuracy rates
- Efficiency delta: month-over-month improvement in automation coverage
- Cost per task: total spend / total tasks completed
- Visualization: bar chart of spend over time (matches demo's Fleet Efficiency panel)

**Status Monitoring**:
- Running: agent is actively processing tasks
- Idle: agent is configured but no pending tasks
- Error: last execution failed, needs attention
- Health check: periodic ping to verify agent responsiveness

**Future (not in V1)**: Actual agent orchestration — deploying LangGraph or Agentforce agents directly from recommendation action plans.

---

## 6. Database Schema

### Core Tables

```sql
-- Multi-tenancy root
organizations (
    id UUID PK DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    clerk_org_id VARCHAR(255) UNIQUE NOT NULL,
    plan_tier VARCHAR(50) DEFAULT 'free',
    settings_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)

users (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    clerk_user_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'member',  -- admin, member, viewer
    created_at TIMESTAMPTZ DEFAULT now()
)

platform_connections (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    platform_type VARCHAR(50) NOT NULL,  -- salesforce, hubspot, netsuite, mulesoft
    instance_url VARCHAR(512),
    oauth_tokens_encrypted BYTEA,  -- Fernet-encrypted JSON {access_token, refresh_token, issued_at}
    status VARCHAR(50) DEFAULT 'pending',  -- pending, connected, syncing, error, disconnected
    entity_count INTEGER DEFAULT 0,
    last_sync_at TIMESTAMPTZ,
    sync_config_json JSONB DEFAULT '{}',  -- polling interval, excluded objects, etc.
    created_at TIMESTAMPTZ DEFAULT now()
)
```

### Metadata & Telemetry

```sql
metadata_objects (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    connection_id UUID FK -> platform_connections NOT NULL,
    api_name VARCHAR(255) NOT NULL,
    label VARCHAR(255),
    object_type VARCHAR(50),  -- standard, custom, managed_package
    field_count INTEGER DEFAULT 0,
    record_count BIGINT DEFAULT 0,
    is_custom BOOLEAN DEFAULT false,
    managed_package_namespace VARCHAR(255),
    has_triggers BOOLEAN DEFAULT false,
    has_flows BOOLEAN DEFAULT false,
    has_validation_rules BOOLEAN DEFAULT false,
    metadata_json JSONB DEFAULT '{}',
    last_synced_at TIMESTAMPTZ,
    UNIQUE(connection_id, api_name)
)

metadata_fields (
    id UUID PK,
    object_id UUID FK -> metadata_objects NOT NULL,
    api_name VARCHAR(255) NOT NULL,
    label VARCHAR(255),
    field_type VARCHAR(100),
    is_custom BOOLEAN DEFAULT false,
    is_required BOOLEAN DEFAULT false,
    is_indexed BOOLEAN DEFAULT false,
    is_unique BOOLEAN DEFAULT false,
    relationship_to VARCHAR(255),  -- related object API name
    relationship_type VARCHAR(50),  -- lookup, master_detail, external_lookup
    metadata_json JSONB DEFAULT '{}',
    UNIQUE(object_id, api_name)
)

metadata_automation (
    id UUID PK,
    connection_id UUID FK -> platform_connections NOT NULL,
    org_id UUID FK -> organizations NOT NULL,
    automation_type VARCHAR(50) NOT NULL,  -- flow, apex_class, apex_trigger, process_builder, workflow_rule
    api_name VARCHAR(255) NOT NULL,
    label VARCHAR(255),
    status VARCHAR(50),  -- active, inactive, draft
    related_object VARCHAR(255),
    complexity_score INTEGER,  -- computed: node count, branching depth
    metadata_json JSONB DEFAULT '{}',
    UNIQUE(connection_id, automation_type, api_name)
)

record_telemetry (
    id UUID PK,
    object_id UUID FK -> metadata_objects NOT NULL,
    record_count BIGINT NOT NULL,
    created_count_delta BIGINT DEFAULT 0,
    modified_count_delta BIGINT DEFAULT 0,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX(object_id, snapshot_at)
)
```

### Documents & Vectors

```sql
documents (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    filename VARCHAR(512) NOT NULL,
    mime_type VARCHAR(255),
    file_size_bytes BIGINT,
    storage_path VARCHAR(1024) NOT NULL,
    status VARCHAR(50) DEFAULT 'uploading',  -- uploading, processing, ready, error
    error_message TEXT,
    uploaded_by UUID FK -> users,
    tags JSONB DEFAULT '[]',
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
)

document_chunks (
    id UUID PK,
    document_id UUID FK -> documents NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(3072) NOT NULL,  -- pgvector, text-embedding-3-large dimensions
    page_number INTEGER,
    section_title VARCHAR(512),
    metadata_json JSONB DEFAULT '{}',
    INDEX USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
)
```

### Processes

```sql
business_processes (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(255),  -- revenue_ops, lead_management, post_sale, onboarding, governance
    description TEXT,
    efficiency_score FLOAT,  -- 0.0 to 1.0
    automation_level VARCHAR(50),  -- high, partial, low, none
    status VARCHAR(50) DEFAULT 'draft',  -- draft, active, optimized, needs_attention
    source VARCHAR(50),  -- auto_detected, manual, document_extracted
    sub_process_count INTEGER DEFAULT 0,
    managed_asset_count INTEGER DEFAULT 0,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
)

process_nodes (
    id UUID PK,
    process_id UUID FK -> business_processes NOT NULL,
    node_type VARCHAR(50) NOT NULL,  -- metadata, data_record, document, manual_step
    label VARCHAR(255) NOT NULL,
    subtitle VARCHAR(255),  -- e.g., "Salesforce Flow", "Manual Process", "PDF"
    platform VARCHAR(100),
    position_x FLOAT DEFAULT 0,
    position_y FLOAT DEFAULT 0,
    metadata_json JSONB DEFAULT '{}',  -- success_rate, latency_hours, implementation_type
    created_at TIMESTAMPTZ DEFAULT now()
)

process_edges (
    id UUID PK,
    process_id UUID FK -> business_processes NOT NULL,
    source_node_id UUID FK -> process_nodes NOT NULL,
    target_node_id UUID FK -> process_nodes NOT NULL,
    relationship_label VARCHAR(100),  -- governs, constrains, configures, syncs_to, converts_to, feeds
    metadata_json JSONB DEFAULT '{}',
    UNIQUE(process_id, source_node_id, target_node_id)
)
```

### Recommendations & Agents

```sql
recommendations (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    title VARCHAR(512) NOT NULL,
    description TEXT,
    priority VARCHAR(50),  -- critical_path, high, medium, low
    category VARCHAR(100),
    estimated_roi DECIMAL(12,2),
    composite_score FLOAT,
    status VARCHAR(50) DEFAULT 'active',  -- active, implemented, dismissed
    analysis_inputs_json JSONB DEFAULT '[]',
    actions_json JSONB DEFAULT '[]',
    impact_json JSONB DEFAULT '{}',
    architecture_health_json JSONB DEFAULT '{}',
    linked_process_ids JSONB DEFAULT '[]',
    generated_at TIMESTAMPTZ DEFAULT now(),
    implemented_at TIMESTAMPTZ
)

agents (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    name VARCHAR(255) NOT NULL,
    model VARCHAR(255) NOT NULL,
    model_version VARCHAR(100),
    monthly_cap DECIMAL(10,2),
    total_spend DECIMAL(10,2) DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'idle',  -- running, idle, error, stopped
    accuracy FLOAT DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    capability_tags JSONB DEFAULT '[]',
    config_json JSONB DEFAULT '{}',
    linked_recommendation_id UUID FK -> recommendations,
    created_at TIMESTAMPTZ DEFAULT now()
)

agent_usage_logs (
    id UUID PK,
    agent_id UUID FK -> agents NOT NULL,
    task_type VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost DECIMAL(8,4),
    duration_ms INTEGER,
    success BOOLEAN,
    logged_at TIMESTAMPTZ DEFAULT now(),
    INDEX(agent_id, logged_at)
)
```

### Business Entities

```sql
business_entities (
    id UUID PK,
    org_id UUID FK -> organizations NOT NULL,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- organization, department, team, individual
    parent_id UUID FK -> business_entities,  -- self-referencing for hierarchy
    department VARCHAR(255),
    title VARCHAR(255),
    role VARCHAR(255),
    headcount INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    salesforce_user_id VARCHAR(18),  -- source SF User.Id
    cost_data_json JSONB DEFAULT '{}',  -- salary_band, hourly_rate, annual_budget
    metadata_json JSONB DEFAULT '{}',  -- profiles, perm sets, login frequency
    created_at TIMESTAMPTZ DEFAULT now()
)
```

---

## 7. API Design (Key Endpoints)

All endpoints prefixed with `/api/v1/`. All require Clerk JWT. All scoped to `org_id` from JWT.

### Connections
- `POST /connections/salesforce/initiate` → returns Salesforce OAuth authorization URL
- `GET /connections/salesforce/callback` → handles OAuth callback, stores tokens
- `GET /connections` → list all platform connections for org
- `POST /connections/{id}/sync` → trigger manual metadata sync
- `DELETE /connections/{id}` → disconnect platform

### Analysis / Metadata
- `GET /metadata/objects` → paginated list of ingested objects with filters
- `GET /metadata/objects/{id}` → object detail (fields, relationships, telemetry)
- `GET /metadata/objects/{id}/telemetry` → time-series record counts for graphing
- `GET /metadata/objects/{id}/fields` → field list for an object
- `GET /metadata/automation` → all automation items (Flows, Triggers, etc.)
- `GET /analysis/velocity` → aggregate data velocity dashboard metrics

### Documents
- `POST /documents/upload` → multipart file upload
- `GET /documents` → paginated list with status filters
- `GET /documents/{id}` → document detail + viewer URL
- `PATCH /documents/{id}/tags` → update tags
- `POST /documents/search` → RAG vector search across org documents
- `DELETE /documents/{id}` → soft delete

### Processes
- `GET /processes` → paginated process list with KPI aggregates
- `GET /processes/{id}` → process detail with nodes and edges
- `POST /processes` → create manual process
- `PATCH /processes/{id}` → update process metadata
- `PUT /processes/{id}/nodes` → batch update node positions (auto-save)
- `POST /processes/generate` → trigger auto-generation from metadata + documents
- `POST /processes/{id}/export` → export as JSON, SVG, or Lucidchart format

### Recommendations
- `GET /recommendations` → paginated list with filters (priority, status, category)
- `GET /recommendations/{id}` → full recommendation detail
- `POST /recommendations/generate` → trigger recommendation analysis pipeline
- `PATCH /recommendations/{id}/status` → mark as implemented/dismissed
- `GET /recommendations/summary` → dashboard-level KPIs (total ROI, coverage, hours)

### Organization / Entities
- `GET /organization/profile` → business profile summary
- `GET /organization/hierarchy` → org chart tree
- `GET /organization/entities` → paginated entity list
- `POST /organization/entities` → manual entity creation
- `PATCH /organization/entities/{id}` → update entity (cost data, etc.)
- `POST /organization/import-csv` → bulk import salary/cost data
- `GET /organization/cost-model` → human capital cost deflection summary
- `POST /organization/sync-from-salesforce` → pull User/Role data from connected SF org

### Agents
- `GET /agents` → paginated agent list with fleet KPIs
- `POST /agents` → create agent
- `GET /agents/{id}` → agent detail + usage history
- `PATCH /agents/{id}` → update config/cap
- `GET /agents/{id}/usage` → token/cost time-series
- `GET /agents/fleet-analytics` → aggregate fleet metrics
- `DELETE /agents/{id}` → deactivate agent

---

## 8. Monorepo Structure

```
arcflare-demo/
├── frontend/                    # React + Vite + TypeScript
│   ├── public/
│   ├── src/
│   │   ├── components/          # Shared UI: Sidebar, Header, Table, Cards, StatusBadge
│   │   ├── pages/
│   │   │   ├── Analysis/        # Analysis page + sub-components
│   │   │   ├── Organization/    # Entity profiling page
│   │   │   ├── Processes/       # Process list + Process Map (React Flow)
│   │   │   ├── Recommendations/ # Recommendation list + detail
│   │   │   └── Agents/          # Agent management + fleet analytics
│   │   ├── hooks/               # useApi, useOrg, useConnection, etc.
│   │   ├── stores/              # Zustand stores per domain
│   │   ├── api/                 # Typed API client (generated from OpenAPI)
│   │   ├── types/               # Shared TypeScript interfaces
│   │   └── lib/                 # Utilities, constants, formatters
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/                     # Python FastAPI
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── api/
│   │   │   ├── deps.py          # Dependency injection (current_user, current_org, db_session)
│   │   │   └── routes/
│   │   │       ├── connections.py
│   │   │       ├── metadata.py
│   │   │       ├── documents.py
│   │   │       ├── processes.py
│   │   │       ├── recommendations.py
│   │   │       ├── organization.py
│   │   │       └── agents.py
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic Settings (env vars)
│   │   │   ├── security.py      # Clerk JWT verification, Fernet encryption
│   │   │   └── database.py      # Async SQLAlchemy engine + session
│   │   ├── models/              # SQLAlchemy ORM models (1 file per table group)
│   │   │   ├── organization.py
│   │   │   ├── connection.py
│   │   │   ├── metadata.py
│   │   │   ├── document.py
│   │   │   ├── process.py
│   │   │   ├── recommendation.py
│   │   │   ├── agent.py
│   │   │   └── entity.py
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # Business logic, one module per domain
│   │   │   ├── salesforce/
│   │   │   │   ├── oauth.py
│   │   │   │   ├── metadata.py
│   │   │   │   └── telemetry.py
│   │   │   ├── documents/
│   │   │   │   ├── upload.py
│   │   │   │   ├── parser.py
│   │   │   │   └── vectorizer.py
│   │   │   ├── processes/
│   │   │   │   ├── miner.py
│   │   │   │   ├── graph.py
│   │   │   │   └── export.py
│   │   │   ├── recommendations/
│   │   │   │   ├── analyzer.py
│   │   │   │   ├── scorer.py
│   │   │   │   └── roi.py
│   │   │   ├── entities/
│   │   │   │   ├── profiler.py
│   │   │   │   └── cost_model.py
│   │   │   └── ai/
│   │   │       ├── base.py      # Abstract LLM interface
│   │   │       ├── openai.py    # OpenAI embeddings
│   │   │       ├── anthropic.py # Claude reasoning
│   │   │       └── router.py    # Model selection logic
│   │   └── workers/             # Celery task definitions
│   │       ├── celery_app.py
│   │       ├── metadata_sync.py
│   │       ├── telemetry_poll.py
│   │       ├── vectorization.py
│   │       └── analysis.py
│   ├── alembic/                 # Database migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yml           # Local dev: PG + pgvector, Redis, backend, frontend
├── railway.toml                 # Railway deployment config
├── .env.example                 # Required environment variables
└── README.md
```

---

## 9. Railway Deployment

Five Railway services in a single project:

| Service | Source | Build | Port |
|---------|--------|-------|------|
| `arcflare-frontend` | `/frontend` | `npm run build` → static files served by `serve` | 3000 |
| `arcflare-backend` | `/backend` | Docker (Python 3.12, uvicorn) | 8000 |
| `arcflare-worker` | `/backend` | Docker (same image, entrypoint: `celery -A app.workers.celery_app worker`) | — |
| `arcflare-postgres` | Railway managed | PostgreSQL 16 + pgvector extension | 5432 |
| `arcflare-redis` | Railway managed | Redis 7 | 6379 |

**Volume**: Attached to `arcflare-backend` at `/data/documents` for file storage.

**Environment Variables** (shared via Railway project-level vars):
- `DATABASE_URL`, `REDIS_URL` (auto-populated by Railway)
- `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET`, `SALESFORCE_REDIRECT_URI`
- `ENCRYPTION_KEY` (Fernet key for OAuth token encryption)
- `FRONTEND_URL` (for CORS and OAuth callbacks)

---

## 10. Security Considerations

- **Token Encryption**: All OAuth tokens encrypted at rest with Fernet (AES-128-CBC). Encryption key stored as environment variable, never in code or database.
- **Tenant Isolation**: Every query scoped by `org_id`. No cross-tenant data access possible through the API.
- **CORS**: Strict origin whitelist (frontend URL only).
- **Rate Limiting**: Per-org API rate limits via Redis-backed sliding window.
- **Audit Logging**: All connection, sync, and recommendation generation events logged with user + timestamp.
- **Data Residency**: Customer record data (when opted in) stored with org_id and encrypted. Deletion on disconnect.

---

## 11. What's Explicitly NOT in V1

- Non-Salesforce connectors (HubSpot, NetSuite, MuleSoft) — UI shows them, backend stubs them, but only Salesforce is functional
- Actual agent execution/orchestration — Agent Management is tracking/config only, not runtime orchestration
- Real-time WebSocket updates — polling-based initially, WebSocket upgrade planned
- Custom LLM model hosting — we use API-based models only
- White-labeling or custom domains per tenant
- Billing / payment processing
