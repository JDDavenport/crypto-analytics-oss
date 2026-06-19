"""
analyzer.py — orchestrator + CLI for the coin-agnostic analytics engine.

Pipeline: resolve coin → data.fetch_all(asset) → scorer.score() →
guardrail.evaluate() → state dict (optionally written to JSON).

⛔ ADVISORY / EDUCATIONAL ONLY. There is NO trade-execution path anywhere in
this package. No exchange API keys. No orders. Not financial advice.

CLI:
    python -m crypto_analytics.analyzer bitcoin
    python -m crypto_analytics.analyzer ethereum --leverage 10
    python -m crypto_analytics.analyzer curve-dao-token --symbol CRV --defillama curve-dex
    python -m crypto_analytics.analyzer bitcoin --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import config, data, guardrail, scorer
from .config import Asset

DISCLAIMER = (
    "EDUCATIONAL ONLY — NOT FINANCIAL ADVICE. This tool does not execute trades, "
    "holds no exchange keys, and makes no guarantees. Leverage trading can lose "
    "you more than your deposit. Do your own research."
)

COINGECKO_API = "https://api.coingecko.com/api/v3"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_asset(coin: str, symbol: str | None = None,
                  defillama: str | None = None) -> Asset:
    """Build an Asset from a CoinGecko id (or, best-effort, a symbol/name).

    If `coin` looks like a symbol/name rather than an id, we try the CoinGecko
    /search endpoint to resolve it to the canonical id. Degrades to using the
    input verbatim on any failure.
    """
    cid = coin.strip().lower()
    sym = (symbol or coin).strip().upper()
    if not symbol:
        # Try to resolve id + a proper symbol via CoinGecko search.
        try:
            url = f"{COINGECKO_API}/search?query={urllib.parse.quote(coin)}"
            req = urllib.request.Request(url, headers={"User-Agent": "crypto-analytics-oss/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                d = json.loads(resp.read().decode())
            coins = d.get("coins", [])
            if coins:
                # Prefer an exact id match, else the top (highest market-cap rank) hit.
                exact = next((c for c in coins if c.get("id") == cid), None)
                best = exact or coins[0]
                cid = best.get("id", cid)
                sym = (best.get("symbol") or sym).upper()
        except Exception:
            pass
    return Asset(coingecko_id=cid, symbol=sym, defillama_slug=defillama)


def analyze(asset: Asset, intended_leverage: float | None = None) -> dict:
    """Run the full pipeline for an asset. Returns the state dict."""
    raw = data.fetch_all(asset)
    sig = scorer.score(raw, asset=asset)

    guard_results = {}
    if sig.price:
        entry = sig.entry_zone[1] if sig.entry_zone else sig.price
        lev_to_check = intended_leverage if intended_leverage else config.MAX_LEVERAGE
        guard_results["intended"] = guardrail.evaluate(
            entry, lev_to_check, sig.atr, symbol=sig.symbol).__dict__
        # Always document a reckless 10x case so the output shows the refusal.
        guard_results["ten_x"] = guardrail.evaluate(
            entry, 10.0, sig.atr, symbol=sig.symbol).__dict__

    return {
        "last_run": _utcnow(),
        "asset": sig.asset,
        "symbol": sig.symbol,
        "advisory_only": True,
        "educational_only": True,
        "execution_path_exists": False,
        "disclaimer": DISCLAIMER,
        "price": sig.price,
        "price_change_24h": raw.get("price", {}).get("change_24h"),
        "market_cap": raw.get("price", {}).get("market_cap"),
        "atr": sig.atr,
        "regime": sig.regime,
        "confluence": sig.confluence,
        "confidence_pct": sig.confidence_pct,
        "entry_zone": list(sig.entry_zone) if sig.entry_zone else None,
        "invalidation": sig.invalidation,
        "layer_scores": {
            n: {"score": l.score, "available": l.available, "detail": l.detail}
            for n, l in sig.layers.items()
        },
        "guardrail": guard_results,
        "notes": sig.notes,
        "data_availability": {k: v.get("available", False) for k, v in raw.items()},
    }


def _price_in_zone(state: dict) -> bool:
    z = state.get("entry_zone")
    p = state.get("price")
    if not z or p is None:
        return False
    return z[0] <= p <= z[1]


def format_scorecard(state: dict) -> str:
    p = state.get("price")
    z = state.get("entry_zone")
    g = (state.get("guardrail") or {}).get("intended", {})
    sym = state.get("symbol", "?")
    lines = [
        f"{sym} ANALYTICS — {state['last_run'][:16]}Z  [EDUCATIONAL ONLY]",
        f"price: ${p:g}" if p else "price: N/A",
        f"regime: {state.get('regime')}  | confidence: {state.get('confidence_pct')}%",
        f"entry zone: ${z[0]:g}–${z[1]:g}" if z else "entry zone: N/A (TA dark)",
        f"invalidation: ${state.get('invalidation'):g}" if state.get("invalidation") else "invalidation: N/A",
        f"in-zone now: {'YES' if _price_in_zone(state) else 'no'}",
        "",
        "layers:",
    ]
    for n, l in state.get("layer_scores", {}).items():
        flag = "" if l["available"] else " [DARK→neutral]"
        lines.append(f"  {n:>11}: {l['score']:+.2f}{flag}  {l['detail']}")
    if g:
        lines += ["", f"guardrail (@{g['leverage']:g}x): {g['verdict']}", f"  {g['explanation']}"]
    if state.get("notes"):
        lines += ["", "notes: " + "; ".join(state["notes"])]
    lines += ["", "⚠ " + DISCLAIMER]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Coin-agnostic crypto analytics (EDUCATIONAL — no execution).")
    ap.add_argument("coin", help="CoinGecko id, symbol, or name (e.g. bitcoin, ETH, solana)")
    ap.add_argument("--symbol", default=None, help="Override derivatives ticker (e.g. BTC)")
    ap.add_argument("--defillama", default=None,
                    help="DefiLlama protocol slug for the on-chain TVL layer (optional)")
    ap.add_argument("--leverage", type=float, default=None,
                    help="Intended leverage to run through the guardrail")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of a scorecard")
    args = ap.parse_args()

    asset = resolve_asset(args.coin, args.symbol, args.defillama)
    state = analyze(asset, intended_leverage=args.leverage)

    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(format_scorecard(state))
        if state.get("price") is None:
            print(f"\n(could not resolve price for '{args.coin}' — check the CoinGecko id)",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
