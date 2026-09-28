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


def _timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a timezone-aware ISO timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + " must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(label + " must be a timezone-aware ISO timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _availability(row, review):
    observed = row["availability_observed"]
    stamp = row.get("availability_ts")
    if stamp is not None:
        observed_at = _timestamp(stamp, "availability_ts")
    else:
        observed_at = None
    if observed != "unknown" and observed_at is None:
        raise ValueError("availability observation needs availability_ts")
    age = None
    if review is not None and observed_at is not None:
        age = (review["as_of_dt"] - observed_at).total_seconds() / 3600
        if age < 0:
            raise ValueError("availability observation is later than review as_of")
    if observed == "unknown":
        status = "unobserved"
    elif observed != "available":
        status = "observed_unavailable"
    elif review is None:
        status = "age_not_assessed"
    elif age > review["max_age_hours"]:
        status = "stale_observation"
    else:
        status = "observed_available_within_window"
    return {
        "status": status, "observed": observed, "observed_at": stamp,
        "as_of": review["as_of"] if review else None,
        "max_age_hours": review["max_age_hours"] if review else None,
        "age_hours": age,
        "rentable_now": False,
        "next_check": "Query the provider for a current offer and confirm account eligibility, allocation, full billing terms and successful provisioning before placement."
    }


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


