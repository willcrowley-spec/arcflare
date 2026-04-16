# Arcflare

**Enterprise platform for Salesforce metadata intelligence, business process mining, and AI-driven automation recommendations.**

Arcflare connects to client Salesforce orgs via OAuth, ingests metadata and operational telemetry, vectorizes business documents, auto-discovers business processes through entity extraction and knowledge graph analysis, and produces AI-driven automation recommendations with quantified ROI.

**[Live Demo](https://willcrowley-spec.github.io/arcflare/)**

## What It Does

| Tab | Capability |
|-----|-----------|
| **Analysis** | Connect Salesforce orgs via OAuth. Inspect metadata objects, field counts, record velocity, automation coverage. Filter by object type, managed package status. |
| **Organization** | Map business entity hierarchy, departments, roles. Model human capital cost deflection — hours saved, cost avoidance, future hires deflected. |
| **Processes** | Auto-generate business process maps from Salesforce metadata (Flows, triggers, object relationships) and extracted document content. Interactive visualization with export to Lucidchart. |
| **Recommendations** | Cross-reference metadata patterns, record telemetry, and vectorized document content to produce ranked automation candidates with estimated ROI, implementation complexity, and business impact. |
| **Agents** | Track deployed AI agents with cost caps, token usage, accuracy metrics, and fleet-level analytics. |

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────────┐
│  React Frontend │────▶│              FastAPI Backend                  │
│  (Vite + TS)    │     │                                              │
│                 │     │  ┌─────────────┐  ┌──────────────────────┐   │
│  • Analysis     │     │  │  Salesforce  │  │  Document Processor  │   │
│  • Organization │     │  │  Connector   │  │  (parse + vectorize) │   │
│  • Processes    │     │  └──────┬──────┘  └──────────┬───────────┘   │
│  • Recommends   │     │         │                    │               │
│  • Agents       │     │  ┌──────┴──────┐  ┌──────────┴───────────┐   │
│                 │     │  │   Process    │  │   Recommendation     │   │
│  Clerk Auth     │     │  │   Miner     │  │   Engine             │   │
│  React Flow     │     │  └─────────────┘  └──────────────────────┘   │
│  Recharts       │     │                                              │
└─────────────────┘     └──────────────┬───────────────────────────────┘
                                       │
                        ┌──────────────┼───────────────┐
                        ▼              ▼               ▼
                 ┌────────────┐ ┌───────────┐  ┌─────────────┐
                 │ PostgreSQL │ │   Redis   │  │   Object    │
                 │ + pgvector │ │  (Celery) │  │   Storage   │
                 └────────────┘ └───────────┘  └─────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| State | Zustand, TanStack Query |
| Visualizations | React Flow (process maps), Recharts (charts) |
| Auth | Clerk (multi-tenant orgs, SSO/SAML, MFA) |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| AI/ML | OpenAI embeddings, Anthropic Claude, Google Gemini, LangChain |
| NLP | spaCy NER, sentence-transformers, tiktoken |
| Salesforce | simple-salesforce, OAuth 2.0, Metadata + Tooling APIs |

## Key Capabilities

### Salesforce Connector
OAuth 2.0 Web Server Flow — connect any Salesforce org without requiring setup in the target environment. Pulls 13+ metadata types: objects, fields, flows, apex classes/triggers, validation rules, workflow rules, approval processes, page layouts, flexipages, reports, dashboards, profiles, permission sets. Platform-agnostic connector architecture supports future CRM integrations.

### Document Intelligence
Upload business documents (PDF, DOCX, XLSX, PPTX). Automatically parsed via `unstructured`, chunked with adaptive token-based splitting, entity-extracted via spaCy NER with LLM fallback, and vectorized with OpenAI embeddings. Stored in pgvector for RAG-powered semantic search.

### Process Mining
Entity matching via fuzzy string matching (rapidfuzz) + cosine similarity + LLM-assisted disambiguation. HDBSCAN clustering groups related entities into business process candidates. Auto-generates process maps with full source lineage tracking. Interactive React Flow visualization with drag-and-drop editing and Lucidchart export.

### Recommendation Engine
LLM-powered analysis cross-references metadata patterns, record telemetry, and vectorized documents to produce ranked automation recommendations. Each recommendation includes estimated ROI, implementation complexity, business impact metrics, and human capital cost deflection modeling.

### Business Entity Profiler
Builds organizational hierarchy from Salesforce User/Role data. Models human capital cost deflection — hours saved, cost avoidance, and future hires deflected per recommendation.

### Agent Management
Track deployed AI agents with cost caps, token usage, accuracy metrics, and fleet-level analytics.

## Multi-Tenancy

Every API request is scoped to the authenticated user's Clerk organization. All database queries filter by `org_id`. No cross-tenant data access is possible through the API layer.

## License

Proprietary. All rights reserved.
