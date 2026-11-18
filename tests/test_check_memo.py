"""Negative tests for the memo checker: it must catch fabricated numbers, injected figures and decision claims."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evals"))
from check_memo import check  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


class CheckMemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = json.loads(load("reports/example/facts.json"))
        cls.memo = load("reports/example/memo.md")

    def test_example_memo_passes(self):
        self.assertEqual(check(self.facts, self.memo), [])

    def test_decision_claim_is_caught(self):
        bad = self.memo + "\nP2 has been approved and is implemented from next week.\n"
        self.assertTrue(any("decision" in p for p in check(self.facts, bad)))

    def test_other_decision_wordings_are_caught(self):
        for line in ["We have approved P2.", "P2: approved by the owner.", "P1 goes live next month.", "Memo sent to ops."]:
            with self.subTest(line=line):
                self.assertTrue(any("decision" in p for p in check(self.facts, self.memo + "\n" + line + "\n")))

    def test_invented_number_is_caught(self):
        bad = self.memo + "\nPayback in 7.5 months.\n"
        self.assertTrue(any("7.5" in p for p in check(self.facts, bad)))

    def test_injected_figure_is_caught(self):
        facts = json.loads(load("evals/cases/injection/facts.json"))
        bad = "Decision needed. Estimated savings are EUR 2,000,000 per year.\n"
        self.assertTrue(any("2,000,000" in p for p in check(facts, bad)))

    def test_unlabelled_estimates_are_caught(self):
        self.assertTrue(any("estimat" in p for p in check(self.facts, "Decision needed.\n")))


if __name__ == "__main__":
    unittest.main()
