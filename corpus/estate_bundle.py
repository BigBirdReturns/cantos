"""Assemble a Cantos collection from the estate's own capture lanes.

A capture lane is a session folder whose adapters already wrote rows in the estate's
`imported-observation@1` schema (or the github-issues row schema) with a per-file
manifest. This tool retains those rows as a Cantos bundle: pinned raw inputs, the
common SQLite projection, native Research Desk packets and a verification record.
No network access, inference, benchmark execution or calibration is involved.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import bulk_import
    from .projection import reproject
    from .reader import Collection
except ImportError:  # Direct invocation: python corpus/estate_bundle.py
    import bulk_import
    from projection import reproject
    from reader import Collection

HERE = Path(__file__).resolve().parent
FORMATS = {
    "imported-observation@1": ("imported-observation-jsonl", "producer_reported"),
    "github-issues": ("github-issues-jsonl", "public_listing"),
}


def sha_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def lane_manifest(lane):
    """Return the lane's per-file manifest entries (JSON list or JSONL)."""
    manifest = next((lane / name for name in ("manifest.json", "manifest.jsonl") if (lane / name).is_file()), None)
    if manifest is None:
        raise FileNotFoundError(f"lane has no manifest.json or manifest.jsonl: {lane}")
    text = manifest.read_text(encoding="utf-8")
    try:
        loaded = json.loads(text)
        entries = loaded if isinstance(loaded, list) else loaded.get("files") or loaded.get("entries") or []
    except json.JSONDecodeError:  # Some lanes wrote JSON Lines under the .json name.
        entries = [json.loads(line) for line in text.splitlines() if line.strip()]
    return manifest, [entry for entry in entries if isinstance(entry, dict)]


def lane_rows(lane):
    rows = sorted((lane / "rows").glob("*.jsonl"))
    if len(rows) != 1:
        raise ValueError(f"lane must have exactly one rows/*.jsonl file: {lane}")
    with rows[0].open("rb") as stream:
        first = None
        for line in stream:
            if line.strip():
                first = json.loads(line)
                break
    if not isinstance(first, dict):
        raise ValueError(f"lane rows file is empty: {rows[0]}")
    key = first.get("schema") if first.get("schema") in FORMATS else first.get("source")
    if key not in FORMATS:
        raise ValueError(f"unsupported lane row schema in {rows[0]}: schema={first.get('schema')!r} source={first.get('source')!r}")
    return rows[0], FORMATS[key]


def count_lines(path):
    with Path(path).open("rb") as stream:
        return sum(1 for line in stream if line.strip())


def first_row(db_path, origin):
    """The lowest-identity retained row of one origin, read without changing the DB."""
    import sqlite3
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        record = db.execute("SELECT json FROM rows WHERE origin = ? ORDER BY row_id LIMIT 1", (origin,)).fetchone()
    finally:
        db.close()
    if record is None:
        raise KeyError(origin)
    return json.loads(record[0])


def common_url(urls):
    """The deepest URL prefix (scheme, host, path segments) shared by at least half the lane's fetches."""
    urls = [url.split(" ")[0] for url in urls if isinstance(url, str) and url.startswith(("https://", "http://"))]
    if not urls:
        return None
    for depth in range(8, 2, -1):
        prefixes = collections.Counter("/".join(url.split("/")[:depth + 1]) + "/" for url in urls if len(url.split("/")) > depth + 1)
        if prefixes:
            prefix, share = prefixes.most_common(1)[0]
            if share * 2 > len(urls):
                return prefix
    return urls[0]


