"""
Scraper für die Gemeinde Zweiflingen.
Website: https://www.zweiflingen.de/veranstaltungskalender/

Besonderheit: JetEngine Calendar (Elementor/WordPress)
- Kalender-Widget lädt Monate dynamisch per JavaScript
- Wir nutzen Playwright um durch die Monate zu navigieren
"""

import re
import time as time_module
from datetime import date as date_class, time as time_class
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright, Page

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class ZweiflingenScraper(BaseScraper):
    """Scraper für Zweiflingen Veranstaltungen (JetEngine Calendar mit Playwright)."""

    SOURCE_NAME = "Gemeinde Zweiflingen"
    BASE_URL = "https://www.zweiflingen.de"
    EVENTS_URL = "https://www.zweiflingen.de/veranstaltungskalender/"

    # Für Google Geocoding API - grenzt Suchergebnisse ein
    GEOCODE_REGION = "74639 Zweiflingen"

    # Anzahl Monate in die Zukunft, die gescraped werden sollen
    MONTHS_AHEAD = 3

    # Selektoren für Navigation
    NEXT_MONTH_SELECTOR = ".jet-calendar-nav__link.nav-link-next"
    CALENDAR_SELECTOR = "div.jet-calendar"

    # Deutsche Monatsnamen
    MONTH_NAMES = {
        "januar": 1, "jan": 1,
        "februar": 2, "feb": 2,
        "märz": 3, "mar": 3, "mär": 3,
        "april": 4, "apr": 4,
        "mai": 5,
        "juni": 6, "jun": 6,
        "juli": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "oktober": 10, "okt": 10,
        "november": 11, "nov": 11,
        "dezember": 12, "dez": 12,
    }

    def parse_german_date(self, date_str: str) -> Optional[date_class]:
        """
        Parst deutsches Datumsformat: "25. Feb. 2026" oder "3. März 2026"
        """
        if not date_str:
            return None

        date_str = date_str.strip().lower()

        # Format: "25. Feb. 2026" oder "3. März 2026"
        match = re.match(r"(\d{1,2})\.\s*(\w+)\.?\s*(\d{4})", date_str)
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            year = int(match.group(3))

            month = self.MONTH_NAMES.get(month_str)
            if month:
                try:
                    return date_class(year, month, day)
                except ValueError:
                    return None

        return None

    def parse_time(self, time_str: str) -> Optional[time_class]:
        """
        Parst Uhrzeitformat: "| 19:00" oder "19:00"
        """
        if not time_str:
            return None

        # Entferne Pipe-Zeichen und Whitespace
        time_str = time_str.replace("|", "").strip()

        match = re.search(r"(\d{1,2}):(\d{2})", time_str)
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                return time_class(hour, minute)
            except ValueError:
                return None

        return None

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den Scrape-Vorgang mit Playwright durch.
        Überschreibt die BaseScraper.run() Methode.
        """
        self.source = self.get_or_create_source()
        self.scrape_log = self.start_scrape_log()

        events_found = 0
        events_new = 0
        events_updated = 0
        skipped = 0

        try:
            all_events = []
            seen_event_keys = set()

            with sync_playwright() as p:
                # Browser starten (headless)
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                print(f"[INFO] Lade {self.EVENTS_URL}...")
                page.goto(self.EVENTS_URL, wait_until="networkidle")

                # Warte auf Kalender
                page.wait_for_selector(self.CALENDAR_SELECTOR, timeout=10000)

                # Parse aktuellen Monat
                current_month = self._get_current_month_name(page)
                print(f"[INFO] Aktueller Monat: {current_month}")

                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                month_events = self._parse_calendar_events(soup, seen_event_keys)
                all_events.extend(month_events)
                print(f"[INFO] {len(month_events)} Events in {current_month}")

                # Navigiere durch weitere Monate
                for i in range(self.MONTHS_AHEAD):
                    try:
                        # Klick auf "Nächster Monat"
                        next_btn = page.locator(self.NEXT_MONTH_SELECTOR)
                        if next_btn.count() == 0:
                            print("[WARN] Kein 'Nächster Monat' Button gefunden")
                            break

                        # Merke aktuellen Monatsnamen für Änderungs-Check
                        old_month = self._get_current_month_name(page)

                        next_btn.click()

                        # Warte auf Aktualisierung des Kalenders
                        time_module.sleep(1)  # Kurze Pause für AJAX
                        page.wait_for_load_state("networkidle")

                        # Warte bis Monatsname sich ändert
                        new_month = self._get_current_month_name(page)
                        attempts = 0
                        while new_month == old_month and attempts < 10:
                            time_module.sleep(0.3)
                            new_month = self._get_current_month_name(page)
                            attempts += 1

                        if new_month == old_month:
                            print(f"[WARN] Monat hat sich nicht geändert nach Klick")
                            break

                        print(f"[INFO] Navigiert zu: {new_month}")

                        # Parse Events
                        html = page.content()
                        soup = BeautifulSoup(html, "lxml")
                        month_events = self._parse_calendar_events(soup, seen_event_keys)
                        all_events.extend(month_events)
                        print(f"[INFO] {len(month_events)} Events in {new_month}")

                    except Exception as e:
                        print(f"[WARN] Fehler bei Navigation: {e}")
                        break

                browser.close()

            # Events speichern
            events_found = len(all_events)
            if debug:
                print(f"[DEBUG] Gesamt: {events_found} Events gefunden")

            seen_ids = set()
            for scraped in all_events:
                if scraped.external_id in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(scraped.external_id)

                event, is_new = self.save_event(scraped)
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
                "skipped_duplicates": skipped,
            }

        except Exception as e:
            import traceback
            if debug:
                traceback.print_exc()
            self.finish_scrape_log(ScrapeStatus.FAILED, error_message=str(e))
            return {
                "status": "failed",
                "source": self.SOURCE_NAME,
                "error": str(e),
            }

    def _get_current_month_name(self, page: Page) -> str:
        """Extrahiert den aktuellen Monatsnamen aus dem Kalender."""
        try:
            month_elem = page.locator(".jet-calendar-caption__name")
            if month_elem.count() > 0:
                return month_elem.inner_text()
        except:
            pass
        return "Unbekannt"

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Standard parse_events - wird hier nicht direkt verwendet,
        da wir run() überschreiben, aber für Kompatibilität nötig.
        """
        return self._parse_calendar_events(soup, set())

    def _parse_calendar_events(
        self, soup: BeautifulSoup, seen_keys: set
    ) -> List[ScrapedEvent]:
        """Parst Events aus dem Kalender-HTML."""
        events = []

        # Finde alle Event-Container
        event_containers = soup.select("div.jet-calendar-week__day-event[data-post-id]")

        for container in event_containers:
            event = self._parse_single_event(container)
            if event and event.external_id not in seen_keys:
                seen_keys.add(event.external_id)
                events.append(event)

        return events

    def _parse_single_event(self, container: Tag) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem Container."""

        # Post-ID extrahieren (für external_id)
        post_id = container.get("data-post-id", "")
        if not post_id:
            return None

        # Titel extrahieren
        title_elem = container.select_one("h3.elementor-heading-title a")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        # URL extrahieren
        url = title_elem.get("href", "")
        if url and not url.startswith("http"):
            url = self.resolve_url(url)

        # Datum extrahieren
        date_elem = None
        for field in container.select(".jet-listing-dynamic-field__content"):
            text = field.get_text(strip=True)
            if re.match(r"\d{1,2}\.\s*\w+\.?\s*\d{4}", text):
                date_elem = field
                break

        if not date_elem:
            return None

        date_text = date_elem.get_text(strip=True)
        event_date = self.parse_german_date(date_text)

        if not event_date:
            return None

        # Uhrzeit extrahieren
        event_time = None
        for field in container.select(".jet-listing-dynamic-field__content"):
            text = field.get_text(strip=True)
            if re.match(r"\|\s*\d{1,2}:\d{2}", text):
                event_time = self.parse_time(text)
                break

        # Location extrahieren (aus dem Location-Field, max 100 Zeichen)
        location = None
        loc_elem = container.select_one(
            "div[data-id='a2b84f8'] .jet-listing-dynamic-field__content"
        )
        if loc_elem:
            loc_text = loc_elem.get_text(strip=True)
            if len(loc_text) < 100:
                location = loc_text

        # External ID generieren
        external_id = f"zweiflingen_{post_id}_{event_date}"

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            url=url,
            raw_location=location,
        )
