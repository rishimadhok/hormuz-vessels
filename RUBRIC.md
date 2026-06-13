# RUBRIC — Strait of Hormuz Vessel Detection

The 7 done-criteria. Each must be checkable and verified by a fresh subagent after the relevant phase.

- [ ] **1. Reproducible acquisition.** Given a bbox over the Strait of Hormuz + a date range, the pipeline pulls free Sentinel-1 SAR scenes for those dates from Microsoft Planetary Computer (`sentinel-1-grd`, anonymous/no credentials).
- [ ] **2. Classical ship detection.** CFAR-style adaptive thresholding on Sentinel-1 GRD VH (with VV available), with land/island masking so static features (coast, islands) are not counted.
- [ ] **3. Opus 4.8 vision verification.** Each candidate image chip is sent to Claude (`claude-opus-4-8`) and classified vessel / island / rig / noise. Final counts are model-verified, not threshold-only.
- [ ] **4. Time series.** Vessel counts across the date range, overlaid on the known open/closed timeline.
- [ ] **5. Analyst brief.** An Opus 4.8-generated, plain-English "what this means for a trader" readout from the traffic curve + closure timeline (+ oil prices if available).
- [ ] **6. Deployed web app.** Live public URL showing: detection+verification on a sample SAR scene (ships highlighted with Claude's call on each), the traffic chart, and the analyst brief. Leads with detection, not the chart.
- [ ] **7. Public repo + README.** Another team can rerun on a new bbox/date range with one command.

## Constraints (must hold throughout)
- Free, openly-licensed data only (Sentinel-1/2, public oil-price series).
- Product is the detection+analysis pipeline, NOT a dashboard. Demo leads with the model detecting ships.
- Deployable on a free tier (Vercel). Detections pre-computed; the web app serves results.
