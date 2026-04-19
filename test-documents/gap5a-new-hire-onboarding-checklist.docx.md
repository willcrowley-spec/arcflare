# New Employee Onboarding Checklist

**Document Owner:** Amy Rodriguez, HR Business Partner
**Last Updated:** November 2025
**Classification:** Internal — Human Resources

## Overview

This checklist covers everything that must happen when a new employee joins the company, from the day the offer is accepted through Day 90. Multiple departments are involved: HR, IT, Facilities, and the hiring manager's team.

## Pre-Start (Offer Accepted → Day 1)

### HR Tasks
- [ ] Send offer letter and collect signed copy (DocuSign)
- [ ] Initiate background check (via Checkr)
- [ ] Create employee record in BambooHR
- [ ] Enroll in benefits portal (Justworks)
- [ ] Send welcome email with Day 1 logistics
- [ ] Order company swag kit (via SwagUp)
- [ ] Add to relevant Slack channels: #general, #random, team channel

### IT Tasks — **This is where the gap is**
- [ ] Create Google Workspace account (email, calendar, drive)
- [ ] Provision Okta SSO profile with appropriate application assignments
- [ ] Create Salesforce user (if applicable) with correct Profile and Permission Sets
- [ ] Create Jira account and add to appropriate project boards
- [ ] Set up VPN access (if remote)
- [ ] Ship or prepare laptop with standard image
- [ ] Configure MFA enrollment invitation

**Problem:** HR sends IT an email with new hire details (name, start date, role, department, manager). IT has their own internal Jira board for provisioning requests. There is no integration between BambooHR and IT's systems. Each request is manually created by the IT Service Desk from the HR email.

**Failure rate:** Approximately 25% of new hires do not have full system access on their start date. The most commonly missed items are Salesforce provisioning (wrong Profile assigned) and Okta app assignments (missing apps for the role).

### Facilities Tasks (On-site employees only)
- [ ] Assign desk/workspace
- [ ] Order access badge
- [ ] Set up desk phone (if applicable)

## Day 1

- HR orientation (benefits, policies, culture) — 90 minutes
- IT setup assistance (laptop, accounts, MFA) — 60 minutes
- Manager 1:1 — 30 minutes
- Team lunch

## Week 1

- Complete compliance training modules in LMS (Lessonly)
- Shadow 3 customer calls or internal meetings
- Complete BambooHR onboarding tasks (tax forms, emergency contact, etc.)
- Set 30-60-90 day goals with manager

## Day 30 / Day 60 / Day 90 Check-ins

- Manager conducts structured check-in using BambooHR performance module
- HR reviews onboarding satisfaction survey
- IT confirms all provisioned access is still appropriate

## Systems Involved

| System | Owner | Purpose |
|--------|-------|---------|
| BambooHR | HR | Employee record, onboarding tasks, performance |
| Justworks | HR | Payroll, benefits |
| Google Workspace | IT | Email, calendar, docs |
| Okta | IT | SSO, application access |
| Salesforce | IT + Admin | CRM access for sales/support roles |
| Jira | IT + Engineering | Project boards, IT service desk |
| Slack | IT | Communication |
| Lessonly | L&D | Training modules |
| Checkr | HR | Background checks |
| DocuSign | HR | Offer letters, contracts |
