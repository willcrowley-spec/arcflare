from app.services.agent_design.object_resolver import resolve_object_references


OBJECTS = [
    {"api_name": "User_Skill__c", "label": "User Skill"},
    {"api_name": "User_Certification__c", "label": "User Certification"},
    {"api_name": "User", "label": "User"},
]


def _mapped_api(result, raw):
    return next(row["api_name"] for row in result["mapped"] if row["raw"] == raw)


def test_resolves_api_labels_and_record_language_to_salesforce_objects():
    result = resolve_object_references(
        [
            "User_Skill__c",
            "user_skill__c",
            "User Skill",
            "User Skill records",
            "User Skill c records",
            "User Certification records",
        ],
        OBJECTS,
    )

    assert _mapped_api(result, "User_Skill__c") == "User_Skill__c"
    assert _mapped_api(result, "user_skill__c") == "User_Skill__c"
    assert _mapped_api(result, "User Skill") == "User_Skill__c"
    assert _mapped_api(result, "User Skill records") == "User_Skill__c"
    assert _mapped_api(result, "User Skill c records") == "User_Skill__c"
    assert _mapped_api(result, "User Certification records") == "User_Certification__c"
    assert result["unresolved"] == []


def test_keeps_ambiguous_fuzzy_matches_unresolved():
    result = resolve_object_references(
        ["Policy Re"],
        [
            {"api_name": "Policy_Request__c", "label": "Policy Request"},
            {"api_name": "Policy_Review__c", "label": "Policy Review"},
        ],
    )

    assert result["mapped"] == []
    assert result["unresolved"][0]["raw"] == "Policy Re"
    assert result["unresolved"][0]["status"] == "ambiguous"
