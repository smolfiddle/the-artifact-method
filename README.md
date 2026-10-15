# The Artifact Method

An Agent Skill for spec-driven, human-orchestrated software development. It
teaches an agent to run a disciplined pipeline — contract first, one-shot
build, read-only audit swarms, design pass, solo deployment, device
acceptance, fix loop, release — where the human owns intent, contract,
sequencing, and gates while the agent owns the rest.

Proven case study: a signed, CI-backed, tested Android app shipped across
three tagged releases for under $2 in metered API cost (~5 human hours). Full
method document — cost ledger, failure taxonomy, open loops — is bundled at
`skills/the-artifact-method/references/The_Artifact_Method.md`; start there,
it opens with a TL;DR.

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
└── scripts/uitap.py                # Android device-test driver (adb + uiautomator)
```

## Using it in a new project

1. Put your specification file in the repo root.
2. Copy `assets/AGENTS.template.md` to the repo root as `AGENTS.md` and fill
   the placeholders (spec path, analyze/test/build commands).
3. Load the skill and give the one-line brief: *"create this application from
   the spec; do not push it yet."*

## Device driver (`scripts/uitap.py`)

A black-box UI driver for Android device acceptance (Stage 7). It talks to the
OS, not the app: `uiautomator dump` reads the accessibility tree, `input tap`
sends the tap.

- **Android-only, framework-agnostic.** Works with any app that exposes
  accessibility labels — Flutter, Jetpack Compose, native Views, React Native —
  and falls back to raw coordinates for canvas-only apps.
- **Requirements:** python3 and `adb` on PATH (Android platform-tools), plus a
  connected device or emulator. The skill itself has no runtime dependencies.
- **Known traps (hit in the case study):** label matching is substring-based
  ("Allow" matches the dialog *title* first — use coordinate taps for dialogs
  whose title contains the button word); the keyboard moves fields between dump
  and tap — re-dump after every keyboard transition.

Usage:

```bash
python3 scripts/uitap.py dump-labels             # list visible labels + bounds
python3 scripts/uitap.py tap "Save"              # tap center of first label match
python3 scripts/uitap.py tap 540 1926            # raw coordinate tap
python3 scripts/uitap.py wait "In your list"     # poll until visible (default 20 s)
python3 scripts/uitap.py find "Continue"         # print match or None
```

## License

MIT — see LICENSE. The bundled reference document describes one case study;
generality is asserted from mechanism, not yet from repetition.
