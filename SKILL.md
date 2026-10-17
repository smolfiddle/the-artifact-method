---
name: the-artifact-method
description: Spec-driven, human-orchestrated development pipeline called The Artifact Method (TAM). Use when the user asks to build an app from a specification file, run TAM stages (elicitation, contract, one-shot build, audit swarm, design pass, deployment, device acceptance, fix loop, release), or mentions "Artifact Method", "TAM", "spec-first build", "audit swarm", "design swarm", "gate discipline", or "swarm vs solo". Also use when helping create a project's spec, AGENTS.md, release workflow, or device-test evidence for a TAM project. Do not use for ordinary one-off coding tasks outside a spec-driven pipeline.
compatibility: opencode, claude-code, codex, cursor
license: MIT
metadata:
  audience: artifact-authors
  workflow: spec-driven
  version: 0.3.0
  opencode/slash: "true"
---

# The Artifact Method (TAM)

A complete development lifecycle where a human who does not write most of the
code ships production-grade software by owning four things exclusively:

1. **Intent**: what should exist and why (elicited, not assumed)
2. **Contract**: a normative specification that is the single source of truth
3. **Sequencing**: what happens next, in what order, with what topology
4. **Gates**: checkpoints where work is verified before it advances

Core claim: **a clear enough contract makes implementation a commodity.** The
human's value concentrates at stage boundaries and gates, not in writing code.

**Reference, not required reading:** `The_Artifact_Method.md`, next to this
file, is the full method document, written for the human Artifact Author:
rationale, case-study evidence, cost ledger, failure taxonomy, open loops.
This file (SKILL.md) is the operational contract for agents. Consult the
reference on demand: when planning a project's pipeline, when a gate or
auto-accept decision is contested, when diagnosing a failure class, or when
the human asks for the full method. Do not load it for routine stage work.

**Scope today:** the exercised path is Android mobile apps built with Flutter.
Web acceptance is exercised at driver level through the bundled Playwright
driver (`scripts/webtap.py`), not yet on a shipped web product. The method and
both drivers are framework-agnostic by design (accessibility-tree driven, with
a coordinate fallback), but iOS and other stacks have not been tested. The
skill is intended to broaden as new case studies are run; treat the current
tooling as Android plus web.

## Pipeline (one phase per shipped version; the loop is mandatory)

| Stage | Name | Actor | Output |
|---|---|---|---|
| 0 | Elicitation | Human + web AI interview | Decision log, then a drafted spec |
| 1 | Contract | AI drafts, human freezes | Normative spec + acceptance criteria |
| 2 | One-shot build | Builder (main context) | Working app, committed locally, never pushed yet |
| 3 | Hiccup triage | Human uses the app | Obvious defects fixed, no scope growth |
| 4 | Audit swarm | 2 read-only subagents (correctness) | Findings → fix round |
| 5 | Design swarm | 2 read-only subagents (aesthetics) | Findings → polish round |
| 6 | Solo ship | Main context | Signed artifacts, CI, README, license, release vN |
| 6b | Tooling bind | Main context | Target bridge: mobile-mcp, adb driver, or Playwright web driver |
| 7 | Target test | Harness + human | Black-box acceptance + evidence bundle |
| 8 | Fix loop | Main context | Diagnosed + fixed defects, re-verified |
| 9 | Re-release | Main context | Version bump, tag, CI release, notes |

Gates: pre-push sweep (analyze + tests + secret audit) · CI gate on every
push/PR · release CI (signed, idempotent) · integrity chain (checksums
re-verified by download) · human acceptance.

## Laws

1. Context Law: swarm for read-mostly analysis; solo for stateful,
   irreversible work (deploy, release, secrets). If the harness has no
   subagents, run the audit and design passes sequentially in one context
   and say so; the law is about mutex safety, not agent count.
2. Sequencing Law: correctness → design → deploy → test → fix → re-release.
   Never polish pre-audit code.
3. Gate Law: auto-accept agent output only when gates are strong. A gate only
   covers the failure classes it was built for; check coverage first.
4. Artifact Law: context lives in files (spec, AGENTS.md, skills). A prompt
   longer than two sentences is a smell.
5. Freeze Law: spec frozen before build; amendments deliberate and attributed.
6. Stop Law: a stage ends when its axis is settled, not when output stops.
7. Ownership Law: the human owns product decisions: brand, license, scope,
   acceptance.

## Briefs (reuse verbatim shape; keep them short)

