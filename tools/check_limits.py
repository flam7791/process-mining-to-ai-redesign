#!/usr/bin/env python3
"""Check an agent/skill/prompt package against recorded platform limits.

Usage:
  python check_limits.py --platform m365-copilot 01_INSTRUCTIONS.txt K01_x.txt ...
  python check_limits.py --platform claude-skill path/to/skill-folder
  python check_limits.py --platform chatgpt-gpt --name "My GPT" 01_INSTRUCTIONS.md K*.md

Files named 01_INSTRUCTIONS* (or SKILL.md for skills) are treated as the instructions field;
files named K<nn>_* as knowledge files. Name/description can be passed with --name/--description
or are read from 00_SETUP_GUIDE (lines after "Name" / "Description" headings) when present.

Limits are those recorded in references/platforms/*.md on the date shown there.
Exit code 0 = within limits, 1 = at least one limit exceeded, 2 = usage error.
"""
import argparse
import glob
import os
import re
import sys

LIMITS = {
    "m365-copilot": {"instructions": 8000, "name": 30, "description": 1000, "knowledge_files": 20},
    "m365-copilot-prompt": {"instructions": 4000},  # practical ceiling; Microsoft publishes none
    "chatgpt-gpt": {"instructions": 8000, "knowledge_files": 20},
    "claude-skill": {"name": 64, "description": 1024, "body_lines": 500},
    "openclaw-skill": {"description": 1024, "body_lines": 500},
    "obsidian": {},
    "agents-md": {},
    "ollama": {},
}


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, text[m.end():]


def from_setup_guide(files, label):
    for f in files:
        if os.path.basename(f).upper().startswith("00_SETUP"):
            lines = read(f).splitlines()
            for i, line in enumerate(lines):
                if re.match(rf"^\s*[\d.]*\s*{label}\b", line, re.I) and i + 1 < len(lines):
                    val = lines[i + 1].strip()
                    if val:
                        return val
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=sorted(LIMITS))
    ap.add_argument("--name")
    ap.add_argument("--description")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    lim = LIMITS[a.platform]

    files = []
    for p in a.paths:
        if os.path.isdir(p):
            files += [f for f in glob.glob(os.path.join(p, "**", "*"), recursive=True) if os.path.isfile(f)]
        else:
            files += glob.glob(p) or [p]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        print("Missing:", ", ".join(missing))
        return 2

    problems, notes = [], []

    def check(label, value, key):
        if key in lim:
            ok = value <= lim[key]
            (notes if ok else problems).append(f"{'OK ' if ok else 'OVER'} {label}: {value} / {lim[key]}")

    if a.platform in ("claude-skill", "openclaw-skill"):
        skill_md = [f for f in files if os.path.basename(f) == "SKILL.md"]
        if not skill_md:
            print("No SKILL.md found")
            return 1
        fm, body = frontmatter(read(skill_md[0]))
        name, desc = a.name or fm.get("name"), a.description or fm.get("description")
        if a.platform == "claude-skill":
            if not name:
                problems.append("MISSING name in frontmatter")
            else:
                check("name characters", len(name), "name")
                if not re.fullmatch(r"[a-z0-9-]+", name):
                    problems.append(f"BAD  name '{name}': lowercase letters, digits and hyphens only")
                if re.search(r"claude|anthropic", name):
                    problems.append(f"BAD  name '{name}': must not contain 'claude' or 'anthropic'")
        if not desc:
            problems.append("MISSING description in frontmatter")
        else:
            check("description characters", len(desc), "description")
            if "<" in desc or ">" in desc:
                problems.append("BAD  description contains angle brackets")
        check("SKILL.md body lines", len(body.splitlines()), "body_lines")
    else:
        instr = [f for f in files if os.path.basename(f).upper().startswith(("01_INSTRUCTIONS", "P01_", "N01_"))]
        for f in instr:
            check(f"{os.path.basename(f)} characters", len(read(f)), "instructions")
        if not instr and "instructions" in lim:
            notes.append("NOTE no 01_INSTRUCTIONS/P01/N01 file given; instructions length not checked")
        kfiles = [f for f in files if re.match(r"^K\d+_", os.path.basename(f), re.I)]
        check("knowledge files", len(kfiles), "knowledge_files")
        name = a.name or from_setup_guide(files, "Name")
        desc = a.description or from_setup_guide(files, "Description")
        if name:
            check("name characters", len(name), "name")
        if desc:
            check("description characters", len(desc), "description")

    for n in notes:
        print(n)
    for p in problems:
        print(p)
    print("RESULT:", "FAIL" if problems else "PASS", f"({a.platform})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
