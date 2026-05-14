from app.services.recommendations.metadata_bindings import (
    METADATA_BINDING_MODEL_VERSION,
    build_metadata_bindings,
)


def _metadata():
    return {
        "objects": [
            {
                "api_name": "Opportunity",
                "label": "Opportunity",
                "fields": [
                    {"api_name": "StageName", "label": "Stage"},
                    {"api_name": "Amount", "label": "Amount"},
                ],
            },
            {
                "api_name": "Account",
                "label": "Account",
                "fields": [{"api_name": "Name", "label": "Account Name"}],
            },
        ]
    }


def test_process_and_step_touchpoints_create_validated_bindings():
    opportunity = {
        "replaces": [
            {
                "process_id": "proc-1",
                "step_ids": ["step-1"],
            }
        ],
        "data_requirements": ["Opportunity record with all deal fields"],
    }
    processes = [
        {
            "id": "proc-1",
            "name": "Close Deal",
            "system_touchpoints": [{"object_api_name": "Opportunity", "fields": ["StageName"], "operation": "read"}],
            "steps": [
                {
                    "id": "step-1",
                    "name": "Update account",
                    "system_touchpoints": ["Account.Name"],
                }
            ],
        }
    ]

    payload = build_metadata_bindings(
        opportunity,
        process_contexts=processes,
        salesforce_metadata=_metadata(),
    )

    assert payload["schema_version"] == METADATA_BINDING_MODEL_VERSION
    assert {
        (binding["ref_type"], binding["object_api_name"], binding.get("field_api_name"), binding["source"], binding["status"])
        for binding in payload["bindings"]
    } == {
        ("object", "Opportunity", None, "process_touchpoint", "validated"),
        ("field", "Opportunity", "StageName", "process_touchpoint", "validated"),
        ("object", "Account", None, "step_touchpoint", "validated"),
        ("field", "Account", "Name", "step_touchpoint", "validated"),
    }
    assert payload["telemetry"]["bindings_from_process_touchpoints"] == 2
    assert payload["telemetry"]["bindings_from_step_touchpoints"] == 2
    assert payload["telemetry"]["bindings_from_llm_suggestions"] == 0
    assert payload["telemetry"]["unresolved_binding_count"] == 0


def test_llm_suggestions_are_not_promoted_to_validated_dependencies():
    payload = build_metadata_bindings(
        {
            "replaces": [],
            "data_requirements": [
                "Opportunity",
                "Customer Onboarding team roster or queue configuration",
            ],
        },
        process_contexts=[],
        salesforce_metadata=_metadata(),
    )

    suggested = [b for b in payload["bindings"] if b["source"] == "llm_suggestion"]
    unresolved = payload["unresolved_bindings"]

    assert suggested[0]["object_api_name"] == "Opportunity"
    assert suggested[0]["status"] == "suggested"
    assert suggested[0]["confidence"] < 0.7
    assert unresolved[0]["ref_type"] == "queue"
    assert unresolved[0]["source"] == "llm_suggestion"
    assert payload["telemetry"]["bindings_from_llm_suggestions"] == 1
    assert payload["telemetry"]["unresolved_binding_count"] == 1


def test_unknown_process_touchpoints_become_unresolved_not_guessed():
    payload = build_metadata_bindings(
        {"replaces": [{"process_id": "proc-1", "step_ids": []}], "data_requirements": []},
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Legacy process",
                "system_touchpoints": [{"object_api_name": "Legacy_Workflow__c", "fields": ["Status__c"]}],
                "steps": [],
            }
        ],
        salesforce_metadata=_metadata(),
    )

    assert payload["bindings"] == []
    assert payload["unresolved_bindings"][0]["object_api_name"] == "Legacy_Workflow__c"
    assert payload["unresolved_bindings"][0]["reason"] == "unknown_object"
    assert payload["telemetry"]["unresolved_binding_count"] == 1


def test_field_touchpoints_require_field_inventory_before_validation():
    payload = build_metadata_bindings(
        {"replaces": [{"process_id": "proc-1", "step_ids": []}], "data_requirements": []},
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Close Deal",
                "system_touchpoints": ["Opportunity.StageName"],
                "steps": [],
            }
        ],
        salesforce_metadata={"objects": [{"api_name": "Opportunity", "label": "Opportunity", "fields": []}]},
    )

    assert [b for b in payload["bindings"] if b["ref_type"] == "object"]
    assert payload["unresolved_bindings"][0]["field_api_name"] == "StageName"
    assert payload["unresolved_bindings"][0]["reason"] == "field_inventory_missing"
