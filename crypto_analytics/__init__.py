"""
crypto_analytics — coin-agnostic crypto analytics engine.

⛔ EDUCATIONAL / ADVISORY ONLY. This package NEVER executes trades. It holds NO
exchange API keys, places NO orders, and has NO order-execution module. It
ingests FREE public market data for ANY cryptocurrency, scores a 5-layer
confluence signal (TA / derivatives / on-chain / macro / sentiment) into an
entry ZONE + INVALIDATION level + CONFIDENCE %, and runs a LIQUIDATION-DISTANCE
GUARDRAIL that REFUSES reckless leverage. This is NOT financial advice.
"""
from .config import Asset

__all__ = ["Asset", "data", "scorer", "guardrail", "analyzer", "indicators", "config"]
__version__ = "1.0.0"
