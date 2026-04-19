# Marketing to Sales — Lead Routing Standard Operating Procedure

**Document Owner:** Lisa Tran, Marketing Operations Manager
**Effective Date:** January 10, 2026
**Classification:** Internal — Marketing & Sales

## Purpose

This SOP defines how Marketing Qualified Leads (MQLs) are routed from the Marketing team to Sales Representatives for follow-up and conversion.

## Lead Scoring Model

Leads are scored in Salesforce using a combination of demographic and behavioral signals:

### Demographic Scoring (max 50 points)
| Criteria | Points |
|----------|--------|
| Job title contains VP, Director, C-level | +20 |
| Company size 100-500 employees | +10 |
| Company size 500+ employees | +15 |
| Industry matches ICP (SaaS, FinTech, Healthcare) | +10 |
| Located in Tier 1 market (US, UK, DACH, ANZ) | +5 |

### Behavioral Scoring (max 50 points)
| Criteria | Points |
|----------|--------|
| Downloaded gated content (whitepaper, ebook) | +10 |
| Attended webinar or virtual event | +15 |
| Visited pricing page | +20 |
| Requested demo via website form | +25 |
| Opened 3+ marketing emails in 30 days | +5 |

**MQL Threshold:** Lead Score >= 60

## Routing Logic

When a Lead's score reaches or exceeds 60, a Salesforce Flow (`Lead_MQL_Router`) fires and performs the following:

1. **Sets Lead.Status** to "Marketing Qualified"
2. **Stamps Lead.MQL_Date__c** with the current datetime
3. **Assigns Lead Owner** based on territory:
   - US West → Round-robin among West Coast SDR team
   - US East → Round-robin among East Coast SDR team
   - EMEA → Round-robin among EMEA SDR team
   - APAC → All leads go to single APAC rep (Kenji Tanaka)
   - Unmatched → Falls into "Unassigned MQL" queue

4. **Creates a Task** for the assigned SDR:
   - Subject: "Follow up on MQL: {Lead.Company}"
   - Due Date: Today + 1 business day
   - Priority: High

5. **Sends Slack notification** via Zapier webhook to `#mql-alerts` channel

## Handoff to Sales (The Gap)

Once the SDR qualifies the lead and creates an Opportunity, the process for handing the Opportunity to an Account Executive is **not formally defined**. Currently:

- SDRs verbally tell the AE during the weekly pipeline meeting
- Some SDRs use Slack DMs to notify the AE
- The Opportunity.Owner is manually changed to the AE by the SDR
- There is no checklist for what information must be present on the Opportunity before handoff
- No SLA exists for how quickly the AE must accept and begin working the opportunity

## Metrics

| Metric | Current Value | Target |
|--------|---------------|--------|
| MQL to SDR first touch | 18 hours avg | 4 hours |
| SDR qualification rate | 32% | 40% |
| MQL-to-Opportunity conversion | 14% | 20% |
| Leads stuck in "Unassigned MQL" queue > 48h | ~8% | 0% |

## Appendix: Salesforce Objects

- **Lead** — primary record, scored and routed
- **Lead.Lead_Score__c** — composite score field
- **Lead.MQL_Date__c** — timestamp of qualification
- **Lead.Territory__c** — assigned territory
- **Task** — follow-up task for SDR
- **Opportunity** — created upon qualification (manual)
