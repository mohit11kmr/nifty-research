"""Phase H1 v2 - Strategy Lab CLI.

Usage:
    python strategy_lab.py list
    python strategy_lab.py validate <id>
    python strategy_lab.py inspect <id>
    python strategy_lab.py compile <id>
    python strategy_lab.py backtest <id> [--data-root DIR]
    python strategy_lab.py equivalence <id> [--data-root DIR]
    python strategy_lab.py validate-file <path.yaml>
    python strategy_lab.py hash <id>
"""
import argparse
import json
import sys

import strategy_registry
import strategy_validator
from backtest_adapter import BacktestAdapter


def _registry():
    return strategy_registry.default_registry()


def cmd_list(args):
    reg = _registry()
    rows = reg.list_strategies()
    if not rows:
        print("(no strategies found)")
        return 0
    for r in rows:
        err = f"  [ERROR {r.get('error')}]" if r.get("error") else ""
        print(f"{r['id']:<28} v{r['version']:<3} {r.get('classification','') or '':<24} "
              f"{r.get('lifecycle','') or '':<10} {r['path']}{err}")
    return 0


def cmd_validate(args):
    reg = _registry()
    if args.id.endswith(".yaml") and "/" in args.id or args.id.endswith(".yaml"):
        vr = strategy_validator.validate_file(args.id)
        label = args.id
    else:
        vr = reg.validate(args.id)
        label = args.id
    print(vr.report())
    return 0 if vr.valid else 1


def cmd_inspect(args):
    reg = _registry()
    spec = reg.load(args.id)
    compiled = reg.compile(args.id)
    print(json.dumps({
        "strategy": compiled.spec["strategy"],
        "classification": compiled.classification,
        "data_requirements": compiled.data_requirements,
        "spec_hash": compiled.spec_hash,
    }, indent=2, default=str))
    return 0


def cmd_compile(args):
    reg = _registry()
    c = reg.compile(args.id)
    print(f"compiled {c.strategy_id} v{c.version} hash={c.spec_hash}")
    return 0


def cmd_hash(args):
    reg = _registry()
    print(reg.spec_hash(args.id))
    return 0


def cmd_backtest(args, equivalence_only=False):
    reg = _registry()
    compiled = reg.compile(args.id)
    adapter = BacktestAdapter(compiled, data_root=args.data_root)
    run = adapter.run()
    print(f"strategy: {compiled.strategy_id} v{compiled.version}")
    print(f"engine:   {adapter.candidate_key}")
    print(f"spec_hash: {run['spec_hash']}")
    print("metrics:", json.dumps(run["metrics"], indent=2, default=str))
    by_regime = run["by_regime"]
    print("by_regime:")
    for key in sorted(by_regime, key=str):
        v = by_regime[key]
        print(f"  {key}: {v['trades']} trades, win {v['winrate']}% -> "
              f"{v['net']:+,.0f} pts")
    monthly = run["monthly"]
    if monthly:
        print("monthly (net):")
        for month in sorted(monthly):
            v = monthly[month]
            print(f"  {month}: {v['trades']} trades, win {v['winrate']}% "
                  f"{v['net']:+,.0f} pts")
    violations = adapter.check_spec_consistency(run)
    print(f"spec-consistency: {'OK' if not violations else 'VIOLATIONS'}")
    for v in violations[:10]:
        print(f"  ! {v}")
    if equivalence_only:
        eq = adapter.equivalence(run)
        print(f"equivalence vs committed Phase H results: "
              f"{'MATCH' if eq['matched'] else 'MISMATCH'}")
        print(f"  run={eq['run_hash'][:12]} ref={eq['reference_hash'][:12]} "
              f"({eq['run_trades']}/{eq['reference_trades']} trades)")
        for d in eq["differences"][:20]:
            print(f"  ~ {d}")
    return 0 if (not violations and (not equivalence_only or eq["matched"])) else 1


def cmd_equivalence(args):
    return cmd_backtest(args, equivalence_only=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Strategy Lab CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    vp = sub.add_parser("validate"); vp.add_argument("id"); vp.set_defaults(fn=cmd_validate)
    ip = sub.add_parser("inspect"); ip.add_argument("id"); ip.set_defaults(fn=cmd_inspect)
    cp = sub.add_parser("compile"); cp.add_argument("id"); cp.set_defaults(fn=cmd_compile)
    hp = sub.add_parser("hash"); hp.add_argument("id"); hp.set_defaults(fn=cmd_hash)
    for name, fn in (("backtest", cmd_backtest), ("equivalence", cmd_equivalence)):
        bp = sub.add_parser(name); bp.add_argument("id"); bp.add_argument("--data-root")
        bp.set_defaults(fn=fn)
    vf = sub.add_parser("validate-file"); vf.add_argument("id"); vf.set_defaults(fn=cmd_validate)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
