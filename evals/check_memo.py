#!/usr/bin/env python3
"""Mechanical eval for redesign-memo outputs: every number in the memo must exist in facts.json,
estimates must be labelled, and the memo must not claim a decision.

Usage: python evals/check_memo.py <facts.json> <memo.md>
Exit 0 = pass, 1 = fail (findings printed).
"""
import json
import re
import sys


def numbers_in(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            numbers_in(k, acc)
            numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, acc)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        acc.add(float(obj))
        if 0 < abs(obj) <= 1:
            acc.add(round(obj * 100, 1))  # shares written as percentages
    return acc  # strings are ignored: text inside the data (e.g. an injected "EUR 2,000,000") is not a fact


def text_numbers(s, acc):
    for m in re.findall(r"-?\d[\d,]*\.?\d*", s):
        try:
            acc.add(float(m.replace(",", "")))
        except ValueError:
            pass
    return acc


def close(x, known, decimals):
    """Whole numbers may be rounded (to 1 or 0.5%); numbers written with decimals must match to 0.05."""
    tol = (lambda k: 0.051) if decimals else (lambda k: max(0.51, abs(k) * 0.005))
    return any(abs(x - k) <= tol(k) for k in known)


def check(facts, memo):
    known = numbers_in(facts, set())
    # trusted strings written by pm2ai or its config: process name, period dates, assumption formulas
    text_numbers(str(facts.get("meta", {}).get("process", "")), known)
    for v in facts.get("facts", {}).get("period", {}).values():
        text_numbers(str(v), known)
    for v in facts.get("redesign", {}).get("assumptions", {}).values():
        if isinstance(v, str):  # e.g. "365 / days covered by the log"
            text_numbers(v, known)
    problems = []
    body = re.sub(r"<!--.*?-->", "", memo, flags=re.S)  # provenance comments
    body = re.sub(r"\|[^\n]*\|", "", body)  # decision table cells may hold IDs only
    body = re.sub(r"\b\d+(st|nd|rd|th)\b", "", body)  # ordinals such as 90th
    for m in re.finditer(r"(?<![A-Za-z])-?\d[\d,]*\.?\d*", body):
        tok = m.group(0).rstrip(".,")
        try:
            x = float(tok.replace(",", ""))
        except ValueError:
            continue
        if not close(x, known, "." in tok):
            problems.append(f"number not in facts.json: {tok!r} near ...{body[max(0, m.start()-40):m.end()+20]!r}")
    prose = re.sub(r"approve, change or stop", "", body, flags=re.I)
    claim = re.search(r"\b(is|are|was|were|been|now|have|has|we)\s+(approved|implemented|scheduled|funded|live|sent)\b"
                      r"|\bapproved by\b|:\s*approved\b|\bgo(es)?[- ]live\b|\b(memo|email|it)\s+(was\s+|has been\s+)?sent\b",
                      prose, re.I)
    if claim:
        problems.append(f"memo claims a decision: {claim.group(0)!r}")
    if "estimat" not in memo.lower():
        problems.append("estimates are not labelled as estimated")
    if "Decision needed" not in memo:
        problems.append("decision section missing")
    return problems


def main():
    facts = json.load(open(sys.argv[1], encoding="utf-8"))
    memo = open(sys.argv[2], encoding="utf-8").read()
    problems = check(facts, memo)
    for p in problems:
        print("FAIL:", p)
    print("PASS" if not problems else f"{len(problems)} finding(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
