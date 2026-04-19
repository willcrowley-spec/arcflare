from app.services.metadata_vectorizer import (
    _describe_automation,
    _describe_object,
    describe_component_chunks,
)


class _FakeAuto:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeComp:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeObj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_describe_flow_automation():
    auto = _FakeAuto(
        label="My Flow", api_name="My_Flow", automation_type="flow",
        status="Active", related_object="Account",
        metadata_json={
            "process_type": "RecordTriggeredFlow",
            "trigger_type": "RecordAfterSave",
            "objects_touched": ["Account", "Task"],
            "element_count": 5,
            "complexity_score": 8,
            "elements": {
                "decisions": [{"name": "Check_Industry"}],
                "record_creates": [{"name": "Create_Task"}],
                "record_updates": [], "record_lookups": [],
                "record_deletes": [], "subflows": [], "action_calls": [],
            },
            "variables": [{"name": "varAccount"}],
            "formulas": [{"name": "f_score", "expression": "1+1"}],
            "description": "Test flow",
        },
    )
    text = _describe_automation(auto)
    assert "RecordTriggeredFlow" in text
    assert "Account" in text
    assert "Task" in text
    assert "Check_Industry" in text
    assert "f_score" in text


def test_describe_workflow_automation():
    auto = _FakeAuto(
        label="Big Deal", api_name="Big_Deal", automation_type="workflow_rule",
        status="Active", related_object="Opportunity",
        metadata_json={
            "criteria": {"formula": "Amount > 100000", "trigger_type": "onCreateOrTriggeringUpdate"},
            "actions": {
                "field_updates": [{"name": "Set_Priority"}],
                "email_alerts": [{"name": "Notify_Manager"}],
                "outbound_messages": [], "tasks": [],
            },
        },
    )
    text = _describe_automation(auto)
    assert "Amount > 100000" in text
    assert "Set_Priority" in text


def test_describe_approval_automation():
    auto = _FakeAuto(
        label="Deal Approval", api_name="Deal_Approval", automation_type="approval_process",
        status="Active", related_object="Opportunity",
        metadata_json={
            "entry_criteria_formula": "Amount > 50000",
            "steps": [{"number": 1, "assignee_type": "relatedUserField"}],
            "final_approval_actions": [{"name": "Mark_Approved"}],
        },
    )
    text = _describe_automation(auto)
    assert "Amount > 50000" in text
    assert "Mark_Approved" in text


def test_apex_class_chunking():
    comp = _FakeComp(
        label="AccountService", api_name="AccountService",
        component_category="apex_class", status="Active", related_object=None,
        metadata_json={
            "methods": [
                {"name": "updateRatings", "return_type": "void", "parameters": "(List<Account>)",
                 "has_dml": True, "has_soql": True, "has_callout": False},
            ],
            "dml_objects": ["accounts"],
            "soql_objects": ["Contact"],
            "callout_detected": False,
            "line_count": 10,
        },
    )
    chunks = describe_component_chunks(comp)
    assert len(chunks) == 2
    assert chunks[0][0] == "overview"
    assert "AccountService" in chunks[0][1]
    assert chunks[1][0] == "method_updateRatings"
    assert "DML" in chunks[1][1]


def test_custom_metadata_type_chunking():
    comp = _FakeComp(
        label="Config", api_name="Config__mdt",
        component_category="custom_metadata_type", status=None, related_object=None,
        metadata_json={
            "record_count": 3,
            "fields": ["Label", "Value__c"],
            "records": [{"Label": "Rule1", "Value__c": "X"}],
        },
    )
    chunks = describe_component_chunks(comp)
    assert len(chunks) == 1
    assert "Config__mdt" in chunks[0][1]
    assert "Records: 3" in chunks[0][1]


def test_describe_object_with_mdapi_enrichment():
    obj = _FakeObj(
        label="Account", api_name="Account", is_custom=False,
        record_count=1000, field_count=50, managed_package_namespace=None,
        metadata_json={
            "validation_rules": [{"name": "Require_Amount", "active": True, "error_condition_formula": "ISBLANK(Amount__c)"}],
            "formula_fields": [{"api_name": "Revenue__c", "formula": "Amount * Rate"}],
            "record_types": [{"developer_name": "Enterprise", "label": "Enterprise"}],
            "field_sets": [{"label": "Quick Create", "fields": ["Name", "Amount"]}],
            "sharing_model": "ReadWrite",
        },
    )
    text = _describe_object(obj, [])
    assert "Require_Amount" in text
    assert "ISBLANK(Amount__c)" in text
    assert "Revenue__c" in text
    assert "Enterprise" in text
    assert "Quick Create" in text
    assert "ReadWrite" in text
