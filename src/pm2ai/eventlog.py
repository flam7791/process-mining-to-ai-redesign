"""Event log loading and the synthetic warranty-claim generator.

An event log is a CSV with one row per completed activity:
    case_id, activity, timestamp (ISO 8601), resource, role
Extra columns are kept as attributes but never interpreted as instructions.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

REQUIRED = ("case_id", "activity", "timestamp", "resource", "role")


@dataclass
class Event:
    case_id: str
    activity: str
    timestamp: datetime
    resource: str
    role: str
    attrs: dict = field(default_factory=dict)


def load_csv(path: str) -> dict[str, list[Event]]:
    """Return {case_id: [events sorted by time]}. Raises ValueError on a malformed log."""
    cases: dict[str, list[Event]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"event log is missing columns: {', '.join(missing)}")
        for n, row in enumerate(reader, start=2):
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except ValueError as e:
                raise ValueError(f"line {n}: bad timestamp {row['timestamp']!r}") from e
            ev = Event(row["case_id"], row["activity"].strip(), ts, row["resource"], row["role"],
                       {k: v for k, v in row.items() if k not in REQUIRED})
            cases.setdefault(ev.case_id, []).append(ev)
    if not cases:
        raise ValueError("event log is empty")
    for evs in cases.values():
        evs.sort(key=lambda e: e.timestamp)
    return cases


# ---------------------------------------------------------------- synthetic generator
# Fictional company: Northwind Appliances, warranty-claim handling. All numbers invented.

ROLES = {
    "Receive claim": ("system", ["portal"]),
    "Register claim": ("service agent", [f"agent_{i:02d}" for i in range(1, 9)]),
    "Check warranty eligibility": ("service agent", [f"agent_{i:02d}" for i in range(1, 9)]),
    "Request missing information": ("service agent", [f"agent_{i:02d}" for i in range(1, 9)]),
    "Receive missing information": ("customer", ["customer"]),
    "Technical assessment": ("technician", [f"tech_{i:02d}" for i in range(1, 4)]),
    "Approve resolution": ("team lead", ["lead_01", "lead_02"]),
    "Order spare part": ("logistics", ["logistics_01", "logistics_02"]),
    "Ship replacement": ("logistics", ["logistics_01", "logistics_02"]),
    "Notify customer": ("service agent", [f"agent_{i:02d}" for i in range(1, 9)]),
    "Close claim": ("service agent", [f"agent_{i:02d}" for i in range(1, 9)]),
}

# median waiting hours before each activity (lognormal), invented
WAIT_H = {
    "Register claim": 6, "Check warranty eligibility": 10, "Request missing information": 4,
    "Receive missing information": 52, "Technical assessment": 40, "Approve resolution": 30,
    "Order spare part": 8, "Ship replacement": 12, "Notify customer": 5, "Close claim": 20,
}


def _wait(rng: random.Random, act: str) -> timedelta:
    med = WAIT_H[act]
    return timedelta(hours=med * rng.lognormvariate(0, 0.55))


def generate(n_cases: int = 600, seed: int = 7, start: datetime = datetime(2026, 1, 5, 8, 0)) -> list[dict]:
    """Generate a reproducible synthetic warranty-claim event log (list of row dicts)."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(1, n_cases + 1):
        cid = f"WC-{i:05d}"
        t = start + timedelta(hours=rng.uniform(0, 24 * 90))
        value = round(rng.lognormvariate(5.0, 0.6), 2)  # claim value in EUR
        channel = rng.choice(["web", "web", "email", "call"])
        seq = ["Receive claim", "Register claim", "Check warranty eligibility"]
        # incomplete claims: more frequent for email/phone channel
        p_missing = 0.45 if channel != "web" else 0.2
        loops = 0
        while rng.random() < p_missing and loops < 3:
            seq += ["Request missing information", "Receive missing information", "Check warranty eligibility"]
            loops += 1
            p_missing *= 0.5
        seq.append("Technical assessment")
        if value > 200 or rng.random() < 0.3:
            seq.append("Approve resolution")
        seq.append("Order spare part" if rng.random() < 0.6 else "Ship replacement")
        seq += ["Notify customer", "Close claim"]
        for act in seq:
            if act != "Receive claim":
                t = t + _wait(rng, act)
            role, pool = ROLES[act]
            rows.append({"case_id": cid, "activity": act, "timestamp": t.replace(microsecond=0).isoformat(),
                         "resource": rng.choice(pool), "role": role, "channel": channel, "claim_value_eur": value})
    rows.sort(key=lambda r: (r["case_id"], r["timestamp"]))
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
