# Phase H1 v2 — AI-Ready Strategy Lab (Audit)

Author: OpenCode
Date: 2026-08-14
Status: VERIFIED — documented for handoff. No commit yet.
Scope: `strategy_schema.py`, `strategy_validator.py`, `strategy_compiler.py`,
`strategy_registry.py`, `backtest_adapter.py`, `paper_adapter.py`,
`strategy_lab.py`, `strategies/*.yaml`, `test_strategy_lab.py`.

Related frozen audits: `audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md`,
`audit/PHASE-H-STRATEGY-SPECIFICATIONS.md`,
`audit/PHASE-E-FROZEN-STRATEGY-BACKTEST.md`.

---

## 1. Objective

Phase H1 v2 turns the Phase H candidates into **versioned, declarative,
validated strategy specifications** that can be consumed later by an
AI strategy-creation loop (and any future tooling) without touching the frozen
strategy engines. The build has four hard constraints:

1. **No strategy mutation** — the frozen Phase H logic is referenced, never
   re-implemented or altered.
2. **No optimization** — nothing is tuned against results in this phase.
3. **Determinism** — identical spec bytes produce identical hashes and
   identical backtest output.
4. **Safety** — strategy files cannot express arbitrary Python; project-rule
   references are resolved only through a curated allowlist; lookahead leaks
   are rejected at validation time.

This phase produces the *specification substrate* (schema → validator →
compiler → registry → adapters → CLI → tests) and **proves control
equivalence** against the committed Phase H results. It does NOT add AI
generation, a web UI, or any live/paper trading behavior.

---

## 2. Architecture

```
strategies/*.yaml   (single source of truth, versioned specs)
        │  safe_load
        ▼
strategy_schema.py  (field registry, operators, lookahead rules,
                     project-rule ALLOWLIST, deterministic spec_hash)
        │
        ▼
strategy_validator.py  (structural + type + lookahead + allowlist checks)
        │
        ▼
strategy_compiler.py   (CompiledStrategy stable API: evaluate /
                        generate_candidate / build_order / build_exit_rules)
        │
        ├──────────────►  backtest_adapter.py  ──►  EXISTING frozen engines
        │                    (multi_strategy_backtest: run_candidate_a/b/c)
        │                        │
        │                        └──► control equivalence vs committed
        │                             results/phaseH_multi_strategy.json
        │
        └──────────────►  paper_adapter.py  ──►  EXISTING PaperExecutionEngine
                              (interface proof only, throwaway engine)
        │
strategy_registry.py   (filesystem registry: list / load / validate / compile)
        │
        ▼
strategy_lab.py        (CLI: list, validate, inspect, compile, hash,
                        backtest, equivalence)
```

Design principle: the adapters are **thin** and reuse the existing
deterministic engines. No engine logic is duplicated. Nothing new is
executable from a YAML file — only the allowlisted references resolve.

---

## 3. strategy_schema.py

Single module owning the vocabulary and the determinism contract.

| Item | Detail |
|---|---|
| `FIELD_REGISTRY` | Registered decision-time fields (e.g. `REGIME`, `VIX`, `DAILY_PNL`) with allowed field types. |
| `FIELD_TYPES` | Type map per field (`float` / `str` / `int`) used for coercion in the compiler. |
| `OPERATORS` | Comparison operators allowed in declarative conditions (`>`, `>=`, `<`, `<=`, `==`, `!=`). |
| `LOOKAHEAD_FORBIDDEN_SUBSTRINGS` | Substrings that may never appear in strategy-time fields/notes (`future_`, `tomorrow`, `next_close`, `outcome`, `realized_pnl`, `exit_price`, …). |
| `PROJECT_RULE_ALLOWLIST` | Explicit `module.function → module` map. Only these references resolve; never `getattr` on user input. |
| `PROJECT_RULE_TOKEN` | `"EXISTING_PROJECT_RULE"` — the only allowed rule token for composed rules. |
| `CANONICAL_EXPIRY_TOKEN` | `"CANONICAL_EXPIRY"` — the only allowed expiry rule. |
| `ID_PATTERN` | `^[a-z0-9_]+$` for strategy ids. |
| `spec_hash(spec)` | sha256 of the JSON-canonical (`sort_keys=True, default=str`) spec dict. |

