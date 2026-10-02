# 15-Minute ORB "the MAX way" — Strategy Spec & Research

## Source & capture

- **Strategy source:** Max Options Trading (YouTube, ~186k subscribers),
  *"Trading the 15 minute ORB the MAX way!"* — <https://youtu.be/seH8Y0RLyjA> and
  <https://youtu.be/QmPUp9ISuDw> (the user gave one title for both; the second video is
  assumed to cover the same method).
- **Captured:** 2026-10-02
- **How it was captured:** YouTube, TradingView and the video-summary sites were blocked
  from the environment these notes were written in, so **the videos were not watched**.
  The rules come from search-indexed descriptions of Max's method: an OpenTools summary
  of the video and the write-up of a community TradingView indicator,
  *"ORB 15 Min Pro — Max Way"*, which says it follows "the approach Max Options Trading
  teaches publicly". Tags: **(max)** = described as Max's rule; **(assumed)** = a standard
  ORB convention I filled in, now a parameter to test. **Watch both videos and correct
  anything marked (assumed).**
- **Code:** [`strategies/orb_15min/`](../../../strategies/orb_15min/) — Python backtester
  and a TradingView Pine strategy that use these rules.

---

## 1. The idea in one line

The first 15 minutes of the US session set a range. When a 15-minute candle **closes**
outside it, trade in that direction, with the range as your risk reference.

## 2. Rules

### Setup
| Item | Rule | Tag |
|---|---|---|
| Market / time | US session open, **9:30–9:45 ET** first 15-minute candle; Max applies it to options, futures and forex | (max) |
| Opening range (OR) | **High and low of the first 15-minute candle, wicks included** | (max) |
| Midline | (OR high + OR low) / 2 — used as a reference level | (max) |
| Bias | **Green** when today's range formed above yesterday's, **red** when below. Coded as today's OR midline vs. yesterday's | (max, definition assumed) |
| Chop vs. trend | Max separates choppy days from trend days and says to avoid chop. His exact filter isn't in the excerpts — coded as an optional max OR-width filter | (max idea, filter assumed) |

### Entry
| Type | Rule | Tag |
|---|---|---|
| **Breakout** | A **15-minute candle closes** above the OR high (long) or below the OR low (short). **Wick pokes don't count.** Enter at that close. | (max) |
| **Break-and-retest (BNR)** | After a breakout close, price **pulls back to the broken level, holds it, and closes back in the breakout direction**. Enter at that close. (Tolerance 10% of OR width; must come within 8 bars.) | (max; numbers assumed) |
| **Failed breakout (X)** | A candle **closes back inside the range** after a breakout → no trade / cancel the BNR setup | (max) |
| Confirmation | Patience; candlestick confirmation; trade with the trend | (max, not coded) |

### Exit & risk
| Item | Rule | Tag |
|---|---|---|
| Stop | **OR midline** (default) or **opposite side of the OR** | (assumed) |
| Failed-breakout exit | Exit if a 15-minute candle closes back inside the range | (max idea, as exit assumed) |
| Target | **2R** default; 1R, or hold to the close, as alternatives | (assumed) |
| End of day | Flat by the close — it's a day trade | (assumed) |
| Frequency | One trade per day | (assumed) |
| Size | Fixed % of account risked per trade (e.g. 0.5–1%) = risk ÷ (entry − stop) | (assumed) |

### If trading it with options (Max's main vehicle)
- 0DTE/1DTE options amplify both sides: **theta decay** works against a slow breakout and
  **bid-ask spreads** can eat a big share of the move. Liquid underlyings only (SPY, QQQ, SPX).
- **Test the rules on the underlying first.** Only move to options once the underlying
  shows an edge after costs. Then log delta, IV and spread at entry.
- Size options by the **premium you can lose**, not the number of contracts.

## 3. Strategy review (mentor Workflow A)

### 3.1 Hypothesis — why might this work?
- The open packs overnight news, gap repricing and institutional orders into a short
  window. A **close** outside the first range suggests one side has won the early auction,
  and order flow often keeps going that way for a while (intraday momentum).
- **Who is on the other side?** Traders fading the open, market makers providing
  liquidity, and stop orders sitting just beyond the range.
- **Weak point:** it's one of the most widely known day-trading setups. A well-known edge
  gets crowded, and false breakouts are common on choppy days. That's why the
  close-confirmation, failed-breakout and chop rules matter.

### 3.2 Lifecycle fit
| Stage | In this strategy |
|---|---|
| Features | OR high/low/midline, OR width %, bias vs. yesterday, breakout close, retest |
| Prediction | Direction for the rest of the session after a confirmed break |
| Portfolio / risk | One position, fixed-fraction risk, stop at midline or opposite side |
| Execution | Market order at the 15-minute close; slippage matters a lot |

### 3.3 How this backtest could lie — checklist
- [ ] **Overfitting:** don't tune OR length, stop, target, tolerance and width filter all
      together on the same data. Choose them on 2016–2020, then test once on 2021–present.
- [ ] **Look-ahead bias:** the OR is only known at 9:45; entry is at the bar *close*; the
      bias uses yesterday's OR only. (The code follows this.)
- [ ] **Costs:** an independent replication of the QQQ ORB found **break-even at about
      2.2¢/share slippage**. Always run with `--slippage`. For options, model the spread.
- [ ] **Same-bar ambiguity:** when stop and target are both inside one 15-minute bar, the
      code assumes the stop hit first (conservative). Rerun on 1- or 5-minute data to check.
