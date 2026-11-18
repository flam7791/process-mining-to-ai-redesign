# Design decisions

- **Measured and estimated never mix.** The miner only reports what the timestamps show. Every estimate lives under `redesign`, carries the assumption keys it rests on, and the report prints the assumption values. A reader can always tell which number came from the log.
- **Hard caps beat scores.** The AI-fit score ranks steps, but autonomy is capped by rules that no score can override: decisions at most L1 (the agent prepares evidence), high-risk or financial-authority steps at most L2 (a person approves every output). The tests enforce the caps.
- **Rework first.** A loop that a third of cases go through is usually cheaper to remove than to automate, so the first proposal targets the loop at intake, before any step-level automation.
- **Pilot, iterate or assist, never "implement".** Proposals end in a decision table for a named process owner. Neither the tool nor the memo agent can mark anything approved.
- **Deterministic core, model at the edge.** Mining, AI-fit and the value case are plain Python with no dependencies, so they are testable and reproducible in CI. The language model only writes the memo, and a mechanical check (`evals/check_memo.py`) verifies that every number it writes exists in facts.json.
- **Synthetic data.** The sample log is generated from a seed for a fictional company, so the repo can be public and the example output reproducible.
