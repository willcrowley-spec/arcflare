# Quarterly Business Review (QBR) Process and Template

**Document Owner:** Dana Sullivan, Senior CSM
**Last Updated:** March 2026
**Classification:** Internal — Customer Success

## Purpose

QBRs are the primary touchpoint where Customer Success assesses account health, reviews value delivered, and identifies expansion or risk signals. This document covers the QBR preparation, execution, and follow-up process.

## QBR Eligibility

- All accounts with ARR > $50K receive quarterly QBRs
- Accounts with ARR $25K-$50K receive semi-annual QBRs
- Accounts below $25K ARR are managed through automated digital touchpoints (email sequences, in-app NPS)

## Preparation (CSM — 1 week before QBR)

### Data Gathering
1. Pull account usage report from Mixpanel dashboard
2. Review all Salesforce Cases created since last QBR — note trends, recurring issues, resolution times
3. Check Account.Health_Score__c and dimension breakdowns
4. Review contract details: renewal date, current plan, committed spend vs. actual
5. Check if any Expansion opportunities are open in Salesforce

### Deck Preparation
Use the standard QBR template (Google Slides in shared drive: `/Customer Success/Templates/QBR Template v4.gslides`):

**Slide 1:** Cover — customer logo, date, attendees
**Slide 2:** Agenda
**Slide 3:** Value Delivered — key metrics showing ROI since last QBR
**Slide 4:** Product Usage Dashboard — screenshots from Mixpanel
**Slide 5:** Support Summary — case volume, resolution times, any outstanding issues
**Slide 6:** Roadmap Preview — upcoming features relevant to this customer (provided by Product monthly)
**Slide 7:** Success Plan Review — progress against goals set in last QBR
**Slide 8:** Open Discussion / Customer Priorities
**Slide 9:** Next Steps and Action Items

## QBR Execution

- Duration: 45-60 minutes
- Attendees: CSM, customer champion, customer exec sponsor (if available), CS Director (for Strategic tier accounts)
- **Sales is NOT typically invited** unless an expansion conversation is already in progress
- Record meeting notes in Salesforce Activity with `Type = "QBR"`

## Post-QBR Follow-Up

### Within 2 Business Days
1. Send recap email to customer with attached deck and action items
2. Log QBR Activity in Salesforce
3. Update Account.Health_Score__c if manual dimension scores changed based on QBR conversation
4. If expansion signal detected:
   - Create Expansion Opportunity in Salesforce (if one doesn't exist)
   - Notify AE via Slack
   - **Capture the customer's exact language and context** (this is the most valuable information for Sales, but there's currently no structured field or template for this)

### The Handoff Problem

QBRs are the #1 source of expansion signals. But:

| Gap | Details |
|-----|---------|
| No structured signal capture | CSM writes freeform notes in Salesforce Activity. No tagged fields for "expansion signal type," "customer budget timing," or "competitive mention." |
| AE not in the room | AE relies on secondhand summary from CSM. Nuance is lost. |
| No joint account planning | CS and Sales do not have a shared document or view that tracks account growth opportunities over time. |
| QBR insights not linked to Opportunities | The Salesforce Activity (QBR notes) is not formally connected to the Expansion Opportunity. When the AE reviews the opp, they don't see the QBR context. |
| Inconsistent follow-through | In 40% of cases where a QBR reveals an expansion signal, no Expansion Opportunity is created within 2 weeks. |

## Systems Involved

- Salesforce (Account, Opportunity, Activity, Case, Subscription__c)
- Mixpanel (product usage analytics)
- Google Slides (QBR deck)
- Slack (notifications to Sales)
- Gong (call recording, if customer consents to recording)
