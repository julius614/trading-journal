# AMD Session Sweep — Data Study & Tuning Report (2026-10-03)

**Verdict: no tradeable edge was found. The bot's default settings were not changed.**
Across 648 parameter combinations (both pairs together), none reached the +0.1R/trade
bar after realistic costs on the tuning years. The three that the pre-declared rule
picked all **lost money on the unseen validation years** (2018–2020).

## Data
| Set | Source | Period | Use |
|---|---|---|---|
| Public | OANDA 1-minute bars (GitHub `FutureSharks/financial-data`), resampled to M5 | 2014-01 – 2020-05 | 2014–2017 tuning, 2018–2020 validation |
| Broker | User's MT5 export (`ny_close` server time → UTC) | 2025-05 – 2026-10 | Final hold-out — **not used**, because nothing passed validation |

- Checks: UTC confirmed (weeks open Sun 21:00/22:00, close Fri 20:59/21:59), no Saturday bars.
  2011–2013 failed the checks and were excluded.
- Costs (raw account): EURUSD 0.2-pip spread, GBPUSD 0.5 pip, $7/lot round trip, 0.2-pip
  slippage on entries and stops. Stress test at 2×.
- Engine: `bots/amd_fx/research/fast_backtest.py` uses the real strategy code and matches
  the bot's replay trade for trade (`tests/test_fast_backtest.py`).

## 1. Data study (2014–2017, no tuning)
**Setup funnel, default filters**
| | EURUSD | GBPUSD |
|---|---|---|
| Days with a valid Asian range | 1,022 | 1,023 |
| Sweeps of 8–20 pips | 4,186 | 4,059 |
| …became breakouts (> 20 pips) | 1,434 | 1,579 |
| …no close back inside within 3 bars | 1,696 | 1,175 |
| …rejected by Z/volatility filters | 493 | 806 |
| **Signals** | **118** | **182** |

Asian range median: EURUSD 23 pips (D1 ATR 76), GBPUSD 27 pips (ATR 97). The 2×ATR gate
almost never skips a day (0.1–0.2%).

**After a signal, how often is each target reached before the stop?** (all setups, no
filters; no costs)
| Target | Random walk | EURUSD (472) | GBPUSD (691) |
|---|---|---|---|
| +0.5R | 66.7% | 65.7% | 66.7% |
| +1R | 50.0% | 48.1% | 50.1% |
| +1.5R | 40.0% | 36.2% | 39.8% |
| +2R | 33.3% | 26.7% | 32.7% |
| +3R | 25.0% | 13.1% | 19.1% |

**After a sweep, price behaves like a coin flip.** Gross expected value is about 0R at
every target (−0.05 to +0.05R), and the Z-score and volatility filters don't improve it.
Targets above 2R do worse than random, because trades run out of time by the end of the day.
Wider targets alone therefore can't create an edge.

TP1 (Asian midpoint) sits at a median **0.56–0.59R** and TP2 (far boundary) at **1.3R**.
That's why average wins were small in the first backtest.

## 2. Tuning grid (2014–2017)
Signal settings: sweep {5–15, 8–20, 10–30 pips} × close-back-inside bars {1, 2, 3} ×
Z gate {off, 1.0, 1.5} × volatility filter {on, off} = 54. Targets: {split mid+edge
(default), single to edge, split mid+edge+0.5 range, single to edge+0.5 range}. Windows:
{London, NY, both}. Pairs: EURUSD, GBPUSD, both. **Total 1,944 configurations**, all
recorded.

| Summary (pair = both, 648 configs) | Value |
|---|---|
| Configs with expectancy > 0 | 65 |
| Configs with expectancy > +0.1R | **0** |
| Median expectancy | −0.086R |
| Best expectancy | +0.090R (t = 1.40) |
| t-stat expected from luck alone across 648 tries | ≈ 3.6 |
| Current default config (8–20, 3 bars, Z 1.5, vol on, split, both windows) | **−0.114R**, PF 0.72, t −2.4, 295 trades |

What the grid suggests (median expectancy by setting):
- **London window only** is the least bad (−0.03R); New York is the worst (−0.17R).
- **Volatility filter off** beats on (−0.07R vs −0.11R): the filter doesn't help.
- The Z gate and target layout make little difference (all −0.08 to −0.10R medians).

## 3. Validation (2018–2020, unseen)
Selection rule (fixed in `research/validate.py` before seeing results): pair = both,
≥ 150 trades, positive in ≥ 3 of 4 years, neighbouring settings also positive on average;
top 3 by neighbour score.

| Config (all: London, single position, TP2 = edge + 0.5 range, vol filter off) | Tune 2014–17 | Validation 2018–20 | Validation, 2× costs |
|---|---|---|---|
| Sweep 8–20, 3 bars, Z 1.0 | +0.085R (443 trades) | **−0.040R** (234), PF 0.92 | −0.114R |
| Sweep 8–20, 3 bars, Z 1.5 | +0.055R (377) | **−0.117R** (196), PF 0.77 | −0.191R |
| Sweep 10–30, 3 bars, Z 1.5 | +0.044R (282) | **−0.041R** (139), PF 0.91 | −0.114R |

None passes (needed > +0.1R, PF > 1.2, ≥ 0 at 2× costs). The small tuning-period profits
didn't carry over to new data, which is what luck-driven results look like.

## 4. Conclusions
1. **The Asian-range sweep, as specified, has no measurable edge** on EURUSD/GBPUSD in
   2014–2020 or in the broker's 2025–2026 data. Outcomes after a sweep match random price
   movement.
2. **Tuning can't fix it.** With no edge in the signal, changing targets, filters or
   thresholds only rearranges noise. The best tuned versions failed out of sample.
3. **Costs turn "zero" into a steady loss** of about −0.05 to −0.1R per trade.
4. **Don't trade this strategy with real money.** The bot framework (risk, Prop Shield,
   MT5 execution, replay) is still sound and can run a different signal.

## 5. If you want to keep researching (new hypotheses, tested the same way)
Each of these is a *new idea*, not a tweak. Write it down first, test it on 2014–2017, and
confirm on 2018–2020 once:
- **London-only with a higher-timeframe trend filter** (trade sweeps against the daily
  trend only) — London was the least-bad window.
- **News-day filter** — sweeps around scheduled releases (NFP, CPI, central banks) may
  behave differently from ordinary days.
- **Larger, deeper sweeps** measured in ATR units rather than fixed pips.
- **Different instruments** (e.g. index futures), where "stop hunts" at session
  extremes are more often studied.

## Reproduce
```bash
python -m bots.amd_fx.research.load_data --oanda-root <financial-data>/pyfinancialdata/data/currencies/oanda
python -m bots.amd_fx.research.study --start 2014 --end 2017
python -m bots.amd_fx.research.tune --start 2014 --end 2017 --out tune_2014_2017.csv   # ~15 min, 4 cores
python -m bots.amd_fx.research.validate --tune tune_2014_2017.csv --start 2018 --end 2020
```
