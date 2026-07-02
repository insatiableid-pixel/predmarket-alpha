---
name: type2-paper-matcher
description: Run the Type 2 sportsbook-reference paper-matching workflow (reference intake, builder hardening, candidate disposition, threshold sensitivity). Use when working on Type 2 reference capture or paper matching research.
---

# Type 2 Paper Matcher Skill

## Purpose

Operate the Type 2 sportsbook-reference paper-matching pipeline: intake
references from sportsbook odds, build hardened reference rows, evaluate
candidates against thresholds, and run sensitivity analysis on gating
parameters. All work is research-only.

## Critical Guardrails

- Reference rows are paper-only; never create live execution paths.
- Threshold changes require explicit policy review.
- Candidate disposition must record a reason for every reject/accept decision.
- Prefer replay of saved artifacts over live data fetches.

## Standard Workflow

1. **Intake**: Build references from captured sportsbook odds data.
   ```bash
   make type2-reference-preflight
   make type2-reference-build
   ```

2. **Match**: Run the paper matcher against current prediction-market data.
   ```bash
   make type2-paper-matcher
   ```

3. **Disposition**: Evaluate candidates and record accept/reject reasons.
   ```bash
   make type2-candidate-disposition
   ```

4. **Sensitivity**: Verify thresholds are not brittle.
   ```bash
   make type2-threshold-sensitivity
   ```

## Verification

```bash
make check-env
make test-unit
.venv/bin/pytest tests/test_type2_*.py -v --tb=short
```
