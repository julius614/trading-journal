from datetime import datetime, timezone

from bots.amd_fx.config import RiskConfig, SessionConfig
from bots.amd_fx.risk_manager import RiskManager, in_time_window


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def make() -> RiskManager:
    return RiskManager(RiskConfig(), SessionConfig())


def test_breaker_trips_at_two_percent_of_day_start_equity():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    assert not rm.check_breaker(9_801)          # -1.99%
    assert rm.check_breaker(9_800)              # -2.00% (realized + unrealized)
    assert rm.can_open(utc("2024-03-05T08:00"), 0)[0] is False


def test_breaker_stays_locked_even_if_equity_recovers():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    rm.check_breaker(9_700)
    assert rm.check_breaker(10_500)


def test_new_day_resets_breaker_and_baseline():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    rm.check_breaker(9_700)
    assert rm.update_day(utc("2024-03-06T00:00"), 9_700)
    assert not rm.state.locked and rm.state.day_start_equity == 9_700
    assert not rm.check_breaker(9_600)          # -1.03% of the new baseline


def test_max_open_trades():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    assert rm.can_open(utc("2024-03-05T08:00"), 1)[0]
    ok, reason = rm.can_open(utc("2024-03-05T08:00"), 2)
    assert not ok and "max open" in reason


def test_rollover_window_blocks_entries():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    assert rm.in_rollover(utc("2024-03-05T21:50"))
    assert rm.in_rollover(utc("2024-03-05T22:14"))
    assert not rm.in_rollover(utc("2024-03-05T22:15"))
    assert not rm.in_rollover(utc("2024-03-05T21:49"))
    assert rm.can_open(utc("2024-03-05T22:00"), 0) == (False, "rollover window")


def test_spread_filter():
    rm = make()
    rm.update_day(utc("2024-03-05T00:05"), 10_000)
    assert not rm.can_open(utc("2024-03-05T08:00"), 0, spread_pips=3.0)[0]
    assert rm.can_open(utc("2024-03-05T08:00"), 0, spread_pips=0.8)[0]


def test_window_crossing_midnight():
    from datetime import time
    assert in_time_window(time(23, 30), time(23, 0), time(1, 0))
    assert in_time_window(time(0, 30), time(23, 0), time(1, 0))
    assert not in_time_window(time(2, 0), time(23, 0), time(1, 0))
