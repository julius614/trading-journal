# EPAT (Executive Programme in Algorithmic Trading) — Study Notes

## Source & capture

- **Primary source:** QuantInsti EPAT programme page — <https://www.quantinsti.com/epat>
- **Captured:** 2026-10-02
- **How it was captured:** the page itself could not be downloaded from the environment these
  notes were written in. The notes are built from search-indexed excerpts of the EPAT page
  and its sub-pages (admissions, FAQ, module pages). Tags: **(epat)** = QuantInsti's own
  EPAT pages; **(other)** = third-party listings (NSE, Shiksha, brochures, reviews).
- **This is a sales page for a paid programme.** Fees, dates and batch numbers change
  often — **check the live page before any decision.** These notes are for studying the
  syllabus as a learning map, not an endorsement.

---

## 1. What it is

- A **6-month, online, instructor-led certification** in algorithmic and quantitative
  trading, run by QuantInsti. (epat)
- **120+ hours of live lectures**, **150+ hours of recorded material** (270+ hours total),
  with lifetime access to the content. (epat/other)
- Built on **three pillars**: **Statistics & Econometrics**, **Quantitative Trading
  Techniques**, and **Financial Computing (Python)**. Covers equities, FX, options, futures
  and ETFs. (epat)
- Described by QuantInsti as the first **proctored certification** in algorithmic trading. (epat)

## 2. Curriculum — use this as a study syllabus

| # | Module | Key topics |
|---|---|---|
| 0 | **Primers** (for beginners) | Statistics, econometrics, options, financial markets, Excel, Python — each with an assessment test (epat) |
| 1 | **Python** | ~15 hours of Python basics, then financial computing with Python (epat) |
| 2 | **Statistics primer** | Descriptive statistics, probability, distributions, inferential statistics, intro to linear regression (epat) |
| 3 | **Statistics for financial markets** | Stats and probability on market data, **modern portfolio theory**, **Monte Carlo simulation**, **CAPM** (epat) |
| 4 | **Advanced statistics for quant strategies** | Time-series models — **ARIMA, ARCH, GARCH** — and strategies built on them (epat) |
| 5 | **Equity, FX & futures strategies** | Moving-average crossovers, **VWAP**, momentum, trend following, **statistical arbitrage**, arbitrage, **market making**, **position sizing** (epat) |
| 6 | **Options trading & strategies** | Payoff diagrams, **Black–Scholes–Merton**, **Greeks**, volatility trading, hedging (epat) |
| 7 | **Machine learning for trading** | SVM, k-means, logistic regression, decision trees, random forests, neural networks / deep learning, **PCA for stat arb** (epat) |
| 8 | **Market microstructure for HFT** | Order books, liquidity, execution in high-frequency settings (epat) |
| 9 | **Also covered** | Risk management, electronic market making, trading technology (other) |
| — | **Project** (optional) | Self-driven strategy or business research under expert mentorship; **no weight in the final score**, but a chance to specialise in an asset class or strategy style (epat) |

## 3. Format & time commitment

- Live lectures on **weekends**; recordings available. (epat)
- Expect **6–8 hours of live lectures + 8–12 hours of self-study per week.** (epat)
- Personal support and one-on-one access to faculty. (epat)

## 4. Faculty (examples)

- **Dr. Robert Kissell** — Kissell Research Group; formerly UBS, JP Morgan (execution and
  transaction-cost research). (other)
- **Dr. Yves J. Hilpisch** — The Python Quants; author on Python for finance. (other)
- About 20 industry experts in total. (epat)

## 5. Eligibility

- Open to people from **any background**. Basic finance, programming or Excel helps;
  **intermediate English** is recommended. (epat)
- Beginners get the primer modules first (row 0 above). (epat)

## 6. Fees & dates (snapshot — verify before acting)

| Item | As found on 2026-10-02 |
|---|---|
| Batch 71 | Started 11 Jul 2026. Fee tiers (currency not shown in the excerpt, likely USD): super early bird **6,999**, early **8,599**, standard **9,499** (epat) |
| Batch 72 | Starts **10 Oct 2026**, last date to enrol **6 Oct 2026**; fee tiers said to be similar (epat/other) |
| India | about **₹3.79 lakh** total (other) |
| Third-party listing | "about $5,000" — **conflicts** with the tiers above; probably outdated (other) |

