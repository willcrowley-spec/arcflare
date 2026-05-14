from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_design import (
    AgentDesignPackage,
    AgentGenerationRun,
    AgentSourceBundle,
    ScratchValidationRun,
)
from app.models.metadata import MetadataObject
from app.models.recommendation import Recommendation
from app.services.agent_design.context_assembler import assemble_generation_context
from app.services.agent_design.package_builder import build_design_package_from_context
from app.services.agent_design.source_compiler import compile_source_bundle
from app.services.agent_design.validators import validate_design_package


async def _known_objects(db: AsyncSession, org_id: UUID) -> set[str]:
    q = await db.execute(select(MetadataObject.api_name).where(MetadataObject.org_id == org_id))
    return {str(row[0]) for row in q.all() if row[0]}


async def create_generation_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    recommendation_id: UUID,
) -> AgentGenerationRun:
    rec = await db.get(Recommendation, recommendation_id)
    if rec is None or rec.org_id != org_id:
        raise ValueError("recommendation_not_found")

    run = AgentGenerationRun(
        org_id=org_id,
        recommendation_id=recommendation_id,
        status="assembling_context",
        current_stage="scope",
        model_json={
            "design_synthesis": {
                "method": "deterministic_package_builder_v1",
                "future_operation": "agent_design_package",
            },
            "source_compiler": "agentforce_source_compiler_v1",
        },
        stage_results={},
    )
    db.add(run)
    await db.flush()

    context = await assemble_generation_context(db, org_id=org_id, recommendation=rec)
    package_json = build_design_package_from_context(context)
    validation = validate_design_package(package_json, known_salesforce_objects=await _known_objects(db, org_id))
    design_status = "blocked" if validation["blockers"] else "draft"

    design = AgentDesignPackage(
        org_id=org_id,
        generation_run_id=run.id,
        recommendation_id=recommendation_id,
        status=design_status,
        package_json=package_json,
        validation_json=validation,
    )
    db.add(design)

    run.status = "blocked" if validation["blockers"] else "awaiting_review"
    run.current_stage = "design"
    run.stage_results = {
        "scope": {
            "process_count": len(context.get("processes") or []),
            "metadata_object_count": len((context.get("salesforce_metadata") or {}).get("objects") or []),
        },
        "design": {
            "status": design_status,
            "blockers": validation["blockers"],
            "warnings": validation["warnings"],
        },
    }
    await db.commit()
    await db.refresh(run)
    return run


