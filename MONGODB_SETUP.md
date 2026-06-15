# Accident Hotspot Dashboard — MongoDB setup

This app now uses **MongoDB** instead of Supabase, for two things:

1. `accidents` collection — live, user-submitted reports (Live Map + Report tabs).
2. `news_crashes` / `state_stats` collections — the data behind the 3D India
   map (2021-22 News_Crashes reports and 2019-2023 official MoRTH stats).
   Keeping these in Mongo means you can edit/update them later (e.g. add a
   2024/2025 stats row, correct a record) without touching code.

## 1. Configure your connection

Create `.streamlit/secrets.toml` (recommended) or set environment variables:

```toml
# .streamlit/secrets.toml
MONGO_URI = "mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
MONGO_DB_NAME = "accident_hotspot"   # optional, this is the default
```

or:

```bash
export MONGO_URI="mongodb+srv://..."
export MONGO_DB_NAME="accident_hotspot"
```

Any MongoDB works — Atlas free tier, a self-hosted instance, or local
`mongodb://localhost:27017` for testing.

## 2. Seed the database (one time)

```bash
pip install -r requirements.txt
python migrate_to_mongo.py
```

This loads `accidents_dataset.csv`, `news_crashes.csv`, and
`state_stats.json` into the three collections above and creates a few
indexes. Re-run it any time you want to reset/refresh the seed data.

## 3. Run the app

```bash
streamlit run app.py
```

## Fallback behavior

If `MONGO_URI` isn't set or MongoDB isn't reachable, the app automatically
falls back to reading the bundled CSV/JSON files directly — so it still
works out of the box for a quick demo, but new reports submitted via the
"Report an Accident" tab won't be saved anywhere in that case.

## Editing the 3D map's reference data later

Once seeded, you can update data straight in MongoDB, e.g. via
`mongosh` / Compass / Atlas UI:

- `news_crashes`: one document per news-reported accident
  (fields: state, location, lat, lon, crash_date, month, killed, injured,
  vehicle1, vehicle2, road_type, crash_type, ...)
- `state_stats`: one document per (state, year) with `accidents` and
  `ranking` — add a `year: 2024` set of documents here once that data is
  published and it'll show up automatically in the "Official Stats" year
  selector.
- `accidents`: live reports, same shape as `accidents_dataset.csv`.

The 3D map's `st.cache_data` cache is set to refresh every hour
(`ttl=3600`), or restart the app / call `st.cache_data.clear()` to see
changes immediately.
