---
phase: 3
slug: fork-detection-live-monitoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_fork_detector.py -x -q` |
| **Full suite command** | `pytest -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_fork_detector.py -x -q`
- **After every plan wave:** Run `pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | MONI-02 | unit | `pytest tests/test_fork_detector.py -x -q` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | MONI-02 | unit | `pytest tests/test_fork_detector.py::TestDetectFork -x -q` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | MONI-02 | unit | `pytest tests/test_fork_detector.py::TestWriteForkEvent -x -q` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 1 | MONI-02 | unit | `pytest tests/test_fork_detector.py::TestForkIdempotency -x -q` | ❌ W0 | ⬜ pending |
| 3-01-05 | 01 | 1 | MONI-02 | unit | `pytest tests/test_fork_detector.py::TestPendingResolution -x -q` | ❌ W0 | ⬜ pending |
| 3-02-01 | 02 | 0 | MONI-01, MONI-03 | unit | `pytest tests/test_monitor.py -x -q` | ❌ W0 | ⬜ pending |
| 3-02-02 | 02 | 1 | MONI-01 | unit | `pytest tests/test_monitor.py::TestWebSocketSubscribe -x -q` | ❌ W0 | ⬜ pending |
| 3-02-03 | 02 | 1 | MONI-01 | unit | `pytest tests/test_monitor.py::TestBackfillGate -x -q` | ❌ W0 | ⬜ pending |
| 3-02-04 | 02 | 1 | MONI-03 | unit | `pytest tests/test_monitor.py::TestRestFallback -x -q` | ❌ W0 | ⬜ pending |
| 3-02-05 | 02 | 1 | MONI-03 | unit | `pytest tests/test_monitor.py::TestGapFill -x -q` | ❌ W0 | ⬜ pending |
| 3-02-06 | 02 | 1 | MONI-03 | unit | `pytest tests/test_monitor.py::TestGapFillForkDetection -x -q` | ❌ W0 | ⬜ pending |
| 3-02-07 | 02 | 1 | MONI-03 | unit | `pytest tests/test_monitor.py::TestLastSyncedHeight -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_fork_detector.py` — stubs for MONI-02 (pure function tests, in-memory DB fixture)
- [ ] `tests/test_monitor.py` — stubs for MONI-01, MONI-03 (mock websockets.sync.client.connect and fetch_blocks_page)

*Existing `tests/conftest.py` with `engine_fixture` and `session_fixture` covers all DB setup needs — no changes required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WebSocket receives live block events from mempool.space | MONI-01 | Requires live network connection and waiting ~10 min for a real Bitcoin block | Run app, watch logs for "New block received via WebSocket" |
| Monitor recovers from WS disconnect and resumes live tracking | MONI-03 | Requires intentional network interruption | Kill network briefly, verify WARNING log + INFO recovery log |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
