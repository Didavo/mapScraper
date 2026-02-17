"""
Pydantic Schemas für die API.
"""

from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


# === Location Schemas ===

class LocationBase(BaseModel):
    source_id: int
    raw_name: str
    display_name: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "Deutschland"
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    status: str = "pending"


class LocationCreate(BaseModel):
    raw_name: str


class LocationUpdate(BaseModel):
    display_name: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    status: Optional[str] = None


class LocationResponse(LocationBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# === Source Schemas ===

class SourceBase(BaseModel):
    name: str
    base_url: str
    scraper_class: str
    is_active: bool = True


class SourceResponse(SourceBase):
    id: int
    last_scraped_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# === Event Schemas ===

class EventBase(BaseModel):
    title: str
    event_date: date
    event_time: Optional[time] = None
    event_end_date: Optional[date] = None
    event_end_time: Optional[time] = None
    url: Optional[str] = None
    raw_location: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    event_date: Optional[date] = None
    event_time: Optional[time] = None
    url: Optional[str] = None
    raw_location: Optional[str] = None
    location_id: Optional[int] = None


class EventResponse(EventBase):
    id: int
    source_id: int
    location_id: Optional[int] = None
    external_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    # Nested
    source: Optional[SourceResponse] = None
    location: Optional[LocationResponse] = None

    model_config = ConfigDict(from_attributes=True)


class EventListResponse(BaseModel):
    id: int
    title: str
    event_date: date
    event_time: Optional[time] = None
    url: Optional[str] = None
    raw_location: Optional[str] = None
    source_id: int
    source_name: Optional[str] = None
    location_id: Optional[int] = None
    location_city: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# === Scrape Log Schemas ===

class ScrapeLogResponse(BaseModel):
    id: int
    source_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    events_found: int
    events_new: int
    events_updated: int
    geocoding_success: int = 0
    geocoding_multiple: int = 0
    geocoding_not_found: int = 0
    geocoding_errors: int = 0
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# === Scraper Schemas ===

class ScrapeRequest(BaseModel):
    source_name: str


class ScrapeResponse(BaseModel):
    status: str
    source: str
    events_found: Optional[int] = None
    events_new: Optional[int] = None
    events_updated: Optional[int] = None
    error: Optional[str] = None


# === Stats ===

class StatsResponse(BaseModel):
    total_events: int
    total_sources: int
    total_locations: int
    pending_locations: int
    events_by_source: dict
