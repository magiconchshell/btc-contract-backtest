# Release and Go-Live Checklists

Date: 2026-03-30
Project: `github-btc-backtest`
Target runtime: Python 3.12

---

## 1. Release Checklist

### Source control
- [ ] Working tree is clean
- [ ] All intended code/docs/config changes are committed
- [ ] No local runtime artifacts are staged
- [ ] Release commit hash is recorded

### Packaging / environment
- [ ] `pyproject.toml` metadata is current
- [ ] Dependency files are up to date:
  - [ ] `requirements-runtime.txt`
  - [ ] `requirements-dev.txt`
  - [ ] `requirements-research.txt`
- [ ] Python target remains 3.12
- [ ] Fresh virtualenv can be created successfully

### Quality gates
- [ ] `python scripts/release_gate.py --report --json --check-clean` reflects the intended hard gate
- [ ] `python scripts/release_gate.py --run --check-clean` passes locally
- [ ] CI on GitHub Actions hard gate is green
- [ ] Underlying hard-gate steps still match the current production scope:
  - [ ] `pytest -q` passes
  - [ ] `flake8 src` passes
  - [ ] `mypy src` passes
  - [ ] `python -m build` passes

### Documentation
- [ ] README matches actual install/test flow
- [ ] live-readiness report is current
- [ ] release/go-live checklists are current
- [ ] operational caveats are documented

### Release artifacts
- [ ] sdist builds successfully
- [ ] wheel builds successfully
- [ ] artifact versions match intended release version

---

## 2. Engineering Go-Live Checklist

### Execution correctness
- [ ] Reconciliation reports are enabled and reviewed
- [ ] Submit ledger is enabled and persisted
- [ ] Recovery orchestrator is enabled at startup
- [ ] Order monitor is active for governed live flow
- [ ] Cancel/replace orchestration path is tested

### Exchange constraints
- [ ] Lot size enforcement reviewed
- [ ] Tick size enforcement reviewed
- [ ] Minimum notional threshold reviewed
- [ ] Margin checks reviewed
- [ ] Leverage/mode assumptions reviewed
- [ ] Reduce-only semantics reviewed

### Restart / recovery
- [ ] Startup recovery report reviewed
- [ ] Pending/unknown intents reviewed before live enablement
- [ ] Remote-only and local-only orders reviewed
- [ ] Restart scenario tested in non-production environment

### Observability
- [ ] Audit log path verified
- [ ] Alert sink path verified
- [ ] Execution event recording path verified
- [ ] Runtime state persistence path verified
- [ ] Operator knows where reconcile and recovery reports are stored

### Dry-run progression
- [ ] Backtest run reviewed
- [ ] Paper trading run reviewed
- [ ] Shadow trading run reviewed
- [ ] Governed live dry-run reviewed
- [ ] Tiny-size supervised live pilot reviewed

---

## 3. Operational Go-Live Checklist

## Current release posture

This repo currently treats **Gate B** as the active progression gate for restart-convergence and event-state correctness. **Gate C** is a supervised testnet pilot gate and should stay blocked until the required fixtures, drills, and pilot evidence are reviewed.

Practical operator path:

- keep Gate B green
- use shadow / paper / governed dry-run evidence first
- only then move to the supervised tiny-size Gate C pilot

### Human controls
- [ ] Emergency stop verified
- [ ] Maintenance mode verified
- [ ] Approval queue verified
- [ ] Operator alert routing verified
- [ ] Incident logging path verified

### Deployment hygiene
- [ ] Secrets are not stored in repo
- [ ] `.gitignore` covers runtime artifacts and local outputs
- [ ] Production config is separated from research/local config
- [ ] Runtime output directories are writable
- [ ] Timezone / clock assumptions are verified

### Before enabling real capital
- [ ] Exchange account and symbol verified
- [ ] Available balance and margin verified
- [ ] Position mode verified
- [ ] Leverage verified on exchange
- [ ] Tiny-size limit is explicitly configured
- [ ] Human supervision plan is defined

### Pilot rules
- [ ] First live run is supervised
- [ ] First live run uses minimal size
- [ ] Reconcile report is reviewed immediately after first run
- [ ] Submit ledger is reviewed immediately after first run
- [ ] Recovery report is reviewed after restart test

---

## 4. Deferred Quality Debt (Tracked, Not Ignored)

These items are known and should be improved, but they should not block all delivery in the same sweep unless explicitly prioritized:

- Full-repo flake8 cleanup
- Full-repo mypy cleanup
- Exchange websocket/user-stream integration
- Exchange metadata auto-sync
- Restart convergence v2 with fill replay
- Cancel/fill/replace race hardening
- Longer soak and fault-injection runs

---

## 5. Recommended CI Policy

### Hard fail gates
- `python scripts/release_gate.py --run --check-clean`

### Current hard gates expanded
- `pytest -q`
- `flake8 src`
- `mypy src`
- `python -m build`

### Out of scope for the current production gate
- `research/`
- exploratory notebooks
- ad-hoc analysis scripts

This keeps the quality gate aligned with the current objective: a production-ready real-time trading engine paired with a reliable backtest system, not research hygiene perfection.
