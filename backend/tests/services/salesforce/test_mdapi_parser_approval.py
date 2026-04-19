import pathlib

from app.services.salesforce.mdapi_parser import parse_approval_process


def test_parse_approval_process_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "sample_deal_approval.approvalProcess-meta.xml"
    out = parse_approval_process(
        path.read_bytes(),
        "approvalProcesses/Opportunity.Deal_Approval.approvalProcess-meta.xml",
    )
    assert out["related_object"] == "Opportunity"
    assert out["entry_criteria_formula"] == "Amount > 50000"
    assert out["record_editability"] == "AdminOnly"
    assert out["steps"][0]["assignee_type"] == "relatedUserField"
    assert any(a["name"] == "Mark_Approved" for a in out["final_approval_actions"])
    assert len(out["raw_xml_hash"]) == 64
