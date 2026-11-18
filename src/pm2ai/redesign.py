"""Turn mined facts + AI-fit into a small set of redesign proposals with an explicit value case.

Measured facts (from the log) and estimates (from config/assumptions.json) are kept apart:
every estimate carries the list of assumption keys it depends on, and the report prints them.
Nothing here is a recommendation to act: proposals go to a named process owner for approval.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from .eventlog import Event

LEVELS = ["L0", "L1", "L2", "L3"]


def _h(td) -> float:
    return td.total_seconds() / 3600.0


def _days(facts: dict) -> float:
    s = datetime.fromisoformat(facts["period"]["start"])
    e = datetime.fromisoformat(facts["period"]["end"])
    return max(_h(e - s) / 24.0, 1.0)


def _loop_hours(evs: list[Event]) -> float:
    """Hours spent between the first and the last occurrence of any repeated activity (the rework loop)."""
    first: dict[str, int] = {}
    span = 0.0
    for i, e in enumerate(evs):
        if e.activity in first:
            span = max(span, _h(e.timestamp - evs[first[e.activity]].timestamp))
        else:
            first[e.activity] = i
    return span


def _loop_events(evs: list[Event]) -> list[Event]:
    """Events that only happen because of the loop: after the first occurrence of a repeated activity,
    up to and including its last occurrence."""
    first: dict[str, int] = {}
    lo = hi = None
    for i, e in enumerate(evs):
        if e.activity in first:
            lo = first[e.activity] + 1 if lo is None else min(lo, first[e.activity] + 1)
            hi = i
        else:
            first[e.activity] = i
    return evs[lo:hi + 1] if lo is not None else []


def propose(facts: dict, fits: list[dict], catalog: dict, assumptions: dict,
            cases: dict[str, list[Event]]) -> dict:
    fit_by = {f["activity"]: f for f in fits}
    cat = catalog.get("activities", {})
    wr = assumptions["wait_reduction_by_level"]
    er = assumptions["effort_reduction_by_level"]
    cost = assumptions["cost_per_staff_hour_eur"]
    year = 365.0 / _days(facts)
    threshold = assumptions["scale_threshold_eur_per_year"]
    proposals = []

    # 1. Rework: the loop is the first target if it is material (>= 10% of cases).
    rw = facts["rework"]
    # intake = the earliest human data-entry step (by position in the most common path) that an agent can take on
    order = {a: i for i, a in enumerate(facts["variants"]["top"][0]["path"])} if facts["variants"]["top"] else {}
    candidates = [a["activity"] for a in facts["activities"]
                  if fit_by.get(a["activity"], {}).get("level") in ("L2", "L3")
                  and cat.get(a["activity"], {}).get("task_type") == "data_entry"]
    intake = min(candidates, key=lambda a: order.get(a, 10 ** 6)) if candidates else None
    avoid_share = assumptions["rework_avoided_by_intake_check"]
    if rw["rate"] >= 0.10 and intake:
        loops = [_loop_events(evs) for evs in cases.values()]
        loops = [lp for lp in loops if lp]
        loop_effort_min = (sum(cat.get(e.activity, {}).get("handling_minutes", 0) for lp in loops for e in lp)
                           / len(loops)) if loops else 0.0
        avoided_cases = round(rw["cases_with_rework"] * avoid_share)
        value = avoided_cases * loop_effort_min / 60.0 * cost * year
        proposals.append({
            "id": "P1", "kind": "remove rework", "target": intake,
            "change": f"An agent checks each claim for completeness at '{intake}' and drafts the request for missing "
                      f"information at once, before the eligibility check, so the loop through "
                      f"{', '.join(rw['repeated_activities'])} is avoided.",
            "level": fit_by[intake]["level"],
            "measured": {"cases_with_rework": rw["cases_with_rework"], "rework_rate": rw["rate"],
                         "avg_loop_effort_min": round(loop_effort_min, 1)},
            "estimate": {"cases_avoided": avoided_cases, "value_eur_per_year": round(value),
                         "median_loop_hours_removed_per_avoided_case": round(median(
                             [_loop_hours(evs) for evs in cases.values() if _loop_hours(evs) > 0]), 1)},
            "assumptions_used": ["rework_avoided_by_intake_check", "handling_minutes (catalog)",
                                 "cost_per_staff_hour_eur", "annualisation_factor"],
        })

    # 2. Waiting-time and effort proposals for the largest bottlenecks that an agent can help with.
    for a in facts["activities"]:
        if len(proposals) >= assumptions["max_proposals"]:
            break
        f = fit_by.get(a["activity"])
        if not f or f["level"] == "L0" or any(p["target"] == a["activity"] for p in proposals):
            continue
        lvl = f["level"]
        effort_h = a["events"] * cat.get(a["activity"], {}).get("handling_minutes", 0) / 60.0
        value = effort_h * er[lvl] * cost * year
        proposals.append({
            "id": f"P{len(proposals) + 1}", "kind": "agent support", "target": a["activity"],
            "change": {"L1": "An agent prepares the evidence and a suggested answer; the person decides.",
                       "L2": "An agent drafts the output from the case record; a person approves each one.",
                       "L3": "An agent completes the step and reports; people review a weekly sample and all exceptions."}[lvl],
            "level": lvl,
            "measured": {"total_wait_h": a["total_wait_h"], "median_wait_h": a["median_wait_h"],
                         "wait_share": a["wait_share"], "events": a["events"]},
            "estimate": {"wait_reduction": wr[lvl], "effort_hours_saved_per_year": round(effort_h * er[lvl] * year),
                         "value_eur_per_year": round(value)},
            "assumptions_used": ["wait_reduction_by_level", "effort_reduction_by_level", "handling_minutes (catalog)",
                                 "cost_per_staff_hour_eur", "annualisation_factor"],
        })

    # Recommendation: pilot when the effort value clears the threshold, or when the step drives cycle time
    # (rework rate >= 20%, or >= 20% of all waiting) and the agent level is L2 or above.
    for p in proposals:
        v = p["estimate"]["value_eur_per_year"]
        cycle_driver = (p["kind"] == "remove rework" and p["measured"]["rework_rate"] >= 0.20) or \
                       p["measured"].get("wait_share", 0) >= 0.20
        if p["level"] == "L1":
            p["recommendation"] = "assist only"
        elif v >= threshold:
            p["recommendation"] = "pilot"
        elif cycle_driver:
            p["recommendation"] = "pilot (cycle-time driver)"
        else:
            p["recommendation"] = "iterate (value below threshold)"

    # 3. Before/after cycle time, recomputed case by case (an estimate, not a measurement).
    targets = {p["target"]: wr[p["level"]] for p in proposals if p["kind"] == "agent support"}
    rework_p = next((p for p in proposals if p["kind"] == "remove rework"), None)
    loop_ids = sorted(cid for cid, evs in cases.items() if _loop_hours(evs) > 0)
    avoid = set(loop_ids[: rework_p["estimate"]["cases_avoided"]]) if rework_p else set()
    before, after = [], []
    for cid, evs in cases.items():
        total = _h(evs[-1].timestamp - evs[0].timestamp)
        saved = sum(_h(b.timestamp - a.timestamp) * targets.get(b.activity, 0.0) for a, b in zip(evs, evs[1:]))
        if cid in avoid:
            saved += _loop_hours(evs)
        before.append(total)
        after.append(max(total - saved, 0.0))

    return {
        "proposals": proposals,
        "cycle_time_estimate_h": {"median_before": round(median(before), 1), "median_after": round(median(after), 1),
                                  "note": "recomputed per case from the assumptions below; not a measurement"},
        "total_value_eur_per_year": sum(p["estimate"]["value_eur_per_year"] for p in proposals),
        "assumptions": {k: v for k, v in assumptions.items() if not k.startswith("_")},
        "approval": {"status": "awaiting process-owner review",
                     "rule": "No proposal is implemented until a named process owner approves it."},
    }
