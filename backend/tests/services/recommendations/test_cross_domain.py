from types import SimpleNamespace
from uuid import UUID

import pytest


ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
DISCOVERY_RUN_ID = UUID("00000000-0000-0000-0000-000000000002")


class _FakeScalarResult:
    def all(self):
        return []


class _FakeExecuteResult:
    def scalars(self):
        return _FakeScalarResult()


class _FakeDb:
    async def execute(self, stmt):
        return _FakeExecuteResult()


@pytest.mark.asyncio
async def test_cross_domain_synthesis_allows_final_answer_budget(monkeypatch):
    from app.services.recommendations import cross_domain

    async def fake_resolve_prompt_blocks(*args, **kwargs):
        return {"instructions": "Instructions", "protocol": "Protocol"}

    calls = []

    def fake_llm_call(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='{"cross_domain_opportunities": [], "merge_suggestions": []}')

    monkeypatch.setattr(cross_domain, "resolve_prompt_blocks", fake_resolve_prompt_blocks)
    monkeypatch.setattr("app.services.ai.router.llm_call", fake_llm_call)

    results = [
        {
            "_domain_name": "Sales",
            "_processes_raw": [{"id": "process-1"}],
            "agent_opportunities": [
                {
                    "agent_name": "Sales Agent",
                    "agent_type": "headless",
                    "description": "Automates sales work.",
                    "topics": [{"topic_name": "Sales"}],
                    "financial_signals": {},
                    "data_requirements": [],
                    "integration_points": [],
                }
            ],
        },
        {
            "_domain_name": "Support",
            "_processes_raw": [{"id": "process-2"}],
            "agent_opportunities": [
                {
                    "agent_name": "Support Agent",
                    "agent_type": "headless",
                    "description": "Automates support work.",
                    "topics": [{"topic_name": "Support"}],
                    "financial_signals": {},
                    "data_requirements": [],
                    "integration_points": [],
                }
            ],
        },
    ]

    data = await cross_domain.synthesize_cross_domain(
        results,
        ORG_ID,
        DISCOVERY_RUN_ID,
        _FakeDb(),
    )

    assert data == {"cross_domain_opportunities": [], "merge_suggestions": []}
    assert calls
    assert calls[0]["operation"] == "agent_opportunity_cross_domain"
    assert calls[0]["max_tokens"] >= 16000
