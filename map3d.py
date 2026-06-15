"""
3D India Accident Map
----------------------
Builds a self-contained deck.gl HTML widget that:

  - Shows India as a 3D extruded choropleth, bar height/color = total
    accidents per state, from one of two sources:
      * "News Reports"  -> News_Crashes dataset (2021-22), filterable by
                            month and crash type; bars recompute live.
      * "Official Stats" -> MoRTH state-wise accident totals, 2019-2023,
                            selectable by year.

  - In "News Reports" mode, zooming in past a threshold fades the state
    columns out and fades in individual accident reports as clickable
    points with full details in a tooltip. "Official Stats" mode has no
    point-level data, so columns stay at full opacity and points are
    hidden.
"""

import json

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

_HTML_TEMPLATE = r"""
<div id="map-root" style="position:relative;width:100%;height:__HEIGHT__px;border-radius:12px;overflow:hidden;background:#0b1020;font-family:'Segoe UI',Arial,sans-serif;">
  <div id="deck-container" style="position:absolute;inset:0;"></div>

  <div id="title-card" style="position:absolute;top:14px;left:14px;max-width:300px;background:rgba(15,18,32,0.78);backdrop-filter:blur(6px);color:#f5f5f5;padding:12px 16px;border-radius:10px;border:1px solid rgba(255,255,255,0.08);box-shadow:0 4px 18px rgba(0,0,0,0.35);z-index:5;">
    <div style="font-size:15px;font-weight:700;letter-spacing:.3px;">🇮🇳 India Accident Hotspots</div>
    <div style="font-size:11.5px;color:#c9ccd6;margin-top:4px;line-height:1.5;">
      Bar height &amp; color = total accidents per state.<br>
      Drag to rotate &middot; scroll to zoom.<br>
      <span id="mode-hint"><b style="color:#ffb454;">Zoom in</b> on a state to reveal individual accident reports.</span>
    </div>
    <div id="zoom-readout" style="margin-top:6px;font-size:11px;color:#7fd1ff;"></div>
  </div>

  <div id="controls-card" style="position:absolute;top:138px;left:14px;max-width:300px;background:rgba(15,18,32,0.78);backdrop-filter:blur(6px);color:#f5f5f5;padding:12px 16px;border-radius:10px;border:1px solid rgba(255,255,255,0.08);box-shadow:0 4px 18px rgba(0,0,0,0.35);z-index:5;font-size:12px;">
    <div style="font-weight:600;margin-bottom:6px;">Data source</div>
    <select id="source-select" style="width:100%;background:#1b2335;color:#f5f5f5;border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:5px 6px;margin-bottom:8px;">
      <option value="news">News Reports (2021-22)</option>
      <option value="official">Official Stats (MoRTH 2019-2023)</option>
    </select>

    <div id="year-control" style="display:none;margin-bottom:8px;">
      <div style="font-weight:600;margin-bottom:4px;">Year</div>
      <select id="year-select" style="width:100%;background:#1b2335;color:#f5f5f5;border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:5px 6px;">
        __YEAR_OPTIONS__
      </select>
    </div>

    <div id="news-filters">
      <div style="font-weight:600;margin-bottom:4px;">Month</div>
      <select id="month-select" style="width:100%;background:#1b2335;color:#f5f5f5;border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:5px 6px;margin-bottom:8px;">
        <option value="All">All months</option>
        __MONTH_OPTIONS__
      </select>
      <div style="font-weight:600;margin-bottom:4px;">Crash type</div>
      <select id="crashtype-select" style="width:100%;background:#1b2335;color:#f5f5f5;border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:5px 6px;">
        <option value="All">All types</option>
        __CRASHTYPE_OPTIONS__
      </select>
    </div>
  </div>

  <div id="legend-card" style="position:absolute;bottom:14px;left:14px;background:rgba(15,18,32,0.78);backdrop-filter:blur(6px);color:#f5f5f5;padding:10px 14px;border-radius:10px;border:1px solid rgba(255,255,255,0.08);z-index:5;font-size:11.5px;">
    <div id="legend-title" style="font-weight:600;margin-bottom:6px;">Accidents per state</div>
    <div style="width:160px;height:10px;border-radius:5px;background:linear-gradient(90deg,#3a4a6b,#ffd166,#ef476f);"></div>
    <div style="display:flex;justify-content:space-between;margin-top:3px;color:#aab0bf;">
      <span>0</span><span id="legend-max">-</span>
    </div>
    <div id="legend-points" style="margin-top:8px;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="width:10px;height:10px;border-radius:50%;background:#ff9f1c;display:inline-block;"></span>
        <span>Accident report</span>
      </div>
      <div style="margin-top:4px;display:flex;align-items:center;gap:6px;">
        <span style="width:10px;height:10px;border-radius:50%;background:#e63946;display:inline-block;"></span>
        <span>Fatal accident report</span>
      </div>
    </div>
  </div>

  <div id="info-card" style="position:absolute;top:14px;right:14px;max-width:300px;min-width:200px;background:rgba(15,18,32,0.85);backdrop-filter:blur(6px);color:#f5f5f5;padding:0;border-radius:10px;border:1px solid rgba(255,255,255,0.08);box-shadow:0 4px 18px rgba(0,0,0,0.35);z-index:5;display:none;">
  </div>

  <button id="reset-btn" style="position:absolute;bottom:14px;right:14px;z-index:5;background:#1b2335;color:#f5f5f5;border:1px solid rgba(255,255,255,0.15);padding:8px 14px;border-radius:8px;font-size:12px;cursor:pointer;">
    ⟲ Reset view
  </button>

  <div style="position:absolute;bottom:4px;left:50%;transform:translateX(-50%);font-size:9px;color:#6b7280;z-index:4;white-space:nowrap;">
    Map tiles &copy; <a href="https://carto.com/attributions" style="color:#8b94a8;" target="_blank">CARTO</a>, &copy; <a href="https://www.openstreetmap.org/copyright" style="color:#8b94a8;" target="_blank">OpenStreetMap</a> contributors
  </div>
</div>

<script src="https://unpkg.com/deck.gl@8.9.35/dist.min.js"></script>
<script>
(function() {
  const POINTS = __POINTS_DATA__;
  const STATES_GEOJSON = __GEOJSON_DATA__;
  const OFFICIAL_DATA = __OFFICIAL_DATA__;     // {year: {state: {accidents, ranking}}}
  const LATEST_YEAR = __LATEST_YEAR__;

  const ZOOM_THRESHOLD = 6.0;     // zoom level where points take over from columns
  const FADE_RANGE = 1.2;         // smoothness of the crossfade

  const INITIAL_VIEW_STATE = {
    longitude: 80.5,
    latitude: 22.5,
    zoom: 4.3,
    pitch: 45,
    bearing: -10,
    minZoom: 3,
    maxZoom: 12
  };

  const FILTERS = {
    source: 'news',     // 'news' | 'official'
    year: LATEST_YEAR,
    month: 'All',
    crashType: 'All'
  };

  // ---------- helpers ----------
  function clamp01(x) { return Math.max(0, Math.min(1, x)); }

  function colorForCount(count, maxCount) {
    const t = clamp01(count / (maxCount || 1));
    const stops = [
      [58, 74, 107],
      [255, 209, 102],
      [239, 71, 111]
    ];
    let a, b, f;
    if (t < 0.5) { a = stops[0]; b = stops[1]; f = t / 0.5; }
    else { a = stops[1]; b = stops[2]; f = (t - 0.5) / 0.5; }
    return [
      Math.round(a[0] + (b[0]-a[0])*f),
      Math.round(a[1] + (b[1]-a[1])*f),
      Math.round(a[2] + (b[2]-a[2])*f),
      230
    ];
  }

  function elevationForCount(count, maxCount) {
    // scale so the tallest bar is always ~280km regardless of source/filters
    const TARGET_MAX_M = 280000;
    if (!maxCount) return 0;
    return (count / maxCount) * TARGET_MAX_M;
  }

  function getFilteredPoints() {
    return POINTS.filter(p =>
      (FILTERS.month === 'All' || p.month === FILTERS.month) &&
      (FILTERS.crashType === 'All' || p.crash_type === FILTERS.crashType)
    );
  }

  function aggregateFromPoints(points) {
    const agg = {};
    for (const p of points) {
      if (!agg[p.state]) agg[p.state] = {accidents: 0, killed: 0, injured: 0};
      agg[p.state].accidents += 1;
      agg[p.state].killed += p.killed;
      agg[p.state].injured += p.injured;
    }
    return agg;
  }

  function getCurrentStateData() {
    if (FILTERS.source === 'official') {
      const yearData = OFFICIAL_DATA[String(FILTERS.year)] || {};
      const out = {};
      for (const name in yearData) {
        out[name] = {
          accidents: yearData[name].accidents,
          killed: null,
          injured: null,
          ranking: yearData[name].ranking
        };
      }
      return out;
    }
    return aggregateFromPoints(getFilteredPoints());
  }

  // ---------- layers ----------
  let currentStateData = {};
  let currentMaxCount = 1;

  function buildLayers(zoom) {
    const isNews = FILTERS.source === 'news';
    const colFade = isNews ? clamp01((ZOOM_THRESHOLD - zoom) / FADE_RANGE + 0.5) : 1;
    const pointFade = isNews ? clamp01((zoom - ZOOM_THRESHOLD) / FADE_RANGE + 0.5) : 0;

    const tileLayer = new deck.TileLayer({
      id: 'basemap',
      data: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
      minZoom: 0,
      maxZoom: 19,
      tileSize: 256,
      renderSubLayers: props => {
        const {bbox: {west, south, east, north}} = props.tile;
        return new deck.BitmapLayer(props, {
          data: null,
          image: props.data,
          bounds: [west, south, east, north]
        });
      }
    });

    const stateLayer = new deck.GeoJsonLayer({
      id: 'states',
      data: STATES_GEOJSON,
      extruded: true,
      wireframe: true,
      filled: true,
      stroked: true,
      pickable: colFade > 0.05,
      autoHighlight: true,
      highlightColor: [255,255,255,60],
      opacity: colFade,
      getElevation: f => {
        const d = currentStateData[f.properties.st_nm];
        return d ? elevationForCount(d.accidents, currentMaxCount) : 0;
      },
      getFillColor: f => {
        const d = currentStateData[f.properties.st_nm];
        return d ? colorForCount(d.accidents, currentMaxCount) : [60,65,80,120];
      },
      getLineColor: [255,255,255,90],
      lineWidthMinPixels: 1,
      updateTriggers: {
        getElevation: [FILTERS.source, FILTERS.year, FILTERS.month, FILTERS.crashType],
        getFillColor: [FILTERS.source, FILTERS.year, FILTERS.month, FILTERS.crashType]
      }
    });

    const pointData = isNews ? getFilteredPoints() : [];
    const pointLayer = new deck.ScatterplotLayer({
      id: 'points',
      data: pointData,
      pickable: pointFade > 0.05,
      opacity: pointFade,
      visible: isNews && pointFade > 0.01,
      radiusUnits: 'meters',
      radiusMinPixels: 3,
      radiusMaxPixels: 22,
      getPosition: d => [d.lon, d.lat],
      getRadius: d => 1800 + d.killed * 1800,
      getFillColor: d => d.killed > 0 ? [230,57,70,220] : [255,159,28,210],
      getLineColor: [20,20,20,160],
      lineWidthMinPixels: 1,
      stroked: true,
      updateTriggers: {
        data: [FILTERS.month, FILTERS.crashType]
      }
    });

    return [tileLayer, stateLayer, pointLayer];
  }

  let viewState = {...INITIAL_VIEW_STATE};

  const infoCard = document.getElementById('info-card');
  const zoomReadout = document.getElementById('zoom-readout');
  const modeHint = document.getElementById('mode-hint');
  const legendTitle = document.getElementById('legend-title');
  const legendMax = document.getElementById('legend-max');
  const legendPoints = document.getElementById('legend-points');

  function updateZoomReadout(zoom) {
    if (FILTERS.source === 'official') {
      zoomReadout.textContent = `Official MoRTH stats — ${FILTERS.year}`;
      return;
    }
    if (zoom < ZOOM_THRESHOLD - FADE_RANGE/2) {
      zoomReadout.textContent = 'State view — zoom in to see individual reports';
    } else if (zoom > ZOOM_THRESHOLD + FADE_RANGE/2) {
      zoomReadout.textContent = 'Report view — showing individual accidents';
    } else {
      zoomReadout.textContent = 'Transitioning…';
    }
  }

  function updateChrome() {
    const isNews = FILTERS.source === 'news';
    modeHint.style.display = isNews ? 'inline' : 'none';
    legendPoints.style.display = isNews ? 'block' : 'none';
    if (isNews) {
      let label = 'Accidents per state (News Reports';
      if (FILTERS.month !== 'All') label += `, ${FILTERS.month}`;
      if (FILTERS.crashType !== 'All') label += `, ${FILTERS.crashType}`;
      legendTitle.textContent = label + ')';
    } else {
      legendTitle.textContent = `Accidents per state (Official ${FILTERS.year})`;
    }
    legendMax.textContent = currentMaxCount.toLocaleString();
    updateZoomReadout(viewState.zoom);
  }

  function updateView() {
    currentStateData = getCurrentStateData();
    const counts = Object.values(currentStateData).map(d => d.accidents);
    currentMaxCount = counts.length ? Math.max(...counts, 1) : 1;
    deckgl.setProps({layers: buildLayers(viewState.zoom)});
    updateChrome();
  }

  // ---------- deck.gl instance ----------
  currentStateData = getCurrentStateData();
  {
    const counts = Object.values(currentStateData).map(d => d.accidents);
    currentMaxCount = counts.length ? Math.max(...counts, 1) : 1;
  }

  const deckgl = new deck.DeckGL({
    container: 'deck-container',
    viewState: viewState,
    controller: true,
    layers: buildLayers(viewState.zoom),
    getTooltip: ({object, layer}) => {
      if (!object || !layer) return null;
      if (layer.id === 'states') {
        const name = object.properties.st_nm;
        const d = currentStateData[name];
        if (!d) return {html: `<b>${name}</b><br/>No data`};
        if (d.killed === null) {
          return {
            html: `<b>${name}</b><br/>Accidents (${FILTERS.year}): <b>${d.accidents.toLocaleString()}</b>${d.ranking ? `<br/>National rank: #${d.ranking}` : ''}`,
            style: {backgroundColor:'#1b2335', color:'#f5f5f5', fontSize:'12px', borderRadius:'6px'}
          };
        }
        return {
          html: `<b>${name}</b><br/>Accidents: <b>${d.accidents}</b><br/>Killed: ${d.killed} &nbsp; Injured: ${d.injured}`,
          style: {backgroundColor:'#1b2335', color:'#f5f5f5', fontSize:'12px', borderRadius:'6px'}
        };
      }
      if (layer.id === 'points') {
        return {
          html: `<b>${object.location}</b>, ${object.state}<br/>${object.crash_date} (${object.crash_day})<br/>${object.crash_type}<br/>Vehicles: ${object.vehicle1}${object.vehicle2 ? ' &amp; ' + object.vehicle2 : ''}<br/>Killed: <b>${object.killed}</b> &nbsp; Injured: ${object.injured}<br/>Road: ${object.road_type}`,
          style: {backgroundColor:'#1b2335', color:'#f5f5f5', fontSize:'12px', borderRadius:'6px', maxWidth:'240px'}
        };
      }
      return null;
    },
    onViewStateChange: ({viewState: vs}) => {
      viewState = vs;
      deckgl.setProps({viewState, layers: buildLayers(vs.zoom)});
      updateZoomReadout(vs.zoom);
    },
    onClick: ({object, layer}) => {
      if (!object || !layer) {
        infoCard.style.display = 'none';
        return;
      }
      let html = '';
      if (layer.id === 'states') {
        const name = object.properties.st_nm;
        const d = currentStateData[name];
        if (d && d.killed === null) {
          html = `
            <div style="padding:14px 16px;">
              <div style="font-size:14px;font-weight:700;margin-bottom:6px;">${name}</div>
              <div style="font-size:12px;line-height:1.6;color:#dfe2eb;">
                Accidents (${FILTERS.year}): <b style="color:#ffd166;">${d.accidents.toLocaleString()}</b><br/>
                ${d.ranking ? `National rank: <b>#${d.ranking}</b>` : ''}
              </div>
            </div>`;
        } else {
          html = `
            <div style="padding:14px 16px;">
              <div style="font-size:14px;font-weight:700;margin-bottom:6px;">${name}</div>
              ${d ? `
                <div style="font-size:12px;line-height:1.6;color:#dfe2eb;">
                  Total accidents: <b style="color:#ffd166;">${d.accidents}</b><br/>
                  Killed: <b style="color:#ef476f;">${d.killed}</b><br/>
                  Injured: <b>${d.injured}</b>
                </div>` : `<div style="font-size:12px;color:#aab0bf;">No reports for this filter</div>`}
            </div>`;
        }
      } else if (layer.id === 'points') {
        html = `
          <div style="padding:14px 16px;">
            <div style="font-size:13px;font-weight:700;margin-bottom:4px;">${object.location}, ${object.state}</div>
            <div style="font-size:11.5px;color:#aab0bf;margin-bottom:6px;">${object.crash_date} (${object.crash_day})${object.million_plus_city && object.million_plus_city !== 'Nil' ? ' &middot; ' + object.million_plus_city : ''}</div>
            <div style="font-size:12px;line-height:1.6;color:#dfe2eb;">
              <b>${object.crash_type}</b> on ${object.road_type}<br/>
              Vehicles: ${object.vehicle1}${object.vehicle2 ? ' & ' + object.vehicle2 : ''}<br/>
              Killed: <b style="color:#ef476f;">${object.killed}</b> &nbsp; Injured: <b>${object.injured}</b>
              ${object.gender ? `<br/>Victim: ${object.gender}${object.age ? ', age ' + object.age : ''}` : ''}
            </div>
          </div>`;
      }
      infoCard.innerHTML = html;
      infoCard.style.display = html ? 'block' : 'none';
    }
  });

  updateChrome();

  // ---------- controls ----------
  const sourceSelect = document.getElementById('source-select');
  const yearControl = document.getElementById('year-control');
  const yearSelect = document.getElementById('year-select');
  const newsFilters = document.getElementById('news-filters');
  const monthSelect = document.getElementById('month-select');
  const crashTypeSelect = document.getElementById('crashtype-select');

  sourceSelect.addEventListener('change', () => {
    FILTERS.source = sourceSelect.value;
    const isOfficial = FILTERS.source === 'official';
    yearControl.style.display = isOfficial ? 'block' : 'none';
    newsFilters.style.display = isOfficial ? 'none' : 'block';
    updateView();
  });

  yearSelect.addEventListener('change', () => {
    FILTERS.year = yearSelect.value;
    updateView();
  });

  monthSelect.addEventListener('change', () => {
    FILTERS.month = monthSelect.value;
    updateView();
  });

  crashTypeSelect.addEventListener('change', () => {
    FILTERS.crashType = crashTypeSelect.value;
    updateView();
  });

  document.getElementById('reset-btn').addEventListener('click', () => {
    viewState = {...INITIAL_VIEW_STATE, transitionDuration: 800, transitionInterpolator: new deck.FlyToInterpolator()};
    deckgl.setProps({viewState, layers: buildLayers(INITIAL_VIEW_STATE.zoom)});
    updateZoomReadout(INITIAL_VIEW_STATE.zoom);
    infoCard.style.display = 'none';
  });
})();
</script>
"""


