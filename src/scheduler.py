"""
Scheduler für automatisierte Scraper-Läufe.

Führt alle registrierten Scraper an konfigurierbaren Tagen aus.
Standard: Dienstag + Freitag um 06:00 Uhr.

Usage:
    python -m src.scheduler

Environment:
    SCRAPE_DAYS=tue,fri    # Wochentage (mon,tue,wed,thu,fri,sat,sun)
    SCRAPE_HOUR=6          # Stunde (0-23)
    SCRAPE_MINUTE=0        # Minute (0-59)
"""

import os
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.models import get_session
from src.cli import SCRAPER_REGISTRY


def run_all_scrapers():
    """Führt alle registrierten Scraper aus."""
    print(f"\n{'='*60}")
    print(f"GEPLANTER SCRAPE-LAUF: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    session = get_session()
    total_found = 0
    total_new = 0
    total_updated = 0
    errors = []

    for name, scraper_class in SCRAPER_REGISTRY.items():
        print(f"\n--- {name} ---")
        try:
            scraper = scraper_class(session)
            result = scraper.run()

            if result["status"] == "success":
                print(f"[OK] {result['source']}: {result['events_found']} gefunden, {result['events_new']} neu, {result['events_updated']} aktualisiert")
                total_found += result["events_found"]
                total_new += result["events_new"]
                total_updated += result["events_updated"]
            else:
                print(f"[FEHLER] {result['source']}: {result['error']}")
                errors.append(f"{name}: {result['error']}")
        except Exception as e:
            print(f"[FEHLER] {name}: {e}")
            errors.append(f"{name}: {e}")

    session.close()

    print(f"\n{'='*60}")
    print(f"ZUSAMMENFASSUNG")
    print(f"  Scraper:      {len(SCRAPER_REGISTRY)}")
    print(f"  Events total: {total_found}")
    print(f"  Neue Events:  {total_new}")
    print(f"  Aktualisiert: {total_updated}")
    if errors:
        print(f"  Fehler:       {len(errors)}")
        for err in errors:
            print(f"    - {err}")
    print(f"{'='*60}\n")


def main():
    # Konfiguration aus Environment
    scrape_days = os.environ.get("SCRAPE_DAYS", "tue,fri")
    scrape_hour = int(os.environ.get("SCRAPE_HOUR", "6"))
    scrape_minute = int(os.environ.get("SCRAPE_MINUTE", "0"))

    # Wochentage umwandeln für APScheduler
    day_of_week = scrape_days.strip()

    print(f"\n{'='*60}")
    print(f"EVENT SCRAPER SCHEDULER")
    print(f"{'='*60}")
    print(f"  Scrape-Tage:  {day_of_week}")
    print(f"  Uhrzeit:      {scrape_hour:02d}:{scrape_minute:02d}")
    print(f"  Scraper:      {len(SCRAPER_REGISTRY)} registriert")
    print(f"  Timezone:     Europe/Berlin")
    print(f"{'='*60}\n")

    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    # Geplanter Job: An den konfigurierten Tagen
    scheduler.add_job(
        run_all_scrapers,
        CronTrigger(
            day_of_week=day_of_week,
            hour=scrape_hour,
            minute=scrape_minute,
            timezone="Europe/Berlin",
        ),
        id="scrape_all",
        name="Alle Scraper ausführen",
        misfire_grace_time=3600,  # 1 Stunde Toleranz bei Verzögerung
    )

    # Graceful shutdown
    def shutdown(signum, frame):
        print("\nScheduler wird beendet...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("Scheduler gestartet. Warte auf nächsten Scrape-Lauf...")
    print(f"Nächster Lauf: {scheduler.get_jobs()[0].next_run_time}\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
