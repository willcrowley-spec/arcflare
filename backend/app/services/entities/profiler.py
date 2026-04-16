"""Sync business entities from Salesforce User / hierarchy sources."""

import json
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import PlatformConnection
from app.models.entity import BusinessEntity
from app.services.salesforce.metadata import get_sf_client, decrypt_tokens

logger = logging.getLogger(__name__)


async def sync_from_salesforce(org_id: UUID, connection_id: UUID, db: AsyncSession) -> int:
    """
    Pull Salesforce Users / roles into BusinessEntity rows.

    Queries UserRole hierarchy and active User aggregates (no PII identifiers beyond
    Salesforce internal role linkage). Replaces all BusinessEntity rows for the org.
    """
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.org_id != org_id:
        raise ValueError("Invalid connection for organization")
    if not conn.oauth_tokens_encrypted:
        return 0
    tokens = json.loads(decrypt_tokens(conn.oauth_tokens_encrypted))
    sf = get_sf_client(tokens["instance_url"], tokens["access_token"])

    role_records = []
    try:
        result = sf.query("SELECT Id, Name, ParentRoleId FROM UserRole")
        role_records = result.get("records", [])
        while not result.get("done") and result.get("nextRecordsUrl"):
            result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
            role_records.extend(result.get("records", []))
    except Exception as e:
        logger.warning("sf_user_roles_failed error=%s", e)

    user_records = []
    try:
        result = sf.query(
            "SELECT Id, UserRoleId, Department, Title, Profile.Name "
            "FROM User WHERE IsActive = true"
        )
        user_records = result.get("records", [])
        while not result.get("done") and result.get("nextRecordsUrl"):
            result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
            user_records.extend(result.get("records", []))
    except Exception as e:
        logger.warning("sf_users_failed error=%s", e)

    await db.execute(delete(BusinessEntity).where(BusinessEntity.org_id == org_id))

    sf_role_to_entity: dict[str, BusinessEntity] = {}
    role_parent_map: dict[str, str | None] = {}

    for role in role_records:
        sf_id = role.get("Id", "")
        parent_sf_id = role.get("ParentRoleId")
        role_parent_map[sf_id] = parent_sf_id

        ent = BusinessEntity(
            org_id=org_id,
            name=role.get("Name", "Unknown Role"),
            entity_type="role",
            headcount=0,
            is_active=True,
            metadata_json={"sf_role_id": sf_id},
            cost_data_json={},
        )
        db.add(ent)
        sf_role_to_entity[sf_id] = ent

    await db.flush()  # assigns PKs

    for sf_id, ent in sf_role_to_entity.items():
        parent_sf_id = role_parent_map.get(sf_id)
        if parent_sf_id and parent_sf_id in sf_role_to_entity:
            ent.parent_id = sf_role_to_entity[parent_sf_id].id

    role_headcount: dict[str, int] = defaultdict(int)
    dept_set: set[str] = set()

    for user in user_records:
        role_id = user.get("UserRoleId")
        if role_id:
            role_headcount[role_id] += 1
        dept = (user.get("Department") or "").strip()
        if dept:
            dept_set.add(dept)

    for sf_id, count in role_headcount.items():
        if sf_id in sf_role_to_entity:
            sf_role_to_entity[sf_id].headcount = count

    for dept_name in sorted(dept_set):
        dept_count = sum(
            1 for u in user_records if (u.get("Department") or "").strip() == dept_name
        )
        db.add(
            BusinessEntity(
                org_id=org_id,
                name=dept_name,
                entity_type="department",
                headcount=dept_count,
                is_active=True,
                metadata_json={},
                cost_data_json={},
            )
        )

    total = len(sf_role_to_entity) + len(dept_set)
    logger.info(
        "entity_sync_complete org=%s roles=%d departments=%d users=%d",
        org_id,
        len(sf_role_to_entity),
        len(dept_set),
        len(user_records),
    )
    return total


async def build_hierarchy(org_id: UUID, db: AsyncSession) -> dict:
    """Return nested tree structure for all BusinessEntity rows in the org."""
    res = await db.execute(select(BusinessEntity).where(BusinessEntity.org_id == org_id))
    entities = res.scalars().all()
    by_parent: dict[UUID | None, list[BusinessEntity]] = {}
    for e in entities:
        by_parent.setdefault(e.parent_id, []).append(e)

    def walk(parent: UUID | None) -> list[dict]:
        nodes = []
        for ent in by_parent.get(parent, []):
            nodes.append(
                {
                    "id": ent.id,
                    "name": ent.name,
                    "entity_type": ent.entity_type,
                    "children": walk(ent.id),
                }
            )
        return nodes

    return {"roots": walk(None)}
