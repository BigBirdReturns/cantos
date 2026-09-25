#!/usr/bin/env python3
"""Diff two shop-fingerprint@1 records and flag what matters for serving throughput.

    diff.py reference.json candidate.json [--json]

Prints every field that differs between the reference (usually the Hot Aisle fixture)
and the candidate (the shop under evaluation), then a short list of flags for the
differences that are known to move serving throughput or correctness: PCIe below
Gen5 x16, VM instead of bare metal, a ROCm/driver major-version mismatch, thermal
throttling observed during the 60 s load sample, nonzero ECC errors, download
throughput under 200 MB/s, a sub-1500 MTU, and under 200 GB free on /.

Stdlib only (Python 3.9+). Exits 0 on a normal run -- a shop failing every flag is
the expected output of this tool, not a tool failure. Only a usage error (missing
files, bad JSON) sets a nonzero code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Generic recursive diff over the flattened field tree
# ---------------------------------------------------------------------------

MISSING = "<missing>"


def flatten(obj: Any, prefix: str = "") -> dict:
    """Flatten nested dict/list JSON into {dotted.path[index]: leaf_value}."""
    out: dict = {}
    if isinstance(obj, dict):
        if not obj:
            out[prefix or "."] = {}
            return out
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten(v, key))
    elif isinstance(obj, list):
        if not obj:
            out[prefix or "."] = []
            return out
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            out.update(flatten(v, key))
    else:
        out[prefix] = obj
    return out


def diff_fields(reference: dict, candidate: dict) -> list:
    """Return sorted (key, ref_value, cand_value) tuples for every differing leaf."""
    rf = flatten(reference)
    cf = flatten(candidate)
    keys = sorted(set(rf) | set(cf))
    diffs = []
    for k in keys:
        rv = rf.get(k, MISSING)
        cv = cf.get(k, MISSING)
        if rv != cv:
            diffs.append((k, rv, cv))
    return diffs


# ---------------------------------------------------------------------------
# Value parsing helpers -- tolerant of "unavailable: ...", "unobserved", "[N/A]"
# ---------------------------------------------------------------------------

_UNKNOWN_STRINGS = ("unavailable", "unobserved", "n/a", "[n/a]", "")


def _is_unknown(s: Any) -> bool:
    if not isinstance(s, str):
        return s is None
    st = s.strip().lower()
    return st in _UNKNOWN_STRINGS or st.startswith("unavailable")


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def to_number(s: Any):
    """Best-effort numeric read of a fingerprint field; None if unknown/unparseable."""
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if _is_unknown(s):
        return None
    m = _NUM_RE.search(s)
    return float(m.group(0)) if m else None


def major_version(s: Any):
    """Leading integer version component ('7' from '7.2.4'), or None if unknown."""
    if _is_unknown(s):
        return None
    if not isinstance(s, str):
        return None
    m = re.match(r"\s*(\d+)", s)
    return m.group(1) if m else None


_SIZE_RE = re.compile(r"^([\d.]+)\s*([KMGTP]?)i?B?$", re.IGNORECASE)
_SIZE_FACTOR_TO_GB = {"": 1e-9, "K": 1e-6, "M": 1e-3, "G": 1.0, "T": 1024.0, "P": 1024.0 * 1024.0}


def parse_size_to_gb(tok: str):
    m = _SIZE_RE.match(tok.strip())
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    factor = _SIZE_FACTOR_TO_GB.get(unit)
    return val * factor if factor is not None else None


# ---------------------------------------------------------------------------
# Flags: PCIe below Gen5 x16, VM vs bare metal, ROCm/driver major mismatch,
# thermal throttle under load, nonzero ECC, download <200 MB/s, MTU, free disk
# ---------------------------------------------------------------------------

# Matches a standalone "Active" that is not part of "Not Active" (nvidia-smi's
# clocks_throttle_reasons.hw_slowdown column reads exactly one of those two).
_ACTIVE_RE = re.compile(r"(?<!Not )\bActive\b")


def check_pcie(candidate: dict) -> list:
    hits = []
    gpu = candidate.get("gpu")
    if not isinstance(gpu, dict):
        return hits
    for dev in gpu.get("devices") or []:
        if not isinstance(dev, dict):
            continue
        gen = to_number(dev.get("pcie_link_gen_current"))
        width = to_number(dev.get("pcie_link_width_current"))
        if gen is None and width is None:
            continue
        if (gen is not None and gen < 5) or (width is not None and width < 16):
            hits.append((dev.get("index", "?"), dev.get("model", "?"),
                         dev.get("pcie_link_gen_current"), dev.get("pcie_link_width_current")))
    return hits


def check_virtualization(candidate: dict):
    v = candidate.get("virtualization")
    if _is_unknown(v):
        return None
    if isinstance(v, str) and v.strip().lower() == "none":
        return None
    return v


def check_driver_mismatch(reference: dict, candidate: dict):
    ref_gpu = reference.get("gpu") if isinstance(reference.get("gpu"), dict) else {}
    cand_gpu = candidate.get("gpu") if isinstance(candidate.get("gpu"), dict) else {}
    for field in ("driver_version", "rocm_or_cuda_version"):
        rm = major_version(ref_gpu.get(field))
        cm = major_version(cand_gpu.get(field))
        if rm is not None and cm is not None and rm != cm:
            return (field, ref_gpu.get(field), cand_gpu.get(field))
    return None


def check_throttle(candidate: dict) -> list:
    ls = candidate.get("load_sample")
    if not isinstance(ls, dict):
        return []
    hits = []
    for sample in ls.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        text = sample.get("sample", "")
        if not isinstance(text, str):
            continue
        low = text.lower()
        throttled = bool(_ACTIVE_RE.search(text)) or (
            "overtemp" in low or ("throttl" in low and "not" not in low)
        )
        if throttled:
            hits.append(sample.get("t_offset_s", "?"))
    return hits


def check_ecc(candidate: dict) -> list:
    hits = []
    gpu = candidate.get("gpu")
    if not isinstance(gpu, dict):
        return hits
    for dev in gpu.get("devices") or []:
        if not isinstance(dev, dict):
            continue
        for field in ("ecc_corrected_total", "ecc_uncorrected_total"):
            n = to_number(dev.get(field))
            if n is not None and n > 0:
                hits.append((dev.get("index", "?"), field, dev.get(field)))
    return hits


def check_download(candidate: dict):
    net = candidate.get("network")
    if not isinstance(net, dict):
        return None
    v = to_number(net.get("download_throughput_mb_s"))
    return v if (v is not None and v < 200) else None


def check_mtu(candidate: dict) -> list:
    hits = []
    net = candidate.get("network")
    if not isinstance(net, dict):
        return hits
    for iface in net.get("interfaces") or []:
        if not isinstance(iface, dict):
            continue
        name = iface.get("name", "?")
        if name == "lo":
            continue
        mtu = to_number(iface.get("mtu"))
        if mtu is not None and mtu < 1500:
            hits.append((name, iface.get("mtu")))
    return hits


def check_free_disk(candidate: dict):
    fs = candidate.get("filesystems")
    if not isinstance(fs, str) or _is_unknown(fs):
        return None
    root_cols = None
    for line in fs.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == "/":
            root_cols = parts
            break
    if not root_cols:
        return None
    avail_tok = root_cols[-3]  # ... Size Used Avail Use% Mounted-on -- avail is 3rd from end
    gb = parse_size_to_gb(avail_tok)
    if gb is not None and gb < 200:
        return (avail_tok, gb)
    return None


def compute_flags(reference: dict, candidate: dict) -> list:
    """Return a list of {tag, message, why} for every flagged condition found."""
    flags = []

    for idx, model, gen, width in check_pcie(candidate):
        flags.append({
            "tag": "pcie_below_gen5_x16",
            "message": f"GPU {idx} ({model}): PCIe link is gen {gen} x{width}, below Gen5 x16",
            "why": "A narrower/older link caps host<->GPU transfer and multi-GPU all-reduce, "
                   "showing up as lower serving throughput than the GPU's own compute suggests.",
        })

    virt = check_virtualization(candidate)
    if virt is not None:
        flags.append({
            "tag": "vm_not_bare_metal",
            "message": f"Running under virtualization ({virt}), not bare metal",
            "why": "A hypervisor adds scheduling/I-O overhead versus bare metal or an SR-IOV VF, "
                   "and can hide or reshape the PCIe/NUMA topology the workload actually sees.",
        })

    mismatch = check_driver_mismatch(reference, candidate)
    if mismatch is not None:
        field, rv, cv = mismatch
        flags.append({
            "tag": "driver_rocm_major_mismatch",
            "message": f"{field} major version differs: reference={rv} candidate={cv}",
            "why": "A driver or ROCm/CUDA major-version step changes kernel selection and "
                   "allocator behavior enough to move throughput and tail latency on its own.",
        })

    for offset in check_throttle(candidate):
        flags.append({
            "tag": "thermal_throttle_under_load",
            "message": f"Thermal/power throttling observed during the load sample (t+{offset}s)",
            "why": "A shop that throttles under sustained load under-delivers its rated "
                   "throughput on anything longer than a warm-up-sized benchmark.",
        })

    for idx, field, val in check_ecc(candidate):
        flags.append({
            "tag": "ecc_errors_nonzero",
            "message": f"GPU {idx}: {field}={val}",
            "why": "Uncorrected ECC risks silent data corruption in a serving workload; nonzero "
                   "corrected counts on a fresh rental suggest marginal memory found the hard way.",
        })

    dl = check_download(candidate)
    if dl is not None:
        flags.append({
            "tag": "download_throughput_low",
            "message": f"Download throughput {dl:.2f} MB/s, under the 200 MB/s floor",
            "why": "Slow egress/ingress stretches model weight download and checkpoint I/O, "
                   "inflating the pull-and-load minutes that are pure overhead on every arm.",
        })

    for name, mtu in check_mtu(candidate):
        flags.append({
            "tag": "mtu_low",
            "message": f"Interface {name} MTU {mtu}, under 1500",
            "why": "A sub-standard MTU without matching jumbo frames end-to-end raises per-packet "
                   "overhead and can cap network throughput below what the link itself suggests.",
        })

    disk = check_free_disk(candidate)
    if disk is not None:
        tok, gb = disk
        flags.append({
            "tag": "free_disk_low",
            "message": f"Free disk on / is {tok} (~{gb:.0f} GB), under the 200 GB floor",
            "why": "Model weights, the HF cache and container images for one serve arm can exceed "
                   "200 GB; running out mid-pull fails the arm after paying for the pull time.",
        })

    return flags


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_table(diffs: list, flags: list) -> None:
    if not diffs:
        print("No differing fields.")
    else:
        key_w = max(len(k) for k, _, _ in diffs)
        key_w = max(key_w, len("field"))
        print(f"{'field'.ljust(key_w)}  {'reference'.ljust(30)}  candidate")
        print(f"{'-' * key_w}  {'-' * 30}  {'-' * 30}")
        for k, rv, cv in diffs:
            print(f"{str(k).ljust(key_w)}  {str(rv)[:30].ljust(30)}  {str(cv)[:60]}")
    print()
    if not flags:
        print("No flags.")
    else:
        print(f"{len(flags)} flag(s):")
        for f in flags:
            print(f"  ! [{f['tag']}] {f['message']}")
            print(f"      why it matters: {f['why']}")


def print_json(diffs: list, flags: list) -> None:
    payload = {
        "diffs": [{"field": k, "reference": rv, "candidate": cv} for k, rv, cv in diffs],
        "flags": flags,
    }
    print(json.dumps(payload, indent=2, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", help="reference.json (e.g. the Hot Aisle fixture)")
    parser.add_argument("candidate", help="candidate.json (the shop under evaluation)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                         help="emit {diffs, flags} as JSON instead of a text table")
    args = parser.parse_args(argv)

    try:
        with open(args.reference, "r", encoding="utf-8") as fh:
            reference = json.load(fh)
        with open(args.candidate, "r", encoding="utf-8") as fh:
            candidate = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"diff.py: could not read fingerprints: {exc}", file=sys.stderr)
        return 2

    diffs = diff_fields(reference, candidate)
    flags = compute_flags(reference, candidate)

    if args.as_json:
        print_json(diffs, flags)
    else:
        print_table(diffs, flags)

    return 0


if __name__ == "__main__":
    sys.exit(main())
