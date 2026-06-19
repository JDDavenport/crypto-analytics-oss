"""
data.py — read-only ingestion from FREE public data sources, for ANY coin.

Every fetch degrades cleanly: on any error it returns {available: False, note}
and NEVER raises. The scorer treats unavailable layers as neutral (0.0).

Sources (all free, all read-only):
  - CoinGecko       : price, market cap, close-price history  (no key needed)
  - DefiLlama       : protocol TVL trend (on-chain proxy; needs a protocol slug)
  - CoinGlass       : perp funding rate (free tier; degrades without a key)
  - FRED            : macro — broad dollar index + Fed funds (needs FRED_API_KEY)
  - alternative.me  : crypto Fear & Greed index (sentiment, free)

⛔ NONE of these are exchange trade/withdraw endpoints. Read-only market data.
No exchange API keys are ever used or stored.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except Exception:
    pass

from .config import Asset

_UA = {"User-Agent": "crypto-analytics-oss/1.0 (educational; advisory-only)"}
COINGECKO_API = "https://api.coingecko.com/api/v3"
DEFILLAMA_API = "https://api.llama.fi"
COINGLASS_API = "https://open-api-v3.coinglass.com/api"
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FEARGREED_API = "https://api.alternative.me/fng/"


def _get_json(url: str, timeout: int = 15, headers: dict | None = None):
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _unavailable(note: str) -> dict:
    return {"available": False, "note": note}


# ---------------------------------------------------------------------------
# CoinGecko: price + close-price history
# ---------------------------------------------------------------------------
def fetch_price(asset: Asset) -> dict:
    try:
        url = (f"{COINGECKO_API}/simple/price?ids={asset.coingecko_id}"
               f"&vs_currencies=usd&include_24hr_change=true&include_market_cap=true")
        d = _get_json(url)
        c = d.get(asset.coingecko_id, {})
        if not c.get("usd"):
            return _unavailable(f"coingecko returned no price for '{asset.coingecko_id}'")
        return {
            "available": True,
            "price": float(c["usd"]),
            "change_24h": c.get("usd_24h_change"),
            "market_cap": c.get("usd_market_cap"),
        }
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"coingecko price error: {e}")


def fetch_ohlc(asset: Asset, days: int = 365) -> dict:
    """Daily close history for TA (market_chart close series)."""
    try:
        url = (f"{COINGECKO_API}/coins/{asset.coingecko_id}/market_chart"
               f"?vs_currency=usd&days={days}&interval=daily")
        d = _get_json(url, timeout=25)
        prices = d.get("prices", [])
        closes = [p[1] for p in prices if p and p[1] is not None]
        if len(closes) < 30:
            return _unavailable(f"coingecko ohlc too short ({len(closes)})")
        return {"available": True, "closes": closes}
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"coingecko ohlc error: {e}")


# ---------------------------------------------------------------------------
# DefiLlama: protocol TVL trend (on-chain proxy)
# ---------------------------------------------------------------------------
def fetch_onchain(asset: Asset) -> dict:
    """TVL 7d/30d trend for the asset's DeFi protocol, if one is configured.
    Many coins (BTC, ETH, memecoins) are not a single protocol — in that case
    there is no slug and the layer degrades to neutral. That is correct."""
    if not asset.defillama_slug:
        return _unavailable("no defillama protocol slug for this asset (on-chain neutral)")
    try:
        url = f"{DEFILLAMA_API}/protocol/{asset.defillama_slug}"
        d = _get_json(url, timeout=25)
        tvl_series = d.get("tvl", [])
        pts = [p.get("totalLiquidityUSD") for p in tvl_series if p.get("totalLiquidityUSD")]
        if len(pts) < 8:
            return _unavailable("defillama tvl series too short")
        cur = pts[-1]
        wk = pts[-8] if len(pts) >= 8 else pts[0]
        mo = pts[-31] if len(pts) >= 31 else pts[0]
        tvl_7d = (cur / wk - 1) * 100 if wk else 0.0
        tvl_30d = (cur / mo - 1) * 100 if mo else 0.0
        return {
            "available": True,
            "tvl_usd": cur,
            "tvl_change_7d_pct": tvl_7d,
            "tvl_change_30d_pct": tvl_30d,
        }
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"defillama error: {e}")


# ---------------------------------------------------------------------------
# CoinGlass: perp funding rate (free tier; degrades without a key)
# ---------------------------------------------------------------------------
def fetch_derivatives(asset: Asset) -> dict:
    """Average perp funding rate for the asset's symbol. The free CoinGlass
    tier usually needs a key header and is often rate-limited; without one this
    degrades to neutral rather than crashing."""
    key = os.getenv("COINGLASS_API_KEY", "")
    try:
        headers = {"CG-API-KEY": key} if key else {}
        url = f"{COINGLASS_API}/futures/funding_rate?symbol={asset.symbol}"
        d = _get_json(url, timeout=12, headers=headers)
        if not isinstance(d, dict) or d.get("code") not in (None, "0", 0):
            return _unavailable("coinglass non-ok response (no/invalid key)")
        rows = d.get("data") or []
        rates = []
        for r in rows:
            v = r.get("rate") or r.get("fundingRate")
            if v is not None:
                rates.append(float(v))
        if not rates:
            return _unavailable("coinglass returned no funding data")
        return {"available": True, "avg_funding_rate": sum(rates) / len(rates)}
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"coinglass error (free tier often blocked): {e}")


# ---------------------------------------------------------------------------
# FRED: macro — broad dollar index + Fed funds rate (needs FRED_API_KEY)
# ---------------------------------------------------------------------------
def fetch_macro() -> dict:
    """Broad dollar index (DTWEXBGS) trend + effective Fed funds (DFF).
    Macro is coin-agnostic (same regime for all crypto). Needs FRED_API_KEY;
    degrades to neutral if absent."""
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        return _unavailable("FRED_API_KEY not set (macro layer neutral)")
    try:
        def series(series_id: str) -> list[float]:
            url = (f"{FRED_API}?series_id={series_id}&api_key={key}&file_type=json"
                   f"&sort_order=desc&limit=40")
            d = _get_json(url, timeout=15)
            obs = d.get("observations", [])
            return [float(o["value"]) for o in obs if o.get("value") not in (".", None)]

        dxy = series("DTWEXBGS")
        ffr = series("DFF")
        out = {"available": True}
        if len(dxy) >= 21:
            out["dxy"] = dxy[0]
            out["dxy_change_20d_pct"] = (dxy[0] / dxy[20] - 1) * 100
        if ffr:
            out["fed_funds_rate"] = ffr[0]
            if len(ffr) >= 21:
                out["ffr_change_20d_bps"] = (ffr[0] - ffr[20]) * 100
        return out if len(out) > 1 else _unavailable("FRED returned no usable series")
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"FRED error: {e}")


# ---------------------------------------------------------------------------
# alternative.me: Fear & Greed (sentiment, free, coin-agnostic)
# ---------------------------------------------------------------------------
def fetch_sentiment() -> dict:
    try:
        d = _get_json(f"{FEARGREED_API}?limit=1", timeout=12)
        rows = d.get("data", [])
        if not rows:
            return _unavailable("fear&greed empty")
        return {"available": True, "fear_greed": int(rows[0]["value"]),
                "classification": rows[0].get("value_classification")}
    except Exception as e:  # noqa: BLE001
        return _unavailable(f"fear&greed error: {e}")


def fetch_all(asset: Asset) -> dict:
    """Ingest every layer for the given asset. Each sub-dict carries its own
    `available` flag so the scorer can degrade gracefully."""
    return {
        "price": fetch_price(asset),
        "ohlc": fetch_ohlc(asset),
        "onchain": fetch_onchain(asset),
        "derivatives": fetch_derivatives(asset),
        "macro": fetch_macro(),
        "sentiment": fetch_sentiment(),
    }
