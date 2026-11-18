# Operating model (sample)

Designed for production; operated as a prototype. Thresholds below are illustrative and would be set with the process owner before a pilot.

## 1. Release gate (tick before each release)
- [ ] `python -m unittest discover -s tests` passes and the CI workflow is green
- [ ] Every must-pass memo case in `evals/EVALS.md` passes, run on the target model (not only simulated)
- [ ] `evals/check_memo.py` passes on the example memo
- [ ] The activity catalog and assumptions were reviewed by the process owner for this process
- [ ] Owner and backup named; the previous tag kept for rollback
- [ ] Users told what changed (CHANGELOG entry)

## 2. Rollout
Pilot with one process owner and one analyst for six weeks on one process. Success metric fixed before launch: the owner decides on every proposal within two weeks, with fewer than one correction per memo. Widen if both hold for four consecutive weeks; stop and fix if a memo states a figure not in facts.json.

## 3. Monitoring
| Signal | Source | Frequency | Alert |
|---|---|---|---|
| Usage | analyses and memos per week (`ops/` log) | weekly | none in two weeks: check in with the owner |
| Grounding | `check_memo.py` on every memo | every memo | any failure |
| Quality | owner corrections per memo; 5 memos sampled per month against the acceptance criteria | monthly | > 1 correction per memo |
| Decisions | proposals approved / changed / stopped | monthly | none decided in a month |
| Cost | model tokens per memo (from the model provider's usage page) | monthly | > 2x the pilot median |

See `ops/sample-monitoring-log.csv` for the format (invented data).

## 4. Feedback into evals
Every confirmed failure (a wrong number, an approval claimed, an upgraded level) becomes a new must-pass case in `evals/EVALS.md` before the fix ships.

## 5. Change and drift
Re-run the regression set (cases marked "yes") on any change to the skill, the assumptions file, the activity catalog format, or the model version. Roll back to the previous tag if a must-pass case regresses and the fix is not same-day.

## 6. Incident runbook
| Incident | Detected by | Contain | Follow-up |
|---|---|---|---|
| Memo states a figure not in facts.json and someone relied on it | check_memo, owner review | withdraw the memo; re-issue from facts.json | new eval case; root cause in CHANGELOG |
| Sensitive personal data in a log or memo | owner review | delete the outputs; rerun on a pseudonymised log | add the field to the pre-processing step |
| Injected text obeyed | E05-type review | stop memo drafting; revert to previous tag | new injection case |
| Cost spike | monthly cost check | switch to a smaller model or pause | cap per run |

## 7. Ownership and retirement
Owner: the process-improvement lead for the process. Backup: the analyst running pm2ai. Review every three months. Retire when no analysis has been run for two reviews or a process-mining platform covers the same need.
