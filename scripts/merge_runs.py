"""Merge parallel per-date detection runs into one multi-timestep artifact set.

Each parallel run wrote to artifacts/dt_<date>/ (its own detections.json + chips).
This combines them: concatenate detections, copy all chips into artifacts/chips/,
run the temporal-persistence filter across the full set (so islands/rigs recurring
across dates are flagged static), recompute per-date counts, fetch oil for all
dates, and write the final artifacts/{detections,timeseries,oil}.json.

Run: PYTHONPATH=src .venv/bin/python scripts/merge_runs.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from hormuz import artifacts, count, oil, persistence
from hormuz.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def main() -> None:
    part_files = sorted(ART.glob("dt_*/detections.json"))
    if not part_files:
        print("no per-date runs found (artifacts/dt_*/detections.json)")
        return

    detections: list[dict] = []
    scene_status: dict[str, str] = {}
    location = None
    bbox = None
    for pf in part_files:
        data = json.loads(pf.read_text())
        detections.extend(data["detections"])
        scene_status.update(data.get("scene_status", {}))
        location = location or data.get("location")
        bbox = bbox or data.get("bbox")
        print(f"  {pf.parent.name}: {data['count']} detections, "
              f"dates {list(data.get('scene_status', {}).keys())}")

    # Copy every part's chips into the unified artifacts/chips/.
    (ART / "chips").mkdir(parents=True, exist_ok=True)
    n_chips = 0
    for pf in part_files:
        for png in (pf.parent / "chips").glob("*.png"):
            shutil.copy2(png, ART / "chips" / png.name)
            n_chips += 1

    # Persistence filter across ALL dates, then counts.
    persist = persistence.tag_static(detections)

    # Label resolution: moving detections are vessels; recurring static features are
    # islands/rigs. (Human-verified for the demo; only un-labeled candidates are set.)
    for d in detections:
        if d.get("label", "unverified") == "unverified":
            d["label"] = "island" if d.get("is_static") else "vessel"

    series = count.vessel_timeseries(detections)
    oil_by_date = oil.prices_by_date(sorted(scene_status.keys()))

    settings = load_settings()
    dates = sorted(scene_status.keys())
    meta = {"location": location, "scene_status": scene_status, "persistence": persist}
    # Override bbox/start/end on the written file to reflect the merged set.
    path = ART / "detections.json"
    artifacts.write_json(path, {
        "bbox": bbox, "start": dates[0] if dates else settings.start,
        "end": dates[-1] if dates else settings.end,
        "collection": settings.collection, "count": len(detections),
        **meta, "detections": detections,
    })
    artifacts.write_timeseries(settings, series)
    artifacts.write_oil(settings, oil_by_date,
                        source="datahub.io core/oil-prices (ODC-PDDL; EIA spot prices)")

    print(f"\nMERGED: {len(detections)} detections across {persist['timesteps']} timesteps "
          f"({dates[0]}..{dates[-1]})")
    print(f"  static (island/rig): {persist['static_count']} | "
          f"moving (vessel est.): {persist['moving_count']} | chips: {n_chips}")
    print(f"  per-date: " + " | ".join(
        f"{s['date']}: {s['moving_count']}m/{s['static_count']}s" for s in series))


if __name__ == "__main__":
    main()
