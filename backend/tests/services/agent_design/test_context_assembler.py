from types import SimpleNamespace
from uuid import UUID

from app.services.agent_design.context_assembler import (
    _serialize_metadata_object,
    _serialize_process_contexts,
)


def test_serialize_metadata_object_includes_field_inventory():
    obj = SimpleNamespace(
        api_name="Case",
        label="Case",
        classification="core",
        record_count=12,
        field_count=3,
        fields=[
            SimpleNamespace(api_name="Subject", label="Subject", field_type="string", is_required=False),
            SimpleNamespace(api_name="Priority", label="Priority", field_type="picklist", is_required=False),
        ],
    )

    row = _serialize_metadata_object(obj)

    assert row["api_name"] == "Case"
    assert row["fields"] == [
        {"api_name": "Subject", "label": "Subject", "field_type": "string", "is_required": False},
        {"api_name": "Priority", "label": "Priority", "field_type": "picklist", "is_required": False},
    ]


def test_serialize_process_contexts_filters_process_ids_out_of_step_ids():
    process_id = UUID("00000000-0000-0000-0000-000000000001")
    real_step_id = UUID("00000000-0000-0000-0000-000000000002")
    process = SimpleNamespace(
        id=process_id,
        name="Case Management",
        level="process",
        description="Manage cases",
        actors=[],
        system_touchpoints=[{"object_api_name": "Case", "operation": "read"}],
        decision_logic=[],
        failure_modes=[],
        value_classification="high",
        automation_potential="high",
        confidence_score=0.9,
        evidence_sources=[],
        parent_id=None,
    )
    step = SimpleNamespace(
        id=real_step_id,
        name="Review Case",
        level="step",
        description="Review case fields",
        actors=[],
        system_touchpoints=[{"object_api_name": "Case", "fields": ["Priority"], "operation": "read"}],
        decision_logic=[],
        failure_modes=[],
        value_classification="high",
        automation_potential="high",
        confidence_score=0.9,
        evidence_sources=[],
        parent_id=process_id,
    )

    rows = _serialize_process_contexts(
        [process, step],
        process_ids={str(process_id)},
        step_ids={str(process_id), str(real_step_id)},
    )

    assert rows == [
        {
            "id": str(process_id),
            "name": "Case Management",
            "level": "process",
            "description": "Manage cases",
            "actors": [],
            "system_touchpoints": [{"object_api_name": "Case", "operation": "read"}],
            "decision_logic": [],
            "failure_modes": [],
            "value_classification": "high",
            "automation_potential": "high",
            "confidence_score": 0.9,
            "evidence_sources": [],
            "steps": [
                {
                    "id": str(real_step_id),
                    "name": "Review Case",
                    "level": "step",
                    "description": "Review case fields",
                    "actors": [],
                    "system_touchpoints": [{"object_api_name": "Case", "fields": ["Priority"], "operation": "read"}],
                    "decision_logic": [],
                    "failure_modes": [],
                    "value_classification": "high",
                    "automation_potential": "high",
                    "confidence_score": 0.9,
                    "evidence_sources": [],
                }
            ],
        }
    ]
