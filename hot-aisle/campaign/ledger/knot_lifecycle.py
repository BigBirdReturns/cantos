#!/usr/bin/env python3
"""Knot lifecycle: states, allowed transitions, and an append-only hash-chained event log. Stdlib only.

States (CAIRN v0.3 section 8, trimmed to what this week's ledger needs, plus INTERRUPTED/REASSIGNED
for the deliberate-interrupt reschedule in the SYNTHESIS 'smallest demo'):

  ISSUED -> QUOTED -> RESERVED -> PROVISIONED -> RUNNING -> DELIVERED -> KNOT_VERIFIED -> SETTLED -> RELEASED

Failure / side states: PROVISIONING_FAILED, INTERRUPTED, REASSIGNED, DELIVERY_REJECTED,
VERIFICATION_FAILED, EXPIRED, CANCELLED. Terminal: RELEASED, EXPIRED. REASSIGNED and CANCELLED still
lead to RELEASED, because the seat keeps billing until the provider confirms release.

Event log format: one JSON object per line (JSONL), append-only, hash-chained:
  {"seq": n, "ts": "...Z", "knot_id": "...", "event": "...", "from": STATE|null, "to": STATE,
   "actor": "...", "seat_id": "..."|null, "data": {...}, "prev": <sha256 of previous line or "0"*64>,
   "hash": sha256(canonical json of the line without "hash")}
verify() replays the file: sequence numbers contiguous, chain intact, every transition allowed.

CLI:
  python knot_lifecycle.py new    <log.jsonl> <knot_id> <actor> [json-data]
  python knot_lifecycle.py event  <log.jsonl> <knot_id> <TO_STATE> <actor> [seat_id] [json-data]
  python knot_lifecycle.py state  <log.jsonl> [knot_id]
  python knot_lifecycle.py verify <log.jsonl>
  python knot_lifecycle.py --selftest
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ZERO = "0" * 64

STATES = [
    "ISSUED", "QUOTED", "RESERVED", "PROVISIONED", "RUNNING", "DELIVERED",
    "KNOT_VERIFIED", "SETTLED", "RELEASED",
    "PROVISIONING_FAILED", "INTERRUPTED", "REASSIGNED", "DELIVERY_REJECTED",
    "VERIFICATION_FAILED", "EXPIRED", "CANCELLED",
]
TERMINAL = {"RELEASED", "EXPIRED"}   # work may be reassigned or cancelled, but the seat is still released and billed until then

# from -> set(to). None = birth.
TRANSITIONS = {
    None: {"ISSUED"},
    "ISSUED": {"QUOTED", "RESERVED", "PROVISIONED", "EXPIRED", "CANCELLED"},
    "QUOTED": {"RESERVED", "PROVISIONED", "EXPIRED", "CANCELLED"},
    "RESERVED": {"PROVISIONED", "PROVISIONING_FAILED", "EXPIRED", "CANCELLED"},
    # PROVISIONED may also come straight from ISSUED/QUOTED (self-serve seats have no reservation step)
    "PROVISIONED": {"RUNNING", "PROVISIONING_FAILED", "INTERRUPTED", "CANCELLED", "RELEASED"},
    "PROVISIONING_FAILED": {"ISSUED", "RESERVED", "CANCELLED", "RELEASED"},   # ISSUED/RESERVED = retry (a new acquisition attempt)
    "RUNNING": {"DELIVERED", "INTERRUPTED", "CANCELLED"},
    "INTERRUPTED": {"RUNNING", "REASSIGNED", "CANCELLED"},                     # RUNNING = same seat resumed; REASSIGNED = unfinished ids go to a new Knot
    "DELIVERED": {"KNOT_VERIFIED", "VERIFICATION_FAILED", "DELIVERY_REJECTED", "SETTLED"},  # SETTLED without verification only with data.verifier == "none", declared
    "DELIVERY_REJECTED": {"RUNNING", "CANCELLED"},
    "VERIFICATION_FAILED": {"RUNNING", "DELIVERED", "CANCELLED"},
    "KNOT_VERIFIED": {"SETTLED", "RELEASED"},
    "SETTLED": {"RELEASED"},
    "RELEASED": set(),
    "REASSIGNED": {"SETTLED", "RELEASED"},   # the original seat keeps its own billing clock: settle partial work, then release
    "EXPIRED": set(),
    "CANCELLED": {"RELEASED"},   # a cancelled seat is still released (billing stops only at release)
}

# Data keys that certain transitions must carry, so the log is a ledger and not a diary.
REQUIRED_DATA = {
    "PROVISIONED": ["seat_id", "t_ssh_or_ready"],
    "PROVISIONING_FAILED": ["reason"],
    "RUNNING": ["t_work_start"],
    "DELIVERED": ["attempted", "completed", "t_work_end"],
    "KNOT_VERIFIED": ["evaluator", "correct", "accepted"],
    "VERIFICATION_FAILED": ["evaluator", "reason"],
    "SETTLED": ["settlement"],         # {"authority": "invoice"|"credit"|"energy"|"none", "ref": ..., "usd": ...}; authority none must not pretend money moved
    "RELEASED": ["t_released"],
    "INTERRUPTED": ["reason", "unfinished_ids"],
    "REASSIGNED": ["to_knot_id", "unfinished_ids"],
    "CANCELLED": ["reason"],
    "EXPIRED": ["reason"],
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def line_hash(line_without_hash):
    return hashlib.sha256(canonical(line_without_hash).encode("utf-8")).hexdigest()


def read_log(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def check_transition(frm, to, data):
    """Return an error string or None."""
    if to not in STATES:
        return f"unknown state {to}"
    allowed = TRANSITIONS.get(frm, set())
    if to not in allowed:
        return f"{frm} -> {to} is not allowed (allowed: {sorted(allowed)})"
    missing = [k for k in REQUIRED_DATA.get(to, []) if k not in (data or {})]
    if missing:
        return f"{to} requires data keys {missing}"
    if to == "SETTLED":
        st = (data or {}).get("settlement") or {}
        if st.get("authority") not in ("invoice", "credit", "energy", "none"):
            return "SETTLED.settlement.authority must be invoice|credit|energy|none"
        if st.get("authority") == "none" and st.get("usd") not in (None, 0):
            return "SETTLED with authority none must not carry a non-zero usd (it must not pretend money moved)"
        if frm == "DELIVERED" and (data or {}).get("verifier") != "none":
            return "DELIVERED -> SETTLED skips verification; allowed only with data.verifier == 'none'"
    return None


def current_states(events):
    """Replay: knot_id -> (state, last_seq)."""
    st = {}
    for e in events:
        st[e["knot_id"]] = (e["to"], e["seq"])
    return st


def verify(events):
    """Replay the whole log. Returns list of error strings (empty = intact)."""
    errors = []
    prev_hash = ZERO
    state = {}
    for i, e in enumerate(events):
        if e.get("seq") != i:
            errors.append(f"line {i}: seq {e.get('seq')} != {i}")
        if e.get("prev") != prev_hash:
            errors.append(f"line {i}: prev hash mismatch")
        body = {k: v for k, v in e.items() if k != "hash"}
        recomputed = line_hash(body)
        if recomputed != e.get("hash"):
            errors.append(f"line {i}: hash mismatch (line altered)")
        frm_recorded = e.get("from")
        frm_actual = state.get(e["knot_id"])
        if frm_recorded != frm_actual:
            errors.append(f"line {i}: recorded from={frm_recorded} but replay says {frm_actual}")
        err = check_transition(frm_actual, e["to"], e.get("data"))
        if err:
            errors.append(f"line {i}: {err}")
        state[e["knot_id"]] = e["to"]
        prev_hash = recomputed   # chain on what the bytes say, not on what the line claims
    return errors


def append_event(path, knot_id, to, actor, seat_id=None, data=None, ts=None, strict=True):
    """Append one transition. Raises ValueError on an illegal transition (strict) so the log never lies.
    The existing chain is verified first; a broken log is never extended."""
    events = read_log(path)
    chain_errors = verify(events)
    if chain_errors:
        raise ValueError(f"refusing to append to a broken event log: {chain_errors[0]}")
    frm = current_states(events).get(knot_id, (None, None))[0]
    err = check_transition(frm, to, data)
    if err and strict:
        raise ValueError(f"{knot_id}: {err}")
    prev = events[-1]["hash"] if events else ZERO
    line = {
        "seq": len(events),
        "ts": ts or now_iso(),
        "knot_id": knot_id,
        "event": f"{frm or 'BIRTH'}->{to}",
        "from": frm,
        "to": to,
        "actor": actor,
        "seat_id": seat_id,
        "data": data or {},
        "prev": prev,
    }
    line["hash"] = line_hash(line)
    with open(path, "a", encoding="utf-8") as f:
        f.write(canonical(line) + "\n")
    return line


def new_knot(path, knot_id, actor, spec=None, ts=None):
    return append_event(path, knot_id, "ISSUED", actor, data={"spec": spec or {}}, ts=ts)


# ---------------------------------------------------------------- self-test
def selftest():
    sys.path.insert(0, HERE)
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond

    from ledger_common import tmpdir
    with tmpdir("knot-selftest-") as td:
        log = os.path.join(td, "events.jsonl")
        new_knot(log, "k1", "test", {"count": 3})
        append_event(log, "k1", "PROVISIONED", "test", "seatA", {"seat_id": "seatA", "t_ssh_or_ready": "2026-09-24T00:01:00Z"})
        append_event(log, "k1", "RUNNING", "test", "seatA", {"t_work_start": "2026-09-24T00:02:00Z"})
        # deliberate interrupt -> reassignment of unfinished ids to k2
        append_event(log, "k1", "INTERRUPTED", "test", "seatA", {"reason": "deliberate interrupt", "unfinished_ids": ["t2", "t3"]})
        append_event(log, "k1", "REASSIGNED", "test", "seatA", {"to_knot_id": "k2", "unfinished_ids": ["t2", "t3"]})
        new_knot(log, "k2", "test", {"parent": "k1", "ids": ["t2", "t3"]})
        append_event(log, "k2", "PROVISIONED", "test", "seatB", {"seat_id": "seatB", "t_ssh_or_ready": "2026-09-24T00:05:00Z"})
        append_event(log, "k2", "RUNNING", "test", "seatB", {"t_work_start": "2026-09-24T00:06:00Z"})
        append_event(log, "k2", "DELIVERED", "test", "seatB", {"attempted": 2, "completed": 2, "t_work_end": "2026-09-24T00:10:00Z"})
        append_event(log, "k2", "KNOT_VERIFIED", "test", "seatB", {"evaluator": "evalplus@frozen", "correct": 2, "accepted": 2})
        append_event(log, "k2", "SETTLED", "test", "seatB", {"settlement": {"authority": "none", "ref": None, "usd": 0}})
        append_event(log, "k2", "RELEASED", "test", "seatB", {"t_released": "2026-09-24T00:12:00Z"})
        ev = read_log(log)
        check(len(ev) == 12, "12 events appended")
        check(verify(ev) == [], "chain verifies")
        st = current_states(ev)
        check(st["k1"][0] == "REASSIGNED" and st["k2"][0] == "RELEASED", "final states k1=REASSIGNED k2=RELEASED")
        # the interrupted seat still has to be released (its own billing clock) after reassignment
        append_event(log, "k1", "SETTLED", "test", "seatA", {"settlement": {"authority": "none", "usd": 0}, "note": "partial work t1 only"})
        append_event(log, "k1", "RELEASED", "test", "seatA", {"t_released": "2026-09-24T00:06:30Z"})
        check(current_states(read_log(log))["k1"][0] == "RELEASED", "REASSIGNED -> SETTLED -> RELEASED records the original seat's release")
        ev = read_log(log)
        check(verify(ev) == [], "chain still verifies after the release events")
        # illegal transitions refuse
        for to, data in [("RUNNING", {"t_work_start": "x"}), ("ISSUED", {})]:
            try:
                append_event(log, "k2", to, "test", data=data)
                check(False, f"terminal RELEASED -> {to} refused")
            except ValueError:
                check(True, f"terminal RELEASED -> {to} refused")
        try:
            new_knot(log, "k3", "test")
            append_event(log, "k3", "RUNNING", "test", data={"t_work_start": "x"})
            check(False, "ISSUED -> RUNNING refused (must provision first)")
        except ValueError:
            check(True, "ISSUED -> RUNNING refused (must provision first)")
        try:
            append_event(log, "k3", "PROVISIONED", "test", data={"seat_id": "s"})
            check(False, "PROVISIONED without t_ssh_or_ready refused")
        except ValueError:
            check(True, "PROVISIONED without t_ssh_or_ready refused")
        # settlement must not pretend money moved
        new_knot(log, "k4", "test")
        append_event(log, "k4", "PROVISIONED", "test", "s", {"seat_id": "s", "t_ssh_or_ready": "x"})
        append_event(log, "k4", "RUNNING", "test", "s", {"t_work_start": "x"})
        append_event(log, "k4", "DELIVERED", "test", "s", {"attempted": 1, "completed": 1, "t_work_end": "x"})
        try:
            append_event(log, "k4", "SETTLED", "test", "s", {"verifier": "none", "settlement": {"authority": "none", "usd": 5}})
            check(False, "authority none with usd refused")
        except ValueError:
            check(True, "authority none with usd refused")
        # provisioning failure and retry counts as a new attempt path
        new_knot(log, "k5", "test")
        append_event(log, "k5", "RESERVED", "test", "do-h200")
        append_event(log, "k5", "PROVISIONING_FAILED", "test", "do-h200", {"reason": "out of capacity in all six regions"})
        append_event(log, "k5", "ISSUED", "test")
        check(current_states(read_log(log))["k5"][0] == "ISSUED", "PROVISIONING_FAILED -> ISSUED retry allowed")
        # tamper detection
        lines = open(log, encoding="utf-8").read().splitlines()
        tampered = json.loads(lines[3]); tampered["data"]["reason"] = "edited"
        lines[3] = canonical(tampered)
        with open(log, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        errs = verify(read_log(log))
        check(any("hash mismatch" in e for e in errs) and any("prev hash" in e for e in errs), "tampered line detected by chain")
        try:
            new_knot(log, "k6", "test")
            check(False, "append to a broken chain refused")
        except ValueError as e:
            check("broken event log" in str(e), "append to a broken chain refused")
        # every state reachable and every transition target is a known state
        targets = set().union(*TRANSITIONS.values())
        check(targets <= set(STATES) and set(TRANSITIONS) - {None} == set(STATES), "transition table covers every state")
    print(f"knot_lifecycle selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    cmd = argv[0]
    if cmd == "new":
        _, log, knot_id, actor = argv[:4]
        spec = json.loads(argv[4]) if len(argv) > 4 else {}
        print(canonical(new_knot(log, knot_id, actor, spec))); return 0
    if cmd == "event":
        _, log, knot_id, to, actor = argv[:5]
        seat = argv[5] if len(argv) > 5 and not argv[5].startswith("{") else None
        data_arg = argv[6] if len(argv) > 6 else (argv[5] if len(argv) > 5 and argv[5].startswith("{") else "{}")
        try:
            print(canonical(append_event(log, knot_id, to, actor, seat, json.loads(data_arg)))); return 0
        except ValueError as e:
            print(f"REFUSED: {e}"); return 2
    if cmd == "state":
        st = current_states(read_log(argv[1]))
        for k, (s, seq) in sorted(st.items()):
            if len(argv) < 3 or argv[2] == k:
                print(f"{k}\t{s}\t(seq {seq})")
        return 0
    if cmd == "verify":
        errs = verify(read_log(argv[1]))
        print("intact" if not errs else "\n".join(errs)); return 0 if not errs else 1
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
