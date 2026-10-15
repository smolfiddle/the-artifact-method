# The Artifact Method
## A Working Reference for Spec-Driven, Human-Orchestrated AI Software Development

**Version:** 1.1 | **Date:** 2026-10-15 | **Case study:** MangaCat (github.com/smolfiddle/MangaCat), releases v0.0.1 and v0.0.2
**Author role:** The practitioner is referred to throughout as the **Artifact Author**.

---

## TL;DR

> A human who does not write most of the code ships production-grade software by
> owning exactly four things: **intent** (what and why), **contract** (a frozen
> spec), **sequencing** (what runs in what order, with what topology), and **gates**
> (where work is verified). Everything else is delegated to AI agents.
>
> **Pipeline:** elicit decisions → freeze spec → one-shot build → hands-on triage
> → two read-only audit swarms (correctness, then design) → solo ship → bind a
> device bridge → black-box device test with an evidence bundle → fix loop →
> re-release. The pipeline is a loop; defects after shipping re-enter at fix.
>
> **Laws that do the work:** swarms for reading, solo for shipping; never polish
> pre-audit code; auto-accept only what a gate covers; context lives in files, not
> prompts; the human owns every decision with no deterministic answer.
>
> **Evidence:** one real app (MangaCat) shipped across three tagged releases , 
> signed artifacts, CI, 41 tests, device acceptance with 31 screenshots, for
> ¥7.76 (~$1.15) metered API cost and roughly five human hours.
>
> **Limits, honestly:** one case study, a spec-completable domain; no security
> audit axis yet; auto-accept still a judgment call. See §13.
>
> **Map:** §4 pipeline · §5 stages · §6 laws · §7 failure taxonomy · §11 costs ·
> §13 open loops · §14 fact ledger.

---

## 1. What This Method Is

The Artifact Method is a complete software development lifecycle in which a human
who does not write most of the code ships production-grade software by owning four
things exclusively:

1. **Intent**: what should exist and why (elicited, not assumed)
2. **Contract**: a normative specification that is the single source of truth
3. **Sequencing**: what happens next, in what order, with what topology
4. **Gates**: the checkpoints at which work is verified before it advances

Everything else, implementation, review passes, deployment mechanics, tooling
evaluation, device testing, polish, is delegated to AI agents. The method's core
claim, empirically exercised on 2026-10-14/15 across two full release cycles of
the MangaCat build:

> **A clear enough contract makes implementation a commodity. The residual human
> value concentrates at stage boundaries and verification gates, not in the
> writing of code.**

**MangaCat ledger (the evidentiary basis of this document):**

Phase 1, v0.0.1:
~1 hour of specification conversation → one evening of build time → 16 commits
total across the project (13 in the initial arc) → a signed, CI-backed,
MIT-licensed, publicly released Android application → API spend ¥4.04 (~$0.60)
for this phase, metered.

Phase 2, v0.0.2 (testing, tooling, and the fix loop):
device-test tooling evaluated and bound (mobile-mcp), full black-box device
acceptance executed, one user-reported defect diagnosed and fixed, second signed
release published with evidence artifacts → Phase 2 API spend ¥3.72, derived
from the overall project meter of ¥7.76 (464 requests, 118,112,557 tokens)
minus Phase 1 (provider dashboard; see §11).

Every number in this document traces to a commit hash, a CI run ID, or a release
URL recorded in §14 (Fact Ledger).

---

## 2. Philosophy

1. **Spec first, code second, always.** The specification is the durable asset;
   code is a regenerable byproduct of the spec.
2. **Artifacts carry context; prompts point at them.** Never write a long prompt
   when a file can hold the context. The prompt is a pointer, the artifact is
   the semantics.
3. **Truth before beauty.** Correctness stages precede design stages. Never
   polish surfaces that may still change.
4. **Swarms for breadth, solo for depth.** Parallel agents for independent,
   read-mostly analysis; a single context for sequential, stateful, irreversible work.
5. **Verify at gates, not per-finding.** Auto-accept agent output when, and only
   when, a cheap, strong verification gate stands behind it. Confidence to
   auto-accept is purchased upstream by gate quality.
6. **The human decides what to do next; agents decide how.** Every decision that
   lacks a deterministic answer is human-owned. Every task that has one is delegated.
7. **Reality adjudicates the spec, not the author.** Post-ship defects are spec
   deltas waiting to be written. The pipeline is cyclic, not terminal (§4).

