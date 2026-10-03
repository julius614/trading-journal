import pandas as pd
import pytest

from bots.amd_fx.research.load_data import to_m5, validate


def test_to_m5_aggregates_ohlc():
    idx = pd.date_range("2016-03-01 07:00", periods=10, freq="1min", tz="UTC")
    m1 = pd.DataFrame({"open": range(10), "high": [x + 0.5 for x in range(10)],
                       "low": [x - 0.5 for x in range(10)], "close": [x + 0.1 for x in range(10)]},
                      index=idx, dtype=float)
    m5 = to_m5(m1)
    assert list(m5.index) == [pd.Timestamp("2016-03-01 07:00", tz="UTC"),
                              pd.Timestamp("2016-03-01 07:05", tz="UTC")]
    assert m5.iloc[0].tolist() == [0.0, 4.5, -0.5, 4.1]


def test_validate_rejects_saturday_bars():
    idx = pd.DatetimeIndex([pd.Timestamp("2016-03-04 20:55", tz="UTC"),
                            pd.Timestamp("2016-03-05 09:00", tz="UTC")])
    bars = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    with pytest.raises(ValueError, match="failed validation"):
        validate("EURUSD", bars)
