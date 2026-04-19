# Customer Support to Product Engineering — Defect Escalation Process

**Document Owner:** James Park, Director of Customer Support
**Last Updated:** February 28, 2026
**Classification:** Internal — Engineering & Support

## Overview

When Customer Support identifies a product defect or recurring issue pattern, it must be escalated to the Product Engineering team for investigation and resolution. This document describes how that escalation currently works.

## Defect Identification

Support agents use the following criteria to determine if a case involves a product defect:

1. The issue can be reproduced in a clean environment
2. The issue is not caused by customer configuration, user error, or data quality
3. Two or more customers have reported the same or substantially similar issue within a 30-day window

When these criteria are met, the agent creates a Jira ticket in the `DEFECTS` project with:
- **Summary** — brief description of the defect
- **Severity** — Critical (system down), High (major feature broken), Medium (workaround available), Low (cosmetic/minor)
- **Steps to Reproduce** — detailed reproduction steps
- **Affected Customers** — list of Salesforce Case IDs and Account names
- **Environment** — browser, OS, product version

## Current Escalation Flow

### From Salesforce to Jira

There is currently **no integration between Salesforce Service Cloud and Jira**. The Support agent:

1. Opens a new browser tab and navigates to Jira
2. Manually fills in the ticket fields
3. Copies the Jira ticket URL back into the Salesforce Case record in the `External_Reference__c` field
4. Updates the Case `Status` to "Escalated to Engineering"
5. Adds a Case Comment notifying the customer that the issue has been escalated

### Engineering Triage

The Product Engineering team runs a weekly triage meeting (Tuesdays at 10 AM PT) where new Jira defect tickets are reviewed. During triage:
- Tickets are assigned to an engineering team
- Priority is confirmed or adjusted
- Target sprint is set (or deferred to backlog)

### Communication Back to Support

When Engineering resolves a defect:
1. The engineer updates the Jira ticket status to "Resolved" and adds release notes
2. There is **no automated notification back to the Support team**
3. The Support Lead (currently Priya Sharma) manually checks Jira every Friday for resolved tickets that have Salesforce case references
4. Priya updates the linked Salesforce Cases and notifies affected customers

## Known Gaps

- **Manual dual-entry:** Every defect requires the agent to enter data in both Salesforce and Jira. Average time per escalation: 22 minutes.
- **No feedback loop:** Support has no visibility into engineering's backlog priority or timeline. Customers ask for updates and agents cannot provide them.
- **Resolution notification delay:** Average time from Jira resolution to customer notification: 5-8 business days.
- **Duplicate defects:** Without a shared system, different agents sometimes create duplicate Jira tickets for the same underlying issue. Engineering estimates 12% of defect tickets are duplicates.
- **No severity-based SLA tracking:** There's no way to measure whether Critical defects are being resolved within the 72-hour target.

## Data Objects Involved

| System | Object/Entity | Role |
|--------|---------------|------|
| Salesforce | Case | Customer-reported issue |
| Salesforce | Case.External_Reference__c | Manual link to Jira ticket |
| Salesforce | Account | Affected customer |
| Jira | DEFECTS project ticket | Engineering tracking |
| Jira | Sprint board | Engineering planning |
