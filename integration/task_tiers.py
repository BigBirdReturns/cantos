"""Retain a native model/seat plan without promoting it to execution authority.

Tier-Bench's bridge owns model evidence; WATERLINE owns seat arithmetic. This
adapter only declares inputs and calls that existing path in the fresh worker.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "hot-aisle/campaign"
BRIDGE = CAMPAIGN / "tierbench-bridge"
LEDGER = CAMPAIGN / "ledger"
ALLOWED = {"id", "task_class", "actor", "source", "evidence", "seats",
           "availability", "local_models"}


def prepare(task, base):
    if not isinstance(task, dict) or task.get("task_class") != "tier-plan":
        raise ValueError("task_tiers only handles tier-plan")
    extra = set(task) - ALLOWED
    if extra:
        raise ValueError("Unknown tier-plan arguments: " + ", ".join(sorted(extra)))

    def path_arg(name, default=None):
        value = task.get(name, default)
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError(name + " must name a retained input")
        return (Path(base) / value).resolve()

    source = path_arg("source")
    evidence = path_arg("evidence")
    seats_path = path_arg("seats", LEDGER / "seats.json")
    availability = path_arg("availability", CAMPAIGN / "availability/observations.jsonl")
    local_models = path_arg("local_models", BRIDGE / "local_models.json")
    inputs = {
        "tier_adapter": Path(__file__).resolve(),
        "tier_owner": BRIDGE / "tier_waterline.py",
        "seat_owner": LEDGER / "waterline.py",
        "seat_helpers": LEDGER / "ledger_common.py",
        "knot": source,
        "tier_summary": evidence / "tierbench-summary.json",
        "tier_ladder": evidence / "tier-ladder.json",
        "seats": seats_path,
        "availability": availability,
        "local_models": local_models,
    }
    # Parse early so a malformed source cannot be mistaken for a reusable plan.
    knot = json.loads(source.read_bytes())
    if not isinstance(knot, dict) or knot.get("schema") != "second-run/knot-spec@1":
        raise ValueError("source must be a second-run/knot-spec@1 object")
    for name, schema in (("tier_summary", "second-run/tierbench-summary@1"),
                         ("tier_ladder", "second-run/tier-ladder@1")):
        value = json.loads(inputs[name].read_bytes())
        if not isinstance(value, dict) or value.get("schema") != schema:
            raise ValueError(name + " must be a native " + schema + " object")

    def execute():
        # Read operative values after the worker's initial dependency snapshot.
        # The prepare-time parse checks shape; it is not the execution snapshot.
        knot = json.loads(source.read_bytes())
        spec = importlib.util.spec_from_file_location("_work_tier_waterline", inputs["tier_owner"])
        owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(owner)
        seats = json.loads(seats_path.read_bytes())
        errors = owner.fabric.check_seats(seats)
        if errors:
            raise ValueError("Native seat registry refused: " + "; ".join(errors))
        observations = owner.load_jsonl(str(availability))
        models = json.loads(local_models.read_bytes())
        plan = owner.plan(knot, str(evidence), seats["seats"], observations, models)
        # Paths belong in the invocation receipt. Copying identical evidence to
        # another directory must not make an otherwise identical result differ.
        plan["evidence_dir"] = "bound inputs: tier_summary and tier_ladder"
        return {
            "basis": "supplied-tierbench-plan",
            "plan": plan,
            "execution_authorized": False,
            "new_model_measurement": False,
            "standing": "planning-only; native verdicts and limitations retained",
            "limits": [
                "The summary and ladder are supplied inputs, not a fresh audit of their upstream measurements.",
                "A chosen tier is the native model-evidence choice, not permission or proof of deadline, availability or evaluator equivalence.",
                "Historical dates, declared class analogies, modeled costs and unmeasured seat candidates remain historical, declared or modeled.",
                "No model call, resource acquisition, hybrid execution or current frontier comparison is performed.",
            ],
        }

    return {"parameters": {}, "inputs": inputs, "execute": execute}
