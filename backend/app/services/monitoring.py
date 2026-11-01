"""Best-effort telemetry export and bounded admin-only aggregate queries."""

import logging
import math
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.telemetry import BOUNDS_MS, METRICS, Registry, histogram, valid_label
from app.models import AssessmentJob, AuditEvent, OperationalMetric, User
from app.services.assessments import AssessmentNotFound

logger = logging.getLogger("trueflag.security")


class MetricFlusher:
    def __init__(self, engine, registry, interval=5):
        self.registry = registry
        self.interval = interval
        self.stop = threading.Event()
        self.correlation_id = uuid4().hex
        self.failed = False
        self.thread = None
        self.engine = None
        if engine.dialect.name == "postgresql":
            self.engine = create_engine(
                engine.url,
                pool_size=1,
                max_overflow=0,
                pool_timeout=0.2,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 1},
            )

    def flush(self):
        if self.engine is None:
            return False
        try:
            rows = self.registry.snapshot()
            with self.engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '500ms'"))
                connection.execute(text("SET LOCAL lock_timeout = '200ms'"))
                if rows:
                    statement = insert(OperationalMetric).values(rows)
                    connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=["instance_id", "minute", "name", "label"],
                            set_={
                                name: getattr(statement.excluded, name)
                                for name in ("count", "total_ms", "buckets")
                            },
                            where=OperationalMetric.count <= statement.excluded.count,
                        )
                    )
                connection.execute(
                    delete(OperationalMetric).where(
                        OperationalMetric.minute < func.clock_timestamp() - timedelta(minutes=120),
                    )
                )
            if self.failed:
                logger.info("telemetry.recovered", extra={"correlation_id": self.correlation_id})
            self.failed = False
            return True
        except Exception:
            if not self.failed:
                logger.warning(
                    "telemetry.unavailable", extra={"correlation_id": self.correlation_id}
                )
            self.failed = True
            return False

    def start(self):
        if self.engine is not None:
            self.thread = threading.Thread(target=self._run, daemon=True, name="safe-metric-export")
            self.thread.start()
        return self

    def _run(self):
        while not self.stop.wait(self.interval):
            self.flush()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        # A bounded final attempt, never part of a domain transaction.
        if not self.thread or not self.thread.is_alive():
            self.flush()
            if self.engine:
                self.engine.dispose()


def _valid(row):
    return (
        row["name"] in METRICS
        and valid_label(row["name"], row["label"])
        and type(row["count"]) is int
        and row["count"] >= 0
        and type(row["total_ms"]) in (int, float)
        and math.isfinite(row["total_ms"])
        and row["total_ms"] >= 0
        and type(row["buckets"]) is list
        and len(row["buckets"]) == len(BOUNDS_MS) + 1
        and all(type(n) is int and n >= 0 for n in row["buckets"])
        and sum(row["buckets"]) == row["count"]
    )


