# NOTES — failures & fixes

Running log. Newest at top.

## Phase 1 — vertical slice
- **PROVEN (criterion 3):** Opus 4.8 vision pass works end-to-end. On the Fujairah anchorage (56.45,25.05,56.70,25.35), 2026-04-03 S1C scene, the 6 strongest CFAR returns were all classified `vessel` (conf 0.70–0.88) with sound reasoning ("compact bright elongated target on dark open water"). Annotated overlay renders green vessel boxes + legend. Key loaded from `.env`.
- **POLISH (Phase 3):** the annotated overlay display stretch is speckle-grainy — a multilook/median pre-filter or a tuned percentile/gamma stretch would make ships pop for the demo. Functional, not blocking.
- **CLI:** `--bbox` takes a comma string `min_lon,min_lat,max_lon,max_lat` (Typer multi-value flags were awkward). Added `--max-candidates` to cap the paid vision pass per scene.

- **BUG (fixed):** `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"` in the GDAL env silently excluded the S1 GRD assets, which are `*.tiff`. Removed the extension filter → COG opens. *Lesson: don't restrict vsicurl extensions unless you've checked the asset suffix.*
- **BUG (fixed):** MPC `sentinel-1-grd` measurement TIFFs are in **radar/ground-range geometry with GCPs**, not a projected CRS — `src.crs` is `None`, no affine transform. (The plan's "GRD is UTM" assumption was wrong; that's true of RTC.) Fix: georeference on read with a `WarpedVRT(src, crs=<UTM>)`, then window the VRT. UTM target (zone 40N for Hormuz) keeps pixels ~10 m and square for CFAR.
- **FINDING:** First slice on the full-Strait bbox yielded 465 candidates in one scene. Area distribution (median 16 px, no 1-px blobs) shows these are real bright multi-pixel returns, not speckle — a mix of genuine anchorage/lane traffic, plus leakage on bright coastline and small mid-water islands that Natural Earth 10m doesn't mask. Two consequences: (1) island/coast leakage is exactly what the Opus vision pass is there to relabel; (2) 465 chips/scene is too many to verify economically.
- **DECISION:** Added `max_candidates_per_scene` (verify the strongest-N by max intensity, **logged** when capping — no silent truncation). Higher-fidelity island masking (OSM polygons) deferred to Phase 3 per the build order.

## Setup
- Recreated `./.venv` on Python 3.12.13 (was macOS system 3.9.6) to avoid PyTorch/geo-stack wheel friction.
- Data source decision: MPC `sentinel-1-grd` (NOT `sentinel-1-rtc`). RTC carries `msft:requires_account: true` and cannot be signed anonymously — would break the no-credentials constraint. GRD is amplitude DN; CFAR runs on intensity (= amplitude²), which is fine because CFAR is a relative local-contrast test.
- `ANTHROPIC_API_KEY` not present in the build shell — verify/brief steps read it from env (`.env` fallback supported). Must be exported before Phase-1 vision runs.
