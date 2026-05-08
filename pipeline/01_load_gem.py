"""
01_load_gem.py
Load GEM Global Coal Mine Tracker, filter to Southern Mongolia, dedupe
multi-phase rows, normalize prefecture names, write GeoJSON.

Note on terminology: GEM source rows use the string "Inner Mongolia".
That is the only place in this project where that string appears.
All output uses "Southern Mongolia".

Output: data/intermediate/gem_sm_mines.geojson  (FeatureCollection of points)
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/gem-data/Global-Coal-Mine-Tracker-May-2025-V2.xlsx"
OUT = ROOT / "data/intermediate/gem_sm_mines.geojson"

# Prefecture canonicalization (raw GEM → display name).
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

# One row in GEM has no prefecture: Xiehua Coal Mine (39.85, 111.33).
# Coordinates place it in Qingshuihe/Tuoketuo area, administered by Hohhot.
def normalize_pref(p):
    if pd.isna(p):
        return "Hohhot"
    return PREF_MAP.get(p, p)


def main():
    df = pd.read_excel(SRC, sheet_name="GCMT Non-closed Mines")
    sm = df[(df["Country / Area"] == "China") &
            (df["State, Province"] == "Inner Mongolia")].copy()
    sm["Prefecture"] = sm["Prefecture, District"].apply(normalize_pref)

    features = []
    multi_phase_dropped = 0
    for _, group in sm.groupby(["Mine Name", "Latitude", "Longitude"],
                               sort=False):
        row = group.iloc[0]
        n = len(group)
        if n > 1:
            capacity = float(group["Capacity (Mtpa)"].sum())
            statuses = list(dict.fromkeys(group["Status"].tolist()))
            status = " + ".join(statuses) + " (multi-phase)"
            multi_phase_dropped += n - 1
        else:
            capacity = float(row["Capacity (Mtpa)"])
            status = row["Status"]

        props = {
            "mine_name": row["Mine Name"],
            "mine_name_zh": (row["Mine Name (Non-ENG)"]
                             if pd.notna(row["Mine Name (Non-ENG)"]) else None),
            "owners": row["Owners"],
            "parent_company": (row["Parent Company"]
                               if pd.notna(row["Parent Company"]) else None),
            "capacity_mtpa": capacity,
            "status": status,
            "mine_type": (row["Mine Type"]
                          if pd.notna(row["Mine Type"]) else None),
            "prefecture": row["Prefecture"],
            "merged_count": n,
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [float(row["Longitude"]),
                                         float(row["Latitude"])]},
            "properties": props,
        })

    fc = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)

    pref_counts = sm["Prefecture"].value_counts().to_dict()
    print(f"Loaded {len(sm)} raw rows from GEM")
    print(f"Wrote {len(features)} unique mines to {OUT.relative_to(ROOT)}")
    print(f"Multi-phase rows merged: {multi_phase_dropped}")
    print("Prefecture counts (post-dedupe):")
    pref_post = pd.DataFrame(features)["properties"].apply(
        lambda p: p["prefecture"]).value_counts()
    for k, v in pref_post.items():
        print(f"  {k:<14} {v}")


if __name__ == "__main__":
    main()
