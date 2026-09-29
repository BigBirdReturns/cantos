"""p10: the same bytes under two artifact ids: two provenance rows; source rows deduped by (artifact_id, sha256, row_index) only."""
import json
import shutil
import sys
from _common import *  # noqa

NAME = "p10_dup_artifact"
BACKFILL_REL = "hot-aisle/campaign/backfill"


def entry(artifact_id, path, raw, created):
    return {"artifact_id": artifact_id, "created_at": created, "head_sha": "1" * 40, "source": "inferencemax", "path": path,
            "url": "https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/%d" % artifact_id,
            "revision": "1" * 40, "retrieved_at": "2026-09-29T00:00:00Z", "observed_at": None, "sha256": sha256_bytes(raw)}


def body(ctx, work):
    root = ctx_root(ctx)
    bf = root / BACKFILL_REL
    raw = (bf / "fixtures/authored-inferencemax.json").read_bytes()
    n_src = len(json.loads(raw))
    (work / "a.json").write_bytes(raw)
    (work / "b.json").write_bytes(raw)   # identical bytes, second artifact id
    man = {"schema": "backfill-manifest@1", "fixture": True,
           "files": [entry(7001, "a.json", raw, "2026-09-28T00:00:00Z"), entry(7002, "b.json", raw, "2026-09-29T00:00:00Z")]}
    write_json(work / "manifest.json", man)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(bf))
    try:
        import importer, summarize
        rows = importer.import_manifest(work / "manifest.json", offline=True)
        per_id = {}
        for r in rows:
            per_id.setdefault(r["provenance"]["artifact_id"], []).append(r)
        need(set(per_id) == {7001, 7002}, "expected provenance rows for both artifact ids, got %r" % sorted(per_id))
        need(len(per_id[7001]) == len(per_id[7002]) and len(rows) == 2 * len(per_id[7001]), "artifact ids yielded unequal row counts")
        need(len({r["id"] for r in rows}) == len(rows), "observation ids collided across the two artifacts")
        need({r["provenance"]["sha256"] for r in rows} == {sha256_bytes(raw)}, "expected a single content hash across both artifacts")
        # the summarize key (artifact_id, sha256, row_index): two artifacts -> 2 x source rows, not merged on sha256 alone
        key = lambda r: (r["provenance"].get("artifact_id"), r["provenance"]["sha256"], r["row_index"])
        unique = {key(r) for r in rows}
        by_sha_only = {(r["provenance"]["sha256"], r["row_index"]) for r in rows}
        need(len(unique) == 2 * n_src, "expected %d source rows under (artifact_id, sha256, row_index), got %d" % (2 * n_src, len(unique)))
        need(len(by_sha_only) == n_src, "control: sha256-only dedup should collapse to %d" % n_src)
        report = {"comparable_source_rows": 0, "measured_cells": 0, "comparable_observations": 0, "gaps": []}
        text = summarize.summarize(rows, json.loads((work / "manifest.json").read_bytes()), report)
        line = next(x for x in text.splitlines() if "source rows;" in x)
        need("%d source rows" % (2 * n_src) in line, "summarize.py counted differently: %r" % line)
        # same artifact id + same bytes listed twice (a real duplicate): the key collapses it
        same = dict(man, files=[entry(7001, "a.json", raw, "2026-09-28T00:00:00Z"), dict(entry(7001, "b.json", raw, "2026-09-28T00:00:00Z"),
                    url="https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/7001?dup=1")])
        write_json(work / "manifest2.json", same)
        rows2 = importer.import_manifest(work / "manifest2.json", offline=True)
        unique2 = {key(r) for r in rows2}
        need(len(unique2) == n_src, "true duplicate (same id, same bytes) should collapse to %d source rows, got %d" % (n_src, len(unique2)))
    finally:
        sys.path.remove(str(bf))
        for m in ("importer", "summarize"):
            sys.modules.pop(m, None)
    return {
        "observed": {"source_rows_per_artifact": n_src, "provenance_artifact_ids": sorted(per_id),
                     "observations_total": len(rows), "distinct_observation_ids": len({r["id"] for r in rows}),
                     "source_rows_by_artifact_sha_row": len(unique), "source_rows_by_sha_only_(control)": len(by_sha_only),
                     "summarize_line": line.strip(), "same_id_same_bytes_source_rows": len(unique2)},
        "expected": "two artifact ids over identical bytes keep two provenance rows (2 x %d source rows); only an identical (artifact_id, sha256, row_index) collapses" % n_src,
        "notes": "importer.import_manifest and summarize.summarize called in-process on a temp manifest. The sha256-only count is reported as a control to show the key matters.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
