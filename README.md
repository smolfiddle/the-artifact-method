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

## Requirements

The skill itself is plain markdown: no runtime, no dependencies. It works with
any Agent Skills compatible agent.

For the device driver (`scripts/uitap.py`, the Android acceptance step):

- python3 3.9 or newer
- `adb` on PATH (Android platform tools), or the `ADB` environment variable
  pointing at the binary
- a connected Android device or a running emulator

Optional: mobile-mcp wired into the agent for the richer interactive path
(config snippet in SKILL.md).

For replicating the full pipeline on the case-study stack, a git host and
GitHub Actions are useful but not required; every other step runs locally.

## What's inside

| Path | Purpose |
|---|---|
| `The_Artifact_Method.md` | Full reference (v1.1). Read this first. |
| `SKILL.md` | The method as an invocable skill: stages, laws, gates, briefs |
| `assets/AGENTS.template.md` | Project governance template. Copy into each repo as `AGENTS.md` and fill the placeholders. |
| `scripts/uitap.py` | Android device-test driver (adb plus uiautomator). Details below. |

## Using it in a new project

1. Create the spec with the Stage 0 loop: put your idea, and this repo's
   `The_Artifact_Method.md`, into a web AI chat; answer rounds of about 30
   forced-choice questions until new questions stop (the case study used 75
   across four rounds); then ask the AI to draft the spec against the Stage 1
   structure.
2. Put the specification file in the repo root. The spec is the asset.
3. Copy `assets/AGENTS.template.md` to the repo root as `AGENTS.md` and fill
   the placeholders: spec path, analyze command, test command, build command.
4. Load the skill and give the one-line brief: *"create this application from
   the spec; do not push it yet."*

Then follow the pipeline in the reference. Every stage ends at a gate, and the
release loop repeats until the acceptance criteria pass on a device.

## Device driver (`scripts/uitap.py`)

Black-box UI driver for Android device acceptance (stage 7). It talks to the
OS, not to the app: `uiautomator dump` reads the accessibility tree, and
`input tap` sends taps. One file, python3 plus adb only.

- Android only, framework agnostic. Works with any app that exposes
  accessibility labels: Flutter, Jetpack Compose, native Views, React Native.
  Falls back to raw coordinates for canvas only apps. Setup is covered in
  Requirements above.
- Selectors: substring by default, plus `--exact`, `--regex`, `--id`,
  `--package`, `--nth`, and position ordering (`--topmost`, `--bottommost`,
  `--leftmost`, `--rightmost`).
- Reliability: taps land on the nearest clickable ancestor (the labeled node is
  often not the one that accepts the tap), `--retry` for animated screens,
  `--dry-run` to author safely, `--expect` to assert the next screen, transient
  uiautomator errors tolerated while polling, and gestures hide the open
  keyboard first (opt out with `--no-hide-ime` on swipe and scroll-to;
  device-level failures like offline devices fail fast instead of
  polling to timeout).
- Exit codes: 0 hit or success, 1 miss or timeout, 2 device or usage error.
- Traps found in testing: label matching is substring based, so a tap on
  "Allow" can hit the dialog title first (use `--exact` or coordinates); the
  keyboard moves fields between dump and tap, so re-dump after transitions; the
  first keystroke after a navigation can be swallowed during the focus change,
  so `text --into` now taps and waits for the screen to settle before typing
  (opt out with `--no-settle`); multi-line labels are normalized to
  single spaces, so "#1 Solo" matches a row rendered across lines; `%s`
  is the device-side space token, so literal `%s` input is typed by
  segmenting it, and `--exact` with `--regex` is rejected up front.

Usage:

```bash
python3 scripts/uitap.py dump-labels                    # all labeled nodes
python3 scripts/uitap.py dump-labels --json             # machine readable
python3 scripts/uitap.py find "Save" --exact            # exit 1 on miss
python3 scripts/uitap.py find "#1" --topmost --json     # ordered, structured
python3 scripts/uitap.py tap "Unlock" --expect "MangaCat.csv"
python3 scripts/uitap.py tap "Save" --retry 3
python3 scripts/uitap.py wait-gone "Loading"
python3 scripts/uitap.py wait-stable --save tree.xml
python3 scripts/uitap.py scroll-to "Series Two" --max 4
python3 scripts/uitap.py text --into "Search title or artist" --clear "solo"
python3 scripts/uitap.py text --into "Search title or artist" --no-settle "solo"
python3 scripts/uitap.py clear
python3 scripts/uitap.py key BACK
python3 scripts/uitap.py swipe up --distance 900
python3 scripts/uitap.py shot 07_tracker
python3 scripts/uitap.py -s emulator-5554 --verbose find "In your list"
```

## Case study

The reference is built from one complete build:
[MangaCat](https://github.com/smolfiddle/MangaCat), a signed, CI backed, tested
Android app shipped across three released versions, the first two feature
cycles metered at ¥7.76 (~$1.15) in API cost and roughly five human hours,
including device acceptance with a screenshot evidence bundle. The third
release was a documentation pass. The document states plainly
where the method is proven and where it is not.

## Support

Maintained by one author, in the open. Issues, reviews, and pull requests
are welcome; response times are best-effort. The reference document states
plainly where the method is proven and where it is not, so treat its open
loops as the current boundary.

## License

MIT, see [LICENSE](LICENSE).
