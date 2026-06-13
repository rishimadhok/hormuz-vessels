"""Regenerate the verified scene's overlay + chips (no Opus calls) and stage just
those verified artifacts into web/public/ for local hosting / a clean demo.

Run: ./.venv/bin/python scripts/stage_web.py
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from pyproj import Transformer

from hormuz.blobs import Candidate
from hormuz.chips import extract_chip, render_overlay, save_chip
from hormuz.config import load_settings
from hormuz.fetch import read_window
from hormuz.search import search_scenes

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
WEB = ROOT / "web" / "public"


def regenerate_verified_scene() -> str:
    det = json.loads((ART / "detections.json").read_text())
    detections = det["detections"]
    scene_id = detections[0]["scene_id"]

    settings = load_settings(
        bbox=(56.45, 25.05, 56.70, 25.35), start="2026-04-01", end="2026-04-30",
        max_scenes=5,
    )
    scene = next(s for s in search_scenes(settings) if s.item_id == scene_id)
    window = read_window(settings, scene)
    assert window is not None

    to_utm = Transformer.from_crs("EPSG:4326", window.crs, always_xy=True)
    inv = ~window.transform

    cands, verdicts = [], []
    for i, d in enumerate(detections):
        x, y = to_utm.transform(d["lon"], d["lat"])
        col, row = inv * (x, y)
        col, row = int(round(col)), int(round(row))
        side = max(int(round(math.sqrt(d["area_px"]))), 4)
        h = side // 2
        cand = Candidate(
            lon=d["lon"], lat=d["lat"], row=row, col=col,
            bbox=(row - h, col - h, row + h, col + h),
            area_px=d["area_px"], max_intensity=d["max_intensity"],
        )
        cands.append(cand)
        verdicts.append(d["label"])
        save_chip(extract_chip(window, cand, settings.chip_px),
                  ART / "chips" / f"{scene_id}_{i:03d}.png")

    render_overlay(window, cands, verdicts, ART / "chips" / f"{scene_id}_overlay.png",
                   title=f"{scene.date}  {scene_id}")
    print(f"regenerated overlay + {len(cands)} chips for {scene_id}")
    return scene_id


def stage(scene_id: str) -> None:
    (WEB / "artifacts" / "chips").mkdir(parents=True, exist_ok=True)
    (WEB / "data").mkdir(parents=True, exist_ok=True)

    for f in ["detections.json", "timeseries.json", "brief.md", "oil.json"]:
        src = ART / f
        if src.exists():
            shutil.copy2(src, WEB / "artifacts" / f)
    for f in ("timeline.json", "news.json"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, WEB / "data" / f)
    # also expose coverage.json to the frontend
    if (ART / "coverage.json").exists():
        shutil.copy2(ART / "coverage.json", WEB / "artifacts" / "coverage.json")

    # Copy chips for EVERY scene present in detections.json (multi-timestep safe),
    # not just the hero scene — the map's per-date popups need them all.
    det = json.loads((ART / "detections.json").read_text())
    scene_ids = {d["scene_id"] for d in det["detections"]}
    dest_chips = WEB / "artifacts" / "chips"
    # Clear stale chips so old runs don't linger.
    for old in dest_chips.glob("*.png"):
        old.unlink()
    n = 0
    for sid in scene_ids:
        for png in ART.glob(f"chips/{sid}_*.png"):
            shutil.copy2(png, dest_chips / png.name)
            n += 1
    print(f"staged {n} chips for {len(scene_ids)} scene(s) -> {WEB}")


def main() -> None:
    det = json.loads((ART / "detections.json").read_text())
    scene_id = det["detections"][0]["scene_id"]
    overlay = ART / "chips" / f"{scene_id}_overlay.png"
    # If the pipeline already produced the overlay+chips for this scene, just stage
    # them; otherwise regenerate from saved verdicts (no Opus calls).
    if overlay.exists():
        print(f"using pipeline-produced overlay for {scene_id}")
    else:
        scene_id = regenerate_verified_scene()
    stage(scene_id)


if __name__ == "__main__":
    main()
