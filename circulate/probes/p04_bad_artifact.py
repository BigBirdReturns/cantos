"""p04: truncated JSON, empty list and tp:0 artifacts through the backfill importer; loud refusal or null count with a rule, never a fabricated count."""
import json
from _common import *  # noqa

NAME = "p04_bad_artifact"
BACKFILL_REL = "hot-aisle/campaign/backfill"


def manifest_for(work, tag, raw: bytes, artifact_id):
    d = work / tag
    d.mkdir(parents=True, exist_ok=True)
    (d / "artifact.json").write_bytes(raw)
    m = {"schema": "backfill-manifest@1", "fixture": True, "files": [{
        "artifact_id": artifact_id, "created_at": "2026-09-29T00:00:00Z", "head_sha": "0" * 40, "source": "inferencemax",
        "path": "artifact.json", "url": "https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/%d" % artifact_id,
        "revision": "0" * 40, "retrieved_at": "2026-09-29T00:00:00Z", "observed_at": None, "sha256": sha256_bytes(raw)}]}
    write_json(d / "manifest.json", m)
    return d


def importer(root, d):
    out = d / "out.jsonl"
    rc, so, se = run_cmd(["python", root / BACKFILL_REL / "importer.py", "--manifest", d / "manifest.json", "--offline", "--output", out],
                         cwd=root / BACKFILL_REL, timeout=120)
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()] if out.exists() else None
    return rc, se.strip(), rows


def body(ctx, work):
    root = ctx_root(ctx)
    good = json.loads((root / BACKFILL_REL / "fixtures/authored-inferencemax.json").read_text(encoding="utf-8"))
    obs = {}

    # control: the untouched fixture row imports and gets a GPU count with a rule
    d = manifest_for(work, "control", json.dumps(good).encode(), 9001)
    rc, se, rows = importer(root, d)
    need(rc == 0 and rows, "control fixture did not import: rc=%s %s" % (rc, se))
    obs["control"] = {"exit": rc, "rows": len(rows), "gpus": rows[0]["gpus"], "gpu_count_rule": rows[0]["gpu_count_rule"]}

    # 1. truncated JSON (sha256 recomputed over the truncated bytes, so provenance checks pass and only the parser can object)
    raw = json.dumps(good).encode()
    d = manifest_for(work, "truncated", raw[: len(raw) // 2], 9002)
    rc, se, rows = importer(root, d)
    need(rc != 0 and se.startswith("import failed"), "truncated JSON was not refused loudly: rc=%s %r" % (rc, se))
    need(not rows, "truncated JSON produced rows")
    obs["truncated_json"] = {"exit": rc, "stderr": se[:160], "rows": 0}

    # 2. empty list
    d = manifest_for(work, "empty", b"[]", 9003)
    rc, se, rows = importer(root, d)
    need(rc != 0 or not rows, "empty list produced rows: %r" % (rows and len(rows)))
    obs["empty_list"] = {"exit": rc, "stderr": se[:160], "rows_emitted": 0 if not rows else len(rows),
                         "behaviour": "refused" if rc != 0 else "accepted with zero rows (no observations, no counts)"}

    # 3. tp:0 artifact (and num_gpus:0 variant): GPU count must degrade to null with a stated rule, never 0 or a product of zeros
    for tag, mut in (("tp0", {"tp": 0}), ("num_gpus0", {"num_gpus": 0})):
        r = dict(good[0]); r.update(mut)
        d = manifest_for(work, tag, json.dumps([r]).encode(), 9004 if tag == "tp0" else 9005)
        rc, se, rows = importer(root, d)
        if rc != 0:
            obs[tag] = {"exit": rc, "stderr": se[:160], "behaviour": "refused"}
            continue
        need(rows, tag + ": exit 0 with no rows and no message")
        need(all(x["gpus"] is None for x in rows), tag + ": fabricated a GPU count: %r" % {x["gpus"] for x in rows})
        need(all("UNVERIFIED" in x["gpu_count_rule"] for x in rows), tag + ": null count carries no rule: %r" % rows[0]["gpu_count_rule"])
        obs[tag] = {"exit": rc, "rows": len(rows), "gpus": None, "gpu_count_rule": rows[0]["gpu_count_rule"], "behaviour": "null count with rule"}

    # 4. impossible counts / measurements must be refused
    for tag, mut in (("successful_gt_total", {"num_requests_total": 10, "num_requests_successful": 11}),
                     ("negative_measurement", {"output_tput_per_gpu": -5}),
                     ("nan_measurement", {"output_tput_per_gpu": "nan"})):
        r = dict(good[0]); r.update(mut)
        d = manifest_for(work, tag, json.dumps([r]).encode(), 9010 + len(obs))
        rc, se, rows = importer(root, d)
        need(rc != 0 and not rows, "%s was not refused (rc=%s rows=%s)" % (tag, rc, rows and len(rows)))
        obs[tag] = {"exit": rc, "stderr": se[:120]}
    return {
        "observed": obs,
        "expected": "importer refuses (nonzero exit, 'import failed') or emits a null GPU count carrying the UNVERIFIED rule; no fabricated count in any case",
        "notes": "Runs hot-aisle/campaign/backfill/importer.py as a subprocess against temp manifests (offline, fixture=true) so the real imported/ files are untouched. "
                 "Every bad artifact's sha256 is recomputed so provenance checks pass and only the artifact content is on trial. "
                 "Finding: an empty [] artifact exits 0 with zero rows and no message (quiet, not loud); it invents nothing, and summarize.py lists such artifacts as 'empty aggregate files' from the manifest.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
