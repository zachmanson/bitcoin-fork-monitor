---
phase: 1
slug: data-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 creates this |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | DATA-01 | unit | `pytest tests/test_database.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 0 | DATA-02 | unit | `pytest tests/test_models.py::test_two_blocks_same_height -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 0 | DATA-03 | unit | `pytest tests/test_analytics.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | DATA-03 | unit | `pytest tests/test_analytics.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — makes tests a package (required for relative imports)
- [ ] `tests/conftest.py` — in-memory SQLite session fixture
- [ ] `tests/test_analytics.py` — stale rate formula assertions (DATA-03)
- [ ] `tests/test_models.py` — DATA-02 two-blocks-at-same-height test
- [ ] `tests/test_database.py` — DATA-01 create_all idempotency test
- [ ] `pyproject.toml` — project definition with `[tool.pytest.ini_options]`
- [ ] pytest installed: `uv add pytest` or `pip install pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SQLite file created on fresh checkout | DATA-01 | Requires app startup from clean state | Delete `*.db`, run app entry point, verify file exists |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
