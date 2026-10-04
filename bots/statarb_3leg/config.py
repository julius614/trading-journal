"""Configuration for the 2-leg H1 pairs-trading bot (default AUDUSD vs NZDUSD;
EURUSD vs GBPUSD via STATARB_PAIR).

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

DEFAULT_PAIR: Tuple[str, str] = ("AUDUSD", "NZDUSD")   # (y, x): y = beta * x + alpha
PAIRS: Dict[str, Tuple[str, str]] = {"AUDNZD": ("AUDUSD", "NZDUSD"), "EURGBP": ("EURUSD", "GBPUSD")}
# typical raw-account spreads in pips, used when data has no spread column
DEFAULT_SPREADS: Dict[str, float] = {"AUDUSD": 0.3, "NZDUSD": 0.7, "EURUSD": 0.2, "GBPUSD": 0.5}
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
    max_hold_bars: Optional[int] = 48      # exit if not reverted within 48 H1 bars (~2 days)
    q_beta: float = 1e-4                   # hedge-ratio drift variance / observation variance
    q_alpha: float = 1e-4                  # intercept drift variance / observation variance (~100-bar memory)
    r_halflife_bars: int = 500             # half-life of the adaptive noise estimate
    clip_sigma: Optional[float] = 4.0      # cap outliers when updating the noise estimate
    warmup_bars: int = 500                 # bars fed to the filter before any trading
    # Bars pulled at start-up for warm-up. The filter adapts slowly (q ~ 1e-4), so it needs
    # the same long history the backtest had: 1,500 bars left beta at 0.45 vs 0.77 on the
    # full 2018-2026 history. Asks for 50,000 and falls back to fewer if the server refuses.
    history_bars: int = 50_000
    # rolling Engle-Granger + half-life gate. OFF by default: on 250 H1 bars it almost
    # never passes (5 trades in 8 years on AUD/NZD, 7 in 6 years on EUR/GBP) and it did
    # not improve the few trades it allowed. See the strategy note before turning it on.
    use_coint_gate: bool = False
    coint_window: int = 250                # bars tested
    coint_max_pvalue: float = 0.05         # ADF p-value must be below this
    coint_max_half_life: float = 48.0      # bars; expected reversion must be faster
    # Funded prop accounts that forbid holding over the weekend: no new baskets from
    # Friday weekend_no_entry_ny, and close any open basket at Friday weekend_close_ny
    # (New York time, so it tracks US daylight saving like the 17:00 NY market close).
    flat_before_weekend: bool = False
    weekend_no_entry_ny: time = time(12, 0)
    weekend_close_ny: time = time(16, 0)


@dataclass(frozen=True)
class FilterConfig:
    min_edge_to_cost: float = 2.5          # expected reversion / total 2-leg cost
    commission_per_lot: float = 7.0        # round trip per 1.0 lot per leg, account ccy
    max_leg_spread_pips: float = 3.0       # reject if either leg's live spread is wider
    news_buffer_minutes: int = 15
    news_currencies: Tuple[str, ...] = ("USD", "AUD", "NZD", "EUR", "GBP")
    news_impacts: Tuple[str, ...] = ("high",)
    # Funded prop accounts that forbid opening OR closing around news (FTMO: 2 minutes):
    # "reverted" and "max hold" exits wait until this many minutes after the event.
    # Protective exits (Z stop, Prop Shield) are never delayed. None = off.
    news_exit_buffer_minutes: Optional[int] = None
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
    # Fixed-risk sizing (overrides notional_equity_mult when set): size the y leg so the
    # loss at the Z stop is about this fraction of equity, e.g. 0.005 = 0.5%.
    risk_per_trade: Optional[float] = None
    max_notional_mult: float = 10.0        # cap on y-leg notional / equity in that mode
    # Wide broker-side stop on every leg (live only), so a crashed PC or lost connection
    # cannot run a leg into the prop firm's daily loss limit. Normal exits stay with the bot.
    emergency_sl_pips: Optional[float] = 250.0
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

    @property
    def conversion_symbol(self) -> Optional[str]:
        """Extra price needed to convert USD amounts into the account currency, e.g. EURUSD
        for a EUR account; None when the legs' own prices are enough."""
        return conversion_pair(self.risk.account_currency, self.pair)

    @property
    def price_symbols(self) -> Tuple[str, ...]:
        """Symbols whose ticks the bot needs: the two legs, plus the conversion pair."""
        return self.pair + ((self.conversion_symbol,) if self.conversion_symbol else ())


