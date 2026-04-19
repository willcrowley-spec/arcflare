from unittest.mock import MagicMock

from app.services.salesforce.metadata import pull_custom_metadata_types


def test_pull_custom_metadata_types_filters_mdt():
    sf = MagicMock()
    sf.query_all.return_value = {
        "records": [
            {"attributes": {"type": "Config__mdt"}, "Label": "Rule1", "Value__c": "X"}
        ]
    }
    objects_list = [
        {"name": "Account", "queryable": True},
        {"name": "Config__mdt", "queryable": True},
        {"name": "Hidden__mdt", "queryable": False},
    ]
    result = pull_custom_metadata_types(sf, objects_list)
    assert len(result) == 1
    assert result[0]["metadata_type"] == "Config__mdt"
    assert result[0]["record_count"] == 1
    sf.query_all.assert_called_once()


def test_pull_custom_metadata_types_empty_org():
    sf = MagicMock()
    result = pull_custom_metadata_types(sf, [{"name": "Account", "queryable": True}])
    assert result == []
    sf.query_all.assert_not_called()
