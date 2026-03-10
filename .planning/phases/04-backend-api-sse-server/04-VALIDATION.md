---
phase: 4
slug: backend-api-sse-server
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_stats.py tests/test_forks.py tests/test_blocks.py tests/test_events.py -x -q` |
| **Full suite command** | `pytest -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_stats.py tests/test_forks.py tests/test_blocks.py tests/test_events.py -x -q`
- **After every plan wave:** Run `pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 0 | DASH-02 | unit | `pytest tests/test_stats.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 0 | DASH-02 | unit | `pytest tests/test_forks.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 0 | DASH-02 | unit | `pytest tests/test_blocks.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 0 | DASH-04 | unit | `pytest tests/test_events.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 1 | DASH-04 | unit | `pytest tests/test_events.py::test_event_bus_notify -x -q` | ❌ W0 | ⬜ pending |
| 4-02-03 | 02 | 1 | DASH-04 | unit | `pytest tests/test_events.py::test_sse_content_type -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_stats.py` — stubs for DASH-02 (`/api/stats` endpoint)
- [ ] `tests/test_forks.py` — stubs for `/api/forks` pagination
- [ ] `tests/test_blocks.py` — stubs for `/api/blocks` recent blocks
- [ ] `tests/test_events.py` — stubs for DASH-04 (EventBus + SSE content type)
- [ ] `app/events.py` — EventBus module skeleton (does not exist yet)
- [ ] `app/routers/__init__.py` — routers package init

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSE client receives event within 2s of monitor writing to DB | DASH-04 | End-to-end timing requires live monitor + real Bitcoin node | Start app, open browser console, subscribe to `/api/events`, wait for next block |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
