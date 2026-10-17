Specification: webtap.py — Web Driver for The Artifact Method

Two parts: the frozen contract (what to build) and the integration (how it plugs into TAM). Written in TAM's own idiom—concrete verbs, honest open loops, evidence receipts.

---

Part 1 — The Specification

1.1 Purpose

Give TAM a web-target acceptance driver with the same shape, philosophy, and exit-code contract as uitap.py. Single file. Only dependencies: python3 and the playwright Python package. Reads the accessibility tree via Playwright's ARIA snapshot; acts via accessibility-first locators; falls back to raw selectors and coordinates.

Non-goals (v0.1.0):

· Not a test framework. No assertions beyond --expect.
· Not a scraper. No data extraction verb.
· Not a CI runner. One command, one action, one exit code.
· Not a replacement for uitap.py. Android stays on uitap.py.
· Not for cross-frame or cross-origin flows. Main frame only in v0.1.0.

1.2 CLI surface (frozen)

```
webtap.py [-s STATE] [--headed] [--browser chromium|firefox|webkit]
          [--verbose] [--log FILE] <command> [args]

Commands:
  goto <url>                             navigate; wait for load state
  url                                    print current URL
  title                                  print page title
  dump-labels [selector] [--json]        list matching elements (ARIA snapshot)
  find <selector args>                   print first match, exit 1 on miss
  tap <selector args>                    click the element
      [--retry N] [--retry-delay S] [--dry-run]
      [--expect L [--expect-exact | --expect-regex]] [--expect-timeout S]
  wait <selector args> [--timeout S]     wait for element visible
  wait-gone <selector args> [--timeout S] wait for element hidden/detached
  wait-stable [--network-idle] [--rounds N]
                                         wait until DOM + (optionally) network settle
  scroll-to <selector args>              scroll element into view
  text [--into LABEL] [--clear] <value>  fill a field; --into focuses first
  clear [--into LABEL]                   clear a field
  key <NAME>                             Enter, Tab, Escape, ArrowDown, ...
  shot <name> [--full-page] [--element SEL] [--format png|jpeg|webp]
                                         screenshot to <name>.<ext>
  console [--since S]                    recent console messages
  network [--since S] [--filter PAT]     recent network requests
  flow <file.json>                       run a sequence in one browser session
  selftest                               internal checks, no browser needed
  version                                print version

Selectors (used by find, tap, wait, wait-gone, scroll-to, text --into):
  <label>              substring on accessible name (role + name)
  --exact              whole accessible-name match
  --regex              regex over accessible name
  --case-sensitive     stop folding case
  --role ROLE          restrict to a role (button, link, textbox, heading, ...)
  --id <css|#id>       CSS selector match instead
  --within <selector>  scope search to a parent element
  --nth N              pick the Nth match (0-based)
  --topmost --bottommost --leftmost --rightmost   pick by position

Exit codes: 0 success, 1 miss/timeout, 2 usage or browser error.
```

The surface deliberately mirrors uitap.py's verb set so agents that learn one can drive the other. dump-labels, find, tap, wait, wait-gone, wait-stable, text, clear, key, shot, selftest, version are all 1:1. New verbs are web-specific: goto, url, title, console, network, flow.

1.3 Session model — stateless with storage state

This is the one design decision that cannot be copied from uitap.py.

Android is inherently stateful: the device is one persistent thing. A browser is not—each playwright.chromium.launch() is a fresh process. If every webtap.py command launches, acts, and closes, login state and cookies vanish between commands.

Decision: stateless with a state file.

