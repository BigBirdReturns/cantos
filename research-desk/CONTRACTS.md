# Contracts and acceptance boundaries

## Research records

A record has a stable `id`, immutable integer `revision`, `kind`, `title`, `summary`, `tier`, `disposition`, `deps`, and `data`. Successors preserve kind. Dependencies pin `{id, revision}`. Missing, duplicate and cyclic dependencies are rejected. `open`, `conflict` and `withdrawn` dispositions block downstream acceptance. A source update does not rewrite a dependent record's pins.

Kinds: source, claim, policy, run, calculation, conclusion, instruments, diligence, mandate. Evidence tiers: public_observation, operator_supplied, synthetic, proposal. These are classifications, not trust scores.

Calculation records support `task-cost@1` only. Their payload must exactly recompute from the pinned policy and run records. Diligence records support `diligence@1` and must recompute from the pinned instruments. Arbitrary manually supplied interpretation belongs in a claim or conclusion. Synthetic inputs cannot be upgraded through these derived calculations.

Reviews bind the current dependency closure, reviewer label, decision and rationale. A changed dependency invalidates that binding. Freezing requires a current accepted review and an exact snapshot; prior snapshots remain historical. Currentness is not truth. An unsupported claim cannot acquire external authority merely because someone typed a name.

## Task run: `second-run/task-run@1`

Use the two complete examples as templates. Each run has identity, evidence class, pins, billing and original tasks. A task has an immutable answer-key object and one or more ordered attempts. Expected fields are scalar strings, finite numbers, booleans or null. All keys, values and the set of fields must match. Monetary strings are appropriate when exact decimal formatting belongs to the contract.

`strict_json` parses the entire trimmed response as one object. `extract_json` accepts one unambiguous JSON object, including inside a fence or prose. Multiple candidate objects refuse. Neither rule executes generated code. A different desired format needs a new explicit grader version, not a silent heuristic.

Each attempt records `status`, `elapsed_ms`, `output` and nullable `cost_usd`. Elapsed time is cumulative since the original task began, including queues and earlier attempts. It must not reset on retry. `timeout` is censored, not a completed task at the threshold. `error` and `refused` do not pass. Only an `ok` attempt that grades correctly within the deadline admits an original task. Multiple correct attempts count once. All recorded charges remain in the numerator.

This implementation models a fixed outcome-per-task benchmark. It does not infer business transaction completion from a returned string. Use an external evaluator or accepted-state record to construct the expected output for real transactional workflows.

Billing holds `actual_total_usd` and `quote_total_usd` separately. Null means missing; zero is permitted when a documented credit or other reconciliation explains it. The total must encompass all attempts and the declared paid interval. It is supplied evidence, not a bank verification. If the paid total is below complete attempt charges without a reconciliation note, the gate holds. Quote cost is never substituted silently for actual spend.

The primary calculation is total supplied USD divided by original tasks passing quality and deadline. Zero accepted tasks or a missing selected total makes it undefined. The sample floor, distinct-task minimum and cost admission must pass before a configuration is eligible. No confidence interval, population error rate, or deployment safety claim is estimated.

Task comparisons require matching `taskset`, `contract`, `load`, `boundary` and exact original-task identities/answer keys. Models may differ. Hardware comparisons additionally match `model`, `revision`, `precision`, `tokenizer`, `runtime`, `cache`. Runs from differing evidence classes are not ranked together. This is a strict comparison rule; intentional mismatches belong in a separately scoped experiment.

Native vLLM summary import preserves serving counts and duration, with quality explicitly unavailable. The generic CSV adapter supplied in the separate original development kit accepts `task_id, expected_json, output, status, elapsed_ms, cost_usd` and a separate run/billing configuration. It does not guess another tool's undocumented semantics. This hosted handoff supplies JSON templates; it does not run the CSV adapter in the browser.

## Diligence case: `second-run/diligence-case@1`

The as-of date governs signed, commenced, unexpired recurring contracts. A source reference must be supplied for inclusion. References are locators provided by the operator, not proof that a referenced contract is authentic or enforceable. Contracts with the same literal counterparty name count as one customer; this is not a beneficial-ownership resolution engine.

Pilots, MOUs, LOIs and terminated/unsigned/future agreements remain visible but do not become recurring consideration. Signed annualized consideration, claimed ARR, reported receipts and accepted deployments are different outputs. Cash includes historical receipts in supplied records even after termination; it is not a current recurring-revenue figure.

Tests have a declared claim, procedure, acceptance condition, result and supporting references. The tool can record a reported pass or fail. It does not execute the test or grant operational acceptance. A pass with no reference is flagged. A successful export test does not satisfy a separate vendor-loss test.

The optional multiple calculation is a sensitivity of two inputs, not a valuation. It deliberately retains the fact that the inputs carry different evidence status.

## Integrity and privacy

The portable envelope contains the entire event journal and a SHA-256 of its canonical JSON. Events hash their predecessor and payload. Import verifies hashes, sequence, revisions, dependencies, derived calculations and reviews through replay before replacing the session.

These are consistency checks, not authentication. A party controlling every byte can construct and hash a new valid history. Keep a trusted earlier hash or packet separately when history assurance matters. This app does not implement AXM Genesis signing, timestamp attestation, institution authentication or a legal evidence chain.

AES-GCM encryption uses a fresh 16-byte salt, 12-byte nonce and PBKDF2-SHA-256 with 250,000 iterations. Passwords require at least 12 characters. A wrong password or altered ciphertext refuses. There is no recovery account. Browser compromise remains outside this protection.

Uploaded HTML is inert text; unsupported binaries receive hashes, not fabricated interpretation. Reports escape entered text. CSV cells beginning with spreadsheet formula characters receive a protective leading apostrophe. Full workspace exports contain entered text and task outputs; application-only copies clear current work data. No automatic persistence or external request exists.
