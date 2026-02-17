"""
Scraper für die Stadt Weikersheim.
Website: https://www.weikersheim.de

HTML-basierter Scraper mit Pagination (KOMM.ONE CMS).
URL-Muster: /node/3502554/page{N}/page{N}?zm.sid=...
Events enthalten Datum, Uhrzeit, Location und Kategorie.
"""

import re
from datetime import date as date_class, time as time_class
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent


class WeikersheimScraper(BaseScraper):
    """Scraper für Weikersheim Veranstaltungen (KOMM.ONE CMS)."""

    SOURCE_NAME = "Stadt Weikersheim"
    BASE_URL = "https://www.weikersheim.de"
    EVENTS_URL = "https://www.weikersheim.de/site/Weikersheim-Layout/node/3502554/azlist/index.html?zm.sid=zmj1si9fnbi2"

    GEOCODE_REGION = "97990 Weikersheim"

    SELECTORS = {
        "event_container": "div.zmitem",
        "title": "h3 a.titel",
        "date_time": "div.zmitem__time",
        "time": "span.dtTimeInfo",
        "location": "div.location",
        "url": "h3 a.titel[href]",
    }

    def _parse_german_date(self, date_str: str) -> Optional[date_class]:
        """Parst deutsches Datum: '05.04.2026' -> date(2026, 4, 5)"""
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
        """Parst Uhrzeit mit Punkt-Format: '14.30' oder '14:30' -> time(14, 30)"""
        match = re.search(r"(\d{1,2})[.:](\d{2})", time_str)
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                return None
        return None

    def _extract_id_from_url(self, url: str) -> Optional[str]:
        """Extrahiert die ID aus der Event-URL: zmdetail_668499224 -> 668499224"""
        match = re.search(r"zmdetail_(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Ermittelt die Gesamtanzahl der Seiten aus der Pagination."""
        pagination = soup.select_one("div.zmNavigClass")
        if not pagination:
            return 1

        max_page = 1
        for link in pagination.select("a[href]"):
            href = link.get("href", "")
            match = re.search(r"/page(\d+)/", href)
            if match:
                page_num = int(match.group(1))
                if page_num > max_page:
                    max_page = page_num

        return max_page

    def _build_page_url(self, page: int) -> str:
        """Baut die URL für eine bestimmte Seite."""
        return f"{self.BASE_URL}/site/Weikersheim-Layout/node/3502554/page{page}/page{page}?zm.sid=zmj1si9fnbi2"

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

        # Titel + URL
        link_el = container.select_one(self.SELECTORS["title"])
        if not link_el:
            return None
        title = link_el.get_text(strip=True)
        if not title:
            return None

        href = link_el.get("href", "")
        url = self.resolve_url(href) if href else None

        # External ID aus URL: zmdetail_668499224 -> 668499224
        event_id = self._extract_id_from_url(href) if href else None
        if not event_id:
            import hashlib
            hash_input = f"{title}".encode("utf-8")
            event_id = hashlib.md5(hash_input).hexdigest()[:8]

        # Datum + Uhrzeit aus zmitem__time
        # Format: "Sonntag, 05.04.2026  14.30 - 16.00 Uhr"
        # Oder mit span: "Sonntag, 05.04.2026  <span class="dtTimeInfo">14.30 - 16.00 Uhr</span>"
        event_date = None
        event_time = None
        event_end_time = None

        date_el = container.select_one(self.SELECTORS["date_time"])
        if date_el:
            date_text = date_el.get_text(strip=True)
            event_date = self._parse_german_date(date_text)

            # Uhrzeit aus dem span.dtTimeInfo
            time_el = container.select_one(self.SELECTORS["time"])
            if time_el:
                time_text = time_el.get_text(strip=True)
                # Format: "14.30 - 16.00 Uhr"
                time_match = re.search(r"(\d{1,2}[.:]\d{2})\s*-\s*(\d{1,2}[.:]\d{2})", time_text)
                if time_match:
                    event_time = self._parse_time(time_match.group(1))
                    event_end_time = self._parse_time(time_match.group(2))
                else:
                    # Nur Startzeit: "14.30 Uhr"
                    event_time = self._parse_time(time_text)

        if not event_date:
            return None

        # External ID mit Datum (für wiederkehrende Events)
        external_id = f"weikersheim_{event_id}_{event_date}"

        # Location
        raw_location = None
        loc_el = container.select_one(self.SELECTORS["location"])
        if loc_el:
            # Entferne das <label> und nimm nur den Text-Inhalt
            label = loc_el.select_one("label")
            if label:
                label.decompose()
            raw_location = loc_el.get_text(strip=True)

        # Kategorie als extra_data
        extra_data = {}
        categories = [
            li.get_text(strip=True)
            for li in container.select("ul.zmitem__kat li")
            if li.get_text(strip=True)
        ]
        if categories:
            extra_data["categories"] = categories

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            event_end_time=event_end_time,
            url=url,
            raw_location=raw_location,
            extra_data=extra_data,
        )
