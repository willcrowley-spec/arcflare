from app.services.processes.visibility import (
    hidden_metadata_terms_from_objects,
    is_visible_metadata_object,
    redact_hidden_metadata_text,
)


class _Object:
    def __init__(self, classification: str | None):
        self.classification = classification


def test_excluded_metadata_objects_are_not_visible_to_process_discovery():
    assert is_visible_metadata_object(_Object("excluded")) is False


def test_included_or_unclassified_metadata_objects_remain_visible_to_process_discovery():
    assert is_visible_metadata_object(_Object("included")) is True
    assert is_visible_metadata_object(_Object(None)) is True


class _MetadataObject:
    def __init__(self, api_name: str, label: str):
        self.api_name = api_name
        self.label = label


def test_hidden_metadata_terms_include_namespaced_and_label_variants():
    terms = hidden_metadata_terms_from_objects(
        [
            _MetadataObject(
                "ElevateForceQBO__QuickBooksRealm__c",
                "QuickBooks Realm",
            )
        ]
    )

    assert "ElevateForceQBO__QuickBooksRealm__c" in terms
    assert "QuickBooksRealm__c" in terms
    assert "QuickBooks Realm" in terms
    assert "QuickBooks_Realm" in terms


def test_redact_hidden_metadata_text_removes_hidden_lines_and_keeps_allowed_evidence():
    text = "\n".join(
        [
            "Salesforce Automation: QuickBooks_Event_Payment_Create",
            "Objects Touched: Account, QuickBooksInvoice__c",
            "action_calls: Parse_Payment_Amount_and_Invoice_Data, Fetch_QuickBooks_Realm_Id",
            "record_creates: Insert_Payment_Record",
        ]
    )

    redacted = redact_hidden_metadata_text(text, {"QuickBooks Realm", "QuickBooks_Realm"})

    assert "Fetch_QuickBooks_Realm_Id" not in redacted
    assert "Parse_Payment_Amount_and_Invoice_Data" not in redacted
    assert "QuickBooksInvoice__c" in redacted
    assert "Insert_Payment_Record" in redacted
