"""
API Endpoints für Locations.
"""

import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.models import Location, LocationStatus, Source
from ..dependencies import get_db
from ..schemas import LocationResponse, LocationUpdate

router = APIRouter()

# CSV-Spalten für Import/Export
LOCATION_CSV_FIELDS = [
    "id", "source_id", "source_name", "raw_name", "display_name",
    "street", "house_number", "postal_code", "city", "country",
    "latitude", "longitude", "status"
]


@router.get("", response_model=List[LocationResponse])
def list_locations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10000),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Liste aller Locations."""
    query = db.query(Location)

    if status:
        query = query.filter(Location.status == status)

    if search:
        query = query.filter(
            (Location.raw_name.ilike(f"%{search}%")) |
            (Location.city.ilike(f"%{search}%"))
        )

    query = query.order_by(Location.created_at.desc())
    return query.offset(skip).limit(limit).all()


@router.get("/pending", response_model=List[LocationResponse])
def list_pending_locations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Liste aller Locations mit Status 'pending'."""
    return (
        db.query(Location)
        .filter(Location.status == LocationStatus.PENDING.value)
        .order_by(Location.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/count")
def count_locations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Anzahl der Locations."""
    query = db.query(Location)

    if status:
        query = query.filter(Location.status == status)

    return {"count": query.count()}


@router.get("/{location_id}", response_model=LocationResponse)
def get_location(location_id: int, db: Session = Depends(get_db)):
    """Einzelne Location."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location nicht gefunden")

    return location


@router.put("/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: int,
    update: LocationUpdate,
    db: Session = Depends(get_db),
):
    """Location aktualisieren (Adresse eintragen)."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location nicht gefunden")

    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(location, key, value)

    db.commit()
    db.refresh(location)

    return location


@router.post("/{location_id}/confirm", response_model=LocationResponse)
def confirm_location(location_id: int, db: Session = Depends(get_db)):
    """Location als 'confirmed' markieren."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location nicht gefunden")

    location.status = LocationStatus.CONFIRMED.value
    db.commit()
    db.refresh(location)

    return location


@router.post("/{location_id}/ignore", response_model=LocationResponse)
def ignore_location(location_id: int, db: Session = Depends(get_db)):
    """Location als 'ignored' markieren."""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location nicht gefunden")

    location.status = LocationStatus.IGNORED.value
    db.commit()
    db.refresh(location)

    return location


@router.get("/export/csv")
def export_locations_csv(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Exportiert alle Locations als CSV-Datei."""
    query = db.query(Location).join(Source)

    if status:
        query = query.filter(Location.status == status)

    locations = query.order_by(Source.name, Location.raw_name).all()

    # CSV erstellen
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=LOCATION_CSV_FIELDS, delimiter=";")
    writer.writeheader()

    for loc in locations:
        writer.writerow({
            "id": loc.id,
            "source_id": loc.source_id,
            "source_name": loc.source.name if loc.source else "",
            "raw_name": loc.raw_name,
            "display_name": loc.display_name or "",
            "street": loc.street or "",
            "house_number": loc.house_number or "",
            "postal_code": loc.postal_code or "",
            "city": loc.city or "",
            "country": loc.country or "Deutschland",
            "latitude": str(loc.latitude) if loc.latitude else "",
            "longitude": str(loc.longitude) if loc.longitude else "",
            "status": loc.status,
        })

    # Als Download zurückgeben
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=locations.csv"}
    )


@router.get("/export/json")
def export_locations_json(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Exportiert alle Locations als JSON-Datei."""
    query = db.query(Location).join(Source)

    if status:
        query = query.filter(Location.status == status)

    locations = query.order_by(Source.name, Location.raw_name).all()

    data = []
    for loc in locations:
        data.append({
            "id": loc.id,
            "source_id": loc.source_id,
            "source_name": loc.source.name if loc.source else "",
            "raw_name": loc.raw_name,
            "display_name": loc.display_name or "",
            "street": loc.street or "",
            "house_number": loc.house_number or "",
            "postal_code": loc.postal_code or "",
            "city": loc.city or "",
            "country": loc.country or "Deutschland",
            "latitude": str(loc.latitude) if loc.latitude else "",
            "longitude": str(loc.longitude) if loc.longitude else "",
            "status": loc.status,
        })

    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=locations.json"}
    )


@router.post("/import")
async def import_locations(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Importiert Locations aus CSV oder JSON.
    Aktualisiert existierende Locations basierend auf der ID.
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Format erkennen
    if file.filename and file.filename.endswith(".json"):
        try:
            data = json.loads(content_str)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Ungültiges JSON: {e}")
    else:
        # CSV
        reader = csv.DictReader(io.StringIO(content_str), delimiter=";")
        data = list(reader)

    if not data:
        raise HTTPException(status_code=400, detail="Keine Daten in der Datei")

    updated = 0
    skipped = 0
    errors = []

    for row in data:
        try:
            location_id = int(row.get("id", 0))

            if not location_id:
                skipped += 1
                continue

            location = db.query(Location).filter(Location.id == location_id).first()

            if not location:
                skipped += 1
                continue

            # Felder aktualisieren
            changed = False

            if row.get("display_name"):
                location.display_name = row["display_name"]
                changed = True

            if row.get("street"):
                location.street = row["street"]
                changed = True

            if row.get("house_number"):
                location.house_number = row["house_number"]
                changed = True

            if row.get("postal_code"):
                location.postal_code = row["postal_code"]
                changed = True

            if row.get("city"):
                location.city = row["city"]
                changed = True

            if row.get("country"):
                location.country = row["country"]
                changed = True

            if row.get("latitude"):
                location.latitude = Decimal(row["latitude"])
                changed = True

            if row.get("longitude"):
                location.longitude = Decimal(row["longitude"])
                changed = True

            if row.get("status") and row["status"] in ["pending", "confirmed", "ignored"]:
                location.status = row["status"]
                changed = True

            if changed:
                location.updated_at = datetime.now(timezone.utc)
                updated += 1

        except Exception as e:
            errors.append(f"ID {row.get('id', '?')}: {str(e)}")

    db.commit()

    return {
        "message": "Import abgeschlossen",
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
