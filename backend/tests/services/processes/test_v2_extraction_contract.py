from app.services.ai.response_schemas import DISCOVERY_V2_EXTRACTION_SCHEMA
from app.services.prompts.seeds import (
    _DISCOVERY_V2_EXTRACTION_INSTRUCTIONS,
    _DISCOVERY_V2_EXTRACTION_PROTOCOL,
)


def test_v2_touchpoint_schema_carries_field_evidence():
    touchpoint_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["properties"]["processes"]["items"]["properties"][
        "system_touchpoints"
    ]["items"]
    child_touchpoint_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["properties"]["processes"]["items"]["properties"][
        "children"
    ]["items"]["properties"]["system_touchpoints"]["items"]

    assert "fields" in touchpoint_schema["properties"]
    assert "fields" in child_touchpoint_schema["properties"]


def test_v2_extraction_requires_child_steps():
    process_schema = DISCOVERY_V2_EXTRACTION_SCHEMA["properties"]["processes"]["items"]

    assert "children" in process_schema["required"]


def test_v2_extraction_prompt_requires_object_field_touchpoints_and_leaf_steps():
    prompt_text = f"{_DISCOVERY_V2_EXTRACTION_INSTRUCTIONS}\n{_DISCOVERY_V2_EXTRACTION_PROTOCOL}"

    assert "Object.Field" in prompt_text
    assert "fields" in prompt_text
    assert "one child step" in prompt_text
