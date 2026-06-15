import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
import json
import os
from datetime import datetime
import requests
import plotly.graph_objects as go
from db import get_db, COL_ACCIDENTS, COL_NEWS_CRASHES, COL_STATE_STATS
from map3d import render_html as render_3d_map_html

# --- CONFIG ---
TOMTOM_KEY = "IFjf18FTjpUqfuLCebGBOV47UQBezPCj"

st.set_page_config(page_title="Accident Hotspot Dashboard", page_icon="🚨", layout="wide")

# --- SESSION STATE INIT (must be first) ---
if 'user_lat' not in st.session_state:
    st.session_state.user_lat = 0.0
if 'user_lon' not in st.session_state:
    st.session_state.user_lon = 0.0
if 'click_lat' not in st.session_state:
    st.session_state.click_lat = 0.0
if 'click_lon' not in st.session_state:
    st.session_state.click_lon = 0.0

# --- READ GPS FROM URL PARAMS ---
params = st.query_params
if params.get("gps_lat", "0.0") not in ("0.0", ""):
    st.session_state.user_lat = float(params.get("gps_lat"))
    st.session_state.user_lon = float(params.get("gps_lon"))

user_lat = st.session_state.user_lat
user_lon = st.session_state.user_lon

# --- GPS BUTTON ---
gps_html = """
<script>
function getLocation() {
    const btn = document.getElementById('gps-btn');
    const status = document.getElementById('gps-status');
    const box = document.getElementById('gps-result');
    btn.disabled = true;
    btn.innerText = '⏳ Detecting...';
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(pos) {
            const lat = pos.coords.latitude.toFixed(6);
            const lon = pos.coords.longitude.toFixed(6);
            btn.disabled = false;
            btn.innerText = '📍 Get My GPS Location';
            status.innerText = '✅ Detected! Copy coordinates below:';
            box.style.display = 'block';
            document.getElementById('lat-val').value = lat;
            document.getElementById('lon-val').value = lon;
        }, function(err) {
            btn.disabled = false;
            btn.innerText = '📍 Get My GPS Location';
            status.innerText = '❌ Permission denied. Allow location in browser settings.';
        }, { enableHighAccuracy: true, timeout: 15000 });
    } else {
        status.innerText = '❌ Geolocation not supported.';
    }
}
</script>
<div style="font-family:Arial;margin:4px 0;">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <button id="gps-btn" onclick="getLocation()" style="
            background:#007bff;color:white;border:none;padding:10px 20px;
            border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">
            📍 Get My GPS Location
        </button>
        <span id="gps-status" style="font-size:13px;color:#555;">Click to detect your location</span>
    </div>
    <div id="gps-result" style="display:none;margin-top:10px;background:#f0f8ff;padding:10px;border-radius:8px;border:1px solid #007bff;">
        <b style="color:#007bff;">Your coordinates (copy and paste into fields below):</b><br><br>
        <label>Latitude:</label>
        <input id="lat-val" type="text" readonly onclick="this.select()" style="
            width:160px;padding:6px;border:1px solid #ccc;border-radius:4px;
            font-size:14px;font-weight:bold;color:#333;cursor:pointer;margin:4px 8px 4px 0;">
        <label>Longitude:</label>
        <input id="lon-val" type="text" readonly onclick="this.select()" style="
            width:160px;padding:6px;border:1px solid #ccc;border-radius:4px;
            font-size:14px;font-weight:bold;color:#333;cursor:pointer;">
        <br><small style="color:#666;">👆 Click each field to select, then Ctrl+C to copy</small>
    </div>
</div>
"""

