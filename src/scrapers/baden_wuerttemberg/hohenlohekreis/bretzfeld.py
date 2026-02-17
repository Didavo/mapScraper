"""
Scraper für die Gemeinde Bretzfeld.
Website: https://www.bretzfeld.de/freizeit-tourismus/termine-veranstaltungen/veranstaltungskalender
Pagination: /seite-X/
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class BretzfeldScraper(BaseScraper):
    """Scraper für Bretzfeld Veranstaltungen mit Pagination."""

    SOURCE_NAME = "Gemeinde Bretzfeld"
    BASE_URL = "https://www.bretzfeld.de"
    EVENTS_URL = "https://www.bretzfeld.de/freizeit-tourismus/termine-veranstaltungen/veranstaltungskalender/seite-1/suche-none"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74626 Bretzfeld"

    # CSS-Selektoren für Bretzfeld
    SELECTORS = {
        "event_container": ".hwveranstaltung__record",
        "title": "h3.hw_record__title span",
        "date": ".hw_record__date .hw_record__value__text",
        "time": ".hw_record__time .hw_record__value__text",
        "location": ".hw_record__simpleLocation .hw_record__value__text",
        "url": ".hw_record__more a",
        "osm_link": 'a.hw_record__map_link--desktop[href*="openstreetmap.org"]',
    }

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst deutsches Datumsformat: "05.03.2026"
        """
        if not date_str:
            return None

        date_str = date_str.strip()

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
        Parst Uhrzeitformat: "17:00 Uhr bis 23:00 Uhr" -> nimmt Startzeit
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

        Pagination-Struktur bei Bretzfeld:
        - Links mit class="hw_button hw_button_square" und title="Zur Seite X"
        - Aktive Seite ist ein <button> statt <a>
        """
        max_page = 1

        # Finde alle Pagination-Links mit "Zur Seite X" im Title
        pagination_links = soup.select('.hw_pagination a.hw_button[title^="Zur Seite"]')
        for link in pagination_links:
            href = link.get("href", "")
            match = re.search(r"/seite-(\d+)/", href)
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)

        # Generiere alle URLs
        base_pattern = "https://www.bretzfeld.de/freizeit-tourismus/termine-veranstaltungen/veranstaltungskalender/seite-{}/suche-none"
        urls = [base_pattern.format(page) for page in range(1, max_page + 1)]

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

        # URL extrahieren
        url = None
        url_elem = container.select_one(self.SELECTORS["url"])
        if url_elem and url_elem.get("href"):
            url = self.resolve_url(url_elem.get("href"))

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
            location = loc_elem.get_text(strip=True)

        # Koordinaten aus OSM-Link extrahieren
        location_latitude = None
        location_longitude = None
        osm_link = container.select_one(self.SELECTORS["osm_link"])
        if osm_link:
            href = osm_link.get("href", "")
            lat_match = re.search(r"mlat=([0-9.]+)", href)
            lon_match = re.search(r"mlon=([0-9.]+)", href)
            if lat_match and lon_match:
                location_latitude = float(lat_match.group(1))
                location_longitude = float(lon_match.group(1))

        # External ID generieren
        external_id = self._generate_external_id(container, title, event_date, url)

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=location,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
        )

    def _generate_external_id(
        self, container: Tag, title: str, event_date: date_class, url: Optional[str]
    ) -> str:
        """Generiert eine eindeutige ID für das Event."""

        # Methode 1: ID aus Container-Attribut (id="hwveranstaltung__record__638")
        container_id = container.get("id", "")
        match = re.search(r"__(\d+)$", container_id)
        if match:
            return f"{match.group(1)}_{event_date}"

        # Methode 2: ID aus URL extrahieren (/veranstaltungskalender/638/...)
        if url:
            match = re.search(r"/veranstaltungskalender/(\d+)/", url)
            if match:
                return f"{match.group(1)}_{event_date}"

        # Fallback: Hash aus Titel + Datum
        import hashlib
        hash_input = f"{title}_{event_date}".encode("utf-8")
        hash_id = hashlib.md5(hash_input).hexdigest()[:8]
        return f"bretzfeld_{hash_id}_{event_date}"