USD_BASE_FIRST = {"EUR", "GBP", "AUD", "NZD", "XAU", "XAG"}   # quoted as XXXUSD, others USDXXX


def conversion_pair(account_ccy: str, pair: Tuple[str, str]) -> Optional[str]:
    """The FX pair linking the account currency to USD (EURUSD, USDJPY...), or None when
    the account is in USD or in one leg's base currency."""
    if account_ccy == "USD" or account_ccy in {s[:3] for s in pair}:
        return None
    return f"{account_ccy}USD" if account_ccy in USD_BASE_FIRST else f"USD{account_ccy}"


def validate_pair(pair: Tuple[str, str], account_ccy: str) -> None:
    """Both legs must be 4-decimal pairs quoted in USD (EURUSD, GBPUSD, AUDUSD, NZDUSD...).
    Any account currency works: if it isn't USD or a leg's base currency, the bot also
    reads the pair linking it to USD (EURUSD, USDJPY, ...) to convert."""
    if len(pair) != 2 or pair[0] == pair[1]:
        raise ValueError(f"pair must be two different symbols, got {pair}")
    for s in pair:
        if len(s) != 6 or not s.isalpha() or not s.isupper():
            raise ValueError(f"unsupported symbol {s!r}")
        if s[3:] != "USD":
            raise ValueError(f"{s}: both legs must be quoted in USD (e.g. EURUSD, GBPUSD)")
    if len(account_ccy) != 3 or not account_ccy.isalpha():
        raise ValueError(f"account currency must be a 3-letter code, got {account_ccy!r}")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:   # optional at runtime; listed in requirements.txt
        return
    load_dotenv()


def _opt_float(name: str, default: str = "") -> Optional[float]:
    """Float from the environment; empty, "0" or "off" means None (feature off)."""
    raw = os.getenv(name, default).strip().lower()
    if raw in ("", "off", "none", "0"):
        return None
    return float(raw)


def load_config() -> AppConfig:
    """Build the config from defaults plus environment variables (and .env)."""
    _load_dotenv()
    broker = dataclasses.replace(BrokerConfig.from_env(),
                                 magic=int(os.getenv("STATARB_MAGIC", "260330")))
    raw_pair = os.getenv("STATARB_PAIR", ",".join(DEFAULT_PAIR))
    pair = tuple(s.strip().upper() for s in raw_pair.split(","))
    suffix = os.getenv("STATARB_SYMBOL_SUFFIX", "")
    acct = os.getenv("STATARB_ACCOUNT_CCY", "USD").upper()
    conv = conversion_pair(acct, pair)  # type: ignore[arg-type]
    extra = (conv,) if conv else ()
    symbol_map = {s: s + suffix for s in pair + extra} if suffix else {}
    risk = RiskConfig(
        account_currency=acct,
        notional_equity_mult=float(os.getenv("STATARB_NOTIONAL_MULT", "1.0")),
        risk_per_trade=_opt_float("STATARB_RISK_PER_TRADE"),
        emergency_sl_pips=_opt_float("STATARB_EMERGENCY_SL_PIPS", "250"),
    )
    news_exit = _opt_float("STATARB_NEWS_EXIT_BUFFER_MIN")
    filters = FilterConfig(
        commission_per_lot=float(os.getenv("STATARB_COMMISSION_PER_LOT", "7.0")),
        news_exit_buffer_minutes=int(news_exit) if news_exit is not None else None,
    )
    strategy = StrategyConfig(
        flat_before_weekend=os.getenv("STATARB_FLAT_WEEKEND", "0").strip().lower() in
        ("1", "true", "yes"),
    )
    return AppConfig(broker=broker, risk=risk, filters=filters, strategy=strategy,
                     pair=pair,  # type: ignore[arg-type]
                     symbol_map=symbol_map, news_csv=os.getenv("STATARB_NEWS_CSV") or None,
                     require_news_calendar=os.getenv("STATARB_REQUIRE_NEWS_CALENDAR", "1")
                     .strip().lower() not in ("0", "false", "no", "off"))
