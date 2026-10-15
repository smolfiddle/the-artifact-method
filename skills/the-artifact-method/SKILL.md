---
name: the-artifact-method
description: Spec-driven, human-orchestrated development pipeline called The Artifact Method (TAM). Use when the user asks to build an app from a specification file, run TAM stages (elicitation, contract, one-shot build, audit swarm, design pass, deployment, device acceptance, fix loop, release), or mentions "Artifact Method", "TAM", "spec-first build", "audit swarm", "design swarm", "gate discipline", or "swarm vs solo". Also use when helping create a project's spec, AGENTS.md, release workflow, or device-test evidence for a TAM project. Do not use for ordinary one-off coding tasks outside a spec-driven pipeline.
compatibility: opencode, claude-code, codex, cursor
license: MIT
metadata:
  audience: artifact-authors
  workflow: spec-driven
  opencode/slash: "true"
---

# The Artifact Method (TAM)

A complete development lifecycle where a human who does not write most of the
code ships production-grade software by owning four things exclusively:

1. **Intent** — what should exist and why (elicited, not assumed)
2. **Contract** — a normative specification that is the single source of truth
3. **Sequencing** — what happens next, in what order, with what topology
4. **Gates** — checkpoints where work is verified before it advances

Core claim: **a clear enough contract makes implementation a commodity.** The
human's value concentrates at stage boundaries and gates, not in writing code.

Full reference: `references/The_Artifact_Method.md` in this skill folder.

## Pipeline (one phase per shipped version; the loop is mandatory)

| Stage | Name | Actor | Output |
|---|---|---|---|
| 0 | Elicitation | Human + AI interview | Numbered decision log |
| 1 | Contract | AI drafts, human freezes | Normative spec + acceptance criteria |
| 2 | One-shot build | Builder (main context) | Working app, committed locally, never pushed yet |
| 3 | Hiccup triage | Human uses the app | Obvious defects fixed, no scope growth |
| 4 | Audit swarm | 2 read-only subagents (correctness) | Findings → fix round |
| 5 | Design swarm | 2 read-only subagents (aesthetics) | Findings → polish round |
| 6 | Solo ship | Main context | Signed artifacts, CI, README, license, release vN |
| 6b | Tooling bind | Main context | Device bridge (mobile-mcp) or adb driver |
| 7 | Device test | Harness + human | Black-box acceptance + evidence bundle |
| 8 | Fix loop | Main context | Diagnosed + fixed defects, re-verified |
| 9 | Re-release | Main context | Version bump, tag, CI release, notes |

Gates: pre-push sweep (analyze + tests + secret audit) · CI gate on every
push/PR · release CI (signed, idempotent) · integrity chain (checksums
re-verified by download) · human acceptance.

## Laws

1. Context Law — swarm for read-mostly analysis; solo for stateful,
   irreversible work (deploy, release, secrets).
2. Sequencing Law — correctness → design → deploy → test → fix → re-release.
   Never polish pre-audit code.
3. Gate Law — auto-accept agent output only when gates are strong. A gate only
   covers the failure classes it was built for; check coverage first.
4. Artifact Law — context lives in files (spec, AGENTS.md, skills). A prompt
   longer than two sentences is a smell.
5. Freeze Law — spec frozen before build; amendments deliberate and attributed.
6. Stop Law — a stage ends when its axis is settled, not when output stops.
7. Ownership Law — the human owns product decisions: brand, license, scope,
   acceptance.

## Briefs (reuse verbatim shape; keep them short)

- One-shot: "create this application from <SPEC>; do not push it yet"
- Audit swarm: "scan the codebase for anomalies/bugs/needed adjustments; use 2
  read-only subagents"
- Design swarm: "review the design/UI/UX for where it can be better overall;
  use subagents"
- Device test: "start testing the app"
- Fix: "diagnose and fix it" (with the user-observed symptom)
- Release: "bump to <version>, create a release with description notes, attach
  debug and test evidence too"

## Starting a new TAM project

1. Put the spec file in the repo root (and keep it there — it is the asset).
2. Copy `assets/AGENTS.template.md` from this skill folder to the repo root as
   `AGENTS.md`; fill the placeholders (spec path, analyze/test/build commands).
3. Load this skill; issue the one-shot brief.
4. Never ship the first artifact. Never push until the pre-push sweep passes.

## Gates & evidence rules

- Zero-issue static analysis is a precondition, not a goal.
- No claim without a receipt: analyzer output, test output, screenshot,
  checksum. "It works" is not evidence.
- Evidence bundle for device runs: numbered screenshots per flow, a test-notes
  table, raw outputs the app produced (e.g. saved files, byte-verified).
- Distinguish app defects from harness artifacts before fixing anything.
- Record open loops honestly (what was not tested, not metered, not secured).

## Device bridge (optional, lean)

mobile-mcp (Mobile Next) via opencode `mcp` config; pinned version, telemetry
off, timeout raised for npx cold start:

```json
"mcp": {
  "mobile-mcp": {
    "type": "local",
    "command": ["npx", "-y", "@mobilenext/mobile-mcp@1.0.11"],
    "environment": { "MOBILEMCP_DISABLE_TELEMETRY": "1" },
    "enabled": true,
    "timeout": 20000
  }
}
```

Fallback bundled in this skill: `scripts/uitap.py` — an adb + uiautomator
label-tap driver that needs nothing but adb.

MCP tools load at session start — restart the agent after wiring. Fallback that
needs nothing: adb + uiautomator driver (dump tree, match label, tap center).

## What NOT to do

- Do not skip Stage 3 or 7 — only hands prove behavior.
- Do not auto-accept unless a gate covers that failure class.
- Do not put the spec, decisions, or process in chat prompts — artifacts.
- Do not release without the signing-identity ceremony (keystore backup,
  secrets, checksum verification).
- Do not expand scope inside fix rounds.
