"""Phase 1 skeleton: DSPy prompt optimization infrastructure (Celery).

TODO: Extract real training examples from Langfuse traces per operation.
TODO: Register operation-specific dspy.Signature classes and wire optimizers
      (MIPROv2, BootstrapFewShot) with production metrics.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import dspy
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import engine
from app.models.prompt import PromptBlock, PromptOptimizationRun
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class ChatResponseSignature(dspy.Signature):
    """Generate a structured JSON response for process discovery."""

    user_message: str = dspy.InputField()
    context: str = dspy.InputField()
    response: str = dspy.OutputField(desc="Valid JSON matching the Arc response schema")


def json_parse_metric(example, prediction, trace=None):
    """Check if the prediction is valid JSON."""
    try:
        json.loads(prediction.response)
        return 1.0
    except (json.JSONDecodeError, AttributeError):
        return 0.0


async def _get_system_default_block(
    session,
    *,
    operation_id: str,
    block_type: str,
) -> PromptBlock | None:
    result = await session.execute(
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


async def _get_existing_system_draft(
    session,
    *,
    operation_id: str,
    block_type: str,
) -> PromptBlock | None:
    result = await session.execute(
        select(PromptBlock).where(
            and_(
                PromptBlock.operation_id == operation_id,
                PromptBlock.block_type == block_type,
                PromptBlock.org_id.is_(None),
                PromptBlock.status == "draft",
            )
        )
    )
    return result.scalar_one_or_none()


async def _run_prompt_optimization_async(
    *,
    operation_id: str,
    block_type: str,
    optimizer_name: str,
    metric_name: str,
) -> str:
    if optimizer_name not in ("miprov2", "bootstrap_few_shot"):
        raise ValueError(f"Unsupported optimizer_name: {optimizer_name!r}")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id: UUID | None = None

    async with factory() as session:
        run = PromptOptimizationRun(
            operation_id=operation_id,
            block_type=block_type,
            optimizer=optimizer_name,
            metric_name=metric_name,
            status="running",
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        await session.commit()

    try:
        async with factory() as session:
            system_block = await _get_system_default_block(
                session, operation_id=operation_id, block_type=block_type
            )
            if system_block is None:
                raise ValueError("No active system default prompt block for operation/block_type")

            # TODO: Pull labeled or scored traces from Langfuse for (operation_id, block_type).
            # TODO: Instantiate DSPy optimizer from optimizer_name and run compile/train loop
            #       against the correct Signature for this operation (ChatResponseSignature is
            #       only an example for chat-style JSON outputs).
            _ = metric_name  # reserved for metric binding in Phase 2

            baseline_prediction = SimpleNamespace(response=system_block.content[:2048])
            baseline_example = SimpleNamespace(user_message="", context="")
            metric_score_before = json_parse_metric(baseline_example, baseline_prediction)

            optimized_content = system_block.content

            draft = await _get_existing_system_draft(
                session, operation_id=operation_id, block_type=block_type
            )
            if draft is not None:
                draft.content = optimized_content
                draft.version = max(draft.version, system_block.version) + 1
                draft.forked_from_id = system_block.id
                draft.updated_at = datetime.now(timezone.utc)
                result_block = draft
            else:
                result_block = PromptBlock(
                    operation_id=operation_id,
                    block_type=block_type,
                    org_id=None,
                    content=optimized_content,
                    version=system_block.version + 1,
                    status="draft",
                    forked_from_id=system_block.id,
                    created_by=None,
                )
                session.add(result_block)
                await session.flush()

            placeholder_prediction = SimpleNamespace(response='{"ok": true}')
            metric_score_after = json_parse_metric(baseline_example, placeholder_prediction)

            run_row = await session.get(PromptOptimizationRun, run_id)
            if run_row is None:
                raise RuntimeError("PromptOptimizationRun missing after create")
            run_row.metric_score_before = metric_score_before
            run_row.metric_score_after = metric_score_after
            run_row.result_block_id = result_block.id
            run_row.status = "completed"
            run_row.completed_at = datetime.now(timezone.utc)
            await session.commit()
        return str(run_id)
    except Exception:
        logger.exception(
            "Prompt optimization failed (operation_id=%s block_type=%s run_id=%s)",
            operation_id,
            block_type,
            run_id,
        )
        if run_id is not None:
            async with factory() as session:
                run_row = await session.get(PromptOptimizationRun, run_id)
                if run_row is not None:
                    run_row.status = "failed"
                    run_row.completed_at = datetime.now(timezone.utc)
                    await session.commit()
        raise


@celery_app.task(name="prompts.run_prompt_optimization")
def run_prompt_optimization(
    operation_id: str,
    block_type: str,
    optimizer_name: str,
    metric_name: str,
) -> str:
    """Celery entrypoint: optimize a system prompt block using DSPy (Phase 1: wiring only)."""
    return asyncio.run(
        _run_prompt_optimization_async(
            operation_id=operation_id,
            block_type=block_type,
            optimizer_name=optimizer_name,
            metric_name=metric_name,
        )
    )
