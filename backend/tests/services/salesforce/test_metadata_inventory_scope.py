from app.services.salesforce.metadata import (
    DEFAULT_OBJECTS,
    select_object_describe_names,
)


def test_default_inventory_includes_agentforce_process_standard_objects():
    assert "EmailMessage" in DEFAULT_OBJECTS
    assert "EmailMessageRelation" in DEFAULT_OBJECTS
    assert "EmailTemplate" in DEFAULT_OBJECTS
    assert "RecordType" in DEFAULT_OBJECTS
    assert "QueueSobject" in DEFAULT_OBJECTS


def test_describe_selection_includes_custom_events_and_metadata_types():
    all_objects = [
        {"name": "Account", "queryable": True},
        {"name": "InternalQuickBooksEvent__e", "queryable": True},
        {"name": "Agent_Config__mdt", "queryable": True},
        {"name": "Development_Items__c", "queryable": True},
        {"name": "IgnoredHistory", "queryable": True},
    ]

    selected = select_object_describe_names(all_objects)

    assert "InternalQuickBooksEvent__e" in selected
    assert "Agent_Config__mdt" in selected
    assert "Development_Items__c" in selected
    assert "IgnoredHistory" not in selected


def test_describe_selection_adds_referenced_objects_without_duplicates():
    selected = select_object_describe_names(
        [{"name": "Development_Items__c", "queryable": True}],
        referenced_objects=["EmailMessage", "Development_Items__c", "MissingObject__c"],
    )

    assert selected.count("Development_Items__c") == 1
    assert "EmailMessage" in selected
    assert "MissingObject__c" in selected
