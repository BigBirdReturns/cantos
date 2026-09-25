"""Offline source operations over the existing provider and backfill owners.

prepare(task, base) returns semantic parameters, dependency paths (None denotes
an absent optional receipt), and a no-argument executor. It never edits sources,
renews review dates, provisions a seat, or upgrades imported evidence.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import types

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
CAMPAIGN = ROOT / "hot-aisle/campaign"
PROVIDER_OWNER = CAMPAIGN / "providers/merge_staging.py"
BENCHMARK_OWNER = CAMPAIGN / "backfill/importer.py"


def _owner(path):
    # Compile the pinned local owner without creating bytecode in its checkout.
    module = types.ModuleType("operation_" + path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _source(task, base):
    source = task.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a nonempty local file path")
    path = Path(source)
    path = (path if path.is_absolute() else Path(base) / path).resolve()
    if not path.is_file():
        raise ValueError("source file is missing: " + str(path))
    return path


def _validate_offer(row, owner, line):
    prefix = f"provider line {line}: "
    if not isinstance(row, dict):
        raise ValueError(prefix + "offer must be an object")
    missing = set(owner.REQUIRED) - set(row)
    if missing:
        raise ValueError(prefix + "missing fields " + ", ".join(sorted(missing)))
    for key in ("provider_id", "provider_name", "offer_id", "gpu", "vendor", "kind", "source_url", "retrieved_at"):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError(prefix + key + " must be a nonempty string")
    for key in ("source_quote", "minimum_billing", "notes"):
        if not isinstance(row[key], str):
            raise ValueError(prefix + key + " must be a string")
    if not isinstance(row["regions"], list) or any(not isinstance(v, str) for v in row["regions"]):
        raise ValueError(prefix + "regions must be a list of strings")
    if row["campaign_role"] not in owner.ROLES:
        raise ValueError(prefix + "unknown campaign_role")
    if row["self_serve"] not in ("yes", "quota", "sales", "unknown"):
        raise ValueError(prefix + "unknown self_serve value")
    if row["availability_observed"] not in ("available", "out_of_stock", "waitlist", "unknown"):
        raise ValueError(prefix + "unknown availability_observed value")
    try:
        observed = dt.datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(prefix + "invalid retrieval timestamp") from exc
    if observed.tzinfo is None:
        raise ValueError(prefix + "retrieval timestamp needs a timezone")
    gpus, rate, basis = row["gpus"], row["rate_usd_per_gpu_hour"], row["rate_basis"]
    if gpus is not None and (type(gpus) is not int or gpus <= 0):
        raise ValueError(prefix + "gpus must be a positive integer or null, not a boolean")
    if rate is not None and not _positive(rate):
        raise ValueError(prefix + "rate must be a positive finite number or null, not a boolean")
    if basis not in ("per_gpu_hour", "per_instance_hour", None):
        raise ValueError(prefix + "unknown rate_basis")
    instance = row.get("instance_rate_usd_per_hour")
    if instance is not None and not _positive(instance):
        raise ValueError(prefix + "instance rate must be a positive finite number or null")
    if rate is not None and basis is None:
        raise ValueError(prefix + "numeric rate has no billing basis")
    if basis == "per_instance_hour" and (rate is not None or instance is not None):
        if instance is None or gpus is None:
            if rate is not None:
                raise ValueError(prefix + "instance normalization needs the instance rate and GPU count")
            # A quoted endpoint price with an explicitly unknown allocation is
            # useful retained evidence, but cannot supply a per-GPU price.
            return None
        normalized = instance / gpus
        if rate is not None and not math.isclose(rate, normalized, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(prefix + "per-GPU rate contradicts instance rate / GPU count")
        return normalized
    return rate


def _provider(task, source):
    owner = _owner(PROVIDER_OWNER)
    offer_id = task.get("offer_id")
    if offer_id is not None and (not isinstance(offer_id, str) or not offer_id.strip()):
        raise ValueError("offer_id must be a nonempty string")
    scenario = task.get("price_scenario")
    if scenario is not None:
        if not isinstance(scenario, dict) or set(scenario) != {"rate_usd_per_gpu_hour"}:
            raise ValueError("price_scenario needs only rate_usd_per_gpu_hour")
        if not _positive(scenario["rate_usd_per_gpu_hour"]):
            raise ValueError("price_scenario rate must be a positive finite number, not a boolean")
    parameters = {"offer_id": offer_id, "price_scenario": copy.deepcopy(scenario)}
    inputs = {"adapter_code": HERE, "provider_owner_code": PROVIDER_OWNER,
              "provider_source": source,
              "provider_schema": CAMPAIGN / "providers/SCHEMA.md",
              "target_reference": CAMPAIGN / "results/RUN3-RESULTS.md"}

    def execute():
        selected = []
        for line_number, raw in enumerate(source.read_bytes().splitlines(keepends=True), 1):
            if not raw.strip():
                continue
            row = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(row, dict):
                raise ValueError(f"provider line {line_number}: offer must be an object")
            if offer_id is not None and row.get("offer_id") != offer_id:
                continue
            rate = _validate_offer(row, owner, line_number)
            selected.append((line_number, raw, row, rate))
        if not selected:
            raise ValueError("no provider offers match the requested selection")
        ids = [row["offer_id"] for _, _, row, _ in selected]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate selected offer_id; select an unambiguous retained source")
        offers = []
        for line, raw, row, rate in selected:
            model_input = copy.deepcopy(row)
            model_rate = scenario["rate_usd_per_gpu_hour"] if scenario else rate
            model_input["rate_usd_per_gpu_hour"] = model_rate
            holds = []
            if rate is None:
                holds.append("source price unknown")
            if row["gpus"] is None:
                holds.append("smallest rentable GPU allocation unknown; no seat target")
            if not row["source_quote"].strip():
                holds.append("source quotation absent; staging declarations are not primary evidence")
            offers.append({
                "offer_id": row["offer_id"], "source_line": line,
                "source_row_sha256": _hash(raw), "native_row": copy.deepcopy(row),
                "declared_rate": {"value": rate, "unit": "USD/GPU-hour" if rate is not None else None,
                                  "basis": row["rate_basis"], "source_url": row["source_url"],
                                  "source_quote": row["source_quote"], "retrieved_at": row["retrieved_at"],
                                  "publication_date": None, "publication_date_basis": None,
                                  "semantic_source_validation": False},
                "modeled_targets": {"rate_usd_per_gpu_hour": model_rate,
                                    "price_scenario": copy.deepcopy(scenario),
                                    "values": owner.targets(model_input),
                                    "baseline": copy.deepcopy(owner.RUN3),
                                    "condition": "Assumes the Run 3 accepted work under its own-seat accounting; not provider performance or an invoice."},
                "declared_unverified": {key: copy.deepcopy(value) for key, value in row.items()
                                        if key not in ("source_url", "source_quote", "retrieved_at")},
                "holds": holds,
                "boundary": "Staged source account only. Quote and declared billing basis are retained; minimum billing, capacity, allocation, funding and ordinary-buyer access are not independently verified. No obtainable seat or measured cost established."
            })
        return {"status": "staged", "offers": offers, "offer_count": len(offers),
                "review_dates_renewed": False, "source_rewritten": False}

    return {"parameters": parameters, "inputs": inputs, "execute": execute}


def _benchmark(task, source):
    owner = _owner(BENCHMARK_OWNER)
    manifest = json.loads(source.read_bytes())
    if not isinstance(manifest, dict) or manifest.get("schema") != "backfill-manifest@1" or not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ValueError("expected a nonempty native backfill-manifest@1")
    inputs = {"adapter_code": HERE, "benchmark_owner_code": BENCHMARK_OWNER, "benchmark_manifest": source}
    sidecars, raw_files = [], []
    for index, entry in enumerate(manifest["files"]):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("every benchmark source needs its native path")
        raw = owner.local_path(source.parent, entry["path"])
        if not raw.is_file():
            raise ValueError("offline cache miss: " + entry["path"])
        receipt = raw.with_name(raw.name + ".retrieval.json")
        exists = receipt.exists()
        if exists and not receipt.is_file():
            raise ValueError("retrieval sidecar is not a regular file")
        role = f"benchmark_raw_{index:04d}"
        inputs[role] = raw
        inputs[role + "_retrieval"] = receipt if exists else None
        sidecars.append((receipt, exists))
        raw_files.append((entry, raw))

    def unchanged_optional_inputs():
        for path, existed in sidecars:
            if path.exists() != existed:
                raise ValueError("optional retrieval sidecar changed after prepare: " + str(path))

    def execute():
        unchanged_optional_inputs()
        observations = owner.import_manifest(source, offline=True)
        unchanged_optional_inputs()
        empty = [copy.deepcopy(entry) for entry, raw in raw_files
                 if entry.get("source") == "inferencemax" and json.loads(raw.read_bytes()) == []]
        source_rows = {(row["provenance"].get("artifact_id"), row["provenance"]["sha256"], row["row_index"])
                       for row in observations}
        return {"status": "imported", "observations": observations,
                "source_files": copy.deepcopy(manifest["files"]), "empty_archives": empty,
                "source_file_count": len(manifest["files"]), "source_row_count": len(source_rows),
                "observation_count": len(observations),
                "boundary": "Native imported observations and identities preserved. Empty archives remain source records. No underlying benchmark repetition, accepted work, price, publication date or funding is inferred."}

    return {"parameters": {}, "inputs": inputs, "execute": execute}


def prepare(task, base):
    """Prepare one offline native-source task; operator/request identity is not a parameter."""
    if not isinstance(task, dict):
        raise ValueError("task must be an object")
    kind = task.get("task_class")
    allowed = {"task_class", "id", "source", "actor"}
    if kind == "provider-intake":
        allowed |= {"offer_id", "price_scenario"}
    elif kind != "benchmark-import":
        raise ValueError("unsupported source task_class")
    extra = set(task) - allowed
    if extra:
        raise ValueError("unsupported task keys: " + ", ".join(sorted(extra)))
    if "id" in task and (not isinstance(task["id"], str) or not task["id"].strip()):
        raise ValueError("id must be a nonempty string when supplied")
    source = _source(task, base)
    return _provider(task, source) if kind == "provider-intake" else _benchmark(task, source)
