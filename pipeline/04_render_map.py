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

# Timeline slider range. Upper bound is the present year, not the latest
# data point in GEM — mines with an Opening Year past the present are
# planned/proposed and shouldn't be on a historical "mines opened by year"
# timeline. They get folded into the undated set: visible only when the
# slider is at SLIDER_MAX, hidden as soon as the user starts sliding.
SLIDER_MIN = 1912
SLIDER_MAX = 2026
SLIDER_INIT = SLIDER_MAX


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_geojson(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


gem_fc = load_geojson(FINAL / "gem_sm_mines.geojson")
tang_poly_fc = load_geojson(FINAL / "tang_sm_polygons.geojson")
tang_cent_fc = load_geojson(FINAL / "tang_sm_centroids.geojson")
noncoal_fc = load_geojson(FINAL / "noncoal_mines.geojson")
with open(FINAL / "summary.json", "r", encoding="utf-8") as f:
    summary = json.load(f)

gem_features = gem_fc["features"]
tang_centroids = tang_cent_fc["features"]
noncoal_features = noncoal_fc["features"]


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


# Coal Grade → marker shape. None / unrecognized → circle (Thermal fallback).
def gem_shape(grade):
    if grade == "Met":
        return "triangle"
    if grade == "Thermal & Met":
        return "diamond"
    return "circle"


# Build an SVG DivIcon for triangle / diamond markers, sized to inscribe the
# same radius as the equivalent CircleMarker. Triangle apex points up;
# diamond points up/down/left/right (square rotated 45°). When `unknown` is
# true (Opening Year missing), use lower opacity + dashed stroke to match
# the dashed-circle treatment for unknown-year mines.
def gem_svg_icon(shape, r, color, unknown=False):
    import math
    pad = 1.5  # leave room for stroke
    d = 2 * r + 2 * pad
    cx = cy = d / 2
    if shape == "triangle":
        top = (cx, cy - r)
        br = (cx + r * math.cos(math.radians(30)),
              cy + r * math.sin(math.radians(30)))
        bl = (cx - r * math.cos(math.radians(30)),
              cy + r * math.sin(math.radians(30)))
        pts = f"{top[0]:.2f},{top[1]:.2f} {br[0]:.2f},{br[1]:.2f} {bl[0]:.2f},{bl[1]:.2f}"
    elif shape == "diamond":
        pts = (f"{cx:.2f},{cy - r:.2f} {cx + r:.2f},{cy:.2f} "
               f"{cx:.2f},{cy + r:.2f} {cx - r:.2f},{cy:.2f}")
    else:
        raise ValueError(shape)
    fill_op = 0.35 if unknown else 0.7
    stroke_op = 0.55 if unknown else 0.7
    dash_attr = ' stroke-dasharray="3,2"' if unknown else ''
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{d:.2f}" '
        f'height="{d:.2f}" viewBox="0 0 {d:.2f} {d:.2f}" '
        f'style="display:block;overflow:visible;">'
        f'<polygon points="{pts}" fill="{color}" fill-opacity="{fill_op}" '
        f'stroke="{color}" stroke-width="1" stroke-opacity="{stroke_op}"'
        f'{dash_attr} stroke-linejoin="round"/></svg>'
    )
    return folium.DivIcon(
        html=svg,
        icon_size=(d, d),
        icon_anchor=(d / 2, d / 2),
        class_name="gem-shape-marker",
    )


# Non-coal mine helpers — color by primary commodity, pointy-top hexagon
# marker, fixed radius (Tailings is enlarged because it's the most
# health-critical site type in the curated list).
NONCOAL_COLORS = {
    "Rare Earth": "#6a1b9a",
    "Gold": "#ffc107",
    "Silver": "#9e9e9e",
    "Copper": "#689f38",
    "Iron": "#424242",
    "Lead": "#c62828",
    "Zinc": "#c62828",
    "Tungsten": "#006064",
    "Tin": "#ad1457",
    "Lithium": "#ce93d8",
    "Uranium": "#cddc39",
    "Fluorite": "#66bb6a",
    "Tailings": "#b71c1c",
}
NONCOAL_DEFAULT_COLOR = "#b39ddb"
NONCOAL_R = 8.0
NONCOAL_TAILINGS_R = 14.0


