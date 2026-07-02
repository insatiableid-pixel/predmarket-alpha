---
name: code-quality-gates
description: Run the full code-quality gate suite (ruff lint, mypy strict, import-linter boundaries, vulture dead-code, deptry unused-deps, jscpd duplicates, tech-debt/file-size ratchets, AGENTS.md validation). Use before committing or when fixing code-quality regressions.
---

# Code Quality Gates Skill

## Purpose

Run every configured code-quality tool in the correct order and interpret
results. The platform uses ruff (lint + format), mypy (strict types),
import-linter (architectural boundaries), vulture (dead code), deptry
(unused dependencies), jscpd (duplicate code), and two ratchet gates
(tech-debt markers and file sizes).

## Standard Workflow

1. **Lint + format** (must pass clean):
   ```bash
   make lint
   make format
   ```

2. **Type checking** (advisory; ratchet down, do not ignore):
   ```bash
   make typecheck
   ```

3. **Architectural boundaries** (must pass):
   ```bash
   make modularize
   ```

4. **Full quality suite**:
   ```bash
   make quality
   ```

5. **Tests** (must pass with coverage >= 65%):
   ```bash
   make test
   ```

## Ratchet Gates

Tech-debt markers (TODO/FIXME) and large files use baseline ratchets.
If a check fails, either fix the new violations or regenerate the baseline:

```bash
make tech-debt-regen    # Accept current TODO/FIXME count as new floor
make file-sizes-regen   # Accept current file sizes as new ceiling
```

Regenerating baselines should be a deliberate decision, not a reflex.

## AGENTS.md Validation

Verify that AGENTS.md references match actual Makefile targets:

```bash
make validate-agents
```
