"""`hormuz` command-line entrypoint.

One command reruns the whole pipeline on a new bbox/date range:

    hormuz run --bbox 55.9,26.3,57.1,27.1 --start 2026-02-15 --end 2026-06-13
"""

from __future__ import annotations

import typer

from .config import load_settings
from .search import search_scenes

app = typer.Typer(add_completion=False, help="Strait of Hormuz vessel detection.")


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    """Parse 'min_lon,min_lat,max_lon,max_lat' into a tuple of floats."""
    if not bbox:
        return None
    parts = [float(x) for x in bbox.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise typer.BadParameter("bbox must be 'min_lon,min_lat,max_lon,max_lat'")
    return tuple(parts)  # type: ignore[return-value]


_BBOX_HELP = "AOI as 'min_lon,min_lat,max_lon,max_lat'"


@app.command()
def run(
    bbox: str = typer.Option(None, help=_BBOX_HELP),
    start: str = typer.Option(None, help="Start date yyyy-mm-dd"),
    end: str = typer.Option(None, help="End date yyyy-mm-dd"),
    max_scenes: int = typer.Option(None, help="Cap scenes processed (slice mode)"),
    max_candidates: int = typer.Option(None, help="Cap candidates verified per scene"),
    artifacts_dir: str = typer.Option(None, help="Output dir (for parallel per-date runs)"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip the Claude vision pass"),
):
    """Run the full detection + verification pipeline and write artifacts/."""
    from . import pipeline  # deferred import so `--help` works without heavy deps

    settings = load_settings(
        bbox=_parse_bbox(bbox),
        start=start,
        end=end,
        max_scenes=max_scenes if max_scenes is not None else ...,
    )
    if max_candidates is not None:
        settings.max_candidates_per_scene = max_candidates
    if artifacts_dir is not None:
        settings.artifacts_dir = artifacts_dir
    pipeline.run(settings, verify=not no_verify)


@app.command()
def brief(
    bbox: str = typer.Option(None, help=_BBOX_HELP),
    start: str = typer.Option(None, help="Start date yyyy-mm-dd"),
    end: str = typer.Option(None, help="End date yyyy-mm-dd"),
):
    """Generate the Opus 4.8 analyst brief from artifacts/ + timeline + oil."""
    from . import brief as brief_mod  # deferred import so `--help` is fast

    settings = load_settings(
        bbox=_parse_bbox(bbox),
        start=start,
        end=end,
    )
    brief_mod.generate_brief(settings)


@app.command()
def search(
    bbox: str = typer.Option(None, help=_BBOX_HELP),
    start: str = typer.Option(None, help="Start date yyyy-mm-dd"),
    end: str = typer.Option(None, help="End date yyyy-mm-dd"),
    max_scenes: int = typer.Option(None, help="Cap scenes listed"),
):
    """List the Sentinel-1 scenes that match the AOI/date range (no download)."""
    settings = load_settings(
        bbox=_parse_bbox(bbox),
        start=start,
        end=end,
        max_scenes=max_scenes if max_scenes is not None else ...,
    )
    scenes = search_scenes(settings)
    typer.echo(f"{len(scenes)} scene(s):")
    for s in scenes:
        typer.echo(f"  {s.date}  {s.item_id}")


if __name__ == "__main__":
    app()
