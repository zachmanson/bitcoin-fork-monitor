---
phase: 02-api-client-backfill
verified: 2026-03-09T00:00:00Z
status: passed
score: 13/13 must-haves verified
gaps: []
human_verification:
  - test: "Run the app for the first time against a clean database and observe that the backfill thread starts and writes rows to bitcoin_forks.db"
    expected: "SyncState row appears in DB with last_synced_height advancing every ~100 blocks; Block rows are being inserted; log lines appear every 1000 blocks"
    why_human: "The backfill hits the live mempool.space API over the network and takes hours — cannot verify real ingestion in automated tests"
  - test: "Kill the running process mid-backfill, restart it, and confirm last_synced_height picks up from where it left off (not from 0)"
    expected: "App restarts, logs 'Backfill starting from height N to tip M' where N is a non-zero checkpoint, not genesis"
    why_human: "Crash/resume cycle requires a real process kill during a live backfill run"
---

# Phase 2: API Client + Backfill — Verification Report

**Phase Goal:** Full Bitcoin blockchain history (all orphaned/stale blocks since genesis) is persisted in SQLite via a rate-limited, checkpointed backfill that can survive process restarts
**Verified:** 2026-03-09
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

The phase goal decomposes into four Success Criteria from ROADMAP.md. All four are verified below.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running the app for the first time triggers the backfill worker, which fetches historical fork/orphan data from mempool.space and writes it to SQLite | VERIFIED | `app/main.py` lifespan launches `threading.Thread(target=run_backfill)` when `backfill_complete` is False; `app/backfill.py` `_do_backfill()` calls `fetch_blocks_page` and writes `Block`/`ForkEvent` rows; `test_backfill_writes_blocks` (30 rows) and `test_backfill_detects_fork` (ForkEvent + orphan Block row) pass |
| 2 | Killing and restarting the app mid-backfill resumes from the last checkpointed height rather than restarting from genesis | VERIFIED | `_do_backfill()` reads `SyncState.last_synced_height` and sets `current_height = state.last_synced_height`; `write_checkpoint()` persists height to SQLite every `CHECKPOINT_INTERVAL` blocks; `test_backfill_resumes_from_checkpoint` asserts first page call uses height `114` (= 100 + 14) not `14` |
| 3 | The API client enforces at least 500ms between requests and applies exponential backoff on HTTP 429 responses — no IP ban during development | VERIFIED | `RETRY_DELAYS = [1, 2, 4, 8, 16]` in `api_client.py`; 429/5xx trigger `time.sleep(delay)` and `continue`; `THROTTLE_SECONDS = 0.5` in `backfill.py` applied via `time.sleep(THROTTLE_SECONDS)` between every page fetch; 8 `test_api_client.py` tests pin retry behavior |
| 4 | After backfill completes, the sync_state table records a "backfill complete" marker and the worker does not run again on subsequent starts | VERIFIED | `_do_backfill()` sets `state.backfill_complete = True` and calls `write_checkpoint()` after the loop; `main.py` lifespan reads `state.backfill_complete` before launching thread (`already_done` guard); `test_backfill_skips_if_complete` asserts `fetch_blocks_page` is never called when flag is `True` |

**Score:** 4/4 Success Criteria verified

---

## Required Artifacts

### Plan 02-01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/api_client.py` | `fetch_blocks_page()` function — sole interface to mempool.space | VERIFIED | 102 lines; exports `fetch_blocks_page`, `BASE_URL`, `RETRY_DELAYS`, `REQUEST_THROTTLE_SECONDS`; full retry loop with `_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}` |
| `tests/test_api_client.py` | Unit tests for retry/backoff behavior using mocked httpx | VERIFIED | 177 lines; contains all 8 required test functions across 4 test classes; uses `patch("app.api_client.httpx.Client")` — no real HTTP calls |

