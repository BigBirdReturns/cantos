# Source-bound EvalPlus grading

The public bridge connects retained streamed application responses to the existing EvalPlus 0.3.1 grader. It prepares exact samples, then binds the independent evaluator output to each run, workload, response and task/trial/repetition identity. It never executes generated solutions. `normalize.py` unwraps one whole-response Python fence or returns raw code unchanged; it performs no repair. Both HumanEval base and plus outcomes must pass. A failed stream remains rejected even when its partial text passes tests.

## Pin the existing grader

Use the existing recipe at `hot-aisle/campaign/run3/grader.Dockerfile`, built through its owner script. Supply a reviewed digest-pinned Python 3.11 CPU base in `BASE_IMAGE`, then run `bash hot-aisle/campaign/run3/grade.sh --build-image`. Record `docker image inspect run3-evalplus:0.3.1` and the installed dependency list retained at `/evalplus-installed.txt`. Set the workload's `grader.artifact_sha256` to the resulting immutable local image ID without the `sha256:` prefix, and use that same image for grading. A different compatible image carries its own identity. The instrument does not infer one build's identity from its version label.

The supported criterion is `humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1`, with `name: EvalPlus` and `revision: 0.3.1`. Set `reference_sha256` from the exact retained HumanEval reference JSONL and `normalizer_sha256` from the trusted normalization file before collecting the workload. The reference's case IDs must equal the declared workload cases. Keep original dataset provenance and license with the reference. The bridge supports single-step complete-code chat tasks and explicitly rejects multi-step or mixed-grader workloads.

The estate qualification used image `sha256:803e956852925ff35f8d7a9f55a97fbcfad09a8dfa77a439f5b2ac537702563d`. That is a retained local image identity, not a public registry address or a requirement to acquire a private artifact.

## Prepare the retained responses

Run from a Cantos checkout. Replace example paths with your retained inputs and new output directories.

```bash
python -B compute/maintainer/evalplus_bridge.py prepare \
  --run /absolute/path/to/baseline/run.json \
  --reference /absolute/path/to/humaneval-reference.jsonl \
  --normalizer compute/maintainer/normalize.py \
  --out /absolute/path/to/baseline-prepared
```

Preparation invokes the instrument's full raw-stream validator, verifies the fixed reference and normalizer hashes, and emits one sample per observation, including capture failures. It preserves the workload, reference, normalized code, exact sample mapping, and a preparation receipt. The source validator's Python files and bridge bytes are pinned; use the same source for binding. `--instrument /absolute/path/to/frozen/source` selects a separate frozen maintainer directory when needed.

## Execute the independent grader

Use the existing owner's bounded container controls. The prepared directory must be absolute and writable by your current user. Set `CANTOS_EVALPLUS_IMAGE` to the immutable local image used in the workload declaration, and `CANTOS_GRADING_DIR` to the prepared directory. Record the command and terminal exit code with the run. The shell trap stops only the named container owned by this invocation, including after a timeout.

```bash
set -euo pipefail
: "${CANTOS_EVALPLUS_IMAGE:?Set the pinned sha256 image identity}"
: "${CANTOS_GRADING_DIR:?Set the absolute prepared directory}"
CANTOS_GRADE_CONTAINER="cantos-maintainer-grader-$$"
docker image inspect "$CANTOS_EVALPLUS_IMAGE" > "$CANTOS_GRADING_DIR/grader-image.json"
trap 'docker stop -t 5 "$CANTOS_GRADE_CONTAINER" >/dev/null 2>&1 || true' EXIT
timeout --signal=TERM --kill-after=30s 2h docker run --rm \
  --name "$CANTOS_GRADE_CONTAINER" \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 512 --memory 8g --cpus 4 --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,exec,size=2g -e HOME=/tmp -e XDG_CACHE_HOME=/tmp/cache \
  -e HUMANEVAL_OVERRIDE_PATH=/work/humaneval-reference.jsonl \
  -v "$CANTOS_GRADING_DIR:/work" -w /work --entrypoint /bin/sh \
  "$CANTOS_EVALPLUS_IMAGE" \
  -ec 'python -c '\''import importlib.metadata as m; assert m.version("evalplus")=="0.3.1"'\''; evalplus.evaluate --dataset humaneval --samples humaneval.jsonl --parallel 4 --min-time-limit 1 --gt-time-limit-factor 4' \
  > "$CANTOS_GRADING_DIR/evalplus.log" 2>&1
```

