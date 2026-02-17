"""
Scraper für die Stadt Gaildorf.
Website: https://www.gaildorf.de/veranstaltungen

Events werden über eine JSON-API geladen, die HTML-Fragmente zurückliefert:
https://www.gaildorf.de/api/event/list/event-appointment?limit=1000

Die API liefert {"results": "<html>..."} - das HTML enthält card-basierte
Event-Container mit Datum, Uhrzeit, Location und Veranstalter.
"""

import re
import time
from datetime import date as date_class, datetime, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


# Deutsche Monatsnamen -> Monatszahl
MONTH_MAP = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}


class GaildorfScraper(BaseScraper):
    """Scraper für Gaildorf Veranstaltungen."""

    SOURCE_NAME = "Stadt Gaildorf"
    BASE_URL = "https://www.gaildorf.de"
    EVENTS_URL = "https://www.gaildorf.de/veranstaltungen"
    API_URL = "https://www.gaildorf.de/api/event/list/event-appointment?limit=1000"

    @property
    def api_url_with_date_filter(self) -> str:
        """API-URL mit Datumsfilter ab heute."""
        today = datetime.now().strftime("%Y-%m-%d 00:00:00")
        return f"{self.API_URL}&filters[date][from]={today}"
    GEOCODE_REGION = "74405 Gaildorf"

    SELECTORS = {
        "event_container": "article.card--event",
        "title": "h3.card-title a",
        "date": "time.card-date",
        "url": "h3.card-title a",
    }

    def _parse_datetime_attr(self, datetime_str: str) -> tuple:
        """
        Parst Datum und Uhrzeit aus dem datetime-Attribut.
        Format: '2026-02-10 20:00:00'
        Returns: (date, time) - time kann None sein.
        """
        event_date = None
        event_time = None

        match = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", datetime_str)
        if match:
            try:
                event_date = date_class(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
                hour, minute = int(match.group(4)), int(match.group(5))
                # Nur setzen wenn nicht Mitternacht (00:00 = wahrscheinlich kein echte Uhrzeit)
                if hour != 0 or minute != 0:
                    event_time = time_class(hour, minute)
            except ValueError:
                pass
        else:
            # Fallback: nur Datum
            date_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", datetime_str)
            if date_match:
                try:
                    event_date = date_class(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                except ValueError:
                    pass

        return event_date, event_time

    def _parse_time_text(self, time_text: str) -> Optional[time_class]:
        """Parst Uhrzeit aus Text wie '20:00 Uhr - 22:00 Uhr' oder '20:00 Uhr'."""
        match = re.search(r"(\d{1,2}):(\d{2})", time_text)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _extract_event_id(self, url: str) -> Optional[str]:
        """Extrahiert Event-ID aus der URL (appointment/event-appointmentXXXX)."""
        match = re.search(r"appointment(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _get_info_by_icon(self, container: Tag, icon_name: str) -> Optional[str]:
        """
        Findet Info-Text anhand des Icon-Namens in den d-flex Elementen.
        Icons: place.svg (Location), schedule.svg (Uhrzeit),
               perm_contact_calendar.svg (Veranstalter).
        """
        for div in container.select("div.d-flex"):
            img = div.select_one("img.icon__image")
            if img and icon_name in img.get("src", ""):
                # Text ist direkt im div, nach dem span
                text = div.get_text(strip=True)
                if text:
                    return text
        return None

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst Events von der Gaildorf JSON-API.

        Die API liefert {"results": "<html>..."} - das HTML wird mit
        BeautifulSoup geparst und die Events daraus extrahiert.
        soup wird hier ignoriert, da die API direkt aufgerufen wird.
        """
        # API aufrufen (Rate Limiting über fetch_page ist nicht nötig,
        # da wir die API nur einmal aufrufen)
        time.sleep(self.settings.request_delay)
        response = self.http_session.get(self.api_url_with_date_filter, timeout=30)
        response.raise_for_status()

        data = response.json()
        html_content = data.get("results", "")

        if not html_content:
            return []

        # HTML-Fragmente parsen
        api_soup = BeautifulSoup(html_content, "lxml")

        events = []
        seen_ids = set()
        # Cache für Detail-Seiten: gleicher Titel = gleiche Location
        detail_cache = {}

        containers = api_soup.select(self.SELECTORS["event_container"])

        for container in containers:
            event = self._parse_single_event(container, seen_ids, detail_cache)
            if event:
                seen_ids.add(event.external_id)
                events.append(event)

        return events

    def _fetch_detail(self, url: str) -> dict:
        """Holt Location-Daten von der Event-Detailseite."""
        try:
            soup = self.fetch_page(url)
            details = {}

            # Location-Zeile: "Veranstaltungsort" -> Venue + Adresse
            # Suche nach dem Location-Block auf der Detail-Seite
            for dt in soup.select("dt"):
                label = dt.get_text(strip=True)
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue

                if "Veranstaltungsort" in label or "Ort" in label:
                    details["raw_location"] = dd.get_text(strip=True)
                elif "Veranstalter" in label:
                    details["veranstalter"] = dd.get_text(strip=True)

            # Fallback: place-icon in detail page
            if not details.get("raw_location"):
                for div in soup.select("div.d-flex"):
                    img = div.select_one("img.icon__image")
                    if img and "place.svg" in img.get("src", ""):
                        details["raw_location"] = div.get_text(strip=True)
                        break

            return details
        except Exception as e:
            print(f"[WARN] Detail-Seite konnte nicht geladen werden: {url} - {e}")
            return {}

    def _parse_single_event(self, container: Tag, seen_ids: set, detail_cache: dict = None) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Card-Container."""

        # Titel und URL
        title_el = container.select_one(self.SELECTORS["title"])
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title:
            return None

        url = title_el.get("href", "")
        if url and not url.startswith("http"):
            url = self.resolve_url(url)
        # API liefert fehlerhafte URLs (z.B. gaildorf.de//Wochenmarkt-event-...)
        # Korrekte Struktur: gaildorf.de/Veranstaltungen/Wochenmarkt-event-...
        if url:
            url = re.sub(r'(?<!:)//', '/', url)
            # Pfad "/Veranstaltungen/" fehlt in API-URLs -> einfügen
            if "/Veranstaltungen/" not in url and "event-appointment" in url:
                url = url.replace(
                    "gaildorf.de/",
                    "gaildorf.de/Veranstaltungen/",
                    1,
                )

        # Event-ID aus URL
        event_id = self._extract_event_id(url) if url else None
        if not event_id:
            return None

        external_id = f"gaildorf_{event_id}"
        if external_id in seen_ids:
            return None

        # Datum und Uhrzeit aus datetime-Attribut
        date_el = container.select_one(self.SELECTORS["date"])
        if not date_el:
            return None

        datetime_attr = date_el.get("datetime", "")
        event_date, event_time = self._parse_datetime_attr(datetime_attr)
        if not event_date:
            return None

        # Uhrzeit aus Icon überschreibt datetime-Attribut (genauer)
        time_text = self._get_info_by_icon(container, "schedule.svg")
        if time_text:
            parsed = self._parse_time_text(time_text)
            if parsed:
                event_time = parsed

        # Location aus Icon-basiertem Info-Bereich
        raw_location = self._get_info_by_icon(container, "place.svg")

        # Veranstalter aus Card
        extra_data = {}
        veranstalter = self._get_info_by_icon(container, "perm_contact_calendar.svg")
        if veranstalter:
            extra_data["veranstalter"] = veranstalter

        # Detail-Seite laden wenn keine Location im Card
        # Cache nutzen: gleicher Titel = gleiche Location (z.B. 50x "Wochenmarkt")
        if not raw_location and url:
            if detail_cache is not None and title in detail_cache:
                details = detail_cache[title]
            else:
                details = self._fetch_detail(url)
                if detail_cache is not None:
                    detail_cache[title] = details
            raw_location = details.get("raw_location")
            if details.get("veranstalter") and not extra_data.get("veranstalter"):
                extra_data["veranstalter"] = details["veranstalter"]

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url or None,
            raw_location=raw_location,
            extra_data=extra_data,
        )
