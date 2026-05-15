from app.services.ai.operations import get_reasoning_effort, resolve_model


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
