"""End-to-end orchestration: the one function the CLI and tests call.

search -> (per scene) fetch -> landmask -> cfar -> blobs -> chips -> verify
      -> accumulate -> count -> artifacts (detections.json, timeseries.json,
         annotated overlay PNGs).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import artifacts, context, count, oil, persistence
from .blobs import extract_candidates
from .cfar import cfar_detect
from .chips import extract_chip, render_overlay, save_chip
from .config import Settings
from .fetch import read_window
from .landmask import build_sea_mask
from .search import search_scenes
from .verify import Verdict, _client, verify_candidate


@dataclass
class PipelineResult:
    detections: list[dict]
    timeseries: list[dict]
    scenes_processed: int


def run(settings: Settings, *, verify: bool = True, log=print) -> PipelineResult:
    """Run the full pipeline and write artifacts. Returns the in-memory result."""
    scenes = search_scenes(settings)
    location = context.describe_location(settings.bbox)
    log(f"[search] {len(scenes)} scene(s) over AOI {settings.bbox} "
        f"{settings.start}..{settings.end}")
    log(f"[location] {location['region']} (centroid {location['lat']},{location['lon']})")

    client = _client() if verify else None
    detections: list[dict] = []
    scene_status: dict[str, str] = {}
    scenes_processed = 0

    for scene in scenes:
        window = read_window(settings, scene)
        if window is None:
            log(f"[fetch] {scene.item_id}: AOI not in scene footprint, skipping")
            continue

        status = context.strait_status_on(scene.date)
        scene_status[scene.date] = status.status

        sea_mask = build_sea_mask(window, settings)
        det_mask = cfar_detect(window.intensity, settings.cfar) & sea_mask
        candidates = extract_candidates(det_mask, window, settings.cfar)
        n_found = len(candidates)

        cap = settings.max_candidates_per_scene
        if cap is not None and n_found > cap:
            candidates = sorted(candidates, key=lambda c: c.max_intensity, reverse=True)[:cap]
            log(f"[detect] {scene.date} {scene.item_id}: {n_found} candidate(s); "
                f"verifying strongest {cap} (cap)")
        else:
            log(f"[detect] {scene.date} {scene.item_id}: {n_found} candidate(s)")

        verdicts: list[str] = []
        for i, cand in enumerate(candidates):
            chip = extract_chip(window, cand, settings.chip_px)
            chip_path = settings.chips_path / f"{scene.item_id}_{i:03d}.png"
            save_chip(chip, chip_path)

            if verify and client is not None:
                v: Verdict = verify_candidate(client, window, cand, chip, settings)
                label, confidence, reasoning = v.label, v.confidence, v.reasoning
            else:
                label, confidence, reasoning = "unverified", 0.0, ""
            verdicts.append(label)

            detections.append(
                {
                    "scene_id": scene.item_id,
                    "date": scene.date,
                    "datetime": scene.datetime,
                    "lon": cand.lon,
                    "lat": cand.lat,
                    "bbox_geo": list(cand.bbox_geo),
                    "area_px": cand.area_px,
                    "max_intensity": cand.max_intensity,
                    "label": label,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "status": status.status,
                    "chip": str(chip_path.relative_to(settings.artifacts_path)),
                }
            )

        overlay = settings.artifacts_path / "chips" / f"{scene.item_id}_overlay.png"
        short_region = location["region"].split(" — ")[0]
        render_overlay(
            window, candidates, verdicts, overlay,
            title=f"{scene.date}  |  {short_region}  |  Strait: {status.status}",
        )
        log(f"[render] {overlay}")
        scenes_processed += 1

    # Temporal-persistence filter: flag detections recurring at the same spot across
    # passes as static (island / fixed rig), so they're excluded from vessel counts.
    persist = persistence.tag_static(detections)
    log(f"[persistence] {persist['timesteps']} timestep(s); "
        f"{persist['static_count']} static (island/rig), {persist['moving_count']} moving")

    # Label resolution for un-verified candidates: moving = vessel, static = island.
    for d in detections:
        if d.get("label", "unverified") == "unverified":
            d["label"] = "island" if d.get("is_static") else "vessel"

    series = count.vessel_timeseries(detections)
    meta = {"location": location, "scene_status": scene_status, "persistence": persist}
    artifacts.write_detections(settings, detections, meta=meta)
    artifacts.write_timeseries(settings, series)

    # Oil prices for the acquisition dates (best-effort; empty if source unreachable).
    oil_by_date = oil.prices_by_date(sorted(scene_status.keys()))
    artifacts.write_oil(settings, oil_by_date,
                        source="datahub.io core/oil-prices (ODC-PDDL; EIA spot prices)")
    if oil_by_date:
        log(f"[oil] {oil_by_date}")
    log(f"[done] {len(detections)} detection(s) across {scenes_processed} scene(s); "
        f"artifacts in {settings.artifacts_dir}/")

    return PipelineResult(detections, series, scenes_processed)
