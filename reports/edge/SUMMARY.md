# Edge search - summary

Pre-declared protocol: `bots/edge/protocol.md`. Hold-out touched once.


| candidate | hold-out trades | exp R @x1 | exp R @x2 | net USD | random p99 | verdict |
|---|---|---|---|---|---|---|
| C1_calendar | 188 | 0.1138 | 0.0704 | 10695 | 32222 | FAIL |
| C2_sweep_D1 | 1133 | -0.2077 | -0.3421 | -117687 | -22339 | FAIL |


Nothing passed, so there is no portfolio step.

## Notes

- Rules, periods and gates: `bots/edge/protocol.md` (committed before this run).
- Costs: spread + slippage + swap (indices/gold 5%/yr, FX 2%/yr, Wednesday x3).
- FOMC dates: `data/events.csv`, written from memory (official pages unreachable), so one-day errors are possible.
