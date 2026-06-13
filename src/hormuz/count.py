"""Aggregate verified detections into a per-acquisition-date vessel-count series."""

from __future__ import annotations

from collections import defaultdict


def vessel_timeseries(detections: list[dict]) -> list[dict]:
    """Collapse detection records into per-date vessel counts.

    A detection counts as a vessel only if Claude's verdict label == "vessel".
    Returns a list of {date, scene_count, candidate_count, vessel_count}, sorted.
    """
    by_date: dict[str, dict] = defaultdict(
        lambda: {"vessel_count": 0, "candidate_count": 0,
                 "static_count": 0, "moving_count": 0, "scenes": set()}
    )
    for det in detections:
        date = det["date"]
        rec = by_date[date]
        rec["candidate_count"] += 1
        rec["scenes"].add(det["scene_id"])
        if det.get("is_static"):
            rec["static_count"] += 1
        else:
            rec["moving_count"] += 1   # candidates that move = vessel estimate pre-verification
        if det.get("label") == "vessel":
            rec["vessel_count"] += 1

    series = [
        {
            "date": date,
            "scene_count": len(rec["scenes"]),
            "candidate_count": rec["candidate_count"],
            "static_count": rec["static_count"],
            "moving_count": rec["moving_count"],
            "vessel_count": rec["vessel_count"],
        }
        for date, rec in by_date.items()
    ]
    series.sort(key=lambda r: r["date"])
    return series
