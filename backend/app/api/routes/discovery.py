"""API routes for process discovery pipeline."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentOrg, DbSession
from app.models.discovery import DiscoveryRun, ProcessHandoff
from app.models.process import BusinessProcess
from app.schemas.discovery import DiscoveryRunResponse, DiscoveryStatusResponse, ProcessHandoffResponse
from app.services.sync_progress import get_redis_client

router = APIRouter()


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(db: DbSession, org: CurrentOrg) -> dict:
    from app.workers.process_discovery import process_discovery_task

    process_discovery_task.delay(str(org.id))
    return {"status": "accepted"}


STALE_RUNNING_TTL_SECONDS = 600


@router.get("/status")
async def discovery_status(org: CurrentOrg) -> DiscoveryStatusResponse:
    r = get_redis_client()
    run_key = f"discovery:{org.id}"
    raw = r.hgetall(run_key)
    if not raw:
        return DiscoveryStatusResponse(
            run_id=None,
            status="idle",
            phases={},
            started_at=None,
            completed_at=None,
            error=None,
        )
    data = {
        k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
        for k, v in raw.items()
    }

    status = data.get("status", "idle")

    if status == "running":
        ttl = r.ttl(run_key)
        # Keys are set with 3600s TTL; if <2400s remain, it's been running >10min — stale
        if isinstance(ttl, int) and 0 < ttl < (3600 - STALE_RUNNING_TTL_SECONDS):
            status = "failed"
            r.hset(run_key, "status", "failed")
            r.hset(run_key, "error", "Pipeline timed out (no updates for 10+ minutes)")

    phases: dict = {}
    for phase_key, val in data.items():
        if phase_key.startswith("phase:"):
            parts = phase_key.split(":")
            if len(parts) == 3:
                phase_name, field = parts[1], parts[2]
                phases.setdefault(phase_name, {})
                phases[phase_name][field] = int(val) if field in ("count", "total") else val
    return DiscoveryStatusResponse(
        run_id=data.get("run_id") or None,
        status=status,
        phases=phases,
        started_at=None,
        completed_at=None,
        error=data.get("error"),
    )


@router.post("/reset")
async def reset_discovery_status(org: CurrentOrg) -> dict:
    """Clear stuck discovery state from Redis."""
    r = get_redis_client()
    run_key = f"discovery:{org.id}"
    r.delete(run_key)
    return {"status": "reset"}


@router.get("/runs", response_model=list[DiscoveryRunResponse])
async def list_runs(db: DbSession, org: CurrentOrg) -> list[DiscoveryRunResponse]:
    q = await db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.org_id == org.id)
        .order_by(DiscoveryRun.started_at.desc())
        .limit(10)
    )
    return [DiscoveryRunResponse.model_validate(r) for r in q.scalars().all()]


@router.get("/handoffs", response_model=list[ProcessHandoffResponse])
async def list_handoffs(db: DbSession, org: CurrentOrg) -> list[ProcessHandoffResponse]:
    q = await db.execute(select(ProcessHandoff).where(ProcessHandoff.org_id == org.id))
    return [ProcessHandoffResponse.model_validate(h) for h in q.scalars().all()]


@router.post("/{process_id}/confirm")
async def confirm_process(process_id: UUID, db: DbSession, org: CurrentOrg) -> dict:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    proc.status = "confirmed"
    await db.commit()
    return {"status": "confirmed"}


@router.post("/{process_id}/reject")
async def reject_process(process_id: UUID, db: DbSession, org: CurrentOrg) -> dict:
    proc = await db.get(BusinessProcess, process_id)
    if proc is None or proc.org_id != org.id:
        raise HTTPException(status_code=404, detail="Process not found")
    proc.status = "rejected"
    await db.commit()
    return {"status": "rejected"}