· Default state path: .webtap/state.json (Playwright's storage_state format).
· Each command: load state if present → launch → act → save state → close.
· goto, tap, text, and flow all save state on success.
· webtap.py never keeps a browser alive between commands.
· Escape hatch: --headed --keep-open launches with --remote-debugging-port and prints the port, letting a human attach DevTools. This is for debugging only, not for the pipeline.

Why this and not a persistent server: TAM's philosophy is "no daemons, no servers, no frameworks." A persistent browser is a daemon. Storage state preserves the stateless contract at the cost of ~1.5s per command.

Honest limitation: storage_state captures cookies, localStorage, and IndexedDB, but not sessionStorage, service workers, or in-memory state. Apps that rely on these for auth will not persist login across commands. This is documented as an open loop.

1.4 Selector model

Playwright already provides accessibility-first locators. The Selector class maps directly:

Selector arg Playwright resolution
<label> page.get_by_role(role, name=label, exact=exact) if --role given; else page.get_by_text(label, exact=exact)
--role R page.get_by_role(R, name=label, exact=exact)
--id "#x" or --id ".x" page.locator(selector)
--regex re.compile(label) passed to get_by_text or get_by_role(name=...)
--within SEL Resolve parent, then .locator(...) on it
--nth N .nth(N) on the resulting locator
--topmost etc. Resolve all matches, sort by bounding_box(), pick

Strict mode: Playwright throws if a locator resolves to multiple elements. webtap.py catches this and reports MISS: N matches; use --nth instead of a stack trace. This is a new failure mode that uitap.py does not have—Android silently picks the first.

1.5 Verbs — behaviors

goto <url> — navigates, waits for load then networkidle with a bounded timeout (default 20s). Prints final URL and title. Saves state.

dump-labels [selector] — calls page.locator("body").aria_snapshot() for the full tree, or enumerates matching elements when a selector is given. Output is one line per node: role=button name="Submit" bounds=[x,y,w,h]. --json emits structured objects. This is the uiautomator dump analog.

find <selector> — resolves the first match, prints its role, name, and bounding box. Exit 1 on no match. Exit 1 with a "multiple matches" message if strict mode fails.

tap <selector> — resolves, scrolls into view if needed, clicks via locator.click(). Supports the same --retry, --dry-run, --expect options as uitap.py. Playwright's auto-waiting handles most animation races for free.

wait <selector> — locator.wait_for(state="visible", timeout=...). Polls natively; no manual sleep loop.

wait-gone <selector> — locator.wait_for(state="hidden", timeout=...). Matches uitap.py's semantics.

wait-stable [--network-idle] — polls page.evaluate("() => document.querySelectorAll('\*').length") plus a hash of visible text until it stops changing for --rounds consecutive checks. --network-idle additionally waits for page.wait_for_load_state("networkidle"), bounded by the same timeout. This is the analog of uitap.py wait-stable.

scroll-to <selector> — locator.scroll_into_view_if_needed(). Playwright does this automatically on click, but explicit is available for scroll-triggered lazy loading.

text [--into LABEL] <value> — if --into, resolves the field and calls .click() first. Then locator.fill(value) or page.keyboard.type(value) if --type is given (fill is instant, type simulates keystrokes). --clear calls .fill("") first. Non-ASCII is fully supported—Playwright types Unicode natively, unlike adb.

key <NAME> — maps to Playwright's key names: Enter, Tab, Escape, ArrowDown, PageDown, Control+A, etc. Rejects unknown keys with exit 2.

shot <name> — page.screenshot(). --full-page captures the entire scrollable page. --element SEL captures a single element via locator.screenshot(). --format inferred from extension or set explicitly. This is a strict superset of uitap.py shot.

console / network — require the browser to be launched with listeners active. Since webtap.py is stateless per command, these read from a rolling log written to .webtap/console.log and .webtap/network.log by every command that runs. --since S filters by seconds-ago. This makes the two verbs useful without a persistent session.

flow <file.json> — the batched mode. Reads a JSON array of {"cmd": "tap", "label": "Login"} objects, runs them in one browser session, writes per-step evidence (screenshot + console tail) to .webtap/evidence/step-N/, and exits with the first non-zero step's code. This is the fastest path and the recommended way to run a TAM acceptance stage end-to-end.

1.6 Evidence model

TAM cares about receipts. Every command that changes page state writes:

· .webtap/evidence/<timestamp>-<cmd>.png — screenshot after the action
· .webtap/evidence/<timestamp>-<cmd>.json — selector, matched element, URL, title, exit code
· .webtap/console.log — appended console messages
· .webtap/network.log — appended request lines: GET https://x/y 200 143ms

flow writes a directory per step. Screenshots are the visual receipt; the JSON is the machine-readable one. Both are the analog of uitap.py shot plus --log, generalized.

1.7 Config

Optional .webtap.toml in the project root:

```toml
[webtap]
base_url = "http://localhost:3000"
browser = "chromium"
viewport = [1280, 800]
state_file = ".webtap/state.json"
evidence_dir = ".webtap/evidence"
timeout_default = 20
```

CLI flags override config. Config overrides env (WEBTAP_BASE_URL, WEBTAP_BROWSER). No config is required.

1.8 Exit codes

Same as uitap.py: 0 success, 1 miss/timeout/expect-failed, 2 usage or browser error. Browser errors that are fatal (browser not installed, launch failed) exit 2 immediately and never poll—mirroring uitap.py's FATAL_ADB_HINTS behavior.

1.9 Open loops (v0.1.0)

· Cross-frame and cross-origin flows are not supported. Main frame only.
· storage_state misses sessionStorage and service workers. Apps using these for auth will not persist across commands.
· Playwright launch overhead is ~1.5s per command. flow mode amortizes this; per-command mode does not.
· aria_snapshot() is Playwright 1.49+. Older versions require fallback to page.accessibility.snapshot().
· No security audit axis. Like uitap.py, this is a driver, not an auditor. A future --capture-network --assert-no-external verb could serve that role, but it is not in v0.1.0.
· No selftest coverage of browser actions. selftest will verify the parser, selector resolution, config loading, and flow-file parsing—all without a browser—because launching Chromium in selftest violates the "no device needed" contract. Browser-path testing requires a separate harness.

---

Part 2 — Integration into TAM

2.1 Stage 7 revision

Current SKILL.md describes Stage 7 as "Bind the hand to the device" with uitap.py as the tool. Revise Stage 7 to be target-agnostic:

Stage 7 — Bind the hand to the target. Drive the shipped artifact through its real UI. Android → uitap.py. Web → webtap.py. Same discipline: black-box, through the system UI, evidence receipts per step, exit-code-driven.

The stage's method is unchanged. Only the tool becomes plural.

2.2 SKILL.md additions

Add a subsection under Stage 7:

```markdown
### Web acceptance (webtap.py)

Same contract as uitap.py: single file, argparse CLI, exit codes 0/1/2.
Prerequisite: `pip install playwright && playwright install chromium`.

Verb parity with uitap.py: dump-labels, find, tap, wait, wait-gone,
wait-stable, text, clear, key, shot, selftest, version.

Web-only verbs: goto, url, title, console, network, flow.

Key difference: webtap.py is stateless per command with a state file at
.webtap/state.json. Use `flow <file.json>` for multi-step acceptance runs—
it launches one browser and runs the whole sequence.

Evidence: every state-changing command writes a screenshot and a JSON
receipt to .webtap/evidence/. Flow runs write one directory per step.
```

2.3 AGENTS.template.md additions

Add to the template's tooling section:

```markdown
## Target acceptance tools

- Android: scripts/uitap.py
- Web: scripts/webtap.py (requires: pip install playwright)
- Evidence: .uitap/ and .webtap/evidence/ are receipts, not logs.
  Commit them for release-gating steps; ignore them otherwise.
```

And add to the "Claims need receipts" rule:

```markdown
A claim about web behavior needs a webtap.py receipt: a screenshot AND a
JSON receipt from .webtap/evidence/. A claim about Android behavior needs
the equivalent from uitap.py.
```

2.4 Repo layout

```
the-artifact-method/
├── The_Artifact_Method.md          (add a §Web acceptance subsection)
├── SKILL.md                        (revise Stage 7)
├── assets/
│   └── AGENTS.template.md          (add tooling section)
└── scripts/
    ├── uitap.py                    (unchanged)
    └── webtap.py                   (new, single file)
```

Do not extract a shared \_common.py in v0.1.0. uitap.py's value is that it is one droppable file. webtap.py should be the same. The Selector class is ~80 lines; duplication is acceptable. If drift becomes a real problem, extract in v0.3.0 and document it as a version break. Listing this as a known open loop now is the honest move.

2.5 A worked example

TAM's MangaCat case study, expressed as a webtap.py flow (hypothetical, if MangaCat had a web build):

```json
[
  { "cmd": "goto", "url": "https://mangacat.example/" },
  { "cmd": "wait", "label": "Library" },
  { "cmd": "shot", "name": "01-library", "full_page": true },
  { "cmd": "tap", "label": "Add Series" },
  { "cmd": "text", "into": "Title", "value": "Solo Leveling" },
  { "cmd": "tap", "label": "Save" },
  { "cmd": "wait", "label": "Solo Leveling" },
  { "cmd": "shot", "name": "02-added", "full_page": true },
  { "cmd": "network", "filter": "api/" }
]
```

Run with:

```bash
python3 scripts/webtap.py --headed flow acceptance.json
```

Exit 0 means the whole flow passed. Any step's non-zero exit aborts and propagates. Evidence lands in .webtap/evidence/step-01/ through step-09/, each containing a PNG and a JSON receipt. That directory is the artifact handed to the human at the Stage 7 gate.

---

Part 3 — Build order (for a one-shot)

If you build webtap.py in a single pass, the dependency order is:

1. CLI skeleton + config loader + exit codes. No browser needed. selftest and version must work with playwright uninstalled.
2. Selector class + selector_namespace() helper. Copy from uitap.py, adapt the role field. selftest verifies resolution logic against a fixture locator tree using a stub object.
3. goto, url, title. Simplest browser actions. Confirm state file round-trips.
4. dump-labels, find. ARIA snapshot + selector resolution. This is the core contract; get it right before adding verbs.
5. tap, wait, wait-gone, wait-stable. The action verbs.
6. text, clear, key. Form interaction.
7. shot, console, network. Evidence layer.
8. flow. The batched runner. Requires everything above to be stable.
9. scroll-to. Trivial once tap works.

Add a selftest at step 2 and grow it with each verb. A one-shot build without selftest will drift on the regex/selector edge cases that uitap.py already paid for—do not repeat the debt.

---

The single most important design decision in this spec: the stateless-per-command model with flow as the batched escape hatch. It preserves TAM's "no daemons" philosophy while amortizing Playwright's launch cost where it matters. If you build only one thing beyond the CLI skeleton, build flow early—it is what turns webtap.py from a toy into a Stage 7 acceptance runner.

---

Part 4 — Amendments after freeze (attributed, 2026-10-17)

Recorded per TAM's Freeze Law rather than silently edited, because the frozen
surface above and the shipped v0.1.0 diverge deliberately:

1. `-s STATE` short flag dropped. `-s` collides with uitap.py's serial flag
   for agents that learn one driver; `--state FILE` is the only form.
2. Config file is `.webtap.json`, not `.webtap.toml` (§1.7). tomllib is
   Python 3.11+; the 3.9 floor wins, and JSON round-trips viewport arrays
   without type ambiguity.
3. Added: DOM commands automatically reopen the last visited URL persisted
   in `.webtap/last.json` (`goto`, `url`, `title` navigate instead). Without
   this, any non-navigating command ran against about:blank and the
   stateless model was unusable per command.
4. Added verbs `scroll up|down|left|right` and `screen`; added `--tree` and
   `--limit` to dump-labels, `--json` to find, `--lines` to console/network.
   The original surface under-specifies the uiautomator-dump analog.
5. Strict mode (§1.4) also applies after --within scoping, and containers
   whose children also match are de-duplicated before the multi-match check,
   so a wrapper element and its labelled child are not "two matches".
6. Evidence layout: standalone commands write `.webtap/evidence/<stamp>-<cmd>`
   `.png`/`.json` pairs; flow writes `.webtap/evidence/flow-<stamp>/step-NN/`
   plus `index.json` and `TEST_NOTES.md` (spec §2.5 said `step-01` directly
   under evidence). One directory per flow keeps concurrent runs separable.
7. §1.3's `--keep-open` escape hatch is not in v0.1.0; the frozen CLI (§1.2)
   never listed it. It remains a candidate, not a promise.
8. §2.3's `.uitap/` directory does not exist: uitap.py takes explicit
   screenshot names and an optional `--log FILE`. The AGENTS template was
   corrected to match reality.
