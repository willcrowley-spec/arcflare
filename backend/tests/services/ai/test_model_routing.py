from app.services.ai.operations import get_reasoning_effort, get_structured_mode, resolve_model


def test_recommendation_operations_default_to_cerebras_hosted_models():
    expected = "cerebras/gpt-oss-120b"

    assert resolve_model(operation="recommendations", tier="strong") == expected
    assert resolve_model(operation="recommendations_composite", tier="strong") == expected
    assert resolve_model(operation="agent_opportunity", tier="strong") == expected
    assert resolve_model(operation="agent_opportunity_cross_domain", tier="strong") == expected
    assert resolve_model(operation="agent_design_package", tier="strong") == expected


def test_cerebras_provider_kwargs_are_added_for_litellm_calls():
    from app.services.ai.router import _provider_kwargs_for_model

    kwargs = _provider_kwargs_for_model("cerebras/gpt-oss-120b")

    assert kwargs["api_base"] == "https://api.cerebras.ai/v1"
    assert kwargs["custom_llm_provider"] == "cerebras"
    assert kwargs["extra_headers"]["X-Cerebras-3rd-Party-Integration"] == "litellm"


def test_cross_domain_recommendation_synthesis_uses_low_cerebras_reasoning():
    assert get_reasoning_effort("agent_opportunity_cross_domain") == "low"


def test_upstream_generation_operations_are_cerebras_first():
    expected = "cerebras/gpt-oss-120b"

    for operation in (
        "metadata_enrichment",
        "community_summarization",
        "contextual_retrieval",
        "entity_extraction",
        "process_matching",
        "discovery_v2_domain",
        "discovery_v2_extraction",
        "discovery_v2_verification",
        "discovery_v2_synthesis",
        "org_research_extraction",
        "org_research_verification",
        "org_research_synthesis",
    ):
        assert resolve_model(operation=operation, tier="strong") == expected


def test_discovery_v2_extraction_uses_high_reasoning_cerebras_strict_schema():
    assert resolve_model(operation="discovery_v2_extraction", tier="fast") == "cerebras/gpt-oss-120b"
    assert get_reasoning_effort("discovery_v2_extraction") == "high"
    assert get_structured_mode("discovery_v2_extraction") == "json_schema"


def test_cerebras_schema_size_guard_blocks_oversized_strict_schema():
    from app.services.ai.router import _validate_provider_capabilities

    oversized_schema = {"type": "object", "description": "x" * 5100}

    try:
        _validate_provider_capabilities(
            model="cerebras/gpt-oss-120b",
            operation="oversized_test",
            schema=oversized_schema,
            output_format="json",
        )
    except ValueError as exc:
        assert "schema" in str(exc).lower()
        assert "cerebras" in str(exc).lower()
    else:
        raise AssertionError("expected oversized Cerebras schema to fail")
