"""
HTML Views für Browser-Ansicht.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from src.models import Event, Source, Location, LocationStatus, ScrapeLog
from ..dependencies import get_db
from ..routers.scraper import SCRAPER_REGISTRY

router = APIRouter()

templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Dashboard / Startseite."""
    # Stats
    total_events = db.query(Event).filter(Event.deleted_at == None).count()
    total_sources = db.query(Source).count()
    pending_locations = (
        db.query(Location)
        .filter(Location.status == LocationStatus.PENDING.value)
        .count()
    )

    # Recent events
    recent_events = (
        db.query(Event)
        .filter(Event.deleted_at == None)
        .order_by(Event.event_date.asc())
        .limit(10)
        .all()
    )

    # Sources
    sources = db.query(Source).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total_events": total_events,
            "total_sources": total_sources,
            "pending_locations": pending_locations,
            "recent_events": recent_events,
            "sources": sources,
        },
    )


@router.get("/events", response_class=HTMLResponse)
def events_page(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    source_id: Optional[str] = None,
    search: Optional[str] = None,
    location_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Events-Liste."""
    per_page = min(per_page, 200)  # Max 200
    offset = (page - 1) * per_page

    # source_id von String zu Int konvertieren (leerer String = None)
    source_id_int = int(source_id) if source_id and source_id.isdigit() else None

    query = db.query(Event).options(
        joinedload(Event.source), joinedload(Event.location)
    ).filter(Event.deleted_at == None)

    if source_id_int:
        query = query.filter(Event.source_id == source_id_int)

    if search:
        query = query.filter(Event.title.ilike(f"%{search}%"))

    if location_filter == "missing":
        query = query.filter(Event.location_id == None)
    elif location_filter == "assigned":
        query = query.filter(Event.location_id != None)

    total = query.count()
    events = query.order_by(Event.event_date.asc()).offset(offset).limit(per_page).all()

    sources = db.query(Source).all()

    total_pages = (total + per_page - 1) // per_page

    # Counts für Location-Filter
    base_query = db.query(Event).filter(Event.deleted_at == None)
    if source_id_int:
        base_query = base_query.filter(Event.source_id == source_id_int)
    if search:
        base_query = base_query.filter(Event.title.ilike(f"%{search}%"))

    all_count = base_query.count()
    missing_count = base_query.filter(Event.location_id == None).count()
    assigned_count = base_query.filter(Event.location_id != None).count()

    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "events": events,
            "sources": sources,
            "current_page": page,
            "total_pages": total_pages,
            "total": total,
            "source_id": source_id_int,
            "search": search or "",
            "per_page": per_page,
            "location_filter": location_filter or "",
            "all_count": all_count,
            "missing_count": missing_count,
            "assigned_count": assigned_count,
        },
    )


@router.get("/events/{event_id}/edit", response_class=HTMLResponse)
def edit_event_page(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
):
    """Event bearbeiten."""
    event = (
        db.query(Event)
        .options(joinedload(Event.source), joinedload(Event.location))
        .filter(Event.id == event_id)
        .first()
    )

    if not event:
        return RedirectResponse("/events", status_code=302)

    # Alle Locations der gleichen Source laden (für Dropdown)
    locations = (
        db.query(Location)
        .filter(Location.source_id == event.source_id)
        .order_by(Location.raw_name)
        .all()
    )

    return templates.TemplateResponse(
        "event_edit.html",
        {
            "request": request,
            "event": event,
            "locations": locations,
        },
    )


@router.post("/events/{event_id}/edit")
def save_event(
    event_id: int,
    title: str = Form(...),
    event_date: str = Form(...),
    event_time: str = Form(None),
    url: str = Form(None),
    raw_location: str = Form(None),
    location_id: str = Form(None),
    db: Session = Depends(get_db),
):
    """Event speichern."""
    from datetime import date as date_cls, time as time_cls

    event = db.query(Event).filter(Event.id == event_id).first()

    if event:
        event.title = title
        event.event_date = date_cls.fromisoformat(event_date)
        event.event_time = (
            time_cls.fromisoformat(event_time) if event_time else None
        )
        event.url = url or None
        event.raw_location = raw_location or None
        event.location_id = (
            int(location_id) if location_id and location_id.isdigit() else None
        )
        db.commit()

    return RedirectResponse("/events", status_code=302)


@router.get("/locations", response_class=HTMLResponse)
def locations_page(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Locations-Liste."""
    per_page = 25
    offset = (page - 1) * per_page

    query = db.query(Location).options(joinedload(Location.source))

    if status:
        query = query.filter(Location.status == status)

    if search:
        query = query.filter(
            (Location.raw_name.ilike(f"%{search}%")) |
            (Location.city.ilike(f"%{search}%"))
        )

    total = query.count()
    locations = query.order_by(Location.created_at.desc()).offset(offset).limit(per_page).all()

    total_pages = (total + per_page - 1) // per_page

    # Counts per status
    pending_count = db.query(Location).filter(Location.status == "pending").count()
    confirmed_count = db.query(Location).filter(Location.status == "confirmed").count()
    ignored_count = db.query(Location).filter(Location.status == "ignored").count()

    return templates.TemplateResponse(
        "locations.html",
        {
            "request": request,
            "locations": locations,
            "current_page": page,
            "total_pages": total_pages,
            "total": total,
            "status": status,
            "search": search or "",
            "pending_count": pending_count,
            "confirmed_count": confirmed_count,
            "ignored_count": ignored_count,
        },
    )


@router.get("/locations/{location_id}/edit", response_class=HTMLResponse)
def edit_location_page(
    request: Request,
    location_id: int,
    db: Session = Depends(get_db),
):
    """Location bearbeiten."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        return RedirectResponse("/locations", status_code=302)

    return templates.TemplateResponse(
        "location_edit.html",
        {
            "request": request,
            "location": location,
        },
    )


@router.post("/locations/{location_id}/edit")
def save_location(
    location_id: int,
    display_name: str = Form(None),
    street: str = Form(None),
    house_number: str = Form(None),
    postal_code: str = Form(None),
    city: str = Form(None),
    latitude: str = Form(None),
    longitude: str = Form(None),
    status: str = Form("pending"),
    db: Session = Depends(get_db),
):
    """Location speichern."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if location:
        location.display_name = display_name or None
        location.street = street or None
        location.house_number = house_number or None
        location.postal_code = postal_code or None
        location.city = city or None
        location.latitude = float(latitude) if latitude else None
        location.longitude = float(longitude) if longitude else None
        location.status = status
        db.commit()

    return RedirectResponse("/locations", status_code=302)


@router.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, db: Session = Depends(get_db)):
    """Sources-Liste."""
    sources = db.query(Source).all()

    # Stats für jede Source
    source_stats = []
    for source in sources:
        events_count = (
            db.query(Event)
            .filter(Event.source_id == source.id, Event.deleted_at == None)
            .count()
        )
        source_stats.append({
            "source": source,
            "events_count": events_count,
        })

    class_to_key = {cls.__name__: key for key, cls in SCRAPER_REGISTRY.items()}
    for item in source_stats:
        item["scraper_key"] = class_to_key.get(item["source"].scraper_class, "")

    return templates.TemplateResponse(
        "sources.html",
        {
            "request": request,
            "source_stats": source_stats,
        },
    )


@router.get("/scrape-logs", response_class=HTMLResponse)
def scrape_logs_page(
    request: Request,
    status: Optional[str] = None,
    source_id: Optional[int] = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Scrape Logs Übersicht."""
    per_page = 50
    offset = (page - 1) * per_page

    query = db.query(ScrapeLog).options(joinedload(ScrapeLog.source))

    if status:
        query = query.filter(ScrapeLog.status == status)

    if source_id:
        query = query.filter(ScrapeLog.source_id == source_id)

    total = query.count()
    logs = query.order_by(ScrapeLog.started_at.desc()).offset(offset).limit(per_page).all()

    total_pages = (total + per_page - 1) // per_page

    sources = db.query(Source).order_by(Source.name).all()

    return templates.TemplateResponse(
        "scrape_logs.html",
        {
            "request": request,
            "logs": logs,
            "sources": sources,
            "current_page": page,
            "total_pages": total_pages,
            "total": total,
            "status": status,
            "source_id": source_id,
        },
    )