def noncoal_color(commodity):
    return NONCOAL_COLORS.get(commodity, NONCOAL_DEFAULT_COLOR)


def noncoal_radius(commodity):
    return NONCOAL_TAILINGS_R if commodity == "Tailings" else NONCOAL_R


def noncoal_hex_icon(r, color, unknown=False):
    import math
    pad = 1.5
    d = 2 * r + 2 * pad
    cx = cy = d / 2
    pts_xy = [
        (cx, cy - r),
        (cx + r * math.cos(math.radians(30)),
         cy - r * math.sin(math.radians(30))),
        (cx + r * math.cos(math.radians(30)),
         cy + r * math.sin(math.radians(30))),
        (cx, cy + r),
        (cx - r * math.cos(math.radians(30)),
         cy + r * math.sin(math.radians(30))),
        (cx - r * math.cos(math.radians(30)),
         cy - r * math.sin(math.radians(30))),
    ]
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts_xy)
    fill_op = 0.4 if unknown else 0.78
    stroke_op = 0.55 if unknown else 0.9
    dash_attr = ' stroke-dasharray="3,2"' if unknown else ''
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{d:.2f}" '
        f'height="{d:.2f}" viewBox="0 0 {d:.2f} {d:.2f}" '
        f'style="display:block;overflow:visible;">'
        f'<polygon points="{pts}" fill="{color}" fill-opacity="{fill_op}" '
        f'stroke="{color}" stroke-width="1.2" stroke-opacity="{stroke_op}"'
        f'{dash_attr} stroke-linejoin="round"/></svg>'
    )
    return folium.DivIcon(
        html=svg,
        icon_size=(d, d),
        icon_anchor=(d / 2, d / 2),
        class_name="noncoal-marker",
    )


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

# No-cache meta tags so opening the file (or hitting a host that serves
# it) always picks up the latest render, not a stale cached copy.
m.get_root().header.add_child(folium.Element(
    '<meta http-equiv="Cache-Control" '
    'content="no-cache, no-store, must-revalidate">\n'
    '<meta http-equiv="Pragma" content="no-cache">\n'
    '<meta http-equiv="Expires" content="0">'
))

# CSS that the slider toggles via a body class. When the timeline is
# active (slider < SLIDER_MAX), Tang centroid markers + cluster icons
# are visually hidden — Tang is 2019 imagery with no temporal axis, so
# showing it on a "mines opened by year" timeline is a category error.
# This is a pure CSS override; the underlying Leaflet layer state stays
# intact, which means the user's LayerControl checkbox preference is
# preserved across slider toggles.
m.get_root().header.add_child(folium.Element(
    "<style>"
    "body.sm-timeline-active .tang-marker, "
    "body.sm-timeline-active .tang-cluster "
    "{ display: none !important; }"
    "</style>"
))

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
# {marker_var_name: opening_year_or_None} — consumed by the timeline slider
# JS to toggle marker visibility. Unknown-year mines (None) are kept on the
# map at all slider positions.
gem_year_map = {}
gem_year_min = None
gem_year_max = None
gem_dated_count = 0
gem_undated_count = 0