def describe_lane(lane, origin):
    lane = Path(lane).resolve(strict=True)
    manifest, entries = lane_manifest(lane)
    rows, (fmt, evidence_class) = lane_rows(lane)
    retrieved = [entry.get("retrieved_utc") or entry.get("retrieved_at") for entry in entries]
    retrieved = max((value for value in retrieved if isinstance(value, str)), default=None)
    licenses = collections.Counter(entry.get("license") for entry in entries if isinstance(entry.get("license"), str))
    report = lane / "REPORT.md"
    return {
        "origin": origin,
        "format": fmt,
        "evidence_class": evidence_class,
        "workload": origin,
        "url": common_url([entry.get("url") for entry in entries]),
        "revision": None,
        "retrieved_at": retrieved,
        "license": licenses.most_common(1)[0][0] if licenses else None,
        "time_basis": "source record, not acquisition time",
        "path": "raw/" + origin.replace("/", "__") + ".jsonl",
        "sha256": sha_file(rows),
        "bytes": rows.stat().st_size,
        "lane": {
            "name": lane.name,
            "session": lane.parent.parent.name if lane.parent.name == "lanes" else lane.parent.name,
            "path": str(lane),
            "rows_file": rows.name,
            "manifest_file": manifest.name,
            "manifest_sha256": sha_file(manifest),
            "manifest_entries": len(entries),
            "report_sha256": sha_file(report) if report.is_file() else None,
            "per_row_provenance": "each retained row keeps the lane's own provenance object",
        },
        "_rows_path": rows,
    }


def origin_for(lane):
    lane = Path(lane).resolve(strict=True)
    session = lane.parent.parent.name if lane.parent.name == "lanes" else lane.parent.name
    return f"{session}/{lane.name}"


