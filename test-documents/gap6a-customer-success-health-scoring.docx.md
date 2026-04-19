# Customer Health Scoring Model — Customer Success

**Document Owner:** Tom Bradley, VP Customer Success
**Last Updated:** March 2026
**Classification:** Internal — Customer Success

## Purpose

This document describes the customer health scoring model used by the Customer Success (CS) team to identify at-risk accounts, expansion candidates, and churn risks. Health scores drive renewal and upsell conversations — but the handoff to Sales for expansion opportunities is the weakest link.

## Health Score Components

Each customer account is scored monthly on a 0-100 scale based on five weighted dimensions:

| Dimension | Weight | Source | Scoring Logic |
|-----------|--------|--------|---------------|
| Product Usage | 30% | Product analytics (Mixpanel) | DAU/MAU ratio, feature adoption breadth, API call volume |
| Support Health | 20% | Salesforce Cases | Ticket volume trend (declining = good), avg resolution time, open P1/P2 count |
| Engagement | 20% | Salesforce Activities + Email | Exec sponsor responsiveness, QBR attendance, NPS survey completion |
| Contract Value Trend | 15% | Salesforce Opportunity + Subscription | ARR growth rate, expansion history, discount depth |
| Relationship | 15% | CSM manual input | Champion strength, multi-threading score, org change risk |

## Score Calculation

The composite score is stored on the Account record:
- **Account.Health_Score__c** — integer 0-100
- **Account.Health_Tier__c** — derived: "Healthy" (75-100), "Monitor" (50-74), "At Risk" (25-49), "Critical" (0-24)
- **Account.Health_Score_Date__c** — date of last calculation

A scheduled Apex job (`HealthScoreBatch`) runs on the 1st of each month to recalculate scores. Between runs, CSMs can manually override individual dimension scores.

## Renewal Process (CS-Owned)

90 days before `Subscription__c.End_Date__c`:
1. Automated email alert to assigned CSM
2. CSM reviews health score and recent activity
3. CSM creates a Renewal Opportunity in Salesforce:
   - `Opportunity.RecordType = "Renewal"`
   - `Opportunity.Amount` = current ARR
   - `Opportunity.CloseDate` = subscription end date
   - `Opportunity.StageName` = "Renewal Due"
4. CSM conducts renewal conversation with customer
5. For straightforward renewals (no price change, same terms), CSM processes directly
6. For complex renewals (price increase, term change, multi-year), CSM involves Sales

## Expansion / Upsell Identification

When a CSM identifies an upsell or cross-sell opportunity:
- Product usage data shows the customer hitting plan limits
- Customer explicitly asks about additional features or products
- QBR reveals new use cases or teams that could benefit

**Current process for handing to Sales:**
1. CSM creates an Opportunity with `RecordType = "Expansion"`
2. CSM manually changes `Opportunity.Owner` to the Account's assigned AE
3. CSM sends a Slack message to the AE with context
4. **There is no structured briefing document or template**
5. **No SLA for when Sales must follow up**
6. **No feedback loop — CSM doesn't know if Sales pursued the opportunity or let it die**

## The Gap: CS → Sales Handoff for Expansion

| Issue | Impact |
|-------|--------|
| No formal handoff process | AEs sometimes don't notice new Expansion opportunities for 1-2 weeks |
| No context transfer | AE contacts customer without knowing what CS discussed, duplicating conversations |
| No tracking of handoff SLA | 35% of Expansion opportunities sit in "Qualification" for >30 days |
| No attribution | When an AE closes an expansion, there's no record that CS sourced it — creates tension |
| CSM creates opportunity prematurely | Sometimes the customer wasn't ready; AE reaches out and customer is confused |

## Salesforce Objects

- Account (Health_Score__c, Health_Tier__c, Health_Score_Date__c)
- Opportunity (RecordType: Renewal, Expansion)
- Subscription__c (End_Date__c, MRR__c, Plan__c)
- Contact (CSM relationship data)
- Activity (engagement tracking)
