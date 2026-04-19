# Monthly Billing Reconciliation Process — Stripe to Salesforce

**Document Owner:** Finance Operations Team
**Format:** Process worksheet (originally Excel, extracted to text)
**Last Updated:** March 2026

## Purpose

This worksheet documents the steps the Finance team follows each month to reconcile charges in Stripe against records in Salesforce. Discrepancies between the two systems are the root cause of most billing disputes.

## Reconciliation Steps

### Week 1 of Each Month (Days 1-5)

| Step | Action | System | Owner |
|------|--------|--------|-------|
| 1 | Export all invoices from Stripe for prior month | Stripe Dashboard → CSV | Finance Analyst |
| 2 | Export all Opportunity records marked "Closed Won" with CloseDate in prior month | Salesforce Report → CSV | Finance Analyst |
| 3 | Export all active Subscription records | Salesforce Report → CSV | Finance Analyst |
| 4 | Match Stripe invoices to Salesforce Opportunities by customer email + amount | Manual Excel VLOOKUP | Finance Analyst |
| 5 | Flag unmatched records in both directions (Stripe charges with no SF match, SF opps with no Stripe charge) | Manual review | Finance Analyst |
| 6 | Investigate flagged records | Both systems | Senior Finance Analyst |
| 7 | Create adjustment entries for confirmed discrepancies | Stripe + Salesforce | Senior Finance Analyst |

### Common Discrepancy Types

| Type | Frequency | Root Cause |
|------|-----------|------------|
| Stripe charge, no Salesforce record | ~8/month | Sales Rep closed deal verbally, never updated Salesforce |
| Salesforce opp, no Stripe charge | ~3/month | Contract signed but billing not configured in Stripe |
| Amount mismatch | ~12/month | Discount applied in one system but not the other |
| Timing mismatch | ~6/month | Pro-rated charges vs full-month charges |

### Week 2 Follow-Up

- Finance Lead reviews all flagged items with Controller
- Adjustment journal entries posted to accounting system (QuickBooks)
- Disputed amounts communicated to affected customers

## Known Problems

1. **Entirely manual process.** Reconciliation takes 2-3 full days per month.
2. **No real-time sync.** Salesforce and Stripe operate independently. A price change in Salesforce does not propagate to Stripe.
3. **Customer impact.** When amount mismatches go unnoticed, customers receive incorrect invoices. 60% of billing disputes trace back to reconciliation misses.
4. **No audit trail.** Adjustments are tracked in a shared Google Sheet, not in Salesforce. Support agents cannot see adjustment history.

## Systems Referenced

- Stripe (payment processor)
- Salesforce (CRM — Opportunity, Account, Subscription__c, Contract)
- QuickBooks (accounting)
- Google Sheets (reconciliation tracker — shared drive)
