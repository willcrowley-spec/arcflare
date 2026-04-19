# Sales Expansion Playbook

**Document Owner:** Michael Torres, Sales Director
**Last Updated:** February 2026
**Classification:** Internal — Sales

## Purpose

This playbook covers how Account Executives handle expansion and upsell opportunities for existing customers. It is intended to complement the Customer Success team's identification of expansion signals, though the formal process for receiving those signals is still being defined.

## Expansion Opportunity Types

| Type | Description | Typical Deal Size | Sales Cycle |
|------|-------------|-------------------|-------------|
| Seat Expansion | Customer adds more users to existing plan | $5K-$50K | 2-4 weeks |
| Plan Upgrade | Customer moves to higher-tier plan | $20K-$200K | 4-8 weeks |
| Cross-Sell | Customer adopts a new product module | $30K-$150K | 6-12 weeks |
| Multi-Year | Customer converts annual to multi-year deal | Varies (10-20% discount) | 4-6 weeks |

## How AEs Receive Expansion Opportunities

**Current reality (inconsistent):**

1. **Best case:** CSM creates an Expansion opportunity in Salesforce and Slacks the AE with context. (~40% of expansions)
2. **Common case:** AE discovers expansion signal during their own account review — often duplicating what CS already knows. (~35% of expansions)
3. **Worst case:** Customer reaches out to Sales directly because CS never surfaced the opportunity, or AE was unresponsive when CS did surface it. (~25% of expansions)

**What AEs wish they received from CS (but rarely do):**
- Customer's current health score and trend
- Specific product usage data showing the expansion signal
- Context from recent CSM conversations (what the customer said, what they're trying to achieve)
- Customer's budget cycle timing
- Key stakeholders and their roles in the expansion decision
- Any competitive threats or alternatives the customer is evaluating

## AE Expansion Process

### Stage 1: Qualification
- Review the Expansion opportunity in Salesforce
- **Check:** Is the Account's `Health_Tier__c` "Healthy" or "Monitor"? (Don't sell into "At Risk" — fix the problem first)
- Research the account's recent support history (any P1/P2 cases?)
- Reach out to customer sponsor within 5 business days of receiving the opportunity

### Stage 2: Discovery
- Conduct expansion discovery call (different from new business — customer already knows us)
- Understand the specific use case driving the expansion
- Identify new stakeholders involved in the decision (procurement, IT, etc.)
- Confirm budget and timeline

### Stage 3: Proposal
- Build a proposal using expansion pricing (existing customer discount applies)
- For plan upgrades: calculate pro-rated credit for remaining current term
- For cross-sell: confirm technical compatibility with customer's existing implementation
- Review proposal with Sales Director if discount > 15%

### Stage 4: Negotiation & Close
- Standard negotiation process applies
- Update Opportunity stages in Salesforce
- For multi-year deals: involve Legal for contract amendments

### Stage 5: Post-Close Handback to CS
- Notify CSM that the expansion is closed
- **This handback is also informal** — AE updates Opportunity to "Closed Won" and assumes CS will notice
- If the expansion requires implementation work, AE should create a Project record (but this is often missed)

## Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Expansion ACV as % of new business ACV | 28% | 40% |
| Average time from Expansion opp creation to first customer contact | 8 days | 3 days |
| Win rate on CS-sourced expansions | 52% | 65% |
| Win rate on AE-sourced expansions | 38% | 50% |
| Expansion opportunities with no activity after 14 days | 22% | 5% |
