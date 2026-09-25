"""Adapters: turn the kit's real inputs into the shapes diagnose.py's rules read.

Two producers exist upstream of diagnose.py and neither writes the rule-facing shape directly:

* ``../counter/records/<shop>.json`` is a raw observation record
  (schema_id ``second-run/counter-record@1``). Its score comes from
  ``../counter/counter_record.py`` ``compute_score``; we call that here.
* ``<outdir>/fingerprint.json`` from ``../probe/fingerprint.sh``
  (schema ``second-run/shop-fingerprint@1``) records every value as the string the
  tool printed, with ``"unavailable..."`` / ``"unobserved"`` for gaps.

Anything already in the rule-facing shape (the fixtures under ``fixtures/``) passes through
untouched. Nothing here invents a value: an unparseable or unobserved field becomes ``None``
so the rule reports "not evaluated" instead of guessing.
"""
from __future__ import annotations

import os
import re
import statistics
import sys
from typing import Any, Optional

COUNTER_SCHEMA_ID = "second-run/counter-record@1"
PROBE_SCHEMAS = {
    "second-run/shop-fingerprint@1",
    "second-run/shop-fingerprint@2",
    "second-run/shop-fingerprint@3",
}

# PCIe ceiling per accelerator family, so a probe's *current* link can be judged against
# what the part supports. Anything not listed stays None (rule HW-01 then reports missing).
PCIE_MAX_BY_MODEL = (
    (re.compile(r"MI3[0-5]5X|MI300X|MI325X", re.I), (5, 16)),
    (re.compile(r"H100|H200|H20\b|GH200|B200|B100|L40S", re.I), (5, 16)),
    (re.compile(r"A100|A10\b|A40|MI250|MI210|RTX 30", re.I), (4, 16)),
)

VM_HINTS = ("kvm", "qemu", "vmware", "xen", "microsoft", "hyperv", "amazon", "oracle", "parallels", "bochs")


