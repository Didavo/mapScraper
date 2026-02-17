"""
Scraper für die Gemeinde Dörzbach.
Website: https://www.doerzbach.de/leben/veranstaltungen
Pagination: ?seite=X
"""

import re
from datetime import datetime, date as date_class, time as time_class
from typing import List, Optional
from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class DoerzbachScraper(BaseScraper):
    """Scraper für Dörzbach Veranstaltungen mit Pagination."""

    SOURCE_NAME = "Gemeinde Dörzbach"
    BASE_URL = "https://www.doerzbach.de"
    EVENTS_URL = "https://www.doerzbach.de/leben/veranstaltungen"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74677 Dörzbach"

    # CSS-Selektoren für Dörzbach
    SELECTORS = {
        "event_container": "article",
        "title": "h1.nk-headline span, .nk-headline--lg span",
        "date": ".fa-calendar",  # Parent enthält Datum
        "time": ".fa-clock",  # Falls vorhanden
        "location": ".fa-map-pin",  # Parent enthält Location
        "pagination_next": 'a[title="Zur nächsten Seite wechseln"]',
    }

    # Deutsche Wochentage und Monate
    WEEKDAYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]
    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
        "jan": 1, "feb": 2, "mär": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "okt": 10, "nov": 11, "dez": 12,
    }

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst deutsches Datumsformat: "So. 08.03.2026" oder "08.03.2026"
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Format: "So. 08.03.2026" oder "08.03.2026"
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
        Parst Uhrzeitformat: "18:00 Uhr" oder "18:00"
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

        Die Pagination zeigt nur einige Seiten an (1, ..., 20, 21).
        Wir finden die maximale Seitenzahl über den "Letzte Seite" Link
        (Icon: fa-chevrons-right) und generieren alle URLs.
        """
        max_page = 1

        # Methode 1: Finde den "Zur letzten Seite" Link (fa-chevrons-right Icon)
        last_page_icon = soup.select_one('span.fa-chevrons-right')
        if last_page_icon:
            # Der Link ist das Parent <a> Element
            last_page_link = last_page_icon.find_parent('a')
            if last_page_link and last_page_link.get('href'):
                match = re.search(r"seite=(\d+)", last_page_link.get('href'))
                if match:
                    max_page = int(match.group(1))

        # Methode 2 (Fallback): Finde höchste Seitennummer aus allen Links
        if max_page == 1:
            pagination_links = soup.select('a[href*="seite="]')
            for link in pagination_links:
                href = link.get("href", "")
                match = re.search(r"seite=(\d+)", href)
                if match:
                    page_num = int(match.group(1))
                    max_page = max(max_page, page_num)

        # Generiere alle URLs von Seite 1 bis max_page
        urls = []
        for page in range(1, max_page + 1):
            if page == 1:
                urls.append(self.EVENTS_URL)
            else:
                urls.append(f"{self.EVENTS_URL}?seite={page}")

        return urls

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst Events von allen Seiten (mit Pagination).
        """
        all_events = []
        seen_event_keys = set()

        # Erste Seite wurde bereits geladen
        page_urls = self.get_all_page_urls(soup)

        print(f"[INFO] {len(page_urls)} Seiten gefunden")

        for i, page_url in enumerate(page_urls):
            if i == 0:
                # Erste Seite haben wir schon
                page_soup = soup
            else:
                # Weitere Seiten laden
                print(f"[INFO] Lade Seite {i + 1}/{len(page_urls)}")
                page_soup = self.fetch_page(page_url)

            # Events auf dieser Seite parsen
            page_events = self._parse_page_events(page_soup, seen_event_keys)
            all_events.extend(page_events)

        return all_events

    def _parse_page_events(
        self, soup: BeautifulSoup, seen_keys: set
    ) -> List[ScrapedEvent]:
        """Parst Events von einer einzelnen Seite."""
        events = []

        # Finde alle Event-Container
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

        # URL extrahieren (Link im Container oder Parent)
        url = None
        link = container.find_parent("a") or container.find("a")
        if link and link.get("href"):
            url = self.resolve_url(link.get("href"))

        # Datum extrahieren
        event_date = None
        date_icon = container.select_one(self.SELECTORS["date"])
        if date_icon:
            # Das Datum steht im Parent-Element des Icons
            date_parent = date_icon.find_parent("li") or date_icon.find_parent("div")
            if date_parent:
                date_text = date_parent.get_text(strip=True)
                event_date = self.parse_german_date(date_text)

        if not event_date:
            # Fallback: Suche im gesamten Container nach Datum
            container_text = container.get_text()
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", container_text)
            if date_match:
                try:
                    event_date = date_class(
                        int(date_match.group(3)),
                        int(date_match.group(2)),
                        int(date_match.group(1)),
                    )
                except ValueError:
                    pass

        if not event_date:
            return None

        # Uhrzeit extrahieren
        event_time = None
        time_icon = container.select_one(self.SELECTORS["time"])
        if time_icon:
            time_parent = time_icon.find_parent("li") or time_icon.find_parent("div")
            if time_parent:
                time_text = time_parent.get_text(strip=True)
                event_time = self.parse_time(time_text)

        # Fallback: Uhrzeit im Datumstext suchen
        if not event_time and date_icon:
            date_parent = date_icon.find_parent("li") or date_icon.find_parent("div")
            if date_parent:
                date_text = date_parent.get_text(strip=True)
                event_time = self.parse_time(date_text)

        # Location extrahieren
        location = None
        loc_icon = container.select_one(self.SELECTORS["location"])
        if loc_icon:
            loc_parent = loc_icon.find_parent("li") or loc_icon.find_parent("div")
            if loc_parent:
                location = loc_parent.get_text(strip=True)
                # Icon-Text entfernen falls vorhanden
                location = re.sub(r"^\s*[\uf0d8\uf041]\s*", "", location).strip()

        # External ID generieren
        external_id = self._generate_external_id(title, event_date, url)

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=location,
        )

    def _generate_external_id(
        self, title: str, event_date: date_class, url: Optional[str]
    ) -> str:
        """Generiert eine eindeutige ID für das Event."""
        # Versuche ID aus URL zu extrahieren
        if url:
            # URL-Muster: /veranstaltungen/123/event-name
            match = re.search(r"/veranstaltungen/(\d+)/", url)
            if match:
                return f"{match.group(1)}_{event_date}"

        # Fallback: Hash aus Titel + Datum
        import hashlib
        hash_input = f"{title}_{event_date}".encode("utf-8")
        hash_id = hashlib.md5(hash_input).hexdigest()[:8]
        return f"doerzbach_{hash_id}_{event_date}"
