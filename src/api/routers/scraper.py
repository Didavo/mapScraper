"""
API Endpoints für Scraper-Steuerung.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.models import Source, Event, Location, LocationStatus
from src.scrapers import MulfingenScraper, DoerzbachScraper, IngelfingenScraper, KuenzelsauScraper, ForchtenbergScraper, BretzfeldScraper, KrautheimScraper, KupferzellScraper, NeuensteinScraper, NiedernhallScraper, OehringenScraper, PfedelbachScraper, SchoentralScraper, WaldenburgScraper, WeissbachScraper, ZweiflingenScraper
from src.scrapers import BlaufeldenScraper, BraunsbachScraper, CrailsheimScraper, GaildorfScraper, GerabronnScraper, LangenburgScraper, MainhardtScraper, MichelfeldScraper, SchrozbergScraper, SchwaebischHallScraper, UntermuenkheimScraper
from src.scrapers import BadMergentheimScraper, BoxbergScraper, CrelingenScraper, IgersheimScraper, NiederstettenScraper, WeikersheimScraper
from ..dependencies import get_db
from ..schemas import ScrapeRequest, ScrapeResponse, StatsResponse

router = APIRouter()

# Registry der verfügbaren Scraper
SCRAPER_REGISTRY = {
    # Hohenlohekreis
    "mulfingen": MulfingenScraper,
    "doerzbach": DoerzbachScraper,
    "ingelfingen": IngelfingenScraper,
    "kuenzelsau": KuenzelsauScraper,
    "forchtenberg": ForchtenbergScraper,
    "bretzfeld": BretzfeldScraper,
    "krautheim": KrautheimScraper,
    "kupferzell": KupferzellScraper,
    "neuenstein": NeuensteinScraper,
    "niedernhall": NiedernhallScraper,
    "oehringen": OehringenScraper,
    "pfedelbach": PfedelbachScraper,
    "schoental": SchoentralScraper,
    "waldenburg": WaldenburgScraper,
    "weissbach": WeissbachScraper,
    "zweiflingen": ZweiflingenScraper,
    # Schwäbisch Hall
    "blaufelden": BlaufeldenScraper,
    "braunsbach": BraunsbachScraper,
    "crailsheim": CrailsheimScraper,
    "gaildorf": GaildorfScraper,
    "gerabronn": GerabronnScraper,
    "langenburg": LangenburgScraper,
    "mainhardt": MainhardtScraper,
    "michelfeld": MichelfeldScraper,
    "schwaebisch_hall": SchwaebischHallScraper,
    "schrozberg": SchrozbergScraper,
    "untermuenkheim": UntermuenkheimScraper,
    # Main-Tauber-Kreis
    "bad_mergentheim": BadMergentheimScraper,
    "boxberg": BoxbergScraper,
    "creglingen": CrelingenScraper,
    "igersheim": IgersheimScraper,
    "niederstetten": NiederstettenScraper,
    "weikersheim": WeikersheimScraper,
}


@router.get("/available")
def list_available_scrapers():
    """Liste aller verfügbaren Scraper."""
    return {
        "scrapers": list(SCRAPER_REGISTRY.keys()),
    }


@router.post("/run", response_model=ScrapeResponse)
def run_scraper(request: ScrapeRequest, db: Session = Depends(get_db)):
    """Scraper manuell ausführen."""
    source_name = request.source_name.lower()

    if source_name not in SCRAPER_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannter Scraper: {source_name}. Verfügbar: {list(SCRAPER_REGISTRY.keys())}",
        )

    scraper_class = SCRAPER_REGISTRY[source_name]
    scraper = scraper_class(db)

    result = scraper.run()

    return ScrapeResponse(**result)


@router.post("/run-all")
def run_all_scrapers(db: Session = Depends(get_db)):
    """Alle aktiven Scraper ausführen."""
    results = []

    for name, scraper_class in SCRAPER_REGISTRY.items():
        scraper = scraper_class(db)
        result = scraper.run()
        results.append(result)

    return {"results": results}


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """Gesamtstatistiken."""
    total_events = db.query(Event).filter(Event.deleted_at == None).count()
    total_sources = db.query(Source).count()
    total_locations = db.query(Location).count()
    pending_locations = (
        db.query(Location)
        .filter(Location.status == LocationStatus.PENDING.value)
        .count()
    )

    # Events pro Source
    sources = db.query(Source).all()
    events_by_source = {}
    for source in sources:
        count = (
            db.query(Event)
            .filter(Event.source_id == source.id, Event.deleted_at == None)
            .count()
        )
        events_by_source[source.name] = count

    return StatsResponse(
        total_events=total_events,
        total_sources=total_sources,
        total_locations=total_locations,
        pending_locations=pending_locations,
        events_by_source=events_by_source,
    )
