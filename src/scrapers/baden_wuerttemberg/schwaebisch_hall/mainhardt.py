"""
Scraper für die Gemeinde Mainhardt.
Website: https://www.mainhardt.de/kultur-freizeit-gaeste/veranstaltungen/kalender

HTML-basierter Scraper mit Pagination (TYPO3 hw_veranstaltung Extension).
Besonderheit: Leaflet-Karte mit data-Attributen für Koordinaten und Adresse.
Pagination via TYPO3 Widget-Parameter.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class MainhardtScraper(BaseScraper):
    """Scraper für Mainhardt Veranstaltungen."""

    SOURCE_NAME = "Gemeinde Mainhardt"
    BASE_URL = "https://www.mainhardt.de"
    EVENTS_URL = "https://www.mainhardt.de/kultur-freizeit-gaeste/veranstaltungen/kalender"

    GEOCODE_REGION = "74535 Mainhardt"

    SELECTORS = {
        "event_container": "div.record.record_list",
        "title": "h4.titel",
        "date": "div.list_icon_calendar",
        "time": "div.list_icon_clock",
        "location": "span.map_marker",
        "url": None,  # Keine Detail-URLs vorhanden
    }

    def _parse_german_date(self, date_str: str) -> Optional[date_class]:
        """Parst deutsches Datum: '12.02.2026' -> date(2026, 2, 12)"""
        match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            try:
                return date_class(
                    int(match.group(3)),
                    int(match.group(2)),
                    int(match.group(1)),
                )
            except ValueError:
                return None
        return None

    def _parse_time(self, time_str: str) -> Optional[time_class]:
        """Parst Uhrzeit: '19:00 Uhr' -> time(19, 0)"""
        match = re.search(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extrahiert die URL der nächsten Seite aus der Pagination."""
        pager = soup.select_one("ul.pager")
        if not pager:
            return None

        next_link = pager.select_one("li.next a[href]")
        if next_link:
            href = next_link.get("href", "")
            if href:
                return urljoin(self.BASE_URL, href)

        return None

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Ermittelt die Gesamtanzahl der Seiten aus der Pagination."""
        pager = soup.select_one("ul.pager")
        if not pager:
            return 1

        last_link = pager.select_one("li.last a[href]")
        if last_link:
            href = last_link.get("href", "")
            match = re.search(r"currentPage%5D=(\d+)", href)
            if not match:
                match = re.search(r"currentPage\]=(\d+)", href)
            if match:
                return int(match.group(1))

        return 1

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Parst Events von allen Seiten (folgt Next-Links für gültige cHash-URLs)."""
        all_events = []
        seen_ids = set()

        total_pages = self._get_total_pages(soup)
        print(f"[INFO] {total_pages} Seiten gefunden")

        page = 1
        page_soup = soup

        while True:
            print(f"[INFO] Parse Seite {page}/{total_pages}")
            page_events = self._parse_page_events(page_soup, seen_ids)
            all_events.extend(page_events)

            # Nächste Seite über den "Next"-Link holen (enthält gültigen cHash)
            next_url = self._get_next_page_url(page_soup)
            if not next_url:
                break

            page += 1
            print(f"[INFO] Lade Seite {page}/{total_pages}")
            page_soup = self.fetch_page(next_url)

        return all_events

    def _parse_page_events(
        self, soup: BeautifulSoup, seen_ids: set
    ) -> List[ScrapedEvent]:
        """Parst Events von einer einzelnen Seite."""
        events = []
        containers = soup.select(self.SELECTORS["event_container"])

        for container in containers:
            event = self._parse_single_event(container)
            if event and event.external_id not in seen_ids:
                seen_ids.add(event.external_id)
                events.append(event)

        return events

    def _parse_single_event(self, container: Tag) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Container."""

        # Titel
        title_el = container.select_one(self.SELECTORS["title"])
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # Datum
        date_el = container.select_one(self.SELECTORS["date"])
        if not date_el:
            return None
        event_date = self._parse_german_date(date_el.get_text(strip=True))
        if not event_date:
            return None

        # External ID aus Leaflet-Map-ID: hw_map4051 -> 4051
        map_div = container.select_one("div.hw_map[id]")
        if map_div:
            map_id = map_div.get("id", "")
            id_match = re.search(r"hw_map(\d+)", map_id)
            event_id = id_match.group(1) if id_match else None
        else:
            event_id = None

        if not event_id:
            import hashlib
            hash_input = f"{title}_{event_date}".encode("utf-8")
            event_id = hashlib.md5(hash_input).hexdigest()[:8]

        external_id = f"mainhardt_{event_id}_{event_date}"

        # Uhrzeit
        event_time = None
        event_end_time = None
        time_el = container.select_one(self.SELECTORS["time"])
        if time_el:
            time_text = time_el.get_text(strip=True)
            # "19:00 Uhr bis 21:00 Uhr"
            time_matches = re.findall(r"(\d{1,2}):(\d{2})", time_text)
            if time_matches:
                try:
                    event_time = time_class(int(time_matches[0][0]), int(time_matches[0][1]))
                except ValueError:
                    pass
            if len(time_matches) >= 2:
                try:
                    event_end_time = time_class(int(time_matches[1][0]), int(time_matches[1][1]))
                except ValueError:
                    pass

        # Location aus span.map_marker
        raw_location = None
        loc_el = container.select_one(self.SELECTORS["location"])
        if loc_el:
            raw_location = loc_el.get_text(strip=True)

        # Koordinaten und Adresse aus Leaflet-Map data-Attributen
        latitude = None
        longitude = None
        location_street = None
        location_postal_code = None
        location_city = None

        if map_div:
            # Koordinaten
            lat_str = map_div.get("data-lat", "")
            lng_str = map_div.get("data-lng", "")
            if lat_str and lng_str:
                try:
                    latitude = float(lat_str)
                    longitude = float(lng_str)
                except ValueError:
                    pass

            # Adresse
            strasse = map_div.get("data-strasse", "").strip()
            hausnummer = map_div.get("data-hausnummer", "").strip()
            plz = map_div.get("data-plz", "").strip()
            ort = map_div.get("data-ort", "").strip()

            if strasse:
                location_street = f"{strasse} {hausnummer}".strip() if hausnummer else strasse
            if plz:
                location_postal_code = plz
            if ort:
                location_city = ort

        # Veranstalter
        extra_data = {}
        organizer_el = container.select_one("span.person")
        if organizer_el:
            extra_data["veranstalter"] = organizer_el.get_text(strip=True)

        # Kategorien
        categories = [
            cat.get_text(strip=True).rstrip(",")
            for cat in container.select("span.category")
            if cat.get_text(strip=True)
        ]
        if categories:
            extra_data["categories"] = categories

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            event_end_time=event_end_time,
            url=self.EVENTS_URL,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            location_latitude=latitude,
            location_longitude=longitude,
            extra_data=extra_data,
        )
