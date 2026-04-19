import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.sync_event_log import SyncEventEmitter


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.publish = MagicMock()
    return r


@pytest.fixture
def emitter(mock_db, mock_redis):
    with patch("app.services.sync_event_log.get_redis_client", return_value=mock_redis):
        return SyncEventEmitter(
            connection_id=uuid4(),
            org_id=uuid4(),
            run_id=uuid4(),
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_emit_increments_sequence(emitter, mock_db):
    await emitter.emit("run_start", "Sync started")
    await emitter.emit("phase_start", "Starting objects", phase="objects")
    assert emitter._sequence == 2
    assert mock_db.add.call_count == 2
    assert mock_db.flush.await_count == 2


@pytest.mark.asyncio
async def test_emit_publishes_to_redis(emitter, mock_redis):
    await emitter.emit("run_start", "Sync started", detail={"foo": 1})
    mock_redis.publish.assert_called_once()
    channel, payload_str = mock_redis.publish.call_args[0]
    assert "sync_events:" in channel
    payload = json.loads(payload_str)
    assert payload["event_type"] == "run_start"
    assert payload["message"] == "Sync started"
    assert payload["detail"]["foo"] == 1
    assert payload["sequence"] == 1
    assert "run_id" in payload and "connection_id" in payload


@pytest.mark.asyncio
async def test_emit_phase_event(emitter, mock_db):
    await emitter.emit("phase_start", "Pulling objects...", phase="objects")
    added_event = mock_db.add.call_args[0][0]
    assert added_event.phase == "objects"
    assert added_event.event_type == "phase_start"


@pytest.mark.asyncio
async def test_emit_error_severity(emitter, mock_db):
    await emitter.emit("error", "MDAPI failed", severity="error", phase="mdapi_retrieve")
    added_event = mock_db.add.call_args[0][0]
    assert added_event.severity == "error"


@pytest.mark.asyncio
async def test_purge_old_runs(mock_db, mock_redis):
    conn_id = uuid4()
    org_id = uuid4()
    with patch("app.services.sync_event_log.get_redis_client", return_value=mock_redis):
        emitter = SyncEventEmitter(conn_id, org_id, uuid4(), mock_db)
    mock_db.execute = AsyncMock()
    await emitter.purge_old_runs()
    mock_db.execute.assert_called_once()
