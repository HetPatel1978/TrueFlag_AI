"""Evidence-only UTC time floor, retained independently from failed requests."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base


class SnapshotClock(Base):
    __tablename__ = "snapshot_clock"
    __table_args__ = (
        CheckConstraint("id=1", name="ck_snapshot_clock_singleton"),
        CheckConstraint("high_water>=0 AND epoch>=1", name="ck_snapshot_clock_values"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    high_water: Mapped[int] = mapped_column(BigInteger)
    epoch: Mapped[int] = mapped_column(BigInteger)
    regressed: Mapped[bool] = mapped_column(Boolean)
    used: Mapped[bool] = mapped_column(Boolean)
