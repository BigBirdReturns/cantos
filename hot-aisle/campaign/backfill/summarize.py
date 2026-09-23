"""Summarize imported source rows once each, never counting metric expansion as runs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from importer import BASE, self_test


def summarize(rows, manifest, report):
    unique = {}
    for r in rows:
        key = (r["provenance"].get("artifact_id"), r["provenance"]["sha256"], r["row_index"])
        unique.setdefault(key, r)
    groups = defaultdict(list)
    for r in unique.values():
        groups[(r["hardware"], r["framework"], r["workload"]["scenario"])].append(r)
    represented = {r["provenance"].get("artifact_id") for r in unique.values()}
    empty = [e["artifact_id"] for e in manifest["files"] if e["artifact_id"] not in represented]
    failures = [r for r in unique.values() if r["outcome"] == "failure"]
    retrieval_times = sorted({e["retrieved_at"] for e in manifest["files"]})
    known_runs = sum(e.get("workflow_run_id") is not None for e in manifest["files"])
    fixture_notice = " FIXTURE INPUT: test output only." if any(r.get("fixture") for r in rows) else ""
    lines = ["# InferenceX import summary", "", "**Imported external observations; not our measurements or qualified results." + fixture_notice + "**", "",
             f"{len(manifest['files'])} artifacts; {len(unique)} source rows; {len(rows)} metric observations. "
             f"{len(empty)} empty aggregate files are retained in the manifest. {len(failures)} zero-success/failure rows retained.", "",
             "Declared retrieval times: " + ", ".join(retrieval_times) + ". "
             "The initial 2026-09-23 23:40 UTC download time is approximate, supplied by the operator; it is not a measurement timestamp. "
             f"{known_runs} artifact entries have workflow run IDs; missing IDs remain null. "
             "Initial artifact IDs, creation times and head SHAs come from index-100.txt, with run IDs from latest.txt. "
             "Subsequent fetches use artifact sidecars. Every aggregate is SHA-256 bound in the import manifest.", "",
             "Counts below are source rows (artifact ID + file hash + row index), not the expanded metric records. "
             "Request success is sum(successful)/sum(total) over rows with both counts. "
             "Agentic totals include warmup drops: the complement of this ratio is not an error rate or correctness rate. "
             "Ranges use only power_valid=1 rows with a reported J/query; missing/invalid power is not zero.", "",
             "| Hardware | Framework | Scenario | Rows | Successful / total | Success rate | Valid energy rows | J/successful query range |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for (hw, framework, scenario), members in sorted(groups.items()):
        counted = [r for r in members if r["num_requests_total"] is not None and r["num_requests_successful"] is not None]
        total = sum(r["num_requests_total"] for r in counted)
        successful = sum(r["num_requests_successful"] for r in counted)
        energy = [r["joules_per_successful_query"] for r in members if r["power_valid"] == 1 and r["joules_per_successful_query"] is not None]
        rate = f"{successful/total:.2%}" if total else "undefined"
        bounds = f"{min(energy):.3f}–{max(energy):.3f}" if energy else "unknown"
        counts = f"{successful} / {total}" if counted else "unknown"
        lines.append(f"| {hw} | {framework} | {scenario} | {len(members)} | {counts} | {rate} | {len(energy)} | {bounds} |")
    lines += ["", f"Comparable source rows: **{report['comparable_source_rows']} / {len(unique)}** against "
              f"{report['measured_cells']} retained campaign cells. Comparable metric observations: "
              f"{report['comparable_observations']}; ratios: {len(report['gaps'])}. "
              "See imported/delta-2026-09-23.json for each observation's nearest-cell blockers.", "",
              "History selection: MI300X/H100/H200, vllm/sglang, fixed sequence 2048/256 or 8192/512. "
              "Then require FP8, one physical GPU, matching concurrency and Qwen3-Coder-30B-A3B or Llama-3.3-70B identity/class. "
              "H200 supplies context only: our retained campaign has no measured H200 arm. "
              "A sglang match remains a runtime-different contextual comparison. Dataset, model/image pins and gates still need review.", "",
              "Suggested bounded history command (not run here):", "", "```text",
              "python -B hot-aisle/campaign/backfill/fetch_history.py --max 100 --hardware MI300X --hardware H100 --hardware H200 --framework vllm --framework sglang --shape 2048/256 --shape 8192/512",
              "```", "", "Repeat the same command to resume; after completion use --restart to discover new arrivals. "
              "Filtering records matching row indices after download; it preserves whole artifacts and failures.", "",
              "Empty artifact IDs: " + ", ".join(map(str, empty)) + ".", "",
              "Failure rows (artifact:row, successful/total): " + ", ".join(
                  f"{r['provenance']['artifact_id']}:{r['row_index']} ({r['num_requests_successful']}/{r['num_requests_total']})" for r in failures) + ".", "",
              "Model revisions remain UNVERIFIED unless supplied. Image digests are copied only when present; "
              "they were not independently fetched. No live GitHub calls or new benchmarks were run."]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--imports", type=Path, default=BASE / "imported/inferencex-2026-09-23.jsonl")
    p.add_argument("--manifest", type=Path, default=BASE / "data-raw/import-manifest.json")
    p.add_argument("--delta", type=Path, default=BASE / "imported/delta-2026-09-23.json")
    p.add_argument("--output", type=Path, default=BASE / "IMPORT-SUMMARY.md")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    rows = [json.loads(line) for line in a.imports.read_text(encoding="utf-8").splitlines() if line.strip()]
    a.output.write_text(summarize(rows, json.loads(a.manifest.read_bytes()), json.loads(a.delta.read_bytes())), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
