"""
Scraper für die Stadt Weikersheim.
Website: https://www.weikersheim.de

HTML-basierter Scraper mit Monats-Navigation (KOMM.ONE CMS).
Die "Pagination" ist eine Monatsfilterung über div.zmRegister.
Jeder Monat hat eine eigene tlist-URL; alle aktiven Monate werden einzeln abgerufen.
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

    def _get_month_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extrahiert alle Monats-URLs aus der zmRegister-Navigation.

        Aktive Monate sind <a class="aktiv" href="...tlist/yyyymm(...)...">.
        Der aktuelle Monat ist <span class="selected current"> (kein Link).
        Inaktive Monate sind <span class="inaktiv"> (kein Link).
        """
        nav = soup.select_one("div.zmRegister")
        if not nav:
            return []

        urls = []
        for link in nav.select("a.aktiv[href]"):
            href = link.get("href", "")
            if "tlist/yyyymm" in href:
                full_url = self.BASE_URL + href if href.startswith("/") else href
                urls.append(full_url)
        return urls

    def _generate_month_urls(self) -> List[str]:
        """Generiert tlist-URLs für den aktuellen und die nächsten 11 Monate."""
        today = date_class.today()
        urls = []
        year, month = today.year, today.month
        for _ in range(12):
            yyyymm = f"{year}{month:02d}"
            urls.append(
                f"{self.BASE_URL}/site/Weikersheim-Layout/node/3502554"
                f"/tlist/yyyymm({yyyymm})/index.html"
            )
            month += 1
            if month > 12:
                month = 1
                year += 1
        return urls

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Parst Events von allen Monatsseiten.

        Versucht zuerst die Monats-URLs aus der zmRegister-Navigation zu lesen.
        Fallback: URLs für die nächsten 12 Monate direkt generieren.
        """
        all_events = []
        seen_ids = set()

        month_urls = self._get_month_urls(soup)

        if not month_urls:
            # azlist-Seite oder fehlende Navigation → aktuelle Monatsseite laden
            today = date_class.today()
            yyyymm = today.strftime("%Y%m")
            current_url = (
                f"{self.BASE_URL}/site/Weikersheim-Layout/node/3502554"
                f"/tlist/yyyymm({yyyymm})/index.html"
            )
            print(f"[INFO] Lade aktuelle Monatsseite für Navigation: {current_url}")
            nav_soup = self.fetch_page(current_url)
            month_urls = self._get_month_urls(nav_soup)

        if month_urls:
            print(f"[INFO] {len(month_urls)} Monate aus Navigation extrahiert")
        else:
            # Fallback: Monats-URLs direkt generieren
            month_urls = self._generate_month_urls()
            print(f"[INFO] Navigation nicht gefunden, generiere {len(month_urls)} Monats-URLs")

        for i, url in enumerate(month_urls, 1):
            print(f"[INFO] Lade Monat {i}/{len(month_urls)}: {url}")
            month_soup = self.fetch_page(url)
            page_events = self._parse_page_events(month_soup, seen_ids)
            all_events.extend(page_events)
            print(f"[INFO]   → {len(page_events)} Events")

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