for feat in gem_features:
    p = feat["properties"]
    cap = float(p["capacity_mtpa"])
    coords = feat["geometry"]["coordinates"]  # [lon, lat]
    year = p.get("opening_year")
    is_future = year is not None and year > SLIDER_MAX
    # `unknown_year` drives both the visual treatment (dashed translucent
    # style) and the slider visibility logic. Future-year mines look and
    # behave like undated mines.
    unknown_year = (year is None) or is_future
    # `slider_year` is what the slider compares against — None for both
    # undated and future mines so they fall into the always-shown-only-
    # at-max group.
    slider_year = None if unknown_year else year

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
    if year is None:
        parts.append("<b>Opening year:</b> <i>unknown</i>")
    elif is_future:
        parts.append(f"<b>Opening year:</b> {year} (planned)")
    else:
        parts.append(f"<b>Opening year:</b> {year}")
    if p["merged_count"] > 1:
        parts.append(
            f"<i>Multi-phase project: details merged from "
            f"{p['merged_count']} GEM records</i>"
        )
    grade = p.get("coal_grade")
    if grade in ("Thermal", "Met", "Thermal & Met"):
        parts.append(f"<b>Coal grade:</b> {grade}")
    popup = folium.Popup("<br>".join(parts), max_width=360)
    color = gem_color(p["status"])
    r = gem_radius(cap)
    shape = gem_shape(grade)

    if shape == "circle":
        marker = folium.CircleMarker(
            location=[coords[1], coords[0]],
            radius=r,
            color=color, weight=1.0, fill=True, fill_color=color,
            fill_opacity=0.35 if unknown_year else 0.7,
            opacity=0.55 if unknown_year else 0.7,
            dash_array="3,2" if unknown_year else None,
            popup=popup,
            pane="gemPane",
        )
    else:
        marker = folium.Marker(
            location=[coords[1], coords[0]],
            icon=gem_svg_icon(shape, r, color, unknown=unknown_year),
            popup=popup,
            pane="gemPane",
        )
    marker.add_to(gem_group)
    gem_year_map[marker.get_name()] = slider_year
    if slider_year is None:
        gem_undated_count += 1
    else:
        gem_dated_count += 1
        gem_year_min = slider_year if gem_year_min is None else min(
            gem_year_min, slider_year)
        gem_year_max = slider_year if gem_year_max is None else max(
            gem_year_max, slider_year)

gem_group.add_to(m)
gem_group_var = gem_group.get_name()

# ---------------------------------------------------------------------------
# Layer 4: curated non-coal mines (hexagon markers, color by commodity)
# ---------------------------------------------------------------------------
noncoal_group = folium.FeatureGroup(
    name=f"Named non-coal mines ({len(noncoal_features)} curated)",
    show=True,
)
noncoal_year_map = {}

def fmt_secondary(s):
    if not s:
        return None
    return s.replace(";", ", ")


for feat in noncoal_features:
    p = feat["properties"]
    coords = feat["geometry"]["coordinates"]
    commodity = p.get("commodity_primary")
    color = noncoal_color(commodity)
    r = noncoal_radius(commodity)
    year = p.get("opened_year")
    is_future = year is not None and year > SLIDER_MAX
    unknown_year = (year is None) or is_future
    slider_year = None if unknown_year else year

    # Build popup; skip lines whose value is None / empty so unknown
    # fields just disappear.
    parts = [f"<b>{p['name_en']}</b>"]
    if p.get("name_zh"):
        parts.append(f"<i>{p['name_zh']}</i>")
    if commodity:
        parts.append(f"<b>Primary commodity:</b> {commodity}")
    sec = fmt_secondary(p.get("commodity_secondary"))
    if sec:
        parts.append(f"<b>Secondary:</b> {sec}")
    where = ", ".join(x for x in [p.get("banner"), p.get("prefecture")] if x)
    if where:
        parts.append(f"<b>Banner / Prefecture:</b> {where}")
    if p.get("operator"):
        parts.append(f"<b>Operator:</b> {p['operator']}")
    if p.get("opened_display"):
        parts.append(f"<b>Opened:</b> {p['opened_display']}")
    elif unknown_year:
        parts.append("<b>Opened:</b> <i>unknown</i>")
    if p.get("notes"):
        parts.append(p["notes"])
    if p.get("source"):
        parts.append(f"<small>Source: {p['source']}</small>")
    popup = folium.Popup("<br>".join(parts), max_width=360)

    marker = folium.Marker(
        location=[coords[1], coords[0]],
        icon=noncoal_hex_icon(r, color, unknown=unknown_year),
        popup=popup,
        pane="gemPane",
    )
    marker.add_to(noncoal_group)
    noncoal_year_map[marker.get_name()] = slider_year

