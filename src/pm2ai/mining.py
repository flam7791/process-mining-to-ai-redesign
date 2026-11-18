"""Process mining on an event log: variants, directly-follows graph, cycle time, rework, handoffs, bottlenecks.

All figures are measured from the log. Waiting time before an activity = time between the previous
event of the same case and this event (timestamps are completion times).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median, quantiles

from .eventlog import Event


def _h(td) -> float:
    return td.total_seconds() / 3600.0


def _p90(xs: list[float]) -> float:
    if len(xs) < 2:
        return xs[0] if xs else 0.0
    return quantiles(xs, n=10, method="inclusive")[-1]


def mine(cases: dict[str, list[Event]], top_variants: int = 5) -> dict:
    n = len(cases)
    cycle = []
    variants: Counter = Counter()
    dfg_count: Counter = Counter()
    dfg_gaps: dict = defaultdict(list)
    act_freq: Counter = Counter()
    act_cases: Counter = Counter()
    wait_before: dict = defaultdict(list)
    rework_cases: Counter = Counter()      # activity -> cases where it occurs more than once
    handoffs = []

    for evs in cases.values():
        acts = [e.activity for e in evs]
        variants[tuple(acts)] += 1
        cycle.append(_h(evs[-1].timestamp - evs[0].timestamp))
        c = Counter(acts)
        for a, k in c.items():
            act_freq[a] += k
            act_cases[a] += 1
            if k > 1:
                rework_cases[a] += 1
        handoffs.append(sum(1 for a, b in zip(evs, evs[1:]) if a.role != b.role))
        for a, b in zip(evs, evs[1:]):
            gap = _h(b.timestamp - a.timestamp)
            dfg_count[(a.activity, b.activity)] += 1
            dfg_gaps[(a.activity, b.activity)].append(gap)
            wait_before[b.activity].append(gap)

    total_wait = sum(sum(v) for v in wait_before.values()) or 1.0
    activities = []
    for a in act_freq:
        w = wait_before.get(a, [])
        activities.append({
            "activity": a,
            "events": act_freq[a],
            "cases": act_cases[a],
            "case_share": round(act_cases[a] / n, 3),
            "median_wait_h": round(median(w), 1) if w else 0.0,
            "p90_wait_h": round(_p90(w), 1) if w else 0.0,
            "total_wait_h": round(sum(w), 1),
            "wait_share": round(sum(w) / total_wait, 3),
            "rework_cases": rework_cases.get(a, 0),
        })
    activities.sort(key=lambda r: r["total_wait_h"], reverse=True)
    for rank, r in enumerate(activities, 1):
        r["bottleneck_rank"] = rank

    loop_acts = [a for a in rework_cases]
    cases_with_rework = sum(1 for evs in cases.values() if len({e.activity for e in evs}) < len(evs))

    return {
        "cases": n,
        "events": sum(act_freq.values()),
        "period": {"start": min(e[0].timestamp for e in cases.values()).isoformat(),
                   "end": max(e[-1].timestamp for e in cases.values()).isoformat()},
        "cycle_time_h": {"median": round(median(cycle), 1), "p90": round(_p90(cycle), 1),
                         "mean": round(sum(cycle) / n, 1)},
        "variants": {"distinct": len(variants),
                     "top": [{"path": list(v), "cases": k, "share": round(k / n, 3)}
                             for v, k in variants.most_common(top_variants)]},
        "rework": {"cases_with_rework": cases_with_rework, "rate": round(cases_with_rework / n, 3),
                   "repeated_activities": sorted(loop_acts)},
        "handoffs_per_case": {"median": median(handoffs), "max": max(handoffs)},
        "activities": activities,
        "dfg": [{"from": a, "to": b, "count": k, "median_gap_h": round(median(dfg_gaps[(a, b)]), 1)}
                for (a, b), k in dfg_count.most_common()],
    }