The runtime has no network, a read-only root, no Linux capabilities, bounded memory/process/CPU resources and an overall timeout. Model-generated Python executes only inside this grader container. Preparation and binding execute the explicitly pinned trusted normalizer, never the generated solution. An evaluator command failure remains a failed attempt; retain its inputs/logs and inspect it before another bounded attempt.

## Bind and analyze

```bash
python -B compute/maintainer/evalplus_bridge.py bind \
  --run /absolute/path/to/baseline/run.json \
  --prepared /absolute/path/to/baseline-prepared \
  --results /absolute/path/to/baseline-prepared/humaneval_eval_results.json \
  --log /absolute/path/to/baseline-prepared/evalplus.log \
  --out /absolute/path/to/baseline-grades

python -B compute/maintainer/maintainer.py analyze \
  --baseline /absolute/path/to/baseline/run.json \
  --candidate /absolute/path/to/candidate/run.json \
  --baseline-grades /absolute/path/to/baseline-grades/grades.json \
  --candidate-grades /absolute/path/to/candidate-grades/grades.json \
  --policy /absolute/path/to/policy.json \
  --out /absolute/path/to/new-graded-analysis
```

Repeat prepare, container and bind for the candidate. Binding recomputes normalization directly from each exact raw answer; validates the run/workload, response and normalizer hashes; recomputes the reference MD5 used by EvalPlus from the pinned reference bytes; requires complete result coverage; and checks exact normalized solution strings and trial/repetition joins. It copies grader inputs, mapping, full evaluator output, log, source run and bridge into the grade receipt's artifact closure. The original raw run retains its own closure. Missing grades, changed raw responses, different solutions, changed validator code or mismatched references produce an error rather than accepted work.

## Regrade an unchanged capture with a new pinned grader

Use a separate JSON grading contract when the independent evaluator image, trusted normalizer or reference changes after collection. Read the original `workload_sha256` from either arm's validated `run.json`. Give both arms the same contract file and use new preparation, grade and analysis directories. The archived workload, observation dates and raw responses stay byte-identical.

```json
{
  "schema": "cantos.maintainer.grading-contract/1",
  "workload_sha256": "<original captured workload SHA-256>",
  "grader": {
    "name": "EvalPlus",
    "revision": "0.3.1",
    "criterion": "humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1",
    "artifact_sha256": "<explicit grader image ID without sha256:>",
    "reference_sha256": "<SHA-256 of the reference JSONL>",
    "normalizer_sha256": "<SHA-256 of the trusted normalizer source>"
  }
}
```

Add `--grading-contract /absolute/path/to/regrade.json` to each arm's `prepare` and `bind` commands and to `analyze`. Grade each prepared sample set with the declared image. The binder retains the exact contract bytes with the new grade receipt. The analyzer checks both grade receipts against that contract and the original run, workload and response hashes. An analysis with only one regraded arm or two different grading bases returns exit 2. Omitting the flag selects the grader pinned in the captured workload. Reuse the original grades and policy to reproduce the original qualification. When exporting a revised analysis to the workbench, the packet retains its original workload SHA and the exact new grading contract. A different grading contract creates a separate workload identity for decision grouping.

The artifact and version fields identify the declared grader, while the retained container image inspection and command log document the actual invocation. When grader-image.json is present, binding requires its observed local image ID to equal the declared image SHA256 and retains it in the artifact closure. It also retains an optional invocation.json. Preserve these environment receipts beside the prepared grading inputs; without the image receipt, image identity remains a declaration. This bridge's integrity checks establish a reproducible join; they are not a remote attestation service. The empirical 32-case subset is a scoped application comparison, not a full 164-case HumanEval score.
