"""Seeded shelf qualification: native Python/browser parity and scoped properties.

No generated specimen is an observation or an admitted card. The population is
stratified by declared rule boundaries, not fitted to an empirical normal curve.
"""
from __future__ import annotations
import argparse
import collections
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import platform
from pathlib import Path
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent
VERSION = "shelf-generated/1"
PROFILES = {
    "smoke": {"valid": 100, "faults": 300, "pairs": 1000, "transitions": 100},
    "ci": {"valid": 500, "faults": 3000, "pairs": 10000, "transitions": 500},
    "full": {"valid": 10000, "faults": 100000, "pairs": 1000000, "transitions": 10000},
}
spec = importlib.util.spec_from_file_location("generated_native_shelf", TOOL / "scripts/shelf.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
BASES = S.read_cards(TOOL / "data/cards.jsonl")
PURPOSES = ("cost_per_accepted", "accepted_work", "seat_property", "measured_cost", "same_period")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def same_json(left, right):
    """JSON equality: booleans are not numbers; object insertion order is immaterial."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    return type(left) is type(right) and left == right


class Bridge:
    def __init__(self):
        self.process = subprocess.Popen(["node", str(HERE / "generated_bridge.cjs")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def ask(self, request):
        self.process.stdin.write(encoded(request) + b"\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Browser-engine worker stopped: " + self.process.stderr.read().decode("utf-8", errors="replace"))
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()
        error = self.process.stderr.read().decode("utf-8", errors="replace")
        self.process.stderr.close()
        if self.process.returncode:
            raise RuntimeError("Browser-engine worker failed: " + error)


def native(request, catalog=()):
    try:
        operation = request["operation"]
        args = request.get("args")
        if "refs" in request:
            args = [catalog[i] for i in request["refs"]]
            if operation == "compose":
                args.append(request["purpose"])
        function = {"validate": S.validate_card, "compose": S.compose, "which": S.which}[operation]
        return {"ok": True, "value": function(*args)}
    except Exception as exc:
        return {"ok": False, "error": {"name": type(exc).__name__, "message": str(exc)}}


def variant(seed, index, archetype=None):
    """Retained archetypes with explicitly synthetic neighborhood changes."""
    rng = random.Random(f"{seed}:{index}")
    c = copy.deepcopy(BASES[index % len(BASES) if archetype is None else archetype])
    c["generated_from"] = c["id"]
    c["id"] = f"generated-{seed}-{index}"
    c["title"] = "Synthetic qualification specimen " + str(index)
    c["spine"] = "Generated test data; no empirical claim, admission or new observation."
    c["filing_version"] = 2
    c["a_claim"]["limits"] = ["Synthetic variation for software qualification; not evidence."]
    for name in ("imported", "modeled", "attributed"):
        c["dimensions"][name] = rng.choice([True, False, None])
    c["a_claim"]["conditions"]["gpus"] = {"value": rng.choice([1, 2, 4, 8]), "unit": "GPUs"}
    benefit = rng.choice([True, False, None])
    c["c_parties"]["observer_benefit"] = {
        "benefits_from_outcome": benefit, "relationship": "generated relationship" if benefit is not None else None,
        "basis": "explicitly synthetic role" if benefit is not None else None,
    }
    c["c_parties"]["funding"] = rng.choice([None, "synthetic self-funded", "synthetic provider credit"])
    for name in ("inspected", "recomputed", "repeated"):
        done = rng.choice([True, False])
        c["e_checks"][name] = {"who": "synthetic-actor" if done else None, "when": "2026-09-24" if done else None}
    return c


FAULTS = (
    "dimension-integer", "dimension-string", "dimension-extra", "funding-missing",
    "benefit-missing", "benefit-integer", "benefit-basis", "period-missing",
    "publication-basis", "hourly-ambiguous", "hourly-short", "hourly-hr",
    "rate-boolean", "rate-negative", "seat-count-missing", "seat-count-boolean",
    "check-object", "check-who", "check-when", "id-uppercase", "id-long",
    "title-multiline", "spine-empty", "version-missing", "results-array",
    "parties-array", "dimensions-array", "claim-array", "population-missing",
    "materials-missing", "check-missing", "version-boolean",
)


def fault(card, kind):
    c = copy.deepcopy(card)
    if kind == "dimension-integer": c["dimensions"]["measured"] = 1
    elif kind == "dimension-string": c["dimensions"]["measured"] = "true"
    elif kind == "dimension-extra": c["dimensions"]["trusted"] = True
    elif kind == "funding-missing": del c["c_parties"]["funding"]
    elif kind == "benefit-missing": del c["c_parties"]["observer_benefit"]
    elif kind == "benefit-integer": c["c_parties"]["observer_benefit"]["benefits_from_outcome"] = 1
    elif kind == "benefit-basis": c["c_parties"]["observer_benefit"].update(benefits_from_outcome=True, basis=None)
    elif kind == "period-missing": del c["a_claim"]["period"]
    elif kind == "publication-basis": c["a_claim"]["period"].update(publication_date="2026-09-24", publication_date_basis=None)
    elif kind.startswith("hourly-"):
        unit = {"hourly-ambiguous": "USD/hour", "hourly-short": "USD/h", "hourly-hr": "USD/hr"}[kind]
        c["a_claim"]["results"]["generated_rate"] = {"value": 1.68, "unit": unit}
    elif kind in ("rate-boolean", "rate-negative"):
        c["a_claim"]["results"]["generated_rate"] = {"value": True if kind == "rate-boolean" else -0.01, "unit": "USD / GPU-hour"}
    elif kind.startswith("seat-count-"):
        c["a_claim"]["results"]["generated_rate"] = {"value": 3.36, "unit": "USD / seat-hour"}
        c["a_claim"]["conditions"]["gpus"] = None if kind.endswith("missing") else True
    elif kind == "check-object": c["e_checks"]["inspected"] = []
    elif kind == "check-who": c["e_checks"]["inspected"]["who"] = ""
    elif kind == "check-when": c["e_checks"]["inspected"]["when"] = ""
    elif kind == "id-uppercase": c["id"] = "Invalid"
    elif kind == "id-long": c["id"] = "a" * 65
    elif kind == "title-multiline": c["title"] = "first\nsecond"
    elif kind == "spine-empty": c["spine"] = ""
    elif kind == "version-missing": del c["filing_version"]
    elif kind == "version-boolean": c["filing_version"] = True
    elif kind == "results-array": c["a_claim"]["results"] = [1]
    elif kind == "parties-array": c["c_parties"] = [1]
    elif kind == "dimensions-array": c["dimensions"] = [True, True, False, False]
    elif kind == "claim-array": c["a_claim"] = [1]
    elif kind == "population-missing": del c["b_population"]
    elif kind == "materials-missing": del c["d_materials"]
    elif kind == "check-missing": del c["e_checks"]["repeated"]
    return c


def validation_cases(seed, count, invalid=False):
    for index in range(count):
        card = variant(seed, index)
        kind = FAULTS[index % len(FAULTS)] if invalid else "valid-neighborhood"
        if invalid: card = fault(card, kind)
        requests = [{"operation": "validate", "args": [card]}]
        if invalid:
            requests.append({"operation": "which", "args": [[card], "USD / GPU-hour", None, False]})
        yield {"label": kind, "index": index, "requests": requests,
               "expect": "invalid" if invalid else "valid"}


def transition_cases(seed, count):
    labels = ("price-locality", "benefit-locality", "funding-access-locality", "retrieval-not-observation",
              "period-boundary", "measurement-boundary", "repeat-does-not-rewrite",
              "import-does-not-negate-measurement", "unit-boundary", "null-is-not-a-result")
    for index in range(count):
        a = variant(seed, index, archetype=0)
        day = dt.date(2026, 9, 1) + dt.timedelta(days=index % 28)
        a["a_claim"]["period"] = {"experiment_date": day.isoformat(), "publication_date": None, "publication_date_basis": None}
        a["dimensions"]["measured"] = True
        unit = "USD / 1000 accepted requests"
        if index % 10 == 9:
            a["a_claim"]["results"] = {"probe": {"value": 0.74, "unit": unit}}
        b = copy.deepcopy(a)
        label = labels[index % len(labels)]
        if label == "price-locality": b["a_claim"]["results"]["h100_rate"]["value"] = round(0.1 + (index % 100) / 10, 2)
        elif label == "benefit-locality": b["c_parties"]["observer_benefit"] = {"benefits_from_outcome": True, "relationship": "synthetic interest", "basis": "generated declared relation"}
        elif label == "funding-access-locality": b["c_parties"].update(funding="synthetic sponsor", access={"mode": "synthetic granted"})
        elif label == "retrieval-not-observation": b["a_claim"]["period"]["retrieved_at"] = "2029-12-31"
        elif label == "period-boundary": b["a_claim"]["period"]["experiment_date"] = (day + dt.timedelta(days=1)).isoformat()
        elif label == "measurement-boundary": b["dimensions"]["measured"] = False
        elif label == "repeat-does-not-rewrite": b["e_checks"]["repeated"] = {"who": "synthetic-repeat-actor", "when": day.isoformat()}
        elif label == "import-does-not-negate-measurement": b["dimensions"]["imported"] = not bool(a["dimensions"]["imported"])
        elif label == "unit-boundary":
            for result in b["a_claim"]["results"].values():
                if isinstance(result, dict) and result.get("unit") == unit: result["unit"] = "USD / 1000 attempted requests"
        elif label == "null-is-not-a-result": b["a_claim"]["results"]["probe"]["value"] = None
        yield {"label": label, "index": index, "requests": [
            {"operation": "which", "args": [[c], unit, day.isoformat(), True]} for c in (a, b)],
            "expect": "transition"}


def composition_pool(seed, count):
    pool, facts = [], []
    # Facts belong to the generator's archetype grammar. They do not call either
    # engine's unit/date predicates to derive their expected answers.
    units = [("USD / 1000 accepted requests", True), ("accepted requests", True),
             ("requests/s", False), ("USD / GPU-hour", False),
             ("unaccepted requests", False), ("accepted bananas", False)]
    for index in range(count):
        c = variant(seed, index)
        unit, accepted = units[index % len(units)]
        measured = [True, False, None][(index // len(units)) % 3]
        date = None if (index // 18) % 4 == 0 else f"2026-09-{1 + (index // 72) % 28:02d}"
        c["dimensions"]["measured"] = measured
        c["a_claim"]["period"] = {"experiment_date": date, "publication_date": None,
                                    "publication_date_basis": None, "retrieved_at": "2026-09-24"}
        c["a_claim"]["results"] = {"probe": {"value": round(0.01 + index / 100, 2), "unit": unit}}
        pool.append(c)
        facts.append({"accepted": accepted, "measured": measured is True, "date": date,
                      "unit": unit, "archetype": c["generated_from"]})
    return pool, facts


def composition_cases(seed, count, pool, facts):
    size = len(pool)
    # A coprime stride traverses distinct ordered pairs; full profile covers the
    # complete 1,000 x 1,000 pool once, with purposes spread across both operands.
    stride = size + 1
    while math.gcd(stride, size * size) != 1: stride += 1
    for index in range(count):
        a, b = divmod((index * stride + seed) % (size * size), size)
        purpose = PURPOSES[(a + b) % len(PURPOSES)]
        fa, fb = facts[a], facts[b]
        if purpose == "cost_per_accepted":
            refused = not (fa["accepted"] and fb["accepted"]); rule = "unit mismatch:"
        elif purpose == "accepted_work":
            refused = not fb["accepted"]; rule = "throughput or latency is not accepted work"
        elif purpose in ("seat_property", "measured_cost"):
            refused = not fb["measured"]
            rule = "an attributed managed-cluster rating" if purpose == "seat_property" else "a party's list price statement"
        else:
            unknown = fa["date"] is None or fb["date"] is None
            refused = unknown or fa["date"] != fb["date"]
            rule = "comparable observation/publication period unknown" if unknown else "periods differ"
        yield {"label": purpose, "index": index, "requests": [
            {"operation": "compose", "refs": [a, b], "purpose": purpose}],
            "expect": "refusal" if refused else "no-refusal", "rule": rule}


def property_failure(case, outputs):
    if any(not o.get("ok") for o in outputs): return "native-exception"
    values = [o["value"] for o in outputs]
    expect = case["expect"]
    if expect == "valid" and values[0] != []: return "validity"
    if expect == "invalid":
        if not values[0]: return "one-fault-not-refused"
        if values[1][0]["status"] != "CANNOT_USE": return "invalid-filing-query-support"
    if expect == "refusal":
        if not isinstance(values[0], str): return "refusal"
        if not values[0].startswith(case["rule"]): return "wrong-refusal-rule"
    if expect == "no-refusal" and values[0] is not None: return "unexpected-refusal"
    if expect == "transition":
        before, after = values[0][0], values[1][0]
        if before["status"] != "SUPPORTS": return "transition-precondition"
        if case["label"] in ("period-boundary", "measurement-boundary", "unit-boundary", "null-is-not-a-result"):
            if after["status"] != "CANNOT_USE": return "query-boundary"
        elif case["label"] in ("repeat-does-not-rewrite", "import-does-not-negate-measurement"):
            if after["status"] != "SUPPORTS" or before["results"] != after["results"]: return "measurement-locality"
        elif before != after: return "metadata-locality"
    return None


def reductions(value):
    """Bounded structural delta-debugging candidates; no schema is invented."""
    if isinstance(value, dict):
        for key in value:
            yield {k: v for k, v in value.items() if k != key}
        for key, child in value.items():
            for smaller in reductions(child):
                out = dict(value); out[key] = smaller; yield out
    elif isinstance(value, list):
        for index in range(len(value)):
            yield value[:index] + value[index + 1:]
        for index, child in enumerate(value):
            for smaller in reductions(child):
                out = list(value); out[index] = smaller; yield out
    elif isinstance(value, str) and value:
        yield ""
    elif type(value) in (int, float) and value != 0:
        yield 0


def shrink_parity(request, bridge, budget=300):
    """Reduce a differential counterexample while retaining its operation arity.

    Schema-validity property failures retain their original generated witness;
    removing required fields would manufacture a different failure, not shrink it.
    """
    current = copy.deepcopy(request)
    attempts = 0
    while attempts < budget:
        changed = False
        for index, argument in enumerate(current["args"]):
            for candidate in reductions(argument):
                test = copy.deepcopy(current); test["args"][index] = candidate
                attempts += 1
                py, js = native(test), bridge.ask(test)
                # Keep a disagreement between returned decisions. Two unrelated
                # interpreter exceptions are not the same counterexample.
                if py.get("ok") and js.get("ok") and not same_json(py, js):
                    current = test; changed = True; break
                if attempts >= budget: break
            if changed or attempts >= budget: break
        if not changed: break
    return current, attempts


def run(seed, counts, output, batch_size=256, max_failures=20):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    files = [Path(__file__), HERE / "generated_bridge.cjs", TOOL / "scripts/shelf.py", TOOL / "index.html", TOOL / "data/cards.jsonl"]
    source_hashes = {str(p.relative_to(TOOL)).replace("\\", "/"): sha(p.read_bytes()) for p in files}
    bridge = Bridge()
    size = max(10, math.ceil(math.sqrt(counts["pairs"])))
    pool, facts = composition_pool(seed, size)
    pool_hash = sha(encoded(pool))
    assert bridge.ask({"catalog": pool}) == {"loaded": len(pool)}
    counters = collections.Counter()
    coverage = collections.Counter()
    failures = []
    stream_hash = hashlib.sha256()

    def check(batch, phase):
        requests = [req for case in batch for req in case["requests"]]
        js = bridge.ask(requests)
        if len(js) != len(requests): raise RuntimeError("Browser worker response cardinality changed")
        offset = 0
        for case in batch:
            reqs = case["requests"]
            pys = [native(req, pool) for req in reqs]
            jss = js[offset:offset + len(reqs)]; offset += len(reqs)
            stream_hash.update(encoded({"phase": phase, "case": case}))
            counters[phase] += 1
            counters["engine_comparisons"] += len(reqs)
            coverage[phase + ":" + case["label"]] += 1
            for reply in pys:
                if reply.get("ok") and isinstance(reply["value"], list):
                    for row in reply["value"]:
                        if isinstance(row, dict) and row.get("status") in ("SUPPORTS", "CANNOT_USE"):
                            counters["query_" + row["status"]] += 1
            if phase == "pairs": counters["pair_" + case["expect"]] += 1
            reason = "parity" if not same_json(pys, jss) else property_failure(case, pys)
            if reason:
                if len(failures) < max_failures:
                    retained = copy.deepcopy(case)
                    for req in retained["requests"]:
                        if "refs" in req:
                            req["args"] = [pool[i] for i in req.pop("refs")] + [req.pop("purpose")]
                    witness = {"seed": seed, "generator": VERSION, "phase": phase, "reason": reason,
                               "case": retained, "python": pys, "browser": jss}
                    if reason == "parity":
                        position = next(i for i, (py, browser) in enumerate(zip(pys, jss)) if not same_json(py, browser))
                        reduced, attempts = shrink_parity(retained["requests"][position], bridge)
                        witness.update(minimized=reduced, shrink_attempts=attempts,
                                       minimization_scope="bounded structural reduction preserving a returned-decision disagreement")
                    else:
                        witness["minimization_scope"] = "original single-fault/transition witness retained; required fields are not removed to manufacture failure"
                    name = f"failure-{len(failures):03d}.json"
                    (output / name).write_bytes(encoded(witness) + b"\n")
                    failures.append(name)
                counters["failures"] += 1

    try:
        phases = [
            ("valid", validation_cases(seed, counts["valid"])),
            ("faults", validation_cases(seed, counts["faults"], True)),
            ("transitions", transition_cases(seed, counts["transitions"])),
            ("pairs", composition_cases(seed, counts["pairs"], pool, facts)),
        ]
        for phase, cases in phases:
            batch = []
            for case in cases:
                batch.append(case)
                if len(batch) >= batch_size:
                    check(batch, phase); batch = []
            if batch: check(batch, phase)
            print(json.dumps({"phase": phase, "cases": counters[phase], "failures_so_far": counters["failures"],
                              "elapsed_seconds": round(time.perf_counter() - started, 2)}), flush=True)
    finally:
        bridge.close()
    after_hashes = {str(p.relative_to(TOOL)).replace("\\", "/"): sha(p.read_bytes()) for p in files}
    if source_hashes != after_hashes:
        counters["failures"] += 1
        failures.append("source changed during qualification; rerun against a stable source identity")
    counters["failures"] += 0
    report = {"schema": VERSION, "seed": seed, "counts": counts, "observed": dict(counters),
              "coverage": dict(sorted(coverage.items())), "case_stream_sha256": stream_hash.hexdigest(),
              "pool_size": size, "pool_sha256": pool_hash, "ordered_pair_population": size * size,
              "pair_scope": "one purpose per distinct ordered pair; five purposes stratified across operands, not all five purposes for every pair",
              "parity": "type-aware JSON decisions and diagnostics; booleans distinct from numbers, array order preserved, object order ignored",
              "source_sha256": source_hashes, "source_stable": source_hashes == after_hashes,
              "source_sha256_after": after_hashes,
              "python": platform.python_version(), "node": subprocess.check_output(["node", "--version"], text=True).strip(),
              "elapsed_seconds": round(time.perf_counter() - started, 3), "failures": failures,
              "scope": "Deterministic stratified software qualification around five retained archetypes. Generated specimens are not evidence, human-use observations, statistical population coverage or independent empirical trials. No normal-distribution/three-sigma claim. Compose tests only its declared purposes; no-refusal is not admission. Configuration alignment, admission-policy monotonicity and arbitrary claim entailment remain outside this API."}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report": str(output / "report.json"), "observed": dict(counters)}), flush=True)
    return 1 if counters["failures"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="smoke")
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if args.replay:
        witness = json.loads(args.replay.read_bytes())
        bridge = Bridge()
        outputs, mismatch = [], False
        try:
            for request in witness["case"]["requests"]:
                py, js = native(request), bridge.ask(request)
                outputs.append(py)
                mismatch |= not same_json(py, js)
                print(json.dumps({"python": py, "browser": js}, ensure_ascii=False))
            if "minimized" in witness:
                py, js = native(witness["minimized"]), bridge.ask(witness["minimized"])
                mismatch |= not same_json(py, js) or not py.get("ok")
                print(json.dumps({"minimized": True, "python": py, "browser": js}, ensure_ascii=False))
        finally: bridge.close()
        return 1 if mismatch or property_failure(witness["case"], outputs) else 0
    if args.out is None:
        parser.error("--out is required for a generated campaign")
    return run(args.seed, PROFILES[args.profile], args.out)


if __name__ == "__main__":
    raise SystemExit(main())
