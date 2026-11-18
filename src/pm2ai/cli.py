"""Command line: python -m pm2ai {generate,analyze} ..."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .ai_fit import assess_all
from .eventlog import generate, load_csv, write_csv
from .mining import mine
from .redesign import propose
from .report import write


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pm2ai", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write the synthetic Northwind Appliances warranty-claim log")
    g.add_argument("--cases", type=int, default=600)
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--out", default="data/sample_event_log.csv")
    a = sub.add_parser("analyze", help="mine a log and write facts.json + report.md")
    a.add_argument("log")
    a.add_argument("--catalog", default="config/activity_catalog.json")
    a.add_argument("--assumptions", default="config/assumptions.json")
    a.add_argument("--process", default="Warranty-claim handling (Northwind Appliances, synthetic)")
    a.add_argument("--out", default="reports/latest")
    args = ap.parse_args(argv)

    if args.cmd == "generate":
        rows = generate(args.cases, args.seed)
        write_csv(rows, args.out)
        print(f"wrote {len(rows)} events to {args.out}")
        return 0

    try:
        cases = load_csv(args.log)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    with open(args.catalog, encoding="utf-8") as f:
        catalog = json.load(f)
    with open(args.assumptions, encoding="utf-8") as f:
        assumptions = json.load(f)
    facts = mine(cases)
    fits = assess_all([x["activity"] for x in facts["activities"]], catalog)
    unknown = [x["activity"] for x in fits if "not in the activity catalog" in " ".join(x["reasons"])]
    redesign = propose(facts, fits, catalog, assumptions, cases)
    bundle = {"meta": {"tool": "pm2ai", "version": __version__, "process": args.process, "source": args.log,
                       "unassessed_activities": unknown},
              "facts": facts, "ai_fit": fits, "redesign": redesign}
    fj, md = write(bundle, args.out)
    print(f"wrote {fj} and {md}")
    if unknown:
        print(f"note: {len(unknown)} activities not in the catalog were not assessed: {', '.join(unknown)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
