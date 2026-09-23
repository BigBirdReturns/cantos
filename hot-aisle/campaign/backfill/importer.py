"""Pinned, stdlib-only historical inference imports. See README.md."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import urllib.request
import urllib.parse

BASE = Path(__file__).resolve().parent
UNKNOWN = "UNVERIFIED"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def number(value, positive=False):
    if isinstance(value, bool):
        raise ValueError("boolean is not a measurement")
    n = float(value)
    if not math.isfinite(n) or n < 0 or (positive and n == 0):
        raise ValueError("measurement must be finite and nonnegative (positive denominator)")
    return n


def hardware(value):
    found = re.search(r"(?<![A-Z0-9])(MI300X|MI325X|MI355X|H100|H200|GB200|GB300|B200|B300)(?![A-Z0-9])", str(value).upper())
    return found.group(1) if found else str(value or UNKNOWN)


def model_class(value):
    s = str(value).lower()
    if "llama" in s and "70b" in s:
        return "dense-70b-llama"
    if "qwen3-coder-30b-a3b" in s:
        return "moe-30b-3b-qwen-coder"
    return None


def precision(value):
    s = str(value).upper()
    return next((p for p in ("MXFP4", "NVFP4", "FP8", "BF16", "FP16", "INT8", "INT4") if p in s), s)


def stamp(value):
    t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("retrieved_at must include timezone")
    return t


def local_path(root, name):
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError("file must remain under manifest directory")
    return p


def acquire(entry, root, offline, fixture):
    """Cache and original retrieval time are manifest-bound; never refresh silently."""
    for key in ("url", "revision", "retrieved_at", "sha256", "path"):
        if not entry.get(key):
            raise ValueError("missing provenance: " + key)
    stamp(entry["retrieved_at"])
    if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
        raise ValueError("expected SHA-256 required")
    if not fixture and (entry["revision"] == UNKNOWN or entry["revision"] in ("main", "master", "latest")):
        raise ValueError("pin a source commit or release tag")
    p = local_path(root, entry["path"])
    receipt_path = p.with_name(p.name + ".retrieval.json")
    if p.exists():
        raw = p.read_bytes()
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_bytes())
            if any(receipt.get(k) != entry[k] for k in ("url", "revision", "sha256")):
                raise ValueError("cached retrieval receipt does not match manifest")
            stamp(receipt["retrieved_at"])
            entry["retrieved_at"] = receipt["retrieved_at"]
    else:
        if offline:
            raise ValueError("offline cache miss: " + entry["path"])
        parsed = urllib.parse.urlsplit(entry["url"])
        if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com" or parsed.username or parsed.password:
            raise ValueError("live fetch accepts only public raw.githubusercontent.com HTTPS files; use local drop-box for artifacts")
        if entry["revision"] not in parsed.path.split("/"):
            raise ValueError("URL must contain the pinned revision")
        # Do not inherit ambient proxy credentials, auth headers, or cookies.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(entry["url"], timeout=30) as response:
            if urllib.parse.urlsplit(response.geturl()).hostname != parsed.hostname:
                raise ValueError("unexpected download redirect")
            raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("raw file exceeds 64 MiB limit; split/select source files")
        if digest(raw) != entry["sha256"]:
            raise ValueError("download SHA-256 mismatch")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        entry["retrieved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        receipt_path.write_text(json.dumps({k: entry[k] for k in ("url", "revision", "sha256", "retrieved_at")}, indent=2) + "\n", encoding="utf-8")
    if digest(raw) != entry["sha256"]:
        raise ValueError("raw SHA-256 mismatch: " + entry["path"])
    return raw


def base_record(entry, raw, index, manifest_hash, fixture):
    return {"schema": "imported-observation@1", "tier": "imported", "fixture": fixture,
            "source": entry["source"], "provenance": {k: entry[k] for k in ("url", "revision", "retrieved_at")},
            "config": {}, "warnings": [], "observed_at": entry.get("observed_at"),
            "row_index": index, "manifest_sha256": manifest_hash,
            "model_revision": UNKNOWN, "image_digest": UNKNOWN,
            "framework_version": UNKNOWN, "backend": UNKNOWN, "gates": UNKNOWN}


def emit(base, raw, metrics):
    result = []
    for name, value, units in metrics:
        row = copy.deepcopy(base)
        row["provenance"]["sha256"] = digest(raw)
        row["metric"] = {"name": name, "value": number(value), "units": units}
        row["id"] = digest(json.dumps(row, sort_keys=True, allow_nan=False).encode())
        result.append(row)
    if not result:
        raise ValueError("no supported metrics; source schema may have changed")
    return result


def count(value, positive=False):
    n = number(value, positive)
    if not n.is_integer():
        raise ValueError("count must be integral")
    return int(n)


def gpu_count(src):
    """Physical allocation, never TP multiplied by overlapping EP/DCP."""
    for key in ("num_gpus", "num_aggregate_gpu"):
        if src.get(key) is not None:
            return count(src[key], True), key
    if all(src.get(k) is not None for k in ("num_prefill_gpu", "num_decode_gpu")):
        return count(count(src["num_prefill_gpu"]) + count(src["num_decode_gpu"]), True), "num_prefill_gpu + num_decode_gpu"
    if not src.get("is_multinode") and not src.get("disagg") and all(k in src for k in ("tp", "pp")):
        return count(src["tp"], True) * count(src["pp"], True) * count(src.get("pcp_size", 1), True), "tp * pp * pcp_size (single-node)"
    return None, UNKNOWN


def inferencemax(entry, raw, manifest_hash, fixture):
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError("expected InferenceX agg_bmk.json list")
    out = []
    for i, src in enumerate(rows):
        if not isinstance(src, dict) or any(k not in src for k in ("hw", "model", "precision", "framework", "conc")):
            raise ValueError("expected InferenceX aggregate row identity")
        scenario = src.get("scenario_type", "fixed-sequence")
        if scenario not in ("fixed-sequence", "agentic-coding"):
            raise ValueError("unsupported InferenceX scenario")
        r = base_record(entry, raw, i, manifest_hash, fixture)
        r["provenance"].update({k: entry.get(k) for k in ("artifact_id", "workflow_run_id", "head_sha", "created_at")})
        r.update(hardware=hardware(src["hw"]), model=src["model"], model_class=model_class(src["model"]),
                 precision=precision(src["precision"]), precision_detail=src["precision"], framework=src["framework"],
                 config=src, data_kind="per-run-summary")
        r["gpus"], r["gpu_count_rule"] = gpu_count(src)
        r["workload"] = {"input_tokens": count(src["isl"], True) if scenario == "fixed-sequence" else None,
                         "output_tokens": count(src["osl"], True) if scenario == "fixed-sequence" else None,
                         "concurrency": count(src["conc"], True), "dataset": src.get("dataset", UNKNOWN),
                         "scenario": scenario, "request_rate": src.get("request_rate", UNKNOWN)}
        for key in ("framework_version", "backend", "gates", "model_revision"):
            r[key] = src.get(key, UNKNOWN)
        image = src.get("image", "")
        r["image_digest"] = image if re.search(r"@sha256:[a-f0-9]{64}$", image) else UNKNOWN
        r["warnings"] = ["Imported summary: no buyer cost, correctness or traversal claim."]
        outcome = src.get("benchmark_outcome", {})
        total = src.get("num_requests_total", outcome.get("requested"))
        successful = src.get("num_requests_successful", outcome.get("completed"))
        r["num_requests_total"] = count(total) if total is not None else None
        r["num_requests_successful"] = count(successful) if successful is not None else None
        if total is not None and successful is not None and r["num_requests_successful"] > r["num_requests_total"]:
            raise ValueError("successful exceeds total requests")
        r["success_rate"] = r["num_requests_successful"] / r["num_requests_total"] if r["num_requests_total"] and successful is not None else None
        r["request_accounting"] = src.get("request_accounting", outcome or None)
        r["request_count_basis"] = "num_requests_* (includes warmup drops)" if "num_requests_total" in src else "benchmark_outcome requested/completed"
        r["outcome"] = "failure" if successful == 0 or outcome.get("status") in ("failed", "failure") else "reported"
        if r["outcome"] == "failure":
            r["comparison_hold"] = "source reports failure or zero successful requests"
        elif outcome and outcome.get("status") != "passed":
            r["comparison_hold"] = "benchmark_outcome requires manual review"
        if scenario == "agentic-coding":
            r["warnings"].append("Success rate is profiled/total records; warmup drops are not necessarily request errors.")
        for key in ("avg_power_w", "avg_total_gpu_power_w", "total_gpu_energy_j", "joules_per_successful_query", "joules_per_output_token"):
            r[key] = number(src[key]) if src.get(key) is not None else None
        r["power_valid"] = src.get("power_valid")
        r["power_invalid_reasons"] = src.get("power_invalid_reasons", [])
        metrics = []
        def add(name, value, units, factor=1):
            if value is not None:
                metrics.append((name, number(value) * factor, units))
        if scenario == "fixed-sequence":
            for key, name, units in (("output_tput_per_gpu", "output_throughput_per_gpu", "tokens/s/GPU"),
                                     ("tput_per_gpu", "total_token_throughput_per_gpu", "tokens/s/GPU"),
                                     ("request_throughput", "request_throughput", "requests/s")):
                add(name, src.get(key), units)
            for metric in ("ttft", "e2el", "itl", "tpot"):
                for stat in ("mean", "median", "p90", "p95", "p99"):
                    add(stat + "_" + metric + "_ms", src.get(stat + "_" + metric), "ms", 1000)
        else:
            rm = src["request_metrics"]
            for metric in ("ttft", "e2el", "itl", "tpot"):
                for stat in ("mean", "p50", "p90", "p95", "p99"):
                    add(("median" if stat == "p50" else stat) + "_" + metric + "_ms",
                        rm.get("latency", {}).get(metric, {}).get(stat), "ms", 1000)
            throughput = rm.get("throughput", {})
            add("output_throughput", throughput.get("output", {}).get("tokens_per_second"), "tokens/s")
            for key, name in (("output_tput_tps", "output_throughput_per_gpu"), ("total_tput_tps", "total_token_throughput_per_gpu")):
                add(name, throughput.get("per_gpu", {}).get(key), "tokens/s/GPU")
            # QPS window mean is retained separately, not equated with whole-run throughput.
            add("window_mean_qps", rm.get("qps", {}).get("mean"), "requests/s")
        add("successful_requests", successful, "requests")  # keeps zero-success rows with no timing data
        if not metrics:
            raise ValueError("row has neither supported metrics nor request counts")
        out.extend(emit(r, raw, metrics))
    return out


def raw_manifest(root, retrieved_at):
    """Build provenance from operator-supplied index and fetch_history sidecars."""
    root = Path(root)
    index = {}
    old = root / "index-100.txt"
    if old.exists():
        for line in old.read_text(encoding="utf-8-sig").splitlines():
            ident, created, sha = line.split()
            index[ident] = {"artifact_id": int(ident), "created_at": created, "head_sha": sha}
    latest = root / "latest.txt"
    if latest.exists():
        for line in latest.read_text(encoding="utf-8-sig").splitlines():
            ident, created, size, sha, run = line.split()
            index.setdefault(ident, {}).update(artifact_id=int(ident), created_at=created, head_sha=sha, workflow_run_id=int(run))
    files = []
    for path in sorted(root.glob("results_bmk_*/agg_bmk.json")):
        ident = path.parent.name.removeprefix("results_bmk_")
        meta = dict(index.get(ident, {}))
        sidecar = path.parent / "artifact.json"
        if sidecar.exists():
            fetched = json.loads(sidecar.read_bytes())
            meta.update(fetched)
        if not meta.get("head_sha") or not meta.get("created_at"):
            raise ValueError("missing artifact index provenance: " + ident)
        raw = path.read_bytes()
        if meta.get("sha256") and meta["sha256"] != digest(raw):
            raise ValueError("artifact receipt SHA-256 mismatch: " + ident)
        files.append(dict(meta, source="inferencemax", path=path.relative_to(root).as_posix(),
                          url="https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts/" + ident,
                          revision=meta["head_sha"], retrieved_at=meta.get("retrieved_at", retrieved_at),
                          observed_at=None, sha256=digest(raw)))
    if not files:
        raise ValueError("no agg_bmk.json files")
    return {"schema": "backfill-manifest@1", "fixture": False, "files": files}


def mlperf(entry, raw, manifest_hash, fixture):
    fields = {}
    for line in raw.decode("utf-8-sig").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    if fields.get("Result is") != "VALID":
        raise ValueError("MLPerf performance log must declare Result is : VALID")
    scenario = fields.get("Scenario")
    if scenario not in ("Offline", "Server", "SingleStream", "MultiStream"):
        raise ValueError("unsupported MLPerf scenario")
    metadata = entry.get("metadata", {})
    r = base_record(entry, raw, 0, manifest_hash, fixture)
    for key in ("hardware", "gpus", "model", "precision", "framework", "framework_version", "backend", "model_revision", "image_digest"):
        r[key] = metadata.get(key, UNKNOWN if key != "gpus" else None)
    r["hardware"] = hardware(r["hardware"])
    r["model_class"] = model_class(r["model"])
    r["precision_detail"] = r["precision"]
    r["precision"] = precision(r["precision"])
    if r["gpus"] is not None:
        r["gpus"] = number(r["gpus"], True)
        if not r["gpus"].is_integer():
            raise ValueError("GPU count must be integral")
    r["workload"] = {"scenario": scenario, "dataset": metadata.get("dataset", "MLPerf; dataset revision UNVERIFIED"),
                     "input_tokens": None, "output_tokens": None, "concurrency": None, "request_rate": None}
    r["gates"] = "MLPerf source validity; not our latency or correctness gates"
    r["data_kind"] = "per-run-summary"
    r["config"] = {"loadgen": fields, "declared_metadata": metadata, "metadata_evidence": entry.get("metadata_evidence", [])}
    r["warnings"] = ["Metadata is curator-supplied; manifest hash binds declarations, not their truth.",
                     "LoadGen validity alone is not accuracy/compliance verification.",
                     "Variable dataset lengths and offered load are not random fixed-length concurrency cells."]
    metrics = []
    for key, name, units in (
        ("Tokens per second", "output_throughput", "tokens/s"),
        ("Completed tokens per second", "output_throughput", "tokens/s"),
        ("Tokens per second (inferred)", "inferred_output_throughput", "tokens/s"),
        ("Completed tokens per second (inferred)", "inferred_output_throughput", "tokens/s"),
        ("Samples per second", "sample_throughput", "samples/s"),
        ("Completed samples per second", "sample_throughput", "samples/s"),
        ("99.00 percentile latency (ns)", "p99_latency_ns", "ns")):
        if key in fields:
            metrics.append((name, fields[key], units))
    return emit(r, raw, metrics)


def import_manifest(path, offline=False):
    path = Path(path)
    raw_manifest = path.read_bytes()
    manifest = json.loads(raw_manifest)
    if manifest.get("schema") != "backfill-manifest@1" or not manifest.get("files"):
        raise ValueError("expected nonempty backfill-manifest@1")
    fixture = manifest.get("fixture", False)
    if not isinstance(fixture, bool):
        raise ValueError("fixture must be boolean")
    out = []
    for entry in manifest["files"]:
        adapter = {"inferencemax": inferencemax, "mlperf": mlperf}.get(entry["source"])
        if not adapter:
            raise ValueError("unsupported source")
        raw = acquire(entry, path.parent, offline, fixture)
        out.extend(adapter(entry, raw, digest(raw_manifest), fixture))
    if len({r["id"] for r in out}) != len(out):
        raise ValueError("duplicate imported observations")
    return out


def self_test():
    import unittest
    suite = unittest.defaultTestLoader.discover(str(BASE), pattern="test_*.py")
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--raw-dir", type=Path)
    p.add_argument("--retrieved-at", help="original download timestamp, required with --raw-dir")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if a.raw_dir and (a.manifest or not a.retrieved_at):
        p.error("--raw-dir requires --retrieved-at and excludes --manifest")
    if not a.raw_dir and not a.manifest:
        p.error("--manifest or --raw-dir is required")
    try:
        if a.raw_dir:
            stamp(a.retrieved_at)
            a.manifest = a.raw_dir / "import-manifest.json"
            a.manifest.write_text(json.dumps(raw_manifest(a.raw_dir, a.retrieved_at), indent=2) + "\n", encoding="utf-8")
            a.offline = True
        rows = import_manifest(a.manifest, a.offline)
        content = "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows)
        if a.output:
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("import failed: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
