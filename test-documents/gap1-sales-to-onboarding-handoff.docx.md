# Sales-to-Onboarding Handoff Procedure

**Document Owner:** Sarah Chen, VP Revenue Operations
**Last Updated:** March 15, 2026
**Classification:** Internal — Operations

## Purpose

This document describes the current process for transitioning a customer from the Sales team to the Customer Onboarding team once an opportunity reaches the "Closed Won" stage in Salesforce.

## Current Process

### Step 1: Opportunity Closure

When a Sales Representative marks an opportunity as "Closed Won" in Salesforce, the following fields must be completed:

- **Opportunity.CloseDate** — actual close date
- **Opportunity.Amount** — final contract value
- **Opportunity.Contract_Term__c** — contract duration in months
- **Opportunity.Implementation_Tier__c** — Standard, Premium, or Enterprise
- **Opportunity.Primary_Contact__c** — main customer contact for onboarding

### Step 2: Handoff Email

The closing Sales Rep sends an email to `onboarding-queue@acme.com` with the following information:
- Opportunity Name and Salesforce link
- Customer company name and primary contact
- Products purchased (copied from the Opportunity Products related list)
- Any special terms or commitments made during the sales process
- Preferred kickoff date if discussed with the customer

**Note:** There is currently no standardized email template. Each rep formats this differently.

### Step 3: Onboarding Team Pickup

The Onboarding Team Lead (currently Marcus Rivera) manually checks the email inbox twice daily (9 AM and 2 PM) and creates a new Project record in Salesforce:

- **Project__c.Account__c** — linked to the customer Account
- **Project__c.Opportunity__c** — linked to the source Opportunity
- **Project__c.Status__c** — set to "Kickoff Pending"
- **Project__c.Assigned_CSM__c** — assigned based on territory and workload

### Step 4: Kickoff Scheduling

The assigned Customer Success Manager reaches out to the customer within 48 hours to schedule the kickoff call.

## Known Issues

1. **No automated trigger.** The handoff relies entirely on the Sales Rep remembering to send the email. Approximately 15% of Closed Won opportunities are not handed off within the first 48 hours.
2. **Information loss.** Sales context (customer pain points, technical requirements, competitive situation) is not systematically captured. CSMs often have to re-discover this information.
3. **No tracking.** There is no way to see which Closed Won opportunities have not yet been picked up by Onboarding.
4. **Inconsistent formatting.** Without a template, critical details are sometimes missing from the handoff email.

## Metrics

- Average time from Closed Won to first customer contact: 3.2 business days
- Handoff email completion rate: ~85%
- Customer satisfaction with onboarding start: 3.4/5.0
