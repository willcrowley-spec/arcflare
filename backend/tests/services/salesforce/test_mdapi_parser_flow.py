import pathlib

from app.services.salesforce.mdapi_parser import parse_flow


def test_parse_flow_sample_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_record_triggered_flow.flow-meta.xml"
    data = path.read_bytes()
    out = parse_flow(data, "sample_record_triggered_flow.flow-meta.xml")
    assert out["process_type"] == "RecordTriggeredFlow"
    assert out["trigger_object"] == "Account"
    assert "Account" in out["objects_touched"]
    assert "Task" in out["objects_touched"]
    assert out["element_count"] >= 4
    assert len(out["raw_xml_hash"]) == 64
    assert out["elements"]["record_updates"][0]["object"] == "Account"
    assert out["elements"]["decisions"][0]["rules"][0]["name"] == "Healthcare"
