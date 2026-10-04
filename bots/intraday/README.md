# Intraday strategy research (M5, flat every night)

This tests five intraday strategies (three published, two the user proposed) on your broker's data, with fixed rules
decided in advance. The rationale and protocol are in
[`knowledge-base/strategies/intraday-momentum/README.md`](../../knowledge-base/strategies/intraday-momentum/README.md).

There is **no trading bot here yet.** One is built only if the research passes its
pre-declared "strong" test.

| File | Role |
|---|---|
| `research/sessions.py` | Market sessions (New York / Frankfurt / London, DST-aware), M5 bars into days |
| `research/dukascopy.py` | Long M5 history from Dukascopy, broker spreads attached |
| `research/histdata.py` | Long M5 history from HistData.com 1-minute files, spliced onto the broker's recent data |
| `research/data.py` | Loads `<SYMBOL>_M5.csv` and `<SYMBOL>_spec.json`; MT5 spread to price |
| `research/strategies.py` | NA (noise area), LH (late half hour), OR (5-min opening range), SW (liquidity sweep + FVG), BK (M15 Donchian breakout); fixed parameters |
| `research/engine.py` | Costs (spread, slippage, FX commission) and statistics |
| `research/costs.py` | Post-hoc break-even costs per strategy × market |
| `research/protocol.py` | The pre-declared race: split, join/keep rules, portfolio, challenge odds, plateau check |
| `research/tests/` | Synthetic-data tests: sessions, each rule, no look-ahead, costs, protocol rules |

## Steps for you (Windows PowerShell, MT5 open and logged in)
Type only the lines below, one at a time.

**1. Get the new code**
```powershell
cd C:\path\to\trading-journal
git pull
```

**2. Find your broker's symbol names** (they differ: `US500`, `US500.cash`, `SPX500`...)
```powershell
$env:MT5_SERVER_TIMEZONE="ny_close"
python -m bots.amd_fx.download_history --list "*500*"
python -m bots.amd_fx.download_history --list "*100*"
python -m bots.amd_fx.download_history --list "*30*"
python -m bots.amd_fx.download_history --list "*GER*"
python -m bots.amd_fx.download_history --list "XAU*"
python -m bots.amd_fx.download_history --list "*OIL*"
```

**3. Download M5 history.** Replace the names with yours from step 2. In MT5, first set
Tools > Options > Charts > "Max bars in chart" to **Unlimited**.
```powershell
python -m bots.amd_fx.download_history --timeframe M5 --from 2019-01-01 --out-dir data/intraday --gzip --symbols US500 USTECH100M US30 DAX UK100 XAUUSD WTI EURUSD GBPUSD USDJPY AUDUSD USDCAD
```
`--from` downloads in 60-day chunks, because a single MT5 request stops at ~100k bars.
Each chunk prints its bar count (0 = the server has nothing that far back). Each symbol prints its date range. **Paste that output back to me.** Three or more years
per symbol is good; under two years is too short to judge.

**4. Get longer history from Dukascopy** (your broker keeps only ~1.5 years of M5).
This uses your broker files from step 3 for spreads and the price scale, needs no MT5,
and takes roughly 30–60 minutes. If it stops, run it again; it resumes.
```powershell
python -m bots.intraday.research.dukascopy --check
python -m bots.intraday.research.dukascopy --from 2019-01-01
```
`--check` downloads one day per market in about 10 seconds. Every line should say OK.

**4b. If Dukascopy keeps refusing: HistData.com instead** (reliable, but manual).
For each market and each year 2019–2025, open
`https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/<code>/<year>`
(codes: spxusd, nsxusd, grxeur, xauusd, eurusd, gbpusd, ukxgbp, wtiusd, usdjpy, audusd,
usdcad), click the `HISTDATA_COM_ASCII_..._M1<year>.zip` link, and save the zip, unopened,
in `data/histdata_raw/`. Then:
```powershell
python -m bots.intraday.research.histdata
```
It writes `data/intraday_hd/`. Run the race with `--data-dir data/intraday_hd`.

**5. Send me the data**
```powershell
git add data/intraday data/intraday_duka data/intraday_hd
git commit -m "Add M5 data for the intraday race"
git push
```

I then run the race once and report the verdict:
```powershell
python -m bots.intraday.research.protocol --data-dir data/intraday_duka
```

## Cost scenarios (post-hoc diagnostics only)
```powershell
python -m bots.intraday.research.costs --data-dir data/intraday_hd
python -m bots.intraday.research.protocol --data-dir data/intraday_hd --cost-mult 0.5
python -m bots.intraday.research.protocol --data-dir data/intraday_hd --spread-from data/intraday_ftmo --spread-map US500=US500.cash
```
`--spread-from` swaps in another broker's spreads (from its own MT5 M5 files, by UTC hour
of the week). Results are flagged as post-hoc.

## Tests
```powershell
pytest -q bots/intraday
```
