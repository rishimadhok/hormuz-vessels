"""Credibility check: per-date AOI coverage vs moving-vessel count.

For each acquisition date, union the imaged footprint of all that date's scenes
onto a common ~150 m AOI grid (read coarse via COG overviews = fast), compute
coverage % and imaged km2, and normalise the moving-vessel count by imaged area.
This tells us whether the open-vs-closed traffic drop is real or a coverage artifact.

Run: PYTHONPATH=src .venv/bin/python scripts/coverage.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window as RioWindow
from rasterio.windows import from_bounds

from hormuz import fetch
from hormuz.config import load_settings
from hormuz.search import search_scenes

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
# Read the AOI bbox from the detections artifact so coverage matches the run
# (portable: works for any bbox another team reruns on).
try:
    BBOX = tuple(json.loads((ART / "detections.json").read_text())["bbox"])
except Exception:  # noqa: BLE001
    BBOX = (56.0, 26.2, 56.9, 26.9)
DST_CRS = fetch._utm_epsg_for(BBOX)  # same UTM target the detector uses (proven path)
DS = 20  # downsample factor for the coverage read (fast; coverage is scale-invariant)

# Full-AOI area in km2 (for imaged_km2 = coverage_frac * this).
_l, _b, _r, _t = transform_bounds("EPSG:4326", DST_CRS, *BBOX)
AOI_KM2 = abs((_r - _l) * (_t - _b)) / 1e6


def _scene_coverage(scene, env) -> float | None:
    """Fraction of the AOI imaged (finite) by one scene, via the detector's read path."""
    with rasterio.open(scene.asset_href) as src:
        with WarpedVRT(src, crs=DST_CRS) as vrt:
            aoi = transform_bounds("EPSG:4326", DST_CRS, *BBOX)
            aoi_win = from_bounds(*aoi, transform=vrt.transform)
            total_aoi = aoi_win.width * aoi_win.height
            inter = aoi_win.intersection(RioWindow(0, 0, vrt.width, vrt.height))
            if inter.width < 1 or inter.height < 1:
                return 0.0
            oh = max(1, round(inter.height / DS))
            ow = max(1, round(inter.width / DS))
            arr = vrt.read(1, window=inter, out_shape=(oh, ow))
            nod = vrt.nodata
    m = np.isfinite(arr) & (arr != 0)
    if nod is not None:
        m &= arr != nod
    imaged = m.mean() * (inter.width * inter.height)
    return float(imaged / total_aoi)


def date_coverage(date: str) -> dict:
    s = load_settings(bbox=BBOX, start=date, end=date, max_scenes=None)
    scenes = search_scenes(s)
    best = 0.0
    with rasterio.Env(**fetch._GDAL_ENV):
        for sc in scenes:
            try:
                best = max(best, _scene_coverage(sc, None) or 0.0)
            except Exception as e:  # noqa: BLE001
                print(f"   ! {date} {sc.item_id}: {e}")
    return {
        "date": date,
        "coverage_pct": round(100.0 * best, 1),
        "imaged_km2": round(best * AOI_KM2, 1),
        "n_scenes": len(scenes),
    }


def main() -> None:
    ts = json.loads((ART / "timeseries.json").read_text())["series"]
    moving = {s["date"]: s["moving_count"] for s in ts}
    status = json.loads((ART / "detections.json").read_text()).get("scene_status", {})

    rows = []
    for date in sorted(moving):
        cov = date_coverage(date)
        cov["moving"] = moving[date]
        cov["status"] = status.get(date, "?")
        cov["vessels_per_1000km2"] = (
            round(1000.0 * cov["moving"] / cov["imaged_km2"], 1) if cov["imaged_km2"] else None
        )
        rows.append(cov)
        print(f"  {date}  cov={cov['coverage_pct']:5.1f}%  imaged={cov['imaged_km2']:7.1f} km2  "
              f"moving={cov['moving']:4d}  density={cov['vessels_per_1000km2']}/1000km2  [{cov['status']}]")

    (ART / "coverage.json").write_text(
        json.dumps({"downsample": DS, "bbox": list(BBOX), "aoi_km2": round(AOI_KM2, 1), "rows": rows}, indent=2))
    print(f"\nwrote {ART/'coverage.json'}")


if __name__ == "__main__":
    main()
