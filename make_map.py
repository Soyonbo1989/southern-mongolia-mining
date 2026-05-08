"""
Southern Mongolia coal mining map.
Outputs southern_mongolia_mining.html.

Data: Global Energy Monitor, Global Coal Mine Tracker, May 2025 V2.
The GEM source data uses the string "Inner Mongolia"; that is the only
place in this project where that string appears. All user-facing output
uses "Southern Mongolia".
"""
import json
import pandas as pd
import folium
from pathlib import Path

SRC = Path("data/gem-data/Global-Coal-Mine-Tracker-May-2025-V2.xlsx")
OUT = Path("southern_mongolia_mining.html")

# ---------------------------------------------------------------------------
# 1. Load + filter
# ---------------------------------------------------------------------------
df = pd.read_excel(SRC, sheet_name="GCMT Non-closed Mines")
sm = df[(df["Country / Area"] == "China") &
        (df["State, Province"] == "Inner Mongolia")].copy()

# ---------------------------------------------------------------------------
# 2. Prefecture normalization
# ---------------------------------------------------------------------------
PREF_MAP = {
    "Ordos": "Ordos",
    "Ordos City": "Ordos",
    "Xilin Gol": "Xilin Gol",
    "Xilingol League": "Xilin Gol",
    "Hulun Buir": "Hulun Buir",
    "Hulunbuir": "Hulun Buir",
    "Alxa": "Alxa",
    "Alxa League": "Alxa",
}

# Xiehua Coal Mine (39.85, 111.33) has no prefecture in GEM; manually
# assigned to Hohhot based on coordinates (Qingshuihe/Tuoketuo area).
def normalize_pref(p):
    if pd.isna(p):
        return "Hohhot"
    return PREF_MAP.get(p, p)

sm["Prefecture"] = sm["Prefecture, District"].apply(normalize_pref)

# ---------------------------------------------------------------------------
# 3. Dedupe multi-phase rows (same Mine Name + coords)
# ---------------------------------------------------------------------------
merged_rows = []
for _, group in sm.groupby(["Mine Name", "Latitude", "Longitude"], sort=False):
    row = group.iloc[0].copy()
    if len(group) > 1:
        row["Capacity (Mtpa)"] = group["Capacity (Mtpa)"].sum()
        statuses = list(dict.fromkeys(group["Status"].tolist()))
        row["Status"] = " + ".join(statuses) + " (multi-phase)"
    row["_merged_count"] = len(group)
    merged_rows.append(row)

mines = pd.DataFrame(merged_rows).reset_index(drop=True)

# ---------------------------------------------------------------------------
# 4. Visual encoding helpers
# ---------------------------------------------------------------------------
CAP_MIN = float(mines["Capacity (Mtpa)"].min())
CAP_MAX = float(mines["Capacity (Mtpa)"].max())
R_MIN, R_MAX = 3.0, 25.0

def radius_for(cap: float) -> float:
    if CAP_MAX == CAP_MIN:
        return (R_MIN + R_MAX) / 2
    norm = (cap - CAP_MIN) / (CAP_MAX - CAP_MIN)
    return R_MIN + norm * (R_MAX - R_MIN)

def color_for(status: str) -> str:
    s = status.lower()
    if "operating" in s:
        return "#d62728"   # red
    if "construction" in s:
        return "#f1c40f"   # yellow
    if "proposed" in s:
        return "#ff8c00"   # orange
    return "#7f7f7f"       # gray (Mothballed, Shelved, etc.)

# ---------------------------------------------------------------------------
# 5. Prefecture bounds + counts (sorted desc by count for the dropdown)
# ---------------------------------------------------------------------------
pref_info = []
for pref, g in mines.groupby("Prefecture"):
    pref_info.append({
        "name": pref,
        "count": int(len(g)),
        "south": float(g["Latitude"].min()),
        "north": float(g["Latitude"].max()),
        "west": float(g["Longitude"].min()),
        "east": float(g["Longitude"].max()),
    })
pref_info.sort(key=lambda x: -x["count"])

pref_bounds_js = {p["name"]: {
    "south": p["south"], "north": p["north"],
    "west":  p["west"],  "east":  p["east"]
} for p in pref_info}

# ---------------------------------------------------------------------------
# 6. Build the map
# ---------------------------------------------------------------------------
INITIAL_CENTER = [43.5, 113.0]
INITIAL_ZOOM = 5

m = folium.Map(location=INITIAL_CENTER, zoom_start=INITIAL_ZOOM,
               tiles="OpenStreetMap", control_scale=True)

# Mine circles
for _, r in mines.iterrows():
    cap = float(r["Capacity (Mtpa)"])
    parts = [f"<b>{r['Mine Name']}</b>"]
    if pd.notna(r["Mine Name (Non-ENG)"]):
        parts.append(f"<i>{r['Mine Name (Non-ENG)']}</i>")
    parts.append(f"<b>Owners:</b> {r['Owners']}")
    if pd.notna(r.get("Parent Company")):
        parts.append(f"<b>Parent company:</b> {r['Parent Company']}")
    parts.append(f"<b>Capacity:</b> {cap:g} Mtpa")
    parts.append(f"<b>Status:</b> {r['Status']}")
    if pd.notna(r["Mine Type"]):
        parts.append(f"<b>Mine type:</b> {r['Mine Type']}")
    parts.append(f"<b>Prefecture:</b> {r['Prefecture']}")
    if r["_merged_count"] > 1:
        parts.append(
            f"<i>Multi-phase project: details merged from "
            f"{r['_merged_count']} GEM records</i>"
        )
    popup = folium.Popup("<br>".join(parts), max_width=360)

    folium.CircleMarker(
        location=[float(r["Latitude"]), float(r["Longitude"])],
        radius=radius_for(cap),
        color=color_for(r["Status"]),
        weight=1,
        fill=True,
        fill_color=color_for(r["Status"]),
        fill_opacity=0.7,
        opacity=0.7,
        popup=popup,
    ).add_to(m)

