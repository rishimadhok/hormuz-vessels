"""Spot-validate the persistence filter's STATIC set: do the recurring detections
sit on real land/islands/infrastructure, or are they random recurring noise?

Clusters the static detections by ~100 m cell, prints the top clusters by
recurrence, and reports each cluster's distance to the nearest Natural Earth land
polygon plus the nearest named Strait feature.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ART = Path("/Users/rishimadhok/Desktop/hormuz-vessels/artifacts")
LAND = Path("/Users/rishimadhok/Desktop/hormuz-vessels/data/land")

# Known features in/near the chokepoint bbox (lon, lat).
KNOWN = [
    ("Larak Island", 56.36, 26.855),
    ("Hormuz Island", 56.46, 27.06),
    ("Qeshm Island (E tip)", 56.27, 26.75),
    ("Hengam Island", 55.91, 26.65),
    ("Greater Tunb", 55.30, 26.25),
    ("Musandam coast (Oman)", 56.40, 26.30),
    ("Iranian mainland (Bandar)", 56.30, 27.10),
]


def main() -> None:
    dets = json.loads((ART / "detections.json").read_text())["detections"]
    static = [d for d in dets if d.get("is_static")]
    print(f"{len(static)} static detections of {len(dets)} total")

    # Cluster by ~100 m cell.
    cells: dict = defaultdict(list)
    for d in static:
        cells[(round(d["lon"], 3), round(d["lat"], 3))].append(d)
    clusters = []
    for (lon, lat), members in cells.items():
        clusters.append({
            "lon": lon, "lat": lat, "n": len(members),
            "max_persist": max(m["persistence_dates"] for m in members),
        })
    clusters.sort(key=lambda c: (c["max_persist"], c["n"]), reverse=True)

    # Natural Earth land (same source as the mask). Clip to the AOI region (in 4326)
    # BEFORE projecting — projecting global land to one UTM zone yields invalid geometry.
    from shapely.geometry import box
    region = box(55.0, 25.5, 57.5, 27.5)  # buffer around the chokepoint bbox
    frames = [gpd.read_file(LAND / f"{lyr}.geojson")[["geometry"]]
              for lyr in ("ne_10m_land", "ne_10m_minor_islands")]
    land = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    land = land.clip(region)
    land_m = land.to_crs("EPSG:32640")
    land_union = land_m.union_all() if hasattr(land_m, "union_all") else land_m.unary_union

    def nearest_known(lon, lat):
        best, bd = None, 1e9
        for name, klon, klat in KNOWN:
            d = ((lon - klon) ** 2 + (lat - klat) ** 2) ** 0.5 * 111.0  # ~km
            if d < bd:
                best, bd = name, d
        return best, bd

    print(f"\n{len(clusters)} static clusters; top by recurrence:\n")
    print(f"{'lon':>8} {'lat':>8} {'n':>3} {'dates':>5}  {'dist→land(km)':>13}  nearest known feature")
    for c in clusters[:8]:
        pt = gpd.GeoSeries([Point(c["lon"], c["lat"])], crs="EPSG:4326").to_crs("EPSG:32640").iloc[0]
        dist_km = pt.distance(land_union) / 1000.0
        name, kd = nearest_known(c["lon"], c["lat"])
        print(f"{c['lon']:8.3f} {c['lat']:8.3f} {c['n']:3d} {c['max_persist']:5d}  "
              f"{dist_km:13.2f}  {name} (~{kd:.0f} km)")


if __name__ == "__main__":
    main()
