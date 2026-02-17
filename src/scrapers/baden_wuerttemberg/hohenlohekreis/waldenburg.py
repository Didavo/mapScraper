"""
Scraper für die Stadt Waldenburg (Hohenlohe).
Website: https://www.waldenburg-hohenlohe.de/freizeit-gaeste-kultur/freizeit/veranstaltungskalender
Pagination: TYPO3-basiert mit tx_hwveranstaltung widget
Anderes CMS als die anderen Hohenlohekreis-Gemeinden.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class WaldenburgScraper(BaseScraper):
    """Scraper für Waldenburg Veranstaltungen mit Pagination."""

    SOURCE_NAME = "Stadt Waldenburg"
    BASE_URL = "https://www.waldenburg-hohenlohe.de"
    EVENTS_URL = "https://www.waldenburg-hohenlohe.de/freizeit-gaeste-kultur/freizeit/veranstaltungskalender"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74638 Waldenburg"

    # CSS-Selektoren für Waldenburg (TYPO3 CMS)
    SELECTORS = {
        "event_container": "div.record",
        "title": "h3.titel",
        "date": "div.list_icon_calendar",
        "time": "div.list_icon_clock",
        "location": "div.list_icon_map_marker",
    }

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst deutsches Datumsformat: "06.02.2026"
        """
        if not date_str:
            return None

        match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            try:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))
                return date_class(year, month, day)
            except ValueError:
                return None

        return None

    def parse_time(self, time_str: str) -> Optional[time_class]:
        """
        Parst Uhrzeitformat: "20:00 Uhr" -> 20:00
        """
        if not time_str:
            return None

        match = re.search(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                return time_class(hour, minute)
            except ValueError:
                return None

        return None

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Findet den 'Nächste Seite' Link in der Pagination.
        TYPO3 nutzt cHash-Validierung, daher dürfen URLs nicht manipuliert werden.
        """
        next_link = soup.select_one('ul.pager li.next a')
        if next_link:
            href = next_link.get("href", "")
            if href:
                return urljoin(self.BASE_URL, href)
        return None

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst Events von allen Seiten (Seite-für-Seite-Navigation).
        Folgt dem 'Nächste Seite' Link statt URLs zu konstruieren.
        """
        all_events = []
        seen_event_keys = set()
        page = 1
        current_soup = soup
        max_pages = 20  # Sicherheitslimit

        while page <= max_pages:
            print(f"[INFO] Parse Seite {page}")
            page_events = self._parse_page_events(current_soup, seen_event_keys)
            all_events.extend(page_events)

            # Nächste Seite?
            next_url = self._get_next_page_url(current_soup)
            if not next_url:
                break

            page += 1
            print(f"[INFO] Lade Seite {page}")
            current_soup = self.fetch_page(next_url)

        print(f"[INFO] {page} Seiten verarbeitet")
        return all_events

    def _parse_page_events(
        self, soup: BeautifulSoup, seen_keys: set
    ) -> List[ScrapedEvent]:
        """Parst Events von einer einzelnen Seite."""
        events = []

        containers = soup.select(self.SELECTORS["event_container"])

        for container in containers:
            event = self._parse_single_event(container)
            if event and event.external_id not in seen_keys:
                seen_keys.add(event.external_id)
                events.append(event)

        return events

    def _parse_single_event(self, container: Tag) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Container."""

        # Titel extrahieren
        title_elem = container.select_one(self.SELECTORS["title"])
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        # Datum extrahieren
        event_date = None
        date_elem = container.select_one(self.SELECTORS["date"])
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            event_date = self.parse_german_date(date_text)

        if not event_date:
            return None

        # Uhrzeit extrahieren
        event_time = None
        time_elem = container.select_one(self.SELECTORS["time"])
        if time_elem:
            time_text = time_elem.get_text(strip=True)
            event_time = self.parse_time(time_text)

        # Location extrahieren
        location = None
        loc_elem = container.select_one(self.SELECTORS["location"])
        if loc_elem:
            location_text = loc_elem.get_text(strip=True)
            # Entferne "Veranstaltungsort:" Label
            location = re.sub(r'^Veranstaltungsort:\s*', '', location_text)

        # External ID generieren
        external_id = self._generate_external_id(title, event_date)

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=None,  # Keine Detail-URLs sichtbar
            raw_location=location,
        )

    def _generate_external_id(
        self, title: str, event_date: date_class
    ) -> str:
        """Generiert eine eindeutige ID für das Event."""
        # Hash aus Titel + Datum (keine spezifische Event-ID im HTML)
        import hashlib
        hash_input = f"{title}_{event_date}".encode("utf-8")
        hash_id = hashlib.md5(hash_input).hexdigest()[:8]
        return f"waldenburg_{hash_id}_{event_date}"
