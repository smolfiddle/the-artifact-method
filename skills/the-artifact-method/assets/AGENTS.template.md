# <PROJECT> — Agent Rules (The Artifact Method)

The specification file `<SPEC_FILE>` is the source of truth. Read it before any
implementation work. If reality contradicts it, stop and ask — spec amendments
are deliberate and attributed, never silent.

## Non-negotiables

- **Analyzer loop.** Run `<ANALYZE_CMD>` after every few files. Zero issues
  before continuing. Report analyzer output verbatim, never summarized away.
- **Tests before push.** Run `<TEST_CMD>` fully green before any push. Never
  push a red tree.
- **Never push without being asked.** Commit locally at stage completion;
  pushing, tagging, and releasing are human gates.
- **Never commit secrets.** No signing material, keys, tokens, or
  `key.properties`-style files. Verify with a secret/ignore audit before push.
- **Fix, don't feature-add.** During defect rounds, change only what the defect
  requires. Scope changes go back to the spec and the human.
- **Claims need receipts.** Every "done" or "fixed" carries evidence: command
  output, test results, screenshots, checksums.

## Commands

- Analyze: `<ANALYZE_CMD>`
- Test: `<TEST_CMD>`
- Build: `<BUILD_CMD>`
- Run/lint/format: `<OTHER_CMDS>`

## Workflow expectations

- Follow the stage order: correctness before design, design before deploy,
  deploy before device test, device test before release.
- Topology: parallel read-only subagents for audits; single context for
  sequential, stateful, or irreversible work (deployments, releases, secrets).
- Keep prompts as pointers. Context belongs in files: this spec, this AGENTS.md,
  committed docs — not in chat.
- Prefer small, honest commits with conventional messages.

## Device/UI work (if applicable)

- Prefer black-box verification on an emulator/device when the change is
  user-visible.
- Capture evidence: screenshots for each flow, raw outputs the app produced.
- Distinguish harness artifacts (driver bugs, accessibility quirks) from app
  defects before "fixing" anything.

## Permissions (if the harness supports allowlists)

- Allow: build, test, analyze, format, read-only inspection.
- Ask: network access, installing tools, anything destructive to user files.
- Deny: writing outside the project, touching credentials or signing material.

## Open loops

Maintain a short honest list in the README or release notes: what was not
tested, not metered, or not secured yet. Do not silently drop known gaps.
