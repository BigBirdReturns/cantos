"""Rebuild imported/inferencex-2026-09-29.jsonl and imported/history-index.json from data-raw.

Covers exactly the artifact IDs in the public-tail 2026-09-29 enumeration (data-raw/lane-2026-09-29-ids.json).
Streams rows to disk (the file is over 1 GB). Offline; no network."""
import json
from pathlib import Path
import sys
from importer import BASE, digest, acquire, inferencemax, raw_manifest

RETRIEVED = "2026-09-23T23:40:00Z"  # operator-declared time for the first 100 artifacts, which have no sidecar
LANE = Path("D:/Projects/Organs/AXM/axm-tools/sessions/public-tail-20260929/lanes/inferencex-history/raw/artifact-index.jsonl")


def main():
    raw = BASE / "data-raw"
    ids = set(json.loads((raw / "lane-2026-09-29-ids.json").read_text()))
    manifest = raw_manifest(raw, RETRIEVED, ids)
    assert len(manifest["files"]) == len(ids), (len(manifest["files"]), len(ids))
    mpath = raw / "import-manifest-2026-09-29.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    mhash = digest(mpath.read_bytes())
    listing = {str(json.loads(l)["id"]): json.loads(l) for l in LANE.read_text(encoding="utf-8").splitlines() if l.strip()}
    seen, rows_n, index = set(), 0, {}
    out = BASE / "imported" / "inferencex-2026-09-29.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for entry in manifest["files"]:
            data = acquire(entry, raw, True, False)
            rows = inferencemax(entry, data, mhash, False)
            src_rows = len(json.loads(data))
            for r in rows:
                if r["id"] in seen:
                    raise ValueError("duplicate imported observation")
                seen.add(r["id"])
                fh.write(json.dumps(r, sort_keys=True, allow_nan=False) + "\n")
            rows_n += len(rows)
            ident = str(entry["artifact_id"])
            listed = listing.get(ident, {})
            index[ident] = {"artifact_id": entry["artifact_id"], "created_at": entry["created_at"], "head_sha": entry["head_sha"],
                            "workflow_run_id": entry.get("workflow_run_id") or listed.get("workflow_run", {}).get("id"),
                            "sha256": entry["sha256"], "retrieved_at": entry["retrieved_at"], "status": "imported",
                            "listed_2026_09_29": ident in listing, "expired": listed.get("expired"),
                            "size_in_bytes": listed.get("size_in_bytes"), "source_rows": src_rows, "metric_observations": len(rows)}
    (BASE / "imported" / "history-index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(index), "metric_observations": rows_n, "source_rows": sum(v["source_rows"] for v in index.values()),
                      "empty": sum(1 for v in index.values() if v["source_rows"] == 0)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
