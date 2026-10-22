# Trading journal: instructions for Claude

## Start of every session
1. Read `knowledge-base/LESSONS.md`. It is the memory of everything learned so far.
2. Skim `knowledge-base/INDEX.md` to see what is in the knowledge base.
3. If `inbox/` contains files other than `.gitkeep` and the README (not counting
   `inbox/processed/`), tell the user there are new items and offer to learn them (skill
   `kb-learn`).

## When the user pastes something to learn from
Use the `kb-learn` skill. It files the item, distils lessons into LESSONS.md, and commits
and pushes.

## About the user
- Not technical. Uses Windows PowerShell and an MT5 MetaQuotes-Demo account (EUR).
- Answer in plain language with exact copy-paste commands. Say `cd` into the repo folder
  first.
- Goal: a strategy that is strong enough for prop-firm challenges, tested honestly.

## Hard rules
- Never place live orders without the user's explicit confirmation. Demo comes first.
- Credentials live only in `.env` (gitignored). Never commit them or print them.
- New strategy tests follow
  `.claude/skills/ai-trading-stack/references/validation-gate.md`: rules fixed and
  committed before the data, real costs, a hold-out touched once.
- The repository is public. Store summaries of other people's articles, not full copies.
