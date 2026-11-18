"""Write the analysis as facts.json (input for the memo agent) and report.md (for people)."""
from __future__ import annotations

import json
import re


def _node(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def mermaid(facts: dict, max_edges: int = 14) -> str:
    lines = ["flowchart LR"]
    for e in facts["dfg"][:max_edges]:
        lines.append(f'  {_node(e["from"])}["{e["from"]}"] -->|{e["count"]} / {e["median_gap_h"]}h| '
                     f'{_node(e["to"])}["{e["to"]}"]')
    return "\n".join(lines)


def eur(x: float) -> str:
    return f"EUR {x:,.0f}"


def to_markdown(bundle: dict) -> str:
    f, fits, r, meta = bundle["facts"], bundle["ai_fit"], bundle["redesign"], bundle["meta"]
    fit_by = {x["activity"]: x for x in fits}
    out = [f"# Process mining and AI redesign: {meta['process']}", "",
           f"Source: `{meta['source']}` · {f['cases']} cases · {f['events']} events · "
           f"{f['period']['start'][:10]} to {f['period']['end'][:10]}", "",
           "> Measured figures come from the event log. Figures marked *estimate* come from the assumptions "
           "listed at the end and must be challenged by the process owner before anyone relies on them.", "",
           "## 1. What the log shows (measured)", "",
           f"- Cycle time: median **{f['cycle_time_h']['median']} h**, 90th percentile {f['cycle_time_h']['p90']} h.",
           f"- Variants: {f['variants']['distinct']} distinct paths; the most common covers "
           f"{f['variants']['top'][0]['share']:.0%} of cases.",
           f"- Rework: **{f['rework']['rate']:.0%}** of cases repeat a step "
           f"({', '.join(f['rework']['repeated_activities']) or 'none'}).",
           f"- Handoffs between roles: median {f['handoffs_per_case']['median']} per case.", "",
           "### Where the time goes", "",
           "| Rank | Activity | Cases | Median wait before (h) | Share of all waiting | AI level |",
           "|---|---|---|---|---|---|"]
    for a in f["activities"]:
        out.append(f"| {a['bottleneck_rank']} | {a['activity']} | {a['cases']} | {a['median_wait_h']} | "
                   f"{a['wait_share']:.0%} | {fit_by.get(a['activity'], {}).get('level', 'n/a')} |")
    out += ["", "### Process map (most frequent transitions: count / median gap)", "", "```mermaid", mermaid(f), "```", "",
            "## 2. Where an agent can help (AI-fit)", "",
            "| Activity | Level | Why | Guardrails |", "|---|---|---|---|"]
    for x in fits:
        out.append(f"| {x['activity']} | {x['level']} | {'; '.join(x['reasons'])} | {' '.join(x['guardrails']) or '-'} |")
    out += ["", "Levels: L0 not applicable · L1 assist · L2 draft, person approves each output · "
            "L3 act and report, people review samples and exceptions. High-risk and financial-authority steps "
            "never go above L2; decisions never above L1.", "",
            "## 3. Redesign proposals (estimates)", "",
            "| ID | Change | Target | Level | Value per year (estimate) | Recommendation |", "|---|---|---|---|---|---|"]
    for p in r["proposals"]:
        out.append(f"| {p['id']} | {p['change']} | {p['target']} | {p['level']} | "
                   f"{eur(p['estimate']['value_eur_per_year'])} | {p['recommendation']} |")
    c = r["cycle_time_estimate_h"]
    out += ["", f"Cycle time if all proposals work as assumed: median {c['median_before']} h -> "
            f"**{c['median_after']} h** (*estimate*: {c['note']}).",
            f"Total value if all proposals work as assumed: **{eur(r['total_value_eur_per_year'])} per year** (*estimate*).", "",
            "## 4. Assumptions behind every estimate", "", "| Assumption | Value |", "|---|---|"]
    for k, v in r["assumptions"].items():
        out.append(f"| {k} | {json.dumps(v)} |")
    out += ["", "## 5. Approval required", "",
            f"Status: **{r['approval']['status']}**. {r['approval']['rule']}", "",
            "| Proposal | Decision (approve / change / stop) | Process owner | Date |", "|---|---|---|---|"]
    for p in r["proposals"]:
        out.append(f"| {p['id']} | | | |")
    return "\n".join(out) + "\n"


def write(bundle: dict, outdir: str) -> tuple[str, str]:
    import os
    os.makedirs(outdir, exist_ok=True)
    fj = os.path.join(outdir, "facts.json")
    md = os.path.join(outdir, "report.md")
    with open(fj, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=1, ensure_ascii=False)
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(bundle))
    return fj, md
