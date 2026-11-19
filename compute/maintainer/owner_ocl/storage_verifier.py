#!/usr/bin/env python3
"""Independently reverify immutable two-host storage-audit receipts and render offline decision evidence."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = "ocl.storage-integrity-native/1"
OUT = "ocl.storage-audit-comparison/1"

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def load(root, host):
    prefix = root / "results" / ("ocl13-" + host + "-storage-")
    paths = {k: Path(str(prefix) + name) for k, name in {
        "write": "write.json", "verify": "verify.json", "journal": "journal.jsonl"}.items()}
    source = {k: p.read_bytes() for k, p in paths.items()}
    w = json.loads(source["write"])
    v = json.loads(source["verify"])
    rows = [json.loads(line) for line in source["journal"].splitlines()]
    reasons = []
    if w.get("schema") != SCHEMA or v.get("schema") != SCHEMA:
        reasons.append("schema_mismatch")
    if w.get("run_id") != v.get("run_id") or w.get("host") != "octo-" + host:
        reasons.append("identity_mismatch")
    if digest(source["write"]) != v.get("original_receipt_sha256"):
        reasons.append("original_receipt_hash_mismatch")
    if digest(source["journal"]) != w.get("journal_sha256"):
        reasons.append("journal_hash_mismatch")
    if w.get("sha256") != v.get("expected_sha256") or v.get("observed_sha256") != w.get("sha256"):
        reasons.append("content_digest_mismatch")
    if w.get("bytes") != v.get("read_bytes") or v.get("source_bytes") != w.get("bytes"):
        reasons.append("size_mismatch")
    if [x.get("block_index") for x in rows] != list(range(len(rows))):
        reasons.append("journal_order_mismatch")
    if len(rows) != w.get("blocks") or sum(x.get("bytes", 0) for x in rows) != w.get("bytes"):
        reasons.append("journal_count_mismatch")
    if not v.get("accepted"):
        reasons.append("remote_verification_rejected")
    if any(not isinstance(x.get("write_fsync_ms"), (int, float)) or
           not 0 <= x.get("write_fsync_ms") < float("inf") for x in rows):
        reasons.append("invalid_timing")
    return {
        "host_label": host.upper(), "accepted": not reasons, "reasons": reasons,
        "bytes": w.get("bytes"), "blocks": w.get("blocks"),
        "write_fsync_median_ms": w.get("median_write_fsync_ms"),
        "write_fsync_max_ms": w.get("max_write_fsync_ms"),
        "read_hash_elapsed_ms": v.get("elapsed_read_hash_ms"),
        "verified_sha256": v.get("observed_sha256"), "run_id": w.get("run_id"),
        "source_sha256": {k: digest(raw) for k, raw in source.items()}
    }

def render(obj):
    lines = []
    for r in obj["hosts"]:
        verified = "PASS" if r["accepted"] else "REJECT"
        lines.append("<tr><td>" + html.escape(r["host_label"]) + "</td><td>" +
                     verified + "</td><td>" + str(r["bytes"]) + "</td><td>" +
                     str(r["blocks"]) + "</td><td>" + str(r["write_fsync_median_ms"]) +
                     "</td><td>" + str(r["read_hash_elapsed_ms"]) + "</td></tr>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<title>Open Compute Ledger: authenticated local storage verification</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{max-width:960px;margin:40px auto;padding:0 18px;font:16px/1.5 system-ui}"
            "table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #aaa;text-align:left}"
            "</style></head><body><h1>Local storage integrity, independent readback</h1>"
            "<p>Two authorized Estate hosts received the same 16 MiB deterministic byte stream. "
            "Four 4 MiB blocks each received an fsync. Distinct native jobs later reopened "
            "and hashed the retained files. These measurements test short-window logical byte "
            "integrity and storage flush timing, with no interruption or data erasure.</p>"
            "<table><thead><tr><th>Host</th><th>Readback</th><th>Bytes</th><th>Blocks</th>"
            "<th>Median write+fsync, ms</th><th>Read+hash, ms</th></tr></thead><tbody>" +
            "".join(lines) + "</tbody></table><p>These samples include filesystem and caching "
            "effects, unisolated host activity and CPU hashing. They do not establish cold-cache "
            "throughput, power-loss durability, cloud-provider SLA, facility power, tariff or "
            "full cost per accepted task. Original 16 MiB source files and their immutable "
            "manifests remain on their respective authorized hosts; the source hashes and "
            "per-block journals are preserved in the private evidence repository.</p>"
            "<p>Reproduce: <code>python scripts/reanalyze_storage_evidence.py --root . "
            "--out-json path-to-new.json --out-html path-to-new.html</code>. New destinations "
            "are required to preserve accepted evidence.</p></body></html>\n").encode("utf-8")

def run(root, outj, outh):
    hosts = [load(root, "w02"), load(root, "w03")]
    obj = {"schema": OUT, "hosts": hosts, "complete_accepted": all(x["accepted"] for x in hosts),
           "scope": "authenticated Estate storage audit only; each 16 MiB retained run independently verified",
           "method": "deterministic source bytes, fsync per block, independent process hash, immutable journals",
           "external_provider_ranking": None, "facility_energy_wh": None, "actual_storage_spend_usd": None,
           "sources": ["results/ocl13-w02-storage-{write,verify,journal}",
                       "results/ocl13-w03-storage-{write,verify,journal}"]}
    raw = (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if outj.exists() or outh.exists():
        raise FileExistsError("immutable prior report")
    with outj.open("xb") as f:
        f.write(raw)
    with outh.open("xb") as f:
        f.write(render(obj))
    return {"accepted": obj["complete_accepted"], "report_sha256": digest(raw),
            "html_sha256": digest(outh.read_bytes())}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out-json", type=Path, required=True)
    p.add_argument("--out-html", type=Path, required=True)
    a = p.parse_args()
    result = run(a.root, a.out_json, a.out_html)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["accepted"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
