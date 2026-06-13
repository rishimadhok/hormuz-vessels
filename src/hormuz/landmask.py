"""Land/island masking so coast and static islands aren't counted as vessels.

Phase 1 uses Natural Earth 10m land + minor-islands (small, openly licensed,
no auth, captures the main Strait islands). Phase 3 can swap in higher-fidelity
OSM land polygons for the smallest features by dropping a GeoJSON/shapefile into
data/land/ and pointing `landmask.source` at it.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from rasterio.features import rasterize
from scipy.ndimage import binary_dilation
from shapely.geometry import box

from .config import Settings
from .fetch import Window

# Natural Earth 10m vectors, openly licensed, served as raw GeoJSON.
_NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
_NE_LAYERS = ["ne_10m_land", "ne_10m_minor_islands"]

_LAND_DIR = Path("data/land")


def _ensure_natural_earth() -> gpd.GeoDataFrame:
    """Download (once) and load the NE land + minor-islands layers in EPSG:4326."""
    _LAND_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for layer in _NE_LAYERS:
        local = _LAND_DIR / f"{layer}.geojson"
        if not local.exists():
            resp = requests.get(f"{_NE_BASE}/{layer}.geojson", timeout=120)
            resp.raise_for_status()
            local.write_bytes(resp.content)
        gdf = gpd.read_file(local)
        frames.append(gdf[["geometry"]])
    land = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    return land


def build_sea_mask(window: Window, settings: Settings) -> np.ndarray:
    """Boolean mask the shape of the window: True = sea (eligible), False = land."""
    land = _ensure_natural_earth()

    # Clip to the AOI (in 4326) before reprojecting — keeps the reprojection cheap.
    aoi = box(*settings.bbox)
    land = land.clip(aoi)
    if land.empty:
        return np.ones(window.amplitude.shape, dtype=bool)  # open ocean: all sea

    # Reproject land into the scene's native CRS and rasterize onto the window grid.
    land = land.to_crs(window.crs)
    shapes = [(geom, 1) for geom in land.geometry if not geom.is_empty]
    if not shapes:
        return np.ones(window.amplitude.shape, dtype=bool)

    land_mask = rasterize(
        shapes,
        out_shape=window.amplitude.shape,
        transform=window.transform,
        fill=0,
        default_value=1,
        dtype="uint8",
    ).astype(bool)

    # Grow the land mask a few pixels to suppress bright coastline/port returns.
    d = settings.landmask.dilate_px
    if d > 0:
        land_mask = binary_dilation(land_mask, iterations=d)

    return ~land_mask
