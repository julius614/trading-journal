# OpenBB — data layer

Repo: https://github.com/OpenBB-finance/OpenBB (Apache-2.0). Now positioned as the "Open
Data Platform" (ODP): one Python library, REST API and MCP server over many data providers.

## Install
```
pip install openbb                 # library with core providers
pip install openbb-cli             # optional terminal CLI
pip install openbb-mcp-server      # MCP server for AI agents
```
Lighter installs are possible per extension (e.g. `pip install openbb-equity openbb-yfinance`).

## Python basics
```python
from openbb import obb

df = obb.equity.price.historical("AAPL").to_dataframe()            # daily OHLCV
fx = obb.currency.price.historical("EURUSD", provider="yfinance", start_date="2015-01-01").to_dataframe()
ix = obb.index.price.historical("^GSPC", provider="yfinance").to_dataframe()
bt = obb.crypto.price.historical("BTC-USD", provider="yfinance").to_dataframe()
```
Other command groups (names follow the API routes; check `obb.coverage` or the reference at
https://docs.openbb.co/python/reference for exact parameters and providers):
- fundamentals: `obb.equity.fundamental.income / balance / cash / metrics`
- options: `obb.derivatives.options.chains("AAPL")`
- economy: `obb.economy.fred_series("CPIAUCSL")` (needs a free FRED key)
- also `fixedincome`, `etf`, `news`, `commodity`, `regulators`

Provider keys (free FRED key; paid ones like Polygon/FMP/Intrinio are optional):
```python
obb.user.credentials.fred_api_key = "..."   # better: load from .env, never hard-code
```
`provider="yfinance"` needs no key and covers stocks, ETFs, indices, FX and crypto daily
bars — good enough for daily research; **not** a substitute for broker spreads or tick data.

## MCP server (lets Claude call OpenBB directly)
```
openbb-mcp                                                     # after pip install openbb-mcp-server openbb
uvx --from openbb-mcp-server --with openbb openbb-mcp          # without installing globally
```
Claude Desktop / Claude Code config:
```json
{
  "mcpServers": {
    "openbb-mcp": {
      "command": "uvx",
      "args": ["--from", "openbb-mcp-server", "--with", "openbb", "openbb-mcp", "--transport", "stdio"]
    }
  }
}
```
Tools are named after API routes (`/equity/price/historical` → `equity_price_historical`);
discovery tools (`available_categories`, `available_tools`, `search_tools`) may be enabled.
REST alternative: `openbb-api` serves FastAPI at http://127.0.0.1:6900.

## Feeding this repo's research tools
The repo's daily/hourly tools read CSVs with columns
`datetime, open, high, low, close, volume, spread` plus a `<SYMBOL>_spec.json` with at least
`point` (see `bots/intraday/research/data.py`). Example for a daily trend dataset:
```python
import json, pandas as pd
from openbb import obb

def export_daily(symbol: str, yf_ticker: str, point: float, out_dir="data/trend_openbb",
                 spread_points: float = 0.0):
    df = obb.currency.price.historical(yf_ticker, provider="yfinance", start_date="2005-01-01").to_dataframe()
    df.index = pd.to_datetime(df.index).tz_localize("UTC")
    out = df[["open", "high", "low", "close"]].copy()
    out["volume"] = df.get("volume", 0)
    out["spread"] = spread_points          # yfinance has no spreads: use your broker's typical spread
    out.to_csv(f"{out_dir}/{symbol}_D1.csv.gz", index_label="datetime", compression="gzip")
    json.dump({"symbol": symbol, "point": point, "source": f"openbb:yfinance:{yf_ticker}"},
              open(f"{out_dir}/{symbol}_spec.json", "w"))
```
Daily bars from yfinance are stamped at the date (00:00), not at MT5 server midnight;
`bots/trend/research/trend.py:trading_dates` adds 3 hours before normalising, which keeps
00:00 bars on the same date — fine. Use the broker's own spreads for costs.
