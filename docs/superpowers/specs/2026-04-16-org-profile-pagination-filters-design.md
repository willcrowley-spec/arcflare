# Organization Profile Enrichment, Pagination, and Automation Filtering — Design Spec

**Date:** 2026-04-16
**Status:** Approved

## Problems

### 1. Inactive automations polluting data
`pull_flows` and `pull_apex_triggers` fetch ALL records regardless of status. Inactive flows and deleted apex classes are persisted and counted in summary cards, tables, and will poison the recommendation engine.

### 2. Pagination is unusable
The `DataTable` component only has prev/next arrows and "Page 2 / 19" text. No way to jump to a specific page, no first/last buttons, no page size selector. Navigating 19 pages with arrows is unacceptable for enterprise UX.

### 3. Organization page shows nothing
Multiple compounding failures:
- `Organization.name` is set to the Clerk org ID string, not the company name.
- `sync_from_salesforce` in `profiler.py` is a stub that returns 0.
- The page gates everything behind `roots.length === 0 && entityTotal === 0`, which blocks licensing/velocity sections from rendering even when that data exists.
- `settings_json` is empty so all profile fields show "—".
- SF org name is queried in `pull_org_info` but never written to the Organization model.

## Design

### A. Automation Filtering

**In `sync_metadata` persistence loop:** Only persist automations where `is_active == True`. Skip inactive flows, inactive triggers, and deleted apex classes.

**For apex classes:** Filter on `Status != 'Deleted'` during the Tooling API query itself (add WHERE clause to SOQL). All non-deleted apex classes are considered "active" for our purposes — they exist in the org and affect the platform.

**Impact:** Summary cards show accurate active counts. Recommendation engine only analyzes active automations. No schema changes needed.

### B. Enterprise Pagination

Replace the DataTable footer with a proper pagination bar:

- **Page number buttons** with ellipsis: `< 1 2 3 ... 17 18 19 >`
- **First/Last buttons** (chevron-double icons)
- **Page size dropdown**: 10, 25, 50, 100 rows per page
- **"Showing X-Y of Z items"** label

Logic for page button rendering:
- Always show first page, last page, and current page +/- 1 sibling
- Use ellipsis (`...`) for gaps larger than 1
- Example: current=5, total=19 → `1 ... 4 5 6 ... 19`

No changes to backend pagination — this is purely frontend.

### C. Organization Profile Enrichment

#### C.1: Enrich Organization.settings_json after sync

At the end of `sync_metadata`, after licensing and velocity snapshots complete, write a structured profile into `Organization.settings_json`:

```json
{
  "sf_org_name": "EPMS Corp",
  "sf_org_id": "00D...",
  "edition": "Enterprise",
  "is_sandbox": false,
  "instance_name": "na139",
  "instance_url": "https://epms.my.salesforce.com",
  "active_users": 247,
  "estimated_annual_spend": 592800,
  "top_packages": ["Salesforce CPQ", "Conga Composer", "DocuSign"],
  "license_summary": { "total": 300, "used": 247 },
  "role_count": 15,
  "profile_count": 8
}
```

Data sources (all already pulled during sync):
- `pull_org_info` → sf_org_name, sf_org_id, edition, is_sandbox, instance_name
- `PlatformConnection.instance_url` → instance_url
- `snapshot_licensing` result → estimated_annual_spend, license totals
- `snapshot_user_velocity` result → active_users, role_count, profile_count
- `MetadataComponent` rows (category=installed_package) → top_packages

Also update `Organization.name` to the SF org name if it's still set to the Clerk org ID.

#### C.2: Implement sync_from_salesforce profiler

Replace the stub in `profiler.py` with actual SF User/Role queries:

1. Query `UserRole` via SOQL: `SELECT Id, Name, ParentRoleId FROM UserRole`
2. Query active Users: `SELECT Id, Name, Department, Title, UserRoleId, Profile.Name FROM User WHERE IsActive = true`
3. Create `BusinessEntity` rows:
   - One per UserRole (entity_type="role", parent_id mapped from ParentRoleId)
   - One per unique Department (entity_type="department")
   - Headcount aggregated per role/department
4. No PII stored — just role names, department names, titles, and headcounts.

Call this from `sync_metadata` after the existing snapshots.

#### C.3: Fix Organization page rendering

The page currently shows "No organization profile yet" when entities and hierarchy are empty, blocking all other sections. Fix:

- Remove the gate that blocks everything. Each section renders independently based on its own data availability.
- Business Profile card: read from `settings_json` (sf_org_name, edition, active_users, instance_url).
- Licensing section: renders if `licensingQuery.data` exists (already coded, just blocked by the gate).
- Velocity section: renders if `velocityQuery.data` exists (already coded, just blocked).
- Hierarchy section: renders if `roots.length > 0` (show "Syncing..." or "Run sync" if empty).
- Cost modeling: renders with whatever data exists.

## Non-Goals

- Pulling individual user PII (emails, phone numbers).
- Manual org profile editing (auto-populated only for now).
- Backend pagination changes (frontend-only table improvement).
- Changing the Organization DB schema (using existing `settings_json` JSONB column).

## Error Handling

- If `pull_org_info` fails, `settings_json` enrichment is skipped (non-fatal).
- If User/Role queries fail in the profiler, log warning and continue (don't break the sync).
- Frontend gracefully handles missing `settings_json` keys with "—" fallbacks (already does this).

## Testing

1. Connect SF org, run sync → verify Organization page shows company name, edition, active users, licensing, velocity.
2. Verify inactive flows/triggers are NOT in the automations table or summary cards.
3. Navigate a table with 200+ rows → verify page buttons, size selector, jumping to page 15.
4. Verify hierarchy tree shows roles after sync.
