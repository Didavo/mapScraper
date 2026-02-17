from datetime import datetime, date, time
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Date, Time, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .source import Source
    from .location import Location


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign Keys
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )

    # Deduplication
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Event data
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[Optional[time]] = mapped_column(Time)
    event_end_date: Mapped[Optional[date]] = mapped_column(Date)
    event_end_time: Mapped[Optional[time]] = mapped_column(Time)

    # URL
    url: Mapped[Optional[str]] = mapped_column(String(1000))

    # Raw location fallback
    raw_location: Mapped[Optional[str]] = mapped_column(String(500))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="events")
    location: Mapped[Optional["Location"]] = relationship(back_populates="events")

    # Constraints
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, title='{self.title}', date={self.event_date})>"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
