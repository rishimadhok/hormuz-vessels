"""Chip extraction, SAR display stretch, and annotated scene overlays.

SAR amplitude has huge dynamic range, so we log-stretch between percentiles to a
uint8 image for both the PNG chips fed to Claude and the human-facing overlay.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

from .blobs import Candidate
from .fetch import Window

# Colours for the annotated overlay, keyed by Claude's verdict label.
LABEL_COLORS = {
    "vessel": (0, 220, 0),
    "rig": (255, 165, 0),
    "island": (80, 140, 255),
    "noise": (140, 140, 140),
}


def stretch_to_uint8(arr: np.ndarray, p_lo: float = 2.0, p_hi: float = 98.0) -> np.ndarray:
    """Log-stretch SAR amplitude between percentiles to a uint8 image."""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype="uint8")
    a = np.where(np.isfinite(arr), arr, 0.0)
    a = np.log1p(np.clip(a, 0, None))
    lo, hi = np.percentile(np.log1p(np.clip(finite, 0, None)), [p_lo, p_hi])
    if hi <= lo:
        hi = lo + 1.0
    norm = np.clip((a - lo) / (hi - lo), 0, 1)
    return (norm * 255).astype("uint8")


def extract_chip(window: Window, cand: Candidate, chip_px: int) -> np.ndarray:
    """Crop a square chip (amplitude) centred on the candidate, edge-clamped."""
    h, w = window.amplitude.shape
    half = chip_px // 2
    r0, r1 = max(cand.row - half, 0), min(cand.row + half, h)
    c0, c1 = max(cand.col - half, 0), min(cand.col + half, w)
    return window.amplitude[r0:r1, c0:c1]


def chip_png_bytes(chip_amplitude: np.ndarray, upscale: int = 4) -> bytes:
    """Render a chip to PNG bytes (upscaled so small chips are legible to vision)."""
    img = Image.fromarray(stretch_to_uint8(chip_amplitude)).convert("L")
    if upscale > 1:
        img = img.resize((img.width * upscale, img.height * upscale), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def chip_base64(chip_amplitude: np.ndarray) -> str:
    return base64.standard_b64encode(chip_png_bytes(chip_amplitude)).decode("ascii")


def save_chip(chip_amplitude: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(chip_png_bytes(chip_amplitude))


def render_overlay(
    window: Window,
    candidates: list[Candidate],
    verdicts: list[str],
    out_path: Path,
    *,
    title: str = "",
) -> None:
    """Full-scene PNG with the SAR backdrop and a coloured box per candidate.

    `verdicts[i]` is Claude's label for `candidates[i]` (or "" if unverified).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    base = stretch_to_uint8(window.amplitude)
    fig, ax = plt.subplots(figsize=(12, 12 * base.shape[0] / max(base.shape[1], 1)))
    ax.imshow(base, cmap="gray", origin="upper")
    ax.set_axis_off()
    if title:
        ax.set_title(title, color="black", fontsize=12)

    for cand, verdict in zip(candidates, verdicts):
        color = LABEL_COLORS.get(verdict, (255, 0, 0))
        minr, minc, maxr, maxc = cand.bbox
        pad = 6
        rect = mpatches.Rectangle(
            (minc - pad, minr - pad),
            (maxc - minc) + 2 * pad,
            (maxr - minr) + 2 * pad,
            linewidth=1.4,
            edgecolor=tuple(v / 255 for v in color),
            facecolor="none",
        )
        ax.add_patch(rect)

    # Legend of the labels actually present.
    present = [v for v in set(verdicts) if v in LABEL_COLORS]
    if present:
        handles = [
            mpatches.Patch(color=tuple(v / 255 for v in LABEL_COLORS[v]), label=v)
            for v in sorted(present)
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", dpi=130)
    plt.close(fig)
