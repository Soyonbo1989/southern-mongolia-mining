"""
05_load_noncoal.py
Load the curated non-coal mine list (data/curated/...) and emit a GeoJSON
for the renderer.

Each row carries:
  - opened_display: the original string ("1957", "1980s", "unknown",
    "exploration") for popup display.
  - opened_year: an int suitable for the timeline slider, or None when no
    sortable year can be inferred. Decade strings ("1980s") collapse to
    the decade start.

NaN cells and the literal string "unknown" become None so the renderer
can suppress empty popup lines.

Output: data/intermediate/noncoal_mines.geojson
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/curated/southern_mongolia_noncoal_mines.csv"
OUT = ROOT / "data/intermediate/noncoal_mines.geojson"


def parse_opened(v):
    """Return (display_string_or_None, sortable_year_or_None)."""
    if pd.isna(v):
        return (None, None)
    s = str(v).strip()
    sl = s.lower()
    if sl in ("", "unknown", "n/a", "tbd"):
        return (None, None)
    if sl == "exploration":
        return (s, None)
    m = re.match(r"^(\d{4})s$", s)
    if m:
        return (s, int(m.group(1)))
    m = re.match(r"^(\d{4})$", s)
    if m:
        y = int(m.group(1))
        if 1800 <= y <= 2100:
            return (s, y)
    return (s, None)


def clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() == "unknown":
            return None
        return s
    return v


def main():
    df = pd.read_csv(SRC)
    features = []
    for _, row in df.iterrows():
        props = {col: clean(row[col]) for col in df.columns}
        opened_display, opened_year = parse_opened(row["opened"])
        props["opened_display"] = opened_display
        props["opened_year"] = opened_year
        # Drop the raw `opened` field — keep only display + year.
        props.pop("opened", None)
        lon = float(row["longitude"])
        lat = float(row["latitude"])
        # Strip lat/lon from props since they are in geometry.
        props.pop("longitude", None)
        props.pop("latitude", None)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    fc = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)

    counts = {}
    for f in features:
        c = f["properties"].get("commodity_primary") or "(unknown)"
        counts[c] = counts.get(c, 0) + 1
    dated = sum(1 for f in features
                if f["properties"].get("opened_year") is not None)
    print(f"Wrote {len(features)} non-coal mines to "
          f"{OUT.relative_to(ROOT)}")
    print(f"  Dated (sortable opened_year): {dated}")
    print(f"  Undated: {len(features) - dated}")
    print("  By commodity_primary:")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {c:<18} {n}")


if __name__ == "__main__":
    main()
