# TAM Cockpit (DeepSeek Harness)

> **Status:** experimental / preview. No shipped case study yet.
> **Applies to:** TAM reference 1.5, TAM skill 0.4.0.
> **Source:** [TAM Cockpit repository](https://github.com/smolfiddle/TAM_DSH_PLUGIN)
> **Spec:** [TAM Cockpit normative specification](https://github.com/smolfiddle/TAM_DSH_PLUGIN/blob/main/spec/spec.md)
> **License:** MIT, smolfiddle.

TAM Cockpit is an optional DeepSeek Harness (DSH) bundle that runs The Artifact
Method inside the harness. It adds an enforced stage machine, a gate ledger,
agent tools, slash commands, and a Web cockpit. It is a harness for the method,
not a new method.

## What it is

- A DSH bundle containing the TAM and artifact-spec skills, pinned snapshots of
  the method, and the two acceptance drivers for later use.
- An enforced state machine for the eleven TAM stages. v1 executes Stages 0–2;
  v2 adds Tooling bind and Target test, and lets the audit/design swarms be
  skipped with a recorded decision.
- A gate engine that runs configured analyze/test/build/secret checks and stores
  immutable receipts.
- A cockpit page that shows the pipeline, the contract, gate evidence, and
  project settings.
- A local-only system: no telemetry, no cloud sync, no implicit network calls.

## What it is not

- It is not a replacement for the method, the web-AI elicitation path, or the
  human's ownership of intent, contract, sequencing, and gates.
- It does not generate application code or choose a stack.
- It does not push, tag, sign, or release. Those remain human gates.
- It does not run audit/design swarms. The vendored device drivers run through
  `tam_driver` in v2.
- It does not provide a multi-project registry.

## Requirements

- DSH with the Web GUI.
- A project directory you want to govern with a TAM contract.
- Python 3.9+ only when v2 device acceptance is enabled. v1 does not need Python
  or Playwright.

## Install

1. Get the bundle from the [TAM Cockpit repository](https://github.com/smolfiddle/TAM_DSH_PLUGIN).
2. Install it through DSH's plugin manager (Plugins → Add, or the
   `plugin_manager` install action) using the package directory.
3. Open the TAM entry in the sidebar.
4. Initialize a TAM project, or open an existing one with `spec/spec.md` and
   `AGENTS.md`.

There is no published package yet. The TAM repo does not host the plugin source.

## v1 scope

| Area | v1 |
|---|---|
| Stages | Elicitation, Contract, Build |
| Gates | `contract.frozen`, `build.local`, `sweep.pre_push` |
| Evidence | Command and attestation receipts, hashed and immutable |
| Cockpit | Pipeline, Contract, Evidence, Settings |
| Skills | Bundled TAM 0.4.0 and artifact-spec 0.1.2; external copies win |
| Later stages | Audit/design/ship visible; tooling and acceptance executable |
| Device test | `tam_driver` bind/run, `tooling.bound`, `acceptance.human`, `TEST_NOTES.md` |

## What it enforces

- Stage order: a stage cannot start until the previous stage is complete.
- Contract freeze: the spec must be FROZEN and open questions must be empty or
  waived before build.
- Receipts: a passed gate needs evidence; "it works" is not evidence.
- Human gates: brand, license, acceptance, and release decisions are attested,
  not inferred.
- No silent push or release: the plugin never runs those actions.

## Agent tools

| Tool | Purpose |
|---|---|
| `tam_status` | Read project, stage, gates, and next action. |
| `tam_start` | Initialize a TAM project. |
| `tam_stage` | Begin or complete a stage, enforcing gates. |
| `tam_gate` | Check, attest, or waive a gate. |
| `tam_decision` | Append a numbered decision. |
| `tam_evidence` | Record a manual receipt. |
| `tam_repair` | Diagnose or rebuild mismatched state. |
| `tam_driver` | Bind or run a vendored uitap/webtap driver. |

## Human commands

| Command | Purpose |
|---|---|
| `/tam` | Show stage, gates, and next action. |
| `/tam start` | Initialize when no TAM artifacts exist. |
| `/tam next` | Show the current stage brief. |
| `/tam gate` | Show gate status and unblock steps. |
| `/tam repair` | Print the diagnostic report. |

## Freeze timing

The contract is normally frozen before the build. TAM Cockpit also supports a
post-build freeze: start the first build from a reviewed draft, let the build
surface contract changes, record them as decisions, then freeze. Build
completion still requires `contract.frozen`; release always does. The cockpit
shows which mode is active and records a late freeze in the stage history.

## Project artifacts

| Path | Purpose |
|---|---|
| `spec/spec.md` | The normative contract. |
| `spec/decisions.md` | Append-only decision log. |
| `spec/open-questions.md` | Open items; empty or waived at freeze. |
| `AGENTS.md` | Project rules and analyze/test/build commands. |
| `.tam/state.json` | Stage, gate, and evidence ledger. |
| `.tam/evidence/` | Receipts and logs; gitignored by default. |

The contract and `AGENTS.md` stay in the project and remain readable without
the plugin. Uninstalling TAM Cockpit does not delete them.

## How it relates to TAM

- The bundled `the-artifact-method` skill remains the method contract.
- Stage 0 can still run in a web AI chat. The cockpit path delegates the
  interview to the bundled `artifact-spec` skill; it does not reimplement it.
- The spec lives at `spec/spec.md` so it is compatible with artifact-spec;
  `AGENTS.md` points at it.
- Swarms, device acceptance, and release remain human-orchestrated.

## Security and privacy

- All state and evidence stay local. There is no telemetry.
- Gate commands are treated as untrusted repository content: shown as argv,
  confirmed on first use, executed without an implicit shell, and redacted.
- The plugin never stores credentials, signing material, or tokens.
- The cockpit API is same-origin only.

## Known limits

- No shipped case study yet.
- The default v1 path stops after the local build and pre-push sweep.
- The v2 device-test path runs the vendored drivers and requires `TEST_NOTES.md`
  plus at least one acceptance receipt before human attestation.
- Audit/design swarms and release automation remain deferred.
- One TAM project per workspace.
- The cockpit is a DSH surface; other harnesses use the plain skill workflow.

## Version pins

| Component | Version |
|---|---|
| TAM reference | 1.5 |
| TAM skill | 0.4.0 |
| artifact-spec | 0.1.2 |
| TAM Cockpit | see the plugin repository |

## License

MIT. See [LICENSE](LICENSE).
