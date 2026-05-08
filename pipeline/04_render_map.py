"""
04_render_map.py
Render the unified Southern Mongolia mining map.

Layers (LayerControl-toggleable):
  1. GEM coal mines (423 named)         — sized colored circles, top z-order
  2. Tang centroids (~5,000 satellite)  — clustered blue dots
  3. Tang polygons (zoom ≥ 9 only)      — translucent gray fills

Mergen marker (May 10, 2011 site) is added directly to the map and lives
in its own pane above all other layers; it cannot be turned off.

Output: southern_mongolia_mining.html (project root).
"""
import json
from pathlib import Path

import folium
import numpy as np
from folium.map import CustomPane
from folium.plugins import FastMarkerCluster

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "data/final"
OUT = ROOT / "southern_mongolia_mining.html"

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
INITIAL_CENTER = [43.5, 113.0]
INITIAL_ZOOM = 5

GEM_R_MIN, GEM_R_MAX = 3.0, 25.0     # capacity → radius
TANG_R_MIN, TANG_R_MAX = 3.0, 13.0   # area → radius (smaller than GEM)
TANG_AREA_CAP_PCT = 95               # cap on the radius mapping
TANG_POLY_MIN_ZOOM = 9
TANG_COLOR = "#1f3a8a"               # deep blue


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_geojson(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


gem_fc = load_geojson(FINAL / "gem_sm_mines.geojson")
tang_poly_fc = load_geojson(FINAL / "tang_sm_polygons.geojson")
tang_cent_fc = load_geojson(FINAL / "tang_sm_centroids.geojson")
with open(FINAL / "summary.json", "r", encoding="utf-8") as f:
    summary = json.load(f)

gem_features = gem_fc["features"]
tang_centroids = tang_cent_fc["features"]


# ---------------------------------------------------------------------------
# GEM helpers
# ---------------------------------------------------------------------------
caps = [float(f["properties"]["capacity_mtpa"]) for f in gem_features]
GEM_CAP_MIN = min(caps)
GEM_CAP_MAX = max(caps)


def gem_radius(cap):
    if GEM_CAP_MAX == GEM_CAP_MIN:
        return (GEM_R_MIN + GEM_R_MAX) / 2
    norm = (cap - GEM_CAP_MIN) / (GEM_CAP_MAX - GEM_CAP_MIN)
    return GEM_R_MIN + norm * (GEM_R_MAX - GEM_R_MIN)


def gem_color(status):
    s = (status or "").lower()
    if "operating" in s:
        return "#d62728"
    if "construction" in s:
        return "#f1c40f"
    if "proposed" in s:
        return "#ff8c00"
    return "#7f7f7f"


# Tang centroid radius scaling (linear, capped at 95th percentile)
tang_areas = np.array([float(f["properties"]["area_km2"])
                       for f in tang_centroids])
TANG_AREA_MIN = float(tang_areas.min())
TANG_AREA_CAP = float(np.percentile(tang_areas, TANG_AREA_CAP_PCT))


# ---------------------------------------------------------------------------
# Build map
# ---------------------------------------------------------------------------
m = folium.Map(location=INITIAL_CENTER, zoom_start=INITIAL_ZOOM,
               tiles="OpenStreetMap", control_scale=True)
map_var = m.get_name()

# Custom Leaflet panes for explicit z-order:
#   tilePane(200) < tangPolyPane(380) < overlayPane(400) < markerPane(600)
#   < gemPane(650) < mergenPane(700)
# CustomPane registers itself as a child of the map, so its createPane
# call is emitted after the map variable is defined.
CustomPane("tangPolyPane", z_index=380, pointer_events=True).add_to(m)
CustomPane("gemPane", z_index=650, pointer_events=True).add_to(m)
CustomPane("mergenPane", z_index=700, pointer_events=True).add_to(m)

# ---------------------------------------------------------------------------
# Layer 1 (bottom): Tang polygons
# ---------------------------------------------------------------------------
def poly_style(_feat):
    return {"fillColor": "#666", "color": "#444", "weight": 0.4,
            "fillOpacity": 0.30, "opacity": 0.5}


tang_poly_layer = folium.GeoJson(
    tang_poly_fc,
    name=f"Tang polygons ({summary['tang_polygon_count']:,}; visible at "
         f"zoom ≥ {TANG_POLY_MIN_ZOOM})",
    style_function=poly_style,
    pane="tangPolyPane",
    popup=folium.GeoJsonPopup(
        fields=["tang_id", "area_km2"],
        aliases=["Tang polygon ID", "Area (km²)"],
        labels=True,
    ),
)
tang_poly_layer.add_to(m)

# ---------------------------------------------------------------------------
# Layer 2 (middle): Tang centroids — FastMarkerCluster
# ---------------------------------------------------------------------------
# Each row: [lat, lon, area_km2, tang_id]
tang_data = [
    [
        f["geometry"]["coordinates"][1],
        f["geometry"]["coordinates"][0],
        float(f["properties"]["area_km2"]),
        int(f["properties"]["tang_id"]),
    ]
    for f in tang_centroids
]

callback = (
    "(function(row) {"
    "  var lat = row[0], lon = row[1], area = row[2], tid = row[3];"
    f"  var capArea = {TANG_AREA_CAP};"
    f"  var minArea = {TANG_AREA_MIN};"
    f"  var rMin = {TANG_R_MIN}, rMax = {TANG_R_MAX};"
    "  var span = capArea - minArea;"
    "  var aClip = Math.min(area, capArea);"
    "  var r = (span <= 0) ? (rMin+rMax)/2 :"
    "    rMin + ((aClip - minArea) / span) * (rMax - rMin);"
    "  var d = Math.max(4, Math.round(r * 2));"
    "  var icon = L.divIcon({"
    "    html: '<div style=\"width:'+d+'px;height:'+d+'px;background:"
    f"{TANG_COLOR}"
    ";border-radius:50%;opacity:0.55;border:1px solid #ffffffaa;\"></div>',"
    "    className: 'tang-marker',"
    "    iconSize: [d, d]"
    "  });"
    "  var marker = L.marker(new L.LatLng(lat, lon), {icon: icon});"
    "  marker.bindPopup("
    "    '<b>Tang &amp; Werner 2023 polygon #' + tid + '</b><br>'"
    "    + 'Mining area identified by satellite imagery '"
    "    + '(Tang &amp; Werner 2023). Mine type and ownership not '"
    "    + 'classified in source data.<br>'"
    "    + '<b>Approximate area:</b> ' + area.toFixed(3) + ' km²'"
    "  );"
    "  return marker;"
    "})"
)

cluster_icon_func = (
    "function(cluster) {"
    "  var n = cluster.getChildCount();"
    "  var size = n < 10 ? 30 : n < 100 ? 36 : n < 1000 ? 44 : 52;"
    "  return L.divIcon({"
    "    html: '<div style=\"background:" + TANG_COLOR +
    ";color:#fff;border-radius:50%;width:'+size+'px;height:'+size+"
    "'px;line-height:'+size+'px;text-align:center;font-weight:600;"
    "border:2px solid #fff;opacity:0.85;font-size:12px;font-family:"
    "-apple-system,BlinkMacSystemFont,sans-serif;\">' + n + '</div>',"
    "    className: 'tang-cluster',"
    "    iconSize: [size, size]"
    "  });"
    "}"
)

tang_cluster = FastMarkerCluster(
    data=tang_data,
    callback=callback,
    name=f"Tang centroids ({summary['tang_centroid_count']:,} satellite "
         f"points)",
    icon_create_function=cluster_icon_func,
    options={
        "showCoverageOnHover": False,
        "spiderfyOnMaxZoom": True,
        "maxClusterRadius": 50,
    },
)
tang_cluster.add_to(m)

# ---------------------------------------------------------------------------
# Layer 3 (top of data layers): GEM mines
# ---------------------------------------------------------------------------
gem_group = folium.FeatureGroup(
    name=f"GEM coal mines ({summary['gem_count']} named)", show=True
)
for feat in gem_features:
    p = feat["properties"]
    cap = float(p["capacity_mtpa"])
    coords = feat["geometry"]["coordinates"]  # [lon, lat]

    parts = [f"<b>{p['mine_name']}</b>"]
    if p.get("mine_name_zh"):
        parts.append(f"<i>{p['mine_name_zh']}</i>")
    parts.append(f"<b>Owners:</b> {p['owners']}")
    if p.get("parent_company"):
        parts.append(f"<b>Parent company:</b> {p['parent_company']}")
    parts.append(f"<b>Capacity:</b> {cap:g} Mtpa")
    parts.append(f"<b>Status:</b> {p['status']}")
    if p.get("mine_type"):
        parts.append(f"<b>Mine type:</b> {p['mine_type']}")
    parts.append(f"<b>Prefecture:</b> {p['prefecture']}")
    if p["merged_count"] > 1:
        parts.append(
            f"<i>Multi-phase project: details merged from "
            f"{p['merged_count']} GEM records</i>"
        )
    popup = folium.Popup("<br>".join(parts), max_width=360)
    color = gem_color(p["status"])

    folium.CircleMarker(
        location=[coords[1], coords[0]],
        radius=gem_radius(cap),
        color=color, weight=1.0, fill=True, fill_color=color,
        fill_opacity=0.7, opacity=0.7,
        popup=popup,
        pane="gemPane",
    ).add_to(gem_group)
gem_group.add_to(m)

# ---------------------------------------------------------------------------
# Mergen marker — never toggleable, always on top
# ---------------------------------------------------------------------------
mergen_popup = folium.Popup(
    "<b>Mergen / 莫日根</b><br>"
    "Killed May 10, 2011 by a coal hauler in West Ujimqin Banner.<br>"
    "Exact site not publicly documented.",
    max_width=320,
)
folium.Marker(
    location=[44.5, 118.0],
    popup=mergen_popup,
    icon=folium.Icon(color="black", icon="info-sign"),
    pane="mergenPane",
).add_to(m)

# ---------------------------------------------------------------------------
# Layer control
# ---------------------------------------------------------------------------
folium.LayerControl(collapsed=False, position="topright").add_to(m)

# ---------------------------------------------------------------------------
# Title, info panel, prefecture dropdown, footnote
# ---------------------------------------------------------------------------
prefectures = summary["prefectures"]
options_html = "\n".join(
    f'<option value="{p["name"]}">{p["name"]} ({p["count"]})</option>'
    for p in prefectures
)
pref_bounds_js = json.dumps({
    p["name"]: {
        "south": p["south"], "north": p["north"],
        "west": p["west"], "east": p["east"],
    }
    for p in prefectures
})

title_html = f"""
<div id="sm-title" style="position: fixed; top: 12px; left: 50%;
    transform: translateX(-50%); z-index: 1000;
    background: rgba(255,255,255,0.94); padding: 10px 18px;
    border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,.15);
    max-width: 78vw;">
  <div style="font-size: 18px; font-weight: 600;">
    Mining Across Southern Mongolia / 南蒙古矿业图谱
  </div>
  <div style="font-size: 12px; color: #444; margin-top: 5px;
       line-height: 1.45;">
    {summary['gem_count']} named coal mines (Global Energy Monitor,
    May 2025)<br>
    {summary['tang_polygon_count']:,} mining areas identified by satellite
    (Tang &amp; Werner 2023, all mineral types)<br>
    Total disturbed area: ~{summary['tang_total_area_km2']:,.0f} km²
  </div>
</div>
"""

info_html = f"""
<div id="sm-info" style="position: fixed; top: 12px; left: 12px;
    z-index: 1000; background: rgba(255,255,255,0.94);
    padding: 10px 12px; border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 11px; color: #333; max-width: 280px; line-height: 1.45;
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div><b>Sources:</b><br>
    • Global Energy Monitor — Global Coal Mine Tracker, May 2025 V2.<br>
    • Tang &amp; Werner (2023), <i>Communications Earth &amp; Environment</i>
    4(134), doi:10.5281/zenodo.7894216.
  </div>
  <div style="margin-top: 5px;"><b>Note:</b> "Southern Mongolia" is the
    standard name for this region in international human-rights contexts.
  </div>
  <div style="margin-top: 7px; padding-top: 5px; border-top: 1px solid #ddd;
       font-size: 10.5px; line-height: 1.4;">
    <b>GEM</b>
    <span style="color:#d62728;">●</span> Operating
    <span style="color:#ff8c00;">●</span> Proposed
    <span style="color:#f1c40f;">●</span> Construction
    <span style="color:#7f7f7f;">●</span> Other<br>
    <b>Tang</b>
    <span style="color:{TANG_COLOR};">●</span> satellite-identified
    surface mining footprint<br>
    Polygon outlines: visible at zoom ≥ {TANG_POLY_MIN_ZOOM}.
  </div>
</div>
"""

pref_panel_html = f"""
<div id="sm-pref-panel" style="position: fixed; top: 240px; right: 12px;
    z-index: 1000; background: rgba(255,255,255,0.94);
    padding: 10px 12px; border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px; width: 220px;
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div style="font-weight: 600; margin-bottom: 6px;">
    Jump to prefecture / 跳转盟市
  </div>
  <select id="sm-pref-select" style="width: 100%; padding: 5px;
      font-size: 12px; box-sizing: border-box;">
    <option value="">— select / 选择 —</option>
    {options_html}
  </select>
  <button id="sm-pref-reset" style="margin-top: 6px; width: 100%;
      padding: 5px; font-size: 12px; cursor: pointer;
      background: #f0f0f0; border: 1px solid #aaa; border-radius: 3px;">
    Reset view / 重置
  </button>
  <div style="font-size: 10px; color: #777; margin-top: 6px;">
    {len(prefectures)} prefectures · sorted by mine count
  </div>
</div>
"""

footer_html = """
<div id="sm-footer" style="position: fixed; bottom: 8px; left: 12px;
    right: 12px; z-index: 999; background: rgba(255,255,255,0.92);
    padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 10.5px; color: #555; line-height: 1.4; text-align: center;
    box-shadow: 0 -1px 4px rgba(0,0,0,.08);">
  Tang &amp; Werner 2023 includes coal, metal, rare earth, and other
  surface mining. GEM May 2025 V2 covers coal mines only with 1 Mtpa+
  capacity. The two datasets together span Southern Mongolia's named
  mining industry and its full satellite-visible footprint.
</div>
"""

m.get_root().html.add_child(folium.Element(
    title_html + info_html + pref_panel_html + footer_html
))

# Zoom toggle for polygon layer + dropdown handlers
panel_js = f"""
<script>
(function() {{
    var prefBounds = {pref_bounds_js};
    var initialCenter = {json.dumps(INITIAL_CENTER)};
    var initialZoom = {INITIAL_ZOOM};
    var POLY_MIN_ZOOM = {TANG_POLY_MIN_ZOOM};

    function ready() {{
        var sel = document.getElementById('sm-pref-select');
        var reset = document.getElementById('sm-pref-reset');
        if (!sel || !reset || typeof {map_var} === 'undefined') {{
            setTimeout(ready, 60);
            return;
        }}

        function updatePolyVisibility() {{
            var z = {map_var}.getZoom();
            var pane = {map_var}.getPane('tangPolyPane');
            if (!pane) return;
            var visible = z >= POLY_MIN_ZOOM;
            pane.style.opacity = visible ? 1 : 0;
            pane.style.pointerEvents = visible ? 'auto' : 'none';
        }}
        {map_var}.on('zoomend', updatePolyVisibility);
        updatePolyVisibility();

        sel.addEventListener('change', function(e) {{
            var v = e.target.value;
            if (!v) return;
            var b = prefBounds[v];
            if (!b) return;
            if (b.south === b.north && b.west === b.east) {{
                {map_var}.flyTo([b.south, b.west], 10, {{duration: 1.0}});
            }} else {{
                var bounds = L.latLngBounds(
                    L.latLng(b.south, b.west),
                    L.latLng(b.north, b.east)
                );
                {map_var}.flyToBounds(bounds, {{
                    padding: [50, 50], maxZoom: 10, duration: 1.0
                }});
            }}
        }});
        reset.addEventListener('click', function() {{
            sel.value = '';
            {map_var}.flyTo(initialCenter, initialZoom,
                {{duration: 1.0}});
        }});
    }}
    ready();
}})();
</script>
"""
m.get_root().html.add_child(folium.Element(panel_js))

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
m.save(str(OUT))
size_mb = OUT.stat().st_size / 1024 / 1024
print(f"Saved: {OUT.relative_to(ROOT)}  ({size_mb:.1f} MB)")
print(f"  GEM mines    : {summary['gem_count']}")
print(f"  Tang centroids: {summary['tang_centroid_count']:,}")
print(f"  Tang polygons: {summary['tang_polygon_count']:,}")
print(f"  Total disturbed area: {summary['tang_total_area_km2']:,.0f} km²")
