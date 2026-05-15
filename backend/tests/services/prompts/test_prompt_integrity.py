from uuid import uuid4

import pytest

from app.services.prompts.registry import get_registry_for_operation
from app.services.prompts.resolver import MissingPromptBlockError, resolve_prompt_blocks
from app.services.prompts.seeds import SEED_BLOCKS


REQUIRED_AGENT_PROMPT_OPERATIONS = {
    "agent_opportunity": {"instructions", "protocol"},
    "agent_opportunity_cross_domain": {"instructions", "protocol"},
    "agent_design_package": {"instructions", "protocol"},
}


class _EmptyScalarResult:
    def all(self):
        return []


class _EmptyExecuteResult:
    def scalars(self):
        return _EmptyScalarResult()


class _EmptyDb:
    async def execute(self, _stmt):
        return _EmptyExecuteResult()


def test_agent_prompt_operations_are_registered():
    for operation_id, block_types in REQUIRED_AGENT_PROMPT_OPERATIONS.items():
        registry = get_registry_for_operation(operation_id)
        assert registry is not None
        assert {row["type"] for row in registry} == block_types


def test_agent_prompt_operations_have_seed_blocks():
    seed_pairs = {(row["operation_id"], row["block_type"]) for row in SEED_BLOCKS}
    for operation_id, block_types in REQUIRED_AGENT_PROMPT_OPERATIONS.items():
        for block_type in block_types:
            assert (operation_id, block_type) in seed_pairs


@pytest.mark.asyncio
async def test_required_agent_prompt_blocks_fail_closed_when_store_is_empty():
    with pytest.raises(MissingPromptBlockError):
        await resolve_prompt_blocks("agent_opportunity", uuid4(), _EmptyDb())
