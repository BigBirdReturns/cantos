"""p02: flip one byte in a copy of data/run3/evidence.json; the page engine must refuse on checksum and no number is produced."""
import json
from _common import *  # noqa

NAME = "p02_evidence_tamper"


def verify(root, record, evidence):
    rc, out, err = run_cmd(["node", CIRCULATE / "probes" / "_p02_verify.cjs", root / "hot-aisle", record, evidence], cwd=root, timeout=120)
    need(out.strip(), "verifier printed nothing (rc=%s): %s" % (rc, err[:300]))
    return json.loads(out.strip().splitlines()[-1])


def body(ctx, work):
    root = ctx_root(ctx)
    ha = root / "hot-aisle"
    record, evidence = ha / "data/run3/record.json", ha / "data/run3/evidence.json"
    control = verify(root, record, evidence)
    need(control["publication_verified"] and control["cost_per_1000"] is not None,
         "untampered pair does not verify, so the probe cannot tell tamper from breakage: %r" % control)
    raw = evidence.read_bytes()
    tampered = flip_byte_in_json_value(raw, b'"rate": ')
    need(sum(a != b for a, b in zip(raw, tampered)) == 1 and len(raw) == len(tampered), "not exactly one byte flipped")
    copy = work / "evidence.json"
    copy.write_bytes(tampered)
    r = verify(root, record, copy)
    need(not r["publication_verified"], "engine accepted a tampered evidence packet")
    need(r["error"] and "checksum" in r["error"].lower(), "expected a checksum error, got %r" % r["error"])
    need(r["cost_per_1000"] is None, "a number was produced from tampered evidence")
    return {
        "observed": {"untampered": {"verified": True, "cost_per_1000": control["cost_per_1000"]},
                     "tampered": {"verified": False, "error": r["error"], "failed_at": r["engine_step"], "cost_per_1000": r["cost_per_1000"]},
                     "record_still_verifies_alone": r["record_verified"], "tampered_sha256": sha256_bytes(tampered)},
        "expected": "page engine reports a checksum mismatch on the tampered copy and yields no cost figure; the untampered pair verifies",
        "notes": "Verifier is runner/lib publication.verify (the check runner/test/run3-door.test.cjs makes). The card renders a number only after it passes, so no number is emitted on failure.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
