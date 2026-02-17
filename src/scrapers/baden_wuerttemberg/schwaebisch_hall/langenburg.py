"""
Scraper für die Stadt Langenburg.
API: https://api.cross-7.de/public/calendar/3232/events

Besonderheit: Eigene JSON-API (Cross-7 CMS) - gleiche Schnittstelle wie Öhringen.
- Kein HTML-Parsing nötig
- Pagination via pageNumber/pageSize
- Strukturierte Adressdaten direkt im JSON
"""

from datetime import date as date_class, time as time_class, datetime
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class LangenburgScraper(BaseScraper):
    """Scraper für Langenburg Veranstaltungen (Cross-7 Calendar API)."""

    SOURCE_NAME = "Stadt Langenburg"
    BASE_URL = "https://www.langenburg.de"
    EVENTS_URL = "https://www.langenburg.de/de/buerger/veranstaltungen/veranstaltungen-termine"

    # API-Endpunkt
    API_URL = "https://api.cross-7.de/public/calendar/3232/events"
    PAGE_SIZE = 150

    # Kategorie-IDs die ausgeschlossen werden sollen
    EXCLUDE_CATEGORY_IDS = [342456, 342455, 342454, 342457]

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74595 Langenburg"

    def _build_api_url(self, page: int = 1) -> str:
        """Baut die API-URL mit aktuellem Datum als 'from'-Parameter."""
        now = datetime.utcnow().strftime("%Y-%m-%dT00:00:00.000Z")
        url = (
            f"{self.API_URL}"
            f"?pageNumber={page}"
            f"&pageSize={self.PAGE_SIZE}"
        )
        for cat_id in self.EXCLUDE_CATEGORY_IDS:
            url += f"&excludeCategoryIds={cat_id}"
        url += f"&from={quote(now)}"
        return url

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den Scrape-Vorgang über die Cross-7 JSON-API durch.
        Überschreibt die BaseScraper.run() Methode.
        """
        self.source = self.get_or_create_source()
        self.scrape_log = self.start_scrape_log()

        events_found = 0
        events_new = 0
        events_updated = 0
        skipped = 0

        try:
            all_events = []
            seen_event_keys = set()
            page = 1

            while True:
                url = self._build_api_url(page)
                print(f"[INFO] Lade API Seite {page}: {url}")

                response = self.http_session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    event = self._parse_api_event(item)
                    if event and event.external_id not in seen_event_keys:
                        seen_event_keys.add(event.external_id)
                        all_events.append(event)

                print(f"[INFO] Seite {page}: {len(items)} Events geladen")

                # Pagination prüfen
                if not data.get("hasNextPage", False):
                    break

                page += 1

            # Events speichern
            events_found = len(all_events)
            if debug:
                print(f"[DEBUG] Gesamt: {events_found} Events gefunden")

            seen_ids = set()
            for scraped in all_events:
                if scraped.external_id in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(scraped.external_id)

                event, is_new = self.save_event(scraped)
                if is_new:
                    events_new += 1
                else:
                    events_updated += 1

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

    def _parse_api_event(self, item: Dict[str, Any]) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem API-JSON."""

        # Titel
        name = item.get("name", "").strip()
        if not name:
            return None

        # Datum parsen
        from_date_str = item.get("fromDate")
        if not from_date_str:
            return None

        try:
            event_date = date_class.fromisoformat(from_date_str)
        except (ValueError, TypeError):
            return None

        # Startzeit parsen
        event_time = self._parse_time(item.get("fromTime"))

        # Enddatum und -zeit
        event_end_date = None
        until_date_str = item.get("untilDate")
        if until_date_str and until_date_str != from_date_str:
            try:
                event_end_date = date_class.fromisoformat(until_date_str)
            except (ValueError, TypeError):
                pass

        event_end_time = self._parse_time(item.get("untilTime"))

        # URL konstruieren
        link = item.get("link", {})
        target_id = link.get("targetId")
        slug = link.get("slug", "")
        url = f"{self.BASE_URL}{slug}" if slug else self.EVENTS_URL

        # Adresse extrahieren - bevorzugt "Veranstaltungsort"
        raw_location = None
        location_street = None
        location_postal_code = None
        location_city = None

        addresses = item.get("addresses", [])
        # Zuerst nach "Veranstaltungsort" suchen, dann Fallback auf erste Adresse
        addr = None
        for a in addresses:
            if a.get("type") == "Veranstaltungsort":
                addr = a
                break
        if not addr and addresses:
            addr = addresses[0]

        if addr:
            addr_name = addr.get("name", "").strip()
            street = addr.get("street", "").strip()
            house_number = addr.get("houseNumber", "").strip()
            zip_code = addr.get("zipCode", "").strip()
            city = addr.get("city", "").strip()

            # raw_location = Name der Location
            if addr_name:
                raw_location = addr_name

            # Straße mit Hausnummer
            if street:
                location_street = f"{street} {house_number}".strip() if house_number else street

            location_postal_code = zip_code or None
            location_city = city or None

        # External ID: targetId + Datum (für wiederkehrende Events)
        if target_id:
            external_id = f"langenburg_{target_id}_{event_date}"
        else:
            import hashlib
            hash_input = f"{name}_{event_date}".encode("utf-8")
            hash_id = hashlib.md5(hash_input).hexdigest()[:8]
            external_id = f"langenburg_{hash_id}_{event_date}"

        # Kategorien als extra_data
        categories = [
            cat.get("name", "")
            for cat in item.get("categoryNames", [])
            if cat.get("name")
        ]

        extra_data = {}
        if categories:
            extra_data["categories"] = categories
        teaser = item.get("teaserText", "").strip()
        if teaser:
            extra_data["description"] = teaser

        return ScrapedEvent(
            external_id=external_id,
            title=name,
            event_date=event_date,
            event_time=event_time,
            event_end_date=event_end_date,
            event_end_time=event_end_time,
            url=url,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            extra_data=extra_data,
        )

    def _parse_time(self, time_str: Optional[str]) -> Optional[time_class]:
        """Parst Zeitformat: '17:00:00' -> time(17, 0)"""
        if not time_str:
            return None

        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            return time_class(hour, minute)
        except (ValueError, IndexError):
            return None

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Standard parse_events - wird hier nicht direkt verwendet,
        da wir run() überschreiben, aber für Kompatibilität nötig.
        """
        return []
