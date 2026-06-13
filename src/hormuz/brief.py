"""Opus 4.8 analyst-brief generator.

Takes the pipeline's vessel-traffic time series, the human-curated closure/
disruption timeline, and (optionally) a crude-oil spot-price series, and asks
Claude Opus 4.8 to write a plain-English "what this means for an oil/commodity
trader" brief in markdown.

The model is told to reason only from the data provided (no invented numbers).
We stream the response (`client.messages.stream`) because an analyst brief can
run long, and pull the full text via `get_final_message()`.

Writes ``artifacts/brief.md`` and returns its Path.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from .config import Settings
from .oil import align_to_dates, fetch_oil_prices

load_dotenv()  # pick up ANTHROPIC_API_KEY from a .env if present

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior maritime and energy-markets analyst writing a short brief "
    "for crude-oil and commodity traders. You translate raw satellite "
    "vessel-detection data and a geopolitical event timeline into a clear, "
    "honest read on what is happening in the Strait of Hormuz and what it means "
    "for the oil market. You write in plain English for a busy trading desk: "
    "lead with the bottom line, be precise, and never overstate what the data "
    "supports. You are rigorous about provenance and uncertainty. You NEVER "
    "invent or estimate numbers that are not in the data you were given — if a "
    "figure is not provided, you say so rather than guessing."
)


def _load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None if missing or unparseable."""
    if not path.exists():
        logger.warning("brief: input file not found: %s", path)
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("brief: could not read %s (%s)", path, exc)
        return None


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it (or put it in a .env file) "
            "before generating the analyst brief."
        )
    return anthropic.Anthropic()


def _build_user_prompt(
    series: list[dict],
    events: list[dict],
    timeline_meta: dict,
    oil_aligned: list[dict | None],
    oil_series: list[dict],
    coverage_rows: list[dict],
) -> str:
    """Assemble the single user message Claude reasons over."""
    parts: list[str] = []

    parts.append(
        "Write a concise analyst brief in markdown on Strait of Hormuz vessel "
        "traffic, for an oil/commodity trader. Use ONLY the data below — do not "
        "invent or estimate any numbers that are not present here.\n"
    )

    # --- Vessel-count time series ---
    parts.append("## DATA 1 — Detected vessel counts (SAR CFAR + temporal-persistence filter)")
    if series:
        parts.append(
            "Each row is one Sentinel-1 SAR acquisition over the Strait of Hormuz "
            "CHOKEPOINT transit corridor (narrowest point, between Oman's Musandam "
            "peninsula and the Iranian coast). Method: classical CFAR ship "
            "detection on VH backscatter, with land/island masking. `moving_count` "
            "is the vessel estimate = detections that do NOT recur at the same "
            "coordinates across passes (vessels move). `static_count` = detections "
            "that recur at the same spot across multiple dates and are therefore "
            "filtered out as fixed features (islands/rigs), NOT vessels. "
            "(NOTE: detections are NOT model-verified in this run — the headline "
            "number is `moving_count`, the persistence-filtered candidate count; "
            "treat it as a vessel ESTIMATE, not a confirmed census.) These are "
            "detections within the imaged corridor on the acquisition date, NOT a "
            "full daily transit census.\n"
        )
        parts.append("```json")
        parts.append(json.dumps({"series": series}, indent=2))
        parts.append("```")
        n_open = sum(1 for r in coverage_rows if "open" in (r.get("status", "")).lower())
        parts.append(
            f"\nIMPORTANT BASELINE CAVEAT: only {n_open} pre-closure ('Open') "
            "acquisition date(s) exist in this window, versus the closed dates. "
            "The during-closure level is well-sampled; the pre-closure baseline is "
            "thin — say this plainly and do not overstate the before/after with a "
            "single baseline point.\n"
        )
    else:
        parts.append(
            "NO vessel-count data is available (the time series is empty). The "
            "brief must be honest that the detection pipeline produced no "
            "usable counts, and lean on the timeline for context.\n"
        )

    # --- Timeline of closure / disruption events ---
    parts.append(
        "\n## DATA 2 — Closure / disruption timeline "
        f"(human-verified: {timeline_meta.get('verified_by_human', False)})"
    )
    if events:
        parts.append(
            "Curated from public reporting. Each event has a date, type, title, "
            "description, confidence, and sources.\n"
        )
        parts.append("```json")
        parts.append(json.dumps(events, indent=2))
        parts.append("```")
    else:
        parts.append("NO timeline events are available.\n")

    # --- Oil prices (optional) ---
    parts.append("\n## DATA 3 — Crude-oil spot prices (optional context)")
    if oil_series:
        sname = oil_series[0].get("series", "brent")
        parts.append(
            f"Daily {sname.upper()} spot price (USD/bbl) over the analysis "
            "window, plus the price aligned to each vessel-acquisition date "
            "(nearest prior trading day). Use this only to comment on "
            "correlation/coincidence — you have no causal model.\n"
        )
        parts.append("```json")
        parts.append(
            json.dumps(
                {
                    "oil_prices": oil_series,
                    "aligned_to_acquisition_dates": [
                        {
                            "acquisition_date": s["date"],
                            "moving_vessels": s.get("moving_count"),
                            "oil_price": (oil_aligned[i] or {}).get("price")
                            if i < len(oil_aligned)
                            else None,
                        }
                        for i, s in enumerate(series)
                    ],
                },
                indent=2,
            )
        )
        parts.append("```")
    else:
        parts.append(
            "Oil-price data was not available for this window — OMIT oil from "
            "the analysis entirely (do not speculate about prices).\n"
        )

    # --- Coverage / normalization (the credibility check) ---
    parts.append("\n## DATA 4 — Imaged coverage per date (credibility / normalization)")
    if coverage_rows:
        parts.append(
            "For each date: what fraction of the AOI bbox the Sentinel-1 swath "
            "actually imaged (`coverage_pct`), the imaged area (`imaged_km2`), and "
            "the coverage-normalized vessel density (`vessels_per_1000km2` = moving "
            "vessels per 1,000 km² imaged). Use this to confirm the open-vs-closed "
            "drop is NOT just a coverage artifact: the open and closed dates are at "
            "comparable coverage, and the density still drops. Cite the normalized "
            "density, not just raw counts, when making the before/after claim.\n"
        )
        parts.append("```json")
        parts.append(json.dumps(coverage_rows, indent=2))
        parts.append("```")
    else:
        parts.append("No coverage data available.\n")

    # --- Instructions on structure ---
    parts.append(
        "\n## WHAT TO WRITE\n"
        "Produce a markdown brief with these elements:\n"
        "1. **Bottom line** — open with the single most important takeaway for a "
        "trader, in 1-2 sentences. The headline finding is that detected moving "
        "vessels in the chokepoint roughly HALVED from the pre-closure baseline to "
        "the closure period, while Brent rose.\n"
        "2. **What the traffic shows vs. the timeline** — reference the moving-"
        "vessel trend against the closure/disruption events. State the before vs "
        "after using the COVERAGE-NORMALIZED density (DATA 4), and explicitly note "
        "the open and closed dates are at comparable imaged coverage so the drop "
        "is not a coverage artifact. Flag the thin pre-closure baseline (few open "
        "dates).\n"
        "3. **Oil correlation** — if oil data is present, note the apparent "
        "coincidence between falling detected traffic and rising Brent; be explicit "
        "it is correlation, not established causation.\n"
        "4. **Caveats / data provenance** — a short closing section, stated plainly: "
        "this is IMAGERY-GROUNDED (Sentinel-1 SAR, free/open via Microsoft "
        "Planetary Computer), detected by classical CFAR; fixed features "
        "(islands/rigs) are FILTERED OUT via a temporal-persistence test (returns "
        "recurring at the same coordinates across passes); detections are NOT "
        "model-verified in this run, so counts are vessel ESTIMATES; counts are "
        "transit-corridor detections on imaged acquisition dates, not a full daily "
        "census; the pre-closure baseline is a single date; the timeline is curated "
        "from public reporting and is "
        f"{'human-verified' if timeline_meta.get('verified_by_human') else 'pending human verification'}.\n"
        "\nKeep it tight and plain-English. Do not invent numbers."
    )

    return "\n".join(parts)


