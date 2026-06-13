"""Fetch a free, openly-licensed crude-oil spot-price series (Brent / WTI).

Used to *optionally* overlay oil prices on the vessel-traffic time series for the
analyst brief. The brief criterion treats oil prices as "if available", so every
network path here degrades gracefully: on any failure (no source reachable, no
key, parse error) the public functions return ``[]`` and log a warning rather
than raising. There is **no** network access at import time.

Sources (tried in order):

1. datahub.io "Brent and WTI Spot Prices" — a well-known open dataset mirrored on
   GitHub as ``datasets/oil-prices``. No API key. Daily CSV columns ``Date,Price``.
   License: Open Data Commons Public Domain Dedication & License v1.0 (ODC-PDDL-1.0).
   Underlying data is the U.S. EIA daily spot series, so values match EIA exactly.
     https://github.com/datasets/oil-prices
     https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv
     https://raw.githubusercontent.com/datasets/oil-prices/main/data/wti-daily.csv

2. EIA open data API v2 (optional, key-gated). Used only if ``EIA_API_KEY`` is set
   in the environment. Free key: https://www.eia.gov/opendata/
     Brent series id: RBRTE   WTI series id: RWTC
     https://api.eia.gov/v2/petroleum/pri/spt/data/

Coverage note: as verified on 2026-06-13 the datahub CSV carried daily data through
2026-06-08, i.e. genuinely current (these are official spot prices published with a
few-day lag, and markets are closed on weekends/holidays). The function is
range-agnostic: it filters whatever the source publishes to ``[start, end]``, so it
works for any historical or recent range and simply returns fewer rows near the
publication frontier.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from bisect import bisect_right
from datetime import date, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

# Network is best-effort; keep timeouts short so an unreachable source can't stall
# the brief pipeline.
_TIMEOUT = 20

_SERIES_ALIASES = {
    "brent": "brent",
    "rbrte": "brent",
    "europe brent": "brent",
    "wti": "wti",
    "rwtc": "wti",
    "cushing": "wti",
}

# datahub mirror: try `main` first, fall back to the legacy `master` branch.
_DATAHUB_CSV = {
    "brent": [
        "https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv",
        "https://raw.githubusercontent.com/datasets/oil-prices/master/data/brent-daily.csv",
    ],
    "wti": [
        "https://raw.githubusercontent.com/datasets/oil-prices/main/data/wti-daily.csv",
        "https://raw.githubusercontent.com/datasets/oil-prices/master/data/wti-daily.csv",
    ],
}

_EIA_SERIES_ID = {"brent": "RBRTE", "wti": "RWTC"}
_EIA_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"


def _normalize_series(series: str) -> str | None:
    """Map a user-supplied series name to the canonical 'brent' or 'wti'."""
    key = (series or "").strip().lower()
    return _SERIES_ALIASES.get(key)


def _valid_date(value: str) -> str | None:
    """Return the date as 'YYYY-MM-DD' if parseable, else None."""
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except (ValueError, AttributeError):
        return None


def _records(rows: list[tuple[str, float]], canonical: str) -> list[dict]:
    """Build sorted, de-duplicated price records from (date, price) pairs."""
    by_date: dict[str, float] = {}
    for d, p in rows:
        by_date[d] = p  # later rows win; source is already chronological
    return [
        {"date": d, "price": by_date[d], "series": canonical}
        for d in sorted(by_date)
    ]


def _fetch_datahub(canonical: str, start: str, end: str) -> list[dict]:
    """Fetch + parse the no-key datahub CSV, filtered to [start, end]."""
    last_err: Exception | None = None
    for url in _DATAHUB_CSV[canonical]:
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:  # network / HTTP error
            last_err = exc
            continue

        rows: list[tuple[str, float]] = []
        reader = csv.DictReader(io.StringIO(resp.text))
        if not reader.fieldnames or "Date" not in reader.fieldnames:
            last_err = ValueError(f"unexpected CSV header from {url}: {reader.fieldnames}")
            continue
        for row in reader:
            d = _valid_date(row.get("Date", ""))
            raw = (row.get("Price") or "").strip()
            if d is None or not raw:
                continue
            if d < start or d > end:
                continue
            try:
                rows.append((d, float(raw)))
            except ValueError:
                continue  # skip blank/non-numeric prices
        return _records(rows, canonical)

    logger.warning("oil: datahub source unavailable for %s (%s)", canonical, last_err)
    return []


def _fetch_eia(canonical: str, start: str, end: str, api_key: str) -> list[dict]:
    """Fetch the EIA v2 daily spot series. Used only when EIA_API_KEY is set."""
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": _EIA_SERIES_ID[canonical],
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    try:
        resp = requests.get(_EIA_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("oil: EIA source failed for %s (%s)", canonical, exc)
        return []

    series = (payload or {}).get("response", {}).get("data")
    if not isinstance(series, list):
        logger.warning("oil: EIA returned no data for %s (%s)", canonical, payload)
        return []

    rows: list[tuple[str, float]] = []
    for item in series:
        d = _valid_date(str(item.get("period", "")))
        val = item.get("value")
        if d is None or val is None:
            continue
        try:
            rows.append((d, float(val)))
        except (ValueError, TypeError):
            continue
    return _records(rows, canonical)


def fetch_oil_prices(start: str, end: str, series: str = "brent") -> list[dict]:
    """Fetch a daily crude-oil spot-price series for ``[start, end]`` (inclusive).

    Args:
        start: ISO date 'YYYY-MM-DD' (inclusive).
        end:   ISO date 'YYYY-MM-DD' (inclusive).
        series: 'brent' (default) or 'wti' (aliases: RBRTE/RWTC/etc.).

    Returns:
        Records ``{"date": "YYYY-MM-DD", "price": float, "series": "brent"|"wti"}``
        sorted ascending by date, or ``[]`` if the series is unknown, the date
        range is invalid, or no source is reachable. Never raises on network
        failure — oil prices are an optional ("if available") brief input.
    """
    canonical = _normalize_series(series)
    if canonical is None:
        logger.warning("oil: unknown series %r (expected 'brent' or 'wti')", series)
        return []

    s, e = _valid_date(start), _valid_date(end)
    if s is None or e is None:
        logger.warning("oil: invalid date range start=%r end=%r", start, end)
        return []
    if s > e:
        s, e = e, s

    # Prefer the no-key open dataset; it carries the same EIA values and needs no
    # credentials. Fall back to the keyed EIA API only if the CSV path yields
    # nothing AND a key is present.
    records = _fetch_datahub(canonical, s, e)
    if records:
        return records

    api_key = os.environ.get("EIA_API_KEY")
    if api_key:
        logger.info("oil: datahub empty for %s; trying EIA API", canonical)
        return _fetch_eia(canonical, s, e, api_key)

    return records  # [] — nothing reachable / no key


def align_to_dates(prices: list[dict], dates: list[str]) -> list[dict | None]:
    """Map a price series onto vessel-count acquisition dates.

    For each target date, returns the price record for the nearest *prior or same*
    trading day (markets are closed on weekends/holidays, so an exact match often
    doesn't exist). Element is ``None`` when no price on/before that date is
    available (e.g. target predates the series, or ``prices`` is empty). Output
    length and order match ``dates``.

    Args:
        prices: output of :func:`fetch_oil_prices` (or any list of records with
            'date'/'price'/'series'); need not be pre-sorted.
        dates: acquisition dates as 'YYYY-MM-DD' strings.

    Returns:
        list aligned 1:1 with ``dates``; each item is a price record or None.
    """
    valid = [r for r in (prices or []) if _valid_date(str(r.get("date", ""))) is not None]
    valid.sort(key=lambda r: r["date"])
    keys = [r["date"] for r in valid]

    out: list[dict | None] = []
    for target in dates:
        t = _valid_date(str(target))
        if t is None or not keys:
            out.append(None)
            continue
        # rightmost record whose date <= target (nearest prior trading day)
        idx = bisect_right(keys, t) - 1
        out.append(valid[idx] if idx >= 0 else None)
    return out


def prices_by_date(
    dates: list[str], series_list: tuple[str, ...] = ("brent", "wti")
) -> dict[str, dict]:
    """Return {date: {series: price, ...}} for the given acquisition dates.

    Fetches each series over a window covering the dates (with a 2-week lookback so
    the nearest-prior-trading-day alignment has data), then aligns. Degrades to an
    empty dict for any series/date that can't be resolved (never raises).
    """
    valid = sorted(d for d in dates if _valid_date(str(d)) is not None)
    if not valid:
        return {}
    start = (datetime.fromisoformat(valid[0]) - timedelta(days=14)).date().isoformat()
    end = valid[-1]

    by_date: dict[str, dict] = {d: {} for d in valid}
    for series in series_list:
        canonical = _normalize_series(series)
        if canonical is None:
            continue
        aligned = align_to_dates(fetch_oil_prices(start, end, series), valid)
        for d, rec in zip(valid, aligned):
            if rec is not None:
                by_date[d][canonical] = rec["price"]
    return by_date


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Recent range near the publication frontier — also exercises the
    # weekend/holiday gaps that align_to_dates() is built to handle.
    sample_start, sample_end = "2026-05-25", "2026-06-12"

    for ser in ("brent", "wti"):
        rows = fetch_oil_prices(sample_start, sample_end, series=ser)
        print(f"\n{ser.upper()}  {sample_start}..{sample_end}: {len(rows)} rows")
        for r in rows[:3]:
            print("  ", r)
        if len(rows) > 3:
            print("   ...")
            print("  ", rows[-1])

    # Demonstrate alignment onto hypothetical acquisition dates, including a
    # weekend date (2026-05-31 = Sunday) and a date before the range.
    acq_dates = ["2026-05-20", "2026-05-28", "2026-05-31", "2026-06-08"]
    brent = fetch_oil_prices(sample_start, sample_end, series="brent")
    aligned = align_to_dates(brent, acq_dates)
    print("\nalign_to_dates (Brent, nearest prior trading day):")
    for d, a in zip(acq_dates, aligned):
        print(f"   {d} -> {a}")

    # Failure-mode demonstration: unknown series returns [] (no raise).
    print("\nunknown series ->", fetch_oil_prices(sample_start, sample_end, series="diesel"))
