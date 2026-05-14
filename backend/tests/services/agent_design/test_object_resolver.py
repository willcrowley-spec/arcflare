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


def test_resolves_embedded_and_multi_object_business_phrases():
    result = resolve_object_references(
        [
            "Opportunity record with all deal fields",
            "Associated Account and Contact records",
            "Purchased product and pricing information",
            "Contract or agreement metadata",
        ],
        [
            {"api_name": "Opportunity", "label": "Opportunity"},
            {"api_name": "Account", "label": "Account"},
            {"api_name": "Contact", "label": "Contact"},
            {"api_name": "Product2", "label": "Product"},
            {"api_name": "PricebookEntry", "label": "Price Book Entry"},
            {"api_name": "Contract", "label": "Contract"},
        ],
    )

    mapped = {(row["raw"], row["api_name"]) for row in result["mapped"]}

    assert ("Opportunity record with all deal fields", "Opportunity") in mapped
    assert ("Associated Account and Contact records", "Account") in mapped
    assert ("Associated Account and Contact records", "Contact") in mapped
    assert ("Purchased product and pricing information", "Product2") in mapped
    assert ("Purchased product and pricing information", "PricebookEntry") in mapped
    assert ("Contract or agreement metadata", "Contract") in mapped
    assert result["unresolved"] == []


def test_prefers_specific_embedded_object_over_shorter_object_name():
    result = resolve_object_references(
        ["User Skill c records"],
        [
            {"api_name": "User", "label": "User"},
            {"api_name": "User_Skill__c", "label": "User Skill"},
        ],
    )

    assert [(row["raw"], row["api_name"]) for row in result["mapped"]] == [
        ("User Skill c records", "User_Skill__c")
    ]


def test_does_not_map_generic_custom_single_word_inside_unrelated_phrase():
    result = resolve_object_references(
        ["Customer Onboarding team roster or queue configuration"],
        [{"api_name": "CHANNEL_ORDERS__Customer__c", "label": "Customer"}],
    )

    assert result["mapped"] == []
    assert result["unresolved"][0]["raw"] == "Customer Onboarding team roster or queue configuration"


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
