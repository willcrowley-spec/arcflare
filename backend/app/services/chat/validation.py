"""Validate chat tool parameters and enrich with server-side context."""

from __future__ import annotations

import logging
from collections import deque
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess

logger = logging.getLogger(__name__)

VALID_LEVELS = frozenset({"domain", "process", "subprocess", "step"})
VALID_HANDOFF_TYPES = frozenset(
    {
        "integration",
        "manual",
        "automated",
        "approval_handoff",
        "data_handoff",
        "unknown",
    }
)


def _parse_uuid(value: object, field: str, errors: list[str]) -> UUID | None:
    if value is None:
        return None
    try:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
    except (ValueError, TypeError):
        errors.append(f"{field} must be a valid UUID")
        return None


async def _collect_descendant_ids(root_id: UUID, org_id: UUID, db: AsyncSession) -> set[UUID]:
    out: set[UUID] = {root_id}
    queue: deque[UUID] = deque([root_id])
    while queue:
        pid = queue.popleft()
        q = await db.execute(
            select(BusinessProcess.id).where(
                BusinessProcess.org_id == org_id,
                BusinessProcess.parent_id == pid,
            )
        )
        for (cid,) in q.all():
            if cid not in out:
                out.add(cid)
                queue.append(cid)
    return out


async def validate_tool_call(
    tool_name: str,
    params: dict,
    org_id: UUID,
    db: AsyncSession,
) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    enriched: dict = dict(params) if params else {}

    if not isinstance(params, dict):
        return False, ["Parameters must be a JSON object"], {}

    if tool_name == "rerun_synthesis":
        running = await db.scalar(
            select(func.count())
            .select_from(DiscoveryRun)
            .where(DiscoveryRun.org_id == org_id, DiscoveryRun.status == "running")
        )
        if running and int(running) > 0:
            errors.append("A discovery run is already in progress for this organization.")
            return False, errors, enriched

    if "level" in params and params["level"] is not None:
        if str(params["level"]) not in VALID_LEVELS:
            errors.append(
                f"Invalid level {params['level']!r}; expected one of {sorted(VALID_LEVELS)}."
            )

    if (
        "handoff_type" in params
        and params["handoff_type"] is not None
        and tool_name in ("create_handoff", "update_handoff")
    ):
        if str(params["handoff_type"]) not in VALID_HANDOFF_TYPES:
            errors.append(
                f"Invalid handoff_type {params['handoff_type']!r}; "
                f"expected one of {sorted(VALID_HANDOFF_TYPES)}."
            )

    id_checks: list[tuple[str, str]] = []
    for key, val in list(params.items()):
        if val is None or val == "":
            continue
        if key in ("process_id", "handoff_id", "parent_id", "source_process_id", "target_process_id"):
            id_checks.append((key, str(key)))
        elif key.endswith("_id") and key not in ("discovery_run_id",):
            id_checks.append((key, str(key)))

    for field, label in id_checks:
        raw = params.get(field)
        uid = _parse_uuid(raw, label, errors)
        if uid is None and raw not in (None, ""):
            continue
        if uid is None:
            continue

        if field == "handoff_id":
            row = await db.get(ProcessHandoff, uid)
            if row is None or row.org_id != org_id:
                errors.append(f"{label} not found or not in this organization.")
        else:
            row = await db.get(BusinessProcess, uid)
            if row is None or row.org_id != org_id:
                errors.append(f"{label} not found or not in this organization.")

    if tool_name == "delete_process" and not errors:
        try:
            pid = UUID(str(params["process_id"]))
        except (ValueError, TypeError, KeyError):
            pid = None
        if pid is not None:
            descendants = await _collect_descendant_ids(pid, org_id, db)
            handoff_count = await db.scalar(
                select(func.count())
                .select_from(ProcessHandoff)
                .where(
                    ProcessHandoff.org_id == org_id,
                    or_(
                        ProcessHandoff.source_process_id.in_(descendants),
                        ProcessHandoff.target_process_id.in_(descendants),
                    ),
                )
            )
            enriched["_cascade_info"] = {
                "child_count": max(0, len(descendants) - 1),
                "handoff_count": int(handoff_count or 0),
            }

    is_valid = len(errors) == 0
    if not is_valid:
        logger.info(
            "tool_validation_failed tool=%s org_id=%s errors=%s",
            tool_name,
            org_id,
            errors,
        )
    return is_valid, errors, enriched
