# ADR-0004: The hub uses only the standard library

## Status
Proposed (depends on the owner approving the portfolio scope, EXTENSION_PLAN.md section 0)

## Date
2026-10-20

## Context
The planned local web hub (`ic_hub`, v2.2) sits on top of the same pipeline. The project's dependency story
is stdlib plus scikit-learn, with no web framework and no packaging beyond requirements.txt.

## Decision
`ic_hub` would use stdlib `http.server`, vanilla JS and 127.0.0.1 only. It imports `incident_commander` and
`ic_plus`; neither imports it. Dev-only tools (coverage, mypy, pip-audit, bandit) are never imported by code.

## Alternatives considered
- Flask or FastAPI: rejected. They add a dependency and a larger attack surface for a local demo.
- No hub, CLI only: remains the fallback if the portfolio scope is not approved.

## Consequences
Nothing new to install and the purity gate keeps its meaning. The hub must implement its own safety checks
(Host, Origin, token, size bounds, text-only rendering, CSP), listed in docs/EXTENSION_PLAN.md.
