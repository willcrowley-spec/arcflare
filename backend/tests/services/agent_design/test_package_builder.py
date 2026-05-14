from app.services.agent_design.package_builder import build_design_package_from_context


def _context(data_requirements):
    return {
        "recommendation": {
            "id": "rec_1",
            "title": "User competency validation",
            "description": "Validate skill and certification records.",
            "agent_opportunity": {
                "agent_name": "User Competency Agent",
                "agent_type": "hybrid",
                "description": "Validates user skill and certification records.",
                "topics": [
                    {
                        "topic_name": "User Skill Record Validation",
                        "description": "Validate required fields and skill references.",
                        "reasoning_type": "deterministic",
                        "actions_needed": [
                            "Read Skill__c record to verify reference",
                            "Validate required fields on User_Skill__c",
                        ],
                    },
                    {
                        "topic_name": "User Certification Record Validation",
                        "description": "Validate certification references and expiration dates.",
                        "reasoning_type": "deterministic",
                        "actions_needed": [
                            "Read Certification__c record to verify reference",
                            "Validate User_Certification__c fields against business rules",
                        ],
                    },
                ],
                "data_requirements": data_requirements,
            },
        },
        "salesforce_metadata": {
            "objects": [
                {"api_name": "User_Skill__c", "label": "User Skill"},
                {"api_name": "User_Certification__c", "label": "User Certification"},
                {"api_name": "User", "label": "User"},
            ],
        },
    }


def test_build_design_package_grounds_topic_actions_to_resolved_objects():
    package = build_design_package_from_context(
        _context(["User Skill c records", "User Certification records"])
    )

    action_objects = {
        action["name"]: action["salesforce_objects"][0]
        for action in package["action_contracts"]
        if action["salesforce_objects"]
    }

    assert action_objects["ReadSkillRecordToVerifyReference"] == "User_Skill__c"
    assert action_objects["ValidateRequiredFieldsOnUserSkill"] == "User_Skill__c"
    assert action_objects["ReadCertificationRecordToVerifyReference"] == "User_Certification__c"
    assert action_objects["ValidateUserCertificationFieldsAgainstBusinessRules"] == "User_Certification__c"
    assert "__c" not in "".join(action_objects)

    permission_objects = {p["object"] for p in package["permission_requirements"]}
    assert permission_objects == {"User_Skill__c", "User_Certification__c"}
    assert package["metadata_grounding"]["unresolved"] == []
    assert not any("unknown_salesforce_object" in b for b in package["blockers"])
    assert not any("missing_permission_requirement" in b for b in package["blockers"])


def test_build_design_package_does_not_pick_arbitrary_object_without_data_requirements():
    package = build_design_package_from_context(_context([]))

    assert package["permission_requirements"] == []
    assert all(action["salesforce_objects"] == [] for action in package["action_contracts"])
    assert package["metadata_grounding"]["mapped"] == []


def test_build_design_package_blocks_unresolved_requirements_without_fake_objects():
    package = build_design_package_from_context(_context(["Legacy workforce planning records"]))

    assert package["metadata_grounding"]["mapped"] == []
    assert package["metadata_grounding"]["unresolved"][0]["raw"] == "Legacy workforce planning records"
    assert all(action["salesforce_objects"] == [] for action in package["action_contracts"])
    assert "unresolved_data_requirement:Legacy workforce planning records" in package["blockers"]
    assert not any("unknown_salesforce_object:Legacy workforce planning records" in b for b in package["blockers"])
