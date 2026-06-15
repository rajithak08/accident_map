"""
One-time migration script: loads the bundled CSV/JSON seed data into MongoDB.

Run this once after pointing MONGO_URI (env var or .streamlit/secrets.toml)
at your MongoDB instance:

    python migrate_to_mongo.py

It (re)creates three collections in the `accident_hotspot` database
(or whatever MONGO_DB_NAME you configured):

  - accidents     <- accidents_dataset.csv   (live/seed accident reports)
  - news_crashes  <- news_crashes.csv        (2,898 News_Crashes records)
  - state_stats   <- state_stats.json        (official 2019-2023 stats per state)

Existing documents in these collections are dropped first, so it's safe
to re-run if you update the seed files.
"""

import json
import pandas as pd
from db import get_db, COL_ACCIDENTS, COL_NEWS_CRASHES, COL_STATE_STATS


def load_accidents():
    df = pd.read_csv("accidents_dataset.csv")
    df['injured'] = pd.to_numeric(df['injured'], errors='coerce').fillna(0).astype(int)
    df['deaths'] = pd.to_numeric(df['deaths'], errors='coerce').fillna(0).astype(int)
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df = df.dropna(subset=['latitude', 'longitude'])

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row['date']) if pd.notna(row['date']) else None,
            "time": str(row['time']) if pd.notna(row['time']) else None,
            "location": str(row['location']) if pd.notna(row['location']) else None,
            "latitude": float(row['latitude']),
            "longitude": float(row['longitude']),
            "deaths": int(row['deaths']),
            "injured": int(row['injured']),
            "cause": str(row['cause']) if pd.notna(row['cause']) else None,
            "vehicle": str(row['vehicle']) if pd.notna(row['vehicle']) else None,
            "url": str(row['url']) if pd.notna(row['url']) else None,
        })
    return records


def load_news_crashes():
    df = pd.read_csv("news_crashes.csv").fillna("")
    return df.to_dict(orient="records")


def load_state_stats():
    with open("state_stats.json") as f:
        return json.load(f)


def main():
    db = get_db()

    accidents = load_accidents()
    db[COL_ACCIDENTS].drop()
    if accidents:
        db[COL_ACCIDENTS].insert_many(accidents)
    print(f"accidents: inserted {len(accidents)} documents")

    news = load_news_crashes()
    db[COL_NEWS_CRASHES].drop()
    if news:
        db[COL_NEWS_CRASHES].insert_many(news)
    print(f"news_crashes: inserted {len(news)} documents")

    stats = load_state_stats()
    db[COL_STATE_STATS].drop()
    if stats:
        db[COL_STATE_STATS].insert_many(stats)
    print(f"state_stats: inserted {len(stats)} documents")

    # Helpful indexes
    db[COL_ACCIDENTS].create_index([("latitude", 1), ("longitude", 1)])
    db[COL_NEWS_CRASHES].create_index("state")
    db[COL_STATE_STATS].create_index([("state", 1), ("year", 1)], unique=True)

    print("\n✅ Done! MongoDB seeded from CSV/JSON files.")


if __name__ == "__main__":
    main()
