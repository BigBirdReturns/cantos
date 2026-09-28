"""Co-op pooling over staged provider offers through the native pool owner.

prepare(task, base) returns semantic parameters, dependency paths and a
no-argument executor. It never edits the offer file, renews retrieval dates,
contacts a provider or forms an agreement between members.
"""
from __future__ import annotations

import json
from pathlib import Path
import types

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
POOL_OWNER = ROOT / "hot-aisle/campaign/providers/pool.py"


def _owner(path):
    # Compile the pinned local owner without creating bytecode in its checkout.
    module = types.ModuleType("operation_" + path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def _path(task, key, base):
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key + " must be a nonempty local file path")
    path = Path(value)
    path = (path if path.is_absolute() else Path(base) / path).resolve()
    if not path.is_file():
        raise ValueError(key + " file is missing: " + str(path))
    return path


def prepare(task, base):
    if not isinstance(task, dict) or task.get("task_class") != "pool-purchase":
        raise ValueError("unsupported pool task_class")
    extra = set(task) - {"task_class", "id", "source", "offers", "actor", "availability_review", "marketplace_snapshot"}
    if extra:
        raise ValueError("unsupported task keys: " + ", ".join(sorted(extra)))
    if "id" in task and (not isinstance(task["id"], str) or not task["id"].strip()):
        raise ValueError("id must be a nonempty string when supplied")
    request, offers = _path(task, "source", base), _path(task, "offers", base)
    import task_sources
    supply = task_sources.prepare({"task_class": "provider-intake", "source": str(offers),
        **{k: task[k] for k in ("availability_review", "marketplace_snapshot") if k in task}}, base)
    owner = _owner(POOL_OWNER)
    owner.validate_request(json.loads(request.read_bytes().decode("utf-8-sig")))
    inputs = {"adapter_code": HERE, "pool_owner_code": POOL_OWNER,
              "pool_request": request, "provider_offers": offers,
              "provider_schema": ROOT / "hot-aisle/campaign/providers/SCHEMA.md"}

    inputs.update({"supply:" + role: path for role, path in supply["inputs"].items()})

    def execute():
        intake = supply["execute"]()
        usable, excluded = [], []
        for offer in intake["offers"]:
            evidence = offer.get("marketplace_evidence") or {}
            if evidence.get("evidence_class") == "official_documentation_sample":
                excluded.append({"offer_id": offer["offer_id"],
                                 "reason": "fictional documentation sample; excluded from price arithmetic"})
            else:
                usable.append(offer)
        result = owner.plan(json.loads(request.read_bytes().decode("utf-8-sig")),
                            [offer["native_row"] for offer in usable],
                            source_holds={offer["offer_id"]: offer["holds"] for offer in usable})
        result["offers_excluded"].extend(excluded)
        result["supply"] = {"intake": intake, "excluded_from_price_arithmetic": excluded,
                            "ready": False, "reserved": False, "execution_authorized": False}
        result["source_rewritten"] = False
        result["review_dates_renewed"] = False
        return result

    return {"parameters": {"supply": supply["parameters"]}, "inputs": inputs, "execute": execute}
