# Strategy Research Report (Options Buying)

_Generated: 08 Aug 2026 16:05_

- Total configurations tested: **1176**
- Positive PnL strategies: **402**
- Minimum 20 trades filter (avoid overfit): applied to rankings below

## Top Performers (by PnL, min 20 trades)

| Strategy | Params | Hold | Trades | PnL | WinRate% | ProfitFactor | AvgRet% | MaxDD% | Sharpe | CAGR% |
|---|---|---|---|---|---|---|---|---|---|---|
| rsi_meanrev | {'low': 40, 'high': 60} | 7 | 36 | 399900.96 | 58.3 | 2.87 | 44.64 | -24.64 | 5.5 | 145.84 |
| stoch_cross | {'low': 25, 'high': 75} | 10 | 30 | 319653.9 | 46.7 | 2.34 | 42.86 | -28.26 | 4.92 | 123.48 |
| stoch_cross | {'low': 30, 'high': 70} | 10 | 31 | 319206.35 | 45.2 | 2.34 | 41.42 | -28.26 | 4.83 | 123.35 |
| rsi_meanrev | {'low': 45, 'high': 55} | 2 | 97 | 293940.97 | 46.4 | 1.74 | 12.17 | -45.48 | 2.63 | 114.69 |
| rsi_meanrev | {'low': 45, 'high': 55} | 5 | 59 | 269921.98 | 39.0 | 1.64 | 18.42 | -36.66 | 2.91 | 107.29 |
| momentum_roc | {'n': 40, 'thresh': 1.0} | 1 | 116 | 244224.87 | 47.4 | 1.63 | 8.47 | -27.75 | 2.76 | 113.19 |
| momentum_roc | {'n': 40, 'thresh': 1.5} | 1 | 110 | 241051.33 | 48.2 | 1.63 | 8.81 | -27.75 | 2.79 | 111.99 |
| rsi_meanrev | {'low': 40, 'high': 60} | 10 | 29 | 235298.69 | 37.9 | 1.89 | 32.54 | -37.55 | 3.32 | 96.65 |
| rsi_meanrev | {'low': 40, 'high': 60} | 3 | 55 | 213527.85 | 49.1 | 1.81 | 15.62 | -27.51 | 3.53 | 89.41 |
| momentum_roc | {'n': 50, 'thresh': 2.0} | 3 | 60 | 204036.01 | 43.3 | 1.73 | 13.68 | -55.49 | 3.01 | 100.85 |
| stoch_cross | {'low': 15, 'high': 85} | 5 | 35 | 183676.16 | 45.7 | 1.88 | 21.16 | -19.52 | 3.62 | 79.43 |
| rsi_meanrev | {'low': 40, 'high': 60} | 1 | 81 | 175648.12 | 54.3 | 1.73 | 8.72 | -19.7 | 2.97 | 76.25 |
| stoch_cross | {'low': 35, 'high': 65} | 10 | 31 | 169566.82 | 41.9 | 1.68 | 22.05 | -59.87 | 2.86 | 74.37 |
| stoch_cross | {'low': 40, 'high': 60} | 10 | 31 | 169566.82 | 41.9 | 1.68 | 22.05 | -59.87 | 2.86 | 74.37 |
| stoch_cross | {'low': 45, 'high': 55} | 10 | 31 | 167325.12 | 41.9 | 1.67 | 21.76 | -59.87 | 2.82 | 73.55 |

## Best Win Rate (min 20 trades)

| Strategy | Params | Hold | Trades | PnL | WinRate% | ProfitFactor | AvgRet% | MaxDD% | Sharpe | CAGR% |
|---|---|---|---|---|---|---|---|---|---|---|
| trend_sma | {'fast': 20, 'slow': 50, 'adx_thresh': 25, 'use_adx': True} | 1 | 35 | 104775.07 | 65.7 | 1.81 | 12.03 | -34.06 | 3.44 | 63.67 |
| trend_sma | {'fast': 20, 'slow': 50, 'adx_thresh': 30, 'use_adx': True} | 1 | 25 | 27286.73 | 64.0 | 1.26 | 4.42 | -36.18 | 1.36 | 18.04 |
| trend_sma | {'fast': 5, 'slow': 50, 'adx_thresh': 25, 'use_adx': True} | 1 | 27 | 89531.91 | 59.3 | 2.25 | 13.32 | -21.45 | 4.11 | 56.11 |
| rsi_meanrev | {'low': 40, 'high': 60} | 7 | 36 | 399900.96 | 58.3 | 2.87 | 44.64 | -24.64 | 5.5 | 145.84 |
| bollinger | {'bands': 2.8} | 1 | 21 | 29123.01 | 57.1 | 1.43 | 5.52 | -23.64 | 2.23 | 15.99 |

## Best Risk-Adjusted (Sharpe, min 20 trades)

| Strategy | Params | Hold | Trades | PnL | WinRate% | ProfitFactor | AvgRet% | MaxDD% | Sharpe | CAGR% |
|---|---|---|---|---|---|---|---|---|---|---|
| rsi_meanrev | {'low': 40, 'high': 60} | 7 | 36 | 399900.96 | 58.3 | 2.87 | 44.64 | -24.64 | 5.5 | 145.84 |
| stoch_cross | {'low': 25, 'high': 75} | 10 | 30 | 319653.9 | 46.7 | 2.34 | 42.86 | -28.26 | 4.92 | 123.48 |
| stoch_cross | {'low': 30, 'high': 70} | 10 | 31 | 319206.35 | 45.2 | 2.34 | 41.42 | -28.26 | 4.83 | 123.35 |
| trend_sma | {'fast': 10, 'slow': 30, 'adx_thresh': 25, 'use_adx': True} | 1 | 26 | 104574.13 | 53.8 | 2.52 | 16.12 | -18.16 | 4.7 | 68.27 |
| trend_sma | {'fast': 5, 'slow': 50, 'adx_thresh': 25, 'use_adx': True} | 1 | 27 | 89531.91 | 59.3 | 2.25 | 13.32 | -21.45 | 4.11 | 56.11 |

## Out-of-Sample Validation (top candidates on last 40% data)

_Overfit check: backtest sirf last 40% dates pe. Agar yahan bhi positive ho = strategy robust._

| Strategy | Params | Hold | Trades | PnL | WinRate% | ProfitFactor | MaxDD% | Sharpe |
|---|---|---|---|---|---|---|---|---|
| rsi_meanrev | {'low': 40, 'high': 60} | 7 | 12 | 94686.7 | 58.3 | 2.24 | -38.91 | 4.66 |
| stoch_cross | {'low': 25, 'high': 75} | 10 | 12 | 88453.74 | 41.7 | 1.86 | -23.06 | 3.22 |
| stoch_cross | {'low': 30, 'high': 70} | 10 | 13 | 88006.19 | 38.5 | 1.85 | -23.06 | 3.08 |
| rsi_meanrev | {'low': 45, 'high': 55} | 2 | 38 | 171296.23 | 52.6 | 2.34 | -20.07 | 3.73 |
| rsi_meanrev | {'low': 45, 'high': 55} | 5 | 23 | 87001.12 | 39.1 | 1.64 | -60.56 | 2.69 |

## Full Results CSV: see `results/research_results.csv`