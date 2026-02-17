from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event import Event
    from .source import Source


class LocationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"


class GeocodingStatus(str, Enum):
    SUCCESS = "success"
    MULTIPLE = "multiple"  # Mehrere Ergebnisse - erstes verwendet, aber unsicher
    NOT_FOUND = "not_found"
    ERROR = "error"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Reference to Source (Location belongs to a municipality/source)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))

    # Original name from scraping
    raw_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Manually maintained data
    display_name: Mapped[Optional[str]] = mapped_column(String(500))
    street: Mapped[Optional[str]] = mapped_column(String(255))
    house_number: Mapped[Optional[str]] = mapped_column(String(20))
    postal_code: Mapped[Optional[str]] = mapped_column(String(10))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100), default="Deutschland")

    # Geocoding
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8))
    geocoding_status: Mapped[Optional[str]] = mapped_column(String(20))  # null, success, not_found, error

    # Status for workflow
    status: Mapped[str] = mapped_column(
        String(20), default=LocationStatus.PENDING.value
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="locations")
    events: Mapped[List["Event"]] = relationship(back_populates="location")

    # Constraints
    __table_args__ = (
        UniqueConstraint("source_id", "raw_name", name="uq_source_location"),
    )

    def __repr__(self) -> str:
        
        return f"<Location(id={self.id}, raw_name='{self.raw_name}', status='{self.status}')>"

    @property
    def full_address(self) -> Optional[str]:
        """Returns formatted full address if available."""
        if not self.street:
            return None

        parts = []
        if self.street:
            addr = self.street
            if self.house_number:
                addr += f" {self.house_number}"
            parts.append(addr)

        if self.postal_code or self.city:
            city_part = " ".join(filter(None, [self.postal_code, self.city]))
            parts.append(city_part)

        if self.country and self.country != "Deutschland":
            parts.append(self.country)

        return ", ".join(parts) if parts else None
