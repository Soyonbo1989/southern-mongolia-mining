"""
03_merge_layers.py
Promote intermediate layer files to data/final/ and write a summary.json
that the renderer reads for title-panel counts and prefecture aggregates.

Inputs (from data/intermediate/):
    gem_sm_mines.geojson
    tang_sm_polygons.geojson
    tang_sm_centroids.geojson

Outputs (to data/final/):
    gem_sm_mines.geojson
    tang_sm_polygons.geojson
    tang_sm_centroids.geojson
    summary.json
"""
import json
import shutil
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parent.parent
INTER = ROOT / "data/intermediate"
FINAL = ROOT / "data/final"

LAYER_FILES = [
    "gem_sm_mines.geojson",
    "tang_sm_polygons.geojson",
    "tang_sm_centroids.geojson",
    "noncoal_mines.geojson",
]


def main():
    FINAL.mkdir(parents=True, exist_ok=True)
    for fname in LAYER_FILES:
        src = INTER / fname
        if not src.exists():
            raise FileNotFoundError(f"Missing intermediate: {src}")
        shutil.copy2(src, FINAL / fname)

    gem = gpd.read_file(FINAL / "gem_sm_mines.geojson")
    tang_poly = gpd.read_file(FINAL / "tang_sm_polygons.geojson")
    tang_cent = gpd.read_file(FINAL / "tang_sm_centroids.geojson")
    noncoal = gpd.read_file(FINAL / "noncoal_mines.geojson")

    # Per-prefecture aggregates from GEM, sorted desc by mine count
    pref_info = []
    for pref, g in gem.groupby("prefecture"):
        pref_info.append({
            "name": pref,
            "count": int(len(g)),
            "south": float(g.geometry.y.min()),
            "north": float(g.geometry.y.max()),
            "west": float(g.geometry.x.min()),
            "east": float(g.geometry.x.max()),
        })
    pref_info.sort(key=lambda x: -x["count"])

    summary = {
        "gem_count": int(len(gem)),
        "noncoal_count": int(len(noncoal)),
        "tang_polygon_count": int(len(tang_poly)),
        "tang_centroid_count": int(len(tang_cent)),
        "tang_total_area_km2": round(float(tang_poly["area_km2"].sum()), 1),
        "tang_min_area_km2": round(float(tang_poly["area_km2"].min()), 6),
        "tang_median_area_km2": round(
            float(tang_poly["area_km2"].median()), 6),
        "tang_max_area_km2": round(float(tang_poly["area_km2"].max()), 4),
        "tang_p95_area_km2": round(
            float(tang_poly["area_km2"].quantile(0.95)), 4),
        "prefectures": pref_info,
    }
    out = FINAL / "summary.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out.relative_to(ROOT)}")
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "prefectures"}, indent=2))


if __name__ == "__main__":
    main()
