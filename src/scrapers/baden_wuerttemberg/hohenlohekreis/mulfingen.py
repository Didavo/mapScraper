"""
Scraper für die Gemeinde Mulfingen.
Website: https://www.mulfingen.de/veranstaltungen/index.php
"""

import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class MulfingenScraper(BaseScraper):
    """Scraper für Mulfingen Veranstaltungen."""

    SOURCE_NAME = "Gemeinde Mulfingen"
    BASE_URL = "https://www.mulfingen.de"
    EVENTS_URL = "https://www.mulfingen.de/veranstaltungen/index.php"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74673 Mulfingen"

    # CSS-Selektoren für Mulfingen
    SELECTORS = {
        "event_container": ".event-entry-new-2",
        "title": ".event-entry-new-2-headline a",
        "date": ".event-entry-new-2-date time[datetime]",
        "time": ".event-entry-new-2-daytime time",
        "location": ".event-entry-new-2-location",
        "url": ".event-entry-new-2-headline a",
}


    # Deutsche Monatsnamen für Datum-Parsing
    MONTH_NAMES = {
        "jan": 1, "januar": 1,
        "feb": 2, "februar": 2,
        "mär": 3, "märz": 3, "mar": 3,
        "apr": 4, "april": 4,
        "mai": 5,
        "jun": 6, "juni": 6,
        "jul": 7, "juli": 7,
        "aug": 8, "august": 8,
        "sep": 9, "september": 9,
        "okt": 10, "oktober": 10,
        "nov": 11, "november": 11,
        "dez": 12, "dezember": 12,
    }

    def parse_german_date(self, date_str: str) -> Optional[datetime]:
        """
        Parst deutsches Datumsformat: "04. Feb 2026" oder "04.02.2026"
        """
        if not date_str:
            return None

        date_str = date_str.strip().lower()

        # Format: "04. Feb 2026" oder "04. Februar 2026"
        match = re.match(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", date_str)
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            year = int(match.group(3))

            month = self.MONTH_NAMES.get(month_str)
            if month:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    return None

        # Format: "04.02.2026"
        match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            try:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))
                return datetime(year, month, day)
            except ValueError:
                return None

        return None

    def parse_time(self, time_str: str) -> Optional[datetime]:
        """
        Parst Uhrzeitformat: "18:00 Uhr" oder "18:00"
        """
        if not time_str:
            return None

        time_str = time_str.strip().lower()

        # Format: "18:00 Uhr" oder "18:00"
        match = re.match(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                return datetime(2000, 1, 1, hour, minute).time()
            except ValueError:
                return None

        return None

    def extract_external_id(self, url: str, event_date: str = None) -> str:
        """
        Extrahiert die externe ID aus der URL + Datum.
        URL-Format: /veranstaltungen/2787189/2026/02/04/yoga-fuer-ruecken.html

        Wiederkehrende Events haben die gleiche URL-ID aber unterschiedliche Daten,
        daher kombinieren wir ID + Datum für Eindeutigkeit.
        """
        if not url:
            return ""

        # Versuche die ID aus dem Pfad zu extrahieren
        match = re.search(r"/veranstaltungen/(\d+)/", url)
        base_id = match.group(1) if match else url

        # Kombiniere mit Datum für eindeutige ID
        if event_date:
            return f"{base_id}_{event_date}"

        return base_id

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst die Events von der Mulfingen-Website mit CSS-Selektoren.
        """
        from datetime import date as date_class, time as time_class

        events = []
        seen_event_keys = set()

        # Finde alle Event-Container
        containers = soup.select(self.SELECTORS["event_container"])

        for container in containers:
            # Title und URL
            title_elem = container.select_one(self.SELECTORS["title"])
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            href = title_elem.get("href", "")

            if not title or not href:
                continue

            # Datum aus dem datetime-Attribut
            date_elem = container.select_one(self.SELECTORS["date"])
            if not date_elem:
                continue

            datetime_attr = date_elem.get("datetime", "")
            if not datetime_attr:
                continue

            try:
                # Format: "2026-02-04"
                year, month, day = map(int, datetime_attr.split("-"))
                event_date = date_class(year, month, day)
            except (ValueError, AttributeError):
                continue

            # Event-ID aus URL extrahieren
            url_match = re.search(r"/veranstaltungen/(\d+)/", href)
            event_id = url_match.group(1) if url_match else href

            # Eindeutiger Schlüssel: ID + Datum
            event_key = f"{event_id}_{event_date}"
            if event_key in seen_event_keys:
                continue
            seen_event_keys.add(event_key)

            # URL absolut machen
            url = self.resolve_url(href)

            # Uhrzeit
            event_time = None
            time_elem = container.select_one(self.SELECTORS["time"])
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                time_match = re.match(r"(\d{1,2}):(\d{2})", time_text)
                if time_match:
                    try:
                        event_time = time_class(int(time_match.group(1)), int(time_match.group(2)))
                    except ValueError:
                        pass

            # Location
            location = None
            location_elem = container.select_one(self.SELECTORS["location"])
            if location_elem:
                location = location_elem.get_text(strip=True)

            events.append(ScrapedEvent(
                external_id=event_key,
                title=title,
                event_date=event_date,
                event_time=event_time,
                url=url,
                raw_location=location,
            ))

        return events

    def _extract_location_from_parent(self, parent: Tag, title_link: Tag) -> Optional[str]:
        """
        Extrahiert die Location aus dem Parent-Element.
        Die Location steht typischerweise in einem <strong> Tag vor dem Event-Link.
        """
        if not parent:
            return None

        # Methode 1: Suche <strong> Tag im Parent
        strong_tags = parent.find_all("strong")
        for strong in strong_tags:
            text = strong.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 150:
                # Ignoriere Datum/Zeit
                if re.match(r"^\d{1,2}\.\s*\w+\s*\d{4}", text):
                    continue
                if re.match(r"^\d{1,2}:\d{2}", text):
                    continue
                return text

        # Methode 2: Suche vorheriges <strong> Sibling des Links
        prev = title_link.find_previous_sibling("strong")
        if prev:
            text = prev.get_text(strip=True)
            if text and len(text) > 2:
                return text

        # Methode 3: Suche <strong> irgendwo vor dem Link im DOM
        prev_strong = title_link.find_previous("strong")
        if prev_strong and parent.find(prev_strong):
            text = prev_strong.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 150:
                if not re.match(r"^\d{1,2}\.\s*\w+\s*\d{4}", text):
                    return text

        # Methode 4: Fallback - Text vor dem Link
        full_text = parent.get_text(separator="\n", strip=True)
        title_text = title_link.get_text(strip=True)

        if title_text in full_text:
            parts = full_text.split(title_text)
            if parts[0]:
                lines = [l.strip() for l in parts[0].split("\n") if l.strip()]
                for line in reversed(lines):
                    if re.match(r"^\d{1,2}\.\s*\w+\s*\d{4}", line):
                        continue
                    if re.match(r"^\d{1,2}:\d{2}", line):
                        continue
                    if line.lower() in ["mehr", "details", "info"]:
                        continue
                    if len(line) > 2 and len(line) < 100:
                        return line

        return None

    def _find_events_by_links(self, soup: BeautifulSoup) -> List[Tag]:
        """
        Finde Events anhand der Veranstaltungs-Links.
        Jeder Link kann mehrfach vorkommen (wiederkehrende Events),
        daher keine Deduplizierung der URLs.
        """
        event_links = soup.find_all("a", href=re.compile(r"/veranstaltungen/\d+/"))

        # Sammle alle Parent-Elemente (auch wenn URL mehrfach vorkommt)
        parents = []
        seen_parents = set()

        for link in event_links:
            # Überspringe Bild-Links (nur Text-Links zählen)
            if link.find("img"):
                continue

            # Finde den nächsten sinnvollen Parent
            parent = link.find_parent(["div", "article", "section", "li", "p"])
            if parent:
                # Verwende id(parent) um das gleiche DOM-Element zu tracken
                parent_id = id(parent)
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    parents.append(parent)

        return parents

    def _parse_single_event(self, container: Tag) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Container."""

        # Titel und URL extrahieren
        title_elem = container.select_one(self.SELECTORS["title"])
        if not title_elem:
            # Fallback: Suche nach jedem Link zu Veranstaltungen
            title_elem = container.find("a", href=re.compile(r"/veranstaltungen/"))

        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        url = title_elem.get("href", "")

        if not title or not url:
            return None

        # URL absolut machen
        url = self.resolve_url(url)

        # Datum extrahieren (brauchen wir für external_id)
        date_elem = container.select_one(self.SELECTORS["date"])
        date_text = date_elem.get_text(strip=True) if date_elem else ""

        # Falls kein Datum-Element, suche im Text
        if not date_text:
            text = container.get_text()
            date_match = re.search(r"(\d{1,2}\.\s*\w+\s*\d{4})", text)
            if date_match:
                date_text = date_match.group(1)

        parsed_date = self.parse_german_date(date_text)
        if not parsed_date:
            return None

        # Externe ID extrahieren (mit Datum für wiederkehrende Events)
        external_id = self.extract_external_id(url, str(parsed_date.date()))
        if not external_id:
            return None

        # Uhrzeit extrahieren
        time_elem = container.select_one(self.SELECTORS["time"])
        time_text = time_elem.get_text(strip=True) if time_elem else ""

        # Falls keine Uhrzeit im Element, suche im Text
        if not time_text:
            text = container.get_text()
            time_match = re.search(r"(\d{1,2}:\d{2})\s*Uhr", text)
            if time_match:
                time_text = time_match.group(1)

        parsed_time = self.parse_time(time_text)

        # Location extrahieren - steht als Text VOR dem Event-Link
        location = self._extract_location(container, title_elem)

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=parsed_date.date(),
            event_time=parsed_time,
            url=url,
            raw_location=location,
        )

    def _extract_location(self, container: Tag, title_elem: Tag) -> Optional[str]:
        """
        Extrahiert die Location aus dem Container.
        Die Location steht als Text direkt vor dem Event-Link.
        """
        # Methode 1: CSS-Selektor versuchen
        location_elem = container.select_one(self.SELECTORS["location"])
        if location_elem:
            loc = location_elem.get_text(strip=True)
            if loc:
                return loc

        # Methode 2: Text vor dem Title-Link extrahieren
        # Hole den gesamten Text und extrahiere den Teil vor dem Titel
        full_text = container.get_text(separator="\n", strip=True)
        title_text = title_elem.get_text(strip=True)

        if title_text in full_text:
            # Text vor dem Titel
            parts = full_text.split(title_text)
            if parts[0]:
                lines = [l.strip() for l in parts[0].split("\n") if l.strip()]
                # Filtere Datumszeilen raus
                for line in lines:
                    # Ignoriere Zeilen die wie Datum aussehen
                    if re.match(r"^\d{1,2}\.\s*\w+\s*\d{4}", line):
                        continue
                    # Ignoriere Zeilen die nur Uhrzeit sind
                    if re.match(r"^\d{1,2}:\d{2}\s*Uhr?$", line):
                        continue
                    # Ignoriere "mehr" Links
                    if line.lower() == "mehr":
                        continue
                    # Das sollte die Location sein
                    if len(line) > 2:
                        return line

        # Methode 3: Vorheriges Sibling-Element prüfen
        prev = title_elem.find_previous_sibling(string=True)
        if prev:
            loc = prev.strip()
            if loc and len(loc) > 2 and not re.match(r"^\d", loc):
                return loc

        return None
