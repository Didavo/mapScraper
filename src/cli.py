"""
CLI für den Event-Scraper.

Usage:
    python -m src.cli scrape mulfingen
    python -m src.cli scrape --all
    python -m src.cli locations --pending
    python -m src.cli locations export --output locations.csv
    python -m src.cli locations import locations.csv
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.models import get_session, Source, Location, LocationStatus
from src.scrapers import MulfingenScraper, DoerzbachScraper, IngelfingenScraper, KuenzelsauScraper, ForchtenbergScraper, BretzfeldScraper, KrautheimScraper, KupferzellScraper, NeuensteinScraper, NiedernhallScraper, OehringenScraper, PfedelbachScraper, SchoentralScraper, WaldenburgScraper, WeissbachScraper, ZweiflingenScraper
from src.scrapers import BlaufeldenScraper, BraunsbachScraper, CrailsheimScraper, GaildorfScraper, GerabronnScraper, LangenburgScraper, MainhardtScraper, MichelfeldScraper, SchrozbergScraper, SchwaebischHallScraper, UntermuenkheimScraper
from src.scrapers import BadMergentheimScraper, BoxbergScraper, CrelingenScraper, IgersheimScraper, NiederstettenScraper, WeikersheimScraper


# Registry aller verfügbaren Scraper
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


def cmd_scrape(args):
    """Führt einen Scrape-Vorgang durch."""
    session = get_session()

    if args.all:
        # Alle registrierten Scraper ausführen
        scraper_names = list(SCRAPER_REGISTRY.keys())
    else:
        scraper_names = [args.source]

    for name in scraper_names:
        if name not in SCRAPER_REGISTRY:
            print(f"[ERROR] Unbekannter Scraper: {name}")
            print(f"Verfügbare Scraper: {', '.join(SCRAPER_REGISTRY.keys())}")
            continue

        print(f"\n{'='*50}")
        print(f"Starte Scraper: {name}")
        print(f"{'='*50}")

        scraper_class = SCRAPER_REGISTRY[name]
        scraper = scraper_class(session)

        result = scraper.run(debug=getattr(args, 'debug', False))

        if result["status"] == "success":
            print(f"[OK] {result['source']}")
            print(f"    Events gefunden: {result['events_found']}")
            print(f"    Neue Events:     {result['events_new']}")
            print(f"    Aktualisiert:    {result['events_updated']}")
        else:
            print(f"[FEHLER] {result['source']}: {result['error']}")

    session.close()


def cmd_locations(args):
    """Zeigt Locations an."""
    session = get_session()

    query = session.query(Location)

    if args.pending:
        query = query.filter(Location.status == LocationStatus.PENDING.value)
    elif args.confirmed:
        query = query.filter(Location.status == LocationStatus.CONFIRMED.value)

    locations = query.all()

    if not locations:
        print("Keine Locations gefunden.")
        return

    print(f"\n{'ID':<5} {'Status':<12} {'Raw Name':<40} {'City':<20}")
    print("-" * 80)

    for loc in locations:
        print(
            f"{loc.id:<5} {loc.status:<12} {loc.raw_name[:38]:<40} {loc.city or '-':<20}"
        )

    print(f"\nGesamt: {len(locations)} Location(s)")
    session.close()


# CSV-Spalten für Import/Export
LOCATION_CSV_FIELDS = [
    "id", "source_id", "source_name", "raw_name", "display_name",
    "street", "house_number", "postal_code", "city", "country",
    "latitude", "longitude", "status"
]


def cmd_locations_export(args):
    """Exportiert Locations in CSV oder JSON."""
    session = get_session()

    query = session.query(Location).join(Source)

    if args.status:
        query = query.filter(Location.status == args.status)

    locations = query.order_by(Source.name, Location.raw_name).all()

    if not locations:
        print("Keine Locations zum Exportieren gefunden.")
        session.close()
        return

    # Daten aufbereiten
    data = []
    for loc in locations:
        row = {
            "id": loc.id,
            "source_id": loc.source_id,
            "source_name": loc.source.name if loc.source else "",
            "raw_name": loc.raw_name,
            "display_name": loc.display_name or "",
            "street": loc.street or "",
            "house_number": loc.house_number or "",
            "postal_code": loc.postal_code or "",
            "city": loc.city or "",
            "country": loc.country or "Deutschland",
            "latitude": str(loc.latitude) if loc.latitude else "",
            "longitude": str(loc.longitude) if loc.longitude else "",
            "status": loc.status,
        }
        data.append(row)

    # Format bestimmen
    output_format = args.format or "csv"
    output_file = args.output

    if output_format == "json":
        output = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        # CSV
        import io
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=LOCATION_CSV_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(data)
        output = buffer.getvalue()

    # Ausgabe
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[OK] {len(data)} Locations exportiert nach: {output_file}")
    else:
        # Ohne Dateiangabe: in Standardausgabe
        if not args.quiet:
            print(f"# {len(data)} Locations exportiert\n")
        print(output)

    session.close()


def cmd_locations_import(args):
    """Importiert Locations aus CSV oder JSON."""
    session = get_session()

    input_file = args.file

    # Datei lesen
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"[FEHLER] Datei nicht gefunden: {input_file}")
        return

    # Format erkennen
    if input_file.endswith(".json"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[FEHLER] Ungültiges JSON: {e}")
            return
    else:
        # CSV
        import io
        reader = csv.DictReader(io.StringIO(content), delimiter=";")
        data = list(reader)

    if not data:
        print("Keine Daten in der Datei gefunden.")
        return

    print(f"[INFO] {len(data)} Einträge gefunden")

    # Statistiken
    updated = 0
    skipped = 0
    errors = 0

    for row in data:
        try:
            location_id = int(row.get("id", 0))

            if not location_id:
                # Ohne ID können wir nicht aktualisieren
                skipped += 1
                continue

            # Location finden
            location = session.query(Location).filter(Location.id == location_id).first()

            if not location:
                print(f"  [WARN] Location ID {location_id} nicht gefunden, übersprungen")
                skipped += 1
                continue

            # Felder aktualisieren (nur wenn Wert vorhanden)
            changed = False

            if row.get("display_name"):
                location.display_name = row["display_name"]
                changed = True

            if row.get("street"):
                location.street = row["street"]
                changed = True

            if row.get("house_number"):
                location.house_number = row["house_number"]
                changed = True

            if row.get("postal_code"):
                location.postal_code = row["postal_code"]
                changed = True

            if row.get("city"):
                location.city = row["city"]
                changed = True

            if row.get("country"):
                location.country = row["country"]
                changed = True

            if row.get("latitude"):
                location.latitude = Decimal(row["latitude"])
                changed = True

            if row.get("longitude"):
                location.longitude = Decimal(row["longitude"])
                changed = True

            if row.get("status") and row["status"] in ["pending", "confirmed", "ignored"]:
                location.status = row["status"]
                changed = True

            if changed:
                location.updated_at = datetime.now(timezone.utc)
                updated += 1
                if args.verbose:
                    print(f"  [OK] Location {location_id}: {location.raw_name}")

        except Exception as e:
            print(f"  [FEHLER] Zeile {row.get('id', '?')}: {e}")
            errors += 1

    session.commit()
    session.close()

    print(f"\n{'='*40}")
    print(f"Import abgeschlossen:")
    print(f"  Aktualisiert: {updated}")
    print(f"  Übersprungen: {skipped}")
    print(f"  Fehler:       {errors}")
    print(f"{'='*40}")


def cmd_stats(args):
    """Zeigt Statistiken an."""
    session = get_session()

    from src.models import Event, ScrapeLog

    sources = session.query(Source).all()

    print(f"\n{'='*60}")
    print("SCRAPER STATISTIKEN")
    print(f"{'='*60}")

    for source in sources:
        events_count = (
            session.query(Event)
            .filter(Event.source_id == source.id, Event.deleted_at == None)
            .count()
        )
        print(f"\n{source.name}:")
        print(f"  URL:           {source.base_url}")
        print(f"  Events:        {events_count}")
        print(f"  Letzter Scrape: {source.last_scraped_at or 'Nie'}")

    # Locations
    pending_locs = (
        session.query(Location)
        .filter(Location.status == LocationStatus.PENDING.value)
        .count()
    )
    print(f"\n{'='*60}")
    print(f"Locations mit Status 'pending': {pending_locs}")

    session.close()


def main():
    parser = argparse.ArgumentParser(description="Event Scraper CLI")
    subparsers = parser.add_subparsers(dest="command", help="Verfügbare Befehle")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape Events von Websites")
    scrape_parser.add_argument("source", nargs="?", help="Name des Scrapers")
    scrape_parser.add_argument(
        "--all", "-a", action="store_true", help="Alle Scraper ausführen"
    )
    scrape_parser.add_argument(
        "--debug", "-d", action="store_true", help="Debug-Ausgabe aktivieren"
    )
    scrape_parser.set_defaults(func=cmd_scrape)

    # Locations command
    loc_parser = subparsers.add_parser("locations", help="Locations verwalten")
    loc_parser.add_argument(
        "--pending", "-p", action="store_true", help="Nur pending Locations"
    )
    loc_parser.add_argument(
        "--confirmed", "-c", action="store_true", help="Nur confirmed Locations"
    )
    loc_parser.set_defaults(func=cmd_locations)

    # Locations export command
    export_parser = subparsers.add_parser("export-locations", help="Locations exportieren")
    export_parser.add_argument(
        "--status", "-s", choices=["pending", "confirmed", "ignored"],
        help="Nur Locations mit diesem Status"
    )
    export_parser.add_argument(
        "--format", "-f", choices=["csv", "json"], default="csv",
        help="Ausgabeformat (default: csv)"
    )
    export_parser.add_argument(
        "--output", "-o", help="Ausgabedatei (ohne: stdout)"
    )
    export_parser.add_argument(
        "--quiet", "-q", action="store_true", help="Keine Info-Ausgabe"
    )
    export_parser.set_defaults(func=cmd_locations_export)

    # Locations import command
    import_parser = subparsers.add_parser("import-locations", help="Locations importieren")
    import_parser.add_argument(
        "file", help="CSV- oder JSON-Datei zum Importieren"
    )
    import_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Ausführliche Ausgabe"
    )
    import_parser.set_defaults(func=cmd_locations_import)

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Statistiken anzeigen")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "scrape" and not args.source and not args.all:
        print("Bitte gib einen Scraper-Namen an oder nutze --all")
        print(f"Verfügbare Scraper: {', '.join(SCRAPER_REGISTRY.keys())}")
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
