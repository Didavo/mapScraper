"""
Scraper für die Gemeinde Igersheim.
API: https://heimatinfo-api-platform.azurewebsites.net/export/events

Besonderheit: JSON-API (Heimatinfo-Plattform)
- Kein HTML-Parsing nötig
- Pagination via pageIndex/pageSize (max 50)
- Monatsweise Abfrage nötig (from/to Parameter)
- Abfrage der nächsten 6 Monate
"""

import re
import time
from calendar import monthrange
from datetime import date as date_class, time as time_class, datetime, timezone
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class IgersheimScraper(BaseScraper):
    """Scraper für Igersheim Veranstaltungen (Heimatinfo API)."""

    SOURCE_NAME = "Gemeinde Igersheim"
    BASE_URL = "https://www.igersheim.de"
    EVENTS_URL = "https://www.igersheim.de"

    # API-Endpunkt
    API_URL = "https://heimatinfo-api-platform.azurewebsites.net/export/events"
    API_CLIENT_ID = "f6857d5c-a6bc-4d18-9c87-0066c05cb80d"
    PAGE_SIZE = 50

    GEOCODE_REGION = "97999 Igersheim"

    def _generate_month_ranges(self) -> List[tuple]:
        """
        Erzeugt Start- und Enddatum für die nächsten 6 Monate.
        Returns: Liste von (from_iso, to_iso) Tupeln im UTC-Format.
        """
        today = date_class.today()
        ranges = []

        for i in range(6):
            # Monat berechnen (aktueller + i)
            month = today.month + i
            year = today.year
            while month > 12:
                month -= 12
                year += 1

            # Erster und letzter Tag des Monats
            _, last_day = monthrange(year, month)

            if i == 0:
                # Für den aktuellen Monat: ab heute
                from_date = today
            else:
                from_date = date_class(year, month, 1)

            to_date = date_class(year, month, last_day)

            # UTC-Format: from = Vortag 22:00 UTC (= 00:00 CET), to = letzter Tag 21:59:59 UTC (= 23:59:59 CET)
            from_iso = f"{from_date.isoformat()}T00:00:00.000Z"
            to_iso = f"{to_date.isoformat()}T21:59:59.999Z"

            ranges.append((from_iso, to_iso))

        return ranges

    def _build_api_url(self, from_iso: str, to_iso: str, page_index: int = 0) -> str:
        """Baut die API-URL mit den gegebenen Parametern."""
        return (
            f"{self.API_URL}"
            f"?pageSize={self.PAGE_SIZE}"
            f"&pageIndex={page_index}"
            f"&c={self.API_CLIENT_ID}"
            f"&from={from_iso}"
            f"&to={to_iso}"
        )

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den Scrape-Vorgang über die Heimatinfo JSON-API durch.
        Iteriert monatsweise über die nächsten 6 Monate.
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

            month_ranges = self._generate_month_ranges()
            print(f"[INFO] {len(month_ranges)} Monate zu scrapen")

            for from_iso, to_iso in month_ranges:
                print(f"[INFO] Lade Zeitraum: {from_iso[:10]} bis {to_iso[:10]}")

                page_index = 0
                while True:
                    url = self._build_api_url(from_iso, to_iso, page_index)
                    if debug:
                        print(f"[DEBUG] API-URL: {url}")

                    # Rate limiting
                    time.sleep(self.settings.request_delay)

                    response = self.http_session.get(url, timeout=30)
                    response.raise_for_status()
                    items = response.json()

                    if not items:
                        break

                    for item in items:
                        event = self._parse_api_event(item)
                        if event and event.external_id not in seen_event_keys:
                            seen_event_keys.add(event.external_id)
                            all_events.append(event)

                    print(f"[INFO]   Seite {page_index}: {len(items)} Events geladen")

                    # Pagination: Wenn weniger als pageSize zurückkommen, gibt es keine weiteren
                    if len(items) < self.PAGE_SIZE:
                        break

                    page_index += 1

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
        title = (item.get("title") or "").strip()
        if not title:
            return None

        # Datum aus startDate: "2026-03-04T07:00:00Z"
        start_date_str = item.get("startDate")
        if not start_date_str:
            return None

        try:
            start_dt = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            event_date = start_dt.date()
            event_time = start_dt.time().replace(second=0, microsecond=0)
            # Wenn Uhrzeit genau 00:00 ist, setzen wir sie auf None
            if event_time == time_class(0, 0):
                event_time = None
        except (ValueError, TypeError):
            return None

        # Enddatum
        event_end_date = None
        event_end_time = None
        end_date_str = item.get("endDate")
        if end_date_str:
            try:
                end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if end_dt.date() != event_date:
                    event_end_date = end_dt.date()
                event_end_time = end_dt.time().replace(second=0, microsecond=0)
                if event_end_time == time_class(0, 0):
                    event_end_time = None
            except (ValueError, TypeError):
                pass

        # External ID aus der UUID + URL
        event_id = item.get("id", "")
        external_id = f"igersheim_{event_id}"
        url = f"https://www.heimat-info.de/veranstaltungen/{event_id}" if event_id else None

        # Location: "Möhlerplatz 9 97999 Igersheim" oder "Kulturhaus, Pfarrgarten 3, 97999 Igersheim"
        raw_location = None
        location_street = None
        location_postal_code = None
        location_city = None

        location_str = (item.get("location") or "").strip()
        if location_str:
            raw_location = location_str
            # Versuche PLZ + Stadt zu extrahieren
            plz_match = re.search(r"(\d{5})\s+(\S+.*?)$", location_str)
            if plz_match:
                location_postal_code = plz_match.group(1)
                location_city = plz_match.group(2).strip()
                # Alles vor der PLZ als Straße
                street_part = location_str[:plz_match.start()].strip().rstrip(",")
                if street_part:
                    # Wenn ein Komma vorhanden, ist der erste Teil der Location-Name
                    # z.B. "Kulturhaus, Pfarrgarten 3" -> Straße = "Pfarrgarten 3"
                    if "," in street_part:
                        parts = street_part.split(",")
                        location_street = parts[-1].strip()
                    else:
                        location_street = street_part

        # Extra-Daten
        extra_data = {}
        content_preview = (item.get("contentPreview") or "").strip()
        if content_preview:
            extra_data["description"] = content_preview[:500]

        return ScrapedEvent(
            external_id=external_id,
            title=title,
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

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Standard parse_events - wird hier nicht direkt verwendet,
        da wir run() überschreiben, aber für Kompatibilität nötig.
        """
        return []
