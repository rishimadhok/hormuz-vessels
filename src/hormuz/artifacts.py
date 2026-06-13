"""Serialize pipeline results into the artifacts/ tree the web app consumes."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Settings


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def write_detections(
    settings: Settings, detections: list[dict], meta: dict | None = None
) -> Path:
    path = settings.artifacts_path / "detections.json"
    write_json(
        path,
        {
            "bbox": list(settings.bbox),
            "start": settings.start,
            "end": settings.end,
            "collection": settings.collection,
            "count": len(detections),
            **(meta or {}),
            "detections": detections,
        },
    )
    return path


def write_timeseries(settings: Settings, series: list[dict]) -> Path:
    path = settings.artifacts_path / "timeseries.json"
    write_json(path, {"series": series})
    return path


def write_oil(settings: Settings, by_date: dict, source: str) -> Path:
    path = settings.artifacts_path / "oil.json"
    write_json(path, {"source": source, "by_date": by_date,
                      "scene_dates": sorted(by_date.keys())})
    return path
