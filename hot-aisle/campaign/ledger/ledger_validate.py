#!/usr/bin/env python3
"""Validate one or more run-ledger records against ledger.schema.json. Stdlib only.

    python ledger_validate.py <ledger.json> [...]     exit 0 = all valid, 1 = problems (listed)
    python ledger_validate.py --selftest              runs the fixtures under fixtures/ledger/

The schema file is a plain JSON description (no jsonschema library). Checks:
  1. required fields and types per group (nullable only where declared)
  2. every null field has a reason in the group's null_reasons
  3. clocks non-decreasing; acquisition counts agree with the attempts array; attempts are delivered-layer
     rows with method api-create | console-create | tui-provision (listings never count)
  4. work ordering (accepted <= correct <= completed <= attempted); correct requires a FROZEN evaluator with a ref
  5. traversal: accepted_closures_per_traversal recomputed from accepted / traversals
  6. money: modeled_usd only over request->release; lower bound arithmetic
  7. derived: $/accepted, buyer wall clock (request->release, null otherwise), work-time throughput kept separate
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ledger_common import ATTEMPT_METHODS, ISO_RE, SHA_RE, parse_iso  # noqa: E402

SCHEMA_PATH = os.path.join(HERE, "ledger.schema.json")


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _type_ok(value, t):
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "iso8601":
        return isinstance(value, str) and bool(ISO_RE.match(value))
    if t == "sha256":
        return isinstance(value, str) and bool(SHA_RE.match(value))
    if t == "any":
        return True
    return False


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_fields(obj, spec, where, errors):
    """Generic required/type/nullable/enum/min/max/item_required checks for one group."""
    for req in spec.get("required", []):
        if req not in obj:
            errors.append(f"{where}: missing required field '{req}'")
    null_reasons = obj.get("null_reasons", {})
    if null_reasons is not None and not isinstance(null_reasons, dict):
        errors.append(f"{where}: null_reasons must be an object")
        null_reasons = {}
    for name, fspec in spec.get("fields", {}).items():
        if name not in obj:
            continue
        v = obj[name]
        if v is None:
            if not fspec.get("nullable"):
                errors.append(f"{where}.{name}: null not allowed")
            elif not (null_reasons or {}).get(name):
                errors.append(f"{where}.{name}: null without a reason in {where}.null_reasons")
            continue
        if not _type_ok(v, fspec["type"]):
            errors.append(f"{where}.{name}: expected {fspec['type']}, got {type(v).__name__}")
            continue
        if "enum" in fspec and v not in fspec["enum"]:
            errors.append(f"{where}.{name}: '{v}' not in {fspec['enum']}")
        if "min" in fspec and _num(v) and v < fspec["min"]:
            errors.append(f"{where}.{name}: {v} < min {fspec['min']}")
        if "max" in fspec and _num(v) and v > fspec["max"]:
            errors.append(f"{where}.{name}: {v} > max {fspec['max']}")
        if fspec["type"] == "object" and "required" in fspec:
            for r in fspec["required"]:
                if r not in v:
                    errors.append(f"{where}.{name}: missing '{r}'")
        if fspec["type"] == "array" and "item_required" in fspec:
            for i, item in enumerate(v):
                if not isinstance(item, dict):
                    errors.append(f"{where}.{name}[{i}]: expected object")
                    continue
                for r in fspec["item_required"]:
                    if r not in item:
                        errors.append(f"{where}.{name}[{i}]: missing '{r}'")
    for name in (null_reasons or {}):
        if name in obj and obj[name] is not None:
            errors.append(f"{where}.null_reasons.{name}: reason given but field is not null")


def _span_s(clocks, a, b):
    ta, tb = clocks.get(a), clocks.get(b)
    if isinstance(ta, str) and isinstance(tb, str) and ISO_RE.match(ta) and ISO_RE.match(tb):
        return (parse_iso(tb) - parse_iso(ta)).total_seconds()
    return None


def _close(a, b, rel=1e-6, abs_=1e-9):
    return abs(a - b) <= max(abs_, rel * abs(b))


def validate(record, schema=None):
    """Return a list of error strings (empty = valid)."""
    schema = schema or load_schema()
    errors = []
    if not isinstance(record, dict):
        return ["record is not an object"]
    _check_fields(record, schema["top_level"], "record", errors)
    for gname, gspec in schema["groups"].items():
        g = record.get(gname)
        if g is None:
            if gname in schema["top_level"]["required"]:
                errors.append(f"record.{gname}: missing group")
            continue
        if not isinstance(g, dict):
            errors.append(f"record.{gname}: must be an object")
            continue
        _check_fields(g, gspec, gname, errors)

    # ---- clocks -------------------------------------------------------------
    clocks = record.get("clocks") or {}
    order = ["t_request", "t_ssh", "t_ready", "t_work_start", "t_work_end", "t_released"]
    last = None
    for k in order:
        v = clocks.get(k)
        if v and isinstance(v, str) and ISO_RE.match(v):
            t = parse_iso(v)
            if last and t < last[1]:
                errors.append(f"clocks: {k} ({v}) is earlier than {last[0]} ({last[2]})")
            last = (k, t, v)

    # ---- acquisition --------------------------------------------------------
    acq = record.get("acquisition") or {}
    attempts = acq.get("attempts")
    if isinstance(attempts, list):
        n_alloc = sum(1 for a in attempts if isinstance(a, dict) and a.get("provisioned") is True)
        if acq.get("n_attempts") != len(attempts):
            errors.append(f"acquisition.n_attempts={acq.get('n_attempts')} but attempts has {len(attempts)} entries")
        if acq.get("n_allocations") != n_alloc:
            errors.append(f"acquisition.n_allocations={acq.get('n_allocations')} but {n_alloc} attempts are provisioned")
        if len(attempts) > 0:
            y = acq.get("yield")
            if y is None or abs(y - n_alloc / len(attempts)) > 1e-9:
                errors.append(f"acquisition.yield should be {n_alloc}/{len(attempts)}")
        for i, a in enumerate(attempts):
            if not isinstance(a, dict):
                continue
            if a.get("layer") != "delivered":
                errors.append(f"acquisition.attempts[{i}].layer must be 'delivered' (got {a.get('layer')!r}); listed probes are not attempts")
            if a.get("method") not in ATTEMPT_METHODS:
                errors.append(f"acquisition.attempts[{i}].method {a.get('method')!r} is not one of {list(ATTEMPT_METHODS)} (a listing is not an attempt; 'create-attempt' was renamed)")
            if a.get("provisioned") is True and a.get("outcome") not in (None, "available"):
                errors.append(f"acquisition.attempts[{i}]: provisioned but outcome {a.get('outcome')!r}")

    # ---- work ---------------------------------------------------------------
    w = record.get("work") or {}
    att, comp, corr, acc, lost = (w.get(k) for k in ("attempted", "completed", "correct", "accepted", "lost"))
    if isinstance(att, int) and isinstance(comp, int) and comp > att:
        errors.append(f"work: completed {comp} > attempted {att}")
    if isinstance(corr, int) and isinstance(comp, int) and corr > comp:
        errors.append(f"work: correct {corr} > completed {comp}")
    if isinstance(acc, int) and isinstance(comp, int) and acc > comp:
        errors.append(f"work: accepted {acc} > completed {comp}")
    if isinstance(acc, int) and isinstance(corr, int) and acc > corr:
        errors.append(f"work: accepted {acc} > correct {corr}")
    if isinstance(lost, int) and isinstance(att, int) and isinstance(comp, int) and lost > att - comp:
        errors.append(f"work: lost {lost} > attempted - completed ({att - comp})")
    ev = w.get("evaluator")
    if corr is not None:
        if not isinstance(ev, dict):
            errors.append("work: correct is non-null but no evaluator is named")
        else:
            if ev.get("frozen") is not True:
                errors.append("work.evaluator.frozen must be true for correct to count (unqualified correctness rejected)")
            if not isinstance(ev.get("ref"), str) or not ev.get("ref").strip():
                errors.append("work.evaluator.ref must name the frozen criterion / sidecar for correct to count")
    rule = w.get("acceptance_rule") or {}
    if isinstance(rule, dict) and rule.get("correctness") is True and corr is None:
        errors.append("work.acceptance_rule.correctness is true but work.correct is null")

    # ---- sustained ----------------------------------------------------------
    s = record.get("sustained") or {}
    if _num(s.get("window_s")) and isinstance(s.get("required_window_s"), int):
        want = s["window_s"] >= s["required_window_s"] and not s.get("interrupted") and acc is not None
        if s.get("meets_required_window") is not want:
            errors.append(f"sustained.meets_required_window should be {want}" + (" (accepted is null: an ungraded window cannot qualify)" if acc is None else ""))
    bk = s.get("buckets")
    if isinstance(bk, list) and isinstance(acc, int):
        total = sum(b.get("accepted") or 0 for b in bk if isinstance(b, dict))
        if any(isinstance(b, dict) and b.get("accepted") is not None for b in bk) and total > acc:
            errors.append(f"sustained.buckets sum accepted {total} > work.accepted {acc}")

    # ---- traversal ----------------------------------------------------------
    tr = record.get("traversal") or {}
    if isinstance(tr.get("traversals"), int) and tr["traversals"] > 0 and isinstance(acc, int) and _num(tr.get("accepted_closures_per_traversal")):
        want = acc / tr["traversals"]
        if not _close(tr["accepted_closures_per_traversal"], want, rel=1e-3, abs_=1e-6):
            errors.append(f"traversal.accepted_closures_per_traversal {tr['accepted_closures_per_traversal']} != accepted / traversals = {want:.6g}")
    if _num(tr.get("accepted_closures_per_traversal")) and tr.get("traversals") is None:
        errors.append("traversal.accepted_closures_per_traversal given without traversals (cannot be recomputed)")
    if isinstance(tr.get("bytes_per_traversal"), int) and isinstance(tr.get("footprint_bytes"), int) \
            and tr["bytes_per_traversal"] == tr["footprint_bytes"] and "measured" not in str(tr.get("bytes_per_traversal_basis", "")).lower():
        errors.append("traversal.bytes_per_traversal equals footprint_bytes without a 'measured' basis (footprint is not traversed bytes)")

    # ---- money --------------------------------------------------------------
    m = record.get("money") or {}
    gpus = (record.get("identity") or {}).get("gpus")
    full_span = _span_s(clocks, "t_request", "t_released")
    if _num(m.get("modeled_usd")):
        if full_span is None:
            errors.append("money.modeled_usd is non-null but t_request/t_released are not both known (use modeled_lower_bound_usd)")
        elif _num(m.get("modeled_minutes")) and abs(m["modeled_minutes"] - full_span / 60.0) > 0.02:
            errors.append(f"money.modeled_minutes {m['modeled_minutes']} != (t_released - t_request)/60 = {full_span / 60.0:.3f}")
    for usd_k, min_k in (("modeled_usd", "modeled_minutes"), ("modeled_lower_bound_usd", "modeled_lower_bound_minutes")):
        if _num(m.get("list_rate_per_gpu_hr")) and _num(m.get(min_k)) and _num(m.get(usd_k)) and isinstance(gpus, int):
            want = m["list_rate_per_gpu_hr"] * gpus * m[min_k] / 60.0
            if abs(want - m[usd_k]) > 0.01:
                errors.append(f"money.{usd_k} {m[usd_k]} != rate*gpus*{min_k}/60 = {want:.4f}")
    if _num(m.get("modeled_lower_bound_usd")) and _num(m.get("modeled_usd")) and m["modeled_lower_bound_usd"] > m["modeled_usd"] + 0.01:
        errors.append("money.modeled_lower_bound_usd exceeds modeled_usd")

    # ---- derived ------------------------------------------------------------
    d = record.get("derived") or {}
    basis = d.get("cost_basis")
    cost = {"modeled": m.get("modeled_usd"), "modeled-lower-bound": m.get("modeled_lower_bound_usd"),
            "billed": m.get("billed_usd"), "energy": (m.get("energy") or {}).get("usd")}.get(basis)
    if basis and cost is None and _num(d.get("usd_per_accepted")):
        errors.append(f"derived.usd_per_accepted is non-null but money figure for cost_basis '{basis}' is null")
    if _num(cost) and isinstance(acc, int) and acc > 0:
        want = cost / acc
        if _num(d.get("usd_per_accepted")) and not _close(d["usd_per_accepted"], want):
            errors.append(f"derived.usd_per_accepted {d['usd_per_accepted']} != {basis} cost / accepted = {want}")
        if _num(d.get("usd_per_1k_accepted")) and not _close(d["usd_per_1k_accepted"], want * 1000):
            errors.append(f"derived.usd_per_1k_accepted {d['usd_per_1k_accepted']} != {want * 1000}")
    if isinstance(acc, int) and acc == 0 and _num(d.get("usd_per_accepted")):
        errors.append("derived.usd_per_accepted must be null when accepted is 0 (zero accepted is not zero cost)")
    if _num(d.get("wall_s_per_accepted")):
        if full_span is None:
            errors.append("derived.wall_s_per_accepted is non-null but t_request/t_released are not both known (work-time is not the buyer's clock)")
        elif isinstance(acc, int) and acc > 0 and not _close(d["wall_s_per_accepted"], full_span / acc):
            errors.append(f"derived.wall_s_per_accepted {d['wall_s_per_accepted']} != (t_released - t_request) / accepted = {full_span / acc:.6g}")
    ww = _span_s(clocks, "t_work_start", "t_work_end")
    if ww is not None and isinstance(acc, int) and acc > 0:
        if _num(d.get("work_s_per_accepted")) and not _close(d["work_s_per_accepted"], ww / acc):
            errors.append(f"derived.work_s_per_accepted {d['work_s_per_accepted']} != work window {ww}s / accepted {acc}")
        if ww > 0 and _num(d.get("accepted_per_work_s")) and not _close(d["accepted_per_work_s"], acc / ww):
            errors.append("derived.accepted_per_work_s != accepted / work window")

    # ---- receipts -----------------------------------------------------------
    for i, item in enumerate((record.get("receipts") or {}).get("items") or []):
        if isinstance(item, dict) and item.get("sha256") is not None and not SHA_RE.match(str(item["sha256"])):
            errors.append(f"receipts.items[{i}].sha256 is not 64 hex chars")
    return errors


def validate_file(path, schema=None):
    if not os.path.exists(path):
        return [f"{path}: no such file"]
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return [f"{path}: not readable JSON ({e})"]
    return validate(rec, schema)


# ---------------------------------------------------------------- self-test
def selftest():
    """fixtures/ledger/valid-*.json must pass; fixtures/ledger/invalid-*.json must fail
    and each must contain a top-level "_expect" substring found in the error list."""
    fx = os.path.join(HERE, "fixtures", "ledger")
    schema = load_schema()
    passed = failed = 0
    for n in sorted(os.listdir(fx)):
        if not n.endswith(".json"):
            continue
        with open(os.path.join(fx, n), encoding="utf-8") as f:
            rec = json.load(f)
        errs = validate(rec, schema)
        if n.startswith("valid"):
            ok = not errs
            detail = "" if ok else "; ".join(errs[:3])
        else:
            expect = rec.get("_expect", "")
            ok = bool(errs) and any(expect in e for e in errs)
            detail = f"expected '{expect}' in {errs[:3]}" if not ok else errs[0]
        print(f"  {'PASS' if ok else 'FAIL'}  {n}  {detail}")
        passed += ok
        failed += (not ok)
    # in-memory mutations Astra used: must be rejected
    base = json.load(open(os.path.join(fx, "valid-estate-full.json"), encoding="utf-8"))
    for label, mut, expect in [
        ("evaluator frozen=false", lambda r: r["work"]["evaluator"].update({"frozen": False}), "frozen"),
        ("closures/traversal = 999", lambda r: r["traversal"].update({"accepted_closures_per_traversal": 999}), "accepted_closures_per_traversal"),
        ("wall clock from work time", lambda r: (r["clocks"].update({"t_released": None}), r["clocks"].setdefault("null_reasons", {}).update({"t_released": "x"}), r["money"].update({"modeled_usd": None, "modeled_minutes": None}), r["money"].setdefault("null_reasons", {}).update({"modeled_usd": "x", "modeled_minutes": "x"})), "wall_s_per_accepted"),
    ]:
        r = json.loads(json.dumps(base)); mut(r); errs = validate(r, schema)
        ok = any(expect in e for e in errs)
        print(f"  {'PASS' if ok else 'FAIL'}  mutation: {label} -> {errs[:1] if errs else 'accepted (WRONG)'}")
        passed += ok; failed += (not ok)
    # malformed input paths never traceback
    for p in [os.path.join(fx, "does-not-exist.json"), os.path.join(HERE, "README.md")]:
        errs = validate_file(p, schema)
        ok = bool(errs)
        print(f"  {'PASS' if ok else 'FAIL'}  malformed input reported without traceback: {os.path.basename(p)}")
        passed += ok; failed += (not ok)
    ex = os.path.join(HERE, "examples")
    for n in sorted(os.listdir(ex)) if os.path.isdir(ex) else []:
        if n.endswith(".ledger.json"):
            errs = validate_file(os.path.join(ex, n), schema)
            print(f"  {'PASS' if not errs else 'FAIL'}  examples/{n}  {'; '.join(errs[:3])}")
            passed += (not errs)
            failed += bool(errs)
    print(f"ledger_validate selftest: {passed} passed, {failed} failed")
    return failed == 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    schema = load_schema()
    bad = 0
    for p in argv:
        errs = validate_file(p, schema)
        if errs:
            bad += 1
            print(f"INVALID {p}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"valid   {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
