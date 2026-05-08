"""Full exploration of Southern Mongolia mines before refactoring make_map.py."""
import pandas as pd
from pathlib import Path

src = Path("data/gem-data/Global-Coal-Mine-Tracker-May-2025-V2.xlsx")
df = pd.read_excel(src, sheet_name="GCMT Non-closed Mines")

# Note: GEM source data uses "Inner Mongolia" — this is the only place we keep that string.
sm = df[(df["Country / Area"] == "China") &
        (df["State, Province"] == "Inner Mongolia")].copy()

print(f"Total Southern Mongolia mines: {len(sm)}\n")

# 1. Missing coordinates
missing_lat = sm["Latitude"].isna().sum()
missing_lon = sm["Longitude"].isna().sum()
missing_either = sm[sm["Latitude"].isna() | sm["Longitude"].isna()]
print(f"Missing Latitude: {missing_lat}")
print(f"Missing Longitude: {missing_lon}")
print(f"Rows missing either coord: {len(missing_either)}\n")

# 2. Duplicate rows (by Mine Name + Lat + Lon)
dup_mask = sm.duplicated(subset=["Mine Name", "Latitude", "Longitude"], keep=False)
print(f"Potential duplicate rows (same name+coords): {dup_mask.sum()}")
if dup_mask.sum() > 0:
    print(sm[dup_mask][["Mine Name", "Latitude", "Longitude", "Status"]].to_string())
print()

# 3. Status field nulls / unique values
print("Status value counts (NaN included):")
print(sm["Status"].value_counts(dropna=False))
print()

# 4. Capacity field nulls
cap_null = sm["Capacity (Mtpa)"].isna().sum()
print(f"Capacity (Mtpa) nulls: {cap_null}")
if sm["Capacity (Mtpa)"].notna().any():
    print(f"Capacity range: {sm['Capacity (Mtpa)'].min()} – {sm['Capacity (Mtpa)'].max()}")
    print(f"Capacity median: {sm['Capacity (Mtpa)'].median()}")
print()

# 5. Prefecture / District raw names — for merge planning
print("Prefecture, District value counts (raw):")
print(sm["Prefecture, District"].value_counts(dropna=False))
