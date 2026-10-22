---
name: kb-learn
description: The user's learning knowledge base. Use whenever the user pastes something to learn from (an article, notes, a video transcript, a strategy idea, trade history, screenshots of trades, or a price-data CSV) or says "learn this", "add to knowledge base", "remember this", "learn the inbox", "what have you learned", "what do you know about X". Files each item in the right place (notes, idea cards, my-trading reports, data/user), distils lessons into knowledge-base/LESSONS.md with evidence levels, then commits and pushes so the next session remembers.
---

# kb-learn: paste data, Claude learns from it

Claude does not keep memory between sessions. **The repository is the memory.** Learning
means filing what the user gives, distilling it into `knowledge-base/LESSONS.md`, and
committing and pushing it. Every session reads LESSONS.md first (see `CLAUDE.md`).

The user is not technical and works in Windows PowerShell. Explain in plain words and give
exact copy-paste commands.

## 1. Sort each item into one of four types

| Type | Signs | Goes to |
|---|---|---|
| **Note** | article, book, course, video transcript, AI chat, market opinion | `knowledge-base/notes/YYYY-MM-DD-<slug>.md` |
| **Idea** | entry/exit rules, "a strategy that…", indicator setup | `knowledge-base/ideas/<slug>.md` + its index table |
| **Trades** | MT5 history/report, journal rows, trade screenshots | `inbox/trades/` → `python -m bots.kb.trades report <csv>` → `knowledge-base/my-trading/` |
| **Prices** | OHLC CSV, MT5 bar export | `python -m bots.kb.prices <csv> --symbol <SYM> [--tz ny_close\|utc\|2]` → `data/user/` |

One paste can contain several types; split it. If the type is unclear, ask once.

## 2. File it

**Notes**
- Follow the template in `knowledge-base/notes/README.md`.
- The repository is **public**: store a summary, key points and at most a few short quotes,
  plus the source link. Never the full text of someone else's article, book or transcript.
  The user's own writing may be stored in full.
- Tag the evidence level honestly. Most internet content is **CLAIM**.

**Ideas**
- Follow the card template in `knowledge-base/ideas/README.md`.
- Write the rules exactly as given. Mark any gaps as "interpretation: …".
- Set status to `untested`.
- Check `knowledge-base/README.md` (strategies table) and LESSONS.md for similar ideas
  already tested, and link them. If it is a near-duplicate of a failed idea, say so plainly.
- Do not backtest unless the user asks. When asked, use the honest protocol in
  `.claude/skills/ai-trading-stack/references/validation-gate.md` with the
  `bots/spec10`/`bots/edge` engines.

**Trades**
- Save the CSV in `inbox/trades/` and run the report.
- Screenshots or pasted text: type the rows into a CSV with the columns
  `symbol,side,open_time,close_time,open_price,close_price,sl,volume,profit`
  (times in UTC if known, otherwise note the time zone), then run the report.
- Remind the user once that the repository is public and their history will be visible
  (see `inbox/README.md` for how to make it private).

**Prices**
- Run the checker. Report the timeframe, date range, gaps and any warning about Saturday
  bars, which mean the wrong `--tz`.

Once an item is processed, move it from `inbox/<type>/` to `inbox/processed/` with
`git mv`.

## 3. Distil into LESSONS.md (this is the "learning")
- Add 1–3 short lessons under the right heading. Each lesson needs an evidence level
  (TESTED / RESEARCH / USER / CLAIM) and a link to the note, report or card.
- **Agreement:** append "(+ support: <link>)" to the existing lesson instead of
  duplicating it.
- **Contradiction:** never overwrite a TESTED lesson with a CLAIM. Add the new view as
  **CONFLICT** next to it and add a test to "Open questions to test".
- **From the user's own trades:**
  - only facts with enough trades (about 30 or more per group) become lessons;
  - smaller groups go to "Open questions";
  - be kind but direct about process problems (no stop-loss, oversizing, revenge trading).
- Keep LESSONS.md short enough to read in a minute. Merge lessons that say the same thing.

## 4. Update the indexes, then commit and push
- `knowledge-base/INDEX.md`: one row per new note, idea or report.
- `knowledge-base/ideas/README.md` table, for ideas.
- Run `git add` on the new or changed files, commit with a clear message ending in the
  session's attribution lines, and push to the working branch.

## 5. Answer back in three lines or fewer
- What was filed and where.
- What was learned (the new LESSONS lines).
- Anything worth testing, or a conflict with what we already know.

## Answering questions with the knowledge base
For "what do you know about X", "what have you learned" or any trading question:
1. Read LESSONS.md and search `knowledge-base/` (Grep for the topic).
2. Answer from the files first, citing them by path. Say which parts are TESTED and which
   are only CLAIM.
3. Then add general market knowledge, clearly labelled as such.

## Guardrails
- Never store passwords, account numbers, server logins or API keys. Credentials live only
  in `.env`, which is gitignored.
- Never place or suggest live orders from pasted material without the user's explicit
  decision. Ideas go to a test first, then a demo.
- A pasted "this strategy wins 80%" is a CLAIM until our own test says otherwise.
