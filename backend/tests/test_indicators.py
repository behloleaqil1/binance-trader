import math

import pandas as pd
import pytest

from app.strategies.indicators import bollinger, ema, macd, rsi, sma


def test_ema_known_values():
    # span=3 → alpha=0.5: 1, 1.5, 2.25, 3.125, 4.0625
    out = ema(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert out.tolist() == pytest.approx([1.0, 1.5, 2.25, 3.125, 4.0625])


def test_sma_known_values():
    out = sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert math.isnan(out.iloc[0]) and math.isnan(out.iloc[1])
    assert out.iloc[2:].tolist() == pytest.approx([2.0, 3.0, 4.0])


def test_ema_of_constant_is_constant():
    out = ema(pd.Series([7.0] * 30), 10)
    assert out.tolist() == pytest.approx([7.0] * 30)


def test_rsi_extremes_and_flat():
    rising = rsi(pd.Series(range(1, 60), dtype=float), 14)
    assert rising.iloc[-1] == pytest.approx(100.0)
    falling = rsi(pd.Series(range(60, 1, -1), dtype=float), 14)
    assert falling.iloc[-1] == pytest.approx(0.0)
    flat = rsi(pd.Series([42.0] * 60), 14)
    assert flat.iloc[-1] == pytest.approx(50.0)  # neutral by convention
    # warmup rows are NaN
    assert math.isnan(rising.iloc[5])


def test_rsi_bounded_on_mixed_series():
    closes = [100 + ((-1) ** i) * (i % 7) for i in range(120)]
    out = rsi(pd.Series(closes, dtype=float), 14).dropna()
    assert ((out >= 0) & (out <= 100)).all()


def test_macd_zero_on_constant():
    line, signal, hist = macd(pd.Series([50.0] * 100))
    assert abs(line.iloc[-1]) < 1e-12
    assert abs(signal.iloc[-1]) < 1e-12
    assert abs(hist.iloc[-1]) < 1e-12


def test_macd_positive_in_uptrend():
    closes = [100 * 1.01 ** i for i in range(80)]
    _, _, hist = macd(pd.Series(closes))
    assert hist.iloc[-1] > 0


def test_bollinger_constant_collapses():
    mid, up, lo = bollinger(pd.Series([10.0] * 40), 20, 2.0)
    assert mid.iloc[-1] == up.iloc[-1] == lo.iloc[-1] == pytest.approx(10.0)


def test_bollinger_known_values():
    mid, up, lo = bollinger(pd.Series([1.0, 2.0, 3.0]), 3, 2.0)
    std = math.sqrt(2.0 / 3.0)  # population std of [1,2,3]
    assert mid.iloc[-1] == pytest.approx(2.0)
    assert up.iloc[-1] == pytest.approx(2.0 + 2 * std)
    assert lo.iloc[-1] == pytest.approx(2.0 - 2 * std)
