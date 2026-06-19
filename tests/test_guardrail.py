"""
test_guardrail.py — CRITICAL. The guardrail must REFUSE reckless leverage and
any setup where liquidation sits within 1 ATR of entry, for ANY coin.
"""
import math

from crypto_analytics import guardrail
from crypto_analytics.config import MAINTENANCE_MARGIN_RATE


def test_liquidation_price_long_math():
    liq = guardrail.liquidation_price_long(0.24, 10.0)
    assert math.isclose(liq, 0.24 * (1 - 1 / 10 + MAINTENANCE_MARGIN_RATE), rel_tol=1e-9)
    assert 0.215 < liq < 0.219  # ~10% below entry


def test_refuses_reckless_10x():
    """10x on a low-priced coin with a normal ATR MUST be refused."""
    v = guardrail.evaluate(entry=0.24, leverage=10.0, atr=0.012, symbol="EXAMPLE")
    assert v.verdict == "REFUSE"
    assert v.leverage == 10.0
    assert any("10x" in r or "exceeds" in r for r in v.reasons)
    assert "REFUSE" in v.explanation
    assert v.liquidation_price < 0.22


def test_refuses_10x_on_btc_scale_price():
    """Generalization check: same refusal at a $60k price scale."""
    v = guardrail.evaluate(entry=60000.0, leverage=10.0, atr=2500.0, symbol="BTC")
    assert v.verdict == "REFUSE"
    assert any("exceeds" in r for r in v.reasons)


def test_refuses_leverage_above_cap_even_if_liq_far():
    v = guardrail.evaluate(entry=0.24, leverage=5.0, atr=1.0)
    assert v.verdict == "REFUSE"
    assert any("exceeds" in r for r in v.reasons)


def test_refuses_liq_inside_one_atr_even_at_legal_leverage():
    v = guardrail.evaluate(entry=0.24, leverage=3.0, atr=0.10)
    assert v.verdict == "REFUSE"
    assert any("ATR" in r for r in v.reasons)


def test_passes_conservative_3x_with_room():
    v = guardrail.evaluate(entry=0.24, leverage=3.0, atr=0.005)
    assert v.verdict == "PASS"
    assert not v.reasons
    assert v.liq_distance_in_atr is not None and v.liq_distance_in_atr >= 1.0


def test_passes_spot_like_2x():
    v = guardrail.evaluate(entry=0.24, leverage=2.0, atr=0.005)
    assert v.verdict == "PASS"


def test_missing_atr_defaults_to_caution():
    v = guardrail.evaluate(entry=0.24, leverage=3.0, atr=None)
    assert v.verdict == "REFUSE"
    assert any("ATR unavailable" in r for r in v.reasons)
