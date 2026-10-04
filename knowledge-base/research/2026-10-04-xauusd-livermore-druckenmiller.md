# XAUUSD — research note (as of 2026-10-01 close; written 2026-10-04)

- **Price data:** the user's MT5 daily bars (MetaQuotes-Demo, `data/trend/XAUUSD_D1.csv.gz`,
  2004–2026).
- **Macro data:** news search on 2026-10-04 (sources below).
- **Lenses:** questflowai/investorskills `livermore` and `druckenmiller` (their own Process,
  Output Format and Guardrails).
- **Status:** hypothesis, not tested. Not financial advice.

## Data snapshot
| Item | Value |
|---|---|
| Last close | 4,176.6 (1 Oct 2026) |
| All-time / 52-week high | 5,598.0 (29 Jan 2026), so price is **−25.4%** from the high |
| 52-week low | 3,886.6 |
| SMA20 / SMA50 / SMA100 / SMA200 | 4,302 / 4,327 / 4,284 / 4,538 (price below all four; SMA50 < SMA200) |
| Returns 1 m / 3 m / 6 m / 12 m | −4.9% / +0.3% / −11.7% / +5.0% |
| ATR(14) | 90.6 (2.2% of price); realised vol 20-day 20.6%, 1-year 28.6% |
| 20-day range | 4,108.3 (29 Sep) – 4,510.8 (3 Sep) |
| 50-day range | 3,995.9 (29 Jul) – 4,696.7 (25 Aug) |
| Last notable day | 28 Sep: −3.9% (4,291 → 4,123); no follow-through since (4,156–4,177) |
| Tick volume | last 5 days ~401k vs 50-day ~417k (no expansion) |
| Cross-asset (3 m / 12 m) | Silver −1.8% / +21.7%; EURUSD −1.4% / −2.7% (USD slightly firmer); US500 +1.6% / +17%; WTI +17.8% / +100% |
| Gold/silver ratio | 68.5 (80.7 a year ago) |

**Macro (news, Sept 2026):**
- **Fed:** hiked 25 bp on 16 Sep to 3.75–4.00%, with projections pointing to another hike
  before year-end.
- **Yields and dollar:** US 10-year ~4.7%, DXY ~98.5.
- **Flows:** gold ETFs saw ~$14.5 bn net outflows year-to-date (after +$35 bn in 2025), and
  central-bank buying has slowed (China and Poland still buying dips).
- **Bank forecasts:** JPMorgan Q4 $4,500, BofA 2026 average $4,360, HSBC 2026 average
  $4,560.

## Lens 1 – Livermore: **Wait / Stand Down**
| Signal | Status | Evidence | Weight |
|---|---|---|---|
| Line of least resistance | Down-to-sideways | Below all main averages; SMA50 < SMA200; −25% from the high | High |
| Pivotal point (down) | Not broken | 4,108 (29 Sep low), then 3,996 (Jul low) and 3,887 (52-week low) | High |
| Pivotal point (up) | Far | 4,511 (Sep high), then 4,697 | Medium |
| Volume / follow-through | Missing | 28 Sep drop not followed through; volume below average | High |
| Choppiness | High | 3-month return ~0% inside a 4,000–4,700 range | Medium |

- **Plan:**
  - **Short** only on a daily close below 4,108 that holds the next day.
  - Initial stop about 1.5 × ATR above the entry (~4,240).
  - First add only after the position shows a profit and price closes below 3,996.
  - Mirror for a long: a close above 4,511 that holds.
  - Size from risk (e.g. 0.5% of equity at the stop).
- **Invalidation:** a close back above 4,302 (SMA20) after a breakdown.
- **Missing data:** intraday volume at the 28 Sep break; futures volume and open interest.
- **Guardrails applied:** don't anticipate the break, never average down, don't trade a dull
  range.

## Lens 2 – Druckenmiller: **Probe (bearish), small; Press only on confirmation**
- **Dominant driver:** a tightening Fed (rate hikes, with another expected), so real yields
  are high and rising, and the marginal ETF buyer is selling.
- **Liquidity and policy:** this works against a non-yielding asset. Central-bank support
  has faded as the price-setter.
- **Market confirmation:** partial.
  - Price is in a downtrend from January, but holding 4,100–4,300 for now.
  - The USD is only slightly firmer, and silver isn't confirming strongly.
- **Consensus:** sell-side Q4 targets (4,360–4,560) sit *above* price, so consensus still
  leans bullish while price action is bearish. That's the asymmetry he looks for, but it
  needs price to confirm.
- **Expression:** XAUUSD itself (liquid). Silver is noisier.
- **Sizing:** start small enough to cut quickly. Add ("press") only if 3,996 breaks with the
  dollar and yields confirming.
- **Proven wrong if:** gold reclaims SMA50 (~4,327) or SMA200 (~4,538), the Fed turns
  dovish, or real yields fall.
- **Missing data:** TIPS real yields, CFTC positioning, a dated catalyst (next FOMC, CPI).

## Where they disagree
- **Both lean bearish but differ on timing.**
  - Druckenmiller would **probe now** because the macro driver and the trend agree.
  - Livermore says **wait** for the 4,108 break with follow-through, because today's market
    is choppy with no volume expansion.
- **Common ground:** no long until 4,511 is reclaimed; any short is small, with fast exits.

## Testable rule draft (a gold-only trend rule)
- **Entry:** short when the daily close is below the prior 50-day low *and* SMA50 < SMA200;
  long mirrored.
- **Exit and stop:** exit on a close beyond the 20-day extreme in the opposite direction.
  Stop at 2 × ATR(14) from entry.
- **Sizing:** risk 0.5% of equity at the stop.
- **Market and costs:** XAUUSD only; broker spread plus slippage, plus **real swap rates for
  multi-day holds**.

## Gate plan (honest)
- **This history isn't clean test data.** Gold's history was already used in the
  trend-following test (`knowledge-base/strategies/trend-following/`). There, gold showed
  the best gross trend Sharpe (0.55), but the multi-market portfolio failed after costs.
- **So a new gold-only test on the same history would be biased.** The fair test is
  **forward**:
  1. Commit this rule now.
  2. Log its signals daily on the demo (paper) for 3–6 months, with real swaps.
  3. Pass if the forward P&L after costs is positive and matches the backtest's behaviour
     (trade count and win/loss size).
- **Prop rules:** holds over weekends, so an **FTMO Swing** account (or close before Friday)
  would be needed.

## Sources
- [Gold falls 1.2% after US Fed rate rise on 16 Sep (Nation Thailand)](https://www.nationthailand.com/news/40071118)
- [Fed signals more hikes, keeping gold below 4,400 (Crux Investor)](https://www.cruxinvestor.com/posts/fed-signals-more-hikes-keeping-gold-below-4-400-into-october)
- [Gold price outlook September 2026 (GoldSilver)](https://goldsilver.com/industry-news/article/gold-price-outlook-september-2026/)
- [Why central banks are buying record gold as prices drop (Crux Investor)](https://www.cruxinvestor.com/posts/why-central-banks-are-buying-record-gold-as-prices-drop-16)
- [Gold: central bank buying offsets ETF outflows — ING (FXStreet)](https://www.fxstreet.com/news/gold-central-bank-buying-offsets-etf-outflows-ing-202607310855)
- [For gold investors, the best approach in 2026 may be to do nothing (Livewire)](https://www.livewiremarkets.com/wires/for-gold-investors-the-best-approach-in-2026-may-be-to-do-nothing)
