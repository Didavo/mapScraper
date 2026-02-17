"""
Scraper für die Gemeinde Schöntal.
Website: https://www.schoental.de/de/tourismus/veranstaltungskalender
Pagination: ?publish[start]=X
Anderes CMS als die anderen Hohenlohekreis-Gemeinden.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class SchoentralScraper(BaseScraper):
    """Scraper für Schöntal Veranstaltungen mit Pagination."""

    SOURCE_NAME = "Gemeinde Schöntal"
    BASE_URL = "https://www.schoental.de"
    EVENTS_URL = "https://www.schoental.de/de/tourismus/veranstaltungskalender"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74214 Schöntal"

    # CSS-Selektoren für Schöntal (anderes CMS)
    SELECTORS = {
        "event_container": "div.list",
        "title": "div.headline",
        "date_block": "div.timeBlock",
        "location": "div.location",
        "event_id_anchor": "a[id^='event']",
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
        Parst Uhrzeitformat: "um 14:00 Uhr" -> 14:00
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

    def get_all_page_urls(self, soup: BeautifulSoup) -> List[str]:
        """
        Ermittelt alle Seiten-URLs aus der Pagination.

        Pagination-Struktur bei Schöntal:
        - Links mit title="Seite X"
        - Letzter Seiten-Link in eckigen Klammern: [16]
        """
        max_page = 1

        # Finde den letzten Seiten-Link (Format: [16])
        pagination = soup.select_one('.controlBlockPageSlider')
        if pagination:
            # Suche nach Link mit [X] Format (letzte Seite)
            last_page_links = pagination.select('a[title^="Seite"]')
            for link in last_page_links:
                text = link.get_text(strip=True)
                # Check for [X] format
                bracket_match = re.match(r'\[(\d+)\]', text)
                if bracket_match:
                    max_page = int(bracket_match.group(1))
                    break

            # Fallback: Finde höchste Seitennummer aus allen Links
            if max_page == 1:
                for link in last_page_links:
                    title = link.get("title", "")
                    match = re.search(r"Seite (\d+)", title)
                    if match:
                        page_num = int(match.group(1))
                        max_page = max(max_page, page_num)

        # Generiere alle URLs
        # Format: index.php?id=20&publish[p]=20&publish[start]=X
        urls = [self.EVENTS_URL]  # Seite 1 ist die Basis-URL
        for page in range(2, max_page + 1):
            url = f"{self.EVENTS_URL}?publish[p]=20&publish[start]={page}"
            urls.append(url)

        return urls

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst Events von allen Seiten (mit Pagination).
        """
        all_events = []
        seen_event_keys = set()

        page_urls = self.get_all_page_urls(soup)

        print(f"[INFO] {len(page_urls)} Seiten gefunden")

        for i, page_url in enumerate(page_urls):
            if i == 0:
                page_soup = soup
            else:
                print(f"[INFO] Lade Seite {i + 1}/{len(page_urls)}")
                page_soup = self.fetch_page(page_url)

            page_events = self._parse_page_events(page_soup, seen_event_keys)
            all_events.extend(page_events)

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

        # Datum und Uhrzeit aus timeBlock extrahieren
        event_date = None
        event_time = None
        date_block = container.select_one(self.SELECTORS["date_block"])
        if date_block:
            block_text = date_block.get_text(" ", strip=True)
            event_date = self.parse_german_date(block_text)
            event_time = self.parse_time(block_text)

        if not event_date:
            return None

        # Location extrahieren
        location = None
        loc_elem = container.select_one(self.SELECTORS["location"])
        if loc_elem:
            location_text = loc_elem.get_text(strip=True)
            # Entferne "Ort:" Prefix
            location = re.sub(r'^Ort:\s*', '', location_text)

        # External ID aus Anchor extrahieren
        external_id = self._generate_external_id(container, title, event_date)

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=None,  # Keine Detail-URLs in diesem CMS
            raw_location=location,
        )

    def _generate_external_id(
        self, container: Tag, title: str, event_date: date_class
    ) -> str:
        """Generiert eine eindeutige ID für das Event."""

        # Methode 1: ID aus Anchor-Element (id="event58837626")
        anchor = container.select_one(self.SELECTORS["event_id_anchor"])
        if anchor:
            anchor_id = anchor.get("id", "")
            match = re.search(r'event(\d+)', anchor_id)
            if match:
                return f"{match.group(1)}_{event_date}"

        # Fallback: Hash aus Titel + Datum
        import hashlib
        hash_input = f"{title}_{event_date}".encode("utf-8")
        hash_id = hashlib.md5(hash_input).hexdigest()[:8]
        return f"schoental_{hash_id}_{event_date}"
