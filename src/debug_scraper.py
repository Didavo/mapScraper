#!/usr/bin/env python
"""
Debug-Tool zum Testen des Scrapers.

Usage:
    python -m src.debug_scraper mulfingen
    python -m src.debug_scraper mulfingen --limit 5
    python -m src.debug_scraper mulfingen --raw
"""

import argparse
import requests
from bs4 import BeautifulSoup

from src.config import get_settings
from src.scrapers import MulfingenScraper, DoerzbachScraper, IngelfingenScraper, KuenzelsauScraper, ForchtenbergScraper, BretzfeldScraper, KrautheimScraper, KupferzellScraper, NeuensteinScraper, NiedernhallScraper, OehringenScraper, PfedelbachScraper, SchoentralScraper, WaldenburgScraper, WeissbachScraper, ZweiflingenScraper
from src.scrapers import BlaufeldenScraper, BraunsbachScraper, CrailsheimScraper, GaildorfScraper, GerabronnScraper, LangenburgScraper, MainhardtScraper, MichelfeldScraper, SchrozbergScraper, SchwaebischHallScraper, UntermuenkheimScraper
from src.scrapers import BadMergentheimScraper, BoxbergScraper, CrelingenScraper, IgersheimScraper, NiederstettenScraper, WeikersheimScraper


SCRAPER_REGISTRY = {
    # Hohenlohekreis
    "mulfingen": MulfingenScraper,
    "doerzbach": DoerzbachScraper,
    "ingelfingen": IngelfingenScraper,
    "kuenzelsau": KuenzelsauScraper,
    "forchtenberg": ForchtenbergScraper,
    "bretzfeld": BretzfeldScraper,
    "krautheim": KrautheimScraper,
    "kupferzell": KupferzellScraper,
    "neuenstein": NeuensteinScraper,
    "niedernhall": NiedernhallScraper,
    "oehringen": OehringenScraper,
    "pfedelbach": PfedelbachScraper,
    "schoental": SchoentralScraper,
    "waldenburg": WaldenburgScraper,
    "weissbach": WeissbachScraper,
    "zweiflingen": ZweiflingenScraper,
    # Schwäbisch Hall
    "blaufelden": BlaufeldenScraper,
    "braunsbach": BraunsbachScraper,
    "crailsheim": CrailsheimScraper,
    "gaildorf": GaildorfScraper,
    "gerabronn": GerabronnScraper,
    "langenburg": LangenburgScraper,
    "mainhardt": MainhardtScraper,
    "michelfeld": MichelfeldScraper,
    "schwaebisch_hall": SchwaebischHallScraper,
    "schrozberg": SchrozbergScraper,
    "untermuenkheim": UntermuenkheimScraper,
    # Main-Tauber-Kreis
    "bad_mergentheim": BadMergentheimScraper,
    "boxberg": BoxbergScraper,
    "creglingen": CrelingenScraper,
    "igersheim": IgersheimScraper,
    "niederstetten": NiederstettenScraper,
    "weikersheim": WeikersheimScraper,
}


def main():
    parser = argparse.ArgumentParser(description="Debug Scraper Tool")
    parser.add_argument("source", help="Name des Scrapers (z.B. mulfingen)")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Anzahl Events (default: 5)")
    parser.add_argument("--raw", "-r", action="store_true", help="Zeige auch Raw HTML")
    parser.add_argument("--all", "-a", action="store_true", help="Alle Seiten laden (langsam)")
    args = parser.parse_args()

    if args.source not in SCRAPER_REGISTRY:
        print(f"Unbekannter Scraper: {args.source}")
        print(f"Verfügbar: {', '.join(SCRAPER_REGISTRY.keys())}")
        return

    scraper_class = SCRAPER_REGISTRY[args.source]

    # Scraper ohne DB-Session erstellen (nur für Parsing)
    scraper = scraper_class.__new__(scraper_class)
    scraper.settings = get_settings()
    scraper.http_session = requests.Session()
    scraper.http_session.headers.update({"User-Agent": scraper.settings.user_agent})

    # Setze Klassenattribute
    scraper.BASE_URL = scraper_class.BASE_URL
    scraper.EVENTS_URL = scraper_class.EVENTS_URL
    scraper.SELECTORS = scraper_class.SELECTORS

    # Setze DB-bezogene Attribute auf None (für location_exists Check)
    scraper.session = None
    scraper.source = None
    scraper.scrape_log = None

    print(f"\n{'='*60}")
    print(f"DEBUG: {scraper_class.SOURCE_NAME}")
    print(f"URL: {scraper_class.EVENTS_URL}")
    print(f"{'='*60}\n")

    # Seite laden
    print("Lade Seite...")
    response = scraper.http_session.get(scraper_class.EVENTS_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "lxml")

    print(f"Seite geladen ({len(response.content)} bytes)\n")

    # Events parsen
    print("Parse Events...")

    if args.all:
        # Alle Seiten laden (wie im echten Scraper)
        events = scraper.parse_events(soup)
        print(f"Gefunden: {len(events)} Events (alle Seiten)\n")
    else:
        # Nur erste Seite parsen (schneller für Debug)
        if hasattr(scraper, '_parse_page_events'):
            # Scraper mit Pagination-Support
            events = scraper._parse_page_events(soup, set())
        else:
            # Fallback: parse_events für einfache Scraper
            events = scraper.parse_events(soup)

        print(f"Gefunden: {len(events)} Events (nur erste Seite)\n")

        # Limit anwenden
        events = events[:args.limit]

    # Events anzeigen
    for i, event in enumerate(events, 1):
        print(f"\n{'─'*60}")
        print(f"EVENT #{i}")
        print(f"{'─'*60}")
        print(f"  Title:       {event.title}")
        print(f"  Datum:       {event.event_date}")
        print(f"  Uhrzeit:     {event.event_time or '-'}")
        print(f"  Location:    {event.raw_location or '-'}")
        print(f"  URL:         {event.url}")
        print(f"  External ID: {event.external_id}")

        # Location-Details anzeigen (falls vorhanden)
        if any([event.location_street, event.location_postal_code, event.location_city,
                event.location_latitude, event.location_longitude]):
            print(f"\n  Location-Details:")
            if event.location_street:
                print(f"    Straße:    {event.location_street}")
            if event.location_postal_code:
                print(f"    PLZ:       {event.location_postal_code}")
            if event.location_city:
                print(f"    Stadt:     {event.location_city}")
            if event.location_latitude and event.location_longitude:
                print(f"    Coords:    {event.location_latitude}, {event.location_longitude}")

        if args.raw and event.url:
            print(f"\n  Raw HTML (Parent):")
            # Finde das Event in der Seite
            link = soup.find("a", href=lambda h: h and event.external_id.split("_")[0] in h)
            if link:
                parent = link.find_parent(["div", "article", "section", "li", "p", "td"])
                if parent:
                    html = str(parent)[:500]
                    for line in html.split("\n"):
                        print(f"    {line}")
                    if len(str(parent)) > 500:
                        print(f"    ... ({len(str(parent))} chars total)")

    print(f"\n{'='*60}")
    print(f"Gesamt: {len(events)} Event(s) angezeigt")
    if not args.all:
        print(f"(Limit: {args.limit}, nur erste Seite)")
        print(f"Nutze --all für alle Seiten")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