# --- HAVERSINE ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# --- TOMTOM ---
@st.cache_data(ttl=300)
def get_traffic_flow(lat, lon):
    try:
        r = requests.get(
            "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json",
            params={"point": f"{lat},{lon}", "key": TOMTOM_KEY, "unit": "KMPH"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("flowSegmentData", {})
            return {
                "current_speed": data.get("currentSpeed", 0),
                "free_flow_speed": data.get("freeFlowSpeed", 0),
                "current_travel_time": data.get("currentTravelTime", 0),
                "free_flow_travel_time": data.get("freeFlowTravelTime", 0),
                "confidence": data.get("confidence", 0),
                "road_closure": data.get("roadClosure", False),
            }
    except:
        return None
    return None



# --- LOAD DATA ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
EMPTY_DF = pd.DataFrame(columns=['date','time','location','latitude','longitude','deaths','injured','cause','vehicle','url'])

@st.cache_data(ttl=0)
def load_data():
    try:
        db = get_db()
        docs = list(db[COL_ACCIDENTS].find({}, {"_id": 0}))
        if not docs:
            return EMPTY_DF.copy()
        df = pd.DataFrame(docs)
    except Exception:
        # MongoDB not configured/reachable yet -> fall back to bundled seed CSV
        try:
            df = pd.read_csv(os.path.join(APP_DIR, "accidents_dataset.csv"))
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            return EMPTY_DF.copy()

    df['deaths'] = pd.to_numeric(df['deaths'], errors='coerce').fillna(0).astype(int)
    df['injured'] = pd.to_numeric(df['injured'], errors='coerce').fillna(0).astype(int)
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    return df.dropna(subset=['latitude', 'longitude'])

df = load_data()


# --- 3D MAP DATA (state totals + individual reports + boundaries) ---
@st.cache_data(ttl=3600)
def load_3d_map_data():
    try:
        db = get_db()
        news_points = pd.DataFrame(list(db[COL_NEWS_CRASHES].find({}, {"_id": 0})))
        state_stats = list(db[COL_STATE_STATS].find({}, {"_id": 0}))
        if news_points.empty or not state_stats:
            raise ValueError("empty collections")
    except Exception:
        # MongoDB not configured/reachable yet -> fall back to bundled seed files
        news_points = pd.read_csv(os.path.join(APP_DIR, "news_crashes.csv"))
        with open(os.path.join(APP_DIR, "state_stats.json")) as f:
            state_stats = json.load(f)

    with open(os.path.join(APP_DIR, "india_states_final.geojson")) as f:
        geojson_obj = json.load(f)

    return news_points, state_stats, geojson_obj

news_points_df, state_stats_records, india_geojson = load_3d_map_data()



# --- TITLE ---
st.title("🚨 Accident Hotspot Dashboard")

# --- 3D INDIA MAP (landing view) ---
st.subheader("🇮🇳 India — Accident Hotspots (3D)")
st.caption("Bar height & color show total accidents per state. Switch between News Reports (2021-22, drill-down to individual reports) and Official MoRTH Stats (2019-2023). Zoom in to a state to reveal individual News Reports.")
map_html = render_3d_map_html(news_points_df, state_stats_records, india_geojson, height=640)
st.components.v1.html(map_html, height=700, scrolling=False)

# --- LOCATION BAR — always visible at top ---
with st.expander("📍 Set Your Location (used across all tabs)", expanded=st.session_state.user_lat == 0.0):
    st.components.v1.html(gps_html, height=130)
    st.markdown("**Or enter manually:**")
    loc1, loc2, loc3 = st.columns([2, 2, 1])
    with loc1:
        input_lat = st.number_input("Latitude", value=st.session_state.user_lat if st.session_state.user_lat != 0.0 else 13.0963, format="%.6f", key="input_lat")
    with loc2:
        input_lon = st.number_input("Longitude", value=st.session_state.user_lon if st.session_state.user_lon != 0.0 else 80.2343, format="%.6f", key="input_lon")
    with loc3:
        st.write("")
        st.write("")
        if st.button("✅ Apply", type="primary", use_container_width=True):
            st.session_state.user_lat = input_lat
            st.session_state.user_lon = input_lon
            st.rerun()

if st.session_state.user_lat != 0.0:
    user_lat = st.session_state.user_lat
    user_lon = st.session_state.user_lon
    st.success(f"📍 Active location: **{user_lat}, {user_lon}** — used across all tabs")

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Live Map", "🚦 Traffic History", "📍 Proximity Alert", "🆘 Report Accident"])

# ================================================================
# TAB 1 — LIVE MAP
# ================================================================
with tab1:
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        search_query = st.text_input("Filter by location keyword", "")
    with col_f2:
        max_deaths = int(df['deaths'].max()) if not df.empty and df['deaths'].max() > 0 else 10
        severity_floor = st.slider("Min deaths", 0, max_deaths, 0)

    map_style = st.radio("Map Style", ["🛰️ ISRO Bhuvan (NavIC)", "🛰️ Esri Satellite", "🗺️ OpenStreetMap"], horizontal=True)

    df_filtered = df.copy()
    if search_query and not df_filtered.empty:
        df_filtered = df_filtered[df_filtered['location'].str.contains(search_query, case=False, na=False)]
    if not df_filtered.empty:
        df_filtered = df_filtered[df_filtered['deaths'] >= severity_floor]

    k1, k2, k3 = st.columns(3)
    k1.metric("Total Accidents", len(df_filtered))
    k2.metric("Total Fatalities", int(df_filtered['deaths'].sum()) if not df_filtered.empty else 0)
    k3.metric("Total Injuries", int(df_filtered['injured'].sum()) if not df_filtered.empty else 0)

    if user_lat != 0.0:
        center_lat, center_lon, zoom = user_lat, user_lon, 12
    elif not df_filtered.empty:
        center_lat = float(df_filtered['latitude'].mean())
        center_lon = float(df_filtered['longitude'].mean())
        zoom = 6
    else:
        center_lat, center_lon, zoom = 20.5937, 78.9629, 6

    if map_style == "🛰️ ISRO Bhuvan (NavIC)":
        accident_map = folium.Map(
            location=[center_lat, center_lon], zoom_start=zoom,
            tiles="https://bhuvan-vec1.nrsc.gov.in/bhuvan/gwc/service/wmts?layer=bhuvan_imagery&style=default&tilematrixset=EPSG:900913&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/jpeg&TileMatrix=EPSG:900913:{z}&TileCol={x}&TileRow={y}",
            attr="ISRO Bhuvan NavIC Satellite"
        )
    elif map_style == "🛰️ Esri Satellite":
        accident_map = folium.Map(
            location=[center_lat, center_lon], zoom_start=zoom,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery"
        )
    else:
        accident_map = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)

    if user_lat != 0.0:
        pulse_html = '''<div style="width:18px;height:18px;background:#007bff;border:3px solid white;
            border-radius:50%;box-shadow:0 0 0 0 rgba(0,123,255,0.6);animation:pulse 1.5s infinite;"></div>
        <style>@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(0,123,255,0.6);}
        70%{box-shadow:0 0 0 14px rgba(0,123,255,0);}100%{box-shadow:0 0 0 0 rgba(0,123,255,0);}}</style>'''
        folium.Marker(
            location=[user_lat, user_lon], popup="<b>📍 Your Location</b>", tooltip="You are here",
            icon=folium.DivIcon(html=pulse_html, icon_size=(18,18), icon_anchor=(9,9))
        ).add_to(accident_map)

    if st.session_state.click_lat != 0.0:
        folium.Marker(
            location=[st.session_state.click_lat, st.session_state.click_lon],
            popup="📍 Selected — check Traffic History or Report tab",
            icon=folium.Icon(color='green', icon='plus', prefix='fa')
        ).add_to(accident_map)

    if not df_filtered.empty:
        for _, row in df_filtered.iterrows():
            color = "red" if row['deaths'] > 0 else "orange"
            url_html = f"<a href='{row['url']}' target='_blank' style='background:#007bff;color:white;padding:4px 8px;border-radius:3px;text-decoration:none;display:inline-block;margin-top:5px'>🌐 News</a>" if row.get('url') else ""
            popup_html = f"""<div style="font-family:Arial;font-size:11px;width:220px">
                <b style="color:#d9534f">Accident Report</b><br>
                <b>Location:</b> {row.get('location','')}<br>
                <b>Cause:</b> {row.get('cause','')}<br>
                <span style="color:red"><b>Deaths: {row['deaths']}</b></span> |
                <span style="color:orange"><b>Injured: {row['injured']}</b></span><br>
                <b>Date:</b> {row.get('date','')}<br>{url_html}</div>"""
            folium.CircleMarker(
                location=[row['latitude'], row['longitude']],
                radius=6 + int(row['deaths']),
                color=color, fill=True, fill_color=color, fill_opacity=0.7,
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f"💀 {row['deaths']} | {row.get('location','')}"
            ).add_to(accident_map)

    st.info("💡 Click anywhere on the map → go to Traffic History or Report Accident tab.")
    map_data = st_folium(accident_map, width="100%", height=560, returned_objects=["last_clicked"])

    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        st.session_state.click_lat = round(clicked["lat"], 6)
        st.session_state.click_lon = round(clicked["lng"], 6)
        st.success(f"📍 Pinned: {st.session_state.click_lat}, {st.session_state.click_lon} — now check other tabs")

# ================================================================
# TAB 2 — TRAFFIC HISTORY
# ================================================================
with tab2:
    st.subheader("🚦 Traffic History — Average Speed by Hour")
    st.caption("Click any location on the Live Map first, or use GPS button below.")

    if st.session_state.click_lat != 0.0:
        t_lat = st.session_state.click_lat
        t_lon = st.session_state.click_lon
        st.success(f"📍 Showing traffic for map-clicked location: {t_lat}, {t_lon}")
    elif user_lat != 0.0:
        t_lat = user_lat
        t_lon = user_lon
        st.success(f"📍 Showing traffic for your GPS location: {t_lat}, {t_lon}")
    else:
        t_lat, t_lon = 0.0, 0.0
        st.warning("⚠️ No location selected. Click a spot on the Live Map tab first, or use the GPS button at the top of the page.")

    if t_lat != 0.0:
        with st.spinner("Fetching live traffic data from TomTom..."):
            traffic = get_traffic_flow(t_lat, t_lon)

        if traffic:
            free_flow = traffic['free_flow_speed']
            current = traffic['current_speed']
            travel_time = traffic['current_travel_time']
            free_travel_time = traffic['free_flow_travel_time']
            confidence = traffic['confidence']
            road_closure = traffic['road_closure']
            congestion_pct = round((1 - current / free_flow) * 100) if free_flow > 0 else 0

            if road_closure:
                st.error("🚫 Road closure reported at this location!")

            # Congestion label
            if congestion_pct <= 25:
                cong_label = "🟢 Free Flowing"
                cong_color = "green"
            elif congestion_pct <= 50:
                cong_label = "🟡 Moderate Congestion"
                cong_color = "orange"
            else:
                cong_label = "🔴 Heavy Congestion"
                cong_color = "red"

            st.markdown(f"### {cong_label}")

            # Real metrics from TomTom
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Speed", f"{current} km/h",
                      delta=f"{current - free_flow} km/h vs free flow",
                      delta_color="normal")
            m2.metric("Free Flow Speed", f"{free_flow} km/h",
                      help="Ideal speed on this road with no congestion")
            m3.metric("Congestion Level", f"{congestion_pct}%")
            m4.metric("Data Confidence", f"{round(confidence * 100)}%",
                      help="TomTom's confidence in this reading")

            if travel_time > 0 and free_travel_time > 0:
                delay = travel_time - free_travel_time
                st.info(f"🕐 Current travel time on this segment: **{travel_time}s** | Free flow: **{free_travel_time}s** | Delay: **+{delay}s**")

            st.markdown("---")

            # Speed gauge chart - real data only
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=current,
                delta={'reference': free_flow, 'increasing': {'color': "green"}, 'decreasing': {'color': "red"}},
                gauge={
                    'axis': {'range': [0, free_flow * 1.1]},
                    'bar': {'color': cong_color},
                    'steps': [
                        {'range': [0, free_flow * 0.5], 'color': '#ffcccc'},
                        {'range': [free_flow * 0.5, free_flow * 0.75], 'color': '#fff3cc'},
                        {'range': [free_flow * 0.75, free_flow * 1.1], 'color': '#ccffcc'},
                    ],
                    'threshold': {
                        'line': {'color': "green", 'width': 3},
                        'thickness': 0.75,
                        'value': free_flow
                    }
                },
                title={'text': "Current Speed (km/h) vs Free Flow"},
                number={'suffix': " km/h"}
            ))
            fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            st.caption("🟢 Green zone = free flowing | 🟡 Yellow = moderate | 🔴 Red = heavy congestion | Green line = free flow speed")

            st.markdown("---")
            st.subheader("⚠️ Accidents Near This Location")
            if not df.empty:
                nearby_acc = [dict(**row.to_dict(), distance_km=round(haversine(t_lat, t_lon, row['latitude'], row['longitude']), 2))
                              for _, row in df.iterrows()
                              if haversine(t_lat, t_lon, row['latitude'], row['longitude']) <= 2.0]
                if nearby_acc:
                    st.error(f"⚠️ {len(nearby_acc)} recorded accident(s) within 2km of this location!")
                    st.dataframe(pd.DataFrame(nearby_acc).sort_values('distance_km')[['distance_km','location','cause','deaths','injured','date']], use_container_width=True, hide_index=True)
                else:
                    st.success("✅ No recorded accidents within 2km of this location.")
        else:
            st.error("❌ No traffic data for this location. TomTom may not cover this road. Try clicking on a major highway.")

