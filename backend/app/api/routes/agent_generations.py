from __future__ import annotations

from io import BytesIO
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentOrg, DbSession
from app.models.agent_design import (
    AgentDesignPackage,
    AgentGenerationRun,
    AgentSourceBundle,
    ScratchValidationRun,
)
from app.schemas.agent_design import (
    AgentDesignPackageResponse,
    AgentGenerationRunResponse,
    AgentSourceBundleResponse,
    ScratchValidationRunResponse,
)
from app.services.agent_design.workflow import (
    approve_design_package,
    create_validation_run,
    generate_source_bundle,
)

router = APIRouter()


async def _latest_generation_response(
    db: DbSession,
    run: AgentGenerationRun,
) -> AgentGenerationRunResponse:
    design = (
        await db.execute(
            select(AgentDesignPackage)
            .where(AgentDesignPackage.generation_run_id == run.id)
            .order_by(AgentDesignPackage.version.desc(), AgentDesignPackage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    source = None
    validations: list[ScratchValidationRun] = []
    if design is not None:
        source = (
            await db.execute(
                select(AgentSourceBundle)
                .where(AgentSourceBundle.design_package_id == design.id)
                .order_by(AgentSourceBundle.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if source is not None:
        validations = list(
            (
                await db.execute(
                    select(ScratchValidationRun)
                    .where(ScratchValidationRun.source_bundle_id == source.id)
                    .order_by(ScratchValidationRun.created_at.desc())
                )
            ).scalars().all()
        )

    base = AgentGenerationRunResponse.model_validate(run)
    return base.model_copy(
        update={
            "design_package": (
                AgentDesignPackageResponse.model_validate(design) if design is not None else None
            ),
            "source_bundle": (
                AgentSourceBundleResponse.model_validate(source) if source is not None else None
            ),
            "validation_runs": [
                ScratchValidationRunResponse.model_validate(row) for row in validations
            ],
        }
    )


@router.post("/design-packages/{design_package_id}/approve", response_model=AgentDesignPackageResponse)
async def approve_agent_design_package(
    design_package_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> AgentDesignPackageResponse:
    try:
        design = await approve_design_package(db, org_id=org.id, design_package_id=design_package_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if detail == "design_package_has_blockers" else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return AgentDesignPackageResponse.model_validate(design)


@router.post("/design-packages/{design_package_id}/generate-source", response_model=AgentSourceBundleResponse)
async def generate_agent_source_bundle(
    design_package_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> AgentSourceBundleResponse:
    try:
        bundle = await generate_source_bundle(db, org_id=org.id, design_package_id=design_package_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if detail == "design_package_not_approved" else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return AgentSourceBundleResponse.model_validate(bundle)


@router.get("/source-bundles/{source_bundle_id}/download")
async def download_agent_source_bundle(
    source_bundle_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> Response:
    bundle = await db.get(AgentSourceBundle, source_bundle_id)
    if bundle is None or bundle.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent source bundle not found")

    source_tree = bundle.source_tree_json or {}
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zf:
        for file in source_tree.get("files") or []:
            if not isinstance(file, dict):
                continue
            path = str(file.get("path") or "").strip()
            if not path:
                continue
            zf.writestr(path, str(file.get("content") or ""))
    archive.seek(0)
    name = source_tree.get("bundle_name") or "arcflare-agent-source"
    return Response(
        content=archive.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.post("/source-bundles/{source_bundle_id}/validate", response_model=ScratchValidationRunResponse)
async def validate_agent_source_bundle(
    source_bundle_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> ScratchValidationRunResponse:
    try:
        validation = await create_validation_run(db, org_id=org.id, source_bundle_id=source_bundle_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScratchValidationRunResponse.model_validate(validation)


@router.get("/{run_id}", response_model=AgentGenerationRunResponse)
async def get_agent_generation(
    run_id: UUID,
    db: DbSession,
    org: CurrentOrg,
) -> AgentGenerationRunResponse:
    run = await db.get(AgentGenerationRun, run_id)
    if run is None or run.org_id != org.id:
        raise HTTPException(status_code=404, detail="Agent generation run not found")
    return await _latest_generation_response(db, run)
