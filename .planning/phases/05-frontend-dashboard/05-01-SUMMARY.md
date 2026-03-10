---
phase: 05-frontend-dashboard
plan: 01
subsystem: analytics-api + frontend-scaffold
tags: [fastapi, sveltekit, analytics, vite, frontend]
dependency_graph:
  requires: []
  provides:
    - "GET /api/analytics/stale-rate-over-time"
    - "GET /api/analytics/era-breakdown"
    - "frontend/ SvelteKit project with static adapter"
    - "Vite proxy config /api/* -> localhost:8000"
  affects:
    - "app/main.py (analytics router wired)"
    - "frontend/src/routes (page shell for plans 02-04)"
tech_stack:
  added:
    - "@sveltejs/kit ^2 (SvelteKit app framework)"
    - "svelte ^5 (UI component framework)"
    - "@sveltejs/adapter-static ^3 (static SPA build for FastAPI serving)"
    - "vite ^6 (build tool + dev proxy)"
    - "lightweight-charts ^5 (charting, used in later plans)"
  patterns:
    - "SQLAlchemy func.strftime() for SQLite date bucketing"
    - "Integer division on ORM column for era grouping (height / 2016)"
    - "SvelteKit +layout.svelte / +page.svelte file-based routing"
    - "Vite server proxy to eliminate CORS in dev"
key_files:
  created:
    - app/routers/analytics.py
    - frontend/package.json
    - frontend/svelte.config.js
    - frontend/vite.config.ts
    - frontend/src/app.html
    - frontend/src/app.css
    - frontend/src/routes/+layout.svelte
    - frontend/src/routes/+page.svelte
    - frontend/.gitignore
  modified:
    - app/main.py
decisions:
  - "2016-block windows used as era boundaries — technically precise, matches difficulty adjustment cycle"
  - "low_confidence flag for eras below height 321000 (pre-2015 orphan data less reliable)"
  - "vite bumped from ^5 to ^6 to satisfy @sveltejs/vite-plugin-svelte peer dependency in SvelteKit 2.53.4"
  - "src/app.html added (not in plan) — required SvelteKit root template missing from original scaffold spec"
metrics:
  duration: "~15 minutes"
  completed_date: "2026-03-10"
  tasks_completed: 2
  files_created: 9
  files_modified: 1
---

# Phase 5 Plan 1: Analytics API + SvelteKit Scaffold Summary

**One-liner:** Two FastAPI analytics endpoints (stale-rate-over-time, era-breakdown) plus a SvelteKit SPA scaffold with dark-mode CSS, static adapter, and Vite proxy to FastAPI.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add analytics endpoints to FastAPI | 2e48059 | app/routers/analytics.py, app/main.py |
| 2 | Create SvelteKit project scaffold | 1bdc1dc | frontend/ (9 files) |

## What Was Built

### Task 1: Analytics Endpoints

`app/routers/analytics.py` adds two endpoints consumed by the frontend analytics charts (Plans 04+):

- **GET /api/analytics/stale-rate-over-time?period=monthly|weekly**
  Groups blocks by SQLite `strftime('%Y-%m', timestamp)` or `strftime('%Y-W%W', timestamp)`. Returns list of `{period, canonical, orphaned, stale_rate}` sorted ascending. Empty list is valid for a fresh DB.

- **GET /api/analytics/era-breakdown**
  Groups by `height / 2016` (integer division = floor, matching Python `//`). Returns `{era, height_start, height_end, canonical, orphaned, stale_rate, low_confidence}` per era. `low_confidence: true` for all eras where `height_start < 321000`.

Both use `calculate_stale_rate()` from `app/analytics.py` for consistent formula application.

### Task 2: SvelteKit Scaffold

A complete SvelteKit SPA project at `frontend/`:

- **svelte.config.js**: adapter-static configured so `npm run build` outputs static files to `frontend/build/` — FastAPI will serve these in production
- **vite.config.ts**: dev server proxy routes `/api/*` to FastAPI at `localhost:8000`, so browser `fetch('/api/...')` works without CORS headers
- **src/app.html**: required root HTML template (SvelteKit will not build without this)
- **src/app.css**: CSS custom properties for dark-mode color palette
- **src/routes/+layout.svelte**: persistent header bar, imports global CSS
- **src/routes/+page.svelte**: single-page dashboard shell with four section placeholders for Plans 02-04

`npm run build` succeeds, producing `frontend/build/index.html`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated vite from ^5 to ^6**
- **Found during:** Task 2 (`npm install`)
- **Issue:** `@sveltejs/kit@2.53.4` (latest minor of ^2) depends on `@sveltejs/vite-plugin-svelte@6.x` which requires `vite@^6.3.0 || ^7.0.0`. The plan specified `vite@^5.0.0`.
- **Fix:** Updated `package.json` devDependency `vite` to `^6.0.0`
- **Files modified:** frontend/package.json
- **Impact:** No behavior change; Vite 6 is a minor update with no breaking changes for our usage

**2. [Rule 2 - Missing Required File] Added frontend/src/app.html**
- **Found during:** Task 2 (`npm run build`)
- **Issue:** SvelteKit requires `src/app.html` as the root HTML template that wraps every page. Without it, the build fails immediately with `Error: src\app.html does not exist`.
- **Fix:** Created standard SvelteKit `src/app.html` with `%sveltekit.head%` and `%sveltekit.body%` placeholders
- **Files created:** frontend/src/app.html
- **Impact:** Required for any SvelteKit project; the plan omitted it from the file list

## Self-Check: PASSED

- app/routers/analytics.py — FOUND
- frontend/package.json — FOUND
- frontend/src/routes/+page.svelte — FOUND
- frontend/build/index.html — FOUND
- 05-01-SUMMARY.md — FOUND
- Commit 2e48059 (Task 1) — FOUND
- Commit 1bdc1dc (Task 2) — FOUND