Financial help (epat):
- Merit-based scholarship based on a test score
- Discount for full-time students
- **Singapore:** IBF-STS subsidy up to 70%, capped at S$3,000
- **USA:** income-based subsidy for incomes under USD 120,000

## 7. After the programme

- **Verified certificate** on completion. (epat/other)
- **Lifetime placement assistance**, with a network of **300+ hiring partners**. (epat/other)
- Target roles: quant trader, quant developer, quant analyst/researcher, data scientist —
  see [Quantitative Trader](../quantitative-trader/README.md) and
  [Quantitative Developer](../quantitative-developer/README.md) notes.
- EPAT vs. Quantra is compared in the
  [Quantitative Trader notes, section 8](../quantitative-trader/README.md#8-quant-trader-courses--algorithmic-trading).

## 8. Self-study version of the syllabus (free / cheap route)

The syllabus works as a learning map even if I don't enrol:

1. **Python + pandas/NumPy** → 2. **Statistics & probability** → 3. **Portfolio theory,
   CAPM, Monte Carlo** → 4. **Time series (ARIMA/GARCH)** → 5. **Classic strategies**
   (MA crossover, momentum, trend, stat arb, VWAP) → 6. **Options & Greeks** →
   7. **ML for trading** (see [AI for Trading notes](../ai-for-trading/README.md)) →
   8. **Microstructure & execution** → 9. **A personal project** (one strategy,
   backtested, paper-traded, journaled).

## 9. Key takeaways

1. EPAT = 6 months, ~270 hours, three pillars: **statistics, quant strategies, Python**.
2. Its syllabus is a solid **checklist of what a quant trader should know**.
3. It is **expensive** (thousands of USD) — weigh it against self-study plus Quantra.
4. The main extras over self-study are **live faculty, a certificate and placement help**.
5. Fees and dates move; always check the live page.

## Self-check questions

1. What are EPAT's three pillars?
2. What do ARIMA and GARCH model, and why do they matter for trading?
3. What are the options Greeks, and what does each measure?
4. How is PCA used in statistical arbitrage?
5. Which parts of the syllabus have I already covered, and which are gaps?

## Applying it to my journal

- **Tag each strategy** with its syllabus family (momentum, trend, stat arb, mean reversion,
  options/volatility, ML) so I can compare performance by family.
- For options trades, log the **Greeks at entry** (delta, gamma, theta, vega) and the
  implied volatility.
- Log **position-sizing method** per trade (fixed, % risk, volatility-based).
- Keep a **syllabus tracker**: one row per module from section 2, with status and notes.
- Treat one strategy as my **"EPAT project"**: hypothesis → backtest → paper trade → live,
  all documented here.

## Further reading

- [EPAT programme page](https://www.quantinsti.com/epat) (primary)
- [EPAT for professional traders](https://www.quantinsti.com/epat/for-traders)
- [EPAT admissions](https://www.quantinsti.com/admissions) · [FAQ](https://www.quantinsti.com/faq) · [Personal support](https://www.quantinsti.com/epat/support)
- Module pages: [Statistics for Financial Markets](https://www.quantinsti.com/epat/statistics-financial-markets) · [Market Microstructure for HFT](https://www.quantinsti.com/epat/market-microstructure)
- [EPAT, Quantra or both?](https://blog.quantinsti.com/epat-quantra/) · [EPAT vs Quantra comparison](https://www.quantinsti.com/epat-quantra-comparison)
- [Quant jobs via EPAT](https://www.quantinsti.com/quant-jobs) · [QuantInsti reviews](https://www.quantinsti.com/reviews)
- [EPAT on NSE India](https://www.nseindia.com/static/learn/executive-programme-in-algorithmic-trading-epat) (other)
- [EPAT on Shiksha — fee, review, duration](https://www.shiksha.com/provider/quantinsti-229221/course-online-executive-programme-in-algorithmic-trading-epat-1237063) (other)
