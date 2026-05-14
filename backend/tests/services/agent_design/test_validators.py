from app.services.agent_design.validators import validate_design_package


def _package(**overrides):
    pkg = {
        "schema_version": "agent_design_package_v1",
        "agent": {
            "name": "Case Intake Agent",
            "type": "hybrid",
            "summary": "Triages inbound support cases and prepares safe updates.",
            "trigger": "Case created or updated",
        },
        "topics": [
            {
                "name": "Classify inbound case",
                "description": "Classify and enrich routine cases.",
                "reasoning_type": "hybrid",
                "actions": ["ClassifyCase"],
            }
        ],
        "action_contracts": [
            {
                "name": "ClassifyCase",
                "label": "Classify Case",
                "target_type": "apex",
                "description": "Reads Case context and returns a classification proposal.",
                "salesforce_objects": ["Case"],
                "inputs": [{"name": "caseId", "type": "Id", "required": True}],
                "outputs": [{"name": "classification", "type": "String", "required": True}],
                "permissions": ["Case:read", "Case:update"],
                "error_states": ["CASE_NOT_FOUND", "MISSING_ACCESS"],
            }
        ],
        "permission_requirements": [
            {"object": "Case", "operations": ["read", "update"], "reason": "Classify and stage cases"}
        ],
        "test_scenarios": [
            {
                "name": "Classifies a routine case",
                "given": "A new support case exists",
                "when": "The agent runs classification",
                "then": "A classification proposal is returned",
            }
        ],
        "blockers": [],
    }
    pkg.update(overrides)
    return pkg


def test_validator_accepts_grounded_package():
    result = validate_design_package(_package(), known_salesforce_objects={"Case"})

    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["warnings"] == []


def test_validator_blocks_unknown_salesforce_objects():
    result = validate_design_package(
        _package(
            action_contracts=[
                {
                    "name": "SyncPolicy",
                    "target_type": "apex",
                    "description": "Syncs an external policy.",
                    "salesforce_objects": ["Policy__c"],
                    "inputs": [{"name": "policyId", "type": "Id", "required": True}],
                    "outputs": [{"name": "status", "type": "String", "required": True}],
                    "permissions": ["Policy__c:read"],
                }
            ]
        ),
        known_salesforce_objects={"Case"},
    )

    assert result["ok"] is False
    assert "unknown_salesforce_object:Policy__c" in result["blockers"]


def test_validator_blocks_action_contracts_without_io_or_permissions():
    result = validate_design_package(
        _package(
            action_contracts=[
                {
                    "name": "ClassifyCase",
                    "target_type": "apex",
                    "description": "Reads Case context.",
                    "salesforce_objects": ["Case"],
                    "inputs": [],
                    "outputs": [],
                    "permissions": [],
                }
            ],
            permission_requirements=[],
        ),
        known_salesforce_objects={"Case"},
    )

    assert result["ok"] is False
    assert "missing_action_inputs:ClassifyCase" in result["blockers"]
    assert "missing_action_outputs:ClassifyCase" in result["blockers"]
    assert "missing_action_permissions:ClassifyCase" in result["blockers"]
    assert "missing_permission_requirement:Case" in result["blockers"]
