```
Erstelle einen neuen Scraper für [GEMEINDE/STADT] im Landkreis [LANDKREIS].

## Basis-Informationen
- Gemeinde/Stadt: [Name]
- Landkreis: [z.B. Hohenlohekreis, Schwäbisch Hall, Main-Tauber-Kreis]
- Website-URL (Events): [URL der Veranstaltungsseite]
- PLZ + Ort (für Geocoding): [z.B. "74653 Künzelsau"]

## HTML-Struktur

### Übersichtsseite (Event-Liste)
[Füge hier ein Beispiel-HTML eines einzelnen Event-Containers ein]

Selektoren:
- Event-Container: [CSS-Selektor, z.B. "div.event-item"]
- Titel: [CSS-Selektor, z.B. "h3 a"]
- Datum: [CSS-Selektor + Format, z.B. "span.date" -> "04.02.2026"]
- Uhrzeit: [CSS-Selektor + Format, z.B. "span.time" -> "18:00 Uhr"]
- Location: [CSS-Selektor, z.B. "span.location"]
- URL/Link: [CSS-Selektor, z.B. "h3 a[href]"]

### Pagination (falls vorhanden)
[Beschreibe wie die Pagination funktioniert, z.B.:]
- Typ: "Weiter"-Link / Seitenzahlen / Keine
- [Füge HTML-Beispiel der Pagination ein]

### Detail-Seite (falls Location-Daten dort stehen)
[Füge HTML-Beispiel der Detail-Seite ein, falls relevant]
- Location-Name: [Selektor]
- Adresse: [Selektor]
- Koordinaten: [Selektor, falls vorhanden]

```

---

## Projekt-Kontext (für Claude Code)

### Projektstruktur

```
src/
├── scrapers/
│   ├── base.py                          # BaseScraper + ScrapedEvent
│   ├── __init__.py                      # Zentrale Exports aller Scraper
│   └── baden_wuerttemberg/
│       ├── __init__.py                  # Exports für ganz BW
│       ├── hohenlohekreis/
│       │   ├── __init__.py              # Exports für den Landkreis
│       │   ├── mulfingen.py
│       │   ├── kuenzelsau.py
│       │   └── ...
│       ├── schwaebisch_hall/
│       │   ├── __init__.py
│       │   └── crailsheim.py
│       └── main_tauber_kreis/
│           └── __init__.py
├── cli.py                               # CLI mit SCRAPER_REGISTRY
├── debug_scraper.py                     # Debug-Tool mit SCRAPER_REGISTRY
└── api/
    └── routers/
        └── scraper.py                   # API mit SCRAPER_REGISTRY
```

### Dateien die bei einem neuen Scraper angepasst werden müssen (6 Stück)

1. **Scraper-Datei erstellen**: `src/scrapers/baden_wuerttemberg/{landkreis}/{gemeinde}.py`
2. **Landkreis `__init__.py`**: `src/scrapers/baden_wuerttemberg/{landkreis}/__init__.py` - Import + `__all__`
3. **BW `__init__.py`**: `src/scrapers/baden_wuerttemberg/__init__.py` - Import + `__all__`
4. **Scrapers `__init__.py`**: `src/scrapers/__init__.py` - Import + `__all__`
5. **CLI**: `src/cli.py` - Import + `SCRAPER_REGISTRY`
6. **Debug-Tool**: `src/debug_scraper.py` - Import + `SCRAPER_REGISTRY`
7. **API-Router**: `src/api/routers/scraper.py` - Import + `SCRAPER_REGISTRY`

> Falls ein neuer Landkreis angelegt wird, muss auch das Landkreis-Package (`__init__.py`) erstellt werden.

### BaseScraper Interface

Jeder Scraper erbt von `BaseScraper` und muss definieren:

```python
from ...base import BaseScraper, ScrapedEvent

class BeispielScraper(BaseScraper):
    SOURCE_NAME = "Gemeinde Beispiel"           # Anzeigename
    BASE_URL = "https://www.beispiel.de"        # Basis-URL
    EVENTS_URL = "https://www.beispiel.de/..."  # Startseite für Events
    GEOCODE_REGION = "74XXX Beispiel"           # PLZ + Ort für Google Geocoding

    SELECTORS = {
        "event_container": "...",  # CSS-Selektor für Event-Container
        "title": "...",            # Titel
        "date": "...",             # Datum
        "time": "...",             # Uhrzeit (optional)
        "location": "...",         # Veranstaltungsort (optional)
        "url": "...",              # Link zur Detailseite (optional)
    }

    def parse_events(self, soup: BeautifulSoup) -> List[ScrapedEvent]:
        """Muss implementiert werden. Gibt Liste von ScrapedEvent zurück."""
        ...
```



### Wichtige Hinweise

- **`raw_location`** ist der Schlüssel für Location-Matching. Ohne `raw_location` wird kein Location-Eintrag erstellt und das Event erscheint nicht auf der Karte.
- **`external_id`** muss pro Source eindeutig sein. Format-Konvention: `{gemeinde}_{id}` (z.B. `crailsheim_12345`).
- **`location_postal_code`** darf max. 10 Zeichen haben (DB: `VARCHAR(10)`). Falls der Wert "74564 Crailsheim" enthält, muss die PLZ extrahiert werden.
- **Pagination**: Falls die Website paginiert ist, muss `parse_events()` alle Seiten durchlaufen. Verwende `self.fetch_page(url)` für weitere Seiten.
- **Geocoding**: Wird automatisch von `BaseScraper.get_or_create_location()` ausgeführt wenn keine Koordinaten vorhanden sind. Benötigt `GEOCODE_REGION`.
- **Detail-Seiten**: Falls Location-Daten nur auf Detail-Seiten stehen, in `parse_events()` oder einer Helper-Methode `self.fetch_page(detail_url)` aufrufen.

### Verfügbare Helper-Methoden von BaseScraper

```python
self.fetch_page(url)           # Seite laden -> BeautifulSoup (mit Rate Limiting)
self.resolve_url(relative_url) # Relative URL -> Absolute URL
self.location_exists(raw_name) # Prüft ob Location schon in DB existiert (spart Detail-Requests)
```

