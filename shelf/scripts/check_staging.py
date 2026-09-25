#!/usr/bin/env python3
"""Every staged import must carry provenance, and no staged card may appear on the shelf
without a recorded promotion in data/promotions.jsonl. Exit code counts violations."""
from __future__ import annotations
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
STAGING = os.path.join(DATA, "staging")


def load_jsonl(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    bad = 0
    shelf_ids = {c.get("id") for c in load_jsonl(os.path.join(DATA, "cards.jsonl"))}
    promoted = {p.get("id"): p for p in load_jsonl(os.path.join(DATA, "promotions.jsonl"))}
    if not os.path.isdir(STAGING):
        print("[PASS   ] no staging directory; nothing imported")
        return 0
    for hub in sorted(os.listdir(STAGING)):
        for stamp in sorted(os.listdir(os.path.join(STAGING, hub))):
            folder = os.path.join(STAGING, hub, stamp)
            files = set(os.listdir(folder))
            if files != {"cards.jsonl", "provenance.json", "source.bytes"}:
                bad += 1; print(f"[FAIL   ] {hub}/{stamp}: expected exactly cards.jsonl, provenance.json, source.bytes; found {sorted(files)}"); continue
            with open(os.path.join(folder, "provenance.json"), encoding="utf-8") as f:
                prov = json.load(f)
            with open(os.path.join(folder, "source.bytes"), "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            if prov.get("sha256") != digest:
                bad += 1; print(f"[FAIL   ] {hub}/{stamp}: provenance sha256 {prov.get('sha256')} != source.bytes {digest}"); continue
            if prov.get("standing") != "imported/candidate":
                bad += 1; print(f"[FAIL   ] {hub}/{stamp}: standing must be imported/candidate at import, not {prov.get('standing')!r}"); continue
            for card in load_jsonl(os.path.join(folder, "cards.jsonl")):
                cid = card.get("id")
                if cid in shelf_ids and cid not in promoted:
                    bad += 1; print(f"[FAIL   ] {hub}/{stamp}: {cid} is on the shelf with no recorded promotion in data/promotions.jsonl")
            print(f"[PASS   ] {hub}/{stamp}: {prov.get('cards')} card(s), sha256 {digest[:12]}, standing {prov['standing']}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
