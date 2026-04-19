import pathlib

from app.services.salesforce.mdapi_parser import parse_workflow


def test_parse_workflow_rules():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_opportunity.workflow-meta.xml"
    rows = parse_workflow(path.read_bytes(), "workflows/Opportunity.workflow-meta.xml")
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["related_object"] == "Opportunity"
    assert r0["criteria"]["formula"].startswith("AND(")
    assert r0["actions"]["field_updates"][0]["field"] == "Priority__c"
    assert r0["actions"]["email_alerts"][0]["template"] == "Big_Deal_Alert"
    assert len(r0["raw_xml_hash"]) == 64
