"""One Run 3 filing bound by native Genesis; no admission or query engine.

Build once into a fresh output directory. Verification never changes receipts.
Only a newly generated, in-memory LOCAL TEST key signs this demonstration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
SHELF = HERE.parent
CAMPAIGN = SHELF.parent
CARD_ID = "run3-at0"
POLICY = {
    "standing": "filed/candidate",
    "authority": None,
    "rule": "Binding and matching preconditions do not grant accepted standing.",
    "acceptance": "Requires a separate named human reconciliation; absent here.",
    "implementation": "Local candidate receipt with native Canon evidence-bundle validation; no human reconciliation.",
    "native_canon_required": True,
}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_bytes(encoded(value))


def table(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line]


def load_native(genesis):
    genesis = Path(genesis).resolve()
    sys.path.insert(0, str(genesis / "src"))
    import axm_build.compiler_generic as compiler
    import axm_verify.crypto as crypto
    import axm_verify.logic as verifier
    import axm_build.sign as sign
    if not Path(compiler.__file__).resolve().is_relative_to(genesis):
        raise ValueError("Imported Genesis does not belong to the requested checkout")
    return compiler, crypto, verifier, sign


def context_for(card):
    return {"card_id": card["id"], "period": card["a_claim"]["period"],
            "conditions": card["a_claim"]["conditions"],
            "acceptance": card["b_population"]["acceptance"],
            "exclusions": card["b_population"]["exclusions"],
            "purpose": "Inspect this historical filing under its exact recorded conditions"}


def native_binding(out, crypto):
    shard = out / "shard"
    provenance = table(shard / "graph/provenance.jsonl")
    spans = table(shard / "evidence/spans.jsonl")
    claims = []
    for claim in table(shard / "graph/claims.jsonl"):
        prov = next(p for p in provenance if p["claim_id"] == claim["claim_id"])
        span = next(s for s in spans if all(s[k] == prov[k] for k in
                    ("source_hash", "byte_start", "byte_end")))
        claims.append({"claim_id": claim["claim_id"], "predicate": claim["predicate"],
                       "object": claim["object"], "provenance_id": prov["provenance_id"],
                       "span_id": span["span_id"], "source_sha256": prov["source_hash"],
                       "byte_start": prov["byte_start"], "byte_end": prov["byte_end"],
                       "text": span["text"]})
    return {"card_id": CARD_ID, "card_revision_sha256": sha(out / "card.json"),
            "shard_id": crypto.derive_shard_id((shard / "manifest.json").read_bytes()),
            "manifest_sha256": sha(shard / "manifest.json"),
            "source_sha256": sha(shard / "content/source.txt"),
            "dependency_scope_sha256": sha(shard / "content/dependency-scope.json"),
            "claims": claims,
            "trust": {"issuer": "local-test-only", "public_key": "local-test.pub",
                      "public_key_sha256": sha(out / "local-test.pub"),
                      "private_key": "Generated in memory for this build; never written",
                      "authority": "No identity authentication, publication trust or human admission"},
            "boundary": "Native Genesis binds a card's assertions and retained evidence hashes; it does not establish their truth or recompute the experiment."}


def canon_run(out, canon):
    command = ["node", str(HERE / "canon_check.mjs"), "--source-root", str(canon),
               "--bundle", str(out)]
    proc = subprocess.run(command, capture_output=True, text=True)
    return {"command": command, "exit_code": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def canon_reference(out, binding):
    receipt = read(out / "canon-validation.json")
    data = json.loads(receipt["stdout"])
    if receipt["exit_code"] != 0 or data["status"] != "PASS" or not data["unsupported_review"]["refused"]:
        raise ValueError("Native Canon evidence validation did not pass")
    for key in ("card_id", "card_revision_sha256", "shard_id"):
        if data[key] != binding[key]:
            raise ValueError("Canon receipt belongs to a different card or native shard")
    if (data["accepted"] is not False or data["reviewer"] is not None
            or data["input"]["sources"][0]["digest"] != binding["source_sha256"]):
        raise ValueError("Canon evidence receipt does not preserve source or candidate standing")
    if {r["id"] for r in data["input"]["records"]} != {c["claim_id"] for c in binding["claims"]}:
        raise ValueError("Canon evidence receipt refers to different claims")
    return {"evidence_bundle_sha256": data["input_sha256"],
            "validation_receipt_sha256": sha(out / "canon-validation.json"),
            "source_commit": data["source_commit"], "validation_status": "PASS",
            "representation": "machine-extracted", "reviewer": None,
            "boundary": "Native evidence validation; human reconciliation not run"}


def inspect(out, genesis, campaign, context=None, canon=None):
    _, crypto, verifier, _ = load_native(genesis)
    out, campaign = Path(out), Path(campaign)
    result = {"card_id": CARD_ID, "card_revision_sha256": None, "shard_id": None,
              "dependency_scope_sha256": None,
              "checked_at": datetime.now(timezone.utc).isoformat(),
              "rules_location": "shard/content/dependency-scope.json",
              "snapshot_notice": "Dated check result; rerun join.py check for current applicability",
              "binding": "unbound", "standing": "unknown", "applicability": "REFUSE",
              "authorized_reuse": False, "reasons": [], "native_verifier": None}
    if not (out / "binding.json").is_file():
        result["reasons"].append("Missing binding.json")
        return result
    native = verifier.verify_shard(out / "shard", out / "local-test.pub")
    result["native_verifier"] = native
    if native["status"] != "PASS":
        result["reasons"].append("Native Genesis rejected shard bytes")
        return result
    expected = native_binding(out, crypto)
    binding = read(out / "binding.json")
    if binding != expected or (out / "card.json").read_bytes() != (out / "shard/content/card.json").read_bytes():
        result["reasons"].append("Binding or card does not match native shard identities")
        return result
    result["binding"] = "bound"
    for identity in ("card_revision_sha256", "shard_id", "dependency_scope_sha256"):
        result[identity] = binding[identity]
    scope = read(out / "shard/content/dependency-scope.json")
    result["expected_scope"] = scope["context"]
    standing = read(out / "standing.json")
    policy = scope["standing_policy"]
    required = {"card_id": CARD_ID, "card_revision_sha256": binding["card_revision_sha256"],
                "shard_id": binding["shard_id"],
                "claim_ids": [c["claim_id"] for c in binding["claims"]],
                "policy_sha256": hashlib.sha256(encoded(policy)).hexdigest(),
                "policy": policy, "predecessor_receipt_sha256": None}
    if policy.get("native_canon_required"):
        try:
            required["native_canon"] = canon_reference(out, binding)
            result["native_canon_validation"] = "retained-PASS"
            if canon:
                fresh = canon_run(out, canon)
                result["native_canon_execution"] = fresh
                if fresh["exit_code"] != 0 or json.loads(fresh["stdout"]) != json.loads(read(out / "canon-validation.json")["stdout"]):
                    raise ValueError("Fresh native Canon validation differs from retained result")
                result["native_canon_validation"] = "fresh-PASS"
        except (OSError, ValueError, KeyError) as error:
            result["reasons"].append("Canon validation: " + str(error))
    if (standing != required or policy.get("standing") != "filed/candidate"
            or policy.get("authority") is not None):
        result["reasons"].append("Standing is not this local candidate receipt; no acceptance authority available")
    else:
        result["standing"] = "filed/candidate"
    desired = context if context is not None else context_for(read(out / "card.json"))
    if desired != scope["context"]:
        result["reasons"].append("Requested period, evaluator, conditions, exclusions or purpose differ; revalidation required")
    current_cards = campaign / "shelf/cards.jsonl"
    current_card = None
    if current_cards.is_file():
        for line in current_cards.read_bytes().splitlines():
            if line and json.loads(line).get("id") == CARD_ID:
                current_card = line + b"\n"
                break
    if current_card != (out / "card.json").read_bytes():
        result["reasons"].append("Current Run 3 card is missing or has a different revision; revalidation required")
    for dependency in scope["dependencies"]:
        target = (campaign / dependency["path"]).resolve()
        if not target.is_relative_to(campaign.resolve()) or not target.is_file():
            result["reasons"].append("Missing dependency: " + dependency["path"])
        elif sha(target) != dependency["sha256"]:
            result["reasons"].append("Changed dependency: " + dependency["path"])
    if not result["reasons"]:
        result["applicability"] = "PASS"
    result["scope"] = "Exact historical filing and retained dependencies only; no present capacity, price, experiment repeat or authoritative reuse"
    return result


def build(out, genesis, scratch, canon):
    compiler, crypto, _, sign = load_native(genesis)
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("Build output must be new; preserve prior receipts and create a successor directory")
    if canon is None:
        raise ValueError("This successor requires --canon pointing at pinned native Canon source")
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    rows = [(line, json.loads(line)) for line in (SHELF / "cards.jsonl").read_bytes().splitlines() if line]
    original, card = next((raw, value) for raw, value in rows if value["id"] == CARD_ID)
    dependencies = {Path(s["path_or_url"]).resolve() for s in card["d_materials"]["sources"]
                    if not s["path_or_url"].startswith(("http:", "https:"))}
    for relative in ("run3/grade.py", "run3/common.py", "run3/replay.py",
                     "results/run3-scored-a-t0/grade/evaluation.json",
                     "results/run3-scored-a-t0/replay/requests.jsonl",
                     "results/run3-scored-a-t0/replay/plan.json",
                     "results/run3-scored-a-t0/replay/journal.jsonl",
                     "results/run3-scored-a-t0/tasks.json",
                     "results/run3-scored-a-t0/detailed.json"):
        dependencies.add(CAMPAIGN / relative)
    dep_rows = [{"path": p.relative_to(CAMPAIGN).as_posix(), "sha256": sha(p)}
                for p in sorted(dependencies)]
    out.mkdir(parents=True)
    (out / "card.json").write_bytes(original + b"\n")
    with tempfile.TemporaryDirectory(prefix="run3-join-", dir=scratch) as workdir:
        work = Path(workdir)
        source = work / "source.txt"
        source.write_bytes(encoded(card))
        scope_path = work / "dependency-scope.json"
        write(scope_path, {"context": context_for(card), "dependencies": dep_rows,
                           "standing_policy": POLICY,
                           "evidence_storage": "Exact card and closure are included; other retained bytes remain in campaign custody and are verified by digest"})
        candidates = []
        for predicate, obj, quote in (
            ("card_statement", card["a_claim"]["statement"], card["a_claim"]["statement"]),
            ("card_accepted_requests", str(card["b_population"]["accepted"]["value"]),
             '"accepted":' + encoded(card["b_population"]["accepted"]).decode().strip()),
            ("card_scheduled_requests", str(card["b_population"]["scheduled"]["value"]),
             '"scheduled":' + encoded(card["b_population"]["scheduled"]).decode().strip()),
        ):
            candidates.append({"subject": CARD_ID, "predicate": predicate, "object": obj,
                               "object_type": "literal:string", "tier": 0, "evidence": quote})
        candidates_path = work / "candidates.jsonl"
        candidates_path.write_bytes(b"".join(encoded(c) for c in candidates))
        public, private = sign.hybrid1_keygen()
        (out / "local-test.pub").write_bytes(public)
        old_tempdir = tempfile.tempdir
        tempfile.tempdir = str(work)
        try:
            passed = compiler.compile_generic_shard(compiler.CompilerConfig(
                source_path=source, candidates_path=candidates_path, out_dir=out / "shard",
                private_key=private, publisher_id="local-test/run3-shelf-join",
                publisher_name="Run 3 local test issuer; no publication authority",
                namespace="second-run/shelf", created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                title="Run 3 shelf filing: local test binding only",
                extra_content=(("card.json", out / "card.json"),
                               ("dependency-scope.json", scope_path),
                               ("closure.json", CAMPAIGN / "results/run3-scored-a-t0/closure.json"))))
        finally:
            tempfile.tempdir = old_tempdir
            del private
        if not passed:
            raise ValueError("Native compiler self-verification failed")
    binding = native_binding(out, crypto)
    if len(binding["claims"]) != 3:
        raise ValueError("Native compiler did not retain exactly three declared claims")
    write(out / "binding.json", binding)
    canon_receipt = canon_run(out, canon)
    write(out / "canon-validation.json", canon_receipt)
    write(out / "standing.json", {"card_id": CARD_ID,
        "card_revision_sha256": binding["card_revision_sha256"], "shard_id": binding["shard_id"],
        "claim_ids": [c["claim_id"] for c in binding["claims"]],
        "policy_sha256": hashlib.sha256(encoded(POLICY)).hexdigest(),
        "policy": POLICY, "predecessor_receipt_sha256": None,
        "native_canon": canon_reference(out, binding)})
    write(out / "applicability.json", inspect(out, genesis, CAMPAIGN))
    env = dict(os.environ, PYTHONPATH=str(Path(genesis) / "src"), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", "-m", "axm_verify.cli", "shard",
                           str(out / "shard"), "--trusted-key", str(out / "local-test.pub")],
                          capture_output=True, text=True, env=env)
    write(out / "native-verifier.json", {"exit_code": proc.returncode,
                                         "stdout": proc.stdout, "stderr": proc.stderr})
    if proc.returncode:
        raise ValueError("Native verifier CLI failed; raw output retained")
    return inspect(out, genesis, CAMPAIGN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--genesis", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=HERE / "run3-v3")
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--scratch", type=Path, default=Path("S:/Scratch/Runs/run3-shelf-join"))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--canon", type=Path, help="Pinned Canon source cache; fresh native validation when supplied")
    args = parser.parse_args()
    result = build(args.output, args.genesis, args.scratch, args.canon) if args.action == "build" else inspect(
        args.output, args.genesis, args.campaign, read(args.context) if args.context else None, args.canon)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["applicability"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
