"""HTTP API for org-scoped prompt block customization."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, DbSession
from app.models.prompt import PromptBlock
from app.schemas.prompt import OperationOut, OperationsListOut, PromptBlockOut, PromptBlockUpdate
from app.services.ai.operations import MODEL_OPERATIONS, OPERATION_GROUPS
from app.services.prompts.registry import BLOCK_REGISTRY, get_block_meta, get_registry_for_operation, is_block_editable
from app.services.prompts.resolver import (
    _invalidate_cache,
    resolve_prompt_blocks_with_meta,
    validate_required_vars,
)

router = APIRouter(tags=["prompts"])


async def _purge_archived_org_block(
    db: AsyncSession,
    *,
    operation_id: str,
    block_type: str,
    org_id: UUID,
) -> None:
    await db.execute(
        delete(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.block_type == block_type,
                PromptBlock.org_id == org_id,
                PromptBlock.status == "archived",
            )
        )
    )


async def _get_system_block(
    db: AsyncSession,
    *,
    operation_id: str,
    block_type: str,
) -> PromptBlock | None:
    result = await db.execute(
        select(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.block_type == block_type,
                PromptBlock.org_id.is_(None),
                PromptBlock.status == "active",
            )
        )
    )
    return result.scalar_one_or_none()


async def _get_org_active_block(
    db: AsyncSession,
    *,
    operation_id: str,
    block_type: str,
    org_id: UUID,
) -> PromptBlock | None:
    result = await db.execute(
        select(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.block_type == block_type,
                PromptBlock.org_id == org_id,
                PromptBlock.status == "active",
            )
        )
    )
    return result.scalar_one_or_none()


def _block_out_from_merged_row(row: dict) -> PromptBlockOut:
    return PromptBlockOut(
        block_type=row["block_type"],
        label=row["label"],
        editable=row["editable"],
        content=row["content"],
        is_customized=row["is_customized"],
        is_locked=row["is_locked"],
        available_vars=list(row["available_vars"]),
        version=row["version"],
    )


@router.get("/operations", response_model=OperationsListOut)
async def list_operations() -> OperationsListOut:
    operations: list[OperationOut] = []
    for operation_id in sorted(BLOCK_REGISTRY.keys()):
        op_meta = MODEL_OPERATIONS.get(operation_id, {})
        label = str(op_meta.get("label", operation_id))
        group_key = str(op_meta.get("group", "other"))
        group_label = OPERATION_GROUPS.get(group_key, group_key)
        registry = get_registry_for_operation(operation_id) or []
        blocks: list[dict] = []
        for b in registry:
            blocks.append(
                {
                    "block_type": b["type"],
                    "label": b["label"],
                    "editable": b["editable"],
                    "required_vars": list(b.get("required_vars", [])),
                    "order": b.get("order"),
                }
            )
        operations.append(
            OperationOut(
                operation_id=operation_id,
                label=label,
                group=group_label,
                blocks=blocks,
            )
        )
    return OperationsListOut(operations=operations)


@router.get("/{operation_id}", response_model=list[PromptBlockOut])
async def get_operation_prompts(
    operation_id: str,
    db: DbSession,
    org: CurrentOrg,
) -> list[PromptBlockOut]:
    if not get_registry_for_operation(operation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operation")
    merged = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    return [_block_out_from_merged_row(r) for r in merged]


@router.put("/{operation_id}/blocks/{block_type}", response_model=PromptBlockOut)
async def update_prompt_block(
    operation_id: str,
    block_type: str,
    body: PromptBlockUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> PromptBlockOut:
    if not get_registry_for_operation(operation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operation")
    if get_block_meta(operation_id, block_type) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown block type")
    if not is_block_editable(operation_id, block_type):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This prompt block is not editable")

    missing = validate_required_vars(body.content, operation_id, block_type)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"missing_required_variables": missing},
        )

    system_row = await _get_system_block(db, operation_id=operation_id, block_type=block_type)
    if system_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System default prompt block not found",
        )

    org_row = await _get_org_active_block(db, operation_id=operation_id, block_type=block_type, org_id=org.id)

    if body.content == system_row.content:
        if org_row is not None:
            await _purge_archived_org_block(db, operation_id=operation_id, block_type=block_type, org_id=org.id)
            org_row.status = "archived"
            await db.commit()
            _invalidate_cache(operation_id, org.id)
        merged = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
        for r in merged:
            if r["block_type"] == block_type:
                return _block_out_from_merged_row(r)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Resolved block missing")

    if org_row is not None:
        await _purge_archived_org_block(db, operation_id=operation_id, block_type=block_type, org_id=org.id)
        org_row.status = "archived"

    next_version = max(system_row.version, org_row.version if org_row else 0) + 1
    new_row = PromptBlock(
        operation_id=operation_id,
        block_type=block_type,
        org_id=org.id,
        content=body.content,
        version=next_version,
        status="active",
        forked_from_id=system_row.id,
        created_by=None,
    )
    db.add(new_row)
    await db.commit()
    _invalidate_cache(operation_id, org.id)
    merged = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    for r in merged:
        if r["block_type"] == block_type:
            return _block_out_from_merged_row(r)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Resolved block missing")


@router.delete("/{operation_id}/blocks/{block_type}", response_model=PromptBlockOut)
async def delete_prompt_block_override(
    operation_id: str,
    block_type: str,
    db: DbSession,
    org: CurrentOrg,
) -> PromptBlockOut:
    if not get_registry_for_operation(operation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown operation")
    if get_block_meta(operation_id, block_type) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown block type")

    org_row = await _get_org_active_block(db, operation_id=operation_id, block_type=block_type, org_id=org.id)
    if org_row is not None:
        await _purge_archived_org_block(db, operation_id=operation_id, block_type=block_type, org_id=org.id)
        org_row.status = "archived"
        await db.commit()
        _invalidate_cache(operation_id, org.id)

    merged = await resolve_prompt_blocks_with_meta(operation_id, org.id, db)
    for r in merged:
        if r["block_type"] == block_type:
            return _block_out_from_merged_row(r)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Resolved block missing")
