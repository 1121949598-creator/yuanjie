import sqlite3
from contextlib import closing

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.models import ScanResult
from yuanjian_agent.storage import ScanStore


@pytest.fixture
def tracked_connections(monkeypatch):
    original_connect = sqlite3.connect
    opened = []

    class TrackedConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            return super().close()

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=TrackedConnection)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    return opened, original_connect


def synthetic_result():
    return ScanResult(id="synthetic", project_name="synthetic", source_path="synthetic",
                      created_at="2026-10-07T00:00:00+00:00", status="completed", version="0.1.0")


def test_store_closes_connections_without_waiting_for_gc(tmp_path, tracked_connections):
    opened, _connect = tracked_connections
    store = ScanStore(Settings(data_dir=tmp_path / "state"))
    store.save(synthetic_result())
    assert store.get("synthetic").id == "synthetic"
    assert len(store.list()) == 1
    with pytest.raises(KeyError):
        store.get("absent")
    assert len(opened) == 5
    assert all(connection.was_closed for connection in opened)


def test_failed_save_rolls_back_and_closes_connection(tmp_path, tracked_connections):
    opened, original_connect = tracked_connections
    settings = Settings(data_dir=tmp_path / "state")
    store = ScanStore(settings)
    with closing(original_connect(settings.database_path)) as connection, connection:
        connection.execute("DROP TABLE findings")
    with pytest.raises(sqlite3.OperationalError):
        store.save(synthetic_result())
    with pytest.raises(KeyError):
        store.get("synthetic")
    assert all(connection.was_closed for connection in opened)
