"""
API Endpoints für Scrape Logs.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from src.models import ScrapeLog, Source
from ..dependencies import get_db
from ..schemas import ScrapeLogResponse

router = APIRouter()


@router.get("", response_model=List[ScrapeLogResponse])
def list_scrape_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    source_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Liste aller Scrape Logs."""
    query = db.query(ScrapeLog)

    if source_id:
        query = query.filter(ScrapeLog.source_id == source_id)

    if status:
        query = query.filter(ScrapeLog.status == status)

    query = query.order_by(ScrapeLog.started_at.desc())
    return query.offset(skip).limit(limit).all()