"""
API Endpoints für Events.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from src.models import Event, Source, Location
from ..dependencies import get_db
from ..schemas import EventResponse, EventListResponse, EventUpdate

router = APIRouter()


@router.get("", response_model=List[EventListResponse])
def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10000),
    source_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    search: Optional[str] = None,
    has_location: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """Liste aller Events mit Filteroptionen."""
    query = db.query(Event).filter(Event.deleted_at == None)

    if source_id:
        query = query.filter(Event.source_id == source_id)

    if has_location is True:
        query = query.filter(Event.location_id != None)
    elif has_location is False:
        query = query.filter(Event.location_id == None)

    if from_date:
        query = query.filter(Event.event_date >= from_date)

    if to_date:
        query = query.filter(Event.event_date <= to_date)

    if search:
        query = query.filter(Event.title.ilike(f"%{search}%"))

    query = query.order_by(Event.event_date.asc())
    events = query.offset(skip).limit(limit).all()

    # Manuelles Mapping für die Liste
    result = []
    for event in events:
        source = db.query(Source).filter(Source.id == event.source_id).first()
        location = db.query(Location).filter(Location.id == event.location_id).first() if event.location_id else None

        result.append(EventListResponse(
            id=event.id,
            title=event.title,
            event_date=event.event_date,
            event_time=event.event_time,
            url=event.url,
            raw_location=event.raw_location,
            source_id=event.source_id,
            source_name=source.name if source else None,
            location_id=event.location_id,
            location_city=location.city if location else None,
        ))

    return result


@router.get("/count")
def count_events(
    source_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Anzahl der Events."""
    query = db.query(Event).filter(Event.deleted_at == None)

    if source_id:
        query = query.filter(Event.source_id == source_id)

    if from_date:
        query = query.filter(Event.event_date >= from_date)

    if to_date:
        query = query.filter(Event.event_date <= to_date)

    return {"count": query.count()}


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Einzelnes Event mit Details."""
    event = (
        db.query(Event)
        .options(joinedload(Event.source), joinedload(Event.location))
        .filter(Event.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")

    return event


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    """Event soft-löschen."""
    from datetime import datetime

    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")

    event.deleted_at = datetime.utcnow()
    db.commit()

    return {"message": "Event gelöscht", "id": event_id}


@router.put("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, update: EventUpdate, db: Session = Depends(get_db)):
    """Event aktualisieren."""
    event = (
        db.query(Event)
        .options(joinedload(Event.source), joinedload(Event.location))
        .filter(Event.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)

    return event
