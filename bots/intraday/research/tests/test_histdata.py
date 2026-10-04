import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from bots.intraday.research import histdata as hd


def _m1_text(start="2024-01-02 09:30", n=30, px=4700.0):
    t = pd.date_range(start, periods=n, freq="1min")
    rows = [f"{x:%Y%m%d %H%M%S};{px + i:.2f};{px + i + 1:.2f};{px - 1 + i:.2f};{px + i + .5:.2f};0"
            for i, x in enumerate(t)]
    return "\n".join(rows) + "\n"


def test_parse_m1_converts_est_to_utc():
    df = hd.parse_m1(_m1_text(n=3))
    assert str(df.index[0]) == "2024-01-02 14:30:00+00:00"        # 09:30 EST = 14:30 UTC
    assert df["close"].iloc[0] == 4700.5 and len(df) == 3


def test_read_raw_from_zip_and_build(tmp_path):
    raw, broker_dir, out = tmp_path / "raw", tmp_path / "b", tmp_path / "o"
    raw.mkdir(); broker_dir.mkdir()
    with zipfile.ZipFile(raw / "HISTDATA_COM_ASCII_SPXUSD_M12024.zip", "w") as z:
        z.writestr("DAT_ASCII_SPXUSD_M1_2024.csv", _m1_text(n=60) + _m1_text("2024-01-03 09:30", 60))
        z.writestr("readme.txt", "x")
    m1 = hd.read_raw(raw, "SPXUSD")
    assert len(m1) == 120 and m1.index.is_monotonic_increasing
    # broker data starts on the second day (UTC), with spread 50 points
    idx = pd.date_range("2024-01-03 14:30", periods=12, freq="5min", tz="UTC")
    pd.DataFrame({"datetime": idx, "open": 4700.0, "high": 4701.0, "low": 4699.0,
                  "close": 4700.5, "volume": 1, "spread": 50}).to_csv(
        broker_dir / "US500_M5.csv.gz", index=False)
    (broker_dir / "US500_spec.json").write_text(json.dumps({"point": 0.01}))
    msg = hd.build_symbol("US500", "SPXUSD", raw, broker_dir, out)
    assert "US500" in msg and "2024" in msg
    df = pd.read_csv(out / "US500_M5.csv.gz", parse_dates=["datetime"]).set_index("datetime")
    assert df.index.is_unique and len(df) == 12 + 12          # 12 HistData M5 + 12 broker
    assert (df["spread"] == 50).all()
    first_broker = df.loc["2024-01-03 14:30:00+00:00"]
    assert first_broker["close"] == 4700.5 and first_broker["open"] == 4700.0
    spec = json.loads((out / "US500_spec.json").read_text())
    assert spec["source"].startswith("histdata:SPXUSD") and spec["histdata_years"] == [2024]
    assert spec["broker_gap_days_filled"] == 0


def test_missing_files_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        hd.read_raw(tmp_path, "SPXUSD")


def test_thin_broker_day_filled_from_histdata(tmp_path):
    raw, broker_dir, out = tmp_path / "raw", tmp_path / "b", tmp_path / "o"
    raw.mkdir(); broker_dir.mkdir()
    (raw / "DAT_ASCII_SPXUSD_M1_2024.csv").write_text(
        _m1_text(n=60) + _m1_text("2024-01-03 09:30", 60) + _m1_text("2024-01-04 09:30", 60))
    full = pd.date_range("2024-01-02 14:30", periods=12, freq="5min", tz="UTC")
    thin = pd.date_range("2024-01-03 14:30", periods=3, freq="5min", tz="UTC")   # 3 of 12
    full2 = pd.date_range("2024-01-04 14:30", periods=12, freq="5min", tz="UTC")
    idx = full.append(thin).append(full2)
    pd.DataFrame({"datetime": idx, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                  "volume": 1, "spread": 50}).to_csv(broker_dir / "US500_M5.csv.gz", index=False)
    (broker_dir / "US500_spec.json").write_text(json.dumps({"point": 0.01}))
    hd.build_symbol("US500", "SPXUSD", raw, broker_dir, out)
    df = pd.read_csv(out / "US500_M5.csv.gz", parse_dates=["datetime"]).set_index("datetime")
    day3 = df.loc["2024-01-03"]
    assert len(day3) == 12 and (day3["close"] > 100).all()     # HistData's whole day
    assert (df.loc["2024-01-04", "close"] == 1.0).all()         # broker's full day kept