# ================================================================
# TAB 3 — PROXIMITY ALERT
# ================================================================
with tab3:
    st.subheader("📍 Are you near an accident hotspot?")

    if user_lat != 0.0:
        st.success(f"✅ Your GPS location: {user_lat}, {user_lon}")
        my_lat = user_lat
        my_lon = user_lon
    else:
        st.warning("⚠️ GPS not detected. Use the 📍 GPS button at the top of the page.")
        my_lat = 13.0963
        my_lon = 80.2343

    c1, c2, c3 = st.columns(3)
    with c1:
        my_lat = st.number_input("Your Latitude", value=my_lat, format="%.6f", key="prox_lat")
    with c2:
        my_lon = st.number_input("Your Longitude", value=my_lon, format="%.6f", key="prox_lon")
    with c3:
        radius = st.slider("Alert radius (km)", 1.0, 30.0, 5.0, 0.5)

    if not df.empty:
        nearby = []
        for _, row in df.iterrows():
            d = haversine(my_lat, my_lon, row['latitude'], row['longitude'])
            if d <= radius:
                item = row.to_dict()
                item['distance_km'] = round(d, 2)
                nearby.append(item)
        if nearby:
            st.error(f"⚠️ {len(nearby)} accident zone(s) within {radius} km of you!")
            st.dataframe(pd.DataFrame(nearby).sort_values('distance_km')[['distance_km','location','cause','deaths','injured']], use_container_width=True, hide_index=True)
        else:
            st.success(f"✅ No recorded accidents within {radius} km. Stay safe!")
    else:
        st.info("No data loaded yet.")

