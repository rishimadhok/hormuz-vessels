"""Search Microsoft Planetary Computer for Sentinel-1 GRD scenes over the AOI.

No credentials required: `planetary_computer.sign_inplace` signs item assets
anonymously for the `sentinel-1-grd` collection.
"""

from __future__ import annotations

from dataclasses import dataclass

import planetary_computer
from pystac_client import Client

from .config import Settings


@dataclass
class Scene:
    """A single Sentinel-1 acquisition matching the AOI + date range."""

    item_id: str
    datetime: str            # ISO timestamp of acquisition
    asset_href: str          # signed COG href for the chosen polarization
    polarization: str

    @property
    def date(self) -> str:
        return self.datetime[:10]


def search_scenes(settings: Settings) -> list[Scene]:
    """Return Sentinel-1 GRD scenes intersecting the AOI/date range, oldest first."""
    catalog = Client.open(settings.stac_url, modifier=planetary_computer.sign_inplace)

    search = catalog.search(
        collections=[settings.collection],
        bbox=list(settings.bbox),
        datetime=f"{settings.start}/{settings.end}",
        query={"sar:instrument_mode": {"eq": settings.instrument_mode}},
    )

    pol = settings.polarization.lower()
    scenes: list[Scene] = []
    for item in search.items():
        # Asset keys are lowercase 'vv'/'vh' on the GRD collection.
        asset = item.assets.get(pol) or item.assets.get(pol.upper())
        if asset is None:
            continue  # scene lacks the requested polarization (e.g. single-pol)
        scenes.append(
            Scene(
                item_id=item.id,
                datetime=item.datetime.isoformat() if item.datetime else "",
                asset_href=asset.href,
                polarization=pol,
            )
        )

    scenes.sort(key=lambda s: s.datetime)
    if settings.max_scenes is not None:
        scenes = scenes[: settings.max_scenes]
    return scenes
