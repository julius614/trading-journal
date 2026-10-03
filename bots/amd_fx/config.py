"""Configuration for the AMD session-sweep bot.

All times are UTC. Credentials come from environment variables only (see .env.example);
never put them in this file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from typing import Optional, Tuple

TimeWindow = Tuple[time, time]


def pip_size(symbol: str) -> float:
    """Price value of one pip: 0.01 for JPY quotes, 0.0001 otherwise."""
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _env_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else None


@dataclass(frozen=True)
class BrokerConfig:
    """MetaTrader 5 connection settings (read from the environment)."""

    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    terminal_path: Optional[str] = None
    magic: int = 260_110
    deviation_points: int = 20
    max_retries: int = 3
    retry_delay_seconds: float = 0.5
    # Broker server time minus UTC, in hours. None = auto-detect from the latest tick.
    server_utc_offset_hours: Optional[int] = None

    @classmethod
    def from_env(cls) -> "BrokerConfig":
        offset = os.getenv("MT5_SERVER_UTC_OFFSET")
        return cls(
            login=_env_int("MT5_LOGIN"),
            password=os.getenv("MT5_PASSWORD") or None,
            server=os.getenv("MT5_SERVER") or None,
            terminal_path=os.getenv("MT5_TERMINAL_PATH") or None,
            magic=_env_int("MT5_MAGIC") or 260_110,
            server_utc_offset_hours=int(offset) if offset not in (None, "") else None,
        )


@dataclass(frozen=True)
class SessionConfig:
    """Session windows in UTC."""

    asian_start: time = time(0, 0)
    asian_end: time = time(6, 0)
    trade_windows: Tuple[TimeWindow, ...] = (
        (time(7, 0), time(10, 0)),   # London open
        (time(12, 0), time(15, 0)),  # New York open
    )
    rollover_start: time = time(21, 50)
    rollover_end: time = time(22, 15)
    day_reset: time = time(0, 0)     # when the daily loss limit resets


@dataclass(frozen=True)
class StrategyConfig:
    symbols: Tuple[str, ...] = ("EURUSD", "GBPUSD")
    timeframe: str = "M5"                 # execution timeframe: "M1" or "M5"
    sweep_min_pips: float = 8.0
    sweep_max_pips: float = 20.0          # beyond this it's a breakout, not a sweep
    displacement_max_bars: int = 3        # close back inside within 1..N bars
    atr_timeframe: str = "D1"             # ATR used for the range-width gate
    atr_period: int = 14
    max_range_atr_mult: float = 2.0       # skip the day if Asian range > mult * ATR
    sl_buffer_pips: float = 2.5
    be_offset_pips: float = 0.5
    tp1_fraction: float = 0.5
    trail_after_tp1: bool = False
    trail_pips: float = 10.0
    history_bars: int = 600               # bars pulled for filters and the Asian range


@dataclass(frozen=True)
class FilterConfig:
    use_zscore: bool = True
    z_threshold: float = 1.5
    # "sweep": most extreme Z during the manipulation (sweep bars through displacement);
    # "displacement": Z of the displacement bar only (stricter - price has already bounced)
    z_measure: str = "sweep"
    z_window: int = 50
    kalman_q_ratio: float = 0.01          # process / measurement variance (lower = smoother)
    use_vol_spike: bool = True
    vol_short: int = 3
    vol_long: int = 20
    vol_mult: float = 1.3


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.01          # 1.0% of equity
    daily_loss_limit: float = 0.02        # 2.0% of day-start equity, realized + unrealized
    max_open_trades: int = 2              # across all pairs
    flatten_on_breaker: bool = True
    flatten_at_rollover: bool = False     # False = only pause new entries
    max_spread_pips: float = 2.0


@dataclass(frozen=True)
class AppConfig:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    poll_seconds: float = 1.0
    data_dir: str = "data/amd_fx"
    log_dir: str = "logs/amd_fx"


def load_config() -> AppConfig:
    """Build the app config, with broker credentials and symbols from the environment."""
    symbols = os.getenv("AMD_SYMBOLS")
    strategy = StrategyConfig(
        symbols=tuple(s.strip().upper() for s in symbols.split(",")) if symbols else StrategyConfig.symbols,
        timeframe=os.getenv("AMD_TIMEFRAME", StrategyConfig.timeframe),
    )
    return AppConfig(broker=BrokerConfig.from_env(), strategy=strategy)