def build_points(points_df, max_points=None):
    """points_df: the cleaned news_crashes dataframe/records"""
    df = points_df
    if max_points and len(df) > max_points:
        df = df.sample(max_points, random_state=42)
    cols = ['lat', 'lon', 'state', 'location', 'million_plus_city',
            'crash_date', 'crash_day', 'month', 'vehicle1', 'vehicle2',
            'killed', 'injured', 'gender', 'age', 'road_type', 'crash_type']
    records = df[cols].fillna('').to_dict(orient='records')
    for r in records:
        r['lat'] = round(float(r['lat']), 5)
        r['lon'] = round(float(r['lon']), 5)
        r['killed'] = int(r['killed'])
        r['injured'] = int(r['injured'])
    return records


def build_official_data(state_stats_records):
    """state_stats_records: list of {state, year, accidents, ranking}"""
    data = {}
    years = set()
    for rec in state_stats_records:
        year = int(rec['year'])
        years.add(year)
        data.setdefault(str(year), {})[rec['state']] = {
            "accidents": int(rec['accidents']),
            "ranking": (int(rec['ranking']) if rec.get('ranking') is not None else None),
        }
    return data, sorted(years)


def render_html(points_df, state_stats_records, geojson_obj, height=640, max_points=None):
    points = build_points(points_df, max_points=max_points)
    official_data, years = build_official_data(state_stats_records)
    latest_year = years[-1] if years else 2023

    crash_types = sorted(set(p['crash_type'] for p in points if p['crash_type']))

    year_options = "".join(
        f'<option value="{y}"{" selected" if y == latest_year else ""}>{y}</option>'
        for y in years
    )
    month_options = "".join(f'<option value="{m}">{m}</option>' for m in MONTHS)
    crashtype_options = "".join(f'<option value="{c}">{c}</option>' for c in crash_types)

    html = _HTML_TEMPLATE
    html = html.replace("__HEIGHT__", str(height))
    html = html.replace("__POINTS_DATA__", json.dumps(points))
    html = html.replace("__GEOJSON_DATA__", json.dumps(geojson_obj))
    html = html.replace("__OFFICIAL_DATA__", json.dumps(official_data))
    html = html.replace("__LATEST_YEAR__", json.dumps(latest_year))
    html = html.replace("__YEAR_OPTIONS__", year_options)
    html = html.replace("__MONTH_OPTIONS__", month_options)
    html = html.replace("__CRASHTYPE_OPTIONS__", crashtype_options)
    return html
