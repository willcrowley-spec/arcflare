# Employee Offboarding Security Protocol

**Document Owner:** Rachel Kim, Information Security Manager
**Last Updated:** February 2026
**Classification:** Internal — Confidential

## Purpose

This protocol defines the security requirements for revoking access when an employee leaves the company, whether voluntarily or involuntarily. The primary goal is to prevent unauthorized access to company systems and customer data after separation.

## Offboarding Types and Response Times

| Type | Max Time to Revoke All Access | Notification Source |
|------|-------------------------------|---------------------|
| Voluntary resignation | End of last business day | HR email to IT, 2 weeks notice typical |
| Involuntary termination | Within 1 hour of notification | HR phone call to IT Security + email |
| Contractor end-of-engagement | End of contract date | Procurement or hiring manager email |
| Leave of absence (>30 days) | End of first day of leave | HR email |

## Access Revocation Checklist

### Immediate (within SLA above)
1. **Okta:** Disable user session and deactivate account
   - This automatically revokes SSO access to: Salesforce, Jira, Slack, Google Workspace (if federated), and all SAML/OIDC apps
   - **Critical:** Some applications have local passwords that bypass Okta. These must be individually addressed.
2. **Google Workspace:** Suspend account (if not federated through Okta), initiate email forwarding to manager for 30 days, transfer Drive ownership
3. **Salesforce:** Deactivate user, freeze account (belt and suspenders), reassign open Opportunities/Cases/Leads to manager
4. **GitHub:** Remove from organization
5. **AWS Console / CLI:** Deactivate IAM user, rotate any shared credentials the employee had access to
6. **VPN:** Revoke certificate
7. **Physical:** Deactivate badge, collect laptop (coordinate with Facilities)

### Within 24 Hours
8. **Slack:** Deactivate account (messages preserved per retention policy)
9. **Jira:** Deactivate account (assigned tickets reassigned by project lead)
10. **Third-party SaaS:** Review Okta app assignments and confirm any non-SSO apps are manually deactivated (Figma, Miro, Notion, etc.)

### Within 7 Days
11. **Data review:** Manager reviews departed employee's recent file activity (Google Drive audit log) for unusual downloads or sharing
12. **Shared credentials rotation:** Rotate any team passwords or API keys the employee had access to
13. **Distribution lists:** Remove from all email groups and Slack channels

## Current Process Failures

### The HR → IT Notification Gap

The biggest security risk is **timing**. Current state:
- HR processes the termination in BambooHR
- HR sends an email to `it-offboarding@acme.com`
- **There is no automated trigger.** If HR forgets the email, IT never knows.
- For involuntary terminations, the phone call protocol works when remembered, but there have been 3 incidents in the past year where access was not revoked for 24+ hours after an involuntary termination.

### No Centralized View

- IT cannot query "show me all employees who left in the last 30 days and their access revocation status"
- Compliance audits require manually correlating BambooHR termination dates with Okta disable dates, which takes ~4 hours per audit

### Contractor Blind Spot

- Contractors are not always in BambooHR (some are tracked in Google Sheets by Procurement)
- When a contractor's engagement ends, the responsible manager must remember to notify IT
- Of the 12 contractor offboardings last quarter, 4 had access revoked late (one was 3 weeks after engagement ended)

## Compliance Requirements

- SOC 2 Type II: Access must be revoked within 24 hours of separation (we are not consistently meeting this)
- Customer contracts (Enterprise tier): Some contracts require notification if a departing employee had access to their data
- GDPR: Departing employee's personal data in internal systems must be reviewed and purged per retention policy
