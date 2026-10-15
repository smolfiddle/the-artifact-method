# The Artifact Method

An Agent Skill for spec-driven, human-orchestrated software development. It
teaches an agent to run a disciplined pipeline — contract first, one-shot
build, read-only audit swarms, design pass, solo deployment, device
acceptance, fix loop, release — where the human owns intent, contract,
sequencing, and gates while the agent owns the rest.

Proven case study: a signed, CI-backed, tested Android app shipped across
three tagged releases for under $2 in metered API cost (~5 human hours). Full method
document, including the cost ledger, failure taxonomy, and open loops, is
bundled at `skills/the-artifact-method/references/The_Artifact_Method.md`.

## Install

```bash
npx skills add smolfiddle/the-artifact-method
```

Works with any Agent Skills compatible agent (opencode, Claude Code, Codex,
Cursor, Gemini CLI, and more). In opencode the skill is also invocable as
`/the-artifact-method`.

## What's inside

```
skills/the-artifact-method/
├── SKILL.md                        # the method, as an invocable skill
├── assets/AGENTS.template.md       # project governance — copy into each repo
├── references/The_Artifact_Method.md  # full v1.1 reference document
└── scripts/uitap.py                # adb + uiautomator device-test driver
```

## Using it in a new project

1. Put your specification file in the repo root.
2. Copy `assets/AGENTS.template.md` to the repo root as `AGENTS.md` and fill
   the placeholders (spec path, analyze/test/build commands).
3. Load the skill and give the one-line brief: *"create this application from
   the spec; do not push it yet."*

## License

MIT — see LICENSE. The bundled reference document describes one case study;
generality is asserted from mechanism, not yet from repetition.
