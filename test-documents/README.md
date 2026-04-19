# Test Documents for Document Ingestion Pipeline

Realistic customer-provided documents designed to close 6 cross-domain gaps that the discovery pipeline would typically identify for a Salesforce-centric B2B SaaS company.

## Gap 1: Sales Ops → Customer Onboarding (1 document)
No automated handoff after Closed Won. Sales rep manually emails the onboarding team.

| File | Simulates |
|------|-----------|
| `gap1-sales-to-onboarding-handoff.docx.md` | SOP documenting the manual email-based handoff, known issues, and metrics |

## Gap 2: Customer Support → Product Engineering (1 document)
No integration between Salesforce Service Cloud and Jira for defect escalation.

| File | Simulates |
|------|-----------|
| `gap2-support-to-product-defect-escalation.docx.md` | Escalation process doc covering dual-entry, triage cadence, and communication gaps |

## Gap 3: Marketing → Sales Ops (1 document)
MQL routing is automated but SDR-to-AE opportunity handoff is undefined.

| File | Simulates |
|------|-----------|
| `gap3-marketing-to-sales-lead-routing.docx.md` | Full lead scoring model, routing logic, and the undocumented SDR→AE handoff |

## Gap 4: Finance/Billing → Customer Support (3 documents)
Billing disputes bounce between Support and Finance with no feedback loop.

| File | Simulates |
|------|-----------|
| `gap4a-billing-dispute-resolution-policy.docx.md` | Finance team's dispute resolution policy |
| `gap4b-support-billing-escalation-runbook.docx.md` | Support agent runbook for billing cases — documents the broken feedback loop |
| `gap4c-stripe-salesforce-reconciliation.xlsx.md` | Monthly reconciliation process between Stripe and Salesforce — root cause of disputes |

## Gap 5: HR/People Ops → IT Operations (3 documents)
Employee lifecycle events (hire, role change, termination) have no system integration between HR and IT.

| File | Simulates |
|------|-----------|
| `gap5a-new-hire-onboarding-checklist.docx.md` | HR's onboarding checklist showing the IT provisioning gap |
| `gap5b-it-provisioning-request-process.docx.md` | IT's internal provisioning process and known pain points |
| `gap5c-employee-offboarding-security-protocol.docx.md` | InfoSec's offboarding protocol highlighting the HR→IT notification gap |

## Gap 6: Customer Success → Sales Ops (3 documents)
Expansion/upsell opportunities identified by CS are handed to Sales informally with no structure.

| File | Simulates |
|------|-----------|
| `gap6a-customer-success-health-scoring.docx.md` | Health scoring model and the CS→Sales expansion handoff gap |
| `gap6b-sales-expansion-playbook.docx.md` | Sales playbook for expansions — documents what AEs wish they received from CS |
| `gap6c-qbr-template-and-process.docx.md` | QBR process showing how expansion signals are captured (poorly) and handed off |

## Usage

Upload these via the Smart Document Library (`/documents`) to test:
1. File upload and SHA-256 deduplication
2. Chunking and vectorization
3. NLP concept extraction and co-occurrence graphs
4. Leiden community detection
5. Community-aware RAG retrieval during chat
6. Document deletion and re-upload flows
