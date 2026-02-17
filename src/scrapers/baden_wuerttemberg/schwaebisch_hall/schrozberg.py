"""
Scraper für die Stadt Schrozberg.
Website: https://schrozberg.de
API: https://schrozberg.de/wp-admin/admin-ajax.php

Besonderheit: WordPress MEC (Modern Events Calendar) Plugin.
- POST-Request an admin-ajax.php mit action=mec_list_load_more
- JSON-Antwort mit HTML-Fragment und Pagination-Metadaten
- Events werden aus JSON-LD-Blöcken im HTML geparst
- Pagination via end_date/offset/has_more_event
"""

import html as html_module
import json
import re
from datetime import date as date_class, time as time_class, datetime, timedelta
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class SchrozbergScraper(BaseScraper):
    """Scraper für Schrozberg Veranstaltungen (WordPress MEC Plugin)."""

    SOURCE_NAME = "Stadt Schrozberg"
    BASE_URL = "https://schrozberg.de"
    EVENTS_URL = "https://schrozberg.de/veranstaltungen/"

    # API-Endpunkt
    API_URL = "https://schrozberg.de/wp-admin/admin-ajax.php"
    MEC_SHORTCODE_ID = 11581

    GEOCODE_REGION = "74575 Schrozberg"

    # Kategorien die gefiltert werden sollen (z.B. Müllabfuhr)
    SKIP_ORGANIZERS = {"Müllabfuhr"}

    def _build_post_data(self, start_date: str, offset: int, month_divider: str) -> Dict[str, str]:
        """Baut die POST-Daten für den MEC AJAX Request."""
        return {
            "action": "mec_list_load_more",
            "mec_start_date": start_date,
            "mec_offset": str(offset),
            "atts[id]": str(self.MEC_SHORTCODE_ID),
            "atts[skin]": "list",
            "atts[sk-options][list][style]": "modern",
            "atts[sk-options][list][pagination]": "loadmore",
            "atts[show_past_events]": "1",
            "current_month_divider": month_divider,
            "apply_sf_date": "0",
        }

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den Scrape-Vorgang über die WordPress MEC AJAX-API durch.
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
            seen_ids = set()

            # Start mit heutigem Datum, max 6 Monate in die Zukunft
            now = datetime.utcnow()
            max_date = (now + timedelta(days=183)).strftime("%Y-%m-%d")
            start_date = now.strftime("%Y-%m-%d")
            month_divider = now.strftime("%Y%m")
            offset = 0
            page = 1

            while True:
                # Abbruch wenn start_date über dem 6-Monats-Limit liegt
                if start_date > max_date:
                    print(f"[INFO] 6-Monats-Limit erreicht ({max_date}), stoppe.")
                    break

                post_data = self._build_post_data(start_date, offset, month_divider)
                print(f"[INFO] Lade MEC Seite {page} (start_date={start_date}, offset={offset})")

                response = self.http_session.post(
                    self.API_URL,
                    data=post_data,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                html = data.get("html", "")
                if not html:
                    break

                page_events = self._parse_mec_html(html)
                print(f"[INFO] Seite {page}: {len(page_events)} Events geparst")

                if not page_events:
                    break

                for event in page_events:
                    if event.external_id not in seen_ids:
                        seen_ids.add(event.external_id)
                        all_events.append(event)

                # Pagination prüfen
                has_more = data.get("has_more_event", 0)
                if not has_more:
                    break

                # Nächste Seite: end_date und offset aus Response
                start_date = data.get("end_date", start_date)
                offset = data.get("offset", 0)
                month_divider = data.get("current_month_divider", month_divider)
                page += 1

                # Sicherheitslimit
                if page > 50:
                    print("[WARN] Sicherheitslimit erreicht (50 Seiten)")
                    break

            # Events speichern
            events_found = len(all_events)
            if debug:
                print(f"[DEBUG] Gesamt: {events_found} Events gefunden")

            for scraped in all_events:
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

    def _parse_mec_html(self, html: str) -> List[ScrapedEvent]:
        """Parst Events aus dem MEC HTML-Fragment via JSON-LD + HTML."""
        soup = BeautifulSoup(html, "lxml")
        events = []

        # JSON-LD Blöcke und HTML-Artikel parallel parsen
        json_ld_blocks = soup.find_all("script", type="application/ld+json")
        articles = soup.find_all("article", class_="mec-event-article")

        # data-event-id aus den Artikeln sammeln
        event_ids_by_url = {}
        for article in articles:
            link = article.select_one("h4.mec-event-title a[data-event-id]")
            if link:
                href = link.get("href", "")
                eid = link.get("data-event-id", "")
                if href and eid:
                    event_ids_by_url[href] = eid

        for script in json_ld_blocks:
            try:
                ld_data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            event = self._parse_json_ld_event(ld_data, event_ids_by_url)
            if event:
                events.append(event)

        return events

    def _parse_json_ld_event(
        self, ld_data: Dict[str, Any], event_ids_by_url: Dict[str, str]
    ) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus einem JSON-LD Block."""

        # Titel (HTML-Entities dekodieren: &#8220; -> „)
        name = html_module.unescape(ld_data.get("name", "")).strip()
        if not name:
            return None

        # Organizer filtern
        organizer = ld_data.get("organizer", {})
        org_name = html_module.unescape(organizer.get("name", "")).strip() if isinstance(organizer, dict) else ""
        if org_name in self.SKIP_ORGANIZERS:
            return None

        # Datum + Uhrzeit aus startDate
        start_date_str = ld_data.get("startDate", "")
        if not start_date_str:
            return None

        event_date, event_time = self._parse_iso_datetime(start_date_str)
        if not event_date:
            return None

        # Enddatum + Endzeit
        end_date_str = ld_data.get("endDate", "")
        event_end_date, event_end_time = self._parse_iso_datetime(end_date_str)

        # Enddatum nur setzen wenn es sich vom Startdatum unterscheidet
        if event_end_date == event_date:
            event_end_date = None

        # URL
        url = ld_data.get("url", "")

        # External ID: data-event-id aus HTML oder Fallback
        wp_event_id = event_ids_by_url.get(url)
        if wp_event_id:
            external_id = f"schrozberg_{wp_event_id}_{event_date}"
        else:
            import hashlib
            hash_input = f"{name}_{event_date}".encode("utf-8")
            hash_id = hashlib.md5(hash_input).hexdigest()[:8]
            external_id = f"schrozberg_{hash_id}_{event_date}"

        # Location
        raw_location = None
        location_street = None
        location_postal_code = None
        location_city = None

        location = ld_data.get("location", {})
        if isinstance(location, dict):
            loc_name = html_module.unescape(location.get("name", "")).strip()
            address = html_module.unescape(location.get("address", "")).strip()

            if loc_name:
                raw_location = loc_name

            # Adresse parsen: "Bahnhofstraße, 74575 Schrozberg" oder "74575 Schrozberg"
            if address:
                addr_match = re.match(r"^(.+?),\s*(\d{5})\s+(.+)$", address)
                if addr_match:
                    location_street = addr_match.group(1).strip()
                    location_postal_code = addr_match.group(2)
                    location_city = addr_match.group(3).strip()
                else:
                    plz_match = re.match(r"^(\d{5})\s+(.+)$", address)
                    if plz_match:
                        location_postal_code = plz_match.group(1)
                        location_city = plz_match.group(2).strip()

        # Extra-Daten
        extra_data = {}
        if org_name:
            extra_data["organizer"] = org_name

        return ScrapedEvent(
            external_id=external_id,
            title=name,
            event_date=event_date,
            event_time=event_time,
            event_end_date=event_end_date,
            event_end_time=event_end_time,
            url=url,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            extra_data=extra_data,
        )

    def _parse_iso_datetime(self, dt_str: str):
        """Parst ISO-Datetime: '2026-02-18T15:00:00+01:00' oder '2026-02-18'."""
        if not dt_str:
            return None, None

        # Mit Uhrzeit: 2026-02-18T15:00:00+01:00
        match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})", dt_str)
        if match:
            try:
                d = date_class.fromisoformat(match.group(1))
                t = time_class(int(match.group(2)), int(match.group(3)))
                return d, t
            except ValueError:
                return None, None

        # Nur Datum: 2026-02-18
        try:
            d = date_class.fromisoformat(dt_str)
            return d, None
        except ValueError:
            return None, None

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Standard parse_events - wird hier nicht direkt verwendet,
        da wir run() überschreiben, aber für Kompatibilität nötig.
        """
        return []
