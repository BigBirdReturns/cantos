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
    found = re.search(r"(?<![A-Z0-9])(MI300X|MI325X|MI355X|H100|H200|B200)(?![A-Z0-9])", str(value).upper())
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


def inferencemax(entry, raw, manifest_hash, fixture):
    payload = json.loads(raw)
    rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        raise ValueError("empty InferenceX artifact")
    out = []
    for i, src in enumerate(rows):
        if not isinstance(src, dict) or any(k not in src for k in ("hw", "model", "precision", "framework", "isl", "osl", "conc")):
            raise ValueError("expected fixed-sequence InferenceX aggregate row")
        if src.get("scenario_type") == "agentic-coding" or src.get("request_metrics"):
            raise ValueError("AgentX is a different workload; unsupported")
        r = base_record(entry, raw, i, manifest_hash, fixture)
        r.update(hardware=hardware(src["hw"]), model=src["model"], model_class=model_class(src["model"]),
                 precision=precision(src["precision"]), precision_detail=src["precision"], framework=src["framework"],
                 config=src, data_kind="per-run-summary")
        gpus = src.get("num_gpus")
        if gpus is None and not src.get("is_multinode") and not src.get("disagg"):
            if "tp" in src and "pp" in src:
                gpus = number(src["tp"], True) * number(src["pp"], True) * number(src.get("pcp_size", 1), True)
        r["gpus"] = number(gpus, True) if gpus is not None else None
        if r["gpus"] is not None and not r["gpus"].is_integer():
            raise ValueError("GPU count must be integral")
        r["workload"] = {"input_tokens": number(src["isl"], True), "output_tokens": number(src["osl"], True),
                         "concurrency": number(src["conc"], True), "dataset": src.get("dataset", UNKNOWN),
                         "scenario": "fixed-sequence", "request_rate": src.get("request_rate", UNKNOWN)}
        for key in ("framework_version", "backend", "gates", "model_revision"):
            r[key] = src.get(key, UNKNOWN)
        image = src.get("image", "")
        r["image_digest"] = image if re.search(r"@sha256:[a-f0-9]{64}$", image) else UNKNOWN
        r["warnings"] = ["Imported summary: no buyer cost, correctness or traversal claim."]
        if "benchmark_outcome" in src:
            # Retain diagnostic artifacts but never compare them without a vetted outcome adapter.
            r["warnings"].append("Outcome metadata requires review; excluded from ratios.")
            r["comparison_hold"] = "benchmark_outcome requires manual review"
        metrics = []
        for key, name, units, factor in (
            ("output_tput_per_gpu", "output_throughput_per_gpu", "tokens/s/GPU", 1),
            ("tput_per_gpu", "total_token_throughput_per_gpu", "tokens/s/GPU", 1),
            ("request_throughput", "request_throughput", "requests/s", 1),
            ("p95_ttft", "p95_ttft_ms", "ms", 1000),
            ("median_ttft", "median_ttft_ms", "ms", 1000),
            ("median_tpot", "median_tpot_ms", "ms", 1000)):
            if src.get(key) is not None:
                metrics.append((name, number(src[key]) * factor, units))
        out.extend(emit(r, raw, metrics))
    return out


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
    suite = unittest.defaultTestLoader.discover(str(BASE), pattern="test_backfill.py")
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not a.manifest:
        p.error("--manifest is required")
    try:
        rows = import_manifest(a.manifest, a.offline)
        content = "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows)
        if a.output:
            a.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("import failed: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