---

## 3. Roles

| Role | Actor | Owns |
|---|---|---|
| **Oracle** | Human | Preferences, tradeoffs, the "whatever is best" delegations, final acceptance |
| **Scribe** | AI (interviewer) | Elicitation, forced-choice questions, expert-default proposals, spec drafting |
| **Builder** | AI agent (main context) | One-shot generation, sequential fixes, deployment, tooling, polish |
| **Swarm** | AI subagents (2+ parallel) | Read-mostly audits: correctness and design critique |
| **Harness** | AI tooling + device tooling | `analyze`/tests, pre-push sweep, CI workflows, MCP device bridge, black-box device runs |
| **Gate** | Human + AI tooling | Accept/reject checkpoints; only hands prove behavior |

---

## 4. The Pipeline

The pipeline is **cyclic**: every release that surfaces a defect re-enters at the
fix stage and exits through release again. The MangaCat run executed stages 0–9
plus one full loop on 2026-10-15.

```
PHASE (one per shipped version)

STAGE 0  Elicitation     Human ⇄ AI interview → decision log
STAGE 1  Contract        Normative spec with acceptance criteria
STAGE 2  One-shot        Builder generates the entire app
STAGE 3  Hiccup triage   Human uses the app; obvious defects fixed
STAGE 4  Audit swarm     2 subagents, read-only, correctness axis
STAGE 5  Design swarm    2 subagents, UI/UX/taste axis
STAGE 6  Solo ship       Deployment, CI, branding, license, release vX
STAGE 6b Tooling bind    Device-test harness selected and wired (MCP/adb)
STAGE 7  Device test     Black-box acceptance on emulator/device; evidence captured
STAGE 8  Fix loop        Defects → diagnosis → fix → re-verify (back to 7 if needed)
STAGE 9  Re-release      Version bump, tag, CI artifacts, release notes, evidence bundle

GATES (cross-cutting)
  Pre-push sweep   zero-issue analyze, full test suite, secret/gitignore audit
  CI gate          analyze + tests on every push/PR
  Release CI       signed artifacts, idempotent release creation
  Integrity chain  published SHA-256 re-verified against the uploaded artifact
```

Stages 4, 5, and 7 are **swarm/harness rounds**; stages 6, 6b, 8, and 9 are
**solo** (stateful, irreversible, credential-adjacent).

---

## 5. Stage Specifications