Authoritative: all validation checks are implemented in `strategy_validator.py`
against this schema module.

## 4. strategy_validator.py

Deterministic acceptance of a strategy file. Refuses to compile anything that
fails. Checks performed:

- Required top-level sections (`strategy`, `market`, `regime`, `entry`,
  `direction`, `instrument`, `risk`, `execution`, `exit`, `state`).
- `strategy.id` matches the file stem; id matches `ID_PATTERN`; version is a
  positive integer.
- `classification` ∈ {CONTROL, WEAK, PROMISING_BUT_INSUFFICIENT, STRONG,
  RETIRED}.
- Declarative conditions: `field` ∈ `FIELD_REGISTRY`, `operator` ∈
  `OPERATORS`, value type compatible with `FIELD_TYPES`.
- Project-rule conditions: `rule == "EXISTING_PROJECT_RULE"` AND
  `project_ref` ∈ `PROJECT_RULE_ALLOWLIST` (no arbitrary code).
- Expiry rules: only `CANONICAL_EXPIRY`.
- Allowed regimes / exit reasons non-empty.
- No-lookahead scan across all string values (see §12).
- `ValidationResult` with `valid`, `errors`, `report()`; `validate_file(path)`
  wrapper.

## 5. strategy_compiler.py

`compile_strategy(spec)` → `CompiledStrategy` (deterministic; refuses invalid
specs). Stable, model-independent interface:

| Method | Contract |
|---|---|
| `evaluate(context)` | Evaluates entry conditions. Declarative conditions compare registered fields; project-rule conditions resolve **only** via the allowlist and are called with context keys matching their parameter names. Missing/unresolvable inputs yield `None` (never fabricated, never crashes). Verdict: `{entry_allowed, conditions}`. |
| `generate_candidate(context)` | Packages an engine-produced `context['candidate_rec']` into a canonical candidate dict. Returns `None` when no candidate is present. The compiler never recomputes strikes/premiums. |
| `build_order(candidate, context)` | Pure order descriptor(s) in `PaperExecutionEngine.submit_order` shape: 1 leg (NAKED_OPTION), 2 legs (defined-risk vertical), 4 legs (iron condor). NEVER submits. |
| `build_exit_rules(position, context)` | Returns the spec's exit policy (stop/target/expiry + allowed reasons) referencing the existing `exit_evaluator` reason vocabulary. |

`compile_file(path)` validates then compiles. `_resolve(ref)` imports the
allowlisted module by name and gets the callable from the allowlist entry —
never from user input.

## 6. strategy_registry.py

Filesystem-backed registry (no database; the YAML files are the source of
truth).

| Method | Behavior |
|---|---|
| `list_strategies()` | Deterministic list of `{id, name, version, classification, lifecycle, path}` for every `*.yaml` in `strategies/`. |
| `load(strategy_id, version=None)` | Returns the parsed spec; raises `KeyError` if absent; pins version when requested. |
| `validate(strategy_id)` | Returns `ValidationResult`. |
| `compile(strategy_id)` | Returns a compiled `CompiledStrategy` (fails fast on invalid specs). |
| `spec_hash(strategy_id)` | `S.spec_hash(load(...))`. |

## 7. backtest_adapter.py

Thin adapter mapping each strategy id to its authoritative frozen engine —
**the same engines Phase H ran** (no engine reimplementation):

```
current_control_v1       -> A_CURRENT_CONTROL       m.run_candidate_a
directional_spread_v1    -> B_DIRECTIONAL_SPREAD    m.run_candidate_b
range_hv_iron_condor_v1  -> C_RANGE_HV_IRON_CONDOR  m.run_candidate_c
```