def collect(engine, registry: Registry, actor_id, minutes):
    with Session(engine) as session, session.begin():
        pg = engine.dialect.name == "postgresql"
        if pg:
            session.execute(text("SET LOCAL statement_timeout = '2s'"))
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
        allowed = session.scalar(
            select(User.id)
            .where(
                User.id == actor_id,
                User.active.is_(True),
                User.role == "admin",
            )
            .with_for_update(read=True)
        )
        if allowed is None:
            raise AssessmentNotFound("monitoring_not_authorized")
        from app.models.domain import utcnow

        now = session.scalar(select(func.clock_timestamp())) if pg else utcnow()
        since = now - timedelta(minutes=minutes)
        local = registry.snapshot()
        local_keys = {(r["instance_id"], r["minute"], r["name"], r["label"]) for r in local}
        stored = (
            session.execute(
                select(OperationalMetric)
                .where(
                    OperationalMetric.minute >= since,
                )
                .order_by(OperationalMetric.minute.desc())
                .limit(10001)
            )
            .scalars()
            .all()
        )
        rows = []
        for r in stored[:10000]:
            minute = r.minute if r.minute.tzinfo else r.minute.replace(tzinfo=now.tzinfo)
            if (r.instance_id, minute, r.name, r.label) not in local_keys:
                rows.append(
                    {
                        "name": r.name,
                        "label": r.label,
                        "count": r.count,
                        "total_ms": r.total_ms,
                        "buckets": r.buckets,
                    }
                )
        rows += [r for r in local if r["minute"] >= since]
        combined, invalid = {}, 0
        for r in rows:
            if not _valid(r):
                invalid += 1
                continue
            key = (r["name"], r["label"])
            group = combined.setdefault(key, [0, 0.0, [0] * (len(BOUNDS_MS) + 1)])
            group[0] += r["count"]
            group[1] += r["total_ms"]
            group[2] = [a + b for a, b in zip(group[2], r["buckets"], strict=True)]
        counters = {
            "worker.recovery_scan",
            "worker.recovered",
            "api.queue_saturation",
            "api.queue_contention",
        }
        series = [
            {
                "name": key[0],
                "label": key[1],
                **(
                    {"kind": "counter", "count": values[0]}
                    if key[0] in counters
                    else {"kind": "histogram", **histogram(*values)}
                ),
            }
            for key, values in sorted(combined.items())
        ]
        counts = dict(
            session.execute(
                select(AssessmentJob.status, func.count()).group_by(AssessmentJob.status)
            ).all()
        )
        oldest = session.scalar(
            select(func.min(AssessmentJob.created_at)).where(AssessmentJob.status == "pending")
        )
        if oldest and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=now.tzinfo)
        expired = session.scalar(
            select(func.count())
            .select_from(AssessmentJob)
            .where(
                AssessmentJob.status == "running",
                or_(AssessmentJob.lease_until <= now, AssessmentJob.deadline <= now),
            )
        )
        durable = dict(
            session.execute(
                select(AuditEvent.action, func.count())
                .where(
                    AuditEvent.created_at >= since,
                    AuditEvent.action.in_(
                        [
                            "assessment.job.claimed",
                            "assessment.job.succeeded",
                            "assessment.job.retry_scheduled",
                            "assessment.job.failed",
                        ]
                    ),
                )
                .group_by(AuditEvent.action)
            ).all()
        )
        request_groups = [r for r in series if r["name"] == "api.request"]
        total = sum(r["count"] for r in request_groups)

        def count_status(states):
            return sum(
                r["count"] for r in request_groups if r["label"].rsplit("|", 1)[-1] in states
            )

        server_errors = count_status({"503", "other5xx"})
        client_errors = count_status({"401", "403", "404", "409", "422", "429", "other4xx"})
        return {
            "window_minutes": minutes,
            "as_of": now.isoformat(),
            "coverage": {
                "row_limit": 10000,
                "truncated": len(stored) > 10000,
                "invalid_rows": invalid,
                "local_dropped_observations": registry.dropped,
                "export_interval_seconds": 5,
                "retention_minutes": 120,
                "quantiles": "histogram upper bounds; null means empty or overflow",
            },
            "api": {
                "requests": total,
                "server_errors": server_errors,
                "server_error_rate": server_errors / total if total else 0.0,
                "client_errors": client_errors,
                "client_error_rate": client_errors / total if total else 0.0,
                "error_rate": (server_errors + client_errors) / total if total else 0.0,
                "queue_saturation": sum(
                    r["count"] for r in series if r["name"] == "api.queue_saturation"
                ),
                "queue_contention": sum(
                    r["count"] for r in series if r["name"] == "api.queue_contention"
                ),
                "authorization_denials": count_status({"401", "403"}),
                "not_found_or_hidden": count_status({"404"}),
                "rate_limited": count_status({"429"}),
                "unavailable": count_status({"503"}),
                "latency": histogram(
                    total,
                    sum(r[1] for key, r in combined.items() if key[0] == "api.request"),
                    [
                        sum(r[2][i] for key, r in combined.items() if key[0] == "api.request")
                        for i in range(len(BOUNDS_MS) + 1)
                    ],
                ),
            },
            "queue": {
                "pending": counts.get("pending", 0),
                "running": counts.get("running", 0),
                "succeeded": counts.get("succeeded", 0),
                "failed": counts.get("failed", 0),
                "oldest_pending_age_seconds": max(0, (now - oldest).total_seconds())
                if oldest
                else 0,
                "expired_leases": expired,
            },
            "durable_events": durable,
            "worker_throughput_per_second": durable.get("assessment.job.succeeded", 0)
            / (minutes * 60),
            "series": series,
        }
