"""Work zone centers — must stay aligned with frontend `src/data/zones.ts` (id, lat, lon)."""

from __future__ import annotations

from typing import TypedDict


class ZoneCenter(TypedDict):
    id: str
    lat: float
    lon: float


# ~25–30 km radius eligibility is applied in fraud checks (see `ZONE_MATCH_RADIUS_KM`).
WORK_ZONE_CENTERS: list[ZoneCenter] = [
    {"id": "chennai-t-nagar", "lat": 13.0418, "lon": 80.2341},
    {"id": "chennai-velachery", "lat": 12.9815, "lon": 80.2209},
    {"id": "chennai-omr", "lat": 12.9499, "lon": 80.2381},
    {"id": "bengaluru-koramangala", "lat": 12.9352, "lon": 77.6245},
    {"id": "bengaluru-whitefield", "lat": 12.9698, "lon": 77.75},
    {"id": "bengaluru-indiranagar", "lat": 12.9719, "lon": 77.6412},
    {"id": "bengaluru-electronic-city", "lat": 12.8456, "lon": 77.6603},
    {"id": "mumbai-andheri", "lat": 19.1136, "lon": 72.8697},
    {"id": "mumbai-borivali", "lat": 19.2313, "lon": 72.8564},
    {"id": "mumbai-thane", "lat": 19.2183, "lon": 72.9781},
    {"id": "delhi-connaught", "lat": 28.6315, "lon": 77.2167},
    {"id": "delhi-rohini", "lat": 28.7495, "lon": 77.0627},
    {"id": "gurugram-cyber-city", "lat": 28.495, "lon": 77.089},
    {"id": "noida-sector-18", "lat": 28.5703, "lon": 77.3216},
    {"id": "hyderabad-hitec", "lat": 17.4474, "lon": 78.3762},
    {"id": "hyderabad-gachibowli", "lat": 17.4401, "lon": 78.3489},
    {"id": "pune-kothrud", "lat": 18.5074, "lon": 73.8077},
    {"id": "pune-viman-nagar", "lat": 18.5679, "lon": 73.9143},
    {"id": "kolkata-park-street", "lat": 22.5511, "lon": 88.3527},
    {"id": "ahmedabad-satellite", "lat": 23.0258, "lon": 72.5873},
    {"id": "jaipur-vaishali", "lat": 26.9124, "lon": 75.7873},
    {"id": "kochi-edappally", "lat": 10.0262, "lon": 76.3084},
    {"id": "coimbatore-rs-puram", "lat": 11.0168, "lon": 76.9558},
    {"id": "lucknow-gomti", "lat": 26.8467, "lon": 80.9462},
    {"id": "indore-vijay-nagar", "lat": 22.7533, "lon": 75.8937},
    {"id": "chandigarh", "lat": 30.7333, "lon": 76.7794},
    {"id": "visakhapatnam-mvp", "lat": 17.7215, "lon": 83.318},
    {"id": "bhubaneswar-patia", "lat": 20.356, "lon": 85.8246},
]

ZONE_BY_ID: dict[str, ZoneCenter] = {z["id"]: z for z in WORK_ZONE_CENTERS}

# Workers must be within this distance of the selected zone centroid (metro-scale).
ZONE_MATCH_RADIUS_KM = 32.0
