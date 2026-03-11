# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Developer Context

The developer is a new grad transitioning from a physics background into software engineering. Strong Python foundation, limited experience with web backends and frontends. The goal is to ship a real project while building genuine understanding — not just getting code to run.

This means:

- **Explain the "why" behind decisions**, not just the "what". When a pattern is used (e.g., lifespan context manager, dependency injection, background threads), briefly note why it exists and what problem it solves.
- **Call out when something is a professional convention** vs a project-specific choice. New grads benefit from knowing what they'd see at any job vs what's specific to this codebase.
- **Don't hide complexity** — if something is genuinely tricky (async, thread safety, database sessions), say so and explain it clearly rather than abstracting it away silently.
- **Frontend and backend concepts are both new territory** — when introducing web concepts (HTTP, REST, SSE, WebSockets, routing), give a one-line orienting comment so the developer knows what they're looking at.

## Development Style

This project is a learning environment. Code should be written the way it would appear in a professional codebase.

Claude should prioritize:

- clean, readable code
- clear function and variable names
- small focused functions
- modular design
- maintainability over cleverness

Avoid overly complex solutions or unnecessary abstractions.

When introducing new concepts, briefly explain the reasoning so the developer can learn from the implementation.

Prefer simple architectures and implement features incrementally.