noncoal_group.add_to(m)
noncoal_group_var = noncoal_group.get_name()

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
    Mining Across Southern Mongolia
  </div>
  <div style="font-size: 12px; color: #444; margin-top: 5px;
       line-height: 1.45;">
    {summary['gem_count']} named coal mines (Global Energy Monitor,
    May 2025)<br>
    {summary['noncoal_count']} named non-coal mines (curated from
    mindat.org and academic sources)<br>
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
    <b>GEM status</b>
    <span style="color:#d62728;">●</span> Operating
    <span style="color:#ff8c00;">●</span> Proposed
    <span style="color:#f1c40f;">●</span> Construction
    <span style="color:#7f7f7f;">●</span> Other<br>
    <b>Coal grade</b><br>
    <span style="color:#555;">●</span> Thermal (steam coal, power generation)<br>
    <span style="color:#555;">▲</span> Metallurgical (coking coal, steel)<br>
    <span style="color:#555;">◆</span> Thermal &amp; Metallurgical<br>
    <b>Non-coal mines (curated)</b>
    <div style="display: grid; grid-template-columns: 1fr 1fr;
         column-gap: 6px; row-gap: 1px; margin: 2px 0 1px 0;">
      <span><span style="color:#6a1b9a;">⬢</span> Rare Earth</span>
      <span><span style="color:#ffc107;">⬢</span> Gold</span>
      <span><span style="color:#9e9e9e;">⬢</span> Silver</span>
      <span><span style="color:#689f38;">⬢</span> Copper</span>
      <span><span style="color:#424242;">⬢</span> Iron</span>
      <span><span style="color:#c62828;">⬢</span> Lead / Zinc</span>
      <span><span style="color:#006064;">⬢</span> Tungsten</span>
      <span><span style="color:#ce93d8;">⬢</span> Lithium</span>
      <span><span style="color:#cddc39;">⬢</span> Uranium</span>
      <span><span style="color:#66bb6a;">⬢</span> Fluorite</span>
      <span><span style="color:#b71c1c;">⬢</span> Tailings</span>
    </div>
    Dashed outline = opening year unknown.<br>
    <b>Tang</b>
    <span style="color:{TANG_COLOR};">●</span> satellite-identified
    surface mining footprint<br>
    Polygon outlines: visible at zoom ≥ {TANG_POLY_MIN_ZOOM}.
  </div>
</div>
"""

pref_panel_html = f"""
<div id="sm-pref-panel" style="position: fixed; top: 380px; right: 12px;
    z-index: 1000; background: rgba(255,255,255,0.94);
    padding: 10px 12px; border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px; width: 220px;
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div style="font-weight: 600; margin-bottom: 6px;">
    Jump to prefecture
  </div>
  <select id="sm-pref-select" style="width: 100%; padding: 5px;
      font-size: 12px; box-sizing: border-box;">
    <option value="">— Select —</option>
    {options_html}
  </select>
  <button id="sm-pref-reset" style="margin-top: 6px; width: 100%;
      padding: 5px; font-size: 12px; cursor: pointer;
      background: #f0f0f0; border: 1px solid #aaa; border-radius: 3px;">
    Reset view
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
  capacity. Non-coal mines manually curated from mindat.org locality
  data and peer-reviewed mining geology literature; coordinates
  accurate to ~1 km.
