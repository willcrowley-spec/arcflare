# User Classification & Historical Adoption Curve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify Salesforce users into Human/System/External tiers and build a historical adoption curve from CreatedDate instead of sync timestamps.

**Architecture:** New pure-function classifier module, rewritten velocity SOQL (6 queries → 2), two new snapshot columns, and a frontend chart rewrite using cumulative monthly buckets from CreatedDate.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Alembic, simple-salesforce SOQL, React/Recharts

---

### Task 1: Create User Classifier Module

**Files:**
- Create: `backend/app/services/salesforce/user_classifier.py`

- [ ] **Step 1: Create the classifier module**

Create `backend/app/services/salesforce/user_classifier.py`:

```python
"""Classify Salesforce User records into human / system / external tiers."""
from app.services.salesforce.licensing import EXTERNAL_LICENSE_KEYS

SYSTEM_LICENSE_KEYS = {
    "SFDC_INTL",
    "AUL_EINSTEIN_ACTIVITY",
    "AUL_LINKEDIN_SALES_NAVIGATOR",
    "PID_Chatter_Only_Integration",
    "SFDC_PLATFORM_INTL",
}

_SYSTEM_NAME_PATTERNS = {
    "integration",
    "einstein",
    "automated",
    "coach",
    "agent user",
    "insights",
}


def classify_user(user: dict) -> str:
    """Return 'system', 'external', or 'human'.

    Classification hierarchy (first match wins):
    1. System — license key in SYSTEM_LICENSE_KEYS or (noreply@salesforce email + name pattern)
    2. External — license key in EXTERNAL_LICENSE_KEYS
    3. Human — everything else
    """
    profile = user.get("Profile") or {}
    user_license = profile.get("UserLicense") or {}
    lic_key = user_license.get("LicenseDefinitionKey", "")

    if lic_key in SYSTEM_LICENSE_KEYS:
        return "system"

    email = (user.get("Email") or "").lower()
    name = (user.get("Name") or "").lower()
    if email.endswith("@salesforce.com") and any(p in name for p in _SYSTEM_NAME_PATTERNS):
        return "system"

    if lic_key in EXTERNAL_LICENSE_KEYS:
        return "external"

    user_type = user.get("UserType", "")
    if user_type not in ("Standard", ""):
        return "external"

    return "human"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/salesforce/user_classifier.py
git commit -m "feat: add user classifier module (human/system/external)"
```

---

### Task 2: Add New Columns to UserVelocitySnapshot Model

**Files:**
- Modify: `backend/app/models/licensing.py:52-84`
- Create: `backend/alembic/versions/004_velocity_classification.py`

- [ ] **Step 1: Add columns to the model**

In `backend/app/models/licensing.py`, add two new columns to `UserVelocitySnapshot` after the `by_profile_json` line (line 81):

