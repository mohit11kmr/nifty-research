# X07 — Dead Code & Inert Module Audit (X-Ray)

> X-Ray phase 7. Built 2026-08-13. Definite dead, dormant, demo-grade, and
> "imported-but-never-invoked" code. Caller truth from grep sweeps.

---

## 1. Definite dead (zero importers, not in run_all/test_all)

| Module | Why dead | Evidence |
|---|---|---|
| `multi_agent_swarm.py` | 4-agent swarm (Macro/Microstructure/Capital Guard/Executive → HIGH_CONVICTION_SWARM_*) | grep: 0 importers; not in test_all/run_all. Only standalone run |
| `telegram_notifier.py` | thin standalone `send_alert` | 0 importers — **superseded** by `notifications_system` |
| `long_term_backtest.py` | "46-year" S&P/Sensex RSI+SMA200 audit, prints hardcoded "ULTRA_ROBUST" | 0 importers; standalone research artifact |

## 2. Dormant / demo-grade (present but inert)

| Module | What it claims | Reality |
|---|---|---|
| `equity_quant.py` | Mansfield RS + sector rotation heatmap | Imported by `run_all` step 17 which **prints a fixed line and never calls it**; no other consumer |
| `connection_resilience.py` | `ConnectionResilienceGuard`: DNS ping, backoff, `reconcile_offline_state()` | Only imported by test_all; **reconcile is a stub** (no real broker reconcile) |
| `history_logger.paper_trade_journal` | paper trade audit table | Table created + counted in summary, **never INSERTed anywhere** |
| `live_trader_brain.py` | master synthesis (5 engines → RECOMMENDED_*) | Standalone only; **no caller in run_all/test_all** — built but unwired |
| `smc_intelligence.py` | FVG/OB/CHoCH engine | Only consumed by live_trader_brain (itself unwired) + test_all |
| `lob_microstructure.py` / `anti_spoofing.py` | VPIN / spoof detection | Only consumed by multi_agent_swarm (**dead**) → transitively dead |
| `mcx_intel.py` | commodity bias | run_all step 17 imports but never calls |
| `adaptive_weights.py` | Q-learning weight optimizer | `update_adaptive_weights()` never gets `trade_outcomes`; `load_adaptive_weights` has **zero consumers** → written-but-never-read state (`data/adaptive_weights.json`) |
| `reflection_engine.py` | hypothesis loop | Output `reflection_hypotheses.jsonl` has **zero consumers**; hypotheses never validated/applied |
| `empirical_proof.py` | verification suite | 0 importers, only `python empirical_proof.py` |
| `volatility_forecaster.py` | GARCH/EWMA | Only smoke-tested in test_all; not in any decision path |
| `portfolio_rebalance.py` | rebalance alpha backtest | Manual only; result near-flat (0.98–1.00), no live caller |
| `profit_engine.py` | plan builder | No consumers besides itself; hardcodes 50% WR |
| `token_lookup.py` fallbacks | scrip tokens | Hardcoded fallback tokens if download fails |

## 3. Imported-but-never-invoked (dead-ish)

| Module | Imported by | Invoked? |
|---|---|---|
| `equity_quant` | run_all:203 | **No** — step prints fixed string |
| `mcx_intel` | run_all:203 | **No** |
| `skew` (skew_analytics) | run_all:203 | **No** (only other consumers exist) |

## 4. Standalone daemons / entry points (no importers, intentionally invoked)

These are NOT dead — they are the intended CLI/daemon surface:
`oi_refresh.py`, `tick_recorder.py`, `live_dash.py`, `alert_monitor.py`,
`control_center.py`, `hermes_agent.py`, `main.py` (LEGACY but functional),
`quant_daemon.py`, `build_data.py`, `daily_report.py`.

## 5. Standalone functional tools

- `trade_journal.py` — journal analyzer CLI (FIFO round-trip pairing, edge
  stats, goal projection). No importers but genuinely usable.
- `main.py` — legacy 4-command CLI, superseded by build_data + daily_report.

## 6. Legacy superseded paths

| Legacy | Superseded by |
|---|---|
| `main.py` fetch-data/report | `build_data.py` + `daily_report.py` |
| `telegram_notifier.py` | `notifications_system.py` |
| `data_fetcher` chain (requests) | `nse_live.py` (Playwright v3) |

## 7. Net waste estimate (for remediation)

- 4 modules fully dead; ~10 more effectively inert → ~13–14 of ~90 files (~15%)
  produce no live behavior.
- Biggest *misleading* surface: `auto_enhancer` "success" log,
  `market_brain` "TRAINED" constants, `lstm_neural_engine` 0.60 verdict,
  `long_term_backtest` "ULTRA_ROBUST", `multi_agent_swarm` conviction output —
  all give the impression of capability that is not wired into decisions.

## 8. Suggested handling

1. **Delete**: `multi_agent_swarm.py`, `telegram_notifier.py`,
   `long_term_backtest.py` (or move to `archive/`).
2. **Move to archive/**: `main.py`, `equity_quant.py`, `empirical_proof.py`,
   `profit_engine.py`, `portfolio_rebalance.py`, `smc_intelligence.py`,
   `live_trader_brain.py`, `lob_microstructure.py`, `anti_spoofing.py`.
3. **Wire or delete the fake success claims**: auto_enhancer verdict string,
   market_brain "TRAINED RULES" labels, lstm display, adaptive_weights/reflection
   state files.
4. **Decide**: if live_trader_brain/master synthesis is wanted, hook it into
   run_all + test_all and give it tests; otherwise archive.

> None of this affects the live decision path (regime → precision → strike →
> capital guard), which does not depend on any dead module.
