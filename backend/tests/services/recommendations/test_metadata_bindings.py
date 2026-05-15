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
        ],
        "automations": [
            {
                "api_name": "Opportunity_Before_Create_Update",
                "type": "flow",
                "label": "Opportunity Before Create Update",
                "related_object": "Opportunity",
                "status": "Active",
            }
        ],
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


def test_data_requirements_are_display_copy_not_dependencies():
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

    assert payload["bindings"] == []
    assert payload["advisory_bindings"] == []
    assert payload["unresolved_bindings"] == []
    assert payload["quality_gates"]["agent_ready"] is True
    assert payload["telemetry"]["bindings_from_llm_suggestions"] == 0
    assert payload["telemetry"]["unresolved_binding_count"] == 0


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


def test_process_touchpoint_name_type_object_shape_creates_validated_object_binding():
    payload = build_metadata_bindings(
        {"replaces": [{"process_id": "proc-1", "step_ids": []}], "data_requirements": []},
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Invoice readiness",
                "system_touchpoints": [{"name": "Opportunity", "type": "object", "operation": "trigger"}],
                "steps": [],
            }
        ],
        salesforce_metadata={"objects": [{"api_name": "Opportunity", "label": "Opportunity", "fields": []}]},
    )

    assert payload["bindings"][0]["object_api_name"] == "Opportunity"
    assert payload["bindings"][0]["operation"] == "trigger"
    assert payload["unresolved_bindings"] == []


def test_touchpoint_normalizes_implicit_suffix_and_uses_readable_raw_value():
    payload = build_metadata_bindings(
        {"replaces": [{"process_id": "proc-1", "step_ids": []}], "data_requirements": []},
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Skill validation",
                "system_touchpoints": [
                    {
                        "name": "User_Skill__c (implicit)",
                        "type": "object",
                        "fields": ["Name"],
                        "operation": "read",
                    }
                ],
                "steps": [],
            }
        ],
        salesforce_metadata={
            "objects": [
                {
                    "api_name": "User_Skill__c",
                    "label": "User Skill",
                    "fields": [{"api_name": "Name", "label": "User Skill Name"}],
                }
            ]
        },
    )

    assert {
        (binding["ref_type"], binding["api_name"], binding.get("field_api_name"))
        for binding in payload["bindings"]
    } == {
        ("object", "User_Skill__c", None),
        ("field", "User_Skill__c.Name", "Name"),
    }
    assert payload["bindings"][0]["raw_value"] == "User_Skill__c"
    assert payload["unresolved_bindings"] == []


def test_typed_automation_touchpoints_create_validated_flow_bindings():
    payload = build_metadata_bindings(
        {
            "replaces": [{"process_id": "proc-1", "step_ids": []}],
            "data_requirements": ["Opportunity record with all deal fields"],
            "suggested_metadata_refs": [
                {
                    "ref_type": "flow",
                    "raw_value": "Opportunity_Before_Create_Update",
                    "object_api_name": "",
                    "operation": "execute",
                }
            ],
        },
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Closed-Won handoff",
                "system_touchpoints": [
                    {"name": "Opportunity", "type": "object", "operation": "write"},
                    {
                        "name": "Opportunity_Before_Create_Update",
                        "type": "automation",
                        "operation": "trigger",
                    },
                ],
                "steps": [],
            }
        ],
        salesforce_metadata=_metadata(),
    )

    assert payload["schema_version"] == "metadata_binding_manifest_v1"
    assert {
        (binding["ref_type"], binding["api_name"], binding["status"], binding["source"])
        for binding in payload["bindings"]
    } == {
        ("object", "Opportunity", "validated", "process_touchpoint"),
        ("flow", "Opportunity_Before_Create_Update", "validated", "process_touchpoint"),
    }
    assert payload["unresolved_bindings"] == []
    assert payload["advisory_bindings"] == []
    assert payload["quality_gates"]["agent_ready"] is True


def test_duplicate_llm_suggestions_and_data_requirements_do_not_create_blockers():
    payload = build_metadata_bindings(
        {
            "replaces": [{"process_id": "proc-1", "step_ids": []}],
            "data_requirements": [
                "Opportunity record with all deal fields",
                "Customer onboarding queue configuration",
            ],
            "suggested_metadata_refs": [
                {
                    "ref_type": "object",
                    "raw_value": "Opportunity record",
                    "object_api_name": "Opportunity",
                    "operation": "read",
                },
                {
                    "ref_type": "flow",
                    "raw_value": "Opportunity_Before_Create_Update",
                    "object_api_name": "",
                    "operation": "execute",
                },
            ],
        },
        process_contexts=[
            {
                "id": "proc-1",
                "name": "Closed-Won handoff",
                "system_touchpoints": [
                    {"name": "Opportunity", "type": "object", "operation": "write"},
                    {
                        "name": "Opportunity_Before_Create_Update",
                        "type": "automation",
                        "operation": "trigger",
                    },
                ],
                "steps": [],
            }
        ],
        salesforce_metadata=_metadata(),
    )

    assert payload["unresolved_bindings"] == []
    assert payload["advisory_bindings"] == []
    assert payload["quality_gates"]["missing_evidence"] == []
