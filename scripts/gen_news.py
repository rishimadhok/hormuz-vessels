"""Generate data/news.json — the OSINT/news layer for the multi-intelligence view.

Blends two real, sourced streams:
  1. The curated closure/disruption timeline (data/timeline.json) — each event
     becomes a news item with its source link.
  2. Market/energy headlines on the Hormuz closure and oil price (real articles
     found via web search, with live URLs), so the feed shows oil prices moving
     with the news.

Run: PYTHONPATH=src .venv/bin/python scripts/gen_news.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Real market/energy-news headlines on the Hormuz closure (live URLs).
MARKET_NEWS = [
    {
        "date": "2026-03-03",
        "headline": "Global energy shock: Brent surges as Iran seals the Strait of Hormuz",
        "source": "FinancialContent",
        "url": "https://markets.financialcontent.com/stocks/article/marketminute-2026-3-3-global-energy-shock-brent-surges-to-8358-as-iran-seals-the-strait-of-hormuz",
        "kind": "news",
        "summary": "Brent spikes as Iran moves to seal the strait at the outset of the conflict.",
    },
    {
        "date": "2026-03-13",
        "headline": "Iran continues to close the Strait of Hormuz; oil breaks US$100/bbl",
        "source": "Katadata / Databoks",
        "url": "https://databoks.katadata.co.id/en/datapublish/2026/03/13/iran-continues-to-close-the-strait-of-hormuz-oil-prices-break-us100-per-barrel",
        "kind": "news",
        "summary": "Brent breaks $100 as the closure persists into a second week.",
    },
    {
        "date": "2026-05-15",
        "headline": "Goldman: another month of Hormuz closure means $100+ Brent through 2026",
        "source": "OilPrice.com",
        "url": "https://oilprice.com/Latest-Energy-News/World-News/Goldman-Another-Month-of-Hormuz-Closure-Means-Over-100-Brent-Throughout-2026.html",
        "kind": "news",
        "summary": "Goldman projects sustained $100+ Brent if tanker traffic stays mostly shut.",
    },
    {
        "date": "2026-05-19",
        "headline": "Crude oil forecast: Strait of Hormuz closure keeps Brent elevated",
        "source": "Capital.com",
        "url": "https://capital.com/en-int/market-updates/crude-oil-price-forecast-19-05-2026",
        "kind": "news",
        "summary": "Analysts see Brent holding above $100 while the strait remains mostly closed.",
    },
    {
        "date": "2026-05-08",
        "headline": "How the Strait of Hormuz closure is driving oil prices in 2026",
        "source": "Discovery Alert",
        "url": "https://discoveryalert.com.au/strait-hormuz-oil-prices-closure-global-energy-shock/",
        "kind": "news",
        "summary": "~20% of global crude transits Hormuz; the closure tightens supply and lifts prices.",
    },
]


def main() -> None:
    items: list[dict] = []

    # 1. Timeline events -> news items (with their first source).
    tl = json.loads((DATA / "timeline.json").read_text())
    for e in tl.get("events", []):
        src = (e.get("sources") or [{}])[0]
        items.append({
            "date": e["date"],
            "headline": e.get("title", ""),
            "source": src.get("name", "public reporting"),
            "url": src.get("url", ""),
            "kind": "news",
            "summary": e.get("description", ""),
        })

    # 2. Market/energy headlines.
    items.extend(MARKET_NEWS)

    items.sort(key=lambda x: x["date"])
    (DATA / "news.json").write_text(json.dumps({"items": items}, indent=2))
    print(f"wrote {DATA/'news.json'} with {len(items)} items "
          f"({len(tl.get('events', []))} timeline + {len(MARKET_NEWS)} market)")


if __name__ == "__main__":
    main()
