#!/usr/bin/env python3
"""Regenerate the Tier-Bench fixture excerpts from the two pinned entry paths. Stdlib only. Run only when
the pinned inputs change; the committed fixtures are what the offline tests use.

    python fixtures/REGENERATE.py [--tierbench-root W] [--router-root R]

Copies SMALL excerpts (verbatim rows / subtrees) and records provenance (path, git commit, sha256 of the
whole source file) in fixtures/PROVENANCE.json. Reads ONLY the entry-locked paths; writes ONLY under fixtures/.
The router receipts under fixtures/router/receipt-*.json are SYNTHETIC (route.py's our-auto/run@1 shape,
no real run was read) and are not regenerated here.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
W_DEFAULT = r"D:\Projects\Measurement\Tier-Bench\worktrees\task-computer-no-console-current-main-20260730"
R_DEFAULT = r"D:\Projects\Measurement\Tier-Bench\integrations\our-auto-router"
PIN = "9693cb99694338e72c15d0ffbb87b5a1c5bbf16a"

LEDGER_TASKS = {  # task_id -> max rows to copy (verbatim, in file order)
    "t0_format_whitespace_002": 3, "t0_rename_symbol_003": 6, "t1_impl_from_docstring_001": 3,
    "t3_parse_duration_004": 6, "task02_wildcard": 8, "almanac_rule_boundary_001": 6,
    "replay02_charclass_filter": 3, "replay04_count_matches": 3, "b2_grade_attrs_1567_setattr_mro": 2,
    "task08_select_exchange": 8, "t4_plan_decomposition_001": 4,
}
MODELS_KEEP = ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5", "gpt-5-mini", "gpt-5.5",
               "qwen2.5-coder", "llama3.1", "deepseek-chat")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def prov(root, rel, note=None):
    p = os.path.join(root, rel)
    head = git(root, "rev-parse", "HEAD")
    last = git(root, "log", "-1", "--format=%H", "--", rel) if head else None
    in_pin = None
    if head:
        in_pin = git(root, "cat-file", "-e", f"{PIN}:{rel.replace(os.sep, '/')}") is not None
    return {"path": p, "sha256": sha256(p), "git_head": head, "git_last_commit": last,
            "git_head_reason": None if head else "not a git repository; sha256 and mtime are the only pins",
            "in_pin_9693cb9": in_pin, "mtime": os.path.getmtime(p), "note": note}


def main(argv):
    W, R = W_DEFAULT, R_DEFAULT
    i = 0
    while i < len(argv):
        if argv[i] == "--tierbench-root": W = argv[i + 1]; i += 2
        elif argv[i] == "--router-root": R = argv[i + 1]; i += 2
        else: print(__doc__); return 1
    P = {"schema": "second-run/tierbench-fixture-provenance@1", "pin": PIN, "entry_lock": {"W": W, "R": R}, "sources": {}}
    tb = os.path.join(HERE, "tierbench")
    # ledger.jsonl excerpt: verbatim rows, capped per task
    rel = os.path.join("experiments", "breadth", "run", "ledger.jsonl")
    left = dict(LEDGER_TASKS)
    out, idx = [], []
    with open(os.path.join(W, rel), encoding="utf-8") as f:
        for n, line in enumerate(f):
            if not line.strip():
                continue
            t = json.loads(line).get("task_id")
            if left.get(t, 0) > 0:
                left[t] -= 1
                out.append(line.rstrip("\n")); idx.append(n)
    with open(os.path.join(tb, "ledger.excerpt.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    P["sources"]["ledger.jsonl"] = prov(W, rel, note=f"{len(out)} verbatim rows; source line indexes {idx}")
    # map.json excerpt: only the tasks we copied
    rel = os.path.join("experiments", "breadth", "run", "map.json")
    m = json.load(open(os.path.join(W, rel), encoding="utf-8"))
    m2 = dict(m); m2["tasks"] = {k: v for k, v in m["tasks"].items() if k in LEDGER_TASKS}
    m2["_excerpt"] = f"tasks limited to {sorted(m2['tasks'])}; totals are the source's, not recomputed"
    json.dump(m2, open(os.path.join(tb, "map.excerpt.json"), "w", encoding="utf-8"), indent=2)
    P["sources"]["map.json"] = prov(W, rel, note="tasks subset")
    # waterline.json: whole file (small)
    rel = os.path.join("experiments", "breadth", "run", "waterline.json")
    json.dump(json.load(open(os.path.join(W, rel), encoding="utf-8")), open(os.path.join(tb, "waterline.json"), "w", encoding="utf-8"), indent=2)
    P["sources"]["waterline.json"] = prov(W, rel, note="whole file")
    # models.json excerpt
    rel = "models.json"
    md = json.load(open(os.path.join(W, rel), encoding="utf-8"))
    md2 = {"_comment": ["EXCERPT of Tier-Bench models.json for offline tests; prices as of the source's 'Last reviewed: 2026-07-26'"],
           "models": {k: v for k, v in md["models"].items() if k in MODELS_KEEP}, "roles": md.get("roles")}
    json.dump(md2, open(os.path.join(tb, "models.excerpt.json"), "w", encoding="utf-8"), indent=2)
    P["sources"]["models.json"] = prov(W, rel, note=f"models subset {list(MODELS_KEEP)}")
    # ledger.py: schema only (the Call dataclass field list), recorded as provenance, not copied
    P["sources"]["ledger.py"] = prov(W, os.path.join("experiments", "breadth", "ledger.py"), note="Call dataclass shape only; not copied")
    for d in ("residue-broker.md", "burden-discipline.md", "residue-resource-lanes.md"):
        P["sources"][d] = prov(W, os.path.join("docs", d), note="read for BRIDGE.md; not copied")
    for fpath in ("seats.py", "protocol.py", "store.py"):
        P["sources"]["tier_runner/fabric/" + fpath] = prov(W, os.path.join("tier_runner", "fabric", fpath), note="SeatIdentity / seat_leases shape; post-pin commit; not copied")
    # router side
    rt = os.path.join(HERE, "router")
    for name in ("policy.json", "race6-results.operator-diagnostic.json"):
        rel = os.path.join("references", name)
        with open(os.path.join(R, rel), "rb") as f:
            data = f.read()
        with open(os.path.join(rt, name), "wb") as f:
            f.write(data)
        P["sources"][name] = prov(R, rel, note="whole file, byte copy")
    P["sources"]["route.py"] = prov(R, os.path.join("scripts", "route.py"), note="receipt schema our-auto/run@1 read; not copied")
    json.dump(P, open(os.path.join(HERE, "PROVENANCE.json"), "w", encoding="utf-8"), indent=2)
    print(f"fixtures regenerated: {len(out)} ledger rows, {len(m2['tasks'])} map tasks, {len(md2['models'])} models; provenance for {len(P['sources'])} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
