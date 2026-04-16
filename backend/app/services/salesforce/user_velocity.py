"""Salesforce user velocity snapshots -- platform adoption tracking."""
import logging
from uuid import UUID

from simple_salesforce import Salesforce
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.licensing import UserVelocitySnapshot

logger = logging.getLogger(__name__)


def _rest_query_all(sf: Salesforce, soql: str) -> list[dict]:
    """Execute a Data API SOQL query with pagination (local copy to avoid import cycles)."""
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
        "new_users_this_month": 0,
        "deactivated_this_month": 0,
        "by_role": {},
        "by_profile": {},
    }

    try:
        result = sf.query("SELECT COUNT() FROM User WHERE IsActive = true")
        data["active_user_count"] = result.get("totalSize", 0)
    except Exception as e:
        logger.warning("sf_active_user_count_failed error=%s", e)

    try:
        result = sf.query(
            "SELECT COUNT() FROM User WHERE IsActive = true "
            "AND CreatedDate = THIS_MONTH"
        )
        data["new_users_this_month"] = result.get("totalSize", 0)
    except Exception as e:
        logger.warning("sf_new_users_failed error=%s", e)

    try:
        result = sf.query(
            "SELECT COUNT() FROM User WHERE IsActive = false "
            "AND LastModifiedDate = THIS_MONTH"
        )
        data["deactivated_this_month"] = result.get("totalSize", 0)
    except Exception as e:
        logger.warning("sf_deactivated_users_failed error=%s", e)

    try:
        raw = _rest_query_all(
            sf,
            "SELECT UserRole.Name roleName, COUNT(Id) cnt "
            "FROM User WHERE IsActive = true "
            "GROUP BY UserRole.Name",
        )
        for r in raw:
            role_name = (r.get("roleName") or r.get("UserRole", {}).get("Name")) or "No Role"
            data["by_role"][role_name] = r.get("cnt", 0)
    except Exception as e:
        logger.warning("sf_users_by_role_failed error=%s", e)

    try:
        raw = _rest_query_all(
            sf,
            "SELECT Profile.Name profileName, COUNT(Id) cnt "
            "FROM User WHERE IsActive = true "
            "GROUP BY Profile.Name",
        )
        for r in raw:
            prof_name = (r.get("profileName") or r.get("Profile", {}).get("Name")) or "Unknown"
            data["by_profile"][prof_name] = r.get("cnt", 0)
    except Exception as e:
        logger.warning("sf_users_by_profile_failed error=%s", e)

    return data


async def snapshot_user_velocity(
    connection_id: UUID, org_id: UUID, sf: Salesforce, db: AsyncSession
) -> UserVelocitySnapshot:
    data = pull_user_velocity(sf)
    snap = UserVelocitySnapshot(
        org_id=org_id,
        connection_id=connection_id,
        active_user_count=data["active_user_count"],
        new_users_this_month=data["new_users_this_month"],
        deactivated_this_month=data["deactivated_this_month"],
        by_role_json=data["by_role"],
        by_profile_json=data["by_profile"],
    )
    db.add(snap)
    await db.flush()

    logger.info(
        "user_velocity_snapshot_complete connection=%s active=%d new=%d deactivated=%d roles=%d profiles=%d",
        connection_id,
        data["active_user_count"],
        data["new_users_this_month"],
        data["deactivated_this_month"],
        len(data["by_role"]),
        len(data["by_profile"]),
    )
    return snap
