# Billing Dispute Resolution Policy

**Document Owner:** Karen Wu, Controller
**Last Updated:** December 5, 2025
**Classification:** Internal — Finance

## Policy Statement

All billing disputes raised by customers must be investigated and resolved within 10 business days of receipt. This policy applies to all subscription, usage-based, and one-time charges processed through our billing system (Stripe) and recorded in Salesforce.

## Dispute Categories

| Category | Description | Example |
|----------|-------------|---------|
| Overcharge | Customer billed more than contracted amount | Annual plan billed at monthly rate |
| Duplicate Charge | Same invoice issued twice | Credit card charged twice for same period |
| Service Not Rendered | Billed for features or period not delivered | Charged for month after cancellation |
| Contract Mismatch | Invoice doesn't match signed contract terms | Wrong discount percentage applied |
| Tax Dispute | Customer disagrees with tax calculation | Tax-exempt org charged sales tax |

## Investigation Process

### Step 1: Dispute Intake

When Finance receives a billing dispute (via email to `billing@acme.com` or flagged by Support):

1. Create a Case in Salesforce with `RecordType = "Billing Dispute"`
2. Set `Case.Priority` based on dispute amount:
   - Over $10,000 → Critical
   - $1,000-$10,000 → High
   - Under $1,000 → Medium
3. Link the Case to the customer's Account
4. Attach the relevant Stripe Invoice ID in `Case.Invoice_Reference__c`

### Step 2: Cross-Reference

The Finance Analyst must verify:
- The customer's contract terms in Salesforce (`Contract` object or `Opportunity.Contract_Term__c`)
- The actual charges in Stripe's dashboard
- The billing configuration in our subscription management system
- Any credit memos or adjustments previously issued (`Credit_Memo__c` records)

### Step 3: Resolution

Based on findings:
- **Valid dispute:** Issue a credit memo via Stripe, create `Credit_Memo__c` record in Salesforce, notify customer
- **Invalid dispute:** Prepare explanation with supporting documentation, send to customer
- **Partial:** Issue partial credit, explain remaining balance

### Step 4: Customer Communication

Finance sends resolution to customer. **There is currently no standard process for looping Support back in** — if the customer originally raised the issue through a Support case, the Support agent may not learn the outcome.

## Escalation

Disputes over $25,000 or disputes involving contract interpretation must be escalated to the VP of Finance and Legal.

## Salesforce Objects

- Case (RecordType: Billing Dispute)
- Account
- Contract
- Opportunity
- Credit_Memo__c
- Invoice_Reference__c (custom field on Case)
