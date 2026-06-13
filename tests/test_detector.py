"""Integration tests for the CFAR vessel detector against real Sentinel-1 scenes.

These tests exercise the actual detection pipeline (search -> read window ->
sea mask -> CFAR -> candidate extraction) on real Microsoft Planetary Computer
imagery, using *geographic* labels rather than per-pixel ground truth:

  * Over an open-water shipping lane in the Strait of Hormuz the detector must
    find a meaningful number of vessel candidates.
  * Over a land-only interior (Qeshm Island), the land mask must suppress
    detections down to ~zero. This proves the mask works and that CFAR is not
    simply firing everywhere.

They hit the network (MPC) and download Natural Earth land polygons on first
run, so they are marked ``network`` and skip cleanly (rather than fail) when no
scene is available -- e.g. CI without network access.

Run:  ./.venv/bin/pytest tests/test_detector.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from hormuz.blobs import extract_candidates
from hormuz.cfar import cfar_detect
from hormuz.config import load_settings
from hormuz.fetch import read_window
from hormuz.landmask import build_sea_mask
from hormuz.search import search_scenes

# A 30-day window in spring 2026: wide enough that the ~weekly Sentinel-1
# revisit reliably yields multiple IW/VH scenes over the strait.
START = "2026-04-01"
END = "2026-04-30"

# Open water packed with ships: the Fujairah / Gulf-of-Oman tanker anchorage at
# the southern mouth of the Strait of Hormuz -- one of the busiest anchorages in
# the world, routinely crowded with tankers, and entirely sea (100% sea mask).
WATER_BBOX = (56.45, 25.05, 56.70, 25.35)

# Land-only box well inside Qeshm Island, away from the coast so coastline
# returns can't leak in. Qeshm interior is arid land -> the sea mask should be
# (almost) entirely False here.
LAND_BBOX = (55.85, 26.78, 55.95, 26.86)

# A few scenes are searched (cheap) and the first window with substantial valid
# data is used: a given orbit can clip the AOI's edge and read mostly nodata.
_MAX_SCENES = 5
_MIN_FINITE_FRACTION = 0.8


def _run_pipeline(bbox: tuple[float, float, float, float]):
    """Run search -> read -> mask -> CFAR -> candidates for one AOI.

    Searches up to ``_MAX_SCENES`` and uses the first window whose AOI is mostly
    inside the imaged swath (so an edge-clipped, mostly-nodata read can't
    masquerade as an empty scene). Returns ``(candidates, sea_fraction)`` or
    ``None`` if no usable scene/window was found (caller should ``pytest.skip``).
    """
    settings = load_settings(bbox=bbox, start=START, end=END, max_scenes=_MAX_SCENES)

    scenes = search_scenes(settings)
    if not scenes:
        return None

    window = None
    for scene in scenes:
        w = read_window(settings, scene)
        if w is None:
            continue
        if np.isfinite(w.amplitude).mean() >= _MIN_FINITE_FRACTION:
            window = w
            break
    if window is None:
        return None

    sea_mask = build_sea_mask(window, settings)
    det = cfar_detect(window.intensity, settings.cfar)
    det &= sea_mask  # apply the sea mask exactly as the pipeline does

    candidates = extract_candidates(det, window, settings.cfar)
    sea_fraction = float(np.count_nonzero(sea_mask)) / sea_mask.size
    return candidates, sea_fraction


@pytest.mark.network
def test_cfar_finds_vessels_in_shipping_lane():
    """Open-water shipping lane: CFAR should find several vessel candidates."""
    result = _run_pipeline(WATER_BBOX)
    if result is None:
        pytest.skip(
            "No Sentinel-1 scene/window available for the water AOI "
            f"({WATER_BBOX}) in {START}..{END} -- network unavailable or no "
            "scene this window."
        )
    candidates, sea_fraction = result

    # The water AOI must actually be (mostly) sea, or the test isn't testing
    # what it claims to.
    assert sea_fraction > 0.5, (
        f"water AOI was only {sea_fraction:.0%} sea; pick a more open-water bbox"
    )

    assert len(candidates) >= 5, (
        f"expected >= 5 vessel candidates in the shipping lane, got "
        f"{len(candidates)}"
    )


@pytest.mark.network
def test_landmask_suppresses_detections_over_land():
    """Land-only interior: the sea mask should drive candidates to ~zero."""
    result = _run_pipeline(LAND_BBOX)
    if result is None:
        pytest.skip(
            "No Sentinel-1 scene/window available for the land AOI "
            f"({LAND_BBOX}) in {START}..{END} -- network unavailable or no "
            "scene this window."
        )
    candidates, sea_fraction = result

    # Sanity: the AOI really is (almost) all land, so masking is what's being
    # exercised here.
    assert sea_fraction < 0.2, (
        f"land AOI was {sea_fraction:.0%} sea -- pick a more interior bbox so "
        "the test actually exercises land masking"
    )

    assert len(candidates) <= 2, (
        f"expected ~0 candidates over masked land, got {len(candidates)}; "
        "land masking may be failing"
    )
