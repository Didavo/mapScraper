"""
Scraper für die Stadt Künzelsau.
Website: https://kuenzelsau.de/freizeit+und+kultur/veranstaltungen
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class KuenzelsauScraper(BaseScraper):
    """Scraper für Künzelsau Veranstaltungen."""

    SOURCE_NAME = "Stadt Künzelsau"
    BASE_URL = "https://kuenzelsau.de"
    EVENTS_URL = "https://kuenzelsau.de/freizeit+und+kultur/veranstaltungen"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74653 Künzelsau"

    # CSS-Selektoren für Künzelsau
    SELECTORS = {
        "event_container": "article.zmitem",
        "title": "h3.titelzmtitel",
        "date": "span.dtstart",
        "time": "span.dtTimeInfo",
        "location": ".zmOrt .organization",
        "url": "footer a.details",
    }

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst deutsches Datumsformat: "Sonntag, 08.02.2026" oder "08.02.2026"
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

    def parse_iso_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst ISO-Datumsformat: "2026-02-08"
        """
        if not date_str:
            return None

        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str.strip())
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                return date_class(year, month, day)
            except ValueError:
                return None

        return None

    def parse_time(self, time_str: str) -> Optional[time_class]:
        """
        Parst Uhrzeitformat: "14:00 - 15:00" -> nimmt Startzeit
        """
        if not time_str:
            return None

        # Nimm die erste Uhrzeit (Startzeit)
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

        Künzelsau verwendet ein spezielles URL-Muster:
        /site/Kuenzelsau/node/494221/pageX/pageX?zm.sid=...

        Die Pagination ist in div.zmNavigClass und zeigt alle Seiten an.
        """
        urls = [self.EVENTS_URL]  # Erste Seite
        seen_pages = {1}

        # Suche nach Pagination-Container
        pagination = soup.select_one('.zmNavigClass')
        if not pagination:
            return urls

        # Finde alle Seiten-Links
        page_links = pagination.select('.zmNavigClassItem a')

        for link in page_links:
            href = link.get("href", "")
            if not href:
                continue

            # Extrahiere Seitennummer aus URL (/page2/, /page3/, etc.)
            match = re.search(r"/page(\d+)/", href)
            if match:
                page_num = int(match.group(1))
                if page_num not in seen_pages:
                    seen_pages.add(page_num)
                    # Vollständige URL erstellen
                    full_url = self.resolve_url(href)
                    urls.append(full_url)

        # Sortiere nach Seitennummer
        def get_page_num(url):
            match = re.search(r"/page(\d+)/", url)
            return int(match.group(1)) if match else 1

        urls.sort(key=get_page_num)

        return urls

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Parst Events von allen Seiten (mit Pagination falls vorhanden).
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
            # Versuche zuerst das title-Attribut (ISO-Format)
            title_attr = date_elem.get("title", "")
            if title_attr:
                event_date = self.parse_iso_date(title_attr)

            # Fallback: Text-Inhalt (deutsches Format)
            if not event_date:
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

        # Location extrahieren (raw_name aus Übersicht)
        location = None
        loc_elem = container.select_one(self.SELECTORS["location"])
        if loc_elem:
            location = loc_elem.get_text(strip=True)

        # External ID generieren
        external_id = self._generate_external_id(container, title, event_date, url)

        # Location-Details initialisieren
        location_street = None
        location_postal_code = None
        location_city = None
        location_latitude = None
        location_longitude = None

        # Wenn Location vorhanden und noch nicht in DB, lade Detail-Seite
        if location and url and not self.location_exists(location):
            print(f"[INFO] Lade Detail-Seite für neue Location: {location}")
            detail_data = self._fetch_location_details(url)
            if detail_data:
                location_street = detail_data.get("street")
                location_postal_code = detail_data.get("postal_code")
                location_city = detail_data.get("city")
                location_latitude = detail_data.get("latitude")
                location_longitude = detail_data.get("longitude")

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
        )

    def _fetch_location_details(self, detail_url: str) -> Optional[dict]:
        """
        Lädt die Detail-Seite und extrahiert Location-Informationen.

        Selektoren auf der Detail-Seite:
        - .street-address: Straße
        - .postal-code: PLZ
        - .locality: Stadt
        - OSM-Link mit mlat=...&mlon=... für Koordinaten
        """
        try:
            soup = self.fetch_page(detail_url)

            result = {}

            # Straße
            street_elem = soup.select_one(".street-address")
            if street_elem:
                result["street"] = street_elem.get_text(strip=True)

            # PLZ (kann "74653 Künzelsau" sein - nur PLZ extrahieren)
            postal_elem = soup.select_one(".postal-code")
            if postal_elem:
                postal_text = postal_elem.get_text(strip=True)
                # Extrahiere nur die Ziffern (PLZ)
                postal_match = re.match(r"(\d{5})", postal_text)
                if postal_match:
                    result["postal_code"] = postal_match.group(1)

            # Stadt
            city_elem = soup.select_one(".locality")
            if city_elem:
                result["city"] = city_elem.get_text(strip=True)

            # Koordinaten aus OSM-Link
            osm_link = soup.select_one('a[href*="openstreetmap.org"]')
            if osm_link:
                href = osm_link.get("href", "")
                lat_match = re.search(r"mlat=([0-9.]+)", href)
                lon_match = re.search(r"mlon=([0-9.]+)", href)
                if lat_match and lon_match:
                    result["latitude"] = float(lat_match.group(1))
                    result["longitude"] = float(lon_match.group(1))

            return result if result else None

        except Exception as e:
            print(f"[WARN] Fehler beim Laden der Detail-Seite {detail_url}: {e}")
            return None

    def _generate_external_id(
        self, container: Tag, title: str, event_date: date_class, url: Optional[str]
    ) -> str:
        """Generiert eine eindeutige ID für das Event."""

        # Methode 1: nodeID aus URL extrahieren
        if url:
            match = re.search(r"nodeID=(\d+)", url)
            if match:
                return f"{match.group(1)}_{event_date}"

            # Alternativ: zmdetail_ID aus URL
            match = re.search(r"zmdetail_(\d+)", url)
            if match:
                return f"{match.group(1)}_{event_date}"

        # Methode 2: iCal-Link prüfen
        ical_link = container.select_one('a[href*=".ics"]')
        if ical_link:
            href = ical_link.get("href", "")
            match = re.search(r"nodeID=(\d+)", href)
            if match:
                return f"{match.group(1)}_{event_date}"

        # Fallback: Hash aus Titel + Datum
        import hashlib
        hash_input = f"{title}_{event_date}".encode("utf-8")
        hash_id = hashlib.md5(hash_input).hexdigest()[:8]
        return f"kuenzelsau_{hash_id}_{event_date}"
