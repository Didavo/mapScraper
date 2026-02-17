"""
API Endpoints für Sources.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.models import Source, Event, ScrapeLog
from ..dependencies import get_db
from ..schemas import SourceResponse, ScrapeLogResponse

router = APIRouter()


@router.get("", response_model=List[SourceResponse])
def list_sources(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    """Liste aller Sources."""
    query = db.query(Source)

    if active_only:
        query = query.filter(Source.is_active == True)

    return query.order_by(Source.name).offset(skip).limit(limit).all()


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: int, db: Session = Depends(get_db)):
    """Einzelne Source."""
    source = db.query(Source).filter(Source.id == source_id).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source nicht gefunden")

    return source


@router.get("/{source_id}/stats")
def get_source_stats(source_id: int, db: Session = Depends(get_db)):
    """Statistiken für eine Source."""
    source = db.query(Source).filter(Source.id == source_id).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source nicht gefunden")

    events_count = (
        db.query(Event)
        .filter(Event.source_id == source_id, Event.deleted_at == None)
        .count()
    )

    last_log = (
        db.query(ScrapeLog)
        .filter(ScrapeLog.source_id == source_id)
        .order_by(ScrapeLog.started_at.desc())
        .first()
    )

    return {
        "source_id": source_id,
        "source_name": source.name,
        "events_count": events_count,
        "last_scraped_at": source.last_scraped_at,
        "last_scrape_status": last_log.status if last_log else None,
    }


@router.get("/{source_id}/logs", response_model=List[ScrapeLogResponse])
def get_source_logs(
    source_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Scrape-Logs für eine Source."""
    source = db.query(Source).filter(Source.id == source_id).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source nicht gefunden")

    return (
        db.query(ScrapeLog)
        .filter(ScrapeLog.source_id == source_id)
        .order_by(ScrapeLog.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/{source_id}/toggle")
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    """Source aktivieren/deaktivieren."""
    source = db.query(Source).filter(Source.id == source_id).first()

    if not source:
        raise HTTPException(status_code=404, detail="Source nicht gefunden")

    source.is_active = not source.is_active
    db.commit()

    return {
        "source_id": source_id,
        "is_active": source.is_active,
    }
