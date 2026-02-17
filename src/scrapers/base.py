"""
Basis-Scraper Klasse für Event-Scraping.

Neue Scraper erben von dieser Klasse und überschreiben:
- SELECTORS: Dict mit CSS-Selektoren für die HTML-Elemente
- parse_events(): Parsing-Logik für die spezifische Website
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date, time as dt_time
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from decimal import Decimal

from src.config import get_settings
from src.models import Source, Event, Location, LocationStatus, GeocodingStatus, ScrapeLog, ScrapeStatus
from src.services.geocoding import GeocodingService


@dataclass
class ScrapedEvent:
    """Datenklasse für ein gescraptes Event."""

    external_id: str
    title: str
    event_date: date
    event_time: Optional[dt_time] = None
    event_end_date: Optional[date] = None
    event_end_time: Optional[dt_time] = None
    url: Optional[str] = None
    raw_location: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)

    # Optionale Location-Daten (z.B. von Detail-Seiten)
    location_street: Optional[str] = None
    location_postal_code: Optional[str] = None
    location_city: Optional[str] = None
    location_latitude: Optional[float] = None
    location_longitude: Optional[float] = None


class BaseScraper(ABC):
    """
    Abstrakte Basis-Klasse für alle Event-Scraper.

    Verwendung:
    1. Erbe von dieser Klasse
    2. Definiere SELECTORS mit den CSS-Selektoren
    3. Implementiere parse_events() für die Website-spezifische Logik
    """

    # Zu überschreiben in Subklassen
    SOURCE_NAME: str = ""
    BASE_URL: str = ""
    EVENTS_URL: str = ""
    GEOCODE_REGION: str = ""  # z.B. "74653 Künzelsau" für Google Geocoding

    # CSS-Selektoren - in Subklassen überschreiben
    SELECTORS: Dict[str, str] = {
        "event_container": "",  # Container für einzelne Events
        "title": "",  # Event-Titel
        "date": "",  # Datum
        "time": "",  # Uhrzeit (optional)
        "location": "",  # Veranstaltungsort (optional)
        "url": "",  # Link zur Detailseite (optional)
    }

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.source: Optional[Source] = None
        self.scrape_log: Optional[ScrapeLog] = None

        # Geocoding Statistiken pro Scrape-Lauf
        self._geo_success = 0
        self._geo_multiple = 0
        self._geo_not_found = 0
        self._geo_errors = 0

        # HTTP Session
        self.http_session = requests.Session()
        self.http_session.headers.update({"User-Agent": self.settings.user_agent})

    def get_or_create_source(self) -> Source:
        """Holt oder erstellt den Source-Eintrag in der Datenbank."""
        source = (
            self.session.query(Source).filter(Source.base_url == self.BASE_URL).first()
        )

        if not source:
            source = Source(
                name=self.SOURCE_NAME,
                base_url=self.BASE_URL,
                scraper_class=self.__class__.__name__,
            )
            self.session.add(source)
            self.session.commit()

        return source

    def start_scrape_log(self) -> ScrapeLog:
        """Startet einen neuen Scrape-Log Eintrag."""
        log = ScrapeLog(
            source_id=self.source.id,
            started_at=datetime.utcnow(),
            status=ScrapeStatus.RUNNING.value,
        )
        self.session.add(log)
        self.session.commit()
        return log

    def finish_scrape_log(
        self,
        status: ScrapeStatus,
        events_found: int = 0,
        events_new: int = 0,
        events_updated: int = 0,
        error_message: Optional[str] = None,
    ):
        """Beendet den Scrape-Log Eintrag."""
        if self.scrape_log:
            self.scrape_log.finished_at = datetime.utcnow()
            self.scrape_log.status = status.value
            self.scrape_log.events_found = events_found
            self.scrape_log.events_new = events_new
            self.scrape_log.events_updated = events_updated
            self.scrape_log.error_message = error_message
            self.scrape_log.geocoding_success = self._geo_success
            self.scrape_log.geocoding_multiple = self._geo_multiple
            self.scrape_log.geocoding_not_found = self._geo_not_found
            self.scrape_log.geocoding_errors = self._geo_errors
            self.session.commit()

        if self.source:
            self.source.last_scraped_at = datetime.utcnow()
            self.session.commit()

    def fetch_page(self, url: Optional[str] = None) -> BeautifulSoup:
        """Holt eine Seite und gibt BeautifulSoup-Objekt zurück."""
        target_url = url or self.EVENTS_URL

        # Rate limiting
        time.sleep(self.settings.request_delay)

        response = self.http_session.get(target_url, timeout=30)
        response.raise_for_status()

        return BeautifulSoup(response.content, "lxml")

    def resolve_url(self, relative_url: str) -> str:
        """Macht aus einer relativen URL eine absolute URL."""
        return urljoin(self.BASE_URL, relative_url)

    def location_exists(self, raw_name: str) -> bool:
        """
        Prüft ob eine Location bereits existiert.
        Nützlich um zu entscheiden, ob Detail-Seiten geladen werden müssen.
        """
        if not raw_name or not self.source:
            return False

        raw_name = raw_name.strip()

        return (
            self.session.query(Location)
            .filter(
                Location.source_id == self.source.id,
                Location.raw_name == raw_name
            )
            .first()
        ) is not None

    def get_or_create_location(
        self,
        raw_name: str,
        street: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Location:
        """
        Holt oder erstellt einen Location-Eintrag.
        Neue Locations bekommen status='pending' für manuelle Bearbeitung.

        Locations sind an die Source gebunden - "Stauseehalle" in Mulfingen
        ist nicht dieselbe wie "Stauseehalle" in Kupferzell.

        Optionale Location-Daten (street, postal_code, city, lat/lon) werden
        nur bei neu erstellten Locations verwendet.

        Wenn keine Koordinaten vorhanden sind, wird Google Geocoding API aufgerufen.
        """
        if not raw_name or not self.source:
            return None

        # Normalisiere den Namen
        raw_name = raw_name.strip()

        location = (
            self.session.query(Location)
            .filter(
                Location.source_id == self.source.id,
                Location.raw_name == raw_name
            )
            .first()
        )

        if not location:
            # Geocoding: Falls keine Koordinaten aus Scraping vorhanden
            geocoding_status = None
            if latitude is None or longitude is None:
                # Versuche Geocoding via Google API
                if self.GEOCODE_REGION:
                    geocoding_service = GeocodingService(
                        dry_run=self.settings.geocoding_dry_run
                    )
                    result = geocoding_service.geocode(raw_name, self.GEOCODE_REGION)

                    geocoding_status = result.status.value

                    # Geocoding-Statistiken tracken
                    if result.status == GeocodingStatus.SUCCESS:
                        self._geo_success += 1
                    elif result.status == GeocodingStatus.MULTIPLE:
                        self._geo_multiple += 1
                    elif result.status == GeocodingStatus.NOT_FOUND:
                        self._geo_not_found += 1
                    elif result.status == GeocodingStatus.ERROR:
                        self._geo_errors += 1

                    if result.status in (GeocodingStatus.SUCCESS, GeocodingStatus.MULTIPLE):
                        latitude = result.latitude
                        longitude = result.longitude
                else:
                    print(f"[WARN] Kein GEOCODE_REGION definiert für {self.__class__.__name__}")

            # Status: confirmed wenn Koordinaten vorhanden, sonst pending
            has_coordinates = latitude is not None and longitude is not None
            location_status = LocationStatus.CONFIRMED.value if has_coordinates else LocationStatus.PENDING.value

            location = Location(
                source_id=self.source.id,
                raw_name=raw_name,
                status=location_status,
                street=street.strip() if street else None,
                postal_code=postal_code.strip() if postal_code else None,
                city=city.strip() if city else None,
                latitude=Decimal(str(latitude)) if latitude else None,
                longitude=Decimal(str(longitude)) if longitude else None,
                geocoding_status=geocoding_status,
            )
            self.session.add(location)
            self.session.commit()

        return location

    def save_event(self, scraped: ScrapedEvent) -> tuple[Event, bool]:
        """
        Speichert ein Event in der Datenbank.
        Returns: (Event, is_new)
        """
        # Prüfe ob Event bereits existiert
        existing = (
            self.session.query(Event)
            .filter(
                Event.source_id == self.source.id,
                Event.external_id == scraped.external_id,
            )
            .first()
        )

        # Location verarbeiten
        location = None
        if scraped.raw_location:
            location = self.get_or_create_location(
                raw_name=scraped.raw_location,
                street=scraped.location_street,
                postal_code=scraped.location_postal_code,
                city=scraped.location_city,
                latitude=scraped.location_latitude,
                longitude=scraped.location_longitude,
            )

        if existing:
            # Update existierendes Event
            existing.title = scraped.title
            existing.event_date = scraped.event_date
            existing.event_time = scraped.event_time
            existing.event_end_date = scraped.event_end_date
            existing.event_end_time = scraped.event_end_time
            existing.url = scraped.url
            existing.raw_location = scraped.raw_location
            if location:
                existing.location_id = location.id
            existing.deleted_at = None  # Reaktiviere falls soft-deleted
            self.session.commit()
            return existing, False
        else:
            # Neues Event erstellen
            event = Event(
                source_id=self.source.id,
                external_id=scraped.external_id,
                title=scraped.title,
                event_date=scraped.event_date,
                event_time=scraped.event_time,
                event_end_date=scraped.event_end_date,
                event_end_time=scraped.event_end_time,
                url=scraped.url,
                raw_location=scraped.raw_location,
                location_id=location.id if location else None,
            )
            self.session.add(event)
            self.session.commit()
            return event, True

    @abstractmethod
    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst die Events aus dem HTML.
        Muss in jeder Subklasse implementiert werden.
        """
        pass

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den kompletten Scrape-Vorgang durch.
        Returns: Statistiken über den Scrape-Lauf
        """
        self.source = self.get_or_create_source()
        self.scrape_log = self.start_scrape_log()

        events_found = 0
        events_new = 0
        events_updated = 0
        skipped = 0

        try:
            # Seite laden
            soup = self.fetch_page()

            # Events parsen
            scraped_events = self.parse_events(soup)
            events_found = len(scraped_events)

            if debug:
                print(f"[DEBUG] Parsed {events_found} events from HTML")

            # Events speichern
            seen_ids = set()
            for i, scraped in enumerate(scraped_events):
                if debug:
                    print(f"[DEBUG] Event {i+1}: {scraped.title[:40]}... | ID: {scraped.external_id} | Date: {scraped.event_date}")

                # Duplikat-Check innerhalb eines Scrape-Laufs
                if scraped.external_id in seen_ids:
                    if debug:
                        print(f"  -> SKIPPED (duplicate ID in this run)")
                    skipped += 1
                    continue
                seen_ids.add(scraped.external_id)

                event, is_new = self.save_event(scraped)
                if is_new:
                    events_new += 1
                    if debug:
                        print(f"  -> NEW")
                else:
                    events_updated += 1
                    if debug:
                        print(f"  -> UPDATED")

            self.finish_scrape_log(
                ScrapeStatus.SUCCESS,
                events_found=events_found,
                events_new=events_new,
                events_updated=events_updated,
            )

            return {
                "status": "success",
                "source": self.SOURCE_NAME,
                "events_found": events_found,
                "events_new": events_new,
                "events_updated": events_updated,
                "skipped_duplicates": skipped,
            }

        except Exception as e:
            import traceback
            if debug:
                traceback.print_exc()
            self.finish_scrape_log(ScrapeStatus.FAILED, error_message=str(e))
            return {
                "status": "failed",
                "source": self.SOURCE_NAME,
                "error": str(e),
            }