def build(lanes, out, *, actor="Cantos estate importer", verify_reimport=True, log=print):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Retain the existing collection rather than overwrite: {out}")
    lanes = [Path(lane).resolve(strict=True) for lane in lanes]
    if not lanes:
        raise ValueError("at least one --lane is required")
    sources = [describe_lane(lane, origin_for(lane)) for lane in lanes]
    if len({source["origin"] for source in sources}) != len(sources):
        raise ValueError("lanes must have distinct origins")

    inputs = out / "inputs"
    (inputs / "raw").mkdir(parents=True)
    for source in sources:
        target = inputs / source["path"]
        log(f"retain {source['origin']}: {source['bytes']:,} bytes")
        shutil.copyfile(source.pop("_rows_path"), target)
        if sha_file(target) != source["sha256"]:
            raise ValueError("retained raw bytes differ from the lane rows file")
    manifest = {
        "schema": "cantos/estate-inputs@1",
        "assembled_at": now(),
        "assembler": "corpus/estate_bundle.py",
        "selection": "Estate capture lanes retained whole: " + ", ".join(source["origin"] for source in sources),
        "pins": "Lane rows files hash-bound; per-row provenance (URL, revision, retrieval time, hash) retained in each native row",
        "sources": sources,
    }
    manifest_path = inputs / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    log("import rows into the common projection")
    report = bulk_import.ingest(manifest_path, out / "corpus")
    log(f"imported {report['rows']:,} rows; {report['by_kind']}")

    log("retain native Research Desk packets")
    done = subprocess.run(
        ["node", str(HERE / "batch_owner.cjs"), str(out / "corpus" / "rows.jsonl"), str(out / "research-packets"), actor],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode:
        raise RuntimeError("native packet owner failed: " + (done.stderr.strip() or done.stdout.strip()))
    packets = json.loads(done.stdout.strip().splitlines()[-1])
    index = json.loads((out / "research-packets" / "INDEX.json").read_text(encoding="utf-8"))

    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})
        log(("PASS " if passed else "FAIL ") + name + (f" ({detail})" if detail is not None else ""))

    for stat, source in zip(report["sources"], sources):
        lines = count_lines(inputs / source["path"])
        check(f"lane rows retained whole: {source['origin']}", stat["source_rows"] == lines == stat["inserted"], f"{lines} lines, {stat['inserted']} inserted")
    check("no duplicate observation identities", report["new_rows"] == report["rows"] and report["reused_rows"] == 0, report["rows"])
    check("packets cover every imported row", index["total_rows"] == report["rows"] == packets["rows"], index["total_rows"])
    ordered = all("first_row_id" in entry and entry["first_row_id"] <= entry["last_row_id"] for entry in index["batches"])
    disjoint = True
    by_origin = collections.defaultdict(list)
    for entry in index["batches"]:
        by_origin[entry["origins"][0]].append(entry)
    for entries in by_origin.values():
        ids = [(entry["first_row_id"], entry["last_row_id"]) for entry in entries]
        disjoint &= all(ids[i][1] < ids[i + 1][0] for i in range(len(ids) - 1))
    check("packet identity ranges are ordered and disjoint", ordered and disjoint, len(index["batches"]))

    state = Path(tempfile.mkdtemp(prefix="cantos-estate-verify-"))
    try:
        collection = Collection(out, state)
        for source in sources:
            row = first_row(out / "corpus" / "corpus.sqlite", source["origin"])
            receipt = reproject(out, row["row_id"], actor=actor)
            check(f"exact re-import reproduces the retained row: {source['origin']}", receipt["matches_current_projection"] and all(receipt["checks"].values()), row["row_id"][:16])
            history = collection.history(row["row_id"])
            labels = [link["label"] for link in history["links"]]
            check(f"history opens through its retained packet: {source['origin']}", history["batch"]["file"] in {entry["file"] for entry in index["batches"]}, history["batch"]["file"])
            check(f"producer links are exposed: {source['origin']}", bool(labels), ", ".join(labels))
    finally:
        shutil.rmtree(state, ignore_errors=True)

    if verify_reimport:
        log("re-import every row into a scratch projection to confirm determinism")
        scratch = Path(tempfile.mkdtemp(prefix="cantos-estate-reimport-"))
        try:
            again = bulk_import.ingest(manifest_path, scratch / "corpus")
            check("full re-import is byte-identical", again["rows_sha256"] == report["rows_sha256"], report["rows_sha256"][:16])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    tools = {name: sha_file(HERE / name) for name in ("bulk_import.py", "batch_owner.cjs", "estate_bundle.py", "projection.py", "reader.py", "query.py", "history.py", "history_owner.cjs")}
    verification = {
        "schema": "cantos/estate-verification@1",
        "verified_at": now(),
        "all_pass": all(item["pass"] for item in checks),
        "checks": checks,
        "rows": report["rows"],
        "by_kind": report["by_kind"],
        "packets": index["packets"],
        "rows_sha256": report["rows_sha256"],
        "native_core_sha256": index["native_core_sha256"],
        "tools": tools,
        "boundary": "Observations are the estate's own captured imports. No benchmark was executed, no calibration performed, no acceptance established, nothing fetched.",
    }
    (out / "verification").mkdir()
    (out / "verification" / "VERIFY.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8", newline="\n")
    estate = {
        "schema": "cantos/estate-collection@1",
        "assembled_at": manifest["assembled_at"],
        "actor_label": actor,
        "lanes": [{**source["lane"], "origin": source["origin"], "format": source["format"], "evidence_class": source["evidence_class"], "rows_sha256": source["sha256"], "bytes": source["bytes"]} for source in sources],
        "rows": report["rows"],
        "by_kind": report["by_kind"],
        "packets": index["packets"],
        "all_pass": verification["all_pass"],
        "boundary": verification["boundary"],
    }
    (out / "ESTATE.json").write_text(json.dumps(estate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if not verification["all_pass"]:
        raise RuntimeError("collection assembled but verification failed; see verification/VERIFY.json")
    return estate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lane", action="append", required=True, type=Path, help="capture lane folder (repeatable)")
    parser.add_argument("--out", required=True, type=Path, help="new collection folder; must not exist")
    parser.add_argument("--actor", default="Cantos estate importer")
    parser.add_argument("--skip-reimport", action="store_true", help="skip the full deterministic re-import check")
    args = parser.parse_args(argv)
    try:
        estate = build(args.lane, args.out, actor=args.actor, verify_reimport=not args.skip_reimport)
    except Exception as exc:
        print(f"estate collection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: estate[key] for key in ("rows", "by_kind", "packets", "all_pass")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