`run()` loads the frozen inputs (saving/restoring the global `bf.ROOT` /
`exp_cal.CALENDAR_CSV` so no state leaks), replays the window, executes the
engine, and returns trades, metrics, by-regime, monthly, fingerprints and the
spec hash. `check_spec_consistency()` cross-checks every produced trade
against the compiled spec invariants (regime allowed, exit reason allowed,
option-type prefix, fees = orders×cost, canonical expiry exists).
`equivalence()` compares the run trades to the committed Phase H rows field
by field.

## 8. paper_adapter.py

Interface proof only. Proves a `CompiledStrategy` can drive the **existing**
`PaperExecutionEngine` without any change to it:

- `validate_order_shape(order)` — pure signature check (all required
  `submit_order` keys present).
- `submit_candidate(engine, candidate)` — submits every leg as OPEN orders.
- `close_candidate(engine, open_order)` — submits a CLOSE order.

The interface test builds a **throwaway engine rooted in a temp directory**
(temp account JSON + temp ground-truth DB) so the production paper account and
the production Ground Truth DB are never opened by this phase (see §17).

## 9. strategy_lab.py CLI

```
python strategy_lab.py list
python strategy_lab.py validate <id>
python strategy_lab.py inspect <id>
python strategy_lab.py compile <id>
python strategy_lab.py hash <id>
python strategy_lab.py backtest <id> [--data-root DIR]
python strategy_lab.py equivalence <id> [--data-root DIR]
python strategy_lab.py validate-file <path.yaml>
```

`equivalence` combines a backtest run + spec-consistency check + field-by-field
comparison against the committed reference, returning a machine-readable
MATCH/MISMATCH verdict.

---

## 10. Strategy specs

All three files live in `strategies/`, validated and hashed by the registry.
Referenced project rules are allowlisted only (see §13).

### 10.1 current_control_v1 — CONTROL

Formal, versioned representation of the EXISTING frozen 6-layer confluence
funnel (`backtest_frozen.py`) — a specification, not a strategy change.
- Classification: `CONTROL`. Lifecycle: `BACKTESTED`.
- Regimes allowed: TREND_HV, TREND_LV, RANGE_HV (RANGE_LV excluded by the
  frozen L1 gate).
- Entry: 6 layers (l1 regime gate → l6 ML) composed via allowlisted
  `backtest_frozen.*` refs; grade gate min_confluence 4.
- Direction: `backtest_frozen.evaluate_day`, with the **frozen defect
  preserved**: side = CE only if `BUY_CALL`/`BULLISH` in the action, else PE —
  so all realized trades are PUT (all-PUT, documented, not altered).
- Instrument: NAKED_OPTION, 1 lot (75).
- Strike: wall/spot rule; SL = 1.5×ATR from entry; target = 2×risk;
  expiry square-off at canonical expiry.
- Cost model: ₹40 × 2 orders = ₹80/trade; slippage 1.5% adverse/fill.

Spec hash: `5132d3db6b8f6abdd1f18f2c7d246b0afea7390d787dc9a08161405e841319ac`

### 10.2 directional_spread_v1 — WEAK

