"""
test_scorer.py — scorer behavior with synthetic data, incl. graceful degradation.
"""
from crypto_analytics import scorer, indicators
from crypto_analytics.config import Asset

BTC = Asset(coingecko_id="bitcoin", symbol="BTC")


def _uptrend_closes(n=250, start=0.20, step=0.001):
    return [start + step * i for i in range(n)]


def _downtrend_closes(n=250, start=0.45, step=0.001):
    return [start - step * i for i in range(n)]


def test_indicators_basic():
    closes = _uptrend_closes()
    assert indicators.sma(closes, 50) is not None
    assert indicators.rsi(closes, 14) is not None
    assert indicators.atr_from_closes(closes, 14) is not None
    assert indicators.swing_structure(closes) == "uptrend"


def test_indicators_too_short_returns_none():
    assert indicators.sma([1, 2], 50) is None
    assert indicators.rsi([1, 2], 14) is None


def test_all_layers_dark_scores_neutral_and_low_confidence():
    data = {
        "price": {"available": False},
        "ohlc": {"available": False, "note": "x"},
        "onchain": {"available": False},
        "derivatives": {"available": False},
        "macro": {"available": False},
        "sentiment": {"available": False},
    }
    sig = scorer.score(data, asset=BTC)
    assert sig.confluence == 0.0
    assert sig.confidence_pct == 0.0
    assert sig.entry_zone is None
    assert sig.symbol == "BTC"
    assert all(not l.available for l in sig.layers.values())


def test_bullish_alignment_raises_confidence():
    data = {
        "price": {"available": True, "price": 0.24, "change_24h": 1.0},
        "ohlc": {"available": True, "closes": _downtrend_closes()},
        "onchain": {"available": True, "tvl_change_7d_pct": 15.0, "tvl_change_30d_pct": 30.0},
        "derivatives": {"available": True, "avg_funding_rate": -0.001},
        "macro": {"available": True, "dxy_change_20d_pct": -2.0, "ffr_change_20d_bps": -10},
        "sentiment": {"available": True, "fear_greed": 15, "classification": "Extreme Fear"},
    }
    sig = scorer.score(data, asset=BTC)
    assert sig.confluence > 0.2
    assert sig.confidence_pct > 55
    assert sig.entry_zone is not None