</div>
"""

noncoal_dated_count = sum(
    1 for f in noncoal_features
    if f["properties"].get("opened_year") is not None
)
noncoal_undated_count = len(noncoal_features) - noncoal_dated_count
total_dated = gem_dated_count + noncoal_dated_count
total_undated = gem_undated_count + noncoal_undated_count

slider_html = f"""
<div id="sm-time-slider" style="position: fixed; bottom: 50px; left: 50%;
    transform: translateX(-50%); z-index: 1000;
    background: rgba(255,255,255,0.94); padding: 8px 16px;
    border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px; color: #333; width: min(680px, 88vw);
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div style="display: flex; justify-content: space-between;
      align-items: baseline; gap: 12px; margin-bottom: 4px;
      flex-wrap: wrap;">
    <span><b>Year:</b>
      <span id="sm-year-label" style="font-weight: 600;">{SLIDER_INIT}</span>
    </span>
    <span style="color: #777; font-size: 10.5px;">
      <span id="sm-year-shown">{total_dated}</span>/<span
          id="sm-year-total">{total_dated}</span> dated mines visible
    </span>
  </div>
  <input id="sm-year-slider" type="range" min="{SLIDER_MIN}"
      max="{SLIDER_MAX}" value="{SLIDER_INIT}" step="1"
      style="width: 100%;">
  <div style="display: flex; justify-content: space-between;
      font-size: 10px; color: #999; margin-top: 1px;">
    <span>{SLIDER_MIN}</span><span>{SLIDER_MAX}</span>
  </div>
  <div style="font-size: 10px; color: #888; line-height: 1.45;
      margin-top: 6px; padding-top: 5px; border-top: 1px solid #eee;">
    Timeline shows mines by recorded opening year (Global Energy
    Monitor data).<br>
    <span id="sm-undated-count">{total_undated}</span> mines without
    recorded opening year are visible only when timeline is at
    {SLIDER_MAX}.<br>
    Tang &amp; Werner satellite layer (2019 imagery) is hidden when
    timeline is active, since it has no temporal resolution.
  </div>
