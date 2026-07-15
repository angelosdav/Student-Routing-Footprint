"""
Distance calculation between two Greek postal codes.

Step 1: Geocoding (postal code -> lat/lon) via Nominatim (OpenStreetMap)
Step 2: Haversine formula (lat/lon -> distance in km)

Requirements: pip install requests --break-system-packages
"""

import requests
import time
from math import radians, sin, cos, sqrt, atan2


def geocode_tk(tk: str, country: str = "Greece") -> tuple[float, float] | None:
    """
    Converts a postal code to (latitude, longitude)
    using the free Nominatim API from OpenStreetMap.

    Important: Nominatim has a rate limit of ~1 request/second.
    If you're geocoding multiple postal codes, add time.sleep(1) between calls.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "postalcode": tk,
        "country": country,
        "format": "json",
        "limit": 1,
    }
    headers = {
        # Nominatim REQUIRES an identifiable User-Agent, otherwise it blocks (403).
        # Put YOUR real email here, not a placeholder.
        "User-Agent": "phd-project-diploma-thesis/1.0 (VALE_TO_EMAIL_SOU@gmail.com)",
        "Referer": "https://github.com/",  # a realistic referer helps
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    results = response.json()

    if not results:
        print(f"  -> Postal code {tk} not found")
        return None

    lat = float(results[0]["lat"])
    lon = float(results[0]["lon"])
    return lat, lon


def geocode_tk_photon(tk: str, country: str = "Greece") -> tuple[float, float] | None:
    """
    Alternative geocoding via Photon (Komoot), in case
    Nominatim keeps returning 403. Free, no API key required.
    """
    url = "https://photon.komoot.io/api/"
    params = {"q": f"{tk} {country}", "limit": 1}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    features = data.get("features", [])
    if not features:
        print(f"  -> Postal code {tk} not found (Photon)")
        return None

    lon, lat = features[0]["geometry"]["coordinates"]
    return lat, lon


def road_distance(coord1: tuple[float, float], coord2: tuple[float, float],
                   profile: str = "driving") -> float | None:
    """
    Calculates the ACTUAL road distance (not straight-line) via the free
    public OSRM server, based on the real road network.

    coord1, coord2: (lat, lon)
    profile: "driving", "walking", or "cycling"

    Note: the public OSRM demo server (router.project-osrm.org) is not
    intended for production/heavy use, it has informal rate limits. For
    bulk execution across many students, it's better to set up your own
    OSRM instance (docker) or use a paid provider (e.g. OpenRouteService, Mapbox).
    """
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    # OSRM expects lon,lat (reversed from the usual order!)
    url = f"http://router.project-osrm.org/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "false"}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        print("  -> Route not found")
        return None

    distance_meters = data["routes"][0]["distance"]
    return distance_meters / 1000  # -> km


def haversine_distance(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """
    Calculates the straight-line (great-circle) distance in kilometers
    between two points (lat, lon), using the Haversine formula.
    """
    R = 6371.0  # Earth's radius in km

    lat1, lon1 = coord1
    lat2, lon2 = coord2

    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def distance_between_postal_codes(tk1: str, tk2: str) -> float | None:
    """
    Combines the two steps: geocoding + Haversine.
    Returns the distance in km, or None if a postal code wasn't found.
    """
    coord1 = geocode_tk(tk1)
    time.sleep(1)  # be polite to the free API
    coord2 = geocode_tk(tk2)

    if coord1 is None or coord2 is None:
        return None

    return haversine_distance(coord1, coord2)