- [ ] **Regime:** split results by year and by volatility. Published ORB profits cluster in
      **2020–2022**.
- [ ] **Survivorship / snooping:** if you test many tickers, pick the list *before* looking
      at results; report every variant you tried.
- [ ] **Random-data sanity check:** on random-walk data the backtester showed about
      +0.1R/trade over 204 trades — **inside noise** (≈1.2 standard errors). Any real result
      needs to clearly beat that, over hundreds of trades.

### 3.4 Validation plan
1. Get **≥5 years of 5-minute data** for SPY and QQQ (and the futures ES/NQ if you trade them).
2. Baseline: `--mode breakout --stop mid --target 2 --slippage 0.01`.
3. Variants, decided in advance (no others): BNR vs. breakout; midline vs. opposite stop;
   2R vs. EOD target; bias filter on/off; width filter on/off.
4. In-sample 2016–2020 → pick one config → **out-of-sample 2021–present, run once**.
5. Accept only if out-of-sample: **≥200 trades, expectancy > +0.1R after costs, profit
   factor > 1.2, no single year carrying the total**, and results hold with double slippage.
6. **Paper trade 30–50 setups** with this journal before risking real money.
7. Go live small (e.g. 0.25% risk/trade) for 50 trades; scale only if live matches paper.

### 3.5 Risk rules
- Risk ≤ 1% of the account per trade (0.25–0.5% while proving it).
- **Daily loss limit:** stop after 2R lost in a day (one trade per day keeps this simple).
- **Weekly review:** stop trading and review after a 6R drawdown.
- No averaging down; no moving the stop away from the entry.

## 4. Evidence from research (not Max's own results)

| Study | What it tested | Finding | Caveats |
|---|---|---|---|
| Zarattini & Aziz, *Can Day Trading Really Be Profitable?* (SSRN 4416622) | **5-minute** ORB on QQQ, 2016–2023; stop at the opposite side of the range, hold to the close; TQQQ for leverage | ~1,484% vs. 169% buy-and-hold; ~33% annual alpha after commissions | The authors sell trading education; 5-min, not 15-min |
| Zarattini, Barbon & Aziz, *A Profitable Day Trading Strategy for the U.S. Equity Market* (SSRN 4729284) | 5-min ORB on 7,000+ US stocks, 2016–2023 | **Plain ORB was weak**; choosing "stocks in play" (high opening relative volume) did almost all the work — top 20: Sharpe 2.81 | Same authors; stock selection is the edge, not the breakout |
| Independent replication (giovannibrusco/zarattini-2023-orb-qqq, GitHub) | Rebuild of the QQQ 5-min ORB with costs | **Break-even ≈ 2.2¢/share slippage**; much of the PnL came from **2022** | Suggests the edge is thin and depends on regime |
| Option Alpha 0DTE ORB backtests | 15-min ORB using options on SPY/QQQ etc. | Reported e.g. 78% win rate, $35 average per trade, $7.6k max drawdown for one combined config | Marketing context; a high win rate with small average wins can hide tail risk |

**Takeaway:** ORB has published support, but the edge is **thin, cost-sensitive,
regime-dependent and helped most by stock selection (relative volume)**. Treat Max's
version as a hypothesis to test, not a proven system.

## 5. Possible improvements to test later (one at a time)
- **Relative-volume filter** (trade only when opening volume is far above normal) — the
  strongest factor in the research.
- 5-minute OR vs. 15-minute OR.
- Trailing the stop to break-even at 1R.
- Skip days with major scheduled news (CPI, FOMC) — or trade only those days.

## 6. Per-trade journal checklist
Use [`journal/templates/orb-trade.md`](../../../journal/templates/orb-trade.md). Minimum:
OR high/low/width, bias, chop call, entry type (breakout/BNR), entry/stop/target,
slippage, exit reason (target/stop/failed/eod), R result, rule followed or override.

## Self-check questions
1. Why does Max insist on a candle *close* rather than a wick through the range?
2. What turns a breakout into a "failed breakout", and what do you do then?
3. Why might a 78% win rate still lose money?
4. What did the stocks-in-play paper find about plain ORB vs. ORB with a relative-volume filter?
5. At what slippage did the independent QQQ replication break even, and what does that mean for options traders?

## Further reading
- [OpenTools summary of the video](https://opentools.ai/youtube-summary/trading-the-15-minute-orb-the-max-way)
- [ORB 15 Min Pro — Max Way (TradingView indicator)](https://www.tradingview.com/script/KhKOWKqM-ORB-15-Min-Pro-Max-Way/)
- [Zarattini & Aziz — Can Day Trading Really Be Profitable? (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622)
- [Zarattini, Barbon & Aziz — A Profitable Day Trading Strategy for the U.S. Equity Market (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284)
- [Independent QQQ ORB replication (GitHub)](https://github.com/giovannibrusco/zarattini-2023-orb-qqq)
- [ORB Trading Strategy: What Replication Shows](https://paperswithbacktest.com/strategies/orb-trading-strategy)
- [Opening Range Breakout Research: What Two Day-Trading Papers Actually Found](https://danfin.net/opening-range-breakout-research)
- [Option Alpha — ORB 0DTE options strategy](https://optionalpha.com/blog/opening-range-breakout-0dte-options-trading-strategy-explained)
- [QuantConnect — ORB for Stocks in Play](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