</div>
"""

m.get_root().html.add_child(folium.Element(
    title_html + info_html + pref_panel_html + slider_html + footer_html
))

# Combined slider registry: {marker_var: {group, year}}. GEM markers map
# to the GEM FeatureGroup; non-coal markers to the non-coal FeatureGroup.
# Both share the slider; non-coal mines without a sortable opened year
# behave identically to GEM mines without an opening year.
combined_year_registry = {}
for varname, year in gem_year_map.items():
    combined_year_registry[varname] = {"group": gem_group_var, "year": year}
for varname, year in noncoal_year_map.items():
    combined_year_registry[varname] = {
        "group": noncoal_group_var, "year": year
    }

# Zoom toggle for polygon layer + dropdown handlers + year slider.
# Year slider semantics:
#   slider == SLIDER_MAX  → undated mines visible (dashed style).
#   slider <  SLIDER_MAX  → undated mines hidden, hint banner visible.
#   prefecture Reset also snaps the slider back to SLIDER_MAX.
# `markerYearMap` is one combined registry — the GEM loop populates it
# now, the non-coal loop (Task B) extends it via the same JSON. Each
# entry is `{{group: <featuregroup-var-name>, year: <int-or-null>}}`.
panel_js = f"""
<script>
(function() {{
    var prefBounds = {pref_bounds_js};
    var initialCenter = {json.dumps(INITIAL_CENTER)};
    var initialZoom = {INITIAL_ZOOM};
    var POLY_MIN_ZOOM = {TANG_POLY_MIN_ZOOM};
    var SLIDER_MAX = {SLIDER_MAX};
    var markerYearRegistry = {json.dumps(combined_year_registry)};
    var GEM_GROUP_NAME = "{gem_group_var}";

    function ready() {{
        var sel = document.getElementById('sm-pref-select');
        var reset = document.getElementById('sm-pref-reset');
        var slider = document.getElementById('sm-year-slider');
        var yearLabel = document.getElementById('sm-year-label');
        var yearShown = document.getElementById('sm-year-shown');
        var yearTotal = document.getElementById('sm-year-total');
        var undatedCount = document.getElementById('sm-undated-count');
        var gemGroup = (typeof {gem_group_var} !== 'undefined')
            ? {gem_group_var} : null;
        if (!sel || !reset || !slider || !gemGroup ||
            typeof {map_var} === 'undefined') {{
            setTimeout(ready, 60);
            return;
        }}

        // Resolve registry entries: each value is either a year (legacy
        // GEM-only format) or {{group, year}}. Coerce to the latter.
        var registry = {{}};
        Object.keys(markerYearRegistry).forEach(function(name) {{
            var v = markerYearRegistry[name];
            if (v === null || typeof v === 'number') {{
                registry[name] = {{ group: GEM_GROUP_NAME, year: v }};
            }} else {{
                registry[name] = v;
            }}
        }});

        var totalDated = 0, totalUndated = 0;
        Object.keys(registry).forEach(function(name) {{
            if (registry[name].year === null) totalUndated += 1;
            else totalDated += 1;
        }});
        yearTotal.textContent = totalDated;
        undatedCount.textContent = totalUndated;

        function timelineActive() {{
            return parseInt(slider.value, 10) < SLIDER_MAX;
        }}

        function updatePolyVisibility() {{
            var z = {map_var}.getZoom();
            var pane = {map_var}.getPane('tangPolyPane');
            if (!pane) return;
            // Polygon pane hides if zoom is too low OR the timeline is
            // active — Tang polygons are 2019 imagery with no temporal
            // axis, same reasoning as for centroid markers (handled by
            // the body.sm-timeline-active CSS rule).
            var visible = z >= POLY_MIN_ZOOM && !timelineActive();
            pane.style.opacity = visible ? 1 : 0;
            pane.style.pointerEvents = visible ? 'auto' : 'none';
        }}
        {map_var}.on('zoomend', updatePolyVisibility);

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

        function setMarkerVisibility(name, entry, visible) {{
            var marker = window[name];
            var grp = window[entry.group];
            if (!marker || !grp) return;
            if (visible) {{
                if (!grp.hasLayer(marker)) grp.addLayer(marker);
                // Belt-and-suspenders: clear any leftover display:none
                // on the rendered DOM element from a previous hide.
                var elS = marker.getElement && marker.getElement();
                if (elS) elS.style.display = '';
            }} else {{
                if (grp.hasLayer(marker)) grp.removeLayer(marker);
                // Belt-and-suspenders: if removeLayer left any orphan
                // DOM (shouldn't, but seen in some Leaflet edge cases
                // with DivIcon markers), force-hide it.
                var elH = marker.getElement && marker.getElement();
                if (elH) elH.style.display = 'none';
            }}
        }}

        function applyYear(y) {{
            yearLabel.textContent = y;
            var active = (y < SLIDER_MAX);
            // Toggle body class so the CSS rule hides Tang centroids
            // and cluster icons. LayerControl state is preserved — when
            // the slider returns to max, Tang's natural state (per the
            // user's checkbox) shines back through.
            document.body.classList.toggle('sm-timeline-active', active);
            // Re-evaluate the polygon pane (zoom × timeline gate).
            updatePolyVisibility();
            var visibleDated = 0;
            Object.keys(registry).forEach(function(name) {{
                var entry = registry[name];
                var yr = entry.year;
                if (yr === null) {{
                    setMarkerVisibility(name, entry, !active);
                }} else if (yr <= y) {{
                    setMarkerVisibility(name, entry, true);
                    visibleDated += 1;
                }} else {{
                    setMarkerVisibility(name, entry, false);
                }}
            }});
            yearShown.textContent = visibleDated;
        }}

        slider.addEventListener('input', function() {{
            applyYear(parseInt(slider.value, 10));
        }});

        reset.addEventListener('click', function() {{
            sel.value = '';
            slider.value = SLIDER_MAX;
            applyYear(SLIDER_MAX);
            {map_var}.flyTo(initialCenter, initialZoom,
                {{duration: 1.0}});
        }});

        applyYear(parseInt(slider.value, 10));
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
