import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orb import ORBConfig, backtest, load_csv, summarize, to_15min  # noqa: E402

# Opening range used by most tests: high 101, low 99, midline 100.
OR_BAR = (100.0, 101.0, 99.0, 100.0)


def day(bars, date="2024-03-04"):
    """Build one session of 15-minute bars from (open, high, low, close) tuples."""
    idx = pd.date_range(f"{date} 09:30", periods=len(bars), freq="15min")
    return pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)


def run(bars, **kw):
    return backtest(day(bars), ORBConfig(**kw))


def test_long_breakout_hits_2r_target():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 105.0, 101.4, 104.8)])
    assert len(t) == 1
    tr = t.iloc[0]
    assert tr.side == "long" and tr.entry_price == 101.5 and tr.stop == 100.0
    assert tr.exit_reason == "target" and tr.exit_price == pytest.approx(104.5)
    assert tr.r_multiple == pytest.approx(2.0)


def test_wick_poke_is_not_a_breakout():
    t = run([OR_BAR, (100.5, 101.8, 100.2, 100.8), (100.8, 100.9, 99.5, 100.0)])
    assert t.empty


def test_failed_breakout_exits_on_close_back_inside():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 101.6, 100.5, 100.8)])
    tr = t.iloc[0]
    assert tr.exit_reason == "failed" and tr.exit_price == 100.8
    assert tr.r_multiple == pytest.approx((100.8 - 101.5) / 1.5)


def test_stop_at_midline():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 101.7, 99.9, 101.2)])
    assert t.iloc[0].exit_reason == "stop"
    assert t.iloc[0].r_multiple == pytest.approx(-1.0)


def test_opposite_side_stop():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 101.7, 99.9, 101.2)],
            stop="opposite", exit_on_failed=False)
    tr = t.iloc[0]
    assert tr.stop == 99.0 and tr.exit_reason == "eod"


def test_short_breakout():
    t = run([OR_BAR, (99.5, 99.6, 98.4, 98.5), (98.5, 98.6, 95.0, 95.5)])
    tr = t.iloc[0]
    assert tr.side == "short" and tr.stop == 100.0
    assert tr.exit_reason == "target" and tr.r_multiple == pytest.approx(2.0)


def test_stop_wins_when_stop_and_target_hit_in_same_bar():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 105.0, 99.5, 102.0)])
    assert t.iloc[0].exit_reason == "stop"


def test_bnr_waits_for_retest():
    bars = [OR_BAR,
            (100.5, 101.6, 100.4, 101.5),   # break
            (101.5, 102.0, 101.05, 101.8),  # retest of 101 (tolerance 0.2), holds, closes up
            (101.8, 106.0, 101.7, 105.5)]   # target: 101.8 + 2 * 1.8 = 105.4
    t = run(bars, mode="bnr")
    tr = t.iloc[0]
    assert tr.entry_type == "bnr" and tr.entry_price == 101.8
    assert tr.entry_time == pd.Timestamp("2024-03-04 10:00")
    assert tr.exit_reason == "target" and tr.r_multiple == pytest.approx(2.0)


def test_bnr_cancelled_by_failed_breakout():
    bars = [OR_BAR,
            (100.5, 101.6, 100.4, 101.5),   # break up
            (101.5, 101.6, 100.3, 100.5),   # closes back inside: setup cancelled
            (100.5, 101.2, 100.6, 101.1)]   # touches 101 and closes above, but no new break
    assert run(bars, mode="bnr").empty


def test_hold_to_eod_when_no_target():
    t = run([OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 102.5, 101.4, 102.0),
             (102.0, 103.2, 101.9, 103.0)], target_r=None)
    tr = t.iloc[0]
    assert tr.exit_reason == "eod" and tr.exit_price == 103.0


def test_width_filter_skips_wide_days():
    # OR width 2 / 100 = 2%
    assert run([OR_BAR, (100.5, 101.6, 100.4, 101.5)], max_or_width_pct=1.5).empty


def test_slippage_reduces_result():
    # failed-breakout exit at a fixed close, so only the costs differ
    bars = [OR_BAR, (100.5, 101.6, 100.4, 101.5), (101.5, 101.6, 100.5, 100.8)]
    clean = run(bars).iloc[0].pnl_per_share
    costly = run(bars, slippage=0.05).iloc[0].pnl_per_share
    assert costly == pytest.approx(clean - 0.10)


def test_bias_filter_uses_previous_or():
    d1 = day([(100, 101, 99, 100), (100, 100.5, 99.5, 100)], "2024-03-04")
    # Day 2 OR is below day 1's, so the bias is bearish: a long breakout is skipped.
    d2 = day([(95, 96, 94, 95), (95.5, 96.6, 95.4, 96.5), (96.5, 100, 96.4, 99)], "2024-03-05")
    bars = pd.concat([d1, d2])
    assert backtest(bars, ORBConfig(use_bias=True)).empty
    assert len(backtest(bars, ORBConfig(use_bias=False))) == 1


def test_load_and_resample_5min(tmp_path):
    idx = pd.date_range("2024-03-04 09:00", periods=24, freq="5min")  # includes pre-market
    df = pd.DataFrame({"datetime": idx, "open": 100.0, "high": 100.5, "low": 99.5,
                       "close": 100.0, "volume": 1000})
    df.loc[7, "high"] = 102.0  # 09:35 bar, inside the opening range
    df.loc[1, "high"] = 110.0  # 09:05 pre-market spike, must be ignored
    path = tmp_path / "bars.csv"
    df.to_csv(path, index=False)
    bars = to_15min(load_csv(str(path)))
    assert bars.index[0] == pd.Timestamp("2024-03-04 09:30")
    assert bars["high"].iat[0] == 102.0


def test_load_tz_aware_timestamps(tmp_path):
    path = tmp_path / "bars.csv"
    path.write_text("time,open,high,low,close\n"
                    "2024-03-04T14:30:00Z,1,2,0.5,1.5\n")
    assert load_csv(str(path)).index[0] == pd.Timestamp("2024-03-04 09:30")


def test_summarize():
    t = pd.DataFrame({"r_multiple": [2.0, -1.0, -1.0, 2.0]})
    s = summarize(t)
    assert s["win_rate"] == 0.5 and s["expectancy_r"] == 0.5
    assert s["profit_factor"] == 2.0 and s["max_drawdown_r"] == -2.0
