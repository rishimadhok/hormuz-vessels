"""Pipeline configuration: load YAML, allow CLI overrides, validate."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CFARConfig(BaseModel):
    pfa: float = 1.0e-5
    guard_px: int = 9
    bg_px: int = 31
    min_area_px: int = 4
    max_area_px: int = 4000


class LandmaskConfig(BaseModel):
    source: str = "natural_earth"   # NE 10m (Phase 1); OSM polygons are a Phase-3 swap
    dilate_px: int = 3


class Settings(BaseModel):
    """Fully-resolved pipeline settings."""

    bbox: tuple[float, float, float, float]
    start: str
    end: str

    stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    collection: str = "sentinel-1-grd"
    polarization: str = "vh"
    instrument_mode: str = "IW"

    cfar: CFARConfig = Field(default_factory=CFARConfig)
    landmask: LandmaskConfig = Field(default_factory=LandmaskConfig)

    chip_px: int = 64
    max_candidates_per_scene: int | None = 75
    model: str = "claude-opus-4-8"
    use_batches: bool = True

    max_scenes: int | None = 5
    artifacts_dir: str = "artifacts"

    @property
    def artifacts_path(self) -> Path:
        return Path(self.artifacts_dir)

    @property
    def chips_path(self) -> Path:
        return self.artifacts_path / "chips"


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "hormuz.yaml"


def load_settings(
    config_path: Path | str = DEFAULT_CONFIG,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    start: str | None = None,
    end: str | None = None,
    max_scenes: int | None = ...,  # type: ignore[assignment]  # sentinel for "not provided"
) -> Settings:
    """Load YAML config, then apply any explicit CLI overrides."""
    data: dict = {}
    config_path = Path(config_path)
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}

    if bbox is not None:
        data["bbox"] = list(bbox)
    if start is not None:
        data["start"] = start
    if end is not None:
        data["end"] = end
    if max_scenes is not ...:
        data["max_scenes"] = max_scenes

    return Settings.model_validate(data)
