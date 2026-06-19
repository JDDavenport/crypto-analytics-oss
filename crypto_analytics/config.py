"""
config.py — generic, coin-agnostic tunables for the analytics engine.

Nothing here is user-specific. The asset is supplied at call time (see
``Asset``), not hard-coded. Risk caps are conservative by design — they are the
responsible default for an EDUCATIONAL tool, not a personalized risk budget.

Override any default via environment variables (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Asset — supplied per request, NOT hard-coded.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Asset:
    """A single cryptocurrency to analyze.

    ``coingecko_id``  — the CoinGecko API id (e.g. "bitcoin", "ethereum",
                        "curve-dao-token"). This is the canonical handle.
    ``symbol``        — display/derivatives ticker (e.g. "BTC", "ETH").
    ``defillama_slug``— OPTIONAL DefiLlama protocol slug for the on-chain TVL
                        layer (e.g. "uniswap", "aave"). Many coins (BTC, ETH)
                        are not single protocols — leave None and the on-chain
                        layer degrades to neutral. That is expected and honest.
    """
    coingecko_id: str
    symbol: str
    defillama_slug: str | None = None


# ---------------------------------------------------------------------------
# Risk / guardrail caps — conservative educational defaults.
# ---------------------------------------------------------------------------
# The liquidation-distance guardrail will REFUSE to bless any leverage above
# MAX_LEVERAGE, or any setup whose liquidation sits within LIQ_ATR_BUFFER ATRs
# of entry. These are deliberately strict. They are not a substitute for your
# own judgment. This is educational software, not advice.
MAX_LEVERAGE = float(os.getenv("CA_MAX_LEVERAGE", "3.0"))
ABSOLUTE_REFUSE_LEVERAGE = MAX_LEVERAGE
MAINTENANCE_MARGIN_RATE = float(os.getenv("CA_MMR", "0.005"))  # ~0.5%, typical major perps
LIQ_ATR_BUFFER = float(os.getenv("CA_LIQ_ATR_BUFFER", "1.0"))

# ---------------------------------------------------------------------------
# Scorer weights (sum need not be 1; normalized internally over AVAILABLE
# layers). Heavier on derivatives + structure for timing; on-chain + macro for
# regime. Tune to taste.
# ---------------------------------------------------------------------------
LAYER_WEIGHTS = {
    "ta": float(os.getenv("CA_W_TA", "0.28")),
    "derivatives": float(os.getenv("CA_W_DERIVATIVES", "0.27")),
    "onchain": float(os.getenv("CA_W_ONCHAIN", "0.20")),
    "macro": float(os.getenv("CA_W_MACRO", "0.15")),
    "sentiment": float(os.getenv("CA_W_SENTIMENT", "0.10")),
}

# --- TA params -----------------------------------------------------------
RSI_PERIOD = 14
MA_FAST = 50
MA_SLOW = 200
ATR_PERIOD = 14
