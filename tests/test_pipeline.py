import csv
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pm2ai.ai_fit import assess, assess_all  # noqa: E402
from pm2ai.eventlog import generate, load_csv, write_csv  # noqa: E402
from pm2ai.mining import mine  # noqa: E402
from pm2ai.redesign import propose  # noqa: E402
from pm2ai.report import to_markdown  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
TINY = [  # 3 hand-made cases; case B loops once through the missing-information step
    ("A", "Register claim", "2026-01-01T08:00:00", "agent_01", "service agent"),
    ("A", "Check warranty eligibility", "2026-01-01T10:00:00", "agent_01", "service agent"),
    ("A", "Close claim", "2026-01-01T14:00:00", "agent_02", "service agent"),
    ("B", "Register claim", "2026-01-02T08:00:00", "agent_01", "service agent"),
    ("B", "Check warranty eligibility", "2026-01-02T09:00:00", "agent_01", "service agent"),
    ("B", "Request missing information", "2026-01-02T10:00:00", "agent_01", "service agent"),
    ("B", "Receive missing information", "2026-01-03T10:00:00", "customer", "customer"),
    ("B", "Check warranty eligibility", "2026-01-03T12:00:00", "agent_02", "service agent"),
    ("B", "Close claim", "2026-01-03T20:00:00", "agent_02", "service agent"),
    ("C", "Register claim", "2026-01-04T08:00:00", "agent_03", "service agent"),
    ("C", "Check warranty eligibility", "2026-01-04T09:00:00", "agent_03", "service agent"),
    ("C", "Close claim", "2026-01-04T10:00:00", "agent_03", "service agent"),
]


def tiny_log(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "activity", "timestamp", "resource", "role"])
        w.writerows(TINY)


def load_cfg():
    with open(os.path.join(ROOT, "config", "activity_catalog.json"), encoding="utf-8") as f:
        cat = json.load(f)
    with open(os.path.join(ROOT, "config", "assumptions.json"), encoding="utf-8") as f:
        asm = json.load(f)
    return cat, asm


class Mining(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "tiny.csv")
        tiny_log(self.path)
        self.cases = load_csv(self.path)
        self.f = mine(self.cases)

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_and_cycle_time(self):
        self.assertEqual(self.f["cases"], 3)
        self.assertEqual(self.f["events"], 12)
        self.assertEqual(self.f["cycle_time_h"]["median"], 6.0)   # cycle times 6, 36, 2 hours

    def test_rework_detected(self):
        self.assertEqual(self.f["rework"]["cases_with_rework"], 1)
        self.assertIn("Check warranty eligibility", self.f["rework"]["repeated_activities"])

    def test_variants_and_dfg(self):
        self.assertEqual(self.f["variants"]["distinct"], 2)
        edge = next(e for e in self.f["dfg"] if e["from"] == "Register claim" and e["to"] == "Check warranty eligibility")
        self.assertEqual(edge["count"], 3)

    def test_bottleneck_is_largest_total_wait(self):
        # Receive missing information carries 24 h of waiting, the largest single block
        self.assertEqual(self.f["activities"][0]["activity"], "Receive missing information")

    def test_bad_log_is_rejected(self):
        bad = os.path.join(self.tmp.name, "bad.csv")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("case_id,activity\nA,x\n")
        with self.assertRaises(ValueError):
            load_csv(bad)


class AiFit(unittest.TestCase):
    def test_high_risk_never_above_l2(self):
        r = assess("x", {"task_type": "data_entry", "data_available": True, "risk": "high", "financial_authority": False})
        self.assertIn(r["level"], ("L1", "L2"))

    def test_financial_authority_capped(self):
        r = assess("x", {"task_type": "data_entry", "data_available": True, "risk": "low", "financial_authority": True})
        self.assertEqual(r["level"], "L2")

    def test_decision_never_above_l1(self):
        r = assess("x", {"task_type": "judgement_decision", "data_available": True, "risk": "low", "financial_authority": False})
        self.assertEqual(r["level"], "L1")

    def test_physical_and_unknown_are_l0(self):
        self.assertEqual(assess("x", {"task_type": "physical", "risk": "low"})["level"], "L0")
        self.assertEqual(assess("x", None)["level"], "L0")

    def test_every_level_above_l0_has_guardrails(self):
        cat, _ = load_cfg()
        for r in assess_all(list(cat["activities"]), cat):
            if r["level"] != "L0":
                self.assertTrue(r["guardrails"], r["activity"])


class Redesign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat, cls.asm = load_cfg()
        rows = generate(300, seed=11)
        cls.tmp = tempfile.TemporaryDirectory()
        p = os.path.join(cls.tmp.name, "log.csv")
        write_csv(rows, p)
        cls.cases = load_csv(p)
        cls.facts = mine(cls.cases)
        cls.fits = assess_all([a["activity"] for a in cls.facts["activities"]], cls.cat)
        cls.r = propose(cls.facts, cls.fits, cls.cat, cls.asm, cls.cases)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_estimate_names_its_assumptions(self):
        for p in self.r["proposals"]:
            self.assertTrue(p["assumptions_used"], p["id"])
            self.assertIn("value_eur_per_year", p["estimate"])

    def test_after_never_worse_than_before(self):
        c = self.r["cycle_time_estimate_h"]
        self.assertLessEqual(c["median_after"], c["median_before"])

    def test_no_l0_or_external_target(self):
        levels = {f["activity"]: f["level"] for f in self.fits}
        for p in self.r["proposals"]:
            self.assertNotEqual(levels[p["target"]], "L0")

    def test_approval_pending(self):
        self.assertEqual(self.r["approval"]["status"], "awaiting process-owner review")

    def test_report_labels_estimates_and_asks_approval(self):
        md = to_markdown({"meta": {"process": "t", "source": "t"}, "facts": self.facts, "ai_fit": self.fits, "redesign": self.r})
        self.assertIn("## 5. Approval required", md)
        self.assertIn("*estimate*", md)
        self.assertIn("## 4. Assumptions behind every estimate", md)


class Reproducible(unittest.TestCase):
    def test_generator_is_deterministic(self):
        h = lambda rows: hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()
        self.assertEqual(h(generate(50, seed=3)), h(generate(50, seed=3)))


if __name__ == "__main__":
    unittest.main()
