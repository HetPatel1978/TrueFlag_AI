"""Real PostgreSQL race and database-trigger rollback tests in disposable schemas."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from test_alert_ingestion import counts

from app.models import Alert

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize(
    "scenario", ["same_key", "different_keys", "key_conflict", "source_conflict"]
)
def test_concurrent_ingestions_have_one_business_effect(
    platform, alert_payload, admin_headers, scenario
):
    client, engine, _, _ = platform
    if engine.dialect.name != "postgresql":
        pytest.skip("Set TRUEFLAG_TEST_POSTGRES_URL to run real PostgreSQL races")
    second = deepcopy(alert_payload)
    second_headers = dict(admin_headers)
    if scenario == "different_keys":
        second_headers["Idempotency-Key"] = str(uuid4())
    elif scenario == "key_conflict":
        second["source_id"] = "another-source-same-key"
    elif scenario == "source_conflict":
        second["features"]["income"] = 0
        second_headers["Idempotency-Key"] = str(uuid4())
    barrier = Barrier(2)

    def both_reached_insert(mapper, connection, target):
        barrier.wait(timeout=10)

    event.listen(Alert, "before_insert", both_reached_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [
                pool.submit(client.post, "/api/v1/alerts", json=payload, headers=auth)
                for payload, auth in [(alert_payload, admin_headers), (second, second_headers)]
            ]
            responses = [request.result(timeout=20) for request in requests]
    finally:
        event.remove(Alert, "before_insert", both_reached_insert)
    expected = [201, 409] if scenario.endswith("conflict") else [200, 201]
    assert sorted(response.status_code for response in responses) == expected
    receipts = 2 if scenario == "different_keys" else 1
    assert counts(engine) == [1, 1, receipts, 0, 0, 1]
    if not scenario.endswith("conflict"):
        assert responses[0].json() == responses[1].json()


def test_database_trigger_failure_rolls_back_alert_case_and_audit(
    platform, alert_payload, admin_headers
):
    client, engine, _, _ = platform
    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL trigger injection requires TRUEFLAG_TEST_POSTGRES_URL")
    # Test schema only: the fixture creates a fresh search_path and drops it afterward.
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION reject_test_ingestion() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic rollback probe'; END; $$
        """)
        )
        connection.execute(
            text("""
            CREATE TRIGGER reject_test_ingestion BEFORE INSERT ON alert_ingestions
            FOR EACH ROW EXECUTE FUNCTION reject_test_ingestion()
        """)
        )
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}
    assert counts(engine) == [0, 0, 0, 0, 0, 0]
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER reject_test_ingestion ON alert_ingestions"))
        connection.execute(text("DROP FUNCTION reject_test_ingestion()"))
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 201
    )
    assert counts(engine) == [1, 1, 1, 0, 0, 1]
