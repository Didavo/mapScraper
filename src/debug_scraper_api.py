#!/usr/bin/env python
"""
Debug-Tool zum Testen von API-basierten Scrapern (Cross-7 etc.).

Usage:
    python -m src.debug_scraper_api langenburg
    python -m src.debug_scraper_api langenburg --limit 10
    python -m src.debug_scraper_api langenburg --all
    python -m src.debug_scraper_api langenburg --raw
    python -m src.debug_scraper_api oehringen
"""

import argparse
import json
import requests

from src.config import get_settings
from src.scrapers import OehringenScraper, LangenburgScraper, MichelfeldScraper, UntermuenkheimScraper
from src.scrapers import CrelingenScraper, IgersheimScraper, BadMergentheimScraper
from src.scrapers import SchrozbergScraper


# Nur API-basierte Scraper (die run() überschreiben)
SCRAPER_REGISTRY = {
    "oehringen": OehringenScraper,
    "langenburg": LangenburgScraper,
    "michelfeld": MichelfeldScraper,
    "untermuenkheim": UntermuenkheimScraper,
    # Schwäbisch Hall
    "schrozberg": SchrozbergScraper,
    # Main-Tauber-Kreis
    "creglingen": CrelingenScraper,
    "igersheim": IgersheimScraper,
    "bad_mergentheim": BadMergentheimScraper,
}