async def regenerate_design_package(
    db: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
) -> AgentGenerationRun:
    run = await db.get(AgentGenerationRun, run_id)
    if run is None or run.org_id != org_id:
        raise ValueError("generation_run_not_found")

    latest_design = (
        await db.execute(
            select(AgentDesignPackage)
            .where(
                AgentDesignPackage.generation_run_id == run.id,
                AgentDesignPackage.org_id == org_id,
            )
            .order_by(AgentDesignPackage.version.desc(), AgentDesignPackage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_design is None:
        raise ValueError("design_package_not_found")
    if latest_design.status not in {"draft", "blocked"}:
        raise ValueError("design_package_not_repairable")

    existing_source = (
        await db.execute(
            select(AgentSourceBundle)
            .where(
                AgentSourceBundle.generation_run_id == run.id,
                AgentSourceBundle.org_id == org_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_source is not None:
        raise ValueError("design_package_not_repairable")

    rec = await db.get(Recommendation, run.recommendation_id)
    if rec is None or rec.org_id != org_id:
        raise ValueError("recommendation_not_found")

    context = await assemble_generation_context(db, org_id=org_id, recommendation=rec)
    package_json = build_design_package_from_context(context)
    validation = validate_design_package(package_json, known_salesforce_objects=await _known_objects(db, org_id))
    design_status = "blocked" if validation["blockers"] else "draft"

    latest_design.status = "superseded"
    design = AgentDesignPackage(
        org_id=org_id,
        generation_run_id=run.id,
        recommendation_id=run.recommendation_id,
        version=int(latest_design.version or 1) + 1,
        status=design_status,
        package_json=package_json,
        validation_json=validation,
    )
    db.add(design)

    run.status = "blocked" if validation["blockers"] else "awaiting_review"
    run.current_stage = "design"
    stage = dict(getattr(run, "stage_results", None) or {})
    stage["design"] = {
        "status": design_status,
        "blockers": validation["blockers"],
        "warnings": validation["warnings"],
        "version": design.version,
        "regenerated_from_version": latest_design.version,
    }
    run.stage_results = stage
    run.error = None
    await db.commit()
    await db.refresh(run)
    return run


async def approve_design_package(
    db: AsyncSession,
    *,
    org_id: UUID,
    design_package_id: UUID,
) -> AgentDesignPackage:
    design = await db.get(AgentDesignPackage, design_package_id)
    if design is None or design.org_id != org_id:
        raise ValueError("design_package_not_found")
    blockers = (design.validation_json or {}).get("blockers") or []
    if blockers:
        raise ValueError("design_package_has_blockers")
    design.status = "approved"
    design.approved_at = datetime.now(tz=UTC)
    run = await db.get(AgentGenerationRun, design.generation_run_id)
    if run is not None:
        run.status = "design_approved"
        run.current_stage = "source"
        stage = dict(run.stage_results or {})
        stage["approval"] = {"approved_at": design.approved_at.isoformat()}
        run.stage_results = stage
    await db.commit()
    await db.refresh(design)
    return design


async def generate_source_bundle(
    db: AsyncSession,
    *,
    org_id: UUID,
    design_package_id: UUID,
) -> AgentSourceBundle:
    design = await db.get(AgentDesignPackage, design_package_id)
    if design is None or design.org_id != org_id:
        raise ValueError("design_package_not_found")
    if design.status != "approved":
        raise ValueError("design_package_not_approved")

    source_tree = compile_source_bundle(design.package_json or {})
    bundle = AgentSourceBundle(
        org_id=org_id,
        generation_run_id=design.generation_run_id,
        design_package_id=design.id,
        status="generated",
        source_tree_json=source_tree,
        checks_json=source_tree.get("checks") or {},
    )
    db.add(bundle)
    design.status = "source_generated"
    run = await db.get(AgentGenerationRun, design.generation_run_id)
    if run is not None:
        run.status = "source_generated"
        run.current_stage = "validation"
        stage = dict(run.stage_results or {})
        stage["source"] = {
            "status": "generated",
            "file_count": len(source_tree.get("files") or []),
            "bundle_name": source_tree.get("bundle_name"),
        }
        run.stage_results = stage
    await db.commit()
    await db.refresh(bundle)
    return bundle


async def create_validation_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    source_bundle_id: UUID,
) -> ScratchValidationRun:
    source = await db.get(AgentSourceBundle, source_bundle_id)
    if source is None or source.org_id != org_id:
        raise ValueError("source_bundle_not_found")

    settings = get_settings()
    enabled = bool(settings.AGENTFORCE_SCRATCH_VALIDATION_ENABLED)
    status = "queued" if enabled else "blocked"
    error = None if enabled else "Scratch org validation is disabled. Set AGENTFORCE_SCRATCH_VALIDATION_ENABLED=true on the worker."
    validation = ScratchValidationRun(
        org_id=org_id,
        source_bundle_id=source_bundle_id,
        status=status,
        devhub_alias=settings.SALESFORCE_DEV_HUB_ALIAS,
        error=error,
        logs_json=[] if enabled else [{"level": "info", "message": error}],
        result_json={"feature_flag_enabled": enabled},
        completed_at=None if enabled else datetime.now(tz=UTC),
    )
    db.add(validation)
    await db.commit()
    await db.refresh(validation)

    if enabled:
        from app.workers.agent_generation import validate_agent_source_bundle_task

        validate_agent_source_bundle_task.delay(str(validation.id))
    return validation
