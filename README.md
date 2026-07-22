# AQI — Daily air quality data for zipcode 10010

A self-updating dataset of daily Air Quality Index (AQI) values for zipcode
10010 (Flatiron/Gramercy, Manhattan), broken out by pollutant. Built to feed a
Google Sheet that Tableau (including Tableau Pulse) can connect to.

## How it works

```
Open-Meteo Air Quality API ──▶ GitHub Actions (weekly, Mondays)
        ──▶ data/aqi_daily_10010.csv ──▶ Google Sheet (IMPORTDATA) ──▶ Tableau Pulse
```

- **Source**: [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)
  — free, no API key. Hourly US AQI (overall and per pollutant) plus pollutant
  concentrations for lat 40.7387, lon -73.9826 (zipcode 10010 centroid).
- **Schedule**: `.github/workflows/update-aqi.yml` runs every Monday at 11:00
  UTC (and on demand via *Run workflow*). Each run rebuilds the full rolling
  365-day window ending yesterday, so the file always holds exactly the last
  year of complete days.
- **Aggregation**: `scripts/fetch_aqi.py` (stdlib-only Python) averages/maxes
  the 24 hourly values into one row per day per pollutant.

## The data

`data/aqi_daily_10010.csv` — long format, one row per day per pollutant
(~2,500 rows):

| Column | Description |
| --- | --- |
| `Date` | Local date (America/New_York) |
| `Zipcode` | Always `10010` |
| `Pollutant` | `PM2.5`, `PM10`, `Ozone`, `Nitrogen Dioxide`, `Sulphur Dioxide`, `Carbon Monoxide`, or `Overall` |
| `Avg Concentration (ug/m3)` | Daily mean concentration (blank for `Overall`) |
| `Daily Avg AQI` | Mean of the 24 hourly US AQI values |
| `Daily Max AQI` | Peak hourly US AQI — the usual headline "daily AQI" |
| `AQI Category` | EPA category for the daily max (Good, Moderate, …) |

## Google Sheet

The connected Google Sheet contains a single formula:

```
=IMPORTDATA("https://raw.githubusercontent.com/SSGrasland/AQI/<branch>/data/aqi_daily_10010.csv")
```

Google re-fetches IMPORTDATA sources roughly hourly, so the sheet picks up
each weekly commit automatically — no manual refresh needed.

> **Note**: scheduled GitHub Actions only fire on the repository's **default
> branch** (`main`). After merging this branch into `main`, update the URL in
> the sheet's cell A1 to point at `main`.

## Tableau Pulse notes

- Connect Tableau to the Google Sheet (Google Drive connector).
- Good starter metric: `Daily Max AQI` filtered to `Pollutant = Overall`,
  aggregated by average, time dimension `Date`.
- The `Pollutant` column works as an adjustable metric filter/dimension for
  per-pollutant breakdowns.
