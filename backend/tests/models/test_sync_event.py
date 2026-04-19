from uuid import uuid4

from app.models.sync_event import SyncEvent


def test_sync_event_instantiation():
    ev = SyncEvent(
        connection_id=uuid4(),
        org_id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        event_type="run_start",
        phase=None,
        message="Metadata sync started",
        detail_json={},
        severity="info",
    )
    assert ev.event_type == "run_start"
    assert ev.sequence == 1
    assert ev.severity == "info"
    assert ev.detail_json == {}