### Stage 0, Elicitation
- Interview in **rounds of forced-choice questions** (the MangaCat elicitation
  used 75 questions across 4 rounds of 30/30/10/5, per the practitioner's log).
- Every question offers an **expert-default escape hatch** ("whatever is best").
  The Oracle answers with preferences where taste matters and delegates where it
  does not. This separates *preference* from *expertise* and merges them into one
  decision log.
- Group questions by concern: usage, data model, file behavior, UI, platform,
  privacy, future-proofing.
- The interviewer's job is to surface contradictions in the Oracle's answers
  (e.g., "keep it simple" vs. "series tracker with all the shebang", resolved
  via a simple/advanced mode toggle).
- **Output:** a numbered decision log. Every later stage traces authority to it.

### Stage 1, The Contract (Normative Specification)
The spec must contain, at minimum:
- Goals and **explicit non-goals** (scope discipline is a feature list of refusals)
- Data model with field-level detail (types, limits, defaults)
- Normative format rules written in *must* language (e.g., "UTF-8, comma-delimited,
  RFC 4180 quoting, CRLF" (MangaCat Specification §5.2))
- An **error-handling matrix**: scenario → detection → behavior
- Architecture sketch and storage model
- A **locked decisions log** (the "whatever is best" resolutions, attributed)
- **Acceptance criteria**: a numbered, pass/fail checklist written *before* code
  exists. This is the contract's enforcement clause and the final gate's script.
- Performance targets and visual design tokens (hex values, spacing, type scale)

**Rule:** the spec is frozen before Stage 2. If reality contradicts it during
the build, the spec is amended deliberately, never silently. Recorded amendment
in this case: the application package was changed from the draft (`ph.jjjardev.*`
to `ph.smolfiddle.mangacat`) at the Author's instruction mid-build, and the spec
file was updated to match in the same commit that scrubbed the old string.

### Stage 2, One-Shot Build (The Entry Ritual)
The ritual is deliberately minimal. Verbatim brief from the case study (one fragment elided for privacy):

> *"create flutter app, use MangaCat_Specification.md for specification, use
> smolfiddle gh account, the release is 0.0.1, do not release it yet but commit
> it to local, [...] dont make mistake, make it perfect"*

Three lines. The artifact carries the semantics; the prompt is a pointer.
**Do not push yet**: the first artifact is never the shipped artifact. The
Builder worked in milestones internally; the Author's only jobs during Stage 2
were: spec reachable, permission rules set, waiting.

### Stage 3, Hiccup Triage
- The Author **uses the app by hand**. Hiccups are felt, not read.
- Fix obvious defects in the main context. MangaCat defects triaged here:
  FAB missing entirely, snackbar queue collisions, fingerprint false-conflict
  dialogs, artist field mislabeled (later re-labeled "Artist/Studio/Org" at the
  Author's request), undo reverting the wrong action.
- Do not expand scope here. Fix, don't feature-add.

### Stage 4, Audit Swarm (Correctness)
- **Topology:** 2 subagents, read-mostly, parallel.
- **Brief, verbatim:** *"can you scan the codebase if you find any anomalies/bug/and
  need of adjustment? use sub agent for this"*
- **Findings handling: auto-accept.** What the swarm found passed to the Builder
  (commit `0f8e743`: 25 findings fixed, PIN cooldown freeze, silent data
  discard on conflict, atomic audit writes, IO moved off the Android main thread,
  and more). This is rational *only because* the gate behind it is strong
  (§2, principle 5). Do not copy auto-accept without copying the gate, and note
  the escape evidence in §13.

### Stage 5, Design Swarm (Aesthetics)
- Same topology, different axis. **Brief, verbatim:** *"now another round of
  subagents, review the Design/UI/UX where where it will be better overall"*
- Runs **only after** correctness is settled. Polish on moving code is wasted.
- Result: commit `9c25e33`, theme tokens consolidated, undo handles introduced,
  gesture hint, explicit "Not in your list." verdict, accessibility semantics,
  icon and brand unification (paw mark).

### Stage 6, Solo Ship
Deployment and polish run in the **main context, no subagents.** Decision rule:
*use the main context when the task is obvious and sequential*, deployment is
stateful, irreversible, and credential-adjacent; polish requires a single
authorial voice. The Builder initiates beyond the spec here; the Author curates.

What Stage 6 actually produced in this case (all in the main context):
- Release signing: `scripts/generate_keystore.sh` (PKCS12, 2048-bit RSA,
  10,000-day validity, random 48-hex-char password; keystore and
  `key.properties` gitignored; GitHub Actions secrets `KEYSTORE_BASE64` and
  `KEY_PROPERTIES_BASE64`).
- `scripts/build_release.sh`: AAB + per-ABI APKs + `SHA256SUMS`, optional
  `UNIVERSAL=1` and `OBFUSCATE=1`.
- Brand assets: the paw launcher icon set (adaptive + legacy + monochrome) and
  matching in-app `CustomPainter`; README; MIT LICENSE; `.gitattributes`.
- Optimization found by build failure, not design: the Flutter template's Gradle
  heap (`-Xmx8G`) killed the build on a 7.4 GiB machine; tuned to `-Xmx2G` with
  worker limits and committed.
- Release workflow initially failed at 0 seconds because `secrets` may not be
  used in a step-level `if`; replaced with a shell guard (`1fbe3bd`), and
  idempotent release creation was added (`29ef580`).

### Stage 6b, Tooling Bind (Device-Test Harness)
New stage, established by observed need: after releasing, there was no way for
the agent to *see* the app. The Bind stage evaluates and wires the device bridge.

Evaluation performed (both read-only, documented, no install of the rejected
option):
- **Maestro**: full YAML test framework with bundled MCP, Flutter support
  documented, but heavy: bash installer into `~/.maestro`, Java required, PATH
  edits to `.bashrc`/`.zshrc`, zip-integrity-only verification, and a Cloud
  upsell. A test *framework* when the immediate need was agent *hands*.
- **mobile-mcp (Mobile Next)**: MCP server for live device control; `npx`
  install; 33 tools (device list, app install/launch, element listing, tap/type,
  logcat, crash reports, batch commands, screen recording); opencode
  configuration documented upstream; telemetry opt-out via a single env var.

Decision: **mobile-mcp only**, on leanness grounds (the Author's explicit
priority). Verified after binding:
- Handshake: server `mobile-mcp 1.0.11`, **33 tools** returned.
- Device discovery: emulator `Medium_Phone_API_36.1`, Android 16, online.
- Node 20.19.4 emits `EBADENGINE` warnings from a transitive package requiring
  Node ≥22, verified harmless (server runs; handshake clean).
- Config facts: pinned version (`@1.0.11`), `timeout: 20000` (npx cold start
  exceeds the 5-second default), `MOBILEMCP_DISABLE_TELEMETRY=1`, and
  platform-tools/emulator added to PATH.

Honest limitation recorded at bind time: the running agent session could not use
the newly bound MCP tools (they load at session start), so the first Stage 7 run
was executed with a purpose-written **adb + uiautomator driver** instead:
`uitap.py` parses the UI tree, matches labels, and taps (the only part that is
annoying in shell), while install, screenshots, text input, and swipes went
through raw adb calls. Android-only, framework-agnostic.
Both paths are harness-equivalent for black-box flows; the MCP path remains to be
exercised in a future session (§13).

### Stage 7, Device Test (Black-Box Acceptance), EXECUTED
- Method: debug APK installed on an Android 16 emulator; every acceptance
  criterion walked black-box through system UI, not in-app test hooks.
- Evidence: **31 numbered screenshots** (`01_launch.png` … `31_bottom_padding.png`),
  a `TEST_NOTES.md` table of every flow and result, and the two CSVs written by
  the app during the run, saved, byte-verified, and bundled.
- Coverage: PIN setup and gate; cold-relaunch persistence; CSV creation via the
  system picker; search verdicts; add and quick-add; detail editing with
  autosave; swipe gestures; undo/restore id semantics; filters; save-to-CSV with
  byte-level RFC 4180 verification; advanced-mode column toggle; history with
  restore; batch folder scan including duplicate handling.
- Findings (fix loop Stage 8): the swipe gestures were over-triggering
  (reported by the Author from live use), the FAB and snackbars could occlude the
  last row, and a few harness-side artifacts were identified and excluded from
  the defect list (see §7, Harness hazards).

### Stage 8, Fix Loop
- The Author's report, verbatim: *"can you asses it the swipe feature 'read and
  delete' since it is way too sensitive and its also itrusive to actual apple
  like home interface like swipe at the side of the touch to go back, I think we
  need to add a comfirmation so the user will not automatically delete it"*
- Diagnosis (found, not guessed): `Dismissible` default threshold 0.4 plus
  fling-velocity dismissal with no confirmation gate.
- Fix (commit `d88ebf9`): thresholds raised to 0.6 both directions; swipe-left
  now raises a "Delete entry?" confirmation (Cancel restores the row untouched);
  the reversible completed-toggle stays instant; list bottom padding added so
  the FAB/snackbar never cover the last row.
- Re-verification on device, same session: short swipes inert; dialog gates
  delete; Cancel keeps the row; Delete + Undo restores the same id; firm toggle
  still works; scrolled-to-end layout verified clear of the FAB.

### Stage 9, Re-release
- Version bump `0.0.1+1` → `0.0.2+2` (commit `91a9f07`).
- Tag `v0.0.2` → CI built signed artifacts and created the GitHub release.
- The release was then completed by hand with the Author's explicit instruction:
  *"commit all first then bump it to 0.0.2 and create a release and add a
  description docs for it in the release, and put all the debug and test too."*
- Final v0.0.2 assets (7): three per-ABI release APKs, AAB, debug APK
  (148.34 MB, versionCode 2 verified inside the artifact), the test-evidence zip
  (31 screenshots + notes + saved CSVs, 3.15 MB), and `SHA256SUMS` covering all
  six others.
- Integrity chain re-verified from the published side: the CI-built arm64 APK
  was downloaded from the release and its SHA-256 matched the published checksum
  file exactly.

### Gates
- **Pre-push sweep** (solo, commit `4e0a37e`): zero-issue `analyze`, full test
  suite (41 tests), unused-dependency removal, secret and ignore-file audit,
  `.gitattributes` normalization. The push is the payment; the sweep is the price.
- **CI gate** (commit `f59a964`): `.github/workflows/ci.yml` runs
  `flutter analyze` + `flutter test` on every push and pull request; Flutter
  pinned to 3.41.7. Observed green runs: `38717574720`, `38724638555`,
  `38725131624`.
- **Release CI**: tag-triggered; restores the signing keystore from secrets
  (debug-signed fallback with a printed warning when absent), builds AAB + splits,
  verifies nothing, publishes a GitHub release with `--generate-notes`, and
  skips creation if the release already exists (idempotence guard).
- **Integrity chain**: checksums published with every release and re-verified by
  download-and-compare after publishing.
- **Human acceptance**: walked on emulator in Stage 7. A physical-device walk
  remains open (§13).

---

## 6. The Laws (Decision Rules)

1. **The Context Law.** Solo context for obvious, sequential, stateful,
   irreversible work (deploy, polish, integration). Swarm for independent,
   read-mostly, parallel-safe analysis (audits). If parallel agents would touch
   the same mutable state, it is a solo task.
2. **The Sequencing Law.** Correctness → design → deploy → test → fix →
   re-release. Never reorder. Never polish pre-audit code. The sequence is a
   cycle, not a line.
3. **The Gate Law.** Verification happens at checkpoints (analyzer, tests,
   pre-push sweep, CI, device), not at per-finding triage. Auto-accept is the
   reward for building strong gates, not a shortcut around them. Corollary from
   evidence: a gate only covers the failure *classes* it was built for; check
   class coverage before auto-accepting (§13).
4. **The Artifact Law.** Context lives in files (spec, AGENTS.md, skills), not
   in prompts. A prompt longer than two sentences is a smell: something should
   have been an artifact.
5. **The Freeze Law.** The spec is frozen before the build; amendments are
   deliberate, attributed, and re-frozen. Post-build discoveries enter the spec
   as deltas when the next version is cut.
6. **The Stop Law.** A stage ends when its axis is settled, not when output
   stops. Audit ends when findings dry up; polish ends at "would ship this."
7. **The Ownership Law.** The human owns every decision without a deterministic
   answer: what to build, in what order, when it's done, what it becomes
   (product-level calls like brand and license are human-only).

---

## 7. Failure Taxonomy (from the case study and generalization)

### Application defects (all fixed)

| Class | MangaCat instance | Caught by | General mitigation |
|---|---|---|---|
| Omission | FAB missing entirely | Stage 3 | Hands-on use; acceptance criteria enumerate every screen element |
| Concurrency/race | Snackbar queue collisions; undo reverting the wrong action | Stage 3 / audit | Audit swarm; one-step undo made handle-scoped |
| Over-strict validation | Fingerprint compare false-conflicts on providers without size/mtime | Stage 3 | "Forgiving and loud" spec language; component-wise compare with unknown tolerated |
| Labeling/UX drift | Artist field mislabeled | Stage 3 | Hiccup triage + design swarm |
| Gesture over-trigger | Swipe delete fired on 40% drag or a flick, no confirmation | **Stage 7** | Threshold raise + confirmation gate for destructive gestures |
| Layout occlusion | FAB/snackbar covering the last row | **Stage 7** | Reserve list bottom padding where floating chrome lives |
| Harness complacency | Agent reading own output calls it done | Prevented | Never skip Stage 3/7, the Author must *feel* the app |
| Context loss on long tasks | (avoided) | - | Milestone large builds; swarm topology for breadth |
| Environment OOM | Gradle template heap 8G on a 7.4 GiB machine; build killed | CI/build | Tune toolchain memory to host; commit the tuning |

### Harness hazards (not app defects; recorded so future runs skip them)

| Hazard | Observed instance | Workaround |
|---|---|---|
| Accessibility persistence | uiautomator's accessibility connection keeps Flutter snackbars from auto-dismissing; they overlay bottom buttons | Dismiss by swipe before tapping under them; judge snackbar timing only on a clean device |
| `pkill` self-match | `pkill -f "gradle"` matched and killed its own shell twice | Bracket pattern: `pkill -f "[G]radleDaemon"` |
| Substring label matching | Driver "click Allow" hit the dialog *title* "Allow MangaCat to access…" | Tap by explicit bounds for dialogs whose title contains the button word |
| Coordinate drift | Keyboard show/hide moves fields between dump and tap | Re-dump after every keyboard transition; prefer text-entry + focus traversal (TAB) over tapping fields |

### Open tradeoffs (recorded, not resolved)

| Item | State |
|---|---|
| PBKDF2 timing | 100k iterations in a Dart isolate measured ~3–8 s per hash on the emulator (set PIN and unlock). Spec targets are written for real hardware; no physical-device measurement yet. |
| Snackbar occlusion of bottom-pinned buttons | Floating snackbars can sit over the pinned Add row / Import button for their duration; left as-is pending a real-device judgment call. |
| "Import N" with all candidates hidden | The hide-duplicates toggle hides rows but the count keeps hidden selections; intentional persistence, flagged as cosmetic. |

---

## 8. Skill Requirements (Honest)

You do **not** need: syntax fluency, framework memorization, or the ability to
write any of the code.

You **do** need:
- **Spec judgment**: knowing what you want well enough to answer forced-choice
  questions, and recognizing when to delegate ("whatever is best")
- **Context intuition**: the Context Law applied without hesitation
- **Gate discipline**: actually running the sweeps, actually pushing only after
- **Stage discipline**: resisting feature creep during fix rounds; stopping
  stages when their axis is settled
- **Calibration honesty**: knowing which of your decisions are preference and
  which are expertise
- **Test orchestration**: deciding what the device run must prove, reading
  evidence (screenshots, byte-level files) instead of trusting "it works," and
  distinguishing app defects from harness artifacts

---

## 9. Anti-Patterns

- **Prompt essays.** Long prompts where an artifact should be. (Use the Artifact Law.)
- **Per-finding triage without gates.** Reviewing every agent finding by hand
  because your verification tier is weak. Fix the gate instead.
- **Swarm deployment.** Parallel agents on sequential, irreversible work.
- **Design before correctness.** Any polish applied to unaudited code.
- **Prompt-and-pray one-shots.** Skipping Stages 0–1. The one-shot only works
  because a contract exists; without it you get the modal hollow scaffold.
- **Shipping the first artifact.** "Do not push it yet" is load-bearing.
- **Treating "CI is green" as acceptance.** CI proves the build compiles and
  tests pass; the swipe defect was found only by Stage 7 hands-on use.
- **Trusting the harness over the artifact.** A failing tap can be a driver bug;
  verify against the screenshot before "fixing" the app.
- **Human micromanagement inside stages.** If you're directing file-level work,
  the contract wasn't clear enough, go fix the contract.
- **Releasing without the identity ceremony.** The signing keystore is the one
  irreplaceable object in the project; back it up before the first tag.

---

## 10. Templates (Verbatim from Practice)

**One-shot:** *(spec file placed in project; compression skill loaded)*
> "create flutter app, use MangaCat_Specification.md for specification, use
> smolfiddle gh account, the release is 0.0.1, do not release it yet but commit
> it to local, [...] dont make mistake, make it perfect"

**Audit swarm:**
> "can you scan the codebase if you find any anomalies/bug/and need of
> adjustment? use sub agent for this"

**Design swarm:**
> "now another round of subagents, review the Design/UI/UX where where it will be
> better overall"

**Device test:**
> "can you start testing the app?"

**Defect fix (user report → diagnosis → fix):**
> "sure fix any stuff, and can you asses it the swipe feature 'read and delete'
> since it is way too sensitive and its also itrusive to actual apple like home
> interface like swipe at the side of the touch to go back, I think we need to
> add a comfirmation so the user will not automatically delete it"

**Release packaging:**
> "commit all first then bump it to 0.0.2 and create a release and add a
> description docs for it in the release, and put all the debug and test too."

**Tooling bind (decision statement):**
> "conclusion, lets just integrate mobile-mcp not maestro, is this a good idea,
> I want my dev set up lean as possible."

**opencode MCP configuration (reusable, as installed):**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mobile-mcp": {
      "type": "local",
      "command": ["npx", "-y", "@mobilenext/mobile-mcp@1.0.11"],
      "environment": { "MOBILEMCP_DISABLE_TELEMETRY": "1" },
      "enabled": true,
      "timeout": 20000
    }
  }
}
```

**AGENTS.md must mandate (harness-agnostic):**
- Run the static analyzer after every few files; zero issues before continuing;
  report analyzer output verbatim
- Permission allowlist (build/test tools); everything else ask-or-deny
- Never push; never commit signing secrets
- Commit locally when the stage completes; pushing is a human gate

**Evidence bundle (Stage 7 artifact, reusable shape):**
- Numbered screenshots for every step, named by flow
- `TEST_NOTES.md`: flow → result table; explicit note of harness artifacts
- Raw outputs the app produced during the run (here: the saved CSVs, byte-verified)
- Bundled as a zip and attached to the release

---

## 11. Cost & Time Model

| Phase | Wall-clock (human-facing) | API spend | Notes |
|---|---|---|---|
| 0–1 Elicitation + contract | ~1 hr | near-zero tokens | Human attention dominant |
| 2 One-shot (v0.0.1) | one evening | ¥4.04 / ~$0.60 (metered) | Fresh input + heavy cached re-reads; output compression on |
| 3–5 Triage + swarms | included above | included | Cached input dominant (audits are read-mostly) |
| 6 + gates Ship (v0.0.1) | included above | included | Output-heavy generation |
| 6b Tooling bind (MCP) | sub-hour | included in Phase 2 total | Assessment (both tools), install, config, verification |
| 7 Device test | ~54 min capture span | included in Phase 2 total | First screenshot 18:08 → last 19:02 → evidence zip 19:09 (host time) |
| 8 Fix loop | sub-hour | included in Phase 2 total | Diagnosis, fix, re-verify on device |
| 9 Re-release (v0.0.2) | sub-hour | included in Phase 2 total | Bump, tag, CI, notes, evidence upload, checksum chain |
| **Phase 2 total (6b–9)** | **≈2 hrs (sum of rows)** | **¥3.72 (~$0.55)** | Aggregate for stages 6b–9; derived from the overall meter minus Phase 1 |
| **Project total** | ~2 evenings | **¥7.76 (~$1.15)** | 464 requests · 118,112,557 tokens (overall meter) |

Economics observed: ≈254k tokens per request across the project
(118,112,557 / 464), cached context re-reads dominate, which is the artifact
economy working as claimed; output-token compression attacks the most expensive
vector of verbose models; milestone staging suppresses retry spirals, the true
cost driver in agentic coding. Metering honesty: Phase 1 was metered live
(¥4.04); Phase 2 is derived from the overall meter minus Phase 1
(¥7.76 − ¥4.04 = ¥3.72). Only project-level aggregates exist, no per-stage
split, and no counterfactual (no-method baseline). These are API marginal costs;
they exclude human time, hardware, and infrastructure.

---

## 12. The Reusable Kit (copy to every new project)

1. The spec **template** (§5 Stage 1 structure, goals/non-goals, data model,
   normative formats, error matrix, locked decisions, acceptance criteria)
2. `AGENTS.md` baseline (analyzer loop, permissions, never-push, commit-at-stage)
3. The verbatim briefs (§10), including the release-packaging and test briefs
4. Permission allowlist configuration
5. Output-compression skill configuration
6. Pre-push sweep habit + **CI gate workflow** (analyze + tests, pinned toolchain)
7. **Release workflow** (signed artifacts from secrets with debug fallback,
   idempotent release creation) + **keystore ceremony** (PKCS12, random password,
   gitignore, off-machine backup) + checksum-in-release + download-and-verify
8. **Device bridge config** (mobile-mcp snippet above; telemetry off; pinned version)
9. **Device driver script** (adb + uiautomator label-tap helper, Android-only
   but framework-agnostic; the Stage 7 fallback that proved sufficient) and
   the **evidence-bundle shape** (§10)
10. This document

**Method v2.0 candidates** (not yet practiced): automated acceptance-runner
(the `uitap.py` driver is the first prototype; promoting it to a checklist
executor is the highest-value addition); persistent "model failure ledger" per
project feeding the audit briefs; spec-diff folding (the v0.0.2 cycle is one
informal instance, formalize it); a **security axis** in the swarm round
(none exists yet, see §13).

---

## 13. Open Loops (Honesty Clause)

- **Physical-device acceptance is still pending.** Stage 7 was executed on an
  Android 16 emulator with full evidence. The method's own rule, "only hands
  prove the behavior", ultimately wants a real phone: touch-feel of swipe
  thresholds, PBKDF2 timing on real hardware, SAF behavior with real providers.
- **Auto-accept remains the weakest load-bearing claim.** Strongest evidence:
  the swipe over-trigger survived Stages 2–5 (spec, build, correctness audit,
  design review) and was found by Stage 7 hands-on use. Auto-accept was safe in
  Stage 4 partly because findings were reasonable, not solely because gates
  covered their classes. Until a gate-to-failure-class matrix exists, auto-accept
  is a judgment call, not a rule.
- **Security has no dedicated axis.** The privacy app's strongest properties
  (zero network permissions, `allowBackup=false`, SAF-only file access) were
  implemented and *verified mechanically* (aapt2 permission dump, `apk signer`
  check), but no adversarial swarm probed them. Add a security checklist to the
  swarm round, or an explicit security gate.
- **Track record is one application project, two releases.** The method's
  generality is asserted from mechanism, not repetition. Run it on a
  different-shaped target (a backend, a team, an exploratory domain) before
  calling it a pattern. The linear-spec assumption is the most likely to break
  in exploratory work; the method has no "when not to use" section yet.
- **The MCP path is bound but untested in anger.** Handshake and device
  discovery verified; the actual Stage 7 run used the adb driver because MCP
  tools load at session start. Next session should re-run one flow through
  mobile-mcp and compare against the adb-driver baseline.
- **Per-stage cost attribution is missing.** The meter is project-level
  (¥7.76, 464 requests, 118,112,557 tokens overall); Phase 2's ¥3.72 is a
  subtraction, not a measurement, and no no-method counterfactual exists.

---

## 14. Fact Ledger (Evidence Anchors)

**Repository:** github.com/smolfiddle/MangaCat (public, MIT)
**Releases:** v0.0.1 (5 assets) · v0.0.2 (7 assets, marked Latest)

**Commits (16):**

| Hash | Subject |
|---|---|
| `80ba811` | feat: MangaCat v0.0.1 offline personal series tracker |
| `3a732cb` | fix: add FAB, snackbar queue, resilient fingerprint compare |
| `12c03a6` | fix(ui): label the artist field as Artist/Studio/Org |
| `0f8e743` | fix: review findings across data, state, UI, and Android layers |
| `9c25e33` | feat(ui): design and UX polish pass |
| `cf1dbd8` | build: production deployment pipeline |
| `df55734` | docs: add project README |
| `979ada9` | feat(brand): ship Stamp Paw launcher art and match in-app mark |
| `4e0a37e` | chore: pre-push sweep |
| `8caee7a` | release: attach artifacts to GitHub releases on version tags |
| `53e4c23` | docs: add MIT license |
| `29ef580` | ci: skip release creation when the release already exists |
| `1fbe3bd` | ci: drop secrets from step if (invalid workflow expression) |
| `f59a964` | ci: add analyze + test gate on push and pull requests |
| `d88ebf9` | fix(tracker): gate swipe-delete behind a confirm dialog |
| `91a9f07` | chore: bump version to 0.0.2 |

**Tags:** `v0.0.1` · `v0.0.2`
**CI runs (all success):** release v0.0.1 `38600366404` · release v0.0.2
`38725416593` · ci gate `38717574720`, `38724638555`, `38725131624`
**Test suite:** 41 tests (CSV codec, PBKDF2 vectors, repository semantics,
fingerprint, PIN widget flows); `flutter analyze` zero-issue policy.
**Metering:** overall project meter ¥7.76 (~$1.15) across 464 requests and
118,112,557 tokens. Phase 1 metered live at ¥4.04 (~$0.60); Phase 2 derived as
¥7.76 − ¥4.04 = ¥3.72 (~$0.55).
**Release identity:** PKCS12 keystore, 2048-bit RSA, 10,000-day validity, random
48-hex password; `android/keystore/*.p12` and `android/key.properties` gitignored;
CI secrets restore the same key (verified: CI-built APK signer `CN=MangaCat`).
**Release APK permissions:** zero `android.permission` entries (only the app-local
`DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`); `allowBackup=false`.
**Stage 7 evidence:** 31 screenshots (`01_launch.png` … `31_bottom_padding.png`),
`TEST_NOTES.md`, 2 saved CSVs; captured 18:08–19:02 host time, bundle finalized
19:09; attached to v0.0.2 as `mangacat-0.0.2-test-evidence.zip` (3.15 MB).
**Device under test:** emulator `Medium_Phone_API_36.1`, Android 16 (API 36),
1080×2400; debug APK versionCode 2 / versionName 0.0.2 verified via aapt2.
**MCP verification:** `mobile-mcp` 1.0.11 handshake OK; 33 tools; device
discovery OK; Node 20.19.4 with non-fatal EBADENGINE warnings.
**Integrity chain:** arm64 release APK re-downloaded from the published release;
SHA-256 matched published `SHA256SUMS` exactly.

---

*The app is the artifact. The pipeline is the asset. The document is the
transfer. End of reference.*
