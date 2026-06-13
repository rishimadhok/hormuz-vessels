# Strait of Hormuz — Vessel Traffic Brief

**Period:** 2026-02-16 → 2026-06-04 · **Source:** Sentinel-1 GRD (C-band SAR) · **Verification:** Claude vision pass

> This is **sample** narrative for layout verification. The live pipeline overwrites
> `artifacts/brief.md` with the real generated brief.

## Summary

Across the observation window, verified vessel counts in the Strait held a seasonal
baseline of roughly **40–50 vessels per pass**, with two notable deviations. CFAR
detection consistently surfaced ~450–600 raw candidates per scene; the vision pass
relabels coastline and island leakage, isolating genuine maritime traffic.

## Key findings

- **Baseline traffic is stable.** Vessel counts cluster around the mid-40s on routine passes, consistent with normal tanker and cargo throughput.
- **Late-April dip.** Following the 2026-04-29 transit advisory, verified vessels fell to single digits for two passes before recovering — the clearest signal in the series.
- **March anomaly.** A short spike in vessels holding near the anchorage coincided with the 2026-03-24 seizure report.
- **False positives dominate raw counts.** The bulk of CFAR candidates are island/coast leakage and speckle; the vision step is what makes the count interpretable.

## Method notes

1. Detection: constant false-alarm-rate (CFAR) over Sentinel-1 intensity.
2. Verification: each strongest-N candidate chip classified by Claude as `vessel | rig | island | noise`.
3. Aggregation: verified `vessel` labels rolled up per pass into the traffic series.

## Caveats

- GRD amplitude only; no polarimetric decomposition.
- Island masking relies on Natural Earth 10m, which misses small mid-water features (relabeled by vision).
- Counts are per-pass snapshots, not continuous AIS-style tracking.