Phase H candidate B (defined-risk directional vertical spread, 500-pt width)
as a declarative spec.
- Classification: `WEAK`. Lifecycle: `BACKTESTED`.
- Entry funnel restricted to trend regimes (TREND_HV / TREND_LV) with correct
  bias → spread mapping (candidate B's phase-H correction).
- Instrument: DEFINED_RISK_DIRECTIONAL (2 legs: long + short same side).
- Engine: `multi_strategy_backtest.run_candidate_b`; strikes/expiry via
  allowlisted `build_spread` / `simulate_spread`.

Spec hash: `27546b3a56c9b556b1b93c5f7940350706b9c28639ffce1651fee98827635048`

### 10.3 range_hv_iron_condor_v1 — PROMISING_BUT_INSUFFICIENT

Phase H candidate C (RANGE_HV iron condor, `premium_seller` structure).
- Classification: `PROMISING_BUT_INSUFFICIENT`. Lifecycle: `BACKTESTED`.
- Declarative conditions: `REGIME == RANGE_HV`, `VIX >= 16`, `VIX < 25` plus
  the allowlisted `premium_seller.sell_ok` project rule.
- Instrument: DEFINED_RISK_RANGE (iron condor, 4 legs) via allowlisted
  `build_condor` / `simulate_condor`.

Spec hash: `56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb`

---

## 11. Field registry and operator allowlist

Declarative conditions may use **only** registered field names and **only**
the operators below. Any unknown field/operator is rejected at validation.

- Operators: `>` `>=` `<` `<=` `==` `!=`
- Fields: the shared decision-time vocabulary (regime, VIX, daily P&L, …) as
  declared in `strategy_schema.FIELD_REGISTRY` / `FIELD_TYPES`.
- Values are type-coerced against `FIELD_TYPES` before comparison in the
  compiler (`_coerce`).

## 12. No-lookahead protection

Enforced in `strategy_validator.py` and backed by the schema's forbidden list:

```
LOOKAHEAD_FORBIDDEN_SUBSTRINGS = ("future_", "tomorrow", "next_close",
    "future_vix", "future_oi", "future_high", "future_low", "outcome",
    "realized_pnl", "exit_price")
```

Every string value in a spec (fields, notes, descriptions) is scanned; a
forbidden substring anywhere fails validation. This is the declarative
mirror of the engine-level no-lookahead data windowing already proven in
Phase H. Covered by `test_rejects_forbidden_lookahead_note`.

## 13. Project-rule allowlist

Strategy files may reference **only** the following references (explicit
map in `strategy_schema.PROJECT_RULE_ALLOWLIST`; the compiler resolves the
module from the map, never `getattr` on user input):

```
backtest_frozen.regime_gate_at        backtest_frozen.technical_verdict_at
backtest_frozen.options_layer_at      backtest_frozen.institutional_layer_at
backtest_frozen.ml_predict_at         backtest_frozen.evaluate_day
backtest_frozen.simulate_trade
expiry_calendar.get_expiry_for_trade_date
premium_seller.sell_ok
multi_strategy_backtest.build_condor  multi_strategy_backtest.simulate_condor
multi_strategy_backtest.build_spread  multi_strategy_backtest.simulate_spread
multi_strategy_backtest.run_candidate_a/b/c
```

Anything outside this list (e.g. `backtest_frozen.definitely_not_real`) fails
validation — proven by `test_rejects_unknown_project_ref`.

## 14. Spec hashing / versioning

- Version identity: file stem == `strategy.id` (versioned per file, e.g.
  `current_control_v1.yaml`); registry can pin an exact version.
- `spec_hash`: sha256 of the JSON-canonical spec dict. Deterministic and
  key-sensitive — any byte change (including a version bump) changes the hash
  (`test_spec_hash_deterministic_and_key_sensitive`).
- The registry exposes `list / load / validate / compile / spec_hash`; the
  CLI prints hashes for handoff.

---

## 15. Control equivalence

Verified live in this session:

```
$ .venv/bin/python strategy_lab.py equivalence current_control_v1
...
spec-consistency: OK
equivalence vs committed Phase H results: MATCH
  run=79ed7c3b865e ref=c1d3a044e574 (48/48 trades)
```

| Item | Value |
|---|---|
| Trades compared | **48/48 MATCH** (field-by-field: entry/exit dates, regime, grade, option type, strikes, reason, net P&L, fees, slippage, MFE, MAE, days held) |
| Run trade-set hash (adapter) | `79ed7c3b865e…` (first 12 chars printed; full sha256 of canonical JSON rows) |
| Committed reference | `results/phaseH_multi_strategy.json` — `result_hash c1d3a044e5744343bfa5796a8ea2c9f978b890d32f041fe627c37040ab3f6146` |
| Phase H control repro check (in reference) | trades 48, win rate 33.3%, net ₹1,906.43, PF 1.011 — PASS |
| Spec hash (Phase H, authoritative) | `f814e452da62b2087fa050be692ba2e5ae4d33a6cf812bcaec859a10a5524f20` |
| Dataset composite hash (Phase H frozen) | `018c182ef833c620d3b36ac22faadf956caabb42bf5264445e4ab7dac2a9d163` |

Reference fingerprints (recorded in the committed JSON):
- nifty_history.csv `691bf02d…f49d` (37,172 B)
- india_vix.csv `9bd5c22a…0c3e` (20,590 B)
- fii_dii_history.csv `6c9d76f8…8cc7` (8,585 B)
- ml_features.csv `6e1225df…14cbd` (128,924 B)
- expiry_calendar.csv `3abbe4cc…6ad2` (9,141 B)
- oi_snapshots_dir `5e01e40e…4c708` (247 files)
- window 2025-08-13 → 2026-08-13 (245 trading days)

## 16. Range-HV spec consistency

The condor spec was run through its frozen engine and every produced trade was
cross-checked against the compiled spec's invariants:

```
$ .venv/bin/python strategy_lab.py equivalence range_hv_iron_condor_v1
spec-consistency: OK          → 0 violations
```

Note: candidate C has n=6 trades and is **not** used as an equivalence proof
(reference equality is only asserted for the CONTROL strategy, which is the
deterministic byte-identical baseline). The consistency check is the condor's
verification surface, and it passes with **0 violations**.

---

## 17. Paper adapter (interface proof)

`test_paper_adapter_interface` builds a throwaway engine:

```python
engine = paper_execution.PaperExecutionEngine(
    account_file=os.path.join(tmp, "account.json"),   # temp dir
    gt_db_file=os.path.join(tmp, "gt.db"))            # temp dir
```

Verified: OPEN order submitted (status SUBMITTED, quantity 75) and a CLOSE
order submitted — all against the temp engine.

- Production paper account: **untouched** — `data/paper_account.json` was never
  passed to any H1 v2 engine. The temp engine used only temp paths.
- Production Ground Truth DB: **untouched** — `data/ground_truth.db` was never
  passed to any H1 v2 engine (temp `gt.db` only).
- Backtest adapter restores the global `bf.ROOT` / `exp_cal.CALENDAR_CSV`
  after each run so no module-level state leaks out of the adapter.

## 18. Tests

Exact commands and results (this session, repo venv):

```
$ .venv/bin/python test_strategy_lab.py
Ran 12 tests in 361.568s    → OK   (12/12 pass)

$ .venv/bin/python test_all.py
Ran 34 tests in 20.842s     → OK   (34/34 pass, pre-existing regression suite)
```

New tests (`test_strategy_lab.py`, 12):
1. spec hash deterministic + key-sensitive
2. all strategies valid + unique ids
3. validator rejects forbidden lookahead
4. validator rejects unknown project ref
5. registry compiles every strategy
6. compiled evaluate (declarative + project-rule + missing-field safe)
7. generate_candidate + build_order (naked)
8. condor builds four legs
9. control equivalence MATCH
10. condor backtest spec consistency (0 violations)
11. backtest determinism
12. paper adapter interface (temp engine)

## 19. Production isolation

- No new code writes to `data/`, `results/`, `blog/`, the paper account, or
  the Ground Truth DB. Adapters read frozen caches only.
- `backtest_adapter.run()` runs the existing frozen engines unchanged over the
  frozen dataset window and restores global data-root state afterward.
- The paper interface proof is isolated to `tempfile.TemporaryDirectory`.
- No strategy logic in the existing engines was modified in this phase
  (engines referenced, never re-implemented).

## 20. Known limitations

1. `evaluate()` resolves project-rule conditions only when the context supplies
   the function's actual parameter names (e.g. `regime`, `vix_level`); with a
   field-name-only context those conditions report `None` and the verdict is
   not evaluable. This is by design (the compiler does not duplicate the
   funnel); declared, not hidden.
2. `directional_spread_v1` is validated and compiled but has **no dedicated
   backtest/consistency test** in `test_strategy_lab.py` (the engine mapping
   exists in the adapter; the spread engine was not re-run in this suite).
3. Control equivalence is asserted only for `current_control_v1` (the
   deterministic byte-identical baseline). Candidates B and C are verified by
   spec consistency, not reference equality.
4. `check_spec_consistency` cannot verify the row-level expiry *date* (rows
   do not carry an expiry field); it verifies the engine only produced
   entries with a canonical expiry, and relies on the engine's own canonical
   expiry rule.
5. The paper adapter proves the submit/close interface shape only — fills,
   GT reconciliation, and exit evaluator interactions are outside this phase's
   scope.
6. No pre-session fingerprint of `data/paper_account.json` /
   `data/ground_truth.db` was captured, so this audit cannot itself prove the
   absence of mutation before the session; it proves isolation of the H1 v2
   code paths (temp engine + read-only adapters).

## 21. Explicit statement

This phase performed **NO**:

- NO optimization of any strategy parameter or rule.
- NO strategy mutation — the frozen Phase H logic and its frozen defect
  (all-PUT control side) are referenced and preserved verbatim.
- NO live trading, NO paper trading, NO order submission outside a throwaway
  temp engine.
- NO AI strategy generation yet — the spec substrate is in place; the
  generation loop is explicitly out of scope for H1 v2.

---

## Appendix A — Git state

- Working tree base commit: `cf132caeb7e8e17a2f316cd45a48f0c88e7cc703`
  (`cf132ca "Remediate audit findings and untrack sensitive runtime state"`)
- The H1 v2 files below are currently **untracked** (not yet committed per
  instruction — commit deferred).

## Appendix B — File hashes (sha256, this session)

| File | sha256 |
|---|---|
| strategy_schema.py | `8932dd37200d41b9d74e37553cc44c57f3f5ba1d0dd437506d39a33c9eacf5c6` |
| strategy_validator.py | `8cb5e4c21aa4d8557334d7c6132784f9555c5acee4297e070db3061d076f6aad` |
| strategy_compiler.py | `ebb10e7614408ce3a047d0db3321579bbda76e43af25d7721df4e5feff48ba22` |
| strategy_registry.py | `f802de5c71b6f29ae6e9b4bc56974531e3826a4098f413ef45cd54bc5396dac5` |
| backtest_adapter.py | `db9b000580a39d3712cb6ac47e2b0c2224ee91166cb9b1f291c0a4bddd582e3e` |
| paper_adapter.py | `021fa651b74510079fac9d91794c8c29db34d5b447cf4f97e8f4306efcd76e16` |
| strategy_lab.py | `662825682e4e1ce73838b9b736c00cd0a04381807d079d70c78fc913b24f10f9` |
| test_strategy_lab.py | `8f9cbb65713e1d81a3929e03288e8026f571763bae7c799782fa2094143fd3f2` |
| strategies/current_control_v1.yaml | `b116bdd63861c3cca46d79e2ba891f7a2c676e03b44e05be3b020eb4f56ad73a` |
| strategies/directional_spread_v1.yaml | `5fa762969b8a16df831e48e52cc532e7fd77b56681c835f59a46f1fb7882174a` |
| strategies/range_hv_iron_condor_v1.yaml | `aca97715de98d1dcda1d6f2a6dd5cc130c34bbeba854c983344b67cdd6cc7103` |

## Appendix C — Spec hashes (registry-computed)

| Strategy | spec_hash |
|---|---|
| current_control_v1 | `5132d3db6b8f6abdd1f18f2c7d246b0afea7390d787dc9a08161405e841319ac` |
| directional_spread_v1 | `27546b3a56c9b556b1b93c5f7940350706b9c28639ffce1651fee98827635048` |
| range_hv_iron_condor_v1 | `56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb` |

## Appendix D — Production DB/account fingerprints (as of audit time)

Recorded as-is; **no pre-session baseline exists** in this audit, so these are
environmental reference points, not proof of non-mutation (see limitation 6).

| Path | sha256 | mtime |
|---|---|---|
| data/paper_account.json | `76503cf6247a8f6dbf1eeef08af756abd3e80492e459e82c30eb21b9ed6561fc` | 2026-08-12 15:55 |
| data/ground_truth.db | `645f9dc4a7ac83d7fa16c476786d6d9a07a039da0ad6b6f9d0c12ba8e16119b2` | 2026-08-14 12:55 |

Neither file is passed to any H1 v2 module; the paper interface test uses temp
paths exclusively.
