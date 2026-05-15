import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest


ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_analyze_domain_offloads_blocking_llm_call(monkeypatch):
    from app.services.recommendations import agent_analyzer

    async def fake_resolve_prompt_blocks(*args, **kwargs):
        return {"instructions": "Instructions", "protocol": "Protocol"}

    monkeypatch.setattr(agent_analyzer, "resolve_prompt_blocks", fake_resolve_prompt_blocks)

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return SimpleNamespace(text='{"agent_opportunities": [], "uncovered_processes": []}')

    monkeypatch.setattr(agent_analyzer.asyncio, "to_thread", fake_to_thread)

    result = await agent_analyzer.analyze_domain(
        {"domain": {"name": "Sales"}, "processes": []},
        ORG_ID,
        db=object(),
    )

    assert result == {"agent_opportunities": [], "uncovered_processes": []}
    assert calls
    assert calls[0][2]["operation"] == "agent_opportunity"


@pytest.mark.asyncio
async def test_analyze_domain_contexts_runs_with_bounded_parallelism():
    from app.services.recommendations.pipeline import analyze_domain_contexts

    active = 0
    max_active = 0

    async def fake_analyzer(domain_context, org_id, db, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        active -= 1
        return {"agent_opportunities": [], "uncovered_processes": []}

    contexts = [
        {"domain": {"name": f"Domain {idx}"}, "_domain_db_id": f"domain-{idx}"}
        for idx in range(5)
    ]

    results = await analyze_domain_contexts(
        contexts,
        org_id=ORG_ID,
        db=object(),
        prompt_blocks={"instructions": "Instructions", "protocol": "Protocol"},
        concurrency=2,
        analyzer=fake_analyzer,
    )

    assert len(results) == 5
    assert max_active == 2
    assert [row["_domain_name"] for row in results] == [f"Domain {idx}" for idx in range(5)]
