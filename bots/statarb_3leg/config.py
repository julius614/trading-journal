"""Configuration for the 2-leg H1 pairs-trading bot (default EURUSD vs GBPUSD).

(The package is still called statarb_3leg for continuity; the 3-leg triangle version is
in git history at commit e5b753f.)

All times are UTC. Credentials come from the environment (or a .env file loaded with
python-dotenv); never put them in this file.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from datetime import time
from typing import Dict, Optional, Tuple

from ..amd_fx.config import BrokerConfig as _MT5Settings

DEFAULT_PAIR: Tuple[str, str] = ("EURUSD", "GBPUSD")   # (y, x): y = beta * x + alpha
CONTRACT_SIZE = 100_000
PIP = 0.0001   # 4-decimal pairs only (no JPY quotes)

# Re-exported: MT5 login, server time zone, magic number, retries.
BrokerConfig = _MT5Settings


@dataclass(frozen=True)
class StrategyConfig:
    timeframe: str = "H1"
    entry_z: float = 2.0                   # |Z| beyond this -> candidate signal
    exit_z: float = 0.1                    # close when Z is back within +-exit_z of zero
    stop_z_extra: Optional[float] = 2.0    # stop if Z widens this far past the entry Z
    max_hold_bars: Optional[int] = 240     # emergency exit after ~10 trading days of H1 bars
    q_beta: float = 1e-4                   # hedge-ratio drift variance / observation variance
    q_alpha: float = 1e-4                  # intercept drift variance / observation variance (~100-bar memory)
    r_halflife_bars: int = 500             # half-life of the adaptive noise estimate
    clip_sigma: Optional[float] = 4.0      # cap outliers when updating the noise estimate
    warmup_bars: int = 500                 # bars fed to the filter before any trading
    history_bars: int = 1500               # bars pulled at start-up for warm-up


@dataclass(frozen=True)
class FilterConfig:
    min_edge_to_cost: float = 2.5          # expected reversion / total 2-leg cost
    commission_per_lot: float = 7.0        # round trip per 1.0 lot per leg, account ccy
    max_leg_spread_pips: float = 3.0       # reject if either leg's live spread is wider
    news_buffer_minutes: int = 15
    news_currencies: Tuple[str, ...] = ("USD", "EUR", "GBP")
    news_impacts: Tuple[str, ...] = ("high",)
    # Rollover (17:00 New York) moves between 22:00 UTC (winter) and 21:00 UTC (US summer
    # time). "ny_close" pauses entries 16:50-17:15 New York time all year (= 21:50-22:15
    # UTC in winter, 20:50-21:15 UTC in summer); "utc" uses the fixed UTC times below.
    rollover_anchor: str = "ny_close"
    rollover_ny_start: time = time(16, 50)
    rollover_ny_end: time = time(17, 15)
    rollover_start: time = time(21, 50)    # used when rollover_anchor == "utc"
    rollover_end: time = time(22, 15)


@dataclass(frozen=True)
class RiskConfig:
    account_currency: str = "USD"          # USD, or the base currency of one of the legs
    notional_equity_mult: float = 1.0      # y-leg notional = mult x equity
    max_lots_per_leg: float = 20.0
    daily_loss_limit: float = 0.02         # 2% of day-start equity, realized + floating
    day_reset: time = time(0, 0)


@dataclass(frozen=True)
class AppConfig:
    broker: BrokerConfig = field(default_factory=lambda: BrokerConfig(magic=260_330))
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    pair: Tuple[str, str] = DEFAULT_PAIR
    symbol_map: Dict[str, str] = field(default_factory=dict)  # e.g. {"EURUSD": "EURUSD.m"}
    news_csv: Optional[str] = None
    require_news_calendar: bool = True     # live mode refuses to start without one
    poll_seconds: float = 1.0
    data_dir: str = "data/statarb_3leg"
    log_dir: str = "logs/statarb_3leg"

    def __post_init__(self) -> None:
        validate_pair(self.pair, self.risk.account_currency)

    @property
    def y(self) -> str:
        return self.pair[0]

    @property
    def x(self) -> str:
        return self.pair[1]

    def broker_symbol(self, symbol: str) -> str:
        return self.symbol_map.get(symbol, symbol)


def validate_pair(pair: Tuple[str, str], account_ccy: str) -> None:
    """Both legs must be 4-decimal pairs quoted in USD (EURUSD, GBPUSD, AUDUSD, NZDUSD...),
    and the account currency must be USD or one leg's base currency, so every amount can
    be converted with the two legs' own prices."""
    if len(pair) != 2 or pair[0] == pair[1]:
        raise ValueError(f"pair must be two different symbols, got {pair}")
    for s in pair:
        if len(s) != 6 or not s.isalpha() or not s.isupper():
            raise ValueError(f"unsupported symbol {s!r}")
        if s[3:] != "USD":
            raise ValueError(f"{s}: both legs must be quoted in USD (e.g. EURUSD, GBPUSD)")
    allowed = {"USD"} | {s[:3] for s in pair}
    if account_ccy not in allowed:
        raise ValueError(f"account currency {account_ccy} must be one of {sorted(allowed)}")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:   # optional at runtime; listed in requirements.txt
        return
    load_dotenv()


def load_config() -> AppConfig:
    """Build the config from defaults plus environment variables (and .env)."""
    _load_dotenv()
    broker = dataclasses.replace(BrokerConfig.from_env(),
                                 magic=int(os.getenv("STATARB_MAGIC", "260330")))
    raw_pair = os.getenv("STATARB_PAIR", ",".join(DEFAULT_PAIR))
    pair = tuple(s.strip().upper() for s in raw_pair.split(","))
    suffix = os.getenv("STATARB_SYMBOL_SUFFIX", "")
    symbol_map = {s: s + suffix for s in pair} if suffix else {}
    risk = RiskConfig(
        account_currency=os.getenv("STATARB_ACCOUNT_CCY", "USD").upper(),
        notional_equity_mult=float(os.getenv("STATARB_NOTIONAL_MULT", "1.0")),
    )
    filters = FilterConfig(
        commission_per_lot=float(os.getenv("STATARB_COMMISSION_PER_LOT", "7.0")),
    )
    return AppConfig(broker=broker, risk=risk, filters=filters, pair=pair,  # type: ignore[arg-type]
                     symbol_map=symbol_map, news_csv=os.getenv("STATARB_NEWS_CSV") or None)
