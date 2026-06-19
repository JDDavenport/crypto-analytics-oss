"""
scorer.py — 5-layer confluence scorer, coin-agnostic.

Each layer emits a normalized sub-score in [-1, +1] (+1 = strongly favorable for
a LONG entry, -1 = strongly unfavorable). Unavailable layers score 0.0 (neutral)
and are flagged so confidence is discounted by data coverage — the engine never
pretends it has data it doesn't. The weighted sum → confidence %, plus an entry
ZONE and an INVALIDATION level.

No single layer triggers a call — alignment (confluence) does.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config, indicators
from .config import Asset


@dataclass
class LayerScore:
    name: str
    score: float          # -1 .. +1
    available: bool
    detail: str


@dataclass
class Signal:
    asset: str
    symbol: str
    price: float | None
    layers: dict[str, LayerScore]
    confluence: float                 # -1 .. +1 weighted
    confidence_pct: float             # 0 .. 100
    entry_zone: tuple[float, float] | None
    invalidation: float | None
    atr: float | None
    regime: str
    notes: list[str] = field(default_factory=list)


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Individual layers
# ---------------------------------------------------------------------------
def score_ta(ohlc: dict, price: float | None) -> LayerScore:
    if not ohlc.get("available") or price is None:
        return LayerScore("ta", 0.0, False, ohlc.get("note", "no ohlc"))
    closes = ohlc["closes"]
    s = 0.0
    bits = []

    ma50 = indicators.sma(closes, config.MA_FAST)
    ma200 = indicators.sma(closes, config.MA_SLOW)
    if ma50 and ma200:
        if price > ma50:
            s += 0.2; bits.append("px>50DMA")
        else:
            s -= 0.15; bits.append("px<50DMA")
        if ma50 > ma200:
            s += 0.2; bits.append("golden")
        else:
            s -= 0.1; bits.append("death-cross")

    r = indicators.rsi(closes, config.RSI_PERIOD)
    if r is not None:
        if r < 30:
            s += 0.3; bits.append(f"RSI {r:.0f} oversold")
        elif r > 70:
            s -= 0.3; bits.append(f"RSI {r:.0f} overbought")
        else:
            bits.append(f"RSI {r:.0f}")

    if indicators.rsi_bullish_divergence(closes):
        s += 0.25; bits.append("bull-div")

    struct = indicators.swing_structure(closes)
    if struct == "uptrend":
        s += 0.2
    elif struct == "downtrend":
        s -= 0.2
    bits.append(struct)

    return LayerScore("ta", _clamp(s), True, ", ".join(bits))


def score_derivatives(deriv: dict) -> LayerScore:
    if not deriv.get("available"):
        return LayerScore("derivatives", 0.0, False, deriv.get("note", "no derivs"))
    s = 0.0
    bits = []
    f = deriv.get("avg_funding_rate")
    if f is not None:
        # Deeply negative funding at a low = crowded shorts = squeeze fuel (bullish).
        if f < -0.0005:
            s += 0.6; bits.append(f"funding {f:.4%} (shorts crowded → squeeze fuel)")
        elif f > 0.0005:
            s -= 0.4; bits.append(f"funding {f:.4%} (longs crowded → risk)")
        else:
            bits.append(f"funding {f:.4%} neutral")
    return LayerScore("derivatives", _clamp(s), True, ", ".join(bits) or "neutral")


def score_onchain(onchain: dict) -> LayerScore:
    if not onchain.get("available"):
        return LayerScore("onchain", 0.0, False, onchain.get("note", "no onchain"))
    s = 0.0
    bits = []
    t7 = onchain.get("tvl_change_7d_pct")
    t30 = onchain.get("tvl_change_30d_pct")
    if t7 is not None:
        s += _clamp(t7 / 20.0) * 0.5   # +20% TVL/7d → +0.5
        bits.append(f"TVL 7d {t7:+.1f}%")
    if t30 is not None:
        s += _clamp(t30 / 40.0) * 0.5
        bits.append(f"TVL 30d {t30:+.1f}%")
    return LayerScore("onchain", _clamp(s), True, ", ".join(bits))


def score_macro(macro: dict) -> LayerScore:
    if not macro.get("available"):
        return LayerScore("macro", 0.0, False, macro.get("note", "no macro"))
    s = 0.0
    bits = []
    dxy_chg = macro.get("dxy_change_20d_pct")
    if dxy_chg is not None:
        # Strong/rising dollar = risk-off (bearish crypto). Falling DXY = bullish.
        s += _clamp(-dxy_chg / 3.0) * 0.6
        bits.append(f"DXY 20d {dxy_chg:+.1f}%")
    ffr_bps = macro.get("ffr_change_20d_bps")
    if ffr_bps is not None:
        s += _clamp(-ffr_bps / 50.0) * 0.4   # hikes = risk-off
        bits.append(f"FFR Δ {ffr_bps:+.0f}bps")
    return LayerScore("macro", _clamp(s), True, ", ".join(bits) or "neutral")


def score_sentiment(sent: dict) -> LayerScore:
    if not sent.get("available"):
        return LayerScore("sentiment", 0.0, False, sent.get("note", "no sentiment"))
    fg = sent.get("fear_greed")
    if fg is None:
        return LayerScore("sentiment", 0.0, False, "no F&G value")
    # Contrarian: extreme fear (<25) is bullish for accumulation; greed (>75) bearish.
    s = _clamp((50 - fg) / 50.0)   # fg=0 → +1, fg=100 → -1
    return LayerScore("sentiment", s, True, f"F&G {fg} ({sent.get('classification','')})")


# ---------------------------------------------------------------------------
# Confluence aggregation
# ---------------------------------------------------------------------------
def score(data: dict, asset: Asset | None = None) -> Signal:
    price_d = data.get("price", {})
    price = price_d.get("price") if price_d.get("available") else None
    ohlc = data.get("ohlc", {})

    layers = {
        "ta": score_ta(ohlc, price),
        "derivatives": score_derivatives(data.get("derivatives", {})),
        "onchain": score_onchain(data.get("onchain", {})),
        "macro": score_macro(data.get("macro", {})),
        "sentiment": score_sentiment(data.get("sentiment", {})),
    }

    # Weighted confluence over AVAILABLE layers only; renormalize weights so a
    # missing layer doesn't silently drag the score to 0.
    avail_weight = sum(config.LAYER_WEIGHTS[n] for n, l in layers.items() if l.available)
    if avail_weight <= 0:
        confluence = 0.0
    else:
        confluence = sum(
            config.LAYER_WEIGHTS[n] * l.score
            for n, l in layers.items() if l.available
        ) / avail_weight

    # Confidence: map confluence [-1,1] → [0,100], then DISCOUNT by data coverage.
    coverage = avail_weight / sum(config.LAYER_WEIGHTS.values())
    raw_conf = (confluence + 1) / 2 * 100
    confidence = raw_conf * coverage

    # Entry zone + invalidation from TA structure.
    atr = None
    entry_zone = None
    invalidation = None
    notes = []
    if ohlc.get("available") and price is not None:
        closes = ohlc["closes"]
        atr = indicators.atr_from_closes(closes, config.ATR_PERIOD)
        recent_low = min(closes[-30:]) if len(closes) >= 30 else min(closes)
        if atr:
            zone_low = min(recent_low, price - atr)
            zone_high = price if price < recent_low + 2 * atr else recent_low + 2 * atr
            entry_zone = (round(zone_low, 6), round(max(zone_high, zone_low + atr), 6))
            invalidation = round(recent_low - atr, 6)
    else:
        notes.append("TA/price unavailable — zone+invalidation cannot be computed")

    # Regime read (macro+onchain).
    regime_score = 0.0
    n = 0
    for nm in ("macro", "onchain"):
        if layers[nm].available:
            regime_score += layers[nm].score; n += 1
    regime = "neutral"
    if n:
        avg = regime_score / n
        regime = "hostile" if avg < -0.3 else "favorable" if avg > 0.3 else "neutral"

    dark = [n for n, l in layers.items() if not l.available]
    if dark:
        notes.append(f"layers unavailable (scored neutral): {', '.join(dark)}")

    return Signal(
        asset=asset.coingecko_id if asset else (price_d.get("id") or "unknown"),
        symbol=asset.symbol if asset else "?",
        price=price,
        layers=layers,
        confluence=round(confluence, 4),
        confidence_pct=round(confidence, 1),
        entry_zone=entry_zone,
        invalidation=invalidation,
        atr=round(atr, 8) if atr else None,
        regime=regime,
        notes=notes,
    )
