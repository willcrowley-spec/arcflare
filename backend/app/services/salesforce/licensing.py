"""Salesforce licensing and billing data retrieval."""
import logging
from uuid import UUID

from simple_salesforce import Salesforce
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.licensing import OrgLicenseSnapshot

logger = logging.getLogger(__name__)

LICENSE_PRICING = {
    "Salesforce": 165,
    "Salesforce Platform": 25,
    "Identity": 5,
    "Chatter Free": 0,
    "Chatter External": 0,
    "Customer Community": 2,
    "Customer Community Plus": 7,
    "Partner Community": 10,
    "Service Cloud": 165,
    "Sales Cloud": 165,
}


def _rest_query_all(sf: Salesforce, soql: str) -> list[dict]:
    """Execute a Data API SOQL query with pagination (local copy to avoid import cycles)."""
    out: list[dict] = []
    result = sf.query(soql)
    out.extend(result.get("records", []))
    while not result.get("done") and result.get("nextRecordsUrl"):
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
        out.extend(result.get("records", []))
    return out


def pull_org_info(sf: Salesforce) -> dict:
    try:
        result = sf.query(
            "SELECT Id, Name, OrganizationType, IsSandbox, TrialExpirationDate, InstanceName FROM Organization"
        )
        records = result.get("records", [])
        return records[0] if records else {}
    except Exception as e:
        logger.warning("sf_org_info_failed error=%s", e)
        return {}


def pull_user_licenses(sf: Salesforce) -> list[dict]:
    try:
        raw = _rest_query_all(sf, "SELECT Id, MasterLabel, TotalLicenses, UsedLicenses, Status FROM UserLicense")
        return [
            {
                "type": r.get("MasterLabel", ""),
                "total": r.get("TotalLicenses", 0),
                "used": r.get("UsedLicenses", 0),
                "status": r.get("Status", ""),
            }
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_user_licenses_failed error=%s", e)
        return []


def pull_package_licenses(sf: Salesforce) -> list[dict]:
    try:
        raw = _rest_query_all(
            sf,
            "SELECT Id, NamespacePrefix, AllowedLicenses, UsedLicenses, "
            "ExpirationDate, Status FROM PackageLicense",
        )
        return [
            {
                "namespace": r.get("NamespacePrefix", ""),
                "total": r.get("AllowedLicenses", 0),
                "used": r.get("UsedLicenses", 0),
                "expiration": r.get("ExpirationDate"),
                "status": r.get("Status", ""),
            }
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_package_licenses_failed error=%s", e)
        return []


def pull_permission_set_licenses(sf: Salesforce) -> list[dict]:
    try:
        raw = _rest_query_all(
            sf,
            "SELECT Id, DeveloperName, MasterLabel, TotalLicenses, UsedLicenses FROM PermissionSetLicense",
        )
        return [
            {
                "name": r.get("MasterLabel", r.get("DeveloperName", "")),
                "developer_name": r.get("DeveloperName", ""),
                "total": r.get("TotalLicenses", 0),
                "used": r.get("UsedLicenses", 0),
            }
            for r in raw
        ]
    except Exception as e:
        logger.warning("sf_psl_failed error=%s", e)
        return []


def pull_limits(sf: Salesforce) -> dict:
    try:
        return sf.restful("limits/")
    except Exception as e:
        logger.warning("sf_limits_failed error=%s", e)
        return {}


def estimate_annual_spend(edition: str, licenses: list[dict]) -> float:
    _ = edition  # reserved for edition-based pricing heuristics
    total = 0.0
    for lic in licenses:
        name = lic.get("type", "")
        used = lic.get("used", 0) or 0
        per_user = LICENSE_PRICING.get(name, 0)
        if per_user == 0:
            for key, price in LICENSE_PRICING.items():
                if key.lower() in name.lower():
                    per_user = price
                    break
        total += used * per_user * 12
    return total


async def snapshot_licensing(
    connection_id: UUID, org_id: UUID, sf: Salesforce, db: AsyncSession
) -> OrgLicenseSnapshot:
    org_info = pull_org_info(sf)
    licenses = pull_user_licenses(sf)
    pkg_licenses = pull_package_licenses(sf)
    psl = pull_permission_set_licenses(sf)
    limits = pull_limits(sf)

    edition = org_info.get("OrganizationType", "")
    is_sandbox = bool(org_info.get("IsSandbox", False))
    spend = estimate_annual_spend(edition, licenses)

    snap = OrgLicenseSnapshot(
        org_id=org_id,
        connection_id=connection_id,
        edition=edition,
        is_sandbox=is_sandbox,
        licenses_json=licenses,
        package_licenses_json=pkg_licenses,
        psl_json=psl,
        limits_json=limits,
        estimated_annual_spend=spend,
    )
    db.add(snap)
    await db.flush()

    logger.info(
        "license_snapshot_complete connection=%s edition=%s licenses=%d packages=%d spend=%.2f",
        connection_id,
        edition,
        len(licenses),
        len(pkg_licenses),
        spend,
    )
    return snap
