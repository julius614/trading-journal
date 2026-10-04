# Investor lenses — questflowai/investorskills

Repo: https://github.com/questflowai/investorskills (MIT). 63 skills that package how a
well-known investor or firm thinks: what they look for, what they reject, how they size and
cut risk. They are **checklists and frames**, not trading signals.

## Structure
```
skills/<name>/
├── SKILL.md   # frontmatter (name, description, invest: ./invest.md) + sections:
│              # When To Use · Do Not Use · Inputs Needed · Process · Output Format · Guardrails
└── invest.md  # optional machine-readable schema: signals, filters, sizing, risk
```
Example (livermore): process = clear direction → pivotal point → volume/follow-through →
reject late/choppy setups → risk-first plan; guardrails = no averaging down, no buying
before confirmation, add only to winners, never widen stops.

## Install
```
npx skills add https://github.com/questflowai/investorskills                    # all
npx skills add https://github.com/questflowai/investorskills --skill "livermore"  # one
```
(The README's own example uses a mirror owner `xuboyuebobb`; use the questflowai URL.)
Without Node.js: download the repo zip and copy the wanted `skills/<name>` folders into this
repo's `.claude/skills/`. Read a lens's `SKILL.md` before applying it — follow its Process and
Output Format rather than paraphrasing the investor from memory.

## Picking lenses (use 2–3 that fit the asset and horizon)

| Style | Skill folders | Fits |
|---|---|---|
| Classic value | `buffett`, `munger`, `graham-net-net`, `schloss-cigar-butt`, `klarman-deep-value`, `li-lu-value`, `templeton-max-pessimism`, `watsa-insurance-float`, `hohn-concentrated-quality`, `nick-sleep-scale-economies`, `marks-cycles` | Listed companies, multi-year holds; needs fundamentals |
| Growth / momentum stocks | `lynch-growth`, `oneil-canslim`, `minervini-vcp`, `darvas-box`, `coleman-tiger-growth`, `cathie-wood-innovation` | Stocks with earnings growth, weeks–years |
| Macro | `soros-reflexivity`, `druckenmiller`, `dalio-principles-allweather`, `ptj-macro-trend`, `tepper-distressed-macro`, `gundlach-bonds`, `libei-macro-hedge`, `shihanbing-macro-interest-analysis` | FX, rates, indices, commodities; regime calls |
| Trend / technical | `livermore`, `seykota-systematic-trend`, `turtle-trading`, `tangnengtong-shortterm-ta`, `chenhao-limit-up`, `fengliu-reverse-weakhand` | Liquid markets incl. FX/CFDs; rule-based entries/stops |
| Activist / special situations | `icahn-activist`, `ackman-concentrated-activism`, `greenblatt-special-situations`, `burry-asymmetric-contrarian` | Single stocks with a catalyst |
| Forensic / short | `einhorn-forensic-short`, `muddy-waters-forensic`, `hindenburg-investigation`, `spruce-point-accounting-short` | Red-flag checks before owning a stock |
| Quant | `simons-quant` | Reminder of data/statistics discipline |
| Venture / thematic | `sequoia-founder-market`, `a16z-techno-optimist`, `founders-fund-contrarian`, `usv-network-effects`, `yc-early-pmf` | Private/early companies, themes |
| Crypto | `a16z-crypto`, `arthur-hayes-liquidity`, `ansem-crypto`, `cobie-cycle-filter`, `cryptocred-structure`, `delphi-thematic-crypto`, `grayscale-crypto-sectors`, `hsaka-crypto-ta`, `multicoin-thesis-vc`, `paradigm-crypto-research`, `placeholder-token-networks`, `willy-woo-onchain` | Crypto assets |
| China / A-shares | `duanyongping-benfen-value`, `danbin-longterm-compounder`, `qiuguolu-value-quality`, `zhanglei-longterm-research-value`, `dengxiaofeng-cycle-industry`, `serenity` | Chinese equities |

Rules of use:
- Match the lens to the asset: value lenses on EURUSD or a 48-hour pairs trade are noise;
  for this repo's FX/CFD bots the relevant lenses are trend/technical and macro.
- Report each lens's verdict **and** where lenses disagree.
- A lens verdict never replaces the validation gate.
