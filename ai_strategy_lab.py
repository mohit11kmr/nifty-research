"""Phase I - AI Strategy Lab CLI.

Usage:
    python ai_strategy_lab.py list
    python ai_strategy_lab.py inspect <proposal.yaml>
    python ai_strategy_lab.py validate <proposal.yaml>
    python ai_strategy_lab.py compile <proposal.yaml>
    python ai_strategy_lab.py research <proposal.yaml> [--data-root DIR] [--out DIR]
    python ai_strategy_lab.py compare <proposal.yaml> [--data-root DIR]
    python ai_strategy_lab.py review <proposal_id> <DECISION>

Safety: this CLI NEVER writes ground_truth.db, paper_account.json, production
signals, or broker state. It writes only to strategy_proposals/ (registry) and
--out (research results). No autonomous generation loops exist.
"""
import argparse
import json
import os
import sys

import strategy_proposal_validator as PV
import strategy_proposal_compiler as PC
import strategy_proposal_registry as SPR
import ai_strategy_research as R
import strategy_proposal_schema as PS

REPO = os.path.dirname(os.path.abspath(__file__))


def _registry():
    return SPR.default_registry()


def cmd_list(args):
    rows = _registry().list_proposals()
    if not rows:
        print("(no proposals registered)")
        return 0
    for r in rows:
        print(f"{r['proposal_id']:<26} {str(r.get('title',''))[:40]:<40} "
              f"{str(r.get('strategy_id','')):<26} {r.get('status','')}")
    return 0


def cmd_inspect(args):
    comp = PC.compile_file(args.proposal)
    print(json.dumps({
        "proposal": comp.to_record(),
        "strategy_id": comp.strategy_id,
        "proposal_hash": comp.proposal_hash,
        "spec_hash": comp.spec_hash,
        "fingerprint": comp.fingerprint,
    }, indent=2, default=str))
    return 0


def cmd_validate(args):
    vr = PV.validate_file(args.proposal)
    print(vr.report())
    return 0 if vr.valid else 1


def cmd_compile(args):
    comp = PC.compile_file(args.proposal)
    print(f"compiled proposal {comp.strategy_id} hash={comp.spec_hash}")
    return 0


def cmd_research(args):
    comp = PC.compile_file(args.proposal)
    # duplicate gate: exact normalized duplicates are rejected
    dup = _registry().duplicate(comp)
    if dup and dup["proposal_id"] != (comp.proposal.get("proposal") or {}).get("proposal_id"):
        print(f"DUPLICATE_PROPOSAL: normalized rules match existing proposal "
              f"{dup['proposal_id']}; cosmetic changes are not new research.")
        _registry().register(comp, status="REJECTED")
        return 1
    _registry().register(comp, status="VALIDATED")
    out = R.run_research(comp, registry=_registry(), data_root=args.data_root,
                         control=True)
    R.persist_research(out, registry=_registry(), out_dir=args.out,
                       status="REVIEW")
    print(f"proposal: {out['proposal']['proposal_id']}")
    print(f"strategy: {out['strategy_id']}  spec_hash={out['spec_hash'][:16]}...")
    print(f"result_hash: {out['result_hash'][:16]}...")
    print(f"trades: {out['metrics'].get('trade_count')}  "
          f"net: {out['metrics'].get('net_pnl')}  "
          f"PF: {out['metrics'].get('profit_factor')}")
    print(f"status: REVIEW (human review required)")
    return 0


def cmd_compare(args):
    comp = PC.compile_file(args.proposal)
    out = R.run_research(comp, registry=_registry(), data_root=args.data_root,
                         control=True)
    base = out.get("baseline") or {}
    print(json.dumps({"proposal": out["proposal"]["proposal_id"],
                      "metrics": out["metrics"],
                      "evaluation_vector": out["evaluation_vector"],
                      "baseline": base}, indent=2, default=str))
    return 0


def cmd_review(args):
    if args.decision not in PS.HUMAN_DECISIONS:
        print(f"decision must be one of {PS.HUMAN_DECISIONS}")
        return 2
    rec = _registry().update(args.proposal_id, status="REVIEW",
                             human_decision=args.decision)
    print(f"proposal {args.proposal_id}: human decision recorded = {args.decision}")
    print(json.dumps(rec, indent=2, default=str))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="AI Strategy Lab CLI (research layer)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    for name in ("inspect", "validate", "compile", "research", "compare"):
        sp = sub.add_parser(name)
        sp.add_argument("proposal")
        sp.add_argument("--data-root", default=None)
        sp.add_argument("--out", default=os.path.join("/tmp", "opencode", "phaseI"))
        sp.set_defaults(fn=cmd_list if name == "list" else
                        {"inspect": cmd_inspect, "validate": cmd_validate,
                         "compile": cmd_compile, "research": cmd_research,
                         "compare": cmd_compare}[name])
    rp = sub.add_parser("review")
    rp.add_argument("proposal_id")
    rp.add_argument("decision")
    rp.set_defaults(fn=cmd_review)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
