"""Bounded metric collection, durable idempotent export and internal authorization/privacy."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.telemetry import BOUNDS_MS, METHODS, ROUTES, STATUS, Registry, capture_stages, stage
from app.models import OperationalMetric, User
from app.security.logging import SecurityFormatter
from app.services.monitoring import MetricFlusher, collect


def test_metric_labels_and_values_are_allowlisted():
    r = Registry()
    for name, label, value in [
        ("private-case", "ok", 1),
        ("api.request", "private-user|GET|2xx", 1),
        ("model.scoring", "private-feature", 1),
        ("model.scoring", "ok", float("nan")),
        ("model.scoring", "ok", -1),
        ("model.scoring", "ok", True),
    ]:
        r.observe(name, label, value)
    assert r.snapshot() == []
    r.observe("model.scoring", "ok", 3)
    assert r.snapshot()[0]["buckets"][2] == 1


def test_bounded_cardinality_and_minute_buffer():
    now = datetime.now(timezone.utc)
    r = Registry(clock=lambda: now)
    for route in ROUTES:
        for method in METHODS:
            for status in STATUS:
                r.observe("api.request", f"{route}|{method}|{status}", 1)
    assert len(r.snapshot()) == 256 and r.dropped > 0
    now += timedelta(minutes=1)
    r.observe("model.scoring", "ok", 2)
    now += timedelta(minutes=1)
    r.observe("model.scoring", "ok", 2)
    assert len({row["minute"] for row in r.snapshot()}) <= 2


def test_concurrent_observations_and_stage_scope():
    r = Registry()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: r.observe("model.scoring", "ok", 2), range(400)))
    assert r.snapshot()[0]["count"] == 400
    with capture_stages() as values:
        with stage("model.scoring"):
            pass
    assert values["model.scoring"] >= 0


def test_log_formatter_rejects_private_fields():
    row = logging.LogRecord(
        "trueflag.security",
        logging.ERROR,
        "private-path",
        1,
        "private-content",
        ("private-feature",),
        None,
    )
    row.request_id = "private-user"
    row.route_name = "private-case"
    row.error_type = "private-error-message"
    row.correlation_id = "a" * 32
    row.customer_features = "private-features"
    row.duration_ms = float("inf")
    data = SecurityFormatter().format(row)
    assert "private" not in data and json.loads(data)["correlation_id"] == "a" * 32


@pytest.fixture
def pg(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("Actual PostgreSQL telemetry acceptance")
    return platform


def test_internal_endpoint_permissions_and_private_values(pg, case_team, caplog):
    client = pg[0]
    path = "/api/v1/internal/metrics"
    assert client.get(path).status_code == 401
    for actor in ["analyst", "supervisor"]:
        assert client.get(path, headers=case_team["auth"][actor]).status_code == 403
    client.get("/private-customer-marker?secret=private-secret")
    response = client.get(path, headers=case_team["auth"]["admin"])
    assert response.status_code == 200
    assert response.json()["api"]["authorization_denials"] >= 3
    assert response.json()["api"]["not_found_or_hidden"] >= 1
    for private in [
        "private-customer",
        "private-secret",
        *case_team["ids"],
        *case_team["users"].values(),
    ]:
        assert private not in response.text and private not in caplog.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get(path + "?minutes=61", headers=case_team["auth"]["admin"]).status_code == 422


def test_export_retry_is_idempotent_and_live_merge_does_not_duplicate(pg, case_team):
    registry = Registry()
    registry.observe("model.scoring", "ok", 4)
    registry.observe("model.scoring", "ok", 10)
    exporter = MetricFlusher(pg[1], registry)
    try:
        assert exporter.flush() and exporter.flush()
        response = collect(pg[1], registry, UUID(case_team["users"]["admin"]), 15)
        row = next(r for r in response["series"] if r["name"] == "model.scoring")
        assert row["count"] == 2 and row["mean_ms"] == 7
        assert row["p50_upper_bound_ms"] == 5 and row["p95_upper_bound_ms"] == 10
        registry.observe("model.scoring", "ok", 100)
        assert exporter.flush()
        with Session(pg[1]) as session:
            assert (
                session.scalar(
                    select(func.sum(OperationalMetric.count)).where(
                        OperationalMetric.instance_id == registry.instance_id
                    )
                )
                == 3
            )
    finally:
        exporter.close()


def test_metric_db_failure_does_not_break_requests_and_recovers(pg, case_team):
    registry = Registry()
    registry.observe("model.scoring", "ok", 5)
    exporter = MetricFlusher(pg[1], registry)
    with pg[1].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_telemetry() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-metric-error'; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER reject_telemetry BEFORE INSERT ON operational_metrics FOR EACH ROW EXECUTE FUNCTION reject_telemetry()"
            )
        )
    try:
        assert exporter.flush() is False
        assert pg[0].get("/health").status_code == 200
        requested = pg[0].post(
            f"/api/v1/cases/{case_team['ids'][0]}/assessments",
            headers={**case_team["auth"]["analyst"], "Idempotency-Key": "metric-outage-request"},
            json={
                "expected_version": 1,
                "run_id": "11111111-1111-4111-8111-111111111111",
                "policy": "Coverage",
            },
        )
        assert requested.status_code == 202
        with pg[1].begin() as connection:
            connection.execute(text("DROP TRIGGER reject_telemetry ON operational_metrics"))
            connection.execute(text("DROP FUNCTION reject_telemetry()"))
        assert exporter.flush() is True
    finally:
        exporter.close()


def test_monitor_role_revocation(pg, case_team):
    auth = case_team["auth"]["admin"]
    with Session(pg[1]) as session, session.begin():
        session.get(User, UUID(case_team["users"]["admin"])).role = "analyst"
    assert pg[0].get("/api/v1/internal/metrics", headers=auth).status_code == 403


def test_quantiles_are_explicitly_bounds():
    from app.core.telemetry import histogram

    buckets = [0] * (len(BOUNDS_MS) + 1)
    buckets[-1] = 1
    assert histogram(1, 700000, buckets)["p99_upper_bound_ms"] is None
    assert histogram(0, 0, [0] * len(buckets))["mean_ms"] is None
