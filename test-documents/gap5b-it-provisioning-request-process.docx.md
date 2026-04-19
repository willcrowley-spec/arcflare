# IT Provisioning Request Process

**Document Owner:** Derek Nguyen, IT Operations Manager
**Version:** 1.4
**Last Updated:** January 2026
**Classification:** Internal — IT Operations

## Scope

This document describes how IT handles provisioning and deprovisioning of user accounts, application access, and hardware for employee lifecycle events (hire, role change, termination).

## Provisioning Request Intake

IT accepts provisioning requests from three sources:

### 1. New Hire Provisioning
- **Source:** Email from HR (`hr-notifications@acme.com`) containing new hire details
- **Trigger:** Offer acceptance
- **Lead time required:** 5 business days before start date
- **Information provided by HR:**
  - Employee name
  - Personal email (for pre-start communications)
  - Start date
  - Department
  - Job title
  - Reporting manager
  - Office location or "Remote"

**What's NOT provided (and causes delays):**
- Salesforce Profile/Permission Set requirements (IT has to ask the hiring manager)
- Which Jira projects the user needs access to (IT guesses based on department)
- Whether the employee needs VPN access (assumed yes for remote, but sometimes needed for on-site too)
- Software license needs beyond standard suite (e.g., Figma, Tableau, IntelliJ)

### 2. Role Change / Transfer
- **Source:** Email from HR or the employee's manager
- **Major gap:** No standard form or request mechanism. IT receives inconsistent information — sometimes just "Please give John access to the Marketing team's stuff"
- **Risk:** Former role access is rarely removed when new access is added (privilege accumulation)

### 3. Termination / Offboarding
- **Source:** Email from HR on the employee's last day (or sometimes after)
- **Critical problem:** In 30% of terminations, IT is notified AFTER the employee's last day. For involuntary terminations, IT is sometimes not notified until 2-3 days later.
- **Process:** Disable Okta account (cascades to all SSO apps), reclaim laptop, archive email, transfer Drive files to manager

## IT Service Desk Workflow (Jira)

All provisioning work is tracked on the IT Service Desk Jira board (`ITSD` project):

1. IT Service Desk Lead creates a Jira ticket from the HR email
2. Ticket is assigned to a technician based on request type
3. Technician provisions accounts in each system individually:
   - Google Workspace Admin Console → create account
   - Okta Admin → create user, assign apps based on department template
   - Salesforce Setup → create user, assign Profile, add to Permission Set Groups
   - Jira Admin → create user, add to projects
   - Slack Admin → invite user
4. Technician updates Jira ticket with completion notes
5. Technician sends "Welcome to IT" email to new hire with credentials and setup instructions

## Metrics

| Metric | Current | Target |
|--------|---------|--------|
| New hire fully provisioned by Day 1 | 75% | 99% |
| Average provisioning time (hire) | 3.2 business days | 1 business day |
| Termination access revoked same day | 70% | 100% |
| Role change access audit completed | 40% | 100% |
| Provisioning errors per month | 8 | 0 |

## Known Issues

1. **No system-to-system integration.** BambooHR, Okta, Salesforce, and Jira are all manually managed. An identity governance tool (SailPoint, Saviynt) has been proposed but not budgeted.
2. **Inconsistent role-to-access mapping.** There is no maintained document that maps "Sales Development Rep" to a specific set of Salesforce Profiles, Okta apps, and Jira projects. IT relies on tribal knowledge.
3. **Late notifications from HR.** The email-based process means IT often gets less than the required 5 days of lead time.
4. **No audit trail connecting HR events to IT actions.** If a compliance audit asks "when was this user provisioned and by whom?", IT must search Jira tickets manually.
