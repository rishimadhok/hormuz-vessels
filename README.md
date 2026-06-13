# Strait of Hormuz — Vessel-Traffic Detection from Sentinel-1 SAR

**Live demo:** https://hormuz-vessels-demo.vercel.app

A **multi-intelligence platform** for the Strait of Hormuz that fuses three open signals
into one trader-facing view: **satellite** (detected vessel traffic), **market** (Brent/WTI
crude), and **news/OSINT** (sourced closure headlines). Built for oil/commodity desks who
want an independent, imagery-grounded read on whether ships are actually moving through the
chokepoint — not rumor.

## One-command rerun

```bash
pip install -e .                              # into a Python 3.12 venv at ./.venv
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env    # only needed for the analyst brief
./run_all.sh "56.0,26.2,56.9,26.9" 2026-01-09 2026-06-11
```

That runs the whole pipeline on the given bbox + date range — detect → temporal-persistence
filter → coverage normalization → news feed → Opus analyst brief → stage web artifacts —
and prints how to preview (`cd web/public && python -m http.server 8765`) or deploy
(`cd web/public && vercel deploy --prod`). Sentinel-1 needs **no credentials**; only the
optional brief step uses an Anthropic key.

## What it does

- **Detect** — pulls free **Sentinel-1 SAR** GRD from the Microsoft Planetary Computer
  (anonymous), runs a classical **CA-CFAR** ship detector on VH backscatter with
  land/island masking. No credentials.
- **Filter fixed features** — a **temporal-persistence** test flags returns that recur at
  the same coordinates across passes (islands / rigs) and excludes them from vessel counts;
  vessels move, fixed features don't.
- **Normalize for credibility** — reports per-date **imaged coverage %** and
  coverage-normalized vessel **density**, so an open-vs-closed traffic drop can't be a
  coverage artifact.
- **Verify** — two options: a **human verification portal** (`/verify.html`, label every
  candidate by eye, no API) or an optional **Opus 4.8 vision** pass (`hormuz run` without
  `--no-verify`) classifying each chip vessel/island/rig/noise.
- **Correlate** — a **time series** of moving-vessel counts across the date range overlaid
  on the open/closed timeline and **Brent crude**, plus a **news/OSINT feed** of sourced
  headlines aligned to the price.
- **Brief** — an **Opus 4.8 analyst brief** turning the curve + timeline + oil into a
  plain-English trading readout, explicit about provenance and caveats.

The web app is static (Vercel-deployable, no backend) and serves pre-computed artifacts:
the home page (detection → traffic+price chart → news → brief), a satellite **map**
(`/map.html`, date-stepper, moving vs static, per-date oil) and the **verify** portal.

## How it works

```
  hormuz run
      │
      ▼
  search ──────────  Microsoft Planetary Computer STAC, collection
   (search.py)       sentinel-1-grd (IW mode), anonymous / no credentials
      │
      ▼
  windowed fetch ──  S1 GRD measurement TIFFs are radar/ground-range with GCPs
   (fetch.py)        (no projected CRS). Georeference on read via WarpedVRT → UTM
                     (zone 40N), then window the VRT to the AOI. ~10 m square px.
      │
      ▼
  land mask ───────  Natural Earth 10m land + minor-islands (downloaded once to
   (landmask.py)     data/land/), rasterized + dilated → sea mask
      │
      ▼
  CA-CFAR ─────────  adaptive threshold on VH intensity (= amplitude²),
   (cfar.py)         guard/background windows, target PFA
      │
      ▼
  blobs ───────────  connected components, area-filtered (min/max px) → candidates
   (blobs.py)
      │
      ▼
  chips ───────────  64 px chip per candidate; annotated scene overlay
   (chips.py)
      │
      ▼
  Opus 4.8 verify ─  each chip classified vessel / island / rig / noise
   (verify.py)       with confidence + rationale (Message Batches API)
      │
      ▼
  counts ──────────  per-date vessel counts (label == "vessel")
   (count.py)
      │
      ▼
  artifacts ───────  detections.json, timeseries.json, chips/*.png
   (artifacts.py)
      │
      ▼
  static web app ──  web/ serves the artifacts (detection → chart → brief)
```

The known open/closed corridor timeline (`data/timeline.json`) and an Opus 4.8 analyst
brief overlay the traffic curve in the web app. Oil prices (`oil.py`) are an optional
"if available" input pulled from a free open dataset.

## Setup

Requires **Python 3.12+**.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs the `hormuz` package and the `hormuz` console command (see
`pyproject.toml`). Dependencies are pinned in `requirements.txt`.

### Credentials

- **Microsoft Planetary Computer needs NO credentials.** The `sentinel-1-grd`
  collection is signed anonymously.
- **The Claude vision verification and analyst brief require an Anthropic API key.**
  Put it in a `.env` file at the repo root (already gitignored):

  ```
  ANTHROPIC_API_KEY=sk-ant-...
  ```

  The pipeline reads the key from the environment / `.env`. If you only want the
  classical detection (no paid vision pass), run with `--no-verify` and no key is
  needed.

## One-command rerun

Rerun the entire pipeline on any AOI and date range with a single command. `--bbox` is a
comma string `min_lon,min_lat,max_lon,max_lat` in EPSG:4326; dates are `YYYY-MM-DD`:

```bash
hormuz run \
  --bbox 55.9,26.3,57.1,27.1 \
  --start 2026-02-15 \
  --end 2026-06-13
```