def _num(value: Any) -> Optional[float]:
    """'3' -> 3, '45.30' -> 45.3, '265.10 W' -> 265.1, 'unobserved' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    m = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not m:
        return None
    n = float(m.group(0))
    return int(n) if n.is_integer() else n


def _is_gap(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and (value.startswith("unavailable") or value == "unobserved" or value == "")
    )


# --------------------------------------------------------------------------- counter

def _counter_module():
    here = os.path.dirname(os.path.abspath(__file__))
    counter_dir = os.path.join(os.path.dirname(here), "counter")
    if counter_dir not in sys.path:
        sys.path.insert(0, counter_dir)
    import counter_record  # sibling lane, stdlib only
    return counter_record


def _billing_label(record: dict) -> Optional[str]:
    quantum = (record.get("billing_granularity") or {}).get("billing_quantum")
    if _is_gap(quantum):
        return None
    q = str(quantum).lower()
    if "second" in q:
        return "per-second"
    if "minute" in q:
        return "per-minute"
    if "hour" in q:
        return "per-hour"
    if "day" in q or "month" in q:
        return "per-hour"  # coarser than hourly is at least as bad for PRICE-01's purpose
    return "unknown"


def adapt_counter(record: dict) -> dict:
    """Raw counter record -> rule-facing shape. Passes other shapes through unchanged."""
    if not isinstance(record, dict) or record.get("schema_id") != COUNTER_SCHEMA_ID:
        return record
    scored = _counter_module().compute_score(record)
    dims = {
        name: {"score": d["score"], "weight": d["weight"], "notes": "; ".join(d.get("rules") or [])}
        for name, d in scored["dimensions"].items()
    }
    proof_src = record.get("public_proof")
    if isinstance(proof_src, dict):
        dims["proof"] = {
            "score": None,
            "weight": 0,
            "notes": proof_src.get("notes", ""),
            "has_manifest_hash": proof_src.get("has_manifest_hash"),
            "has_disclosure": proof_src.get("has_disclosure"),
            "has_pinned_commit": proof_src.get("has_pinned_commit"),
            "publishes_whole_window_cost": proof_src.get("publishes_whole_window_cost"),
        }
    attempts = ((record.get("provisioning") or {}).get("attempts")) or []
    ssh_times = [_num(a.get("time_to_ssh_s")) for a in attempts if isinstance(a, dict)]
    ssh_times = [t for t in ssh_times if t is not None]
    prov = record.get("provenance") or {}
    ledger = ((record.get("availability_honesty") or {}).get("ledger_attempts")) or []
    ledger = [row for row in ledger if isinstance(row, dict)]
    # Do not pool a listing for one SKU/region/time with a create for another.
    # Until the ledger carries explicit listing_snapshot_id -> snapshot_id linkage,
    # availability agreement is unknown rather than inferred from unrelated rows.
    snapshots = {row.get("snapshot_id"): row for row in ledger
                 if row.get("method") == "tui-provision-list" and row.get("snapshot_id")}
    matched = []
    for row in ledger:
        if row.get("method") not in {"api-create", "console-create", "tui-provision"}:
            continue
        snap = snapshots.get(row.get("listing_snapshot_id"))
        if not snap or (snap.get("sku"), snap.get("region")) != (row.get("sku"), row.get("region")):
            continue
        if snap.get("outcome") not in {"available", "unavailable"} or not isinstance(row.get("provisioned"), bool):
            continue
        matched.append((snap.get("outcome") == "available", row.get("provisioned")))
    if len(matched) == 1:
        listed_available, provisioned = matched[0]
    else:
        listed_available = provisioned = None
    return {
        "schema": "second-run/counter-scored@1",
        "shop": record.get("provider_name") or record.get("provider_id"),
        "generated_at": prov.get("evaluated_at"),
        "score": scored["total"],
        "raw_total": scored["raw_total"],
        "capped": scored["capped"],
        "disqualifying_observations": scored["disqualifying_observations"],
        "billing_granularity": _billing_label(record) or "unknown",
        "dimensions": dims,
        "provisioning": {
            "seconds_to_ssh": statistics.median(ssh_times) if ssh_times else None,
            "attempts": len(attempts),
            "measured_3x": (record.get("provisioning") or {}).get("measured_3x"),
            "listed_available": listed_available,
            "provisioned": provisioned,
            "matched_availability_attempts": len(matched),
        },
        "disclosure": prov.get("disclosure"),
        "_adapted_from": record.get("schema_id"),
    }


# --------------------------------------------------------------------------- fingerprint

def _pcie_max(model: str):
    for pattern, ceiling in PCIE_MAX_BY_MODEL:
        if pattern.search(model or ""):
            return ceiling
    return (None, None)


def _virt_label(raw: Any) -> Optional[str]:
    if _is_gap(raw):
        return None
    v = str(raw).strip().lower()
    if v == "none":
        return "bare-metal"
    if any(h in v for h in VM_HINTS):
        return "vm"
    if v in ("lxc", "docker", "podman", "systemd-nspawn", "openvz"):
        return "container"
    return v


def _parse_nvidia_sample(line: str):
    # "1410, 1215, 62, 265.10 W, Not Active"  (clocks.sm, clocks.mem, temp, power, hw_slowdown)
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 5:
        return None
    throttle = parts[4].lower()
    return {
        "clock_mhz": _num(parts[0]),
        "temp_c": _num(parts[2]),
        "power_w": _num(parts[3]),
        "throttled": (throttle == "active") if throttle in ("active", "not active") else None,
    }


def _parse_amd_sample(blob: str):
    # rocm-smi --showclocks --showtemp --showpower text; best effort, first GPU only.
    clock = re.search(r"sclk.*?\((\d+)\s*Mhz\)", blob, re.I) or re.search(r"\((\d+)\s*Mhz\)", blob, re.I)
    temp = (
        re.search(r"Temperature\s*\(Sensor\s*(?:junction|edge)\)[^\d]*(\d+(?:\.\d+)?)", blob, re.I)
        or re.search(r"Temperature[^\d]*(\d+(?:\.\d+)?)", blob, re.I)
    )
    power = re.search(r"Power[^\d]*(\d+(?:\.\d+)?)\s*W", blob, re.I)
    if not (clock or temp or power):
        return None
    return {
        "clock_mhz": _num(clock.group(1)) if clock else None,
        "temp_c": _num(temp.group(1)) if temp else None,
        "power_w": _num(power.group(1)) if power else None,
        "throttled": None,  # rocm-smi text has no throttle flag; PWR-01 falls back to the clock slope
    }


def _sustained(load_sample: Any, vendor: str):
    if not isinstance(load_sample, dict):
        return None
    if str(load_sample.get("status", "")).lower() != "pass":
        return None
    samples = load_sample.get("samples") or []
    parsed = []
    for s in samples:
        text = s.get("sample") if isinstance(s, dict) else s
        if not isinstance(text, str) or _is_gap(text):
            continue
        p = _parse_nvidia_sample(text) if vendor == "nvidia" else _parse_amd_sample(text)
        if p:
            parsed.append(p)
    if len(parsed) < 2:
        return None
    first, last = parsed[0], parsed[-1]
    throttle_flags = [p["throttled"] for p in parsed if p["throttled"] is not None]
    return {
        "clock_mhz_start": first["clock_mhz"],
        "clock_mhz_end": last["clock_mhz"],
        "temp_c_start": first["temp_c"],
        "temp_c_end": last["temp_c"],
        "power_w_start": first["power_w"],
        "power_w_end": last["power_w"],
        "throttled": any(throttle_flags) if throttle_flags else None,
        "samples": len(parsed),
        "actual_duration_s": _num(load_sample.get("duration_s")),
    }


def adapt_fingerprint(fp: dict, counter_scored: Optional[dict] = None) -> dict:
    """Probe fingerprint -> rule-facing shape. Passes other shapes through unchanged."""
    if not isinstance(fp, dict) or fp.get("schema") not in PROBE_SCHEMAS:
        return fp
    if isinstance(fp.get("gpus"), list) and not isinstance(fp.get("gpu"), dict):
        return fp  # already rule-facing (the fixtures under fixtures/ carry the same schema string)
    gpu = fp.get("gpu") or {}
    vendor = str(gpu.get("vendor") or fp.get("requested_gpu_vendor") or "").lower()
    stack_version = gpu.get("rocm_or_cuda_version") if vendor == "amd" else gpu.get("driver_version")
    if _is_gap(stack_version):
        stack_version = None
    sustained = _sustained(fp.get("load_sample"), vendor)
    gpus = []
    for dev in gpu.get("devices") or []:
        model = dev.get("model") or ""
        gen_max, width_max = _pcie_max(model)
        gpus.append({
            "index": _num(dev.get("index")),
            "model": model,
            "vendor": vendor,
            "vbios": None if _is_gap(dev.get("vbios")) else dev.get("vbios"),
            "firmware": None if _is_gap(dev.get("firmware")) else dev.get("firmware"),
            "firmware_age_days": None,  # not observable from the node; needs the vendor release date
            "driver_or_rocm_version": stack_version,
            "pcie_gen": _num(dev.get("pcie_link_gen_current")),
            "pcie_gen_max": gen_max,
            "pcie_width": _num(dev.get("pcie_link_width_current")),
            "pcie_width_max": width_max,
            "ras_errors_correctable": _num(dev.get("ecc_corrected_total")),
            "ras_errors_uncorrectable": _num(dev.get("ecc_uncorrected_total")),
            "idle_temp_c": _num(dev.get("temp_c_idle")),
            "idle_clock_mhz": _num(dev.get("clock_sm_mhz_idle")),
            "idle_power_w": _num(dev.get("power_w_idle")),
            "idle_verified": fp.get("idle_verified") is True,
            "sample_context": fp.get("sample_context") or fp.get("idle_power_state"),
            "sustained_load": sustained,
        })
    cmdline = fp.get("kernel_cmdline")
    hugepages_total = _num(fp.get("hugepages_total"))
    out = dict(fp)
    provisioning = dict(fp.get("provisioning") or {})
    seconds_to_ssh = provisioning.get("seconds_to_ssh")
    provisioning["seconds_to_ssh"] = None if _is_gap(seconds_to_ssh) else _num(seconds_to_ssh)
    out["provisioning"] = provisioning
    out.update({
        "gpu_vendor": vendor,
        "virtualization": _virt_label(fp.get("virtualization")),
        "virtualization_raw": fp.get("virtualization"),
        "cpu": {**(fp.get("cpu") or {}), "numa_nodes": _num((fp.get("cpu") or {}).get("numa_nodes"))},
        "gpus": gpus,
        "hugepages_enabled": (hugepages_total > 0) if hugepages_total is not None else None,
        "acs_enabled": (
            ("pcie_acs_override" in cmdline)
            if isinstance(cmdline, str) and not _is_gap(cmdline) else None
        ),
        "observed_backend": fp.get("observed_backend"),
        "_adapted_from": fp.get("schema"),
    })
    if counter_scored and isinstance(counter_scored.get("provisioning"), dict):
        for key in ("seconds_to_ssh", "listed_available", "provisioned"):
            if out["provisioning"].get(key) is None or _is_gap(out["provisioning"].get(key)):
                out["provisioning"][key] = counter_scored["provisioning"].get(key)
    return out
