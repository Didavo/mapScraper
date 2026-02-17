#!/usr/bin/env python
"""
Test-Skript für Google Geocoding API.

Usage:
    python -m src.test_geocoding "Hauptstraße 1, 74653 Künzelsau"
    python -m src.test_geocoding "Rathaus, Mulfingen"
"""

import argparse
import requests
from src.config import get_settings


def geocode_address(address: str) -> dict:
    """
    Konvertiert eine Adresse in Koordinaten via Google Geocoding API.

    Returns:
        dict mit lat, lng, formatted_address oder error
    """
    settings = get_settings()

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": settings.google_api_key,
        "language": "de",
        "region": "de",
    }

    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    if data["status"] == "OK":
        result = data["results"][0]
        location = result["geometry"]["location"]
        return {
            "success": True,
            "latitude": location["lat"],
            "longitude": location["lng"],
            "formatted_address": result["formatted_address"],
            "place_id": result.get("place_id"),
            "types": result.get("types", []),
        }
    else:
        return {
            "success": False,
            "error": data["status"],
            "error_message": data.get("error_message", "Unbekannter Fehler"),
        }


def main():
    parser = argparse.ArgumentParser(description="Google Geocoding API Test")
    parser.add_argument("address", nargs="?", help="Adresse zum Geocodieren")
    parser.add_argument("--test", "-t", action="store_true", help="Führe Beispiel-Tests aus")
    args = parser.parse_args()

    if args.test:
        # Test mit mehreren Beispiel-Adressen
        test_addresses = [
            "Hauptstraße 10, 74653 Künzelsau",
            "Rathaus, 74673 Mulfingen",
            "Schwarzer Hof, Ingelfingen",
            "Dörzbach, Baden-Württemberg",
        ]

        print("=" * 60)
        print("Google Geocoding API Test")
        print("=" * 60)

        for addr in test_addresses:
            print(f"\nAdresse: {addr}")
            print("-" * 40)
            result = geocode_address(addr)

            if result["success"]:
                print(f"  Latitude:  {result['latitude']}")
                print(f"  Longitude: {result['longitude']}")
                print(f"  Formatiert: {result['formatted_address']}")
            else:
                print(f"  FEHLER: {result['error']}")
                print(f"  {result['error_message']}")

    elif args.address:
        # Einzelne Adresse geocodieren
        print(f"\nGeocoding: {args.address}")
        print("-" * 40)

        result = geocode_address(args.address)

        if result["success"]:
            print(f"Latitude:  {result['latitude']}")
            print(f"Longitude: {result['longitude']}")
            print(f"Formatiert: {result['formatted_address']}")
            print(f"Place ID: {result['place_id']}")
            print(f"Types: {', '.join(result['types'])}")
        else:
            print(f"FEHLER: {result['error']}")
            print(f"{result['error_message']}")

    else:
        parser.print_help()
        print("\nBeispiele:")
        print('  python -m src.test_geocoding "Hauptstraße 1, Künzelsau"')
        print('  python -m src.test_geocoding --test')


if __name__ == "__main__":
    main()
