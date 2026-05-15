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


def test_compile_source_bundle_groups_action_artifacts_and_uses_exact_manifest_members():
    bundle = compile_source_bundle(_design_package())
    paths = {f["path"]: f for f in bundle["files"]}
    groups = {g["id"]: g for g in bundle["artifact_groups"]}
    action_group = groups["action:ClassifyCase"]

    assert action_group["display_name"] == "Classify Case"
    assert action_group["common_name"] == "Classify Case"
    assert action_group["kind"] == "action_contract"
    assert action_group["target_name"] == "ClassifyCaseAction"
    assert action_group["files"]["apex_class"].endswith("ClassifyCaseAction.cls")
    assert action_group["files"]["apex_meta"].endswith("ClassifyCaseAction.cls-meta.xml")
    assert action_group["files"]["apex_test"].endswith("ClassifyCaseActionTest.cls")
    assert action_group["files"]["apex_test_meta"].endswith("ClassifyCaseActionTest.cls-meta.xml")

    package_xml = paths["manifest/package.xml"]["content"]
    assert "<members>ClassifyCaseAction</members>" in package_xml
    assert "<members>ClassifyCaseActionTest</members>" in package_xml
    assert "<members>CaseIntakeAgent</members>" in package_xml
    assert "<members>*</members>" not in package_xml


def test_compile_source_bundle_is_deterministic():
    first = compile_source_bundle(_design_package())
    second = compile_source_bundle(_design_package())

    assert first == second


def test_compile_source_bundle_emits_bounded_apex_for_field_grounded_actions():
    design = _design_package()
    action = design["action_contracts"][0]
    action.update(
        {
            "capability_type": "read_context",
            "implementation_status": "bounded_candidate",
            "apex_generation_mode": "bounded_apex",
            "read_fields": [
                {"object_api_name": "Case", "field_api_name": "Subject"},
                {"object_api_name": "Case", "field_api_name": "Priority"},
            ],
            "write_fields": [],
            "field_bindings": [
                {"object_api_name": "Case", "field_api_name": "Subject", "operation": "read"},
                {"object_api_name": "Case", "field_api_name": "Priority", "operation": "read"},
            ],
            "quality_warnings": [],
        }
    )
    action["inputs"] = [{"name": "caseId", "type": "Id", "required": True, "object": "Case"}]
    action["outputs"] = [
        {"name": "contextJson", "type": "String", "required": True},
        {"name": "status", "type": "String", "required": True},
    ]

    bundle = compile_source_bundle(design)
    paths = {f["path"]: f for f in bundle["files"]}
    apex = paths["force-app/main/default/classes/ClassifyCaseAction.cls"]["content"]
    permset = paths["force-app/main/default/permissionsets/CaseIntakeAgent.permissionset-meta.xml"]["content"]
    group = next(g for g in bundle["artifact_groups"] if g["id"] == "action:ClassifyCase")

    assert "SELECT Id, Priority, Subject" in apex
    assert "FROM Case" in apex
    assert "WITH USER_MODE" in apex
    assert "objectType.getDescribe().isAccessible()" in apex
    assert "try {" in apex
    assert "catch (Exception ex)" in apex
    assert "JSON.serialize(record)" in apex
    assert "<field>Case.Priority</field>" in permset
    assert "<field>Case.Subject</field>" in permset
    assert group["quality"]["implementation_status"] == "bounded_candidate"
    assert group["quality"]["apex_generation_mode"] == "bounded_apex"
    assert bundle["checks"]["implementation_quality"]["bounded_candidate"] == 1


def test_compile_source_bundle_emits_writeback_apex_and_meaningful_test_records():
    design = _design_package()
    action = design["action_contracts"][0]
    action.update(
        {
            "name": "ApplyCaseDecision",
            "target_name": "ApplyCaseDecisionAction",
            "common_name": "Apply Case decision",
            "capability_type": "writeback",
            "implementation_status": "bounded_candidate",
            "apex_generation_mode": "bounded_apex",
            "read_fields": [],
            "write_fields": [{"object_api_name": "Case", "field_api_name": "Priority"}],
            "field_bindings": [{"object_api_name": "Case", "field_api_name": "Priority", "operation": "update"}],
            "permissions": ["Case:read", "Case:update"],
            "quality_warnings": [],
            "inputs": [
                {"name": "caseId", "type": "Id", "required": True, "object": "Case"},
                {"name": "priority", "type": "String", "required": False, "object": "Case", "field": "Priority"},
            ],
            "outputs": [{"name": "status", "type": "String", "required": True}],
        }
    )
    design["topics"][0]["actions"] = ["ApplyCaseDecision"]
    design["permission_requirements"] = [
        {
            "object": "Case",
            "operations": ["read", "update"],
            "fields": [{"field_api_name": "Priority", "operations": ["read", "update"]}],
            "reason": "Apply case decisions",
        }
    ]

    bundle = compile_source_bundle(design)
    paths = {f["path"]: f for f in bundle["files"]}
    apex = paths["force-app/main/default/classes/ApplyCaseDecisionAction.cls"]["content"]
    test = paths["force-app/main/default/classes/ApplyCaseDecisionActionTest.cls"]["content"]

    assert "Case record = new Case(Id = request.caseId);" in apex
    assert "record.Priority = request.priority;" in apex
    assert "objectType.getDescribe().isUpdateable()" in apex
    assert "Security.stripInaccessible(AccessType.UPDATABLE" in apex
    assert "Database.update(sanitizedRecords, false, AccessLevel.USER_MODE)" in apex
    assert "insert caseRecord;" in test
    assert "request.caseId = caseRecord.Id;" in test
    assert "System.assertEquals('UPDATED', responses[0].status" in test
