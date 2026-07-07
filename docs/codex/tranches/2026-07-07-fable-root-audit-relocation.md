# Fable Root Audit Relocation

Date: 2026-07-07

## Why

Fable explicitly called out root-level audit markdown clutter as part of the repo hygiene problem. Historical audits and completion reports should not live beside operational entry points.

## What Moved

Moved the root audit/advice/remediation/completion-report files into `docs/audits/`.

Recovered the active `Fable_5_Repo_Advice_7.6.2026.md` memo from the split stash and archived it under `docs/audits/` so the current guiding advice is tracked in-repo.

Root text/markdown files now remain limited to:

- `AGENTS.md`
- `README.md`
- `dev-requirements.txt`
- `requirements.txt`
- `kalshi_ev_discovery_plan.md`

## Guardrails

- Documentation/filesystem hygiene only.
- No source behavior changed.
- No thresholds changed.
- No labels inferred.
- No EV, paper, or live promotion changed.
- No account, order, or execution path touched.

## Verification

- Root text/markdown scan shows only operational root files.
- Moved-report references in Codex notes now point to `docs/audits/...`.
- The active Fable 7/6 advice memo is tracked under `docs/audits/`.
- `git diff --check` clean.
