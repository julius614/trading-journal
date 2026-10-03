import numpy as np
import pandas as pd
import pytest

from bots.amd_fx.quantitative_filters import (
    atr, kalman_filter_1d, kalman_zscore, range_within_atr, volatility_spike,
)


def series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="5min"))


def test_kalman_tracks_a_constant():
    est = kalman_filter_1d(np.full(100, 1.1))
    assert np.allclose(est, 1.1)


def test_kalman_lags_a_step_and_converges():
    est = kalman_filter_1d(np.r_[np.full(50, 1.0), np.full(200, 2.0)], q_ratio=0.01,
                           measurement_var=0.01)
    assert est[50] < 1.5            # smooths the jump
    assert est[-1] == pytest.approx(2.0, abs=1e-3)


def test_kalman_rejects_bad_input():
    with pytest.raises(ValueError):
        kalman_filter_1d([])
    with pytest.raises(ValueError):
        kalman_filter_1d([1.0, 2.0], q_ratio=0)


def test_zscore_sign_after_drop_and_spike():
    rng = np.random.default_rng(1)
    base = 1.1 + rng.normal(0, 0.0001, 200)
    down = series(np.r_[base, base[-1] - 0.0030])
    up = series(np.r_[base, base[-1] + 0.0030])
    assert kalman_zscore(down, window=50).iloc[-1] < -1.5
    assert kalman_zscore(up, window=50).iloc[-1] > 1.5


def test_zscore_nan_until_window_full():
    z = kalman_zscore(series(np.linspace(1.0, 1.1, 60)), window=50)
    assert z.iloc[:49].isna().all()
    assert np.isfinite(z.iloc[-1])


def test_kalman_is_causal_with_fixed_noise():
    rng = np.random.default_rng(2)
    prices = 1.1 + np.cumsum(rng.normal(0, 0.0002, 300))
    # with R fixed, appending a future spike must not change earlier estimates
    est_a = kalman_filter_1d(prices[:200], measurement_var=1e-8)
    est_b = kalman_filter_1d(np.r_[prices[:200], 5.0], measurement_var=1e-8)
    assert np.allclose(est_a, est_b[:200])


def test_volatility_spike():
    # steady alternating moves: recent volatility equals the baseline (ratio ~1)
    calm = 1.1 * np.exp(np.cumsum(np.tile([0.0001, -0.0001], 20)))
    jumpy = np.r_[calm, calm[-1] * np.exp(np.cumsum([0.002, -0.0025, 0.003]))]
    spike, ratio = volatility_spike(series(jumpy), 3, 20, 1.3)
    assert spike and ratio > 1.3
    spike, ratio = volatility_spike(series(calm), 3, 20, 1.3)
    assert not spike


def test_volatility_spike_needs_enough_bars():
    assert volatility_spike(series([1.0, 1.1, 1.2]), 3, 20)[0] is False


def test_atr_and_range_gate():
    df = pd.DataFrame({"high": [1.2] * 30, "low": [1.1] * 30, "close": [1.15] * 30})
    assert atr(df, 14).iloc[-1] == pytest.approx(0.1)
    assert range_within_atr(0.15, 0.1, 2.0)
    assert not range_within_atr(0.25, 0.1, 2.0)
    assert not range_within_atr(0.05, None, 2.0)   # fail safe without ATR
