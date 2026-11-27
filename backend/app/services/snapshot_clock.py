"""Durable, evidence-only clock regression containment. No authentication/lease changes."""

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.snapshot_clock import SnapshotClock
from app.services.evidence import EvidenceUnavailable


class ClockUnavailable(EvidenceUnavailable):
    pass


@dataclass(frozen=True)
class ClockObservation:
    second: int
    epoch: int


class SnapshotTime:
    def __init__(self, engine):
        self.engine = engine

    def observe(self):
        # Separate commit is essential: an expired-token rejection or caller rollback
        # must not erase the observed expiry time or a newly detected regression.
        try:
            if self.engine.dialect.name != "postgresql":
                raise ClockUnavailable("snapshot_clock_unavailable")
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                session.execute(text("SET LOCAL lock_timeout='1s'"))
                session.execute(text("SET LOCAL statement_timeout='2s'"))
                session.execute(text("SET LOCAL idle_in_transaction_session_timeout='3s'"))
                session.execute(text("SET LOCAL synchronous_commit='on'"))
                row = session.scalar(
                    select(SnapshotClock).where(SnapshotClock.id == 1).with_for_update()
                )
                if row is None:
                    raise ClockUnavailable("snapshot_clock_unavailable")
                # Sample AFTER obtaining the lock, never before a concurrent observer.
                now = int(session.scalar(select(func.clock_timestamp())).timestamp())
                unsafe = now < row.high_water
                row.used = True
                if unsafe:
                    if not row.regressed:
                        row.epoch += 1
                        row.regressed = True
                else:
                    row.high_water = now
                    row.regressed = False
                observation = ClockObservation(now, row.epoch)
            # Raising inside session.begin() would incorrectly roll back containment.
            if unsafe:
                raise ClockUnavailable("snapshot_clock_unavailable")
            return observation
        except ClockUnavailable:
            raise
        except (SQLAlchemyError, ValueError, TypeError, OverflowError):
            raise ClockUnavailable("snapshot_clock_unavailable") from None
