# One Run 3 native binding

`run3-v3/` retains one unchanged Run 3 card and the three requested receipts:
`binding.json`, `standing.json`, and `applicability.json`.
`run3-v1/` preserves the earlier Genesis-only local-candidate binding. Its signed
policy is unchanged; v2 adds the native Canon candidate-evidence requirement.
v3 binds the later card revision that records the parent's actual local
recomputation. The older records remain unchanged; current-card checks now refuse
their applicability because they bind the earlier revision. This is historical
retention, not a human acceptance or native cross-shard reconciliation chain.

The canonical Genesis compiler created the native `shard/` and its actual
Shard, Claim, Provenance and Span IDs. Three claims record what this card says:
its narrow comparison, 4,336 accepted requests, and 8,622 scheduled requests.
Their exact spans address the compiler's normalized serialization of the card.
`content/card.json` additionally preserves the original selected JSONL row bytes
with one LF terminator. The closure bytes and a dependency/scope record are sealed
alongside it. Larger evidence stays in campaign custody and is checked by digest.
This operation did not rerun grading, inference, or a hardware experiment.

The signature uses a newly generated **local test key**, held only in process
memory. Only its public half is retained. Trusting `local-test.pub` establishes
this local binding; it does not authenticate a publisher or grant publication
trust, independent validation, or human acceptance. Rebuilding creates a new key,
timestamp and Shard ID; it cannot recreate this signature.

The local standing receipt is **filed/candidate**, with no accepting authority.
Its `native_canon` entry identifies the evidence-bundle digest and native
validation receipt. Canon's existing `validateCanonEvidenceBundle` accepts all
three source-bound propositions as `machine-extracted`, with no reviewer. The
same validator rejects marking them `reviewed` without a named reviewer. This is
native evidence-format compatibility, not human reconciliation or admission.
Canon's recall/reconciliation work-order path was not invoked, and no fiction
domain was assigned to compute.
Applicability PASS means that this historical filing still has the exact recorded
period, configuration, acceptance rule and retained dependency bytes. It can pass
while standing remains candidate. `authorized_reuse` remains false. These files
make no present-day capacity, price or repeatability claim.
The applicability receipt identifies the exact card revision, Shard ID and sealed
dependency/scope digest. Its timestamp describes a saved check, not ongoing
applicability; rerun `check` against current retained bytes before relying on it.

From this directory, using the resolved canonical Genesis checkout:

```powershell
python -B join.py check --genesis D:/Projects/Organs/AXM/axm-genesis/main
python -B test_join.py
```

The native verifier is also independently runnable with Genesis installed:

```powershell
python -B -m axm_verify.cli shard run3-v3/shard --trusted-key run3-v3/local-test.pub
```

`native-verifier.json` retains the actual CLI stdout, stderr and exit code.
`canon-validation.json` retains Canon's exact input and actual stdout, stderr and
exit code, including Node's experimental type-erasure warning. Five unmodified
Canon TypeScript sources are pinned to commit
`fec0ddc9a5697d465ac46e55b7e3cb7647221952` and individual SHA-256 values in
`canon_check.mjs`. Source and generated JavaScript live in typed scratch, not in
this repository. No package installation or copied validator is needed.

Fresh native Canon verification with the retained source cache:

```powershell
python -B join.py check --genesis D:/Projects/Organs/AXM/axm-genesis/main --canon S:/Scratch/Runs/run3-shelf-join/canon-fec0ddc9a5697d465ac46e55b7e3cb7647221952
```

To restore that cache on another seat, pass a scratch path to this explicit
download-and-verify command, then supply the same path to `join.py --canon`:

```powershell
node canon_check.mjs --source-root S:/Scratch/Runs/run3-shelf-join/canon-fec0ddc9a5697d465ac46e55b7e3cb7647221952 --bundle run3-v3 --fetch
```

Without `--canon`, `check` validates the retained Canon receipt's linkage; it does
not claim a fresh Canon execution. With it, the source hashes are checked and the
native validator runs again. The evidence-bundle SHA uses the exact UTF-8
`JSON.stringify(input)` bytes emitted by the adapter. Genesis remains the byte
integrity authority; Canon's evidence validator does not itself read source bytes.

Tests mutate disposable copies under `S:/Scratch/Runs/run3-shelf-join`, including
native source tamper, missing binding, changed evaluator dependency, changed
period/evaluator context, invented Claim ID and attempted acceptance by editing
the standing file. They preserve historical bound bytes when applicability fails.

To deliberately create a successor, use `join.py build --genesis <checkout>
--canon <pinned-cache> --output <new-directory>`. Existing output directories are refused. This bounded
adapter has no automatic acceptance or successor-authority transition, no query
layer, and no publication action. Current-card revision changes require a new
binding and renewed checks; historical receipts remain unchanged.
