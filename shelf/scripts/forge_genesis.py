#!/usr/bin/env python3
"""Genesis regime for the forge: IDENTITY, NON-TRANSFER and SUCCESSION through the native
estate kernel, not through JSON diffs.

Each sampled card is compiled into a signed Genesis shard with claims bound to byte spans
of the card's canonical bytes (the same way hot-aisle/campaign/shelf/join binds Run 3).
Then, per card:

  BIND          the shard verifies under its own local test key
  NON-TRANSFER  the same shard does not verify under another issuer's key
  IDENTITY      one flipped byte in the sealed card content fails verification;
                a metadata-only edit (title) yields a different card revision, so the old
                binding no longer names the current card and cannot be carried silently
  SUCCESSION    a corrected card compiles as a successor shard that names its predecessor
                (manifest.supersedes + lineage@1 rows); the predecessor shard still verifies
                unchanged; the two shard ids and card revisions differ

Keys are generated in memory per card and never written. Nothing here grants standing,
authenticates a publisher, or touches the Genesis checkout; it is imported read-only.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_native(genesis):
    genesis = Path(genesis).resolve()
    src = str(genesis / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import axm_build.compiler_generic as compiler
    import axm_build.sign as sign
    import axm_verify.crypto as crypto
    import axm_verify.logic as verifier
    if not Path(compiler.__file__).resolve().is_relative_to(genesis):
        raise ValueError("Imported Genesis does not belong to the requested checkout")
    return compiler, sign, crypto, verifier


def first_dict_result(card):
    for k, v in card["a_claim"]["results"].items():
        if isinstance(v, dict) and v.get("value") is not None:
            return k, v
    return None, None


def candidates_for(card):
    rows = [{"subject": card["id"], "predicate": "card_statement", "object": card["a_claim"]["statement"],
             "object_type": "literal:string", "tier": 0, "evidence": card["a_claim"]["statement"]}]
    k, v = first_dict_result(card)
    if k:
        quote = '"' + k + '":' + encoded(v).decode().strip()
        rows.append({"subject": card["id"], "predicate": "card_result_" + k, "object": str(v["value"]),
                     "object_type": "literal:string", "tier": 0, "evidence": quote})
    return rows


def compile_card(native, card, out, private, public, supersedes=(), action="supersede", note=""):
    compiler, sign, crypto, verifier = native
    out = Path(out)
    work = out / "work"
    work.mkdir(parents=True)
    source = work / "source.txt"
    source.write_bytes(encoded(card))
    cands = work / "candidates.jsonl"
    cands.write_bytes(b"".join(encoded(c) for c in candidates_for(card)))
    (out / "card.json").write_bytes(encoded(card))
    (out / "local-test.pub").write_bytes(public)
    old = tempfile.tempdir
    tempfile.tempdir = str(work)
    try:
        ok = compiler.compile_generic_shard(compiler.CompilerConfig(
            source_path=source, candidates_path=cands, out_dir=out / "shard", private_key=private,
            publisher_id="local-test/forge", publisher_name="Forge local test issuer; no publication authority",
            namespace="second-run/shelf-forge", created_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            title="forge binding: local test only", supersedes=tuple(supersedes), lineage_action=action, lineage_note=note,
            extra_content=(("card.json", out / "card.json"),)))
    finally:
        tempfile.tempdir = old
    if not ok:
        raise ValueError("native compiler self-verification failed")
    manifest = (out / "shard" / "manifest.json").read_bytes()
    return {"shard_id": crypto.derive_shard_id(manifest), "card_revision_sha256": hashlib.sha256((out / "card.json").read_bytes()).hexdigest(),
            "manifest": json.loads(manifest)}


def verify(native, out, pub):
    return native[3].verify_shard(Path(out) / "shard", Path(pub))


def check_genesis(valid, genesis, n, F, rng, strip):
    native = load_native(genesis)
    _, sign, _, _ = native
    sample = [strip(c) for c in valid[:n]]
    stats = {"bound": 0, "cards": len(sample), "genesis_commit": genesis_commit(genesis)}
    with tempfile.TemporaryDirectory(prefix="shelf-forge-genesis-") as tmp:
        for i, card in enumerate(sample):
            base = Path(tmp) / f"c{i:04d}"
            public, private = sign.hybrid1_keygen()
            other_pub, other_priv = sign.hybrid1_keygen()
            try:
                v1 = compile_card(native, card, base / "v1", private, public)
            except Exception as e:  # a card the kernel refuses to bind is a finding, not a crash
                F.add("IDENTITY", "genesis-bind", i, {"detail": "native compile failed", "error": str(e)[:400]}, card)
                continue
            r = verify(native, base / "v1", base / "v1" / "local-test.pub")
            if r["status"] != "PASS":
                F.add("IDENTITY", "genesis-bind", i, {"detail": "fresh shard failed native verification", "result": r}, card); continue
            stats["bound"] += 1
            # NON-TRANSFER: another issuer's key must not verify this shard
            (base / "other.pub").write_bytes(other_pub)
            r2 = verify(native, base / "v1", base / "other.pub")
            if r2["status"] == "PASS":
                F.add("NON-TRANSFER", "genesis-key", i, {"detail": "shard verified under a different issuer's key"}, card)
            # IDENTITY: flip one byte of the sealed card content
            tampered = base / "t1"
            copy_tree(base / "v1", tampered)
            p = tampered / "shard" / "content" / "card.json"
            b = bytearray(p.read_bytes()); j = b.rfind(b"1") if b.rfind(b"1") >= 0 else 0; b[j] = ord("2") if b[j] != ord("2") else ord("3"); p.write_bytes(bytes(b))
            r3 = verify(native, tampered, tampered / "local-test.pub")
            if r3["status"] == "PASS":
                F.add("IDENTITY", "genesis-tamper", i, {"detail": "a flipped byte in sealed content still verified"}, card)
            # IDENTITY: a metadata-only edit is a new revision; the old binding cannot name it
            meta = copy.deepcopy(card); meta["title"] = card["title"] + " (retitled)"; meta["spine"] = "respun"
            if hashlib.sha256(encoded(meta)).hexdigest() == v1["card_revision_sha256"]:
                F.add("IDENTITY", "genesis-revision", i, {"detail": "metadata edit kept the bound card revision"}, card)
            # SUCCESSION: a corrected value compiles as a successor naming its predecessor; v1 is untouched
            succ = copy.deepcopy(card); k, v = first_dict_result(succ)
            if k and isinstance(v["value"], (int, float)) and not isinstance(v["value"], bool):
                v["value"] = round(v["value"] * 1.1 + 0.01, 2)
            else:
                succ["a_claim"]["statement"] = card["a_claim"]["statement"] + " Corrected."
            try:
                v2 = compile_card(native, succ, base / "v2", private, public, supersedes=(v1["shard_id"],), action="amend", note="forge correction")
            except Exception as e:
                F.add("SUCCESSION", "genesis-successor", i, {"detail": "successor compile failed", "error": str(e)[:400]}, {"card": card, "successor": succ}); continue
            r4 = verify(native, base / "v2", base / "v2" / "local-test.pub")
            r5 = verify(native, base / "v1", base / "v1" / "local-test.pub")
            lineage = v2["manifest"].get("supersedes")
            ok = (r4["status"] == "PASS" and r5["status"] == "PASS" and lineage == [v1["shard_id"]]
                  and v2["shard_id"] != v1["shard_id"] and v2["card_revision_sha256"] != v1["card_revision_sha256"])
            rows = lineage_rows(base / "v2" / "shard")
            ok = ok and any(row.get("supersedes_shard_id") == v1["shard_id"] and row.get("action") == "amend" for row in rows)
            if not ok:
                F.add("SUCCESSION", "genesis-successor", i, {"v2": r4["status"], "v1_after": r5["status"], "supersedes": lineage, "lineage_rows": rows[:3],
                                                              "ids_differ": v2["shard_id"] != v1["shard_id"]}, {"card": card, "successor": succ})
            del private, other_priv
    return stats


def lineage_rows(shard):
    for cand in ("ext/lineage@1.jsonl", "ext/lineage.jsonl", "graph/lineage.jsonl"):
        p = Path(shard) / cand
        if p.is_file():
            return [json.loads(l) for l in p.read_bytes().splitlines() if l]
    rows = []
    for p in Path(shard).rglob("*.jsonl"):
        if "lineage" in p.name:
            rows += [json.loads(l) for l in p.read_bytes().splitlines() if l]
    return rows


def copy_tree(src, dst):
    import shutil
    shutil.copytree(src, dst)


def genesis_commit(genesis):
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(genesis), "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, text=True).stdout.strip() or None
    except OSError:
        return None
