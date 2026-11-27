"""Legitimate empty polls are not evidence/source failures or valid chunk claims."""

import sys
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_csv_imports import approve, prepare, total
from test_csv_imports import base_upload as upload_fixture
from test_csv_imports import imports as import_fixture

from app.models import Alert, Case, CSVImport
from app.services.csv_imports import ImportLeaseLost
from app.workers.csv_import_worker import CSVImportWorker

base_upload = upload_fixture
imports = import_fixture
pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("reason", ["future", "locked"])
def test_empty_claim_is_safe_and_committed_import_remains_recoverable(imports, monkeypatch, reason):
    if sys.platform != "linux":
        pytest.skip("Real Linux CSV worker required")
    import app.services.csv_imports as module

    response = approve(imports, prepare(imports, [{}]))
    assert response.status_code == 202
    engine, queue, token = imports["engine"], imports["queue"], imports["token"]
    with Session(engine) as session:
        row = session.scalar(select(CSVImport))
        identity, available = row.id, row.available_at
    # Change only the CSV service's test-local query time; never host/DB clocks,
    # evidence snapshot guards, source hashes, authorization or lease predicates.
    clock = [available - timedelta(seconds=2) if reason == "future" else available]
    monkeypatch.setattr(module, "_now", lambda _: clock[0])
    worker = CSVImportWorker(queue, token)
    if reason == "locked":
        with Session(engine) as locker, locker.begin():
            locker.scalar(select(CSVImport).where(CSVImport.id == identity).with_for_update())
            assert queue.claim(token) is None
            assert worker.run_once() is None
    else:
        assert queue.claim(token) is None
        assert worker.run_once() is None
    # Reproduces the original exception's exact entry fence if a caller wrongly
    # assumes every poll returned a claim. No source verification was reached.
    with pytest.raises(ImportLeaseLost):
        queue.process_chunk(token, None)
    assert total(imports, Alert) == total(imports, Case) == 0
    with Session(engine) as session:
        row = session.get(CSVImport, identity)
        assert row.status == "pending" and row.attempts == row.processed_rows == 0
    clock[0] = available + timedelta(seconds=1)
    result = worker.run_once()
    assert result.status == "completed" and result.created_rows == 1
    assert total(imports, Alert) == total(imports, Case) == 1
    assert worker.run_once() is None
