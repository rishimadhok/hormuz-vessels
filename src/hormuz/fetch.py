"""Windowed read of just the AOI sub-region from a remote Sentinel-1 GRD COG.

Pulls a small region instead of the full ~1 GB product.

Important geometry note: MPC `sentinel-1-grd` measurement TIFFs are in radar
(ground-range) geometry tagged with GCPs — `src.crs` is None and there is no
simple affine transform. We georeference them on the fly with a WarpedVRT to a
target UTM CRS (so pixels are ~10 m and square, matching the CFAR window sizes),
then read only the AOI window from the VRT.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window as RioWindow
from rasterio.windows import from_bounds

from .config import Settings
from .search import Scene

# Efficient remote reads: don't list the whole bucket. (Do NOT restrict by
# extension — S1 GRD assets are *.tiff and an extension filter would exclude them.)
_GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    GDAL_HTTP_MULTIRANGE="YES",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
)


@dataclass
class Window:
    """An AOI raster window read (and georeferenced) from one scene."""

    amplitude: np.ndarray        # 2D float32 amplitude (DN), nodata -> nan
    transform: object            # affine transform of the window (target UTM)
    crs: object                  # rasterio CRS of the window (target UTM)
    scene: Scene

    @property
    def intensity(self) -> np.ndarray:
        """SAR intensity = amplitude**2 (the CFAR input)."""
        return np.square(self.amplitude)


def _utm_epsg_for(bbox: tuple[float, float, float, float]) -> str:
    """UTM EPSG for the bbox centroid (northern hemisphere — Strait of Hormuz)."""
    lon = (bbox[0] + bbox[2]) / 2.0
    zone = int((lon + 180.0) / 6.0) + 1
    return f"EPSG:{32600 + zone}"


def read_window(settings: Settings, scene: Scene) -> Window | None:
    """Read the AOI window from a scene, georeferenced via GCPs to UTM.

    Returns None if the AOI falls outside the scene footprint.
    """
    dst_crs = _utm_epsg_for(settings.bbox)
    with rasterio.Env(**_GDAL_ENV):
        with rasterio.open(scene.asset_href) as src:
            with WarpedVRT(src, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
                aoi = transform_bounds("EPSG:4326", dst_crs, *settings.bbox)
                win = from_bounds(*aoi, transform=vrt.transform)
                win = win.intersection(RioWindow(0, 0, vrt.width, vrt.height))
                if win.width < 1 or win.height < 1:
                    return None

                data = vrt.read(1, window=win).astype("float32")
                win_transform = vrt.window_transform(win)
                nodata = vrt.nodata

    if nodata is not None:
        data[data == nodata] = np.nan
    data[data == 0] = np.nan  # GRD border fill is 0

    if not np.isfinite(data).any():
        return None  # window is entirely nodata (AOI off the imaged swath)

    return Window(amplitude=data, transform=win_transform, crs=dst_crs, scene=scene)
