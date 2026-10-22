import numpy as np
import pandas as pd
import pytest

from bots.kb import prices, trades


def _deals():
    t = lambda s: pd.Timestamp(s, tz="UTC")
    return pd.DataFrame([
        # position 10: buy 1.0, closed in two halves
        dict(ticket=1, position_id=10, type=0, entry=0, volume=1.0, price=1.1000, time=t("2024-03-04 09:00"),
             profit=0.0, commission=-3.5, swap=0.0, fee=0.0, symbol="EURUSD", magic=0, comment=""),
        dict(ticket=2, position_id=10, type=1, entry=1, volume=0.5, price=1.1010, time=t("2024-03-04 10:00"),
             profit=50.0, commission=-1.75, swap=0.0, fee=0.0, symbol="EURUSD", magic=0, comment=""),
        dict(ticket=3, position_id=10, type=1, entry=1, volume=0.5, price=1.1030, time=t("2024-03-04 11:00"),
             profit=150.0, commission=-1.75, swap=0.0, fee=0.0, symbol="EURUSD", magic=0, comment=""),
        # position 11: still open -> skipped
        dict(ticket=4, position_id=11, type=1, entry=0, volume=1.0, price=1.2, time=t("2024-03-05 09:00"),
             profit=0.0, commission=0.0, swap=0.0, fee=0.0, symbol="GBPUSD", magic=0, comment=""),
        # balance row -> skipped
        dict(ticket=5, position_id=0, type=2, entry=0, volume=0.0, price=0.0, time=t("2024-03-01"),
             profit=1000.0, commission=0.0, swap=0.0, fee=0.0, symbol="", magic=0, comment="deposit"),
    ])


def test_positions_from_deals_pairs_partial_closes():
    orders = pd.DataFrame([dict(position_id=10, time_setup=1, sl=1.0980, tp=1.1040)])
    p = trades.positions_from_deals(_deals(), orders)
    assert len(p) == 1
    r = p.iloc[0]
    assert r["side"] == "buy" and r["volume"] == 1.0
    assert r["close_price"] == pytest.approx(1.1020)
    assert r["profit"] == 200.0 and r["commission"] == pytest.approx(-7.0)
    assert r["sl"] == 1.0980


def test_report_from_generic_csv(tmp_path):
    csv = tmp_path / "mine.csv"
    pd.DataFrame({
        "Symbol": ["EURUSD", "EURUSD", "XAUUSD", "XAUUSD"],
        "Type": ["Buy", "Sell", "buy", "SELL"],
        "Open Time": ["2024.03.04 09:00", "2024.03.05 13:00", "2024.03.06 02:00", "2024.03.07 15:00"],
        "Close Time": ["2024.03.04 10:00", "2024.03.05 13:01", "2024.03.06 05:00", "2024.03.07 18:00"],
        "Open Price": [1.10, 1.10, 2000, 2000], "Close Price": [1.101, 1.102, 2010, 1990],
        "S/L": [1.099, 0, 1990, 2010], "Volume": [1, 1, 0.1, 1.0], "Profit": [100, -200, 100, 100],
    }).to_csv(csv, index=False)
    df = trades.enrich(trades.load_trades(csv))
    assert list(df["side"]) == ["buy", "sell", "buy", "sell"]
    assert df["R"].iloc[0] == pytest.approx(1.0)
    assert np.isnan(df["R"].iloc[1])                         # no stop -> no R
    assert df["R"].iloc[3] == pytest.approx(1.0)
    f = trades.flags(df)
    assert any("no stop-loss" in x for x in f)
    assert any("within 2 minutes" in x for x in f)
    out = trades.report(csv, tmp_path)
    text = out.read_text()
    assert "By market" in text and "Small sample" in text


def test_prices_mt5_export_format(tmp_path):
    rows = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    t = pd.Timestamp("2024-07-01 10:00")
    for i in range(50):
        ts = t + pd.Timedelta(hours=i)
        rows.append(f"{ts:%Y.%m.%d}\t{ts:%H:%M:%S}\t1.10000\t1.10100\t1.09900\t1.10050\t100\t0\t8")
    rows.append(rows[-1])                                      # duplicate
    src = tmp_path / "raw.csv"
    src.write_text("\n".join(rows))
    rep = prices.file_prices(src, "EURUSD", "ny_close", tmp_path / "out")
    assert rep["timeframe"] == "H1" and rep["duplicates_removed"] == 1
    assert rep["point"] == pytest.approx(1e-5)
    saved = pd.read_csv(tmp_path / "out" / "EURUSD_H1.csv.gz")
    assert saved["datetime"].iloc[0].startswith("2024-07-01 07:00")   # UTC+3 in summer
    assert rep["has_spread"]


def test_prices_bad_rows_removed(tmp_path):
    idx = pd.date_range("2024-01-02", periods=10, freq="D")
    df = pd.DataFrame({"datetime": idx, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0})
    df.loc[3, "high"] = 0.5                                     # high below open -> bad
    src = tmp_path / "d.csv"
    df.to_csv(src, index=False)
    rep = prices.file_prices(src, "TEST", "utc", tmp_path / "out")
    assert rep["bad_rows_removed"] == 1 and rep["timeframe"] == "D1"
