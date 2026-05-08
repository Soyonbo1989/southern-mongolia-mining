"""
02_load_tang.py
Filter Tang & Werner 2023 global mining polygons to Southern Mongolia,
drop tiny polygons (<0.001 km²), simplify geometries for web rendering,
extract centroids.

Source CRS is WGS 84 / NSIDC EASE-Grid Global (equal-area, meters).
We use it to compute area and to simplify in metric units, then
reproject to EPSG:4326 for web display.

Outputs:
    data/intermediate/tang_sm_polygons.geojson   (simplified polygons)
    data/intermediate/tang_sm_centroids.geojson  (one centroid per poly)
"""
import json
import warnings
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely import force_2d
from shapely.geometry import box

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
TANG = ROOT / "data/raw/tang2023/74548_projected polygons.shp"
NE = (ROOT / "data/raw/natural_earth/ne_10m_admin_1/"
      "ne_10m_admin_1_states_provinces.shp")
OUT_POLY = ROOT / "data/intermediate/tang_sm_polygons.geojson"
OUT_CENT = ROOT / "data/intermediate/tang_sm_centroids.geojson"

# Bbox covers all of Inner Mongolia (CN-NM) plus a small margin.
BBOX_LATLON = (97.0, 36.0, 127.0, 54.0)
MIN_AREA_KM2 = 0.001          # 1000 m² — drops digitization noise
SIMPLIFY_TOLERANCE_M = 50     # ≈ 1/6 pixel at zoom 9


def main():
    print(f"Reading {TANG.name}")
    gdf = gpd.read_file(TANG, engine="pyogrio")
    src_crs = gdf.crs
    print(f"  {len(gdf):,} polygons total")

    # Bbox prefilter in source CRS (faster than reprojecting all 74k first)
    t = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
    x0, y0 = t.transform(BBOX_LATLON[0], BBOX_LATLON[1])
    x1, y1 = t.transform(BBOX_LATLON[2], BBOX_LATLON[3])
    bbox_native = box(min(x0, x1), min(y0, y1),
                      max(x0, x1), max(y0, y1))
    gdf_pre = gdf[gdf.geometry.intersects(bbox_native)].copy()
    print(f"  {len(gdf_pre):,} after bbox prefilter")

    # Reproject the subset to WGS84 for admin filtering
    gdf_wgs = gdf_pre.to_crs("EPSG:4326")

    # Filter to Inner Mongolia using Natural Earth CN-NM polygon
    ne = gpd.read_file(NE)
    nm_geom = ne[ne["iso_3166_2"] == "CN-NM"].geometry.iloc[0]
    in_sm = gdf_wgs[gdf_wgs.intersects(nm_geom)].copy()
    print(f"  {len(in_sm):,} in Southern Mongolia (CN-NM)")

    # Compute area in km² using equal-area source CRS
    in_sm_proj = in_sm.to_crs(src_crs)
    in_sm["area_km2"] = (in_sm_proj.geometry.area / 1e6).values
    in_sm_proj["area_km2"] = in_sm["area_km2"].values

    pre_n = len(in_sm)
    in_sm = in_sm[in_sm["area_km2"] >= MIN_AREA_KM2].copy()
    in_sm_proj = in_sm_proj[in_sm_proj["area_km2"] >= MIN_AREA_KM2].copy()
    dropped = pre_n - len(in_sm)
    print(f"  Dropped {dropped} polygons with area < {MIN_AREA_KM2} km²")
    print(f"  {len(in_sm):,} polygons remaining")

    # Simplify in projected metric CRS, then reproject and force 2D
    in_sm_proj["geometry"] = in_sm_proj.geometry.simplify(
        SIMPLIFY_TOLERANCE_M, preserve_topology=True
    )
    in_sm_simp = in_sm_proj.to_crs("EPSG:4326")
    in_sm_simp["geometry"] = in_sm_simp.geometry.apply(force_2d)

    # Save polygons (only keep id + area + geometry to keep file small)
    poly_out = in_sm_simp[["OBJECTID", "area_km2", "geometry"]].copy()
    poly_out = poly_out.rename(columns={"OBJECTID": "tang_id"})
    poly_out["tang_id"] = poly_out["tang_id"].astype(int)
    poly_out["area_km2"] = poly_out["area_km2"].round(6)
    if OUT_POLY.exists():
        OUT_POLY.unlink()
    poly_out.to_file(OUT_POLY, driver="GeoJSON")
    print(f"  Saved polygons → {OUT_POLY.relative_to(ROOT)} "
          f"({OUT_POLY.stat().st_size/1024/1024:.2f} MB)")

    # Compute centroids in projected CRS for accuracy, then reproject
    centroids_proj = in_sm_proj.geometry.centroid
    centroids_wgs = gpd.GeoSeries(centroids_proj, crs=src_crs).to_crs(
        "EPSG:4326"
    )
    cent_out = gpd.GeoDataFrame(
        {
            "tang_id": in_sm["OBJECTID"].astype(int).values,
            "area_km2": in_sm["area_km2"].round(6).values,
            "geometry": centroids_wgs.values,
        },
        crs="EPSG:4326",
    )
    if OUT_CENT.exists():
        OUT_CENT.unlink()
    cent_out.to_file(OUT_CENT, driver="GeoJSON")
    print(f"  Saved centroids → {OUT_CENT.relative_to(ROOT)} "
          f"({OUT_CENT.stat().st_size/1024:.1f} KB)")

    print("\nSummary:")
    print(json.dumps({
        "polygons_kept": len(in_sm),
        "polygons_dropped_tiny": dropped,
        "total_area_km2": round(float(in_sm["area_km2"].sum()), 1),
        "min_area_km2": round(float(in_sm["area_km2"].min()), 6),
        "median_area_km2": round(float(in_sm["area_km2"].median()), 6),
        "max_area_km2": round(float(in_sm["area_km2"].max()), 4),
    }, indent=2))


if __name__ == "__main__":
    main()
