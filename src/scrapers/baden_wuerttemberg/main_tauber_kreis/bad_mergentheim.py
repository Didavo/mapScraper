"""
Scraper für Bad Mergentheim (Tourismus-Portal).
API: https://visit.bad-mergentheim.de/api/cms/veranstaltungen_merged

JSON-API-basierter Scraper mit Pagination.
Parameter: seite, datum_von, datum_bis, order[], sprache, pro_seite
Antwort: {data: [...], anzahl: N, seiten: N}
"""

import html as html_module
import re
import time
from datetime import date as date_class, time as time_class, datetime, timedelta
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup

from ...base import BaseScraper, ScrapedEvent
from src.models import ScrapeStatus


class BadMergentheimScraper(BaseScraper):
    """Scraper für Bad Mergentheim Veranstaltungen (JSON API)."""

    SOURCE_NAME = "Stadt Bad Mergentheim"
    BASE_URL = "https://visit.bad-mergentheim.de"
    EVENTS_URL = "https://visit.bad-mergentheim.de"

    # API-Endpunkt
    API_URL = "https://visit.bad-mergentheim.de/api/cms/veranstaltungen_merged"
    PAGE_SIZE = 50

    GEOCODE_REGION = "97980 Bad Mergentheim"

    def _build_api_url(self, page: int = 1) -> str:
        """Baut die API-URL mit dynamischem Datumsbereich (heute + 6 Monate)."""
        today = date_class.today()
        date_from = today.isoformat()
        date_to = (today + timedelta(days=183)).isoformat()

        return (
            f"{self.API_URL}"
            f"?seite={page}"
            f"&datum_von={date_from}"
            f"&datum_bis={date_to}"
            f"&order[]=%60datum_bis%60+ASC"
            f"&order[]=%60datum_von%60+ASC"
            f"&sprache=de"
            f"&pro_seite={self.PAGE_SIZE}"
        )

    def run(self, debug: bool = False) -> Dict[str, Any]:
        """
        Führt den Scrape-Vorgang über die JSON-API durch.
        Paginiert automatisch über alle Seiten.
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

            page = 1
            total_pages = None

            while True:
                url = self._build_api_url(page)
                if debug:
                    print(f"[DEBUG] API-URL: {url}")

                # Rate limiting
                time.sleep(self.settings.request_delay)

                response = self.http_session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()

                items = data.get("data", [])
                total_pages = data.get("seiten", 1)
                total_count = data.get("anzahl", 0)

                if page == 1:
                    print(f"[INFO] {total_count} Events auf {total_pages} Seiten")

                print(f"[INFO] Seite {page}/{total_pages}: {len(items)} Events")

                for item in items:
                    event = self._parse_api_event(item)
                    if event and event.external_id not in seen_ids:
                        seen_ids.add(event.external_id)
                        all_events.append(event)

                if page >= total_pages:
                    break

                page += 1

            # Events speichern
            events_found = len(all_events)
            if debug:
                print(f"[DEBUG] Gesamt: {events_found} Events gefunden")

            save_seen = set()
            for scraped in all_events:
                if scraped.external_id in save_seen:
                    skipped += 1
                    continue
                save_seen.add(scraped.external_id)

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

    def _parse_api_event(self, item: Dict[str, Any]) -> Optional[ScrapedEvent]:
        """Parst ein einzelnes Event aus dem API-JSON."""

        # Titel
        title = html_module.unescape((item.get("titel") or "").strip())
        if not title:
            return None

        # ID
        event_id = item.get("id")
        if not event_id:
            return None

        # Datum: "2026-02-17T19:00:00.000Z"
        datum_von = item.get("datum_von")
        if not datum_von:
            return None

        try:
            start_dt = datetime.fromisoformat(datum_von.replace("Z", "+00:00"))
            event_date = start_dt.date()
            event_time = start_dt.time().replace(second=0, microsecond=0)
            if event_time == time_class(0, 0):
                event_time = None
        except (ValueError, TypeError):
            return None

        # Enddatum
        event_end_date = None
        event_end_time = None
        datum_bis = item.get("datum_bis")
        if datum_bis:
            try:
                end_dt = datetime.fromisoformat(datum_bis.replace("Z", "+00:00"))
                if end_dt.date() != event_date:
                    event_end_date = end_dt.date()
                event_end_time = end_dt.time().replace(second=0, microsecond=0)
                if event_end_time == time_class(0, 0):
                    event_end_time = None
            except (ValueError, TypeError):
                pass

        # External ID mit Datum (für wiederkehrende Events)
        external_id = f"bad_mergentheim_{event_id}_{event_date}"

        # URL aus rubriken[0].detailURL
        url = None
        rubriken = item.get("rubriken") or []
        if rubriken:
            url = rubriken[0].get("detailURL")

        # Location / Adresse
        raw_location = None
        location_street = None
        location_postal_code = None
        location_city = None
        location_latitude = None
        location_longitude = None

        # Veranstaltungsort als raw_location
        veranstaltungsort = html_module.unescape(
            (item.get("veranstaltungsort") or "").strip()
        )

        # Adresse direkt am Event
        adresse = item.get("adresse") or {}
        strasse = (adresse.get("strasse") or "").strip()
        plz = (adresse.get("plz") or "").strip()
        ort = (adresse.get("ort") or "").strip()

        # Koordinaten: zuerst aus brancheneintrag_veranstaltungsort, dann aus adresse
        geo = adresse.get("geokoordinaten") or {}
        lat_str = (geo.get("latitude") or "").strip()
        lon_str = (geo.get("longitude") or "").strip()

        # Brancheneintrag hat oft bessere Geodaten
        bvo = item.get("brancheneintrag_veranstaltungsort")
        if bvo:
            bvo_adresse = bvo.get("adresse") or {}
            bvo_geo = bvo_adresse.get("geokoordinaten") or {}
            bvo_lat = (bvo_geo.get("latitude") or "").strip()
            bvo_lon = (bvo_geo.get("longitude") or "").strip()
            if bvo_lat and bvo_lon:
                lat_str = bvo_lat
                lon_str = bvo_lon
            # Fallback Adresse aus Brancheneintrag
            if not strasse:
                strasse = (bvo_adresse.get("strasse") or "").strip()
            if not plz:
                plz = (bvo_adresse.get("plz") or "").strip()
            if not ort:
                ort = (bvo_adresse.get("ort") or "").strip()

        # raw_location zusammenbauen
        if veranstaltungsort:
            raw_location = veranstaltungsort
        elif strasse:
            parts = [strasse]
            if plz and ort:
                parts.append(f"{plz} {ort}")
            raw_location = ", ".join(parts)

        if strasse:
            location_street = strasse
        if plz:
            location_postal_code = plz
        if ort:
            location_city = ort

        if lat_str and lon_str:
            try:
                location_latitude = float(lat_str)
                location_longitude = float(lon_str)
            except ValueError:
                pass

        # Veranstalter
        extra_data = {}
        veranstalter = html_module.unescape(
            (item.get("veranstalter") or "").strip()
        )
        if veranstalter:
            extra_data["veranstalter"] = veranstalter

        # Kategorien aus Interessengruppen
        interessengruppen = item.get("interessengruppen") or []
        categories = [
            ig.get("interessengruppe")
            for ig in interessengruppen
            if ig.get("interessengruppe")
        ]
        if categories:
            extra_data["categories"] = categories

        return ScrapedEvent(
            external_id=external_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            event_end_date=event_end_date,
            event_end_time=event_end_time,
            url=url,
            raw_location=raw_location,
            location_street=location_street,
            location_postal_code=location_postal_code,
            location_city=location_city,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            extra_data=extra_data,
        )

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """
        Standard parse_events - wird hier nicht direkt verwendet,
        da wir run() überschreiben, aber für Kompatibilität nötig.
        """
        return []