# Mergen marker (added last → renders in markerPane, above CircleMarkers)
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
    z_index_offset=1000,
).add_to(m)

# ---------------------------------------------------------------------------
# 7. Title, info panel, prefecture dropdown
# ---------------------------------------------------------------------------
total_mines = len(mines)
total_prefectures = len(pref_info)

option_tags = "\n".join(
    f'<option value="{p["name"]}">{p["name"]} ({p["count"]})</option>'
    for p in pref_info
)

panel_html = f"""
<div id="sm-title" style="
    position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
    z-index: 1000; background: rgba(255,255,255,0.94);
    padding: 10px 18px; border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div style="font-size: 18px; font-weight: 600;">
    Mining Across Southern Mongolia / 南蒙古矿业图谱
  </div>
  <div style="font-size: 12px; color: #555; margin-top: 3px;">
    {total_mines} coal mines mapped from Global Energy Monitor data (May 2025)
  </div>
</div>

<div id="sm-info" style="
    position: fixed; top: 12px; left: 12px; z-index: 1000;
    background: rgba(255,255,255,0.94); padding: 10px 12px;
    border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 11px; color: #333; max-width: 260px; line-height: 1.45;
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div><b>Source:</b> Global Energy Monitor, Global Coal Mine Tracker,
  May 2025 V2.</div>
  <div style="margin-top: 4px;"><b>Known limitation:</b> GEM systematically
  under-counts small private mines; the real number is higher.</div>
  <div style="margin-top: 4px;"><b>Note:</b> "Southern Mongolia" is the
  standard name for this region in international human-rights contexts.</div>
  <div style="margin-top: 6px; padding-top: 4px; border-top: 1px solid #ddd;">
    <b>Color:</b>
    <span style="color:#d62728;">●</span> Operating
    <span style="color:#ff8c00;">●</span> Proposed
    <span style="color:#f1c40f;">●</span> Construction
    <span style="color:#7f7f7f;">●</span> Other<br>
    <b>Size:</b> capacity (Mtpa)
  </div>
</div>

<div id="sm-pref-panel" style="
    position: fixed; top: 100px; right: 12px; z-index: 1000;
    background: rgba(255,255,255,0.94); padding: 10px 12px;
    border: 1px solid #aaa; border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px; width: 220px;
    box-shadow: 0 2px 6px rgba(0,0,0,.15);">
  <div style="font-weight: 600; margin-bottom: 6px;">
    Jump to prefecture / 跳转盟市
  </div>
  <select id="sm-pref-select" style="width: 100%; padding: 5px;
      font-size: 12px; box-sizing: border-box;">
    <option value="">— select / 选择 —</option>
    {option_tags}
  </select>
  <button id="sm-pref-reset" style="margin-top: 6px; width: 100%;
      padding: 5px; font-size: 12px; cursor: pointer;
      background: #f0f0f0; border: 1px solid #aaa; border-radius: 3px;">
    Reset view / 重置
  </button>
  <div style="font-size: 10px; color: #777; margin-top: 6px;">
    {total_prefectures} prefectures · sorted by mine count
  </div>
</div>
"""

m.get_root().html.add_child(folium.Element(panel_html))

map_var = m.get_name()
panel_js = f"""
<script>
(function() {{
    var prefBounds = {json.dumps(pref_bounds_js)};
    var initialCenter = {json.dumps(INITIAL_CENTER)};
    var initialZoom = {INITIAL_ZOOM};

    function ready() {{
        var sel = document.getElementById('sm-pref-select');
        var reset = document.getElementById('sm-pref-reset');
        if (!sel || !reset || typeof {map_var} === 'undefined') {{
            setTimeout(ready, 60);
            return;
        }}
        sel.addEventListener('change', function(e) {{
            var v = e.target.value;
            if (!v) return;
            var b = prefBounds[v];
            if (!b) return;
            var degenerate = (b.south === b.north && b.west === b.east);
            if (degenerate) {{
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
            {map_var}.flyTo(initialCenter, initialZoom, {{duration: 1.0}});
        }});
    }}
    ready();
}})();
</script>
"""

m.get_root().html.add_child(folium.Element(panel_js))

# ---------------------------------------------------------------------------
# 8. Save
# ---------------------------------------------------------------------------
m.save(str(OUT))

print(f"Saved: {OUT}")
print(f"Mines on map (after dedupe): {total_mines}")
print(f"Prefectures: {total_prefectures}")
print(f"Capacity range: {CAP_MIN:g} – {CAP_MAX:g} Mtpa")
print("\nPrefecture breakdown:")
for p in pref_info:
    print(f"  {p['name']:<14} {p['count']:>4}")
