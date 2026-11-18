"""AI-fit assessment: for each activity, how much of it an AI agent could take on, and under which guardrails.

Autonomy levels
  L0  not applicable (physical, external party, or system step)
  L1  assist      - the agent suggests; a person does the work
  L2  draft       - the agent prepares the output; a person approves each one
  L3  act+report  - the agent acts; people review a sample and exceptions

Hard rules (never overridden by scores):
  * risk "high" or financial_authority -> at most L2 (a person approves every item)
  * judgement_decision -> at most L1 (the agent may prepare evidence, never the decision)
  * data_available false -> at most L1
"""
from __future__ import annotations

BASE = {"data_entry": 0.9, "document_review": 0.8, "rules_check": 0.8, "communication": 0.75,
        "judgement_decision": 0.4, "physical": 0.0, "external": 0.0, "system": 0.0}

GUARDRAILS = {
    "L1": ["Suggestions are shown with their source data; the person decides."],
    "L2": ["A named person approves every output before it leaves the team.",
           "The agent cites the record fields it used; missing fields are listed, not guessed."],
    "L3": ["A weekly sample of agent actions is reviewed against the acceptance criteria.",
           "Exceptions (low confidence, missing data, policy edge cases) are routed to a person.",
           "Kill switch: the step falls back to the manual procedure if error rate exceeds the agreed threshold."],
}

LEVEL_ORDER = ["L0", "L1", "L2", "L3"]


def _cap(level: str, cap: str) -> str:
    return level if LEVEL_ORDER.index(level) <= LEVEL_ORDER.index(cap) else cap


def assess(activity: str, spec: dict | None) -> dict:
    if spec is None:
        return {"activity": activity, "fit": 0.0, "level": "L0", "reasons": ["not in the activity catalog: not assessed"],
                "guardrails": []}
    t = spec.get("task_type", "")
    fit = BASE.get(t, 0.0)
    reasons = [f"task type: {t}"]
    if fit == 0.0:
        return {"activity": activity, "fit": 0.0, "level": "L0", "reasons": reasons + ["no AI role for this kind of step"],
                "guardrails": []}
    if not spec.get("data_available", False):
        fit *= 0.5
        reasons.append("data needed by the step is not available to an agent")
    level = "L3" if fit >= 0.8 else "L2" if fit >= 0.6 else "L1"
    risk = spec.get("risk", "high")
    if risk == "medium":
        fit -= 0.1
        level = _cap(level, "L2")
        reasons.append("medium risk: a person approves each output")
    if risk == "high" or spec.get("financial_authority"):
        fit -= 0.2
        level = _cap(level, "L2")
        reasons.append("high risk or financial authority: never autonomous")
    if t == "judgement_decision":
        level = _cap(level, "L1")
        reasons.append("decision stays with a person; the agent prepares the evidence only")
    if not spec.get("data_available", False):
        level = _cap(level, "L1")
    return {"activity": activity, "fit": round(max(fit, 0.0), 2), "level": level, "reasons": reasons,
            "guardrails": GUARDRAILS.get(level, [])}


def assess_all(activities: list[str], catalog: dict) -> list[dict]:
    acts = catalog.get("activities", {})
    out = []
    for a in activities:
        r = assess(a, acts.get(a))
        r["handling_minutes"] = (acts.get(a) or {}).get("handling_minutes")
        out.append(r)
    return out
