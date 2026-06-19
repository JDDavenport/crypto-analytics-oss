"""
guardrail.py — the responsible core. The liquidation-distance guardrail.

Given a proposed entry price + intended leverage, it computes the liquidation
price for a LONG and REFUSES (verdict=REFUSE) any setup where:
  1. leverage > MAX_LEVERAGE (default 3x), OR
  2. the liquidation price sits within LIQ_ATR_BUFFER (~1) ATR of entry.

It does not advise around reckless leverage — it refuses and explains why, in
plain language, with the math. This is the feature, not a limitation.

Liquidation (long) ≈ Entry × (1 − 1/Leverage + MMR).

⛔ This module computes prices ONLY. It places NO orders. It is pure math.
   This is educational software, NOT financial advice.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass
class GuardrailVerdict:
    verdict: str            # "REFUSE" | "PASS"
    leverage: float
    entry: float
    liquidation_price: float
    atr: float | None
    liq_distance_pct: float          # % drop from entry to liquidation
    liq_distance_in_atr: float | None
    reasons: list[str]
    explanation: str


def liquidation_price_long(entry: float, leverage: float,
                           mmr: float = config.MAINTENANCE_MARGIN_RATE) -> float:
    """Liquidation price for a LONG. Entry × (1 − 1/L + MMR)."""
    if leverage <= 0:
        raise ValueError("leverage must be > 0")
    return entry * (1 - 1 / leverage + mmr)


def evaluate(entry: float, leverage: float, atr: float | None = None,
             symbol: str = "the asset",
             max_leverage: float = config.ABSOLUTE_REFUSE_LEVERAGE,
             atr_buffer: float = config.LIQ_ATR_BUFFER) -> GuardrailVerdict:
    """Run the guardrail. Returns REFUSE or PASS with a full explanation."""
    if entry <= 0:
        raise ValueError("entry must be > 0")

    liq = liquidation_price_long(entry, leverage)
    liq_distance_pct = (entry - liq) / entry * 100
    liq_distance_in_atr = ((entry - liq) / atr) if atr else None

    reasons: list[str] = []

    # Rule 1: leverage cap.
    if leverage > max_leverage:
        reasons.append(
            f"leverage {leverage:g}x exceeds the {max_leverage:g}x hard cap — "
            f"this tool NEVER blesses leverage above {max_leverage:g}x."
        )

    # Rule 2: liquidation inside ~1 ATR of entry.
    if atr is not None and liq_distance_in_atr is not None:
        if liq_distance_in_atr < atr_buffer:
            reasons.append(
                f"liquidation sits {liq_distance_in_atr:.2f} ATR below entry "
                f"(< {atr_buffer:g} ATR buffer). A single normal daily range for "
                f"{symbol} would liquidate this position."
            )
    elif atr is None:
        reasons.append("ATR unavailable — cannot verify liquidation is outside a "
                       "normal daily range; defaulting to caution.")

    verdict = "REFUSE" if reasons else "PASS"

    if verdict == "REFUSE":
        explanation = (
            f"REFUSE. Entry {entry:g} at {leverage:g}x → liquidation "
            f"≈ {liq:g} (only {liq_distance_pct:.1f}% below entry"
            + (f", {liq_distance_in_atr:.2f} ATR" if liq_distance_in_atr is not None else "")
            + "). " + " ".join(reasons)
            + " Safer pattern: hold the core thesis in SPOT (no liquidation), use "
            "low leverage only with a hard stop at the invalidation level, and "
            "size so a stop-out is a survivable loss."
        )
    else:
        explanation = (
            f"PASS. Entry {entry:g} at {leverage:g}x → liquidation "
            f"≈ {liq:g} ({liq_distance_pct:.1f}% below entry"
            + (f", {liq_distance_in_atr:.2f} ATR" if liq_distance_in_atr is not None else "")
            + "). Liquidation sits outside one normal daily range AND leverage is "
            f"within the {max_leverage:g}x cap. Still: use the invalidation level as "
            "a hard stop and size so a stop-out is a survivable loss."
        )

    return GuardrailVerdict(
        verdict=verdict,
        leverage=leverage,
        entry=entry,
        liquidation_price=round(liq, 8),
        atr=atr,
        liq_distance_pct=round(liq_distance_pct, 2),
        liq_distance_in_atr=round(liq_distance_in_atr, 3) if liq_distance_in_atr is not None else None,
        reasons=reasons,
        explanation=explanation,
    )
