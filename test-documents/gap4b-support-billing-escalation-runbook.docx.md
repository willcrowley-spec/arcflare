# Support Agent Runbook: Billing-Related Case Handling

**Document Owner:** Priya Sharma, Support Lead
**Version:** 2.3
**Last Updated:** January 22, 2026

## When a Customer Contacts Support About Billing

Approximately 18% of inbound support cases involve billing questions or disputes. This runbook covers how agents should handle these cases.

## Triage Checklist

When a case comes in tagged with `Case.Category__c = "Billing"`:

1. **Verify the customer's identity** — confirm Account Name, primary contact email, last 4 of payment method on file.
2. **Determine the issue type:**
   - Simple billing question (when is my next invoice, what plan am I on) → Agent can answer directly from Account and Subscription records
   - Payment failure / declined card → Route to Customer Success for payment update
   - Actual dispute (overcharged, duplicate charge, etc.) → Escalate to Finance (see below)

## Escalation to Finance

If the case is a billing dispute that the agent cannot resolve:

1. Update `Case.Status` to "Pending Finance Review"
2. Add a Case Comment with:
   - Summary of the customer's complaint
   - The invoice(s) in question (Stripe Invoice IDs if available)
   - The customer's desired resolution
3. Send an email to `billing@acme.com` with the Case link
4. Set `Case.Follow_Up_Date__c` to 3 business days from today
5. Inform the customer: "I've escalated this to our Finance team. You should hear back within 5 business days."

## Following Up

**This is where the process breaks down.** After escalating:
- There is no notification from Finance back to Support when the dispute is resolved
- The agent must manually check the Case for updates every few days
- If Finance resolves the issue by contacting the customer directly, the Support Case often stays in "Pending Finance Review" indefinitely
- Customers sometimes contact Support again asking for status, and the agent has no information to share

## Workarounds Currently in Use

- Priya checks the "Pending Finance Review" queue every Monday and emails Karen's team for batch status updates
- Some agents add themselves as Case Team Members on billing cases and set personal calendar reminders
- The quarterly Support ↔ Finance sync meeting reviews stale billing cases (but this only catches issues after they've been sitting for weeks)

## Data Points

- Average billing dispute cases per month: 47
- Cases stuck in "Pending Finance Review" > 10 business days: 23%
- Customer re-contacts about billing disputes with no update: 31%
- CSAT for billing-related cases: 2.8/5.0 (lowest category)