# ================================================================
# TAB 4 — REPORT ACCIDENT
# ================================================================
with tab4:
    st.subheader("🆘 Report an Accident")
    st.info("Click a spot on the **Live Map** tab first — coordinates auto-fill here. Or use GPS button below.")

    if st.session_state.click_lat != 0.0:
        r_lat = st.session_state.click_lat
        r_lon = st.session_state.click_lon
        st.success(f"📍 From map click: {r_lat}, {r_lon}")
    elif user_lat != 0.0:
        r_lat = user_lat
        r_lon = user_lon
        st.success(f"📍 From your GPS: {r_lat}, {r_lon}")
    else:
        r_lat, r_lon = 0.0, 0.0
        st.warning("⚠️ No coordinates yet. Click on the map or use GPS button at the top of page.")

    with st.form("report_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            r_location = st.text_input("Location Name *", placeholder="e.g. NH48, Sriperumbudur")
            r_deaths = st.number_input("Deaths", min_value=0, value=0)
            r_cause = st.selectbox("Cause *", [
                "Overspeeding", "Drunk driving", "Vehicle collision", "Hit and run",
                "Pothole / Road condition", "Tyre burst", "Signal jumping",
                "Pedestrian accident", "Animal on road", "Other"
            ])
        with col2:
            r_lat_input = st.number_input("Latitude *", value=r_lat, format="%.6f")
            r_lon_input = st.number_input("Longitude *", value=r_lon, format="%.6f")
            r_injured = st.number_input("Injured", min_value=0, value=0)
            r_vehicle = st.text_input("Vehicle Types", placeholder="e.g. Truck, Car")

        r_url = st.text_input("News Link (optional)", placeholder="https://...")
        submitted = st.form_submit_button("🚨 SUBMIT REPORT", use_container_width=True, type="primary")

        if submitted:
            if not r_location or (r_lat_input == 0.0 and r_lon_input == 0.0):
                st.error("Please fill location name and coordinates.")
            else:
                now = datetime.now()
                record = {
                    "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%I:%M %p"),
                    "location": r_location, "latitude": r_lat_input, "longitude": r_lon_input,
                    "deaths": int(r_deaths), "injured": int(r_injured),
                    "cause": r_cause, "vehicle": r_vehicle, "url": r_url
                }
                try:
                    db = get_db()
                    db[COL_ACCIDENTS].insert_one(record)
                    st.cache_data.clear()
                    st.session_state.click_lat = 0.0
                    st.session_state.click_lon = 0.0
                    st.success("✅ Report submitted! Go to Live Map tab to see it.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Submission failed: {e}")

# --- FULL TABLE ---
st.markdown("---")
st.subheader("📋 All Accident Records")
if not df.empty:
    st.dataframe(df[['date','time','location','deaths','injured','cause','vehicle']], use_container_width=True, hide_index=True)
