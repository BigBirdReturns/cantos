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
    extra = set(task) - {"task_class", "id", "source", "offers", "actor"}
    if extra:
        raise ValueError("unsupported task keys: " + ", ".join(sorted(extra)))
    if "id" in task and (not isinstance(task["id"], str) or not task["id"].strip()):
        raise ValueError("id must be a nonempty string when supplied")
    request, offers = _path(task, "source", base), _path(task, "offers", base)
    owner = _owner(POOL_OWNER)
    owner.validate_request(json.loads(request.read_bytes().decode("utf-8-sig")))
    inputs = {"adapter_code": HERE, "pool_owner_code": POOL_OWNER,
              "pool_request": request, "provider_offers": offers,
              "provider_schema": ROOT / "hot-aisle/campaign/providers/SCHEMA.md"}

    def execute():
        result = owner.plan(json.loads(request.read_bytes().decode("utf-8-sig")), owner.load_rows(offers))
        result["source_rewritten"] = False
        result["review_dates_renewed"] = False
        return result

    return {"parameters": {}, "inputs": inputs, "execute": execute}
