import pathlib

from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger


def test_analyze_apex_class_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountService.cls"
    out = analyze_apex_class(path.read_text(encoding="utf-8"), None)
    assert "updateRatings" in {m["name"] for m in out["methods"]}
    # DML should resolve to SObject types, not variable names
    assert "Account" in out["dml_objects"]
    assert "Contact" in out["soql_objects"]
    assert out["line_count"] >= 5
    # Per-method flags
    method = next(m for m in out["methods"] if m["name"] == "updateRatings")
    assert method["has_dml"] is True
    assert method["has_soql"] is True
    assert "Account" in method["dml_objects"]


def test_analyze_apex_trigger_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountRating.trigger"
    out = analyze_apex_trigger(path.read_text(encoding="utf-8"), None)
    assert out["trigger_object"] == "Account"
    assert any("update" in e.lower() for e in out["trigger_events"])
