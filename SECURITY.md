# Security Policy

Incident Commander is a coursework and portfolio project that runs over simulated data. It has no production
deployment, no user accounts and no stored incident data.

## Reporting a vulnerability

Please report problems privately instead of opening a public issue: email sohanroy676@gmail.com with a short
description and the steps to reproduce. Expect a reply within about a week; this is a solo project.

## Scope

- In scope: the code in `incident_commander/` and `ic_plus/`, the CI workflow, and any secret that could leak
  through traces, logs or the repository.
- Out of scope: the simulated fixtures, and the quality of an LLM's free-text narrative. That text is labelled and
  never read by a decision.

## Design notes that matter for security

- `incident_commander/` reads no environment variables, no keys and no network. It never imports `ic_plus`.
- Decisions use typed evidence only. Log text and LLM output never change a decision (see the planted-log attack
  in `python -m incident_commander evaluate`).
- LLM keys live only in `.env` (gitignored; `.env.example` has no values). The extension never prints, logs or
  traces a key, and the LLM client scrubs it from error text.
- CI runs `pip-audit` on `requirements.txt` and `bandit` (high severity gates the build). Known low and medium
  bandit findings are listed in `.github/workflows/ci.yml`.

## Supported versions

Only the latest release on `main` is supported.
