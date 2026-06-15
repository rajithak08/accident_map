"""
MongoDB connection helper.
---------------------------
Centralizes the Mongo client + database handle used across the app.

Configuration (checked in this order):
  1. Streamlit secrets:  st.secrets["MONGO_URI"], st.secrets["MONGO_DB_NAME"]
  2. Environment vars:   MONGO_URI, MONGO_DB_NAME
  3. Local fallback:     mongodb://localhost:27017 / "accident_hotspot"

If no MongoDB is reachable, get_db() raises - callers should catch this
and fall back to the bundled CSV/JSON seed files (see app.py / map3d.py),
so the app keeps working even before Mongo is configured.
"""

import os
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError


def _secret(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


MONGO_URI = _secret("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = _secret("MONGO_DB_NAME", "accident_hotspot")

# Collection names
COL_ACCIDENTS = "accidents"        # live, user-submitted reports (was Supabase "accidents" table)
COL_NEWS_CRASHES = "news_crashes"  # News_Crashes.xlsx dataset (2021-22 news reports)
COL_STATE_STATS = "state_stats"    # official MoRTH state-wise accident stats, 2019-2023


@st.cache_resource
def get_client():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
    # Force a round trip so connection issues surface immediately
    client.admin.command("ping")
    return client


def get_db():
    """Returns the Mongo database handle. Raises if Mongo is unreachable."""
    return get_client()[MONGO_DB_NAME]
