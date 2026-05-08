"""
One-shot exploration of the Tang & Werner 2023 dataset.
Reports counts, fields, CRS, area stats, China/SM intersection, and
overlap with the GEM 423 SM mines.

Run from project root:
    python explore_tang.py
"""
import time
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely.geometry import box

warnings.filterwarnings("ignore")

TANG = Path("data/raw/tang2023/74548_projected polygons.shp")
NE = Path("data/raw/natural_earth/ne_10m_admin_1/"
         "ne_10m_admin_1_states_provinces.shp")
GEM = Path("data/gem-data/Global-Coal-Mine-Tracker-May-2025-V2.xlsx")

# Bbox covers Southern Mongolia plus a safety margin into surrounding
# Mongolia/Russia/Liaoning; we then trim to actual China/SM territory.
BBOX_LATLON = (97.0, 41.0, 126.0, 53.5)  # (minx, miny, maxx, maxy)


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


# ---------------------------------------------------------------------------
section("1. Tang dataset metadata (no geometry load)")
info = pyogrio.read_info(TANG)
print(f"Total polygons         : {info['features']:,}")
print(f"Native CRS             : {info['crs'][:60]}...")
print(f"Geometry type          : {info['geometry_type']}")
print(f"Fields                 : {info['fields']}")
print(f"Field dtypes           : {info['dtypes']}")
print(f"Native bbox (m)        : {info.get('total_bounds')}")

# ---------------------------------------------------------------------------
section("2. Load full dataset")
t0 = time.time()
gdf = gpd.read_file(TANG, engine="pyogrio")
load_time = time.time() - t0
print(f"Loaded {len(gdf):,} rows in {load_time:.1f}s")
print(f"Columns                : {list(gdf.columns)}")
print(f"CRS                    : {gdf.crs.name}")
print(f"CRS is_projected       : {gdf.crs.is_projected}")
print(f"CRS units              : {gdf.crs.axis_info[0].unit_name}")

# ---------------------------------------------------------------------------
section("3. Attribute field summary")
for col in gdf.columns:
    if col == "geometry":
        continue
    nuniq = gdf[col].nunique(dropna=False)
    if nuniq <= 25:
        print(f"\n[{col}]  {nuniq} unique values")
        print(gdf[col].value_counts(dropna=False).head(25))
    else:
        sample = gdf[col].dropna().head(3).tolist()
        print(f"\n[{col}]  {nuniq} unique values (sample: {sample})")

# ---------------------------------------------------------------------------
section("4. Global area stats (km², equal-area CRS)")
areas_km2_all = gdf.geometry.area / 1e6
print(f"min    : {areas_km2_all.min():.6f}")
print(f"median : {areas_km2_all.median():.6f}")
print(f"mean   : {areas_km2_all.mean():.6f}")
print(f"max    : {areas_km2_all.max():.4f}")
print(f"sum    : {areas_km2_all.sum():,.1f}")

# ---------------------------------------------------------------------------
section("5. Reproject to WGS84 + bbox prefilter")
t0 = time.time()
# Convert bbox lat/lon to EASE-Grid for fast pre-filter in source CRS
to_native = Transformer.from_crs("EPSG:4326", gdf.crs, always_xy=True)
bx0, by0 = to_native.transform(BBOX_LATLON[0], BBOX_LATLON[1])
bx1, by1 = to_native.transform(BBOX_LATLON[2], BBOX_LATLON[3])
bbox_native = (min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1))
print(f"BBox in EASE coords    : {tuple(round(v) for v in bbox_native)}")

bbox_mask = gdf.geometry.intersects(
    box(*bbox_native).buffer(0)
)
in_bbox = gdf[bbox_mask].copy()
print(f"Polygons in bbox       : {len(in_bbox):,}  ({time.time()-t0:.1f}s)")

# Reproject only the bbox subset to WGS84 for admin filtering
in_bbox_wgs = in_bbox.to_crs("EPSG:4326")

# ---------------------------------------------------------------------------
section("6. Filter to China + Southern Mongolia (Natural Earth)")
ne = gpd.read_file(NE)
chn = ne[ne["adm0_a3"] == "CHN"].copy()
chn_union = chn.unary_union  # whole China outline (incl. claimed areas in NE)

in_china = in_bbox_wgs[in_bbox_wgs.intersects(chn_union)].copy()
print(f"In China (within bbox) : {len(in_china):,}")

nm_geom = chn[chn["iso_3166_2"] == "CN-NM"].geometry.iloc[0]
in_sm = in_bbox_wgs[in_bbox_wgs.intersects(nm_geom)].copy()
print(f"In Southern Mongolia   : {len(in_sm):,}")

# ---------------------------------------------------------------------------
section("7. SM-only area stats (km²)")
in_sm_native = in_sm.to_crs(gdf.crs)
areas_sm = in_sm_native.geometry.area / 1e6
print(f"min    : {areas_sm.min():.6f}")
print(f"median : {areas_sm.median():.6f}")
print(f"mean   : {areas_sm.mean():.6f}")
print(f"max    : {areas_sm.max():.4f}")
print(f"sum    : {areas_sm.sum():,.1f}")

# ---------------------------------------------------------------------------
section("8. GEM overlap (1 km buffer of each GEM point)")
df = pd.read_excel(GEM, sheet_name="GCMT Non-closed Mines")
sm_mines = df[(df["Country / Area"] == "China") &
              (df["State, Province"] == "Inner Mongolia")].copy()
# Same dedupe as make_map.py (3 multi-phase mines collapse to 1 row each)
seen = set()
rows = []
for _, r in sm_mines.iterrows():
    key = (r["Mine Name"], r["Latitude"], r["Longitude"])
    if key in seen:
        continue
    seen.add(key)
    rows.append({"name": r["Mine Name"],
                 "lon": float(r["Longitude"]),
                 "lat": float(r["Latitude"])})
print(f"GEM SM mines (deduped) : {len(rows)}")

gem_pts = gpd.GeoDataFrame(
    rows,
    geometry=gpd.points_from_xy([x["lon"] for x in rows],
                                [x["lat"] for x in rows]),
    crs="EPSG:4326",
)
gem_native = gem_pts.to_crs(gdf.crs)  # EASE-Grid (meters)
gem_buf = gem_native.copy()
gem_buf["geometry"] = gem_native.geometry.buffer(1000)  # 1 km buffer

joined = gpd.sjoin(gem_buf, in_sm_native, how="inner", predicate="intersects")
matched = joined.index.unique()
n_match = len(matched)
print(f"GEM points whose 1 km buffer intersects ≥1 Tang polygon (in SM):")
print(f"  {n_match} / {len(gem_pts)}  ({n_match/len(gem_pts)*100:.1f}%)")

# Also: how many Tang polygons in SM are touched by ≥1 GEM buffer
tang_touched = joined["index_right"].nunique()
print(f"Tang SM polygons touched by ≥1 GEM buffer:")
print(f"  {tang_touched} / {len(in_sm_native)}  "
      f"({tang_touched/len(in_sm_native)*100:.1f}%)")

# ---------------------------------------------------------------------------
section("9. Done.  Summary line:")
print(f"Tang has {info['features']:,} global polygons; "
      f"{len(in_china):,} in China, "
      f"{len(in_sm):,} in Southern Mongolia.")
print(f"GEM/Tang overlap in SM: {n_match}/{len(gem_pts)} GEM points "
      f"({n_match/len(gem_pts)*100:.1f}%) "
      f"have a Tang polygon within 1 km.")
