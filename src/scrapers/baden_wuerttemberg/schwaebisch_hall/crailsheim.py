"""
Scraper für die Stadt Crailsheim.
Website: https://www.crailsheim.de

Verwendet das ZM-Veranstaltungsmodul mit Pagination.
Detail-Seiten werden für Location-Daten geladen.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class CrailsheimScraper(BaseScraper):
    """Scraper für Crailsheim Veranstaltungen."""

    SOURCE_NAME = "Stadt Crailsheim"
    BASE_URL = "https://www.crailsheim.de"
    EVENTS_URL = "https://www.crailsheim.de/site/Crailsheim/node/926013/page1/index.html"
    GEOCODE_REGION = "74564 Crailsheim"

    SELECTORS = {
        "event_container": "div.zmitem.vk-item",
        "title": "h3 a.titel",
        "date": "div.zmitem__time",
        "time": "span.dtTimeInfo",
        "url": "h3 a.titel",
    }

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Findet den 'Weiter' Link in der Pagination."""
        pagination = soup.select_one("ul.zmNavigClassInnen.pagination")
        if not pagination:
            return None

        for link in pagination.select("li.page-item a.page-link"):
            if link.get_text(strip=True) == "Weiter":
                href = link.get("href", "")
                if href:
                    return urljoin(self.BASE_URL, href)
        return None

    def _parse_date(self, date_text: str) -> Optional[date_class]:
        """Parst Datum aus Format 'Montag, 09.02.2026'."""
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_text)
        if match:
            try:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))
                return date_class(year, month, day)
            except ValueError:
                return None
        return None

    def _parse_time(self, time_text: str) -> Optional[time_class]:
        """Parst Uhrzeit aus Format '18.30 Uhr' (Punkt statt Doppelpunkt)."""
        match = re.search(r"(\d{1,2})\.(\d{2})", time_text)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _extract_event_id(self, url: str) -> Optional[str]:
        """Extrahiert die Event-ID aus der URL (zmdetail_XXXXX)."""
        match = re.search(r"zmdetail_(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _fetch_detail(self, url: str) -> dict:
        """
        Holt Location-Daten von der Event-Detailseite.

        Verwendet die vCard-Struktur für strukturierte Location-Daten:
        - div.vCard div.organization -> Location-Name (raw_location)
        - div.vCard div.street-address -> Straße
        - div.vCard span.postal-code -> PLZ
        - div.vCard span.locality -> Stadt
        - div.vCard a[href*="openstreetmap.org"] -> Koordinaten (mlat/mlon)
        - div.veranstalter_alternative .value -> Veranstalter
        """
        try:
            soup = self.fetch_page(url)
            details = {}

            # vCard mit strukturierten Location-Daten
            vcard = soup.select_one("div.vCard")
            if vcard:
                # Location-Name
                org = vcard.select_one("div.organization")
                if org:
                    details["raw_location"] = org.get_text(strip=True)

                # Straße
                street = vcard.select_one("div.street-address")
                if street:
                    details["street"] = street.get_text(strip=True)

                # PLZ und Stadt aus cityline
                postal = vcard.select_one("span.postal-code")
                city = vcard.select_one("span.locality")

                if postal:
                    postal_text = postal.get_text(strip=True)
                    # Manchmal enthält postal-code "74564 Crailsheim" statt nur "74564"
                    plz_match = re.match(r"(\d{5})\s*(.*)", postal_text)
                    if plz_match:
                        details["postal_code"] = plz_match.group(1)
                        # Falls keine separate locality, Stadt aus PLZ-Feld nehmen
                        if not city and plz_match.group(2):
                            details["city"] = plz_match.group(2).strip()

                if city:
                    details["city"] = city.get_text(strip=True)

                # Koordinaten aus OSM-Link
                osm_link = vcard.select_one('a[href*="openstreetmap.org"]')
                if osm_link:
                    href = osm_link.get("href", "")
                    lat_match = re.search(r"mlat=([0-9.]+)", href)
                    lon_match = re.search(r"mlon=([0-9.]+)", href)
                    if lat_match and lon_match:
                        details["latitude"] = float(lat_match.group(1))
                        details["longitude"] = float(lon_match.group(1))

            # Fallback: ort_alternative wenn kein vCard vorhanden
            if not details.get("raw_location"):
                ort_alt = soup.select_one("div.ort_alternative .value")
                if ort_alt:
                    ort_text = ort_alt.get_text(strip=True)
                    if ort_text:
                        details["raw_location"] = ort_text
                        # Versuche PLZ und Stadt aus dem Text zu extrahieren
                        plz_match = re.search(r"(\d{5})\s+(\S+)", ort_text)
                        if plz_match:
                            details["postal_code"] = plz_match.group(1)
                            details["city"] = plz_match.group(2)

            # Veranstalter
            veranstalter = soup.select_one("div.veranstalter_alternative .value")
            if veranstalter:
                details["veranstalter"] = veranstalter.get_text(strip=True)

            return details
        except Exception as e:
            print(f"[WARN] Detail-Seite konnte nicht geladen werden: {url} - {e}")
            return {}

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Parst Events von allen Seiten (mit Pagination)."""
        all_events = []
        seen_ids = set()
        current_soup = soup
        page_num = 1

        while True:
            print(f"[INFO] Crailsheim: Seite {page_num} wird geparst...")

            containers = current_soup.select(self.SELECTORS["event_container"])

            for container in containers:
                event = self._parse_single_event(container, seen_ids)
                if event:
                    seen_ids.add(event.external_id)
                    all_events.append(event)

            # Nächste Seite?
            next_url = self._get_next_page_url(current_soup)
            if not next_url:
                break

            page_num += 1
            current_soup = self.fetch_page(next_url)

        return all_events

    def _parse_single_event(self, container: Tag, seen_ids: set) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Container."""

        # Titel und URL
        title_el = container.select_one(self.SELECTORS["title"])
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title:
            return None

        relative_url = title_el.get("href", "")
        url = urljoin(self.BASE_URL, relative_url) if relative_url else None

        # Event-ID aus URL
        event_id = self._extract_event_id(relative_url)
        if not event_id:
            return None

        external_id = f"crailsheim_{event_id}"
        if external_id in seen_ids:
            return None

        # Datum
        date_el = container.select_one(self.SELECTORS["date"])
        if not date_el:
            return None

        event_date = self._parse_date(date_el.get_text(strip=True))
        if not event_date:
            return None

        # Uhrzeit
        event_time = None
        time_el = container.select_one(self.SELECTORS["time"])
        if time_el:
            event_time = self._parse_time(time_el.get_text(strip=True))

        # Detail-Seite für Location laden
        raw_location = None
        location_street = None
        location_postal_code = None
        location_city = None
        location_latitude = None
        location_longitude = None
        extra_data = {}

        if url:
            details = self._fetch_detail(url)
            raw_location = details.get("raw_location")
            location_street = details.get("street")
            location_postal_code = details.get("postal_code")
            location_city = details.get("city")
            location_latitude = details.get("latitude")
            location_longitude = details.get("longitude")
            if details.get("veranstalter"):
                extra_data["veranstalter"] = details["veranstalter"]

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            extra_data=extra_data,
        )
