"""Stream the 2026-09-29 imports and print the full-history InferenceX and MLPerf summary tables (markdown).

Counts are source rows (artifact ID + file hash + row index), not metric expansion. Nothing is loaded whole."""
from collections import defaultdict
import json
from pathlib import Path
import sys
from importer import BASE, hardware

INF = BASE / "imported/inferencex-2026-09-29.jsonl"
MLP = BASE / "imported/mlperf-2026-09-29.jsonl"


def inferencex():
    seen, groups, metrics = set(), defaultdict(list), 0
    fails = []
    for line in INF.open(encoding="utf-8"):
        r = json.loads(line)
        metrics += 1
        k = (r["provenance"].get("artifact_id"), r["provenance"]["sha256"], r["row_index"])
        if k in seen:
            continue
        seen.add(k)
        row = (r["num_requests_total"], r["num_requests_successful"], r["power_valid"], r["joules_per_successful_query"])
        groups[(r["hardware"], r["framework"], r["workload"]["scenario"])].append(row)
        if r["outcome"] == "failure":
            fails.append(k)
    return groups, len(seen), metrics, fails


def mlperf():
    seen, groups, metrics = set(), defaultdict(lambda: {"logs": set(), "systems": set(), "models": set(), "rel": set(), "obs": 0, "hold": 0}), 0
    for line in MLP.open(encoding="utf-8"):
        r = json.loads(line)
        metrics += 1
        p = r["provenance"]
        g = groups[(hardware(r["hardware"]) if r["hardware"] != "N/A" else "N/A (no accelerator)", r["workload"]["scenario"])]
        g["logs"].add(p["path"] + "@" + p["release"])
        g["systems"].add(r["config"].get("system_id", p["path"].split("/")[2]) + "@" + p["release"])
        g["models"].add(r["model"])
        g["rel"].add(p["release"])
        g["obs"] += 1
        g["hold"] += 1 if r.get("comparison_hold") else 0
        seen.add(p["path"] + "@" + p["release"])
    return groups, len(seen), metrics


def main():
    groups, nrows, nmetrics, fails = inferencex()
    arts = json.loads((BASE / "imported/history-index.json").read_text())
    empty = sum(1 for v in arts.values() if v["source_rows"] == 0)
    o = ["## Full history, 2026-09-29 (InferenceX results_bmk)", "",
         "**Imported external observations; not our measurements or qualified results.**", "",
         f"{len(arts)} artifacts; {nrows} source rows; {nmetrics} metric observations. {empty} empty aggregate files retained in the manifest "
         f"(data-raw/import-manifest-2026-09-29.json). {len(fails)} zero-success/failure rows retained with comparison_hold. "
         "Prior sample (Sept 23 section below): 100 artifacts, 198 rows, 3620 observations.", "",
         "Same conventions as the Sept 23 table: counts are source rows; success = sum(successful)/sum(total) over rows with both counts "
         "(agentic totals include warmup drops, not an error rate); energy ranges use only power_valid=1 rows with a reported J/query. "
         "Hardware is normalized from hw strings (CLUSTER:B200 -> B200). Flat early-July agentic rows carry mean/p90/p95 latency only, "
         "with seconds assumed.", "",
         "| Hardware | Framework | Scenario | Rows | Successful / total | Success rate | Valid energy rows | J/successful query range |",
         "|---|---|---|---:|---:|---:|---:|---:|"]
    for (hw, fw, sc), rows in sorted(groups.items()):
        c = [r for r in rows if r[0] is not None and r[1] is not None]
        t, s = sum(r[0] for r in c), sum(r[1] for r in c)
        e = [r[3] for r in rows if r[2] == 1 and r[3] is not None]
        o.append(f"| {hw} | {fw} | {sc} | {len(rows)} | {f'{s} / {t}' if c else 'unknown'} | {f'{s / t:.2%}' if t else 'undefined'} | "
                 f"{len(e)} | {f'{min(e):.3f}–{max(e):.3f}' if e else 'unknown'} |")
    o += ["", f"{len(groups)} hardware x framework x scenario groups.", ""]
    g, nlogs, nmet = mlperf()
    o += ["## MLPerf Inference v4.0, v4.1, v5.0, v5.1 (LLM LoadGen summaries), 2026-09-29", "",
          "**Imported external observations; not our measurements or qualified results.**", "",
          f"{nlogs} performance-run summaries (all `Result is : VALID`); {nmet} metric observations, from imported/mlperf-2026-09-29.jsonl "
          "(lane rows, unchanged). Validity is LoadGen validity only; accuracy and compliance were not evaluated. Hardware is the importer's SKU token "
          "where one matches, else the submitted accelerator string; GB200/GB300 are separate from B200. Systems are counted per release. "
          "Held = observations carrying comparison_hold (inferred throughput, open division).", "",
          "| Hardware | Scenario | Summaries | Systems | Models | Releases | Observations | Held |", "|---|---|---:|---:|---:|---|---:|---:|"]
    for (hw, sc), v in sorted(g.items()):
        o.append(f"| {hw} | {sc} | {len(v['logs'])} | {len(v['systems'])} | {len(v['models'])} | {', '.join(sorted(v['rel']))} | {v['obs']} | {v['hold']} |")
    o += ["", f"{len(g)} hardware x scenario groups.", ""]
    print("\n".join(o))
    (BASE / "imported/.failures-2026-09-29.txt").write_text(", ".join(f"{a}:{i}" for a, _, i in fails) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
