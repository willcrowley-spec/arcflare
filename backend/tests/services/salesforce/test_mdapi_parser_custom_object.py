import pathlib

from app.services.salesforce.mdapi_parser import parse_custom_object


def test_parse_custom_object_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_custom_object.object-meta.xml"
    out = parse_custom_object(path.read_bytes(), "sample_custom_object.object-meta.xml")
    assert out["sharing_model"] == "ReadWrite"
    assert out["validation_rules"][0]["error_condition_formula"] == "ISBLANK(Amount__c)"
    assert out["formula_fields"][0]["api_name"] == "Expected_Revenue__c"
    assert "Name" in out["field_sets"][0]["fields"]
    assert len(out["raw_xml_hash"]) == 64