def _vast_snapshot(source, snapshot):
    """Map retained Vast Search Offers JSON; collection is an explicit prior step."""
    if not isinstance(snapshot, dict) or set(snapshot) != {"source_url", "captured_at", "evidence_class"}:
        raise ValueError("marketplace_snapshot needs source_url, captured_at and evidence_class")
    source_url = snapshot["source_url"]
    evidence_class = snapshot["evidence_class"]
    allowed = {"official_api_response": "https://console.vast.ai/api/v0/bundles",
               "official_documentation_sample": "https://docs.vast.ai/api-reference/search/search-offers"}
    if evidence_class not in allowed or source_url != allowed[evidence_class]:
        raise ValueError("marketplace_snapshot source must match its official evidence class")
    captured_at = _timestamp(snapshot["captured_at"], "marketplace_snapshot captured_at")
    raw = source.read_bytes()
    body = json.loads(raw)
    if not isinstance(body, dict) or not isinstance(body.get("offers"), (list, dict)):
        raise ValueError("expected Vast Search Offers response with offers")
    offers = body["offers"] if isinstance(body["offers"], list) else [body["offers"]]
    if not offers:
        raise ValueError("Vast Search Offers response is empty")
    result = []
    seen = set()
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            raise ValueError("Vast offer must be an object")
        identity, count, name = offer.get("id"), offer.get("num_gpus"), offer.get("gpu_name")
        if type(identity) is not int or identity <= 0 or identity in seen:
            raise ValueError("Vast offer id must be a unique positive integer")
        seen.add(identity)
        if type(count) is not int or count <= 0:
            raise ValueError("Vast num_gpus must be a positive integer")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Vast gpu_name must be a nonempty string")
        if offer.get("resource_type") != "gpu":
            raise ValueError("Vast offer must have resource_type gpu")
        if offer.get("currency", "USD") != "USD":
            raise ValueError("Vast offer currency must be USD")
        search = offer.get("search")
        if not isinstance(search, dict) or not _positive(search.get("gpuCostPerHour")):
            raise ValueError("Vast search.gpuCostPerHour must be positive USD per offer-hour")
        for field in ("storage_cost", "internet_up_cost_per_tb", "internet_down_cost_per_tb"):
            value = offer.get(field)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError("Vast " + field + " must be nonnegative when present")
        available = offer.get("rentable") is True and offer.get("rented") is False
        unavailable = offer.get("rentable") is False or offer.get("rented") is True
        observed = ("available" if available else "out_of_stock" if unavailable else "unknown") if evidence_class == "official_api_response" else "unknown"
        compute = search["gpuCostPerHour"]
        offer_id = f"vast-offer-{identity}"
        row = {"provider_id": "vast", "provider_name": "Vast.ai", "offer_id": offer_id,
               "gpu": name, "vendor": "NVIDIA" if offer.get("gpu_arch") == "nvidia" else "unknown",
               "memoryGB": None, "gpus": count, "rate_usd_per_gpu_hour": compute / count,
               "rate_basis": "per_instance_hour", "instance_rate_usd_per_hour": compute,
               "kind": "marketplace", "minimum_billing": "unknown", "regions": [offer["geolocation"]] if isinstance(offer.get("geolocation"), str) else [],
               "self_serve": "unknown", "availability_observed": observed,
               "availability_ts": captured_at.isoformat().replace("+00:00", "Z") if observed != "unknown" else None,
               "source_url": source_url, "source_quote": f'"gpuCostPerHour": {json.dumps(compute)}',
               "retrieved_at": captured_at.isoformat().replace("+00:00", "Z"),
               "campaign_role": "other", "notes": "Search listing only; account eligibility, minimum billing and total bill unverified."}
        evidence = {"provider_offer_id": identity, "response_index": index,
                    "evidence_class": evidence_class, "source_url": source_url,
                    "captured_at": row["retrieved_at"], "capture_time_basis": "caller_declared",
                    "raw_snapshot_sha256": _hash(raw),
                    "raw_offer_sha256": _hash(json.dumps(offer, sort_keys=True, separators=(",", ":")).encode("utf-8")),
                    "raw_offer": copy.deepcopy(offer),
                    "charges": {"currency": "USD", "compute_instance_usd_per_hour": compute,
                                "compute_gpu_usd_per_hour": compute / count,
                                "storage_usd_per_gb_month": offer.get("storage_cost"),
                                "bandwidth_up_usd_per_tb": offer.get("internet_up_cost_per_tb"),
                                "bandwidth_down_usd_per_tb": offer.get("internet_down_cost_per_tb"),
                                "advertised_total_usd_per_hour": search.get("totalHour"),
                                "total_bill_qualified": False}}
        result.append((index + 1, json.dumps(offer, sort_keys=True).encode("utf-8"), row, compute / count, evidence))
    return result


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
    review = task.get("availability_review")
    if review is not None:
        if not isinstance(review, dict) or set(review) != {"as_of", "max_age_hours"}:
            raise ValueError("availability_review needs as_of and max_age_hours")
        if not _positive(review["max_age_hours"]):
            raise ValueError("availability_review max_age_hours must be positive and finite")
        as_of = _timestamp(review["as_of"], "availability_review as_of")
        review = {"as_of": as_of.isoformat().replace("+00:00", "Z"),
                  "as_of_dt": as_of, "max_age_hours": review["max_age_hours"]}
    marketplace = task.get("marketplace_snapshot")
    if marketplace is not None:
        if scenario is not None:
            raise ValueError("price_scenario is not supported for marketplace snapshots")
        if not isinstance(marketplace, dict):
            raise ValueError("marketplace_snapshot must be an object")
        # Validate metadata before work.py creates a reusable operation key.
        if set(marketplace) != {"source_url", "captured_at", "evidence_class"}:
            raise ValueError("marketplace_snapshot needs source_url, captured_at and evidence_class")
        _timestamp(marketplace["captured_at"], "marketplace_snapshot captured_at")
    parameters = {"offer_id": offer_id, "price_scenario": copy.deepcopy(scenario),
                  "marketplace_snapshot": copy.deepcopy(marketplace),
                  "availability_review": {k: v for k, v in review.items() if k != "as_of_dt"} if review else None}
    inputs = {"adapter_code": HERE, "provider_owner_code": PROVIDER_OWNER,
              "provider_source": source,
              "provider_schema": CAMPAIGN / "providers/SCHEMA.md",
              "target_reference": CAMPAIGN / "results/RUN3-RESULTS.md"}

    def execute():
        selected = []
        if marketplace is not None:
            candidates = _vast_snapshot(source, marketplace)
        else:
            candidates = []
            for line_number, raw in enumerate(source.read_bytes().splitlines(keepends=True), 1):
                if not raw.strip():
                    continue
                row = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(row, dict):
                    raise ValueError(f"provider line {line_number}: offer must be an object")
                candidates.append((line_number, raw, row, None, None))
        for line_number, raw, row, rate, evidence in candidates:
            if offer_id is not None and row.get("offer_id") != offer_id:
                continue
            validated_rate = _validate_offer(row, owner, line_number)
            if evidence is None:
                rate = validated_rate
            selected.append((line_number, raw, row, rate, evidence))
        if not selected:
            raise ValueError("no provider offers match the requested selection")
        ids = [row["offer_id"] for _, _, row, _, _ in selected]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate selected offer_id; select an unambiguous retained source")
        offers = []
        for line, raw, row, rate, evidence in selected:
            model_input = copy.deepcopy(row)
            model_rate = scenario["rate_usd_per_gpu_hour"] if scenario else rate
            if evidence is not None and evidence["evidence_class"] == "official_documentation_sample":
                model_rate = None
            model_input["rate_usd_per_gpu_hour"] = model_rate
            holds = []
            availability = _availability(row, review)
            if availability["status"] != "observed_available_within_window":
                holds.append("placement requires a current available offer; availability status: " + availability["status"])
            if evidence is not None:
                holds.append("marketplace snapshot is a listing, not obtained capacity or an account-specific quote")
                if evidence["evidence_class"] == "official_documentation_sample":
                    holds.append("documentation sample is fictional and cannot establish a price target")
            if rate is None:
                holds.append("source price unknown")
            if row["gpus"] is None:
                holds.append("smallest rentable GPU allocation unknown; no seat target")
            if not row["source_quote"].strip():
                holds.append("source quotation absent; staging declarations are not primary evidence")
            offers.append({
                "offer_id": row["offer_id"], "source_line": line if evidence is None else None,
                "source_row_sha256": evidence["raw_offer_sha256"] if evidence else _hash(raw),
                "native_row": copy.deepcopy(row),
                "marketplace_evidence": evidence,
                "declared_rate": {"value": rate, "unit": "USD/GPU-hour" if rate is not None else None,
                                  "basis": row["rate_basis"], "source_url": row["source_url"],
                                  "source_quote": row["source_quote"], "retrieved_at": row["retrieved_at"],
                                  "publication_date": None, "publication_date_basis": None,
                                  "semantic_source_validation": False},
                "availability_review": availability,
                "modeled_targets": {"rate_usd_per_gpu_hour": model_rate,
                                    "price_scenario": copy.deepcopy(scenario),
                                    "values": owner.targets(model_input),
                                    "baseline": copy.deepcopy(owner.RUN3),
                                    "condition": "Assumes the Run 3 accepted work under its own-seat accounting; not provider performance or an invoice."},
                "declared_unverified": {key: copy.deepcopy(value) for key, value in row.items()
                                        if key not in ("source_url", "source_quote", "retrieved_at")},
                "holds": holds,
                "boundary": ("Marketplace response mapping only. The listing, price components and caller-declared capture time do not establish an account-specific quote, minimum billing, full bill, obtained capacity or a reservation."
                             + (" Documentation samples are fictional." if evidence["evidence_class"] == "official_documentation_sample" else "")
                             if evidence else
                             "Staged source account only. Quote and declared billing basis are retained; minimum billing, capacity, allocation, funding and ordinary-buyer access are not independently verified. No obtainable seat or measured cost established.")
            })
        return {"status": "marketplace_snapshot" if marketplace else "staged", "offers": offers, "offer_count": len(offers),
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
        allowed |= {"offer_id", "price_scenario", "availability_review", "marketplace_snapshot"}
    elif kind != "benchmark-import":
        raise ValueError("unsupported source task_class")
    extra = set(task) - allowed
    if extra:
        raise ValueError("unsupported task keys: " + ", ".join(sorted(extra)))
    if "id" in task and (not isinstance(task["id"], str) or not task["id"].strip()):
        raise ValueError("id must be a nonempty string when supplied")
    source = _source(task, base)
    return _provider(task, source) if kind == "provider-intake" else _benchmark(task, source)
