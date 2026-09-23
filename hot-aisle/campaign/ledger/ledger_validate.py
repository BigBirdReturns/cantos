#!/usr/bin/env python3
"""Validate one or more run-ledger records against ledger.schema.json. Stdlib only.

    python ledger_validate.py <ledger.json> [...]     exit 0 = all valid, 1 = problems (listed)
    python ledger_validate.py --selftest              runs the fixtures under fixtures/ledger/

The schema file is a plain JSON description (no jsonschema library). Checks:
  1. required fields and types per group (nullable only where declared)
  2. every null field has a reason in the group's null_reasons
  3. clocks non-decreasing; acquisition counts agree with the attempts array
  4. work ordering (accepted <= correct <= completed <= attempted)
  5. money: modeled_usd = rate * gpus * minutes / 60
  6. derived values recomputed from the groups above
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "ledger.schema.json")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_ts(s):
    return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z") if "." not in s else \
        datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")


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
        if "min" in fspec and isinstance(v, (int, float)) and v < fspec["min"]:
            errors.append(f"{where}.{name}: {v} < min {fspec['min']}")
        if "max" in fspec and isinstance(v, (int, float)) and v > fspec["max"]:
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
    # reasons for fields that are not null are harmless but flagged as noise
    for name in (null_reasons or {}):
        if name in obj and obj[name] is not None:
            errors.append(f"{where}.null_reasons.{name}: reason given but field is not null")


def _work_window_s(clocks):
    a, b = clocks.get("t_work_start"), clocks.get("t_work_end")
    if a and b and ISO_RE.match(a) and ISO_RE.match(b):
        return (parse_ts(b) - parse_ts(a)).total_seconds()
    return None


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
            if gname not in schema["top_level"]["required"]:
                continue
            errors.append(f"record.{gname}: missing group")
            continue
        if not isinstance(g, dict):
            errors.append(f"record.{gname}: must be an object")
            continue
        _check_fields(g, gspec, gname, errors)

    # ---- cross-field rules -------------------------------------------------
    clocks = record.get("clocks") or {}
    order = ["t_request", "t_ssh", "t_ready", "t_work_start", "t_work_end", "t_released"]
    last = None
    for k in order:
        v = clocks.get(k)
        if v and isinstance(v, str) and ISO_RE.match(v):
            t = parse_ts(v)
            if last and t < last[1]:
                errors.append(f"clocks: {k} ({v}) is earlier than {last[0]} ({last[2]})")
            last = (k, t, v)

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
            if isinstance(a, dict) and a.get("method") not in ("console-create", "tui-provision", "api-create", "estate-lease"):
                errors.append(f"acquisition.attempts[{i}].method '{a.get('method')}' is a listing, not an attempt")

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
    if w.get("evaluator") is None and corr is not None:
        errors.append("work: correct is non-null but no evaluator is named")

    s = record.get("sustained") or {}
    if isinstance(s.get("window_s"), (int, float)) and isinstance(s.get("required_window_s"), int):
        want = s["window_s"] >= s["required_window_s"]
        if s.get("meets_required_window") is not want:
            errors.append(f"sustained.meets_required_window should be {want}")

    m = record.get("money") or {}
    gpus = (record.get("identity") or {}).get("gpus")
    if all(isinstance(m.get(k), (int, float)) for k in ("list_rate_per_gpu_hr", "modeled_minutes", "modeled_usd")) and isinstance(gpus, int):
        want = m["list_rate_per_gpu_hr"] * gpus * m["modeled_minutes"] / 60.0
        if abs(want - m["modeled_usd"]) > 0.01:
            errors.append(f"money.modeled_usd {m['modeled_usd']} != rate*gpus*minutes/60 = {want:.4f}")

    d = record.get("derived") or {}
    basis = d.get("cost_basis")
    cost = {"modeled": m.get("modeled_usd"), "billed": m.get("billed_usd"), "energy": (m.get("energy") or {}).get("usd")}.get(basis)
    if isinstance(cost, (int, float)) and isinstance(acc, int) and acc > 0:
        want = cost / acc
        if isinstance(d.get("usd_per_accepted"), (int, float)) and abs(d["usd_per_accepted"] - want) > max(1e-9, 1e-6 * want):
            errors.append(f"derived.usd_per_accepted {d['usd_per_accepted']} != {basis} cost / accepted = {want}")
        if isinstance(d.get("usd_per_1k_accepted"), (int, float)) and abs(d["usd_per_1k_accepted"] - want * 1000) > max(1e-6, 1e-6 * want * 1000):
            errors.append(f"derived.usd_per_1k_accepted {d['usd_per_1k_accepted']} != {want * 1000}")
    ww = _work_window_s(clocks)
    if ww is not None and isinstance(acc, int) and acc > 0:
        if isinstance(d.get("wall_s_per_accepted"), (int, float)) and abs(d["wall_s_per_accepted"] - ww / acc) > 1e-6 * max(1.0, ww / acc):
            errors.append(f"derived.wall_s_per_accepted {d['wall_s_per_accepted']} != work window {ww}s / accepted {acc}")
        if isinstance(d.get("accepted_per_s"), (int, float)) and abs(d["accepted_per_s"] - acc / ww) > 1e-6 * max(1.0, acc / ww):
            errors.append(f"derived.accepted_per_s {d['accepted_per_s']} != accepted / work window")

    for i, item in enumerate((record.get("receipts") or {}).get("items") or []):
        if isinstance(item, dict) and item.get("sha256") is not None and not SHA_RE.match(str(item["sha256"])):
            errors.append(f"receipts.items[{i}].sha256 is not 64 hex chars")
    return errors


def validate_file(path, schema=None):
    with open(path, encoding="utf-8") as f:
        try:
            rec = json.load(f)
        except json.JSONDecodeError as e:
            return [f"{path}: not JSON ({e})"]
    return validate(rec, schema)


# ---------------------------------------------------------------- self-test
def selftest():
    """fixtures/ledger/valid-*.json must pass; fixtures/ledger/invalid-*.json must fail
    and each must contain a top-level "_expect" substring found in the error list."""
    fx = os.path.join(HERE, "fixtures", "ledger")
    schema = load_schema()
    names = sorted(os.listdir(fx))
    passed = failed = 0
    for n in names:
        if not n.endswith(".json"):
            continue
        p = os.path.join(fx, n)
        with open(p, encoding="utf-8") as f:
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
    # the worked examples, if built, must validate too
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
