"""Turn a CFAR detection mask into vessel candidates with geolocation.

Connected-component labelling + region properties, filtered by area to drop
speckle and very large land-leakage blobs. Pixel centroids are converted to
lon/lat via the window's affine transform and the scene CRS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from scipy.ndimage import label
from skimage.measure import regionprops

from .config import CFARConfig
from .fetch import Window


@dataclass
class Candidate:
    """A CFAR vessel candidate in one scene."""

    lon: float
    lat: float
    row: int                 # centroid row in the window
    col: int                 # centroid col in the window
    bbox: tuple[int, int, int, int]   # (min_row, min_col, max_row, max_col)
    area_px: int
    max_intensity: float
    # (min_lon, min_lat, max_lon, max_lat); default for manually-built candidates
    bbox_geo: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def extract_candidates(
    detection: np.ndarray, window: Window, cfg: CFARConfig
) -> list[Candidate]:
    """Label the detection mask and return geolocated, area-filtered candidates."""
    labels, n = label(detection)
    if n == 0:
        return []

    to_lonlat = Transformer.from_crs(window.crs, "EPSG:4326", always_xy=True)
    intensity = window.intensity

    out: list[Candidate] = []
    for prop in regionprops(labels, intensity_image=intensity):
        if prop.area < cfg.min_area_px or prop.area > cfg.max_area_px:
            continue
        r, c = prop.centroid
        x, y = window.transform * (c, r)          # pixel -> scene CRS (UTM)
        lon, lat = to_lonlat.transform(x, y)       # scene CRS -> lon/lat
        minr, minc, maxr, maxc = prop.bbox

        # Geographic bbox: project all four pixel corners, take lon/lat extents.
        corners_px = [(minc, minr), (maxc, minr), (minc, maxr), (maxc, maxr)]
        lons, lats = [], []
        for cc, rr in corners_px:
            ux, uy = window.transform * (cc, rr)
            clon, clat = to_lonlat.transform(ux, uy)
            lons.append(clon)
            lats.append(clat)

        out.append(
            Candidate(
                lon=float(lon),
                lat=float(lat),
                row=int(round(r)),
                col=int(round(c)),
                bbox=(minr, minc, maxr, maxc),
                area_px=int(prop.area),
                max_intensity=float(np.nan_to_num(prop.intensity_max)),
                bbox_geo=(float(min(lons)), float(min(lats)),
                          float(max(lons)), float(max(lats))),
            )
        )
    return out
