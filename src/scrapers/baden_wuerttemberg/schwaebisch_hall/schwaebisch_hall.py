"""
Scraper für die Stadt Schwäbisch Hall.
Website: https://www.schwaebischhall.de/de/kultur-tourismus/veranstaltungen/veranstaltungskalender

HTML-basierter Scraper mit Pagination und Detail-Seiten.
URL-Muster Übersicht: /seite-{n}/suche-none
Detail-Seiten enthalten Datum, Uhrzeit, Adresse, Koordinaten (Leaflet) und Veranstalter.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class SchwaebischHallScraper(BaseScraper):
    """Scraper für Schwäbisch Hall Veranstaltungen."""

    SOURCE_NAME = "Stadt Schwäbisch Hall"
    BASE_URL = "https://www.schwaebischhall.de"
    EVENTS_URL = "https://www.schwaebischhall.de/de/kultur-tourismus/veranstaltungen/veranstaltungskalender/seite-1/suche-none"

    GEOCODE_REGION = "74523 Schwäbisch Hall"
    MAX_PAGES = 75

    SELECTORS = {
        "event_container": "div.record[id^='hwveranstaltung__record__']",
        "title": "a.kalender_link_more span",
        "url": "a.kalender_link_more",
    }

    def _parse_german_date(self, date_str: str) -> Optional[date_class]:
        """Parst deutsches Datum: '15.02.2026' -> date(2026, 2, 15)"""
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
        """Parst Uhrzeit: '14:30 Uhr' -> time(14, 30). Gibt None bei 'Ganztägig'."""
        if "ganztägig" in time_str.lower():
            return None
        match = re.search(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Ermittelt die Gesamtanzahl der Seiten aus der Pagination."""
        pagination = soup.select_one("div.hw_pagination")
        if not pagination:
            return 1

        # "Letzte Seite" Link: TYPO3-Format mit currentPage=N
        max_page = 1
        for link in pagination.select("a.hw_button_square[href]"):
            href = link.get("href", "")
            # TYPO3 widget format: currentPage%5D=106
            match = re.search(r"currentPage%5D=(\d+)", href)
            if match:
                page_num = int(match.group(1))
                if page_num > max_page:
                    max_page = page_num

            # Simple format: /seite-N/
            match = re.search(r"/seite-(\d+)/", href)
            if match:
                page_num = int(match.group(1))
                if page_num > max_page:
                    max_page = page_num

        return max_page

    def _build_page_url(self, page: int) -> str:
        """Baut die URL für eine bestimmte Seite."""
        return f"{self.BASE_URL}/de/kultur-tourismus/veranstaltungen/veranstaltungskalender/seite-{page}/suche-none"

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Parst Events von allen Seiten (mit Pagination + Detail-Seiten)."""
        all_events = []
        seen_ids = set()

        total_pages = min(self._get_total_pages(soup), self.MAX_PAGES)
        print(f"[INFO] {total_pages} Seiten gefunden (Limit: {self.MAX_PAGES})")

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
        """Parst Events von einer einzelnen Seite (holt Detail-Seiten)."""
        events = []
        containers = soup.select(self.SELECTORS["event_container"])

        for container in containers:
            # URL und Event-ID aus der Listenseite holen
            url_el = container.select_one(self.SELECTORS["url"])
            if not url_el or not url_el.get("href"):
                continue

            event_url = self.resolve_url(url_el.get("href"))
            href = url_el.get("href", "")

            # Termin-ID aus URL: /termin-193043
            termin_match = re.search(r"termin-(\d+)", href)
            termin_id = termin_match.group(1) if termin_match else None

            # Event-ID aus Container: hwveranstaltung__record__3116
            container_id = container.get("id", "")
            id_match = re.search(r"__(\d+)$", container_id)
            record_id = id_match.group(1) if id_match else None

            # Deduplizierung via termin_id
            dedup_key = termin_id or record_id or event_url
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            # Detail-Seite laden
            try:
                detail_soup = self.fetch_page(event_url)
            except Exception:
                continue

            event = self._parse_detail_page(
                detail_soup, event_url, termin_id, record_id
            )
            if event and event.external_id not in seen_ids:
                seen_ids.add(event.external_id)
                events.append(event)

        return events

    def _parse_detail_page(
        self,
        soup: BeautifulSoup,
        event_url: str,
        termin_id: Optional[str],
        record_id: Optional[str],
    ) -> Optional[ScrapedEvent]:
        """Parst ein Event von der Detail-Seite."""

        # Titel
        title_el = soup.select_one("h3.hw_content__first_title span")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # Datum
        date_el = soup.select_one("span.hw_record__date .hw_record__value__text")
        if not date_el:
            return None
        event_date = self._parse_german_date(date_el.get_text(strip=True))
        if not event_date:
            return None

        # External ID
        if termin_id:
            external_id = f"schwaebisch_hall_{termin_id}_{event_date}"
        elif record_id:
            external_id = f"schwaebisch_hall_{record_id}_{event_date}"
        else:
            import hashlib
            hash_input = f"{title}_{event_date}".encode("utf-8")
            hash_id = hashlib.md5(hash_input).hexdigest()[:8]
            external_id = f"schwaebisch_hall_{hash_id}_{event_date}"

        # Uhrzeit
        event_time = None
        time_el = soup.select_one("span.hw_record__time .hw_record__value__text")
        if time_el:
            event_time = self._parse_time(time_el.get_text(strip=True))

        # Location aus simpleLocation (erste Zeile = Name)
        raw_location = None
        loc_el = soup.select_one(
            "span.hw_record__simpleLocation .hw_record__value__text"
        )
        if loc_el:
            # HTML enthält <br> Tags, erste Zeile ist der Location-Name
            loc_parts = []
            for part in loc_el.stripped_strings:
                loc_parts.append(part)
            if loc_parts:
                raw_location = loc_parts[0]

        # Koordinaten und Adresse aus Leaflet-Map data-Attributen
        latitude = None
        longitude = None
        location_street = None
        location_postal_code = None
        location_city = None

        map_div = soup.select_one("div.hw_map_location[data-lat]")
        if map_div:
            lat_str = map_div.get("data-lat", "")
            lng_str = map_div.get("data-lng", "")
            if lat_str and lng_str:
                try:
                    latitude = float(lat_str)
                    longitude = float(lng_str)
                except ValueError:
                    pass

            strasse = map_div.get("data-strasse", "").strip()
            hausnummer = map_div.get("data-hausnummer", "").strip()
            plz = map_div.get("data-plz", "").strip()
            ort = map_div.get("data-ort", "").strip()

            if strasse:
                location_street = (
                    f"{strasse} {hausnummer}".strip() if hausnummer else strasse
                )
            if plz:
                location_postal_code = plz
            if ort:
                location_city = ort
        else:
            # Fallback: Koordinaten aus OSM-Link
            osm_link = soup.select_one('a[href*="openstreetmap.org"]')
            if osm_link:
                href = osm_link.get("href", "")
                lat_match = re.search(r"mlat=([0-9.]+)", href)
                lon_match = re.search(r"mlon=([0-9.]+)", href)
                if lat_match and lon_match:
                    try:
                        latitude = float(lat_match.group(1))
                        longitude = float(lon_match.group(1))
                    except ValueError:
                        pass

            # Fallback: Adresse aus Apple Maps Link
            maps_link = soup.select_one('a[href*="maps.apple.com"]')
            if maps_link:
                href = maps_link.get("href", "")
                q_match = re.search(r"\?q=([^&]+)", href)
                if q_match:
                    parts = q_match.group(1).split(",")
                    if len(parts) >= 3:
                        street = parts[1].strip()
                        if street:
                            location_street = street
                        plz_city = parts[2].strip()
                        plz_match = re.match(r"(\d{5})\s*(.*)", plz_city)
                        if plz_match:
                            location_postal_code = plz_match.group(1)
                            city = plz_match.group(2).strip()
                            if city:
                                location_city = city

        # Veranstalter
        extra_data = {}
        organizer_el = soup.select_one(
            "span.hw_record__organizer .hw_record__value__text"
        )
        if organizer_el:
            extra_data["veranstalter"] = organizer_el.get_text(strip=True)

        # Kategorien
        categories = [
            tag.get_text(strip=True)
            for tag in soup.select("span.hw_tag")
            if tag.get_text(strip=True)
        ]
        if categories:
            extra_data["categories"] = categories

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=event_url,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            location_latitude=latitude,
            location_longitude=longitude,
            extra_data=extra_data,
        )
