from app.services.agent_design.source_compiler import compile_source_bundle


def _design_package():
    return {
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
        "session_variables": [{"name": "caseId", "type": "Id", "description": "Active Case Id"}],
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


def test_compile_source_bundle_emits_expected_salesforce_project_files():
    bundle = compile_source_bundle(_design_package())
    paths = {f["path"]: f for f in bundle["files"]}

    assert bundle["schema_version"] == "agent_source_bundle_v1"
    assert "sfdx-project.json" in paths
    assert "manifest/package.xml" in paths
    assert "config/project-scratch-def.json" in paths
    assert "force-app/main/default/aiAuthoringBundles/CaseIntakeAgent/CaseIntakeAgent.agent" in paths
    assert "force-app/main/default/classes/ClassifyCaseAction.cls" in paths
    assert "force-app/main/default/classes/ClassifyCaseAction.cls-meta.xml" in paths
    assert "force-app/main/default/classes/ClassifyCaseActionTest.cls" in paths
    assert "force-app/main/default/classes/ClassifyCaseActionTest.cls-meta.xml" in paths
    assert "force-app/main/default/permissionsets/CaseIntakeAgent.permissionset-meta.xml" in paths
    assert "README.md" in paths


def test_compile_source_bundle_apex_uses_safe_defaults_and_contract_io():
    bundle = compile_source_bundle(_design_package())
    apex = next(f for f in bundle["files"] if f["path"].endswith("ClassifyCaseAction.cls"))

    assert "public with sharing class ClassifyCaseAction" in apex["content"]
    assert "@InvocableMethod" in apex["content"]
    assert "@InvocableVariable(required=true)" in apex["content"]
    assert "public Id caseId;" in apex["content"]
    assert "public String classification;" in apex["content"]
    assert "Security.stripInaccessible" in apex["content"]
    assert "TODO" in apex["content"]


def test_compile_source_bundle_is_deterministic():
    first = compile_source_bundle(_design_package())
    second = compile_source_bundle(_design_package())

    assert first == second
