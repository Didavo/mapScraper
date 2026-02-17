from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .source import Source


class ScrapeStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign Key
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Statistics
    events_found: Mapped[int] = mapped_column(Integer, default=0)
    events_new: Mapped[int] = mapped_column(Integer, default=0)
    events_updated: Mapped[int] = mapped_column(Integer, default=0)

    # Geocoding Statistics
    geocoding_success: Mapped[int] = mapped_column(Integer, default=0)
    geocoding_multiple: Mapped[int] = mapped_column(Integer, default=0)
    geocoding_not_found: Mapped[int] = mapped_column(Integer, default=0)
    geocoding_errors: Mapped[int] = mapped_column(Integer, default=0)

    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="scrape_logs")

    def __repr__(self) -> str:
        return f"<ScrapeLog(id={self.id}, source_id={self.source_id}, status='{self.status}')>"
