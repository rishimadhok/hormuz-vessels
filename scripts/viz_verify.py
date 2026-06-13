"""Generate verification visuals from existing artifacts (no new Opus calls).

1) artifacts/viz_detections.png — the verified scene re-fetched, with each saved
   Opus verdict re-projected from lon/lat to pixels and drawn as a coloured marker.
2) artifacts/viz_timeline.png — the closure/disruption timeline from data/timeline.json.

Run: ./.venv/bin/python scripts/viz_verify.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from pyproj import Transformer

from hormuz.chips import LABEL_COLORS, stretch_to_uint8
from hormuz.config import load_settings
from hormuz.fetch import read_window
from hormuz.search import search_scenes

ART = Path("artifacts")


def viz_detections() -> None:
    det = json.loads((ART / "detections.json").read_text())
    detections = det["detections"]
    if not detections:
        print("no detections to plot")
        return
    scene_id = detections[0]["scene_id"]

    # Re-fetch the verified scene's window (the run used the Fujairah anchorage bbox).
    settings = load_settings(
        bbox=(56.45, 25.05, 56.70, 25.35), start="2026-04-01", end="2026-04-30",
        max_scenes=5,
    )
    scene = next((s for s in search_scenes(settings) if s.item_id == scene_id), None)
    if scene is None:
        print(f"could not re-find scene {scene_id}")
        return
    window = read_window(settings, scene)
    if window is None:
        print("window fetch returned None")
        return

    to_utm = Transformer.from_crs("EPSG:4326", window.crs, always_xy=True)
    inv = ~window.transform

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(stretch_to_uint8(window.amplitude), cmap="gray", origin="upper")
    ax.set_axis_off()
    ax.set_title(f"Verified detections — {scene.date}  {scene_id}", fontsize=11)

    for d in detections:
        x, y = to_utm.transform(d["lon"], d["lat"])
        col, row = inv * (x, y)
        color = tuple(v / 255 for v in LABEL_COLORS.get(d["label"], (255, 0, 0)))
        ax.add_patch(mpatches.Circle((col, row), radius=12, fill=False,
                                     edgecolor=color, linewidth=1.8))
        ax.text(col + 14, row, f"{d['label']} {d['confidence']:.2f}",
                color=color, fontsize=8, va="center")

    labels_present = sorted({d["label"] for d in detections})
    ax.legend(handles=[mpatches.Patch(color=tuple(v / 255 for v in LABEL_COLORS[l]), label=l)
                       for l in labels_present if l in LABEL_COLORS],
              loc="upper right", fontsize=9, framealpha=0.85)
    fig.savefig(ART / "viz_detections.png", bbox_inches="tight", dpi=130)
    plt.close(fig)
    print(f"wrote {ART/'viz_detections.png'}  ({len(detections)} detections)")


def viz_timeline() -> None:
    tl = json.loads(Path("data/timeline.json").read_text())
    events = tl.get("events", [])
    if not events:
        print("no timeline events")
        return

    type_color = {
        "escalation": "#d62728", "closure": "#000000", "partial_closure": "#7f3f3f",
        "disruption": "#ff7f0e", "incident": "#9467bd", "reopen": "#2ca02c",
        "deescalation": "#1f77b4",
    }
    dates = [datetime.fromisoformat(e["date"]) for e in events]
    fig, ax = plt.subplots(figsize=(13, 5.5))
    levels = np.tile([1, -1, 2, -2, 3, -3], len(events))[: len(events)]
    ax.vlines(dates, 0, levels, color="lightgray", lw=1)
    for d, lev, e in zip(dates, levels, events):
        c = type_color.get(e["type"], "#555555")
        ax.plot(d, lev, "o", color=c, markersize=7)
        ax.annotate(f"{e['date']}  {e['title']}", (d, lev),
                    xytext=(6, 6 if lev > 0 else -12), textcoords="offset points",
                    fontsize=7.5, color=c, rotation=0)
    ax.axhline(0, color="black", lw=1)
    ax.set_title("Strait of Hormuz — disruption/closure timeline (human-verification pending)",
                 fontsize=12)
    ax.get_yaxis().set_visible(False)
    for s in ["left", "right", "top"]:
        ax.spines[s].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    handles = [mpatches.Patch(color=c, label=t) for t, c in type_color.items()]
    ax.legend(handles=handles, loc="lower center", ncol=4, fontsize=8, framealpha=0.8)
    fig.autofmt_xdate()
    fig.savefig(ART / "viz_timeline.png", bbox_inches="tight", dpi=130)
    plt.close(fig)
    print(f"wrote {ART/'viz_timeline.png'}  ({len(events)} events)")


if __name__ == "__main__":
    ART.mkdir(exist_ok=True)
    viz_timeline()
    viz_detections()
