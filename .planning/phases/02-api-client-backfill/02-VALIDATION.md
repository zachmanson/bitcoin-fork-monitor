---
phase: 2
slug: api-client-backfill
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — already exists from Phase 1 |
| **Quick run command** | `python -m pytest tests/ -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (all unit tests, no real network calls) |

**Baseline:** 11 tests passing from Phase 1. Phase 2 adds tests alongside new modules.

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | BACK-03 | unit (mock) | `python -m pytest tests/test_api_client.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | BACK-03 | unit (mock) | `python -m pytest tests/test_api_client.py -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 0 | BACK-01/02 | unit | `python -m pytest tests/test_backfill.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | BACK-01/02 | unit | `python -m pytest tests/test_backfill.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_api_client.py` — stubs for BACK-03 (retry/backoff via mocked httpx)
- [ ] `tests/test_backfill.py` — stubs for BACK-01, BACK-02 (worker logic via mocked API client + in-memory DB)

No framework changes needed — pytest and conftest.py already in place from Phase 1.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Backfill thread starts on app startup | BACK-01 | Requires running FastAPI server | `uvicorn app.main:app`, observe logs for backfill start |
| Thread stops cleanly on Ctrl+C | BACK-01 | Requires running process + interrupt | Start app, press Ctrl+C, verify no hanging threads |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
