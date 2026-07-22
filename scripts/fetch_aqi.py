#!/usr/bin/env python3
"""Fetch the last 365 days of daily AQI data for zipcode 10010 (Manhattan, NYC).

Pulls hourly US AQI values (overall and per pollutant) plus pollutant
concentrations from the Open-Meteo Air Quality API, aggregates them to one row
per day per pollutant, and writes data/aqi_daily_10010.csv.

The script is idempotent: every run rebuilds the full rolling 365-day window,
so there is no incremental merge logic to break.

Uses only the Python standard library so it runs on a bare GitHub Actions
runner with no pip installs.
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ZIPCODE = "10010"
# Centroid of zipcode 10010 (Flatiron/Gramercy, Manhattan)
LATITUDE = 40.7387
LONGITUDE = -73.9826
TIMEZONE = "America/New_York"

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Display name -> (AQI variable, concentration variable)
POLLUTANTS = {
    "PM2.5": ("us_aqi_pm2_5", "pm2_5"),
    "PM10": ("us_aqi_pm10", "pm10"),
    "Ozone": ("us_aqi_ozone", "ozone"),
    "Nitrogen Dioxide": ("us_aqi_nitrogen_dioxide", "nitrogen_dioxide"),
    "Sulphur Dioxide": ("us_aqi_sulphur_dioxide", "sulphur_dioxide"),
    "Carbon Monoxide": ("us_aqi_carbon_monoxide", "carbon_monoxide"),
    "Overall": ("us_aqi", None),
}

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "aqi_daily_10010.csv"

DAYS_OF_HISTORY = 365
CHUNK_DAYS = 90  # keep each API request comfortably sized
MAX_RETRIES = 4


def aqi_category(aqi: float) -> str:
    """EPA AQI category names."""
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def fetch_chunk(start: date, end: date) -> dict:
    hourly_vars = sorted(
        {var for pair in POLLUTANTS.values() for var in pair if var is not None}
    )
    params = urllib.parse.urlencode(
        {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "hourly": ",".join(hourly_vars),
            "timezone": TIMEZONE,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
    )
    url = f"{API_URL}?{params}"
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                payload = json.load(resp)
            if "hourly" not in payload or "time" not in payload["hourly"]:
                raise ValueError(f"Unexpected API response keys: {sorted(payload)}")
            return payload["hourly"]
        except Exception as exc:  # noqa: BLE001 - retry any transient failure
            last_error = exc
            wait = 2 ** (attempt + 1)
            print(f"  attempt {attempt + 1} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {start}..{end}: {last_error}")


def main() -> int:
    today_local = datetime.now(ZoneInfo(TIMEZONE)).date()
    end = today_local - timedelta(days=1)  # yesterday = last complete day
    start = end - timedelta(days=DAYS_OF_HISTORY - 1)
    print(f"Fetching {start} .. {end} for zipcode {ZIPCODE}")

    # {date -> {variable -> [hourly values]}}
    days: dict[str, dict[str, list[float]]] = {}

    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS - 1), end)
        print(f"Requesting chunk {chunk_start} .. {chunk_end}")
        hourly = fetch_chunk(chunk_start, chunk_end)
        times = hourly["time"]
        for i, stamp in enumerate(times):
            day = stamp[:10]
            bucket = days.setdefault(day, {})
            for _, (aqi_var, conc_var) in POLLUTANTS.items():
                for var in (aqi_var, conc_var):
                    if var is None:
                        continue
                    value = hourly.get(var, [None] * len(times))[i]
                    if value is not None:
                        bucket.setdefault(var, []).append(value)
        chunk_start = chunk_end + timedelta(days=1)

    rows = []
    for day in sorted(days):
        bucket = days[day]
        for name, (aqi_var, conc_var) in POLLUTANTS.items():
            aqi_values = bucket.get(aqi_var, [])
            if not aqi_values:
                continue
            avg_aqi = round(sum(aqi_values) / len(aqi_values), 1)
            max_aqi = round(max(aqi_values))
            conc_values = bucket.get(conc_var, []) if conc_var else []
            avg_conc = (
                round(sum(conc_values) / len(conc_values), 2) if conc_values else ""
            )
            rows.append(
                {
                    "Date": day,
                    "Zipcode": ZIPCODE,
                    "Pollutant": name,
                    "Avg Concentration (ug/m3)": avg_conc,
                    "Daily Avg AQI": avg_aqi,
                    "Daily Max AQI": max_aqi,
                    "AQI Category": aqi_category(max_aqi),
                }
            )

    if not rows:
        print("ERROR: no data returned by the API", file=sys.stderr)
        return 1

    n_days = len({r["Date"] for r in rows})
    print(f"Writing {len(rows)} rows covering {n_days} days to {OUTPUT_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