This searches scenes, fetches/windows imagery, masks land, runs CA-CFAR, extracts chips,
verifies each candidate with Opus 4.8, and writes:

- `artifacts/detections.json` — every candidate with its location, area, intensity, and
  Claude's label/confidence/reasoning.
- `artifacts/timeseries.json` — per-date verified vessel counts.
- `artifacts/chips/<scene_id>_NNN.png` — one chip per candidate.
- `artifacts/chips/<scene_id>_overlay.png` — annotated scene overlay (boxes + verdicts).

### Useful flags (`hormuz run`)

| Flag | Effect |
| --- | --- |
| `--bbox "min_lon,min_lat,max_lon,max_lat"` | AOI (overrides config default) |
| `--start YYYY-MM-DD` / `--end YYYY-MM-DD` | inclusive date range |
| `--max-scenes N` | cap how many matching scenes are processed |
| `--max-candidates N` | cap the (paid) vision pass to the strongest N candidates per scene; logged when it caps |
| `--no-verify` | skip the Opus 4.8 vision pass entirely (no API key / no cost) — candidates are written `unverified` |

All flags fall back to `config/hormuz.yaml` when omitted.

### List scenes without downloading

To see which Sentinel-1 scenes match an AOI/date range without fetching imagery or
calling the model:

```bash
hormuz search \
  --bbox 55.9,26.3,57.1,27.1 \
  --start 2026-02-15 \
  --end 2026-06-13
```

It prints each scene's date and item id. `hormuz search` also accepts `--max-scenes`.

### Generate the analyst brief

After a run has produced `artifacts/timeseries.json`, generate the Opus 4.8 analyst
brief (it reads the time series, `data/timeline.json`, and optional oil prices):

```bash
hormuz brief \
  --bbox 55.9,26.3,57.1,27.1 \
  --start 2026-02-15 \
  --end 2026-06-13
```

This writes `artifacts/brief.md`. The open/closed `data/timeline.json` is compiled from
public reporting (human-verified-pending) and overlays the traffic chart in the web app.

## Outputs / artifacts

All written under `artifacts/` (configurable via `artifacts_dir`).

**`detections.json`**

```jsonc
{
  "bbox": [55.9, 26.3, 57.1, 27.1],
  "start": "2026-02-15",
  "end": "2026-06-13",
  "collection": "sentinel-1-grd",
  "count": 123,
  "detections": [
    {
      "scene_id": "S1C_IW_GRDH_...",
      "date": "2026-04-03",
      "datetime": "2026-04-03T01:48:12Z",
      "lon": 56.51, "lat": 25.22,
      "area_px": 16,
      "max_intensity": 1234.5,
      "label": "vessel",          // vessel | island | rig | noise | unverified
      "confidence": 0.84,
      "reasoning": "compact bright elongated target on dark open water",
      "chip": "chips/S1C_..._000.png"
    }
  ]
}
```

**`timeseries.json`** — one record per acquisition date; a detection counts as a vessel
only when Claude's label is `"vessel"`:

```jsonc
{
  "series": [
    {
      "date": "2026-04-03",
      "scene_count": 1,
      "candidate_count": 75,
      "vessel_count": 42
    }
  ]
}
```

**`chips/`** — per-candidate PNG chips (`<scene_id>_NNN.png`) and one annotated scene
overlay per scene (`<scene_id>_overlay.png`).

## Web app

A dependency-light **static** frontend (`web/`) renders the pre-computed artifacts —
detection overlay first, then the traffic chart, then the analyst brief — and deploys to
the Vercel free tier with no backend. A `sync_artifacts.sh` script copies
`artifacts/` and `data/timeline.json` into the deployable `public/` directory; bundled
sample data lets the page render before the pipeline has run. See
[`web/README.md`](web/README.md) for the full deploy and artifact-sync flow.

## Data sources & licensing

| Source | Use | License |
| --- | --- | --- |
| Sentinel-1 GRD via Microsoft Planetary Computer | SAR imagery | Open, free, anonymous (Copernicus) |
| Natural Earth 10m (land + minor islands) | land/island masking | Public domain |
| datahub.io oil prices (Brent/WTI) | optional brief input | ODC-PDDL-1.0 |
| Anthropic Opus 4.8 | candidate verification + analyst brief | Anthropic API — **user-provided key** |

Everything is free / openly licensed except the Anthropic API, which uses your own key.

## Caveats

- **GRD, not RTC.** We use the `sentinel-1-grd` collection because it can be signed
  anonymously. The RTC (terrain-corrected) collection carries
  `msft:requires_account: true` and would break the no-credentials constraint. GRD is
  amplitude DN; CFAR runs on intensity (amplitude²), which is fine — CFAR is a relative
  local-contrast test. GRD scenes are in radar/ground-range geometry with GCPs (no
  projected CRS), so the pipeline georeferences on read via a `WarpedVRT` to UTM.
- **Counts are transit-corridor detections, model-verified — not AIS ground truth.**
  Numbers reflect candidates that fall in the AOI and survive land masking and the
  Opus 4.8 vision pass. Off-corridor traffic, vessels too small/dark for the GRD
  resolution, and scenes where the AOI is outside the footprint are not counted.
- **Land/island leakage** is exactly what the vision pass is there to relabel; Natural
  Earth 10m does not mask the smallest mid-water features (higher-fidelity OSM polygons
  are a documented future swap via `landmask.source`).
- **The open/closed timeline is human-verified-pending** — treat the event markers as a
  working annotation, not a settled record.