### Plan 02-02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/backfill.py` | `run_backfill()` worker function and `_do_backfill()` implementation | VERIFIED | 225 lines; exports `run_backfill`, `_do_backfill(engine=None)`, `write_checkpoint`, `_process_block`; full checkpoint/resume logic, ForkEvent creation, idempotency guards |
| `app/main.py` | FastAPI app with lifespan context manager that launches/joins the backfill thread | VERIFIED | 99 lines; `AsyncContextManager` lifespan; `threading.Thread(target=run_backfill, daemon=True, name="backfill")`; `join(timeout=5.0)` on shutdown; `/health` endpoint |
| `tests/test_backfill.py` | Unit tests for backfill worker logic using mocked `fetch_blocks_page` and in-memory DB | VERIFIED | 307 lines; contains all 5 required test classes/functions; injects engine via `_do_backfill(engine=engine)` — no production DB touched |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_api_client.py` | `app/api_client.py` | `patch("app.api_client.httpx.Client")` | WIRED | Line 48: `with patch("app.api_client.httpx.Client") as mock_client_cls`; return value threaded through `__enter__` mock correctly |
| `app/main.py` | `app/backfill.py` | `threading.Thread(target=run_backfill)` | WIRED | Line 73-74: `backfill_thread = threading.Thread(target=run_backfill, daemon=True, name="backfill")`; `run_backfill` imported at line 38 |
| `app/backfill.py` | `app/api_client.py` | `from app.api_client import fetch_blocks_page` | WIRED | Line 26: import; used at lines 103 and 124 in `_do_backfill()` |
| `app/backfill.py` | `app.database.engine` | `Session(engine)` — thread-owned session | WIRED | Line 27: `from app.database import engine as _module_engine`; line 85: `with Session(engine) as session:`; injected engine used in tests |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BACK-01 | 02-02-PLAN.md | On first run, system backfills complete historical fork/orphan data from genesis via mempool.space API | SATISFIED | `_do_backfill()` walks from `last_synced_height` (0 on first run) to tip via `fetch_blocks_page`; writes `Block` and `ForkEvent` rows; 5 tests pass |
| BACK-02 | 02-02-PLAN.md | Backfill progress is checkpointed to SQLite so a restart resumes where it left off | SATISFIED | `write_checkpoint()` writes `SyncState.last_synced_height` every `CHECKPOINT_INTERVAL=100` blocks; `_do_backfill()` reads this on startup; `test_backfill_resumes_from_checkpoint` and `test_checkpoint_frequency` pass |
| BACK-03 | 02-01-PLAN.md | Backfill implements adaptive rate limiting and exponential backoff to avoid being blocked by mempool.space | SATISFIED | `RETRY_DELAYS = [1, 2, 4, 8, 16]`; `THROTTLE_SECONDS = 0.5` applied per page; 8 api_client tests pin retry on 429, 5xx, and `RequestError` |

No orphaned requirements: all three BACK-XX IDs assigned to Phase 2 in REQUIREMENTS.md traceability table are covered by the two plans and verified above.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/backfill.py` | 222 | `datetime.utcnow()` — deprecated in Python 3.12 | Info | Generates `DeprecationWarning` in test output; no functional impact; `datetime.now(UTC)` is the preferred form |

No stubs, placeholders, empty implementations, or TODO/FIXME comments found in any Phase 2 file.

---

## Test Suite Results

```
24 passed, 13 warnings in 0.55s

tests/test_analytics.py:  7 tests  (Phase 1 — no regressions)
tests/test_api_client.py: 8 tests  (BACK-03)
tests/test_backfill.py:   5 tests  (BACK-01, BACK-02)
tests/test_database.py:   2 tests  (Phase 1 — no regressions)
tests/test_models.py:     2 tests  (Phase 1 — no regressions)
```

Phase 1 baseline of 11 tests is preserved. The 13 new Phase 2 tests all pass. Zero regressions.

Smoke test:
```
python -c "from app.main import app; print(app.title)"
# Bitcoin Fork Monitor
```

---

## Human Verification Required

### 1. Live Backfill Ingestion

**Test:** Start the server for the first time against a clean database (`rm bitcoin_forks.db` if needed), let it run for 10+ minutes, then inspect the DB with `sqlite3 bitcoin_forks.db "SELECT COUNT(*) FROM block; SELECT * FROM syncstate;"`.
**Expected:** Block count grows over time; `last_synced_height` advances; backfill log lines appear every 1000 blocks.
**Why human:** Backfill runs against the live mempool.space API over a long-running process — cannot verify real ingestion programmatically in CI.

### 2. Crash-Resume Cycle

**Test:** Start the server, wait until `last_synced_height` is > 0 (confirm via DB query), kill the process with Ctrl+C, restart it, observe startup logs.
**Expected:** Log line shows `Backfill starting from height N to tip M` where N matches the last saved checkpoint, not 0 (genesis).
**Why human:** Requires a real process kill mid-backfill and inspection of live log output.

---

## Gaps Summary

No gaps. All automated checks passed:
- All 3 artifacts from Plan 02-01 are present, substantive, and wired.
- All 3 artifacts from Plan 02-02 are present, substantive, and wired.
- All 4 key links are confirmed in actual source code (not just summaries).
- All 3 phase requirements (BACK-01, BACK-02, BACK-03) are satisfied by real implementation.
- 24 tests pass, 0 failures, 0 regressions from Phase 1.
- No stubs, placeholders, or disconnected code found.

Two items are flagged for human verification because they require a live multi-hour network run that cannot be automated. These are operational confirmation items, not implementation gaps.

---

_Verified: 2026-03-09_
_Verifier: Claude (gsd-verifier)_
