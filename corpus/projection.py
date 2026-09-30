"""Rebuild one retained normalized observation from its pinned raw source."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

try:
    from . import bulk_import
    from .query import row_by_id
except ImportError:  # Direct invocation: python corpus/projection.py
    import bulk_import
    from query import row_by_id


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reproject(bundle, row_id, actor="Local operator"):
    """Re-run the retained adapter for one exact row without changing the bundle.

    The result is a normalization replay receipt. It does not execute a benchmark,
    infer acceptance, or write to the bundle.
    """
    bundle = Path(bundle).resolve(strict=True)
    if not bundle.is_dir():
        raise ValueError("bundle must be a directory")
    if not isinstance(actor, str) or not actor.strip() or len(actor.strip()) > 120:
        raise ValueError("actor must contain 1 to 120 characters")
    actor = actor.strip()

    db_path = bundle / "corpus" / "corpus.sqlite"
    manifest_path = bundle / "inputs" / "manifest.json"
    if not db_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("bundle is missing corpus/corpus.sqlite or inputs/manifest.json")
    before = row_by_id(db_path, row_id)
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    origin = before.get("source", {}).get("origin")
    matches = [source for source in manifest.get("sources", [])
               if source.get("origin") == origin]
    if len(matches) != 1:
        raise ValueError("manifest must contain exactly one pinned source for this observation")
    source = matches[0]
    before_source = before.get("source", {})
    metadata_fields = ("origin", "url", "revision", "retrieved_at",
                       "evidence_class", "license", "time_basis")
    if any(source.get(key) != before_source.get(key) for key in metadata_fields):
        raise ValueError("manifest source metadata differs from the stored observation")
    if source.get("sha256") != before_source.get("raw_sha256"):
        raise ValueError("manifest raw-source pin differs from the stored observation")

    raw_path = (manifest_path.parent / source["path"]).resolve(strict=True)
    if manifest_path.parent.resolve() not in raw_path.parents:
        raise ValueError("manifest source path escapes inputs directory")
    if source.get("format") not in bulk_import.ADAPTERS:
        raise ValueError("manifest uses an unsupported retained adapter")
    row_index = before.get("source", {}).get("row_index")
    if not isinstance(row_index, int) or row_index < 0:
        raise ValueError("stored observation has an invalid source row index")
    # JSONL adapters hash the full retained file while keeping only the selected
    # native line. Other formats retain the existing byte-backed adapter path.
    rebuilt = bulk_import.rebuild_source_row(source, raw_path, row_index)
    raw_sha = source["sha256"]

    native = rebuilt.get("native")
    native_sha = _sha_bytes(_canonical(native).encode("utf-8"))
    computed_row_id = _sha_bytes(_canonical(
        [source["origin"], source["sha256"], row_index]
    ).encode("utf-8"))
    checks = {
        "pinned_source_match": all(source.get(key) == before_source.get(key)
                                    for key in metadata_fields),
        "raw_sha256_match": raw_sha == before_source.get("raw_sha256"),
        "row_id_match": rebuilt.get("row_id") == row_id == computed_row_id,
        "native_row_sha256_match": native_sha == before_source.get("native_row_sha256"),
    }
    if not all(checks.values()):
        raise ValueError("re-imported row does not match its retained identity pins")

    procedure_path = Path(__file__)
    adapter_path = procedure_path.with_name("bulk_import.py")
    procedure_file_sha = _sha_file(procedure_path)
    adapter_file_sha = _sha_file(adapter_path)
    procedure_sha = _sha_bytes(_canonical({
        "corpus/projection.py": procedure_file_sha,
        "corpus/bulk_import.py": adapter_file_sha,
    }).encode("utf-8"))
    return {
        "schema": "cantos/observation-reprojection@1",
        "operation": "reimported_projection",
        "actor": actor,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "row_id": row_id,
        "bundle": {
            "name": bundle.name,
            "manifest_sha256": _sha_bytes(manifest_raw),
        },
        "source": {
            **{key: source.get(key) for key in
               ("origin", "url", "revision", "retrieved_at", "evidence_class", "license", "time_basis")},
            "format": source.get("format"),
            "path": source.get("path"),
            "raw_sha256": raw_sha,
            "row_index": row_index,
            "native_row_sha256": native_sha,
        },
        "checks": checks,
        "procedure": {
            "name": "corpus.projection.reproject + bulk_import.rebuild_source_row",
            "sha256": procedure_sha,
            "projection_sha256": procedure_file_sha,
            "adapter_sha256": adapter_file_sha,
        },
        "before": before,
        "rebuilt": rebuilt,
        "matches_current_projection": _canonical(before) == _canonical(rebuilt),
        "outcome": {
            "kind": "reimport",
            "benchmark_executed": False,
            "calibration_performed": False,
            "accepted_work": None,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--row-id", required=True)
    parser.add_argument("--actor", default="Local operator")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    receipt = reproject(args.bundle, args.row_id, actor=args.actor)
    serialized = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = args.out.resolve()
        bundle = args.bundle.resolve()
        if output == bundle or bundle in output.parents:
            raise ValueError("receipt output must be outside the retained bundle")
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
