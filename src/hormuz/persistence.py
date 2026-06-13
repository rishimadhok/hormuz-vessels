"""Temporal-persistence filter: flag detections that recur at the same location
across multiple acquisition dates as STATIC (island / fixed rig / platform).

Rationale: vessels move between Sentinel-1 passes (days apart), so a real ship
will not reappear at the same coordinates on multiple dates. A bright return that
shows up at (approximately) the same spot on several passes is a fixed feature.

Approach: bin detections into a ~100 m lon/lat grid; for each detection, count the
number of DISTINCT dates present in its cell and the 8 neighbouring cells (so a
feature whose centroid jitters across a cell boundary still matches). If that count
meets a threshold (a fraction of the available timesteps), mark it static.
"""

from __future__ import annotations

import math
from collections import defaultdict

# ~100 m cells at the Strait's latitude (1e-3 deg lat ~= 111 m).
_CELL_DEG = 0.001


def _cell(lon: float, lat: float) -> tuple[int, int]:
    return (round(lon / _CELL_DEG), round(lat / _CELL_DEG))


def tag_static(detections: list[dict], *, min_fraction: float = 0.6) -> dict:
    """Annotate each detection in place with `is_static` and `persistence_dates`.

    Returns a summary dict. A detection is static when the same ~100 m location is
    occupied on at least `min_dates` distinct dates, where
    `min_dates = max(2, ceil(min_fraction * n_timesteps))` and there are >= 2 dates.
    With a single timestep nothing can be judged static.
    """
    dates = sorted({d["date"] for d in detections})
    n = len(dates)

    # Cell -> set of dates present in that cell.
    cell_dates: dict[tuple[int, int], set[str]] = defaultdict(set)
    for d in detections:
        cell_dates[_cell(d["lon"], d["lat"])].add(d["date"])

    def neighbourhood_dates(cell: tuple[int, int]) -> set[str]:
        cx, cy = cell
        out: set[str] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out |= cell_dates.get((cx + dx, cy + dy), set())
        return out

    min_dates = max(2, math.ceil(min_fraction * n))
    static_count = 0
    for d in detections:
        nd = neighbourhood_dates(_cell(d["lon"], d["lat"]))
        d["persistence_dates"] = len(nd)
        d["is_static"] = (n >= 2) and (len(nd) >= min_dates)
        if d["is_static"]:
            static_count += 1

    return {
        "timesteps": n,
        "dates": dates,
        "min_dates_for_static": min_dates if n >= 2 else None,
        "static_count": static_count,
        "moving_count": len(detections) - static_count,
    }
