"""Geographic + temporal context for a scene.

- describe_location(bbox): a human-readable place for the AOI centroid.
- strait_status_on(date): was the Strait open/closed/disrupted on a date, per the
  human-curated data/timeline.json (so the demo can say "this image is from during
  the closure").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Known sub-regions of the Strait, matched by AOI centroid. (min_lon,min_lat,max_lon,max_lat)
_REGIONS = [
    ((56.2, 24.8, 57.0, 25.6),
     "Fujairah anchorage, Gulf of Oman — the southern approach to the Strait of Hormuz "
     "(major bunkering/anchorage hub where vessels wait outside the strait)"),
    ((56.0, 26.3, 56.8, 27.0),
     "Strait of Hormuz transit corridor — the narrowest point, between Oman's Musandam "
     "peninsula and the Iranian coast"),
    ((55.3, 26.8, 56.6, 27.4),
     "Bandar Abbas / Qeshm Island approaches — the northern Strait, along the Iranian coast"),
]


def describe_location(bbox: tuple[float, float, float, float]) -> dict:
    """Return {region, lat, lon} for the AOI centroid."""
    lon = (bbox[0] + bbox[2]) / 2.0
    lat = (bbox[1] + bbox[3]) / 2.0
    region = None
    for (mnx, mny, mxx, mxy), name in _REGIONS:
        if mnx <= lon <= mxx and mny <= lat <= mxy:
            region = name
            break
    if region is None:
        region = "Strait of Hormuz region"
    return {"region": region, "lat": round(lat, 3), "lon": round(lon, 3)}


@dataclass
class StraitStatus:
    status: str          # "Open" | "Disrupted" | "Closed" | "Open (pre-crisis)"
    as_of: str           # date of the governing event
    basis: str           # title of the most recent event on/before the date
    note: str


_TIMELINE = Path("data/timeline.json")

# How each timeline event type moves the open/closed baseline.
_CLOSE = {"closure", "partial_closure"}
_OPEN = {"reopen"}
_EASE = {"deescalation"}
_DISRUPT = {"disruption", "escalation", "incident"}


def strait_status_on(date: str, timeline_path: Path = _TIMELINE) -> StraitStatus:
    """Infer the Strait's open/closed status on `date` from the curated timeline."""
    if not timeline_path.exists():
        return StraitStatus("Unknown", "", "no timeline.json", "")
    events = sorted(json.loads(timeline_path.read_text()).get("events", []),
                    key=lambda e: e["date"])
    prior = [e for e in events if e["date"] <= date]
    if not prior:
        return StraitStatus("Open (pre-crisis)", "", "before first recorded event",
                            "No disruption recorded on/before this date.")

    state = "Open"
    disrupted = False
    for e in prior:
        t = e.get("type", "")
        if t in _CLOSE:
            state, disrupted = "Closed", False
        elif t in _OPEN:
            state, disrupted = "Open", False
        elif t in _EASE:
            state = "Open (partial)"
        elif t in _DISRUPT and state == "Open":
            disrupted = True

    if state == "Open" and disrupted:
        state = "Disrupted"
    last = prior[-1]
    return StraitStatus(
        status=state,
        as_of=last["date"],
        basis=last.get("title", ""),
        note=f"Most recent event on/before {date}: {last['date']} — {last.get('title','')}.",
    )
