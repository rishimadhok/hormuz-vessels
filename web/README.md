# Strait of Hormuz — Vessel Detection (web)

A dependency-light **static** frontend that renders pre-computed pipeline artifacts.
No backend. Deploys to the Vercel free tier as a zero-config static site.

The page leads with the **detection** (annotated SAR scene + Claude's verdicts),
then the **traffic chart** (vessels over time with event markers), then the
**analyst brief**.

## Layout

```
web/
├── public/                 # <- the deployable static site (Vercel output dir)
│   ├── index.html
│   ├── style.css
│   ├── app.js              # fetches artifacts, falls back to sample/, renders all 3 sections
│   ├── sample/             # bundled SAMPLE data so the page renders before the pipeline runs
│   │   ├── detections.json
│   │   ├── timeseries.json
│   │   ├── timeline.json
│   │   ├── brief.md
│   │   └── chips/          # tiny generated SAR-style overlay + candidate chips
│   ├── artifacts/          # (generated) synced from ../artifacts — gitignored
│   └── data/               # (generated) synced from ../data/timeline.json — gitignored
├── sync_artifacts.sh       # copies ../artifacts + ../data/timeline.json into public/
├── vercel.json             # runs sync at build, serves public/ statically
├── .gitignore              # ignores the synced (generated) artifact copies
└── README.md
```

## How it loads data

`app.js` fetches the **real** artifacts first:
`artifacts/detections.json`, `artifacts/timeseries.json`, `artifacts/brief.md`,
`data/timeline.json`, and chip/overlay PNGs under `artifacts/chips/`.

- If `detections.json` 404s, it falls back to everything in `sample/` and shows a
  **SAMPLE DATA** badge (top-right).
- Each artifact loads independently — a missing `brief.md` or `timeline.json` only
  blanks that one section (with a "no data yet" placeholder); the rest still renders.
- Chip/overlay images that 404 degrade to inline placeholders.

The chip/overlay paths in `detections.json` are relative (e.g. `chips/<scene>_000.png`)
and are resolved against `artifacts/`. The hero overlay is derived as
`<scene_id>_overlay.png` in the same chips dir.

## Preview locally

The site fetches files, so open it through a web server (not `file://`):

```bash
# 1. (optional) pull in real artifacts produced by the pipeline
./web/sync_artifacts.sh

# 2. serve public/
cd web/public
python3 -m http.server 8000
#   or:  npx serve .
```

Open http://localhost:8000.

- With **no** sync run, you'll see the bundled sample data + the SAMPLE DATA badge.
- After `sync_artifacts.sh` copies real artifacts in, you'll see live data.

## Sync artifacts

`sync_artifacts.sh` copies, from the repo root one level up:

- `../artifacts/detections.json`, `../artifacts/timeseries.json`, `../artifacts/brief.md`
- `../artifacts/chips/` (overlays + per-candidate chips)
- `../data/timeline.json`

into `web/public/artifacts/` and `web/public/data/`. Files that don't exist yet are
skipped (the frontend handles their absence). Run it anytime the pipeline regenerates
artifacts.

## Deploy to Vercel

Set the Vercel project **Root Directory** to `web/`. `vercel.json` does the rest:

- `buildCommand: bash sync_artifacts.sh` — copies the latest artifacts into `public/`
- `outputDirectory: public` — Vercel serves this folder statically
- `framework: null` — no framework build step

```bash
cd web
vercel        # preview deploy
vercel --prod # production
```

If your build environment doesn't have the artifacts checked out next to `web/`
(e.g. they're produced elsewhere), either commit a synced `public/artifacts/`
copy, or override the build command to `true` (no-op) and ship the sample data —
the page still renders.

This is a fully static deploy: **no server, no API routes, free-tier friendly.**
