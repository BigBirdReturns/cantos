#!/usr/bin/env python3
"""Read-only Cantos GitHub CI/Pages and served-kit source-identity witness.

A PASS joins a current public main commit, its latest exact-head qualification,
its latest exact-head Pages deployment and the exact served recipient bytes.
GitHub responses are TLS client-vantage observations, not signed attestations.
Offline verification requires an independently retained receipt SHA-256.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

REPOSITORY = "BigBirdReturns/cantos"
PAGES_URL = "https://bigbirdreturns.github.io/cantos/public/open-compute/maintainer-kit.zip"
API = "https://api.github.com/repos/" + REPOSITORY
MAX_KIT_BYTES = 25_000_000
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = ("id", "head_sha", "event", "status", "conclusion",
          "created_at", "run_attempt", "html_url")
QUALIFY = "hot-aisle-ci.yml"
PAGES = "pages.yml"


class WitnessError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise WitnessError(message)


def expectation(commit, digest, size):
    require(isinstance(commit, str) and bool(_SHA.fullmatch(commit)), "exact 40-digit commit required")
    require(isinstance(digest, str) and bool(_DIGEST.fullmatch(digest)), "exact 64-digit kit SHA-256 required")
    require(type(size) is int and 1 <= size <= MAX_KIT_BYTES, "bounded kit byte count required")
    return {"repository": REPOSITORY, "commit": commit,
            "kit_sha256": digest, "kit_bytes": size, "kit_url": PAGES_URL}


def run_view(run):
    require(type(run) is dict, "run must be an object")
    row = {k: run.get(k) for k in FIELDS}
    require(type(row["id"]) is int and row["id"] > 0, "run id")
    require(type(row["run_attempt"]) is int and row["run_attempt"] > 0, "run attempt")
    require(isinstance(row["head_sha"], str) and bool(_SHA.fullmatch(row["head_sha"])), "run SHA")
    require(isinstance(row["event"], str), "run event")
    require(row["status"] in ("queued", "requested", "waiting", "pending",
                               "in_progress", "completed"), "run status")
    require(isinstance(row["created_at"], str) and row["created_at"].endswith("Z"), "run created_at")
    return row


def latest(runs, sha, events):
    require(type(runs) is list and len(runs) <= 100, "bounded workflow rows")
    eligible = [r for r in (run_view(x) for x in runs)
                if r["head_sha"] == sha and r["event"] in events]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r["created_at"], r["id"], r["run_attempt"]))


def evaluate(expected, observation):
    require(type(expected) is dict and expected == expectation(
        expected.get("commit"), expected.get("kit_sha256"),
        expected.get("kit_bytes")), "expected source binding")
    require(type(observation) is dict, "observation object")
    require(type(observation.get("main_sha")) is str and
            bool(_SHA.fullmatch(observation["main_sha"])), "main SHA observation")
    require(type(observation.get("qualify_runs")) is list, "qualification observations")
    require(type(observation.get("pages_runs")) is list, "Pages observations")
    served = observation.get("served_kit")
    require(type(served) is dict, "served kit observation")
    require(served.get("url") == PAGES_URL and served.get("effective_url") == PAGES_URL,
            "canonical Pages URL and redirect boundary")
    require(type(served.get("http_status")) is int, "HTTP status")
    require(type(served.get("bytes")) is int and 0 <= served["bytes"] <= MAX_KIT_BYTES,
            "bounded served bytes")
    require(type(served.get("sha256")) is str and
            bool(_DIGEST.fullmatch(served["sha256"])), "served content digest")
    current = observation["main_sha"] == expected["commit"]
    ci = latest(observation["qualify_runs"], expected["commit"], {"push", "workflow_dispatch"})
    pages = latest(observation["pages_runs"], expected["commit"], {"workflow_run", "workflow_dispatch"})
    findings = []
    if not current:
        findings.append("main_commit_mismatch")
    for name, row in (("qualification", ci), ("pages", pages)):
        if row is None:
            findings.append(name + "_missing")
        elif row["status"] != "completed":
            findings.append(name + "_pending")
        elif row["conclusion"] != "success":
            findings.append(name + "_failed")
    if served["http_status"] != 200:
        findings.append("kit_http_failure")
    if served["bytes"] != expected["kit_bytes"]:
        findings.append("kit_length_mismatch")
    if served["sha256"] != expected["kit_sha256"]:
        findings.append("kit_digest_mismatch")
    state = "HOLD" if any(x.endswith(("_mismatch", "_failed", "_failure")) for x in findings) else (
        "WAIT" if findings else "PASS")
    return {"state": state, "findings": findings,
            "current_main_matches": current,
            "qualification_run_id": ci["id"] if ci else None,
            "qualification_attempt": ci["run_attempt"] if ci else None,
            "pages_run_id": pages["id"] if pages else None,
            "pages_attempt": pages["run_attempt"] if pages else None,
            "served_sha256": served["sha256"],
            "served_bytes": served["bytes"],
            "evidence_class": "sampled_public_client_vantage"}


def get(url, *, max_bytes):
    req = Request(url, headers={"Accept": "application/vnd.github+json",
                                "User-Agent": "cantos-publication-witness-1"})
    with urlopen(req, timeout=20) as r:
        body = r.read(max_bytes + 1)
        require(len(body) <= max_bytes, "HTTP body limit")
        return {"raw": body, "status": r.status, "effective_url": r.geturl(),
                "url": url}


def api_json(url):
    result = get(url, max_bytes=4_000_000)
    require(result["status"] == 200 and result["effective_url"] == url,
            "GitHub API status or redirect")
    payload = json.loads(result["raw"])
    return payload, {"url": url, "status": result["status"],
                     "bytes": len(result["raw"]),
                     "sha256": sha256(result["raw"]).hexdigest()}


def observe(expected):
    commit = expected["commit"]
    urls = (
        API + "/git/ref/heads/main",
        API + "/actions/workflows/" + QUALIFY + "/runs?head_sha=" + commit + "&per_page=100",
        API + "/actions/workflows/" + PAGES + "/runs?head_sha=" + commit + "&per_page=100",
    )
    responses = [api_json(url) for url in urls]
    main, qual, pages = (x[0] for x in responses)
    require(type(main) is dict and type(main.get("object")) is dict, "GitHub main response")
    require(type(qual) is dict and type(qual.get("workflow_runs")) is list, "GitHub qualification runs")
    require(type(pages) is dict and type(pages.get("workflow_runs")) is list, "GitHub Pages runs")
    kit = get(PAGES_URL, max_bytes=MAX_KIT_BYTES)
    require(kit["effective_url"] == PAGES_URL, "Pages redirected outside exact artifact URL")
    observation = {
        "main_sha": main["object"].get("sha"),
        "qualify_runs": [run_view(x) for x in qual["workflow_runs"][:100]],
        "pages_runs": [run_view(x) for x in pages["workflow_runs"][:100]],
        "served_kit": {"url": PAGES_URL, "effective_url": kit["effective_url"],
                       "http_status": kit["status"], "bytes": len(kit["raw"]),
                       "sha256": sha256(kit["raw"]).hexdigest()},
        "api_evidence": [x[1] for x in responses]
    }
    return observation


def canonical(document):
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def verify(raw, pinned_sha256):
    require(bool(_DIGEST.fullmatch(pinned_sha256)), "external SHA-256 pin")
    require(sha256(raw).hexdigest() == pinned_sha256, "receipt SHA-256 mismatch")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WitnessError("malformed receipt") from exc
    require(type(doc) is dict and doc.get("schema") == "cantos.publication-witness/1", "receipt schema")
    decision = evaluate(doc.get("expected"), doc.get("observed"))
    require(decision == doc.get("decision"), "receipt decision does not replay")
    return decision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    obs = sub.add_parser("observe", help="Read public GitHub CI/Pages and kit; no write to provider")
    obs.add_argument("--commit", required=True)
    obs.add_argument("--kit-sha256", required=True)
    obs.add_argument("--kit-bytes", required=True, type=int)
    obs.add_argument("--receipt", required=True, type=Path)
    ver = sub.add_parser("verify", help="Recompute decision from an externally pinned offline receipt")
    ver.add_argument("--receipt", required=True, type=Path)
    ver.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "observe":
            expected = expectation(args.commit, args.kit_sha256, args.kit_bytes)
            observation = observe(expected)
            doc = {"schema": "cantos.publication-witness/1",
                   "observed_at": datetime.now(timezone.utc).isoformat(),
                   "expected": expected, "observed": observation,
                   "decision": evaluate(expected, observation)}
            raw = canonical(doc)
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_bytes(raw)
            decision = doc["decision"]
            print(json.dumps({"state": decision["state"],
                              "findings": decision["findings"],
                              "receipt_sha256": sha256(raw).hexdigest(),
                              "receipt": str(args.receipt)}))
        else:
            decision = verify(args.receipt.read_bytes(), args.sha256)
            print(json.dumps(decision, sort_keys=True))
        return {"PASS": 0, "HOLD": 2, "WAIT": 3}[decision["state"]]
    except (WitnessError, OSError, ValueError, KeyError) as exc:
        print("publication witness invalid or unavailable: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
