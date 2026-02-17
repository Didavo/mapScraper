"""
Scraper für die Stadt Niederstetten.
Website: https://www.niederstetten.de/freizeit-kultur/kalender

HTML-basierter Scraper mit Pagination.
URL-Muster: /seite-{n}/suche-none
Events enthalten Datum, Location, Veranstalter und ggf. OSM-Koordinaten.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class NiederstettenScraper(BaseScraper):
    """Scraper für Niederstetten Veranstaltungen."""

    SOURCE_NAME = "Stadt Niederstetten"
    BASE_URL = "https://www.niederstetten.de"
    EVENTS_URL = "https://www.niederstetten.de/freizeit-kultur/kalender/seite-1/suche-none"

    GEOCODE_REGION = "97996 Niederstetten"

    SELECTORS = {
        "event_container": "div.hwveranstaltung__record",
        "title": "h3.hw_record__title span",
        "date": "div.hw_record__date .hw_record__value__text",
        "time": "div.hw_record__time .hw_record__value__text",
        "location": "div.hw_record__simpleLocation .hw_record__value__text",
        "url": "a.hw_record__more__show",
    }

    def _parse_german_date(self, date_str: str) -> Optional[date_class]:
        """Parst deutsches Datum: '21.02.2026' -> date(2026, 2, 21)"""
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
        """Parst Uhrzeit: '16:30 Uhr' -> time(16, 30)"""
        match = re.search(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _extract_coordinates(self, container: Tag) -> tuple:
        """Extrahiert Koordinaten aus dem OSM-Link im Event-Container."""
        osm_link = container.select_one('a[href*="openstreetmap.org"]')
        if osm_link:
            href = osm_link.get("href", "")
            lat_match = re.search(r"mlat=([0-9.]+)", href)
            lon_match = re.search(r"mlon=([0-9.]+)", href)
            if lat_match and lon_match:
                try:
                    return float(lat_match.group(1)), float(lon_match.group(1))
                except ValueError:
                    pass
        return None, None

    def _extract_address_from_maps_link(self, container: Tag) -> dict:
        """Extrahiert Adresse aus dem Apple Maps Link."""
        maps_link = container.select_one('a[href*="maps.apple.com"]')
        if not maps_link:
            return {}

        href = maps_link.get("href", "")
        q_match = re.search(r"\?q=([^&]+)", href)
        if not q_match:
            return {}

        parts = q_match.group(1).split(",")
        result = {}

        if len(parts) >= 3:
            street = parts[1].strip()
            if street:
                result["street"] = street

            plz_city = parts[2].strip()
            plz_match = re.match(r"(\d{5})\s*(.*)", plz_city)
            if plz_match:
                result["postal_code"] = plz_match.group(1)
                city = plz_match.group(2).strip()
                if city:
                    result["city"] = city

        return result

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Ermittelt die Gesamtanzahl der Seiten aus der Pagination."""
        pagination = soup.select_one("div.hw_pagination")
        if not pagination:
            return 1

        max_page = 1
        for link in pagination.select("a.hw_button_square[href]"):
            href = link.get("href", "")
            match = re.search(r"/seite-(\d+)/", href)
            if match:
                page_num = int(match.group(1))
                if page_num > max_page:
                    max_page = page_num

        return max_page

    def _build_page_url(self, page: int) -> str:
        """Baut die URL für eine bestimmte Seite."""
        return f"{self.BASE_URL}/freizeit-kultur/kalender/seite-{page}/suche-none"

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Parst Events von allen Seiten (mit Pagination)."""
        all_events = []
        seen_ids = set()

        total_pages = self._get_total_pages(soup)
        print(f"[INFO] {total_pages} Seiten gefunden")

        for page in range(1, total_pages + 1):
            if page == 1:
                page_soup = soup
            else:
                print(f"[INFO] Lade Seite {page}/{total_pages}")
                page_soup = self.fetch_page(self._build_page_url(page))

            page_events = self._parse_page_events(page_soup, seen_ids)
            all_events.extend(page_events)

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

        # External ID aus Container-ID: hwveranstaltung__record__1226 -> 1226
        container_id = container.get("id", "")
        id_match = re.search(r"__(\d+)$", container_id)
        if id_match:
            event_id = id_match.group(1)
        else:
            import hashlib
            hash_input = f"{title}".encode("utf-8")
            event_id = hashlib.md5(hash_input).hexdigest()[:8]

        # Datum
        date_el = container.select_one(self.SELECTORS["date"])
        if not date_el:
            return None
        event_date = self._parse_german_date(date_el.get_text(strip=True))
        if not event_date:
            return None

        # External ID mit Datum (für wiederkehrende Events)
        external_id = f"niederstetten_{event_id}_{event_date}"

        # Uhrzeit
        event_time = None
        time_el = container.select_one(self.SELECTORS["time"])
        if time_el:
            event_time = self._parse_time(time_el.get_text(strip=True))

        # URL
        url = None
        url_el = container.select_one(self.SELECTORS["url"])
        if url_el and url_el.get("href"):
            url = self.resolve_url(url_el.get("href"))

        # Location
        raw_location = None
        loc_el = container.select_one(self.SELECTORS["location"])
        if loc_el:
            raw_location = loc_el.get_text(strip=True)

        # Koordinaten aus OSM-Link
        latitude, longitude = self._extract_coordinates(container)

        # Adresse aus Apple Maps Link
        address = self._extract_address_from_maps_link(container)

        # Veranstalter
        extra_data = {}
        organizer_el = container.select_one("div.hw_record__organizer .hw_record__value__text")
        if organizer_el:
            extra_data["veranstalter"] = organizer_el.get_text(strip=True)

        # Kategorien
        categories = [
            tag.get_text(strip=True)
            for tag in container.select("span.hw_tag")
            if tag.get_text(strip=True)
        ]
        if categories:
            extra_data["categories"] = categories

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=raw_location,
            location_street=address.get("street"),
            location_postal_code=address.get("postal_code"),
            location_city=address.get("city"),
            location_latitude=latitude,
            location_longitude=longitude,
            extra_data=extra_data,
        )
