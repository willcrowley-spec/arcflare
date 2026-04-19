import pathlib

from app.services.salesforce.apex_parser.analyzer import analyze_apex_class, analyze_apex_trigger


def test_analyze_apex_class_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountService.cls"
    out = analyze_apex_class(path.read_text(encoding="utf-8"), None)
    assert "updateRatings" in {m["name"] for m in out["methods"]}
    assert "accounts" in out["dml_objects"]
    assert "Contact" in out["soql_objects"]
    assert out["line_count"] >= 5


def test_analyze_apex_trigger_fixture():
    path = pathlib.Path(__file__).parent / "fixtures" / "AccountRating.trigger"
    out = analyze_apex_trigger(path.read_text(encoding="utf-8"), None)
    assert out["trigger_object"] == "Account"
    assert any("update" in e.lower() for e in out["trigger_events"])
