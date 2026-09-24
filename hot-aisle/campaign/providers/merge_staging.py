#!/usr/bin/env python3
"""Merge provider staging rows into one reviewed table with Run 3 targets.

Reads every staging/*.jsonl, validates against SCHEMA.md, drops duplicates
(last row per offer_id wins, earlier duplicates are reported), and writes:

  providers.jsonl   the merged rows plus computed target fields
  PROVIDERS.md      a human table, one section per campaign role

Targets are modeled from the Run 3 whole-run ledger and are labelled so:
  H100 1x   modeled $/1k accepted = 1.20 * rate / 4.41   (same accepted work as N/T0)
  MI300X 1x modeled $/1k accepted = 0.74 * rate / 2.99   (same accepted work as A/T0)
  any 1x    accepted/hour needed to tie Hot Aisle at $0.74/1k = rate / 0.00074

Nothing here is a measurement. A row becomes evidence only after a run.
"""
from __future__ import annotations
import json, sys, glob, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
RUN3 = {  # whole-run figures from results/RUN3-RESULTS.md
    "ha_rate": 2.99, "ha_per_1k": 0.74, "ha_accepted_per_hour": 4336 / (64.7 / 60),
    "do_rate": 4.41, "do_per_1k": 1.20,
}
REQUIRED = ["provider_id", "provider_name", "offer_id", "gpu", "vendor", "gpus",
            "rate_usd_per_gpu_hour", "rate_basis", "kind", "minimum_billing", "regions",
            "self_serve", "availability_observed", "source_url", "source_quote",
            "retrieved_at", "campaign_role", "notes"]
ROLES = ["h100-comparator", "mi300x-neutral", "amd-next", "nvidia-next", "other"]
GPU_MEM = {"MI300X": 192, "MI325X": 256, "MI350X": 288, "MI355X": 288, "H100": 80,
           "H200": 141, "B200": 180, "B300": 288, "A100": 80, "L40S": 48, "RTX PRO 6000": 96}


def targets(r: dict) -> dict:
    rate, gpus, gpu = r.get("rate_usd_per_gpu_hour"), r.get("gpus"), r.get("gpu")
    t = {"modeled_per_1k_accepted": None, "accepted_per_hour_to_tie_ha": None, "vs_ha_list": None}
    if not isinstance(rate, (int, float)) or rate <= 0 or not isinstance(gpus, int):
        return t
    if gpus == 1:
        t["accepted_per_hour_to_tie_ha"] = round(rate / (RUN3["ha_per_1k"] / 1000))
        if gpu == "H100":
            t["modeled_per_1k_accepted"] = round(RUN3["do_per_1k"] * rate / RUN3["do_rate"], 2)
        elif gpu == "MI300X":
            t["modeled_per_1k_accepted"] = round(RUN3["ha_per_1k"] * rate / RUN3["ha_rate"], 2)
    t["vs_ha_list"] = round(rate / RUN3["ha_rate"], 2)
    return t


def main() -> int:
    rows, problems, seen = [], [], {}
    for path in sorted(glob.glob(os.path.join(HERE, "staging", "*.jsonl"))):
        lane = os.path.basename(path)
        for n, line in enumerate(open(path, encoding="utf-8-sig"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                problems.append(f"{lane}:{n} bad json: {e}"); continue
            missing = [k for k in REQUIRED if k not in r]
            if missing:
                problems.append(f"{lane}:{n} {r.get('offer_id','?')} missing {missing}")
            if not isinstance(r.get("gpus"), int):
                problems.append(f"{lane}:{n} {r.get('offer_id','?')} gpus unknown; no targets computed")
            if r.get("campaign_role") not in ROLES:
                problems.append(f"{lane}:{n} {r.get('offer_id','?')} bad role {r.get('campaign_role')!r}")
            if r.get("memoryGB") in (None, "") and r.get("gpu") in GPU_MEM:
                r["memoryGB"] = GPU_MEM[r["gpu"]]; r["notes"] = (r.get("notes") or "") + " memoryGB filled from spec."
            r["lane"] = lane
            oid = r.get("offer_id")
            if oid in seen and seen[oid].startswith(lane):
                # same lane reused an id for a variant (e.g. SXM vs PCIe): keep both, suffix the later one
                k = 2
                while f"{oid}-v{k}" in seen:
                    k += 1
                problems.append(f"{lane}:{n} reused {oid}; kept as {oid}-v{k}")
                oid = f"{oid}-v{k}"; r["offer_id"] = oid
            elif oid in seen:
                problems.append(f"duplicate {oid}: {seen[oid]} superseded by {lane}:{n}")
            seen[oid] = f"{lane}:{n}"
            r.update(targets(r))
            rows = [x for x in rows if x.get("offer_id") != oid] + [r]
    rows.sort(key=lambda r: (ROLES.index(r.get("campaign_role", "other")) if r.get("campaign_role") in ROLES else 9,
                             r.get("rate_usd_per_gpu_hour") if isinstance(r.get("rate_usd_per_gpu_hour"), (int, float)) else 1e9))
    with open(os.path.join(HERE, "providers.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    today = datetime.date.today().isoformat()
    out = [f"# Rentable single-accelerator offers · staged {today}", "",
           f"{len(rows)} offers from {len({r['provider_id'] for r in rows})} providers. List prices as published, "
           "gathered by lanes and not yet human-approved into compute/data/catalog.json. "
           "Targets are modeled from Run 3 (Hot Aisle MI300X $0.74 and DigitalOcean H100 $1.20 per 1k accepted, whole run); "
           "they assume the same accepted work and are not measurements.", ""]
    for role in ROLES:
        sub = [r for r in rows if r.get("campaign_role") == role]
        if not sub:
            continue
        out += [f"## {role} ({len(sub)})", "",
                "| provider | gpu | n | $/GPU-h | kind | min bill | self-serve | avail | modeled $/1k | acc/h to tie HA | ×HA | source |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sub:
            rate = r.get("rate_usd_per_gpu_hour")
            out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | [src]({}) |".format(
                r.get("provider_name"), r.get("gpu"), r.get("gpus"),
                f"{rate:.2f}" if isinstance(rate, (int, float)) else "n/p",
                r.get("kind"), r.get("minimum_billing"), r.get("self_serve"), r.get("availability_observed"),
                r.get("modeled_per_1k_accepted") if r.get("modeled_per_1k_accepted") is not None else "",
                r.get("accepted_per_hour_to_tie_ha") if r.get("accepted_per_hour_to_tie_ha") is not None else "",
                r.get("vs_ha_list") if r.get("vs_ha_list") is not None else "", r.get("source_url")))
        out.append("")
    if problems:
        out += ["## Validation notes", ""] + [f"- {p}" for p in problems] + [""]
    open(os.path.join(HERE, "PROVIDERS.md"), "w", encoding="utf-8").write("\n".join(out))
    print(f"{len(rows)} rows, {len(problems)} problems -> providers.jsonl, PROVIDERS.md")
    for p in problems:
        print(" ", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