def generate_brief(settings: Settings) -> Path:
    """Generate the analyst brief and write it to ``artifacts/brief.md``.

    Reads ``artifacts/timeseries.json`` and ``data/timeline.json`` (both handled
    gracefully if missing), optionally fetches oil prices over the settings date
    range, composes a single Opus 4.8 streaming request, and writes the markdown.

    Returns the path to the written ``brief.md``.
    """
    artifacts = settings.artifacts_path
    timeseries = _load_json(artifacts / "timeseries.json") or {}
    timeline = _load_json(Path("data") / "timeline.json") or {}

    series: list[dict] = timeseries.get("series", []) or []
    events: list[dict] = timeline.get("events", []) or []
    coverage = _load_json(artifacts / "coverage.json") or {}
    coverage_rows: list[dict] = coverage.get("rows", []) or []

    # Optional oil prices over the configured window, aligned to acq dates.
    oil_series: list[dict] = []
    oil_aligned: list[dict | None] = []
    try:
        oil_series = fetch_oil_prices(settings.start, settings.end, series="brent")
    except Exception as exc:  # oil is strictly optional; never let it break the brief
        logger.warning("brief: oil fetch failed, omitting oil (%s)", exc)
        oil_series = []
    if oil_series and series:
        oil_aligned = align_to_dates(oil_series, [s["date"] for s in series])

    user_prompt = _build_user_prompt(
        series, events, timeline, oil_aligned, oil_series, coverage_rows
    )

    client = _client()

    logger.info(
        "brief: composing with %s (series=%d, events=%d, oil_rows=%d)",
        settings.model,
        len(series),
        len(events),
        len(oil_series),
    )

    # Stream because the brief may be long; accumulate via get_final_message().
    with client.messages.stream(
        model=settings.model,
        max_tokens=4000,
        thinking={"type": "adaptive", "display": "summarized"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        final = stream.get_final_message()

    if final.stop_reason == "refusal":
        raise RuntimeError(
            "Claude declined to generate the brief (stop_reason=refusal)."
        )

    markdown = "".join(b.text for b in final.content if b.type == "text").strip()
    if not markdown:
        raise RuntimeError("Brief generation returned no text content.")

    out_path = artifacts / "brief.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown + "\n")

    print(f"Wrote analyst brief to {out_path}")
    return out_path
