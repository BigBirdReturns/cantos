#!/usr/bin/env python3
"""Append a verified observation re-import receipt to a native Research Desk packet."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime
from pathlib import Path

def append_projection_attempt(packet_path, receipt_path, out_dir, *, bundle):
    packet_path, receipt_path, out_dir, bundle = Path(packet_path).resolve(), Path(receipt_path).resolve(), Path(out_dir).resolve(), Path(bundle).resolve()
    if not bundle.exists(): raise FileNotFoundError(f"bundle does not exist: {bundle}")
    if out_dir == bundle or bundle in out_dir.parents: raise ValueError("successor packet output must be outside the retained bundle")
    if not packet_path.is_file() or not receipt_path.is_file():
        raise FileNotFoundError("packet and projection receipt must be existing files")
    raw = receipt_path.read_bytes()
    try: receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError(f"invalid projection receipt: {exc}") from exc
    row_id = receipt.get("row_id") if isinstance(receipt, dict) else None
    if not isinstance(row_id, str) or len(row_id) != 64 or any(c not in "0123456789abcdef" for c in row_id):
        raise ValueError("receipt must contain a 64-character lowercase row_id")
    # Recompute through the corpus adapter so changing rebuilt/result fields in a
    # receipt is detected. observed_at is deliberately excluded because replay
    # is a fresh read; the original event time remains the recorded value.
    try:
        try: from .projection import reproject
        except ImportError: from projection import reproject
        replay = reproject(bundle, row_id, actor=receipt.get("actor"))
    except Exception as exc:
        raise RuntimeError(f"could not replay projection from pinned bundle: {exc}") from exc
    replay_fields = ("schema", "operation", "actor", "row_id", "source", "checks",
                     "procedure", "before", "rebuilt", "matches_current_projection", "outcome")
    for field in replay_fields:
        if replay.get(field) != receipt.get(field):
            raise ValueError(f"projection receipt does not match deterministic replay at {field}")
    if replay.get("bundle", {}).get("manifest_sha256") != receipt.get("bundle", {}).get("manifest_sha256"):
        raise ValueError("projection receipt does not match deterministic replay at bundle.manifest_sha256")
    observed_at = receipt.get("observed_at")
    try:
        parsed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if parsed_at.tzinfo is None: raise ValueError("missing timezone")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("receipt observed_at must be an ISO timestamp with timezone") from exc
    receipt_sha = hashlib.sha256(raw).hexdigest()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"projection-{row_id[:16]}-{receipt_sha[:16]}.research-packet.json"
    if output.exists(): raise FileExistsError(f"refusing to overwrite existing packet: {output}")
    helper = Path(__file__).with_name("history_owner.cjs")
    done = subprocess.run(["node", str(helper), "--packet", str(packet_path), "--receipt", str(receipt_path)], capture_output=True, text=True, encoding="utf-8", errors="strict")
    if done.returncode: raise RuntimeError(done.stderr.strip() or done.stdout.strip() or "native owner failed")
    try: result = json.loads(done.stdout)
    except json.JSONDecodeError as exc: raise RuntimeError("native owner returned invalid JSON") from exc
    packet = result.get("packet")
    if not isinstance(packet, dict) or packet.get("schema") != "second-run/research-packet@1":
        raise RuntimeError("native owner did not return a Research Desk packet")
    if output.exists(): raise FileExistsError(f"refusing to overwrite existing packet: {output}")
    serialized = (json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(serialized); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        try: output.unlink()
        except OSError: pass
        raise
    return {"packet_path": str(output), "packet_sha256": hashlib.sha256(serialized).hexdigest(),
            "native_packet_sha256": packet.get("sha256"), "source_record_id": result["source_record_id"],
            "source_record_revision": result["source_record_revision"],
            "claim_record_id": result["claim_record_id"], "claim_record_revision": result["claim_record_revision"], "row_id": row_id,
            "actor_label": result["actor_label"], "authenticated_actor": False, "replayed_before_append": True,
            "bundle_path": str(bundle), "source_packet_path": str(packet_path), "source_packet_preserved": True}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--packet", required=True, help="verified native Research Desk packet to extend")
    p.add_argument("--receipt", required=True, help="cantos/observation-reprojection@1 receipt")
    p.add_argument("--out", required=True, help="directory for a fresh successor packet")
    p.add_argument("--bundle", required=True, help="corpus bundle used for deterministic receipt replay")
    a = p.parse_args()
    try: print(json.dumps(append_projection_attempt(a.packet, a.receipt, a.out, bundle=a.bundle), indent=2)); return 0
    except Exception as exc: print(f"history append failed: {exc}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
