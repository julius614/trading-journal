# Intraday strategy research (M5, flat every night)

This tests three published intraday strategies on your broker's data, with fixed rules
decided in advance. The rationale and protocol are in
[`knowledge-base/strategies/intraday-momentum/README.md`](../../knowledge-base/strategies/intraday-momentum/README.md).

There is **no trading bot here yet.** One is built only if the research passes its
pre-declared "strong" test.

| File | Role |
|---|---|
| `research/sessions.py` | Market sessions (New York / Frankfurt / London, DST-aware), M5 bars into days |
| `research/data.py` | Loads `<SYMBOL>_M5.csv` and `<SYMBOL>_spec.json`; MT5 spread to price |
| `research/strategies.py` | NA (noise area), LH (late half hour), OR (5-min opening range); fixed parameters |
| `research/engine.py` | Costs (spread, slippage, FX commission) and statistics |
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
python -m bots.amd_fx.download_history --timeframe M5 --bars 400000 --out-dir data/intraday --gzip --symbols US500 NAS100 US30 GER40 UK100 XAUUSD USOIL EURUSD GBPUSD USDJPY AUDUSD USDCAD
```
Each symbol prints its date range. **Paste that output back to me.** Three or more years
per symbol is good; under two years is too short to judge.

**4. Send me the data**
```powershell
git add data/intraday
git commit -m "Add M5 data for the intraday race"
git push
```

I then run the race once and report the verdict:
```powershell
python -m bots.intraday.research.protocol --data-dir data/intraday
```

## Tests
```powershell
pytest -q bots/intraday
```
