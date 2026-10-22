# Inbox: drop anything here for Claude to learn from

There are two ways to add something:
1. **Paste it in the chat** and say "learn this". Claude files it for you.
2. **Put a file in a folder below,** commit and push it, then say "learn the inbox".

| Folder | What goes in | What Claude does with it |
|---|---|---|
| `notes/` | Articles, book notes, YouTube transcripts, course notes, AI chat answers (.md / .txt / .pdf) | Writes a summary note in `knowledge-base/notes/`, tags it, and adds the key lessons to `knowledge-base/LESSONS.md` |
| `ideas/` | Strategy rules you found or invented | Writes a strategy card in `knowledge-base/ideas/` with fixed rules and status "untested". It is backtested when you ask |
| `trades/` | Your MT5 trade history | Runs `python -m bots.kb.trades report …` and writes the facts to `knowledge-base/my-trading/` and the lessons to LESSONS.md |
| `prices/` | Price data CSVs (MT5: Symbols → Bars → Export) | Runs `python -m bots.kb.prices …`: checks the data and files it in `data/user/` for backtests |

Once a file has been processed it is moved out of the inbox, so the inbox only holds new
items.

## Getting your trades out of MT5 (on your Windows PC, MT5 open and logged in)
```
cd C:\path\to\trading-journal
$env:MT5_SERVER_TIMEZONE = "ny_close"
python -m bots.kb.trades export --days 365
git add inbox/trades
git commit -m "my trades"
git push
```
The file contains no account number, password or server.

## ⚠ This repository is PUBLIC
Everything committed here can be read by anyone on GitHub, and that includes your trade
history. To keep it private, go to github.com → the repo → **Settings → General → Danger
Zone → Change visibility → Private**.

Pasted articles are stored as **summaries with the source link**, not as full copies,
because copying other people's articles into a public repo is not allowed.
