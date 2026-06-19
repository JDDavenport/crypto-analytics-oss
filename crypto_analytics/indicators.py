"""
indicators.py — pure-python TA over a close-price series. No numpy/pandas.
All functions are defensive: too-short input → None.
"""
from __future__ import annotations


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr_from_closes(closes: list[float], period: int = 14) -> float | None:
    """ATR proxy from close-to-close absolute moves (free CoinGecko history
    gives closes, not full OHLC). Conservative — slightly understates true
    range, so the liquidation guardrail errs toward MORE caution."""
    if len(closes) < period + 1:
        return None
    ranges = [abs(closes[i] - closes[i - 1]) for i in range(-period, 0)]
    return sum(ranges) / period


def swing_structure(closes: list[float], lookback: int = 30) -> str:
    """Crude HH/HL vs LH/LL read over the lookback window."""
    if len(closes) < lookback:
        return "unknown"
    window = closes[-lookback:]
    mid = len(window) // 2
    first_high, second_high = max(window[:mid]), max(window[mid:])
    first_low, second_low = min(window[:mid]), min(window[mid:])
    if second_high > first_high and second_low > first_low:
        return "uptrend"      # HH + HL
    if second_high < first_high and second_low < first_low:
        return "downtrend"    # LH + LL
    return "range"


def rsi_bullish_divergence(closes: list[float], period: int = 14, lookback: int = 30) -> bool:
    """Price makes a lower low but RSI makes a higher low → bullish divergence."""
    if len(closes) < lookback + period:
        return False
    mid = lookback // 2
    recent, prior = closes[-mid:], closes[-lookback:-mid]
    if not recent or not prior:
        return False
    price_lower_low = min(recent) < min(prior)
    rsi_recent = rsi(closes[-(period + mid):], period)
    rsi_prior = rsi(closes[-(period + lookback):-mid], period)
    if rsi_recent is None or rsi_prior is None:
        return False
    rsi_higher_low = rsi_recent > rsi_prior
    return price_lower_low and rsi_higher_low
