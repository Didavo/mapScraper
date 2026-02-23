"""
Scraper für die Gemeinde Zweiflingen.
Website: https://www.zweiflingen.de/veranstaltungskalender/

JetEngine Calendar (Elementor/WordPress) - POST API
Statt Playwright wird direkt wp-admin/admin-ajax.php aufgerufen.
Die API gibt JSON zurück, dessen "data.content" das Kalender-HTML enthält.
"""

import random
import re
from datetime import date as date_class, time as time_class
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup, Tag

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class ZweiflingenScraper(BaseScraper):
    """Scraper für Zweiflingen Veranstaltungen (JetEngine Calendar API)."""

    SOURCE_NAME = "Gemeinde Zweiflingen"
    BASE_URL = "https://www.zweiflingen.de"
    EVENTS_URL = "https://www.zweiflingen.de/veranstaltungskalender/"

    GEOCODE_REGION = "74639 Zweiflingen"

    # Anzahl Monate in die Zukunft
    MONTHS_AHEAD = 6

    # JetEngine AJAX-Endpunkt (mit nocache-Parameter gegen Server-Caching)
    API_URL = "https://www.zweiflingen.de/veranstaltungskalender/"

    # Feste API-Parameter (aus Browser-Request extrahiert)
    API_SETTINGS = {
        "jet_engine_action": "jet_engine_calendar_get_month",
        "settings[lisitng_id]": "35389",
        "settings[week_days_format]": "short",
        "settings[allow_multiday]": "",
        "settings[end_date_key]": "",
        "settings[group_by]": "meta_date",
        "settings[group_by_key]": "datum_meta",
        "settings[meta_query_relation]": "AND",
        "settings[tax_query_relation]": "AND",
        "settings[hide_widget_if]": "",
        "settings[caption_layout]": "layout-1",
        "settings[show_posts_nearby_months]": "yes",
        "settings[hide_past_events]": "",
        "settings[allow_date_select]": "",
        "settings[start_year_select]": "1970",
        "settings[end_year_select]": "2038",
        "settings[use_custom_post_types]": "",
        "settings[custom_post_types]": "",
        "settings[custom_query]": "yes",
        "settings[custom_query_id]": "148",
        "settings[_element_id]": "",
        "settings[cache_enabled]": "",
        "settings[cache_timeout]": "60",
        "settings[max_cache]": "12",
        "settings[_id]": "cabff9b",
        "settings[__switch_direction]": "1",
        "post": "47012",
    }

    # Englische Monatsnamen für die API (locale-unabhängig)
    EN_MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    MONTH_NAMES = {
        "jan": 1, "januar": 1,
        "feb": 2, "februar": 2,
        "mär": 3, "mar": 3, "märz": 3,
        "apr": 4, "april": 4,
        "mai": 5,
        "jun": 6, "juni": 6,
        "jul": 7, "juli": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "okt": 10, "oktober": 10,
        "nov": 11, "november": 11,
        "dez": 12, "dezember": 12,
    }

    def _fetch_month(self, month_str: str) -> Optional[BeautifulSoup]:
        """Ruft die JetEngine API für einen Monat auf.

        month_str: Englischer Monatsname + Jahr, z.B. "April 2026"
        Gibt BeautifulSoup des Kalender-HTMLs zurück, oder None bei Fehler.
        """
        import time
        time.sleep(self.settings.request_delay)

        payload = dict(self.API_SETTINGS)
        payload["month"] = month_str

        url = f"{self.API_URL}?nocache={random.randint(1000000000, 9999999999)}"
        response = self.http_session.post(url, data=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not data.get("success"):
            print(f"[WARN] API-Fehler für {month_str}: {data}")
            return None

        html = data.get("data", {}).get("content", "")
        return BeautifulSoup(html, "lxml") if html else None

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """Parst "25. Feb. 2026" oder "3. März 2026" -> date"""
        if not date_str:
            return None
        date_str = date_str.strip().lower()
        match = re.match(r"(\d{1,2})\.\s*(\w+)\.?\s*(\d{4})", date_str)
        if match:
            month = self.MONTH_NAMES.get(match.group(2))
            if month:
                try:
                    return date_class(int(match.group(3)), month, int(match.group(1)))
                except ValueError:
                    pass
        return None

    def parse_time(self, time_str: str) -> Optional[time_class]:
        """Parst "| 19:00" oder "19:00" -> time"""
        if not time_str:
            return None
        match = re.search(r"(\d{1,2}):(\d{2})", time_str.replace("|", ""))
        if match:
            try:
                return time_class(int(match.group(1)), int(match.group(2)))
            except ValueError:
                pass
        return None

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """Führt den Scrape-Vorgang via JetEngine POST API durch."""
        self.source = self.get_or_create_source()
        self.scrape_log = self.start_scrape_log()

        events_new = 0
        events_updated = 0

        try:
            all_events = []
            seen_ids = set()

            today = date_class.today()
            year, month = today.year, today.month

            for i in range(self.MONTHS_AHEAD):
                month_str = f"{self.EN_MONTHS[month - 1]} {year}"
                print(f"[INFO] Lade Monat {i + 1}/{self.MONTHS_AHEAD}: {month_str}")

                soup = self._fetch_month(month_str)
                if soup is None:
                    print(f"[WARN] Kein Inhalt für {month_str}")
                else:
                    month_events = self._parse_calendar_events(soup, seen_ids)
                    all_events.extend(month_events)
                    print(f"[INFO]   → {len(month_events)} Events")

                month += 1
                if month > 12:
                    month = 1
                    year += 1

            events_found = len(all_events)
            if debug:
                print(f"[DEBUG] Gesamt: {events_found} Events gefunden")

            for scraped in all_events:
                _, is_new = self.save_event(scraped)
                if is_new:
                    events_new += 1
                else:
                    events_updated += 1

            self.finish_scrape_log(
                ScrapeStatus.SUCCESS,
                events_found=events_found,
                events_new=events_new,
                events_updated=events_updated,
            )

            return {
                "status": "success",
                "source": self.SOURCE_NAME,
                "events_found": events_found,
                "events_new": events_new,
                "events_updated": events_updated,
            }

        except Exception as e:
            import traceback
            if debug:
                traceback.print_exc()
            self.finish_scrape_log(ScrapeStatus.FAILED, error_message=str(e))
            return {"status": "failed", "source": self.SOURCE_NAME, "error": str(e)}

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Für Kompatibilität mit BaseScraper."""
        return self._parse_calendar_events(soup, set())

    def _parse_calendar_events(
        self, soup: BeautifulSoup, seen_ids: set
    ) -> List[ScrapedEvent]:
        """Parst Events aus dem Kalender-HTML."""
        events = []
        for container in soup.select("div.jet-calendar-week__day-event[data-post-id]"):
            event = self._parse_single_event(container)
            if event and event.external_id not in seen_ids:
                seen_ids.add(event.external_id)
                events.append(event)
        return events

    def _parse_single_event(self, container: Tag) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Kalender-Container."""
        post_id = container.get("data-post-id", "")
        if not post_id:
            return None

        title_elem = container.select_one("h3.elementor-heading-title a")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        url = title_elem.get("href", "")
        if url and not url.startswith("http"):
            url = self.resolve_url(url)

        # Datum: erstes Feld das dem Datumsmuster entspricht
        event_date = None
        for field in container.select(".jet-listing-dynamic-field__content"):
            text = field.get_text(strip=True)
            if re.match(r"\d{1,2}\.\s*\w+\.?\s*\d{4}", text):
                event_date = self.parse_german_date(text)
                break

        if not event_date:
            return None

        # Uhrzeit: Feld mit "| HH:MM"
        event_time = None
        for field in container.select(".jet-listing-dynamic-field__content"):
            text = field.get_text(strip=True)
            if re.match(r"\|\s*\d{1,2}:\d{2}", text):
                event_time = self.parse_time(text)
                break

        # Location: bekanntes data-id Attribut des Location-Feldes
        location = None
        loc_elem = container.select_one(
            "div[data-id='a2b84f8'] .jet-listing-dynamic-field__content"
        )
        if loc_elem:
            loc_text = loc_elem.get_text(strip=True)
            if len(loc_text) < 100:
                location = loc_text

        return ScrapedEvent(
            external_id=f"zweiflingen_{post_id}_{event_date}",
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=location,
        )
