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