def main():
    parser = argparse.ArgumentParser(description="Debug API Scraper Tool")
    parser.add_argument("source", help="Name des Scrapers (z.B. langenburg)")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Anzahl Events (default: 5)")
    parser.add_argument("--all", "-a", action="store_true", help="Alle Seiten laden")
    parser.add_argument("--raw", "-r", action="store_true", help="Zeige Raw JSON pro Event")
    parser.add_argument("--page", "-p", type=int, default=1, help="Startseite (default: 1)")
    args = parser.parse_args()

    if args.source not in SCRAPER_REGISTRY:
        print(f"Unbekannter API-Scraper: {args.source}")
        print(f"Verfügbar: {', '.join(SCRAPER_REGISTRY.keys())}")
        return

    scraper_class = SCRAPER_REGISTRY[args.source]

    # Scraper ohne DB-Session erstellen (nur für Parsing)
    scraper = scraper_class.__new__(scraper_class)
    scraper.settings = get_settings()
    scraper.http_session = requests.Session()
    scraper.http_session.headers.update({"User-Agent": scraper.settings.user_agent})
    scraper.BASE_URL = scraper_class.BASE_URL
    scraper.EVENTS_URL = scraper_class.EVENTS_URL

    print(f"\n{'='*60}")
    print(f"DEBUG API: {scraper_class.SOURCE_NAME}")
    print(f"API URL:   {scraper_class.API_URL}")
    print(f"{'='*60}\n")

    all_events = []
    all_raw_items = []
    seen_ids = set()
    total_api_items = 0

    # Unterscheidung: Heimatinfo-API (Igersheim) vs. CMS-API (Bad Mergentheim) vs. Cross-7-API
    is_heimatinfo = hasattr(scraper, '_generate_month_ranges')
    is_cms_api = hasattr(scraper, 'PAGE_SIZE') and hasattr(scraper, '_build_api_url') and not is_heimatinfo and not hasattr(scraper, 'MEC_SHORTCODE_ID')
    # Check if _build_api_url takes only page param (CMS-API style)
    import inspect
    if is_cms_api:
        sig = inspect.signature(scraper_class._build_api_url)
        is_cms_api = list(sig.parameters.keys()) == ['self', 'page']

    if is_cms_api:
        # CMS-API (Bad Mergentheim): Pagination via seite/seiten
        page = args.page

        while True:
            url = scraper._build_api_url(page)
            print(f"Lade Seite {page}: {url}")

            response = scraper.http_session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            items = data.get("data", [])
            total_pages = data.get("seiten", 1)
            total_count = data.get("anzahl", "?")

            print(f"  -> {len(items)} Items auf Seite {page} (Gesamt: {total_count}, Seiten: {total_pages})")

            total_api_items += len(items)

            for item in items:
                event = scraper._parse_api_event(item)
                if event and event.external_id not in seen_ids:
                    seen_ids.add(event.external_id)
                    all_events.append(event)
                    all_raw_items.append(item)

            if not args.all or page >= total_pages:
                break

            page += 1

    elif is_heimatinfo:
        # Heimatinfo-API: Monatsweise Abfrage, flaches JSON-Array
        month_ranges = scraper._generate_month_ranges()
        ranges_to_load = month_ranges if args.all else month_ranges[:1]

        for from_iso, to_iso in ranges_to_load:
            print(f"Lade Zeitraum: {from_iso[:10]} bis {to_iso[:10]}")
            page_index = 0

            while True:
                url = scraper._build_api_url(from_iso, to_iso, page_index)
                response = scraper.http_session.get(url, timeout=30)
                response.raise_for_status()
                items = response.json()

                if not items:
                    break

                print(f"  -> Seite {page_index}: {len(items)} Items")
                total_api_items += len(items)

                for item in items:
                    event = scraper._parse_api_event(item)
                    if event and event.external_id not in seen_ids:
                        seen_ids.add(event.external_id)
                        all_events.append(event)
                        all_raw_items.append(item)

                if len(items) < scraper.PAGE_SIZE:
                    break
                page_index += 1
    else:
        # Cross-7-API: Pagination via pageNumber/hasNextPage
        page = args.page

        while True:
            url = scraper._build_api_url(page)
            print(f"Lade Seite {page}: {url}")

            response = scraper.http_session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            total_count = data.get("totalCount", "?")
            total_pages = data.get("totalPages", "?")
            has_next = data.get("hasNextPage", False)

            print(f"  -> {len(items)} Items auf Seite {page} (Gesamt: {total_count}, Seiten: {total_pages})")

            total_api_items += len(items)

            for item in items:
                event = scraper._parse_api_event(item)
                if event and event.external_id not in seen_ids:
                    seen_ids.add(event.external_id)
                    all_events.append(event)
                    all_raw_items.append(item)

            if not args.all or not has_next:
                break

            page += 1

    print(f"\nAPI Items geladen: {total_api_items}")
    print(f"Events geparst:    {len(all_events)} (nach Deduplizierung)")

    # Limit anwenden
    if not args.all:
        display_events = all_events[:args.limit]
        display_raw = all_raw_items[:args.limit]
    else:
        display_events = all_events
        display_raw = all_raw_items

    # Events anzeigen
    for i, event in enumerate(display_events):
        print(f"\n{'─'*60}")
        print(f"EVENT #{i + 1}")
        print(f"{'─'*60}")
        print(f"  Title:       {event.title}")
        print(f"  Datum:       {event.event_date}")
        print(f"  Uhrzeit:     {event.event_time or '-'}")
        if event.event_end_date:
            print(f"  End-Datum:   {event.event_end_date}")
        if event.event_end_time:
            print(f"  End-Zeit:    {event.event_end_time}")
        print(f"  Location:    {event.raw_location or '-'}")
        print(f"  URL:         {event.url}")
        print(f"  External ID: {event.external_id}")

        # Location-Details
        if any([event.location_street, event.location_postal_code, event.location_city]):
            print(f"\n  Location-Details:")
            if event.location_street:
                print(f"    Strasse:   {event.location_street}")
            if event.location_postal_code:
                print(f"    PLZ:       {event.location_postal_code}")
            if event.location_city:
                print(f"    Stadt:     {event.location_city}")

        # Extra-Daten
        if event.extra_data:
            print(f"\n  Extra-Daten:")
            for key, value in event.extra_data.items():
                print(f"    {key}: {value}")

        # Raw JSON
        if args.raw and i < len(display_raw):
            print(f"\n  Raw JSON:")
            raw_str = json.dumps(display_raw[i], indent=4, ensure_ascii=False)
            for line in raw_str.split("\n"):
                print(f"    {line}")

    # Zusammenfassung
    print(f"\n{'='*60}")
    print(f"Gesamt: {len(display_events)} Event(s) angezeigt")
    if not args.all:
        print(f"(Limit: {args.limit}, nur Seite {args.page})")
        print(f"Nutze --all fuer alle Seiten")
    else:
        print(f"(Alle {len(all_events)} Events von {total_api_items} API-Items)")

    # Statistiken
    with_location = sum(1 for e in all_events if e.raw_location)
    without_location = len(all_events) - with_location
    with_time = sum(1 for e in all_events if e.event_time)
    print(f"\nStatistiken (alle geladenen Events):")
    print(f"  Mit Location:  {with_location}")
    print(f"  Ohne Location: {without_location}")
    print(f"  Mit Uhrzeit:   {with_time}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