- Elicitation (web AI chat): "Here is my idea: <idea>. Ask me about 30
  forced-choice questions, each with an expert-default option. Keep asking
  new rounds until you run out." Then: "Using The_Artifact_Method.md as the
  template, draft the specification."
- One-shot: "create this application from <SPEC>; do not push it yet"
- Audit swarm: "scan the codebase for anomalies/bugs/needed adjustments; use 2
  read-only subagents"
- Design swarm: "review the design/UI/UX for where it can be better overall;
  use subagents"
- Target test: "start testing the app"
- Fix: "diagnose and fix it" (with the user-observed symptom)
- Release: "bump to <version>, create a release with description notes, attach
  debug and test evidence too"

## Starting a new TAM project

1. Create the spec with the Stage 0 loop: seed the idea, and this repo's
   The_Artifact_Method.md, into a web AI chat; answer rounds of about 30
   forced-choice questions until new questions stop; then have the AI draft
   the spec against the Stage 1 structure.
2. Put the spec file in the repo root (and keep it there, it is the asset).
3. Copy `assets/AGENTS.template.md` from this skill folder to the repo root as
   `AGENTS.md`; fill the placeholders (spec path, analyze/test/build commands).
4. Load this skill; issue the one-shot brief.
5. Never ship the first artifact. Never push until the pre-push sweep passes.

## Gates & evidence rules

- Zero-issue static analysis is a precondition, not a goal.
- No claim without a receipt: analyzer output, test output, screenshot,
  checksum. "It works" is not evidence.
- Evidence bundle for device runs: numbered screenshots per flow, a test-notes
  table, raw outputs the app produced (e.g. saved files, byte-verified).
- Distinguish app defects from harness artifacts before fixing anything.
- CLI projects: no device profile; the evidence bundle is golden files, an
  exit-code table, and TEST_NOTES.md.
- Record open loops honestly (what was not tested, not metered, not secured).

## Target bridge (optional, lean)

For Android, mobile-mcp (Mobile Next) via opencode `mcp` config; pinned
version, telemetry off, timeout raised for npx cold start:

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

MCP tools load at session start, restart the agent after wiring.

Fallback bundled in this skill: `scripts/uitap.py`, an adb + uiautomator
device driver. Verbs: dump-labels, find, tap, wait, wait-gone, wait-stable,
scroll-to, text (--into, --clear), clear, key, swipe, shot, screen, selftest,
version. Selectors: substring, --exact, --regex, --id, --package, --nth, and
position ordering (--topmost, --bottommost, --leftmost, --rightmost).
Reliability: taps land on the nearest clickable ancestor, --retry and
--dry-run, --expect assertions after a tap, transient-error tolerance while
polling, and gestures hide the open keyboard first. Globals: -s, --verbose,
--log, --json. Exit codes: 0 hit, 1 miss or timeout, 2 device or usage error.
Android-only and framework-agnostic: works with any app that exposes
accessibility labels (Flutter, Compose, native Views, React Native) and falls
back to raw-coordinate taps for canvas-only apps. Needs python3 and adb on
PATH.

Web targets use `scripts/webtap.py` (v0.1.0, bundled since skill v0.3.0),
the Playwright counterpart with the same contract (single file, argparse,
exit codes 0/1/2). Verbs mirror uitap.py (dump-labels, find, tap, wait,
wait-gone, wait-stable, scroll-to, text, clear, key, shot, screen, selftest,
version) and add web-only ones: goto, url, title, console, network, flow.
Selectors: accessible-name substring, --exact, --regex, --case-sensitive,
--role, --id (CSS), --within, --nth, position ordering. Strict mode: multiple
matches are a miss unless --nth or a position flag narrows them. The session
is stateless per command with a storage-state file (.webtap/state.json); DOM
commands reopen the last visited URL automatically, and in-memory page state
(form fields, JS variables) does not survive between commands, so use
`flow <file.json>` for multi-step acceptance: one browser, per-step evidence
under .webtap/evidence/, first non-zero step aborts. Needs python3 3.9+ and
`pip install playwright && playwright install chromium`. `.webtap/` holds
credential-adjacent state: gitignore it in target projects.

## What NOT to do

- Do not skip Stage 3 or 7, only hands prove behavior.
- Do not auto-accept unless a gate covers that failure class.
- Do not put the spec, decisions, or process in chat prompts, artifacts.
- Do not release without the signing-identity ceremony (keystore backup,
  secrets, checksum verification).
- Do not expand scope inside fix rounds.
