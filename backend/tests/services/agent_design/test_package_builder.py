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


def test_build_design_package_grounds_standard_crm_business_phrases():
    context = {
        "recommendation": {
            "id": "rec_2",
            "title": "Closed-Won Onboarding Handoff Agent",
            "description": "Prepare onboarding after closed won.",
            "agent_opportunity": {
                "agent_name": "Closed-Won Onboarding Handoff Agent",
                "agent_type": "hybrid",
                "topics": [
                    {
                        "topic_name": "Closed-Won Detection and Handoff Initiation",
                        "description": "Monitors Opportunity stage transitions.",
                        "reasoning_type": "deterministic",
                        "actions_needed": [
                            "Validate Opportunity is in Closed Won status with required fields complete",
                            "Write handoff initiated timestamp and status to Opportunity record",
                        ],
                    },
                    {
                        "topic_name": "Onboarding Package Assembly",
                        "description": "Compiles account, contact, and product details.",
                        "reasoning_type": "agentic",
                        "actions_needed": ["Retrieve Opportunity Account Contact and Product records"],
                    },
                ],
                "data_requirements": [
                    "Opportunity record with all deal fields",
                    "Associated Account and Contact records",
                    "Purchased product and pricing information",
                    "Customer Onboarding team roster or queue configuration",
                ],
            },
        },
        "salesforce_metadata": {
            "objects": [
                {"api_name": "Opportunity", "label": "Opportunity"},
                {"api_name": "Account", "label": "Account"},
                {"api_name": "Contact", "label": "Contact"},
                {"api_name": "Product2", "label": "Product"},
                {"api_name": "PricebookEntry", "label": "Price Book Entry"},
            ],
        },
    }

    package = build_design_package_from_context(context)
    mapped = {(row["raw"], row["api_name"]) for row in package["metadata_grounding"]["mapped"]}
    unresolved = {row["raw"] for row in package["metadata_grounding"]["unresolved"]}
    permission_objects = {p["object"] for p in package["permission_requirements"]}

    assert ("Opportunity record with all deal fields", "Opportunity") in mapped
    assert ("Associated Account and Contact records", "Account") in mapped
    assert ("Associated Account and Contact records", "Contact") in mapped
    assert ("Purchased product and pricing information", "Product2") in mapped
    assert ("Purchased product and pricing information", "PricebookEntry") in mapped
    assert "Customer Onboarding team roster or queue configuration" in unresolved
    assert {"Opportunity", "Account", "Contact", "Product2", "PricebookEntry"}.issubset(permission_objects)
    assert "Opportunity" in package["action_contracts"][0]["salesforce_objects"]
    assert "Opportunity" in package["action_contracts"][1]["salesforce_objects"]
    assert {"Opportunity", "Account", "Contact", "Product2"}.issubset(
        set(package["action_contracts"][2]["salesforce_objects"])
    )
