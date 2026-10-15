# The Artifact Method

The Artifact Method (TAM) is a development pipeline for shipping real software
with AI agents while a human owns the decisions that matter. The human defines
intent, freezes a written specification, decides what happens next, and guards
the gates. Agents do the implementation, the audits, the deployment mechanics,
and the device testing.

**Start here: read [The_Artifact_Method.md](The_Artifact_Method.md).** That file
is the full reference: pipeline stages, the seven laws, the failure taxonomy,
the cost ledger, and an honest list of open loops. It opens with a TL;DR.
`SKILL.md` is the operational digest that agents load; the reference document is
the source those instructions come from.

## What it gives you

- A stage order that works: contract, one-shot build, hands-on triage, two
  read-only audit swarms, design pass, solo deployment, device acceptance,
  fix loop, re-release.
- Topology rules: parallel agents for reading, one context for stateful or
  irreversible work such as deployments, releases, and secrets.
- Gate discipline: verification at checkpoints (analyzer, tests, pre-push
  sweep, CI, device run), not per-finding review.
- Reusable briefs: short prompts that point at artifacts instead of carrying
  context themselves.

## Scope

Exercised today on Android mobile apps built with Flutter. That is the path
the case study covers and the one the bundled device driver was proven on.
The method and the driver are framework-agnostic by design (accessibility
labels with a coordinate fallback), and the intent is to broaden the skill
to iOS and other stacks as new case studies are run.

## Install

```bash
npx skills add smolfiddle/the-artifact-method
```

Works with any Agent Skills compatible agent (opencode, Claude Code, Codex,
Cursor, Gemini CLI, and more). In opencode the skill is also invocable as
`/the-artifact-method`. Manual install: copy this whole folder into your
agent's skills directory, for example `.agents/skills/the-artifact-method/`
for a project or `~/.config/opencode/skills/the-artifact-method/` for opencode
global. Zips are attached to the releases.

## What's inside

| Path | Purpose |
|---|---|
| `The_Artifact_Method.md` | Full reference (v1.1). Read this first. |
| `SKILL.md` | The method as an invocable skill: stages, laws, gates, briefs |
| `assets/AGENTS.template.md` | Project governance template. Copy into each repo as `AGENTS.md` and fill the placeholders. |
| `scripts/uitap.py` | Android device-test driver (adb plus uiautomator). Details below. |

## Using it in a new project

1. Put your specification file in the repo root. The spec is the asset.
2. Copy `assets/AGENTS.template.md` to the repo root as `AGENTS.md` and fill
   the placeholders: spec path, analyze command, test command, build command.
3. Load the skill and give the one-line brief: *"create this application from
   the spec; do not push it yet."*

Then follow the pipeline in the reference. Every stage ends at a gate, and the
release loop repeats until the acceptance criteria pass on a device.

## Device driver (`scripts/uitap.py`)

Black-box UI driver for Android device acceptance (stage 7). It talks to the
OS, not to the app: `uiautomator dump` reads the accessibility tree, and
`input tap` sends taps.

- Android only, framework agnostic. Works with any app that exposes
  accessibility labels: Flutter, Jetpack Compose, native Views, React Native.
  Falls back to raw coordinates for canvas only apps.
- Requirements: python3 and `adb` on PATH (Android platform tools), plus a
  connected device or emulator. The skill itself has no runtime dependencies.
- Known traps from the case study: label matching is substring based, so a tap
  on "Allow" can hit the dialog title first; use coordinate taps for dialogs
  whose title contains the button word. The keyboard moves fields between dump
  and tap, so re-dump after every keyboard transition.

Usage:

```bash
python3 scripts/uitap.py dump-labels             # list visible labels and bounds
python3 scripts/uitap.py tap "Save"              # tap center of first label match
python3 scripts/uitap.py tap 540 1926            # raw coordinate tap
python3 scripts/uitap.py wait "In your list"     # poll until visible (default 20 s)
python3 scripts/uitap.py find "Continue"         # print match or None
```

## Case study

The reference is built from one complete build:
[MangaCat](https://github.com/smolfiddle/MangaCat), a signed, CI backed, tested
Android app shipped across three released versions for a metered total of
¥7.76 (~$1.15) in API cost and roughly five human hours, including device
acceptance with a screenshot evidence bundle. The document states plainly
where the method is proven and where it is not.

## License

MIT, see [LICENSE](LICENSE).
