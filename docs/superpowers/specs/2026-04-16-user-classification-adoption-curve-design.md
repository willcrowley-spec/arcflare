# User Classification & Historical Adoption Curve

**Date**: 2026-04-16
**Status**: Draft
**Scope**: Backend user classification, velocity snapshot enrichment, frontend adoption chart rewrite

## Problem

1. **System/integration users inflate counts.** Salesforce auto-provisions users like EinsteinServiceAgent, SalesforceIQ Integration, B2BMA Integration, etc. These appear alongside real humans in internal user counts, role/profile distributions, and cost modeling — making all of those metrics misleading.

2. **Adoption chart has no history.** The Platform Adoption chart plots `snapshot_at` timestamps from `UserVelocitySnapshot` records. Since snapshots only exist for each sync run, a freshly connected org shows a flat line from one date to the same date. The chart should show when users were actually created over time.

## Design

### User Classification

Three-tier classification applied to every active `User` record during sync. First match wins:

| Tier | Signal | Examples |
|------|--------|----------|
| **System** | `LicenseDefinitionKey` in `SYSTEM_LICENSE_KEYS` OR (`Email` ends with `@salesforce.com` AND name matches known integration patterns) | EinsteinServiceAgent, SalesforceIQ Integration, B2BMA Integration, SalesEinsteinCoach |
| **External** | `LicenseDefinitionKey` in `EXTERNAL_LICENSE_KEYS` (existing set from `licensing.py`) | Customer Community, Partner Community, External Identity |
| **Human** | Everything else | Standard Salesforce, Platform, Platform One users |

**System license keys** (new constant):

```
SYSTEM_LICENSE_KEYS = {
    "SFDC_INTL",                    # Salesforce Integration
    "AUL_EINSTEIN_ACTIVITY",        # Einstein Activity Capture
    "AUL_LINKEDIN_SALES_NAVIGATOR", # LinkedIn Sales Navigator
    "PID_Chatter_Only_Integration", # Chatter Integration
    "SFDC_PLATFORM_INTL",          # Platform Integration
}
```

**Email-based fallback heuristic** (catches system users on standard licenses):
- `Email` domain is `salesforce.com` AND
- `Name` contains one of: `Integration`, `Einstein`, `Automated`, `Coach`, `Agent User`, `Insights`

This heuristic is intentionally conservative — it requires both the email domain AND a name pattern to avoid false positives on real humans who happen to work at Salesforce.

### New Module: `backend/app/services/salesforce/user_classifier.py`

Single pure function:

```python
def classify_user(user: dict) -> str:
    """Return 'system', 'external', or 'human'."""
```

Takes a raw SOQL user record dict. No database access, no side effects. Reuses `EXTERNAL_LICENSE_KEYS` from `licensing.py`.

### SOQL Changes in `user_velocity.py`

**Before**: 6 separate aggregate queries (`COUNT()` for active, internal, new, deactivated, GROUP BY role, GROUP BY profile).

**After**: 2 queries:

1. **Active users** (individual records for classification + bucketing):
   ```sql
   SELECT Id, Name, Email, CreatedDate, UserType,
          Profile.Name, Profile.UserLicense.LicenseDefinitionKey,
          UserRole.Name
   FROM User
   WHERE IsActive = true
   ```
2. **Deactivated this month** (stays aggregate since we just need a count):
   ```sql
   SELECT COUNT() FROM User
   WHERE IsActive = false AND LastModifiedDate = THIS_MONTH
   ```

From query 1, we derive everything: active counts per tier, by_role, by_profile (both filtered to human-only), new_users_this_month (human users with `CreatedDate = THIS_MONTH`), and the historical adoption curve.

### Data Model Changes

`UserVelocitySnapshot` gets two new columns:

| Column | Type | Description |
|--------|------|-------------|
| `by_created_month_json` | `JSON` | Monthly user creation buckets: `{ "2023-01": { "human": 3, "system": 1, "external": 0 }, ... }` |
| `system_user_count` | `Integer` | Active system/integration user count |

Existing columns remain and are derived from the classified user data:
- `active_user_count` = human + system + external
- `internal_active_count` = human only (system users excluded)
- `external_active_count` = external tier count
- `by_role_json` = human users only (unchanged filter intent, now explicitly excludes system)
- `by_profile_json` = human users only

### Alembic Migration

New migration `004_velocity_classification.py`:
- Adds `by_created_month_json` column (JSON, nullable, default `{}`)
- Adds `system_user_count` column (Integer, not nullable, server_default `0`)

### Frontend Changes

**`VelocitySection` in `Organization/index.tsx`:**

- X-axis: months from `by_created_month_json` keys, sorted chronologically (e.g., "Jan '23" through "Apr '26")
- Y-axis: cumulative user count
- Three lines:
  - **Human** — dark blue, primary visual weight
  - **External** — teal, secondary
  - **System** — grey dashed, de-emphasized
- Cumulative sum computed on frontend: for month N, value = sum of all months <= N
- Falls back to current `snapshot_at` plotting if `by_created_month_json` is empty/missing (backward compat with old snapshots)

**Summary stats update:**
```
Human: 10 | System: 5 | External: 3 | New this month: +1 | Deactivated: -0
```

**Organization profile card:**
- Shows `human_users` count instead of `internal_users`
- Adds `system_users` as a separate de-emphasized stat

**Role & Profile distribution:**
- Already filtered to `UserType = 'Standard'` on backend
- Now additionally excludes system-tier users, so distributions reflect real human organizational structure

### Settings JSON Enrichment

The `settings_json` block written to `Organization` during sync updates:
- `internal_users` → renamed to `human_users`
- New field: `system_users` (count of system/integration tier)
- `external_users` stays as-is

### Impact on Cost Modeling

System users should not contribute to human capital cost deflection calculations. They represent Salesforce platform overhead, not labor. The cost model should use `human_users` as its headcount basis, not `internal_users`.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/salesforce/user_classifier.py` | **New** — classification function + constants |
| `backend/app/services/salesforce/user_velocity.py` | Rewrite queries, integrate classifier, add monthly bucketing |
| `backend/app/services/salesforce/metadata.py` | Update `settings_json` enrichment to use human/system split |
| `backend/app/models/licensing.py` | Add `by_created_month_json`, `system_user_count` to `UserVelocitySnapshot` |
| `backend/app/schemas/organization.py` | Add new fields to `UserVelocityResponse` |
| `backend/alembic/versions/004_velocity_classification.py` | **New** — migration |
| `frontend/src/pages/Organization/index.tsx` | Rewrite `VelocitySection` chart + update profile card stats |
