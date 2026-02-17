"""
Google Geocoding Service.

Verwendet die Google Maps Geocoding API um Adressen in Koordinaten umzuwandeln.
"""

from dataclasses import dataclass
from typing import Optional
import requests

from src.config import get_settings
from src.models import GeocodingStatus


@dataclass
class GeocodingResult:
    """Ergebnis eines Geocoding-Versuchs."""
    status: GeocodingStatus
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: Optional[str] = None
    error_message: Optional[str] = None
    results_count: int = 0  # Anzahl der Google-Ergebnisse


class GeocodingService:
    """
    Service für Google Maps Geocoding API.

    Usage:
        service = GeocodingService()
        result = service.geocode("Stauseehalle", "74673 Mulfingen")

        if result.status == GeocodingStatus.SUCCESS:
            print(f"Lat: {result.latitude}, Lon: {result.longitude}")
    """

    API_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(self, dry_run: bool = False):
        """
        Initialisiert den Geocoding Service.

        Args:
            dry_run: Wenn True, werden keine API-Calls gemacht.
                     Stattdessen wird geloggt was gemacht würde.
        """
        self.settings = get_settings()
        self.dry_run = dry_run

    def geocode(self, raw_name: str, region: str) -> GeocodingResult:
        """
        Geocodiert eine Location.

        Args:
            raw_name: Name der Location (z.B. "Stauseehalle")
            region: GEOCODE_REGION des Scrapers (z.B. "74673 Mulfingen")

        Returns:
            GeocodingResult mit Status und ggf. Koordinaten
        """
        # Suchstring zusammenbauen
        search_address = f"{raw_name}, {region}"

        if self.dry_run:
            print(f"[DRY-RUN] Würde geocoden: '{search_address}'")
            return GeocodingResult(
                status=GeocodingStatus.SUCCESS,
                latitude=0.0,
                longitude=0.0,
                formatted_address=f"[DRY-RUN] {search_address}",
            )

        try:
            response = requests.get(
                self.API_URL,
                params={
                    "address": search_address,
                    "key": self.settings.google_api_key,
                    "language": "de",
                    "region": "de",
                },
                timeout=10,
            )
            data = response.json()

            if data["status"] == "OK":
                results = data["results"]
                results_count = len(results)
                result = results[0]
                location = result["geometry"]["location"]

                if results_count > 1:
                    print(f"[GEOCODING] MEHRFACH ({results_count} Ergebnisse) '{search_address}' -> {location['lat']}, {location['lng']} (verwende erstes)")
                    status = GeocodingStatus.MULTIPLE
                else:
                    print(f"[GEOCODING] '{search_address}' -> {location['lat']}, {location['lng']}")
                    status = GeocodingStatus.SUCCESS

                return GeocodingResult(
                    status=status,
                    latitude=location["lat"],
                    longitude=location["lng"],
                    formatted_address=result["formatted_address"],
                    results_count=results_count,
                )

            elif data["status"] == "ZERO_RESULTS":
                print(f"[GEOCODING] Keine Ergebnisse für: '{search_address}'")
                return GeocodingResult(
                    status=GeocodingStatus.NOT_FOUND,
                    error_message=f"Keine Ergebnisse für: {search_address}",
                )

            else:
                # Andere Fehler: OVER_QUERY_LIMIT, REQUEST_DENIED, INVALID_REQUEST, etc.
                error_msg = data.get("error_message", data["status"])
                print(f"[GEOCODING] API-Fehler: {error_msg}")
                return GeocodingResult(
                    status=GeocodingStatus.ERROR,
                    error_message=error_msg,
                )

        except requests.RequestException as e:
            print(f"[GEOCODING] Netzwerkfehler: {e}")
            return GeocodingResult(
                status=GeocodingStatus.ERROR,
                error_message=str(e),
            )
        except Exception as e:
            print(f"[GEOCODING] Unerwarteter Fehler: {e}")
            return GeocodingResult(
                status=GeocodingStatus.ERROR,
                error_message=str(e),
            )
