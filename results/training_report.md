# Agent Training Report (Walk-Forward)

- Horizon: 3 bars forward | Predictions logged: 245
- Directional calls: 195
- **Overall hit-rate: 42.8%** (194 calls, avg move -0.07%)

## Hit-rate by Regime

| Regime | Calls | Hit-rate% | Avg move% |
|---|---|---|---|
| RANGE | 109 | 47.7 | -0.15 |
| TRANSITION | 39 | 33.3 | +0.13 |
| TRENDING | 36 | 36.1 | +0.09 |
| VOLATILE | 10 | 50.0 | -0.57 |

## Hit-rate by Bias

| Bias | Calls | Hit-rate% | Avg move% |
|---|---|---|---|
| CALL | 112 | 42.0 | -0.22 |
| PUT | 82 | 43.9 | +0.13 |

## Hit-rate by Signal Strength

| Strength | Calls | Hit-rate% |
|---|---|---|
| HIGH | 36 | 36.1 |
| MEDIUM | 11 | 45.5 |
| LOW | 147 | 44.2 |

## Lessons (auto-derived)
- Agent is most accurate in **VOLATILE** markets (50.0% hit-rate, n=10)
- High-confidence calls (>=60% conf): 40.4% hit-rate (n=171) - still need caution