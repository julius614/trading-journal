import json
import lzma
from datetime import date

import numpy as np
import pandas as pd
import pytest

from bots.intraday.research import dukascopy as dk


def _bi5(minutes, base=4_000_000, vol=1.0):
    rec = np.zeros(len(minutes), dtype=dk.RECORD)
    rec["t"] = np.asarray(minutes) * 60
    rec["o"] = base + np.arange(len(minutes))
    rec["c"] = rec["o"] + 1
    rec["l"] = rec["o"] - 2
    rec["h"] = rec["o"] + 3
    rec["v"] = vol
    return lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)


def test_decode_bi5_times_fields_and_closed_minutes():
    raw = _bi5(range(0, 10))
    df = dk.decode_bi5(raw, date(2024, 1, 15))
    assert len(df) == 10 and str(df.index[0]) == "2024-01-15 00:00:00+00:00"
    assert df["high"].iloc[0] == 4_000_003 and df["low"].iloc[0] == 3_999_998
    assert df["close"].iloc[0] == 4_000_001
    assert dk.decode_bi5(_bi5(range(5), vol=0.0), date(2024, 1, 15)).empty
    assert dk.decode_bi5(b"", date(2024, 1, 15)).empty


def test_to_m5_aggregates():
    df = dk.decode_bi5(_bi5(range(10)), date(2024, 1, 15))
    m5 = dk.to_m5(df)
    assert len(m5) == 2
    first = m5.iloc[0]
    assert first["open"] == 4_000_000 and first["close"] == 4_000_005
    assert first["high"] == 4_000_007 and first["volume"] == 5


def test_price_scale_power_of_ten():
    assert dk.price_scale(pd.Series([4_000_000.0]), pd.Series([4012.5])) == pytest.approx(1e-3)
    assert dk.price_scale(pd.Series([108_500.0]), pd.Series([1.0851])) == pytest.approx(1e-5)


def test_spread_profile_by_utc_hour_of_week():
    idx = pd.date_range("2024-01-15", periods=24 * 7 * 12, freq="5min", tz="UTC")
    b = pd.DataFrame({"spread_price": np.where(idx.hour == 14, 0.5, 0.1)}, index=idx)
    prof = dk.spread_profile(b, 0.01)
    assert prof[0 * 24 + 14] == pytest.approx(50) and prof[0 * 24 + 3] == pytest.approx(10)
    assert len(prof) == 168 and prof.notna().all()


def test_build_symbol_offline(tmp_path, monkeypatch):
    broker_dir, out = tmp_path / "b", tmp_path / "o"
    broker_dir.mkdir()
    idx = pd.date_range("2024-01-16", periods=288 * 3, freq="5min", tz="UTC")
    px = 4000.0 + np.arange(len(idx)) * 0.005
    pd.DataFrame({"datetime": idx, "open": px, "high": px, "low": px, "close": px + 0.001,
                  "volume": 1, "spread": 40}).to_csv(broker_dir / "US500_M5.csv.gz", index=False)
    (broker_dir / "US500_spec.json").write_text(json.dumps({"point": 0.01}))

    def fake_fetch(inst, day, cache):
        return dk.decode_bi5(_bi5(range(1440), base=4_000_000 + (day.day - 15) * 1440), day)

    monkeypatch.setattr(dk, "fetch_day", fake_fetch)
    msg = dk.build_symbol("US500", "USA500IDXUSD", date(2024, 1, 15), date(2024, 1, 19),
                          broker_dir, out, workers=2)
    assert "US500" in msg
    df = pd.read_csv(out / "US500_M5.csv.gz")
    spec = json.loads((out / "US500_spec.json").read_text())
    assert spec["price_scale"] == pytest.approx(1e-3) and spec["source"].startswith("dukascopy")
    assert df["spread"].median() == pytest.approx(40)
    assert 3990 < df["close"].median() < 4010
