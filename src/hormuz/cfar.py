"""Cell-Averaging CFAR (CA-CFAR) ship detection on Sentinel-1 VH intensity.

Sea clutter on VH at IW/~10 m is well-modelled as exponential, so CA-CFAR is the
standard, defensible detector. Vectorised with uniform_filter (no per-pixel loop):
estimate the local background mean from a ring of training cells (outer box minus
guard box), then threshold each cell at `mean * alpha`.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

from .config import CFARConfig


def _nan_uniform_mean(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Box-sum and box-count of finite values over a `size`x`size` window."""
    finite = np.isfinite(x)
    filled = np.where(finite, x, 0.0)
    # uniform_filter returns the mean; multiply by area to recover the sum.
    area = size * size
    box_sum = uniform_filter(filled, size=size, mode="nearest") * area
    box_cnt = uniform_filter(finite.astype("float32"), size=size, mode="nearest") * area
    return box_sum, box_cnt


def cfar_detect(intensity: np.ndarray, cfg: CFARConfig) -> np.ndarray:
    """Return a boolean detection mask the same shape as `intensity`.

    `intensity` may contain NaN (nodata / land border); those cells never detect.
    """
    o, g = cfg.bg_px, cfg.guard_px

    outer_sum, outer_cnt = _nan_uniform_mean(intensity, o)
    guard_sum, guard_cnt = _nan_uniform_mean(intensity, g)

    # Ring (training) statistics = outer box minus the inner guard box.
    ring_sum = outer_sum - guard_sum
    ring_cnt = outer_cnt - guard_cnt

    with np.errstate(invalid="ignore", divide="ignore"):
        ring_mean = np.where(ring_cnt > 0, ring_sum / ring_cnt, np.nan)

    # CA-CFAR multiplier for exponential clutter:
    #   alpha = N * (Pfa^(-1/N) - 1),  N = number of training cells.
    n = max(int(round(np.nanmedian(ring_cnt))), 1)
    alpha = n * (cfg.pfa ** (-1.0 / n) - 1.0)

    threshold = ring_mean * alpha
    det = np.isfinite(intensity) & np.isfinite(threshold) & (intensity > threshold)
    return det