```python
    by_created_month_json: Mapped[dict] = mapped_column(JSONB, nullable=True, server_default=text("'{}'::jsonb"))
    system_user_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

- [ ] **Step 2: Create Alembic migration**

Create `backend/alembic/versions/004_velocity_classification.py`:

```python
"""Add by_created_month_json and system_user_count to user_velocity_snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("by_created_month_json", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "user_velocity_snapshots",
        sa.Column("system_user_count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_velocity_snapshots", "system_user_count")
    op.drop_column("user_velocity_snapshots", "by_created_month_json")
```

- [ ] **Step 3: Update the Pydantic response schema**

In `backend/app/schemas/organization.py`, add to `UserVelocityResponse` (after `external_active_count`):

```python
    system_user_count: int = 0
    by_created_month_json: dict = {}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/licensing.py backend/alembic/versions/004_velocity_classification.py backend/app/schemas/organization.py
git commit -m "feat: add velocity classification columns + migration"
```

---

### Task 3: Rewrite user_velocity.py to Use Classifier + Monthly Bucketing

**Files:**
- Modify: `backend/app/services/salesforce/user_velocity.py` (full rewrite of `pull_user_velocity`)

- [ ] **Step 1: Rewrite pull_user_velocity**

Replace the entire contents of `backend/app/services/salesforce/user_velocity.py`:

```python
"""Salesforce user velocity snapshots -- platform adoption tracking."""
import logging
from collections import defaultdict
from uuid import UUID

from simple_salesforce import Salesforce
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.licensing import UserVelocitySnapshot
from app.services.salesforce.user_classifier import classify_user

logger = logging.getLogger(__name__)


def _rest_query_all(sf: Salesforce, soql: str) -> list[dict]:
    out: list[dict] = []
    result = sf.query(soql)
    out.extend(result.get("records", []))
    while not result.get("done") and result.get("nextRecordsUrl"):
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
        out.extend(result.get("records", []))
    return out


def pull_user_velocity(sf: Salesforce) -> dict:
    data: dict = {
        "active_user_count": 0,
        "internal_active_count": 0,
        "external_active_count": 0,
        "system_user_count": 0,
        "new_users_this_month": 0,
        "deactivated_this_month": 0,
        "by_role": {},
        "by_profile": {},
        "by_created_month": {},
    }

    try:
        users = _rest_query_all(
            sf,
            "SELECT Id, Name, Email, CreatedDate, UserType, "
            "Profile.Name, Profile.UserLicense.LicenseDefinitionKey, "
            "UserRole.Name "
            "FROM User WHERE IsActive = true",
        )
    except Exception as e:
        logger.warning("sf_user_query_failed error=%s", e)
        return data

    monthly_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"human": 0, "system": 0, "external": 0})
    role_counts: dict[str, int] = defaultdict(int)
    profile_counts: dict[str, int] = defaultdict(int)
    human_count = 0
    system_count = 0
    external_count = 0
    new_this_month = 0

    for u in users:
        tier = classify_user(u)

        created = (u.get("CreatedDate") or "")[:7]  # "2024-03"
        if created:
            monthly_buckets[created][tier] += 1

        if tier == "human":
            human_count += 1
            role_name = (u.get("UserRole") or {}).get("Name") or "No Role"
            profile_name = (u.get("Profile") or {}).get("Name") or "Unknown"
            role_counts[role_name] += 1
            profile_counts[profile_name] += 1
            created_date = u.get("CreatedDate", "")
            if "T" in created_date:
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
                    now = datetime.now(tz=timezone.utc)
                    if dt.year == now.year and dt.month == now.month:
                        new_this_month += 1
                except ValueError:
                    pass
        elif tier == "system":
            system_count += 1
        else:
            external_count += 1

    data["active_user_count"] = len(users)
    data["internal_active_count"] = human_count
    data["external_active_count"] = external_count
    data["system_user_count"] = system_count
    data["new_users_this_month"] = new_this_month
    data["by_role"] = dict(role_counts)
    data["by_profile"] = dict(profile_counts)
    data["by_created_month"] = {k: dict(v) for k, v in sorted(monthly_buckets.items())}

    try:
        result = sf.query(
            "SELECT COUNT() FROM User WHERE IsActive = false AND LastModifiedDate = THIS_MONTH"
        )
        data["deactivated_this_month"] = result.get("totalSize", 0)
    except Exception as e:
        logger.warning("sf_deactivated_users_failed error=%s", e)

    return data


async def snapshot_user_velocity(
    connection_id: UUID, org_id: UUID, sf: Salesforce, db: AsyncSession
) -> UserVelocitySnapshot:
    data = pull_user_velocity(sf)
    snap = UserVelocitySnapshot(
        org_id=org_id,
        connection_id=connection_id,
        active_user_count=data["active_user_count"],
        internal_active_count=data["internal_active_count"],
        external_active_count=data["external_active_count"],
        system_user_count=data["system_user_count"],
        new_users_this_month=data["new_users_this_month"],
        deactivated_this_month=data["deactivated_this_month"],
        by_role_json=data["by_role"],
        by_profile_json=data["by_profile"],
        by_created_month_json=data["by_created_month"],
    )
    db.add(snap)
    await db.flush()

    logger.info(
        "user_velocity_snapshot_complete connection=%s total=%d human=%d system=%d external=%d new=%d deactivated=%d roles=%d profiles=%d months=%d",
        connection_id,
        data["active_user_count"],
        data["internal_active_count"],
        data["system_user_count"],
        data["external_active_count"],
        data["new_users_this_month"],
        data["deactivated_this_month"],
        len(data["by_role"]),
        len(data["by_profile"]),
        len(data["by_created_month"]),
    )
    return snap
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/salesforce/user_velocity.py
git commit -m "feat: rewrite velocity to use classifier + monthly bucketing"
```

---

### Task 4: Update settings_json Enrichment in metadata.py

**Files:**
- Modify: `backend/app/services/salesforce/metadata.py:869-871`

- [ ] **Step 1: Update the settings_json block**

In `backend/app/services/salesforce/metadata.py`, find the settings_json enrichment block (around lines 869-871) and replace:

```python
                "active_users": getattr(vel_snap, "active_user_count", 0) if vel_snap else 0,
                "internal_users": getattr(vel_snap, "internal_active_count", 0) if vel_snap else 0,
                "external_users": getattr(vel_snap, "external_active_count", 0) if vel_snap else 0,
```

with:

```python
                "active_users": getattr(vel_snap, "active_user_count", 0) if vel_snap else 0,
                "human_users": getattr(vel_snap, "internal_active_count", 0) if vel_snap else 0,
                "system_users": getattr(vel_snap, "system_user_count", 0) if vel_snap else 0,
                "external_users": getattr(vel_snap, "external_active_count", 0) if vel_snap else 0,
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/salesforce/metadata.py
git commit -m "feat: update settings_json enrichment with human/system split"
```

---

### Task 5: Rewrite Frontend VelocitySection + Update Profile Card

**Files:**
- Modify: `frontend/src/pages/Organization/index.tsx:300-414` (VelocitySection)
- Modify: `frontend/src/pages/Organization/index.tsx:435-506` (profile card stats)

- [ ] **Step 1: Update the VelocitySnap type and chart**

In `frontend/src/pages/Organization/index.tsx`, replace the `VelocitySnap` type and `VelocitySection` function (lines 300-413):

```typescript
type VelocitySnap = {
  snapshot_at: string
  active_user_count: number
  internal_active_count?: number
  external_active_count?: number
  system_user_count?: number
  new_users_this_month: number
  deactivated_this_month: number
  by_role_json: Record<string, number>
  by_profile_json: Record<string, number>
  by_created_month_json?: Record<string, { human: number; system: number; external: number }>
}

function VelocitySection({ velocityQuery }: { velocityQuery: { data?: unknown } }) {
  if (!velocityQuery.data || !Array.isArray(velocityQuery.data) || velocityQuery.data.length === 0) return null

  const snapshots = (velocityQuery.data as VelocitySnap[]).slice().reverse()
  const latestSnap = snapshots[snapshots.length - 1]

  const monthlyBuckets = latestSnap?.by_created_month_json
  let chartData: { date: string; human: number; system: number; external: number }[]

  if (monthlyBuckets && Object.keys(monthlyBuckets).length > 0) {
    const months = Object.keys(monthlyBuckets).sort()
    let cumHuman = 0
    let cumSystem = 0
    let cumExternal = 0
    chartData = months.map((m) => {
      const bucket = monthlyBuckets[m] ?? { human: 0, system: 0, external: 0 }
      cumHuman += bucket.human ?? 0
      cumSystem += bucket.system ?? 0
      cumExternal += bucket.external ?? 0
      const [y, mo] = m.split('-')
      const label = new Date(Number(y), Number(mo) - 1).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
      return { date: label, human: cumHuman, system: cumSystem, external: cumExternal }
    })
  } else {
    chartData = snapshots.map((s) => ({
      date: new Date(s.snapshot_at).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }),
      human: s.internal_active_count ?? s.active_user_count,
      system: s.system_user_count ?? 0,
      external: s.external_active_count ?? 0,
    }))
  }

  const humanCount = latestSnap?.internal_active_count ?? latestSnap?.active_user_count ?? 0
  const systemCount = latestSnap?.system_user_count ?? 0
  const externalCount = latestSnap?.external_active_count ?? 0
  const roleEntries = Object.entries(latestSnap?.by_role_json ?? {}).sort((a, b) => b[1] - a[1])
  const profileEntries = Object.entries(latestSnap?.by_profile_json ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <TrendingUp className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Platform Adoption</h2>
            <p className="text-sm text-slate-600">Cumulative user growth by classification</p>
          </div>
        </div>
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="humanGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1e3a5f" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#1e3a5f" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="externalGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0d9488" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Area type="monotone" dataKey="human" name="Human" stroke="#1e3a5f" fill="url(#humanGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="external" name="External" stroke="#0d9488" fill="url(#externalGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="system" name="System" stroke="#94a3b8" fill="none" strokeWidth={1.5} strokeDasharray="4 3" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {chartData.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-600">
            <span>Human: <strong className="text-navy-900">{humanCount}</strong></span>
            <span>System: <strong className="text-slate-500">{systemCount}</strong></span>
            <span>External: <strong className="text-teal-700">{externalCount}</strong></span>
            <span>New this month: <strong className="text-emerald-700">+{latestSnap?.new_users_this_month ?? 0}</strong></span>
            <span>Deactivated: <strong className="text-red-600">-{latestSnap?.deactivated_this_month ?? 0}</strong></span>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Role & Profile Distribution</h2>
            <p className="text-sm text-slate-600">Human users by role and profile</p>
          </div>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By Role</p>
            <div className="max-h-[180px] space-y-1 overflow-auto pr-1">
              {roleEntries.length === 0 ? (
                <p className="text-xs text-slate-400">No role data</p>
              ) : (
                roleEntries.map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-slate-700">{name}</span>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By Profile</p>
            <div className="max-h-[180px] space-y-1 overflow-auto pr-1">
              {profileEntries.length === 0 ? (
                <p className="text-xs text-slate-400">No profile data</p>
              ) : (
                profileEntries.map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-slate-700">{name}</span>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
```

- [ ] **Step 2: Update profile card stats**

In the same file, find the line reading `internal_users` from settings (around line 435):

```typescript
  const internalUsers = typeof settings?.internal_users === 'number' ? settings.internal_users : null
```

Replace with:

```typescript
  const humanUsers = typeof settings?.human_users === 'number' ? settings.human_users : null
  const systemUsers = typeof settings?.system_users === 'number' ? settings.system_users : null
```

Then find where `internalUsers` is displayed in the profile card (around line 505):

```html
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Internal Users</dt>
                  <dd className="font-medium text-slate-900">{internalUsers != null ? formatInt(internalUsers) : employeesDisplay}</dd>
                </div>
```

Replace with:

```html
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Human Users</dt>
                  <dd className="font-medium text-slate-900">{humanUsers != null ? formatInt(humanUsers) : employeesDisplay}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-400">System / Integration</dt>
                  <dd className="font-medium text-slate-500">{systemUsers != null ? formatInt(systemUsers) : '—'}</dd>
                </div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Organization/index.tsx
git commit -m "feat: rewrite adoption chart with historical curve + human/system/external split"
```

---

### Task 6: Run Migration on Railway + Deploy

- [ ] **Step 1: Push all commits to trigger Railway deploy**

```bash
git push
```

- [ ] **Step 2: Run the Alembic migration on Railway Postgres**

Connect to the Railway public Postgres URL and execute:

```sql
ALTER TABLE user_velocity_snapshots
  ADD COLUMN IF NOT EXISTS by_created_month_json jsonb DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS system_user_count integer NOT NULL DEFAULT 0;
```

- [ ] **Step 3: Verify deployment**

Wait for Railway backend and GitHub Pages frontend to finish deploying. Then trigger a Salesforce re-sync from the UI. Verify:
- Sync progress panel shows all phases completing
- Platform Adoption chart shows a historical curve with months on X-axis
- Summary stats show "Human: X | System: Y | External: Z"
- Profile card shows "Human Users" and "System / Integration" as separate lines
- Role & Profile distribution only includes human users
