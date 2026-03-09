---
phase: 02-api-client-backfill
plan: "01"
subsystem: api-client
tags: [http-client, retry, backoff, httpx, tdd]
dependency_graph:
  requires: []
  provides: [fetch_blocks_page, BASE_URL, RETRY_DELAYS]
  affects: [backfill-worker]
tech_stack:
  added: [httpx]
  patterns: [context-manager, exponential-backoff, tdd-red-green]
key_files:
  created:
    - app/api_client.py
    - tests/test_api_client.py
  modified: []
key_decisions:
  - "time.sleep lives inside retry loop only — no sleep on successful first call; inter-page throttle belongs to backfill worker"
  - "RETRY_DELAYS list is the single source of truth for backoff schedule — 5 entries = 5 total attempts"
  - "_RETRYABLE_STATUS_CODES set contains 429/500/502/503/504; all others treated as success or raise via raise_for_status()"
metrics:
  duration: "2m"
  completed_date: "2026-03-09"
  tasks_completed: 1
  files_created: 2
  files_modified: 0
---

# Phase 2 Plan 01: API Client Module Summary

**One-liner:** mempool.space HTTP client with 5-attempt exponential backoff (1/2/4/8/16s) retrying 429, 5xx, and network errors via httpx, pinned by 8 mocked unit tests.

## What Was Built

`app/api_client.py` is the sole outbound HTTP interface for the application. Every future plan that needs block data calls `fetch_blocks_page(start_height)` — no other module should make HTTP requests directly.

The function opens an `httpx.Client` context manager, iterates over `RETRY_DELAYS = [1, 2, 4, 8, 16]`, and handles three cases per attempt:
- Retryable status (429/500/502/503/504): log warning, sleep, continue
- `httpx.RequestError` (network failure): log warning, sleep (unless last attempt), continue
- Anything else: call `raise_for_status()` then return `resp.json()`

If all 5 attempts fail, `RuntimeError` is raised with the block height in the message so the caller knows which height failed.

## Tests Written (TDD)

8 tests in `tests/test_api_client.py`, all using `unittest.mock.patch` on `app.api_client.httpx.Client`:

| Test | What It Verifies |
|------|-----------------|
| `test_success_returns_blocks` | 200 response returns the parsed JSON list |
| `test_correct_url_constructed` | URL is `BASE_URL/api/v1/blocks/<height>` |
| `test_retry_on_429` | 4 x 429 then 200 → returns successfully |
| `test_retry_on_5xx` | 4 x 503 then 200 → returns successfully |
| `test_all_retries_exhausted` | 5 x 429 → raises RuntimeError with height in message |
| `test_network_error_retries` | 1 x RequestError then 200 → returns successfully |
| `test_network_error_all_retries` | Always RequestError → raises RuntimeError |
| `test_500ms_throttle_not_called_on_success` | `time.sleep` not called when first attempt succeeds |

## Verification

```
python -m pytest tests/ -v
19 passed, 1 warning in 0.24s
```

Phase 1 baseline: 11 tests. New tests: 8. Total: 19. Zero regressions.

## Deviations from Plan

None — plan executed exactly as written.

## Key Design Notes

**Why `httpx` instead of `requests`?** `httpx` is the modern Python HTTP client with better async support. The backfill worker is synchronous now, but `httpx` won't block a migration to async if needed later.

**Why store `RETRY_DELAYS` as a list?** It makes the backoff schedule explicit — you can read it and immediately know the shape: 5 attempts at 1s, 2s, 4s, 8s, 16s. It also makes tests easy: `assert len(RETRY_DELAYS) == 5` is clearer than testing implementation internals.

**Why does `time.sleep` live only inside the retry loop?** The 500ms inter-page throttle is a backfill-worker concern — it applies between pages of a successful batch. The client function shouldn't know about the caller's pacing strategy.

## Commits

- `a94a626` — test(02-01): add failing tests for fetch_blocks_page (RED)
- `0a85776` — feat(02-01): implement fetch_blocks_page with exponential backoff (GREEN)
