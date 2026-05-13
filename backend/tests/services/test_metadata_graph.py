from app.services.metadata_graph import (
    _dedupe_edges,
    _edges_from_apex_class,
    _edges_from_flow,
    _filter_edge_for_objects,
)


def test_edges_from_flow():
    meta = {
        "trigger_object": "Account",
        "elements": {
            "record_lookups": [{"object": "Contact"}],
            "record_creates": [{"object": "Task"}],
            "record_updates": [],
            "record_deletes": [],
            "subflows": [{"flow_name": "Sub_Flow"}],
            "action_calls": [
                {"action_type": "apex", "action_name": "MyService"},
                {"action_type": "emailAlert", "action_name": "WelcomeEmail"},
            ],
        },
    }
    edges = _edges_from_flow("Test_Flow", meta)
    rels = {(e["relationship_type"], e["target_api_name"]) for e in edges}
    assert ("triggers_on", "Account") in rels
    assert ("reads", "Contact") in rels
    assert ("writes", "Task") in rels
    assert ("calls_subflow", "Sub_Flow") in rels
    assert ("invokes_apex", "MyService") in rels
    assert ("sends_email", "WelcomeEmail") in rels


def test_edges_from_apex_class():
    edges = _edges_from_apex_class("Svc", {"soql_objects": ["Account"], "dml_objects": ["Case"]})
    assert len(edges) == 2
    assert edges[0]["relationship_type"] == "reads"
    assert edges[1]["relationship_type"] == "writes"


def test_filter_edge_drops_unknown_object():
    valid = {"Account"}
    good = {
        "source_type": "flow",
        "source_api_name": "F",
        "relationship_type": "reads",
        "target_type": "object",
        "target_api_name": "Account",
        "metadata_json": {},
    }
    bad = {**good, "target_api_name": "Fake__c"}
    assert _filter_edge_for_objects(good, valid) is True
    assert _filter_edge_for_objects(bad, valid) is False


def test_dedupe_edges():
    e = {
        "source_type": "flow",
        "source_api_name": "F",
        "relationship_type": "reads",
        "target_type": "object",
        "target_api_name": "A",
        "metadata_json": {},
    }
    assert len(_dedupe_edges([e, e, e])) == 1
