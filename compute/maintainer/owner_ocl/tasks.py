from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any

FAMILIES = (
    "invoice_minor_units",
    "inventory_selection",
    "telemetry_aggregation",
    "source_id_evidence",
)


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    key: str
    fixture: Any
    expected: Any
    description: str


def _invoice(rng: random.Random, index: int) -> Task:
    rows = []
    total = 0
    for line in range(4):
        quantity = rng.randint(1, 7)
        unit = rng.randint(125, 2400)
        discount = rng.randint(0, min(75, unit // 5))
        amount = quantity * (unit - discount)
        total += amount
        rows.append({"line": line + 1, "quantity": quantity, "unit_minor": unit, "discount_minor": discount})
    fixture = {"currency": "USD", "lines": rows, "claimed_total_minor": total + (1 if index % 2 else 0)}
    key = f"invoice-{index}"
    return Task(key, FAMILIES[0], key, fixture, {"total_minor": total, "matches_claimed": index % 2 == 0}, "Reconcile invoice amounts in integer minor units.")


def _inventory(rng: random.Random, index: int) -> Task:
    items = []
    for item in range(5):
        stock = rng.randint(0, 12)
        price = rng.randint(100, 1800)
        items.append({"sku": f"SKU-{index}-{item + 1}", "stock": stock, "price_minor": price})
    requested = rng.randint(2, 8)
    feasible = [x for x in items if x["stock"] >= requested]
    chosen = min(feasible, key=lambda x: (x["price_minor"], x["sku"])) if feasible else None
    fixture = {"requested": requested, "items": items}
    expected = {"feasible": chosen is not None, "sku": chosen["sku"] if chosen else None, "price_minor": chosen["price_minor"] if chosen else None}
    key = f"inventory-{index}"
    return Task(key, FAMILIES[1], key, fixture, expected, "Select the least expensive item with sufficient stock.")


def _telemetry(rng: random.Random, index: int) -> Task:
    samples = [{"device": f"D{rng.randint(1, 3)}", "value": rng.randint(-20, 80)} for _ in range(8)]
    aggregate = {}
    for sample in samples:
        aggregate[sample["device"]] = aggregate.get(sample["device"], 0) + sample["value"]
    expected = {"totals": {k: aggregate[k] for k in sorted(aggregate)}}
    key = f"telemetry-{index}"
    return Task(key, FAMILIES[2], key, {"samples": samples}, expected, "Aggregate telemetry values by device using integer arithmetic.")


def _evidence(rng: random.Random, index: int) -> Task:
    records = []
    for item in range(5):
        records.append({"source_id": f"SRC-{index}-{item + 1}", "title": f"Evidence document {item + 1}", "year": 2020 + rng.randint(0, 5), "relevant": item == index % 5})
    wanted = records[index % 5]["source_id"]
    found = next(x for x in records if x["source_id"] == wanted)
    key = f"evidence-{index}"
    return Task(key, FAMILIES[3], key, {"records": records, "source_id": wanted}, {"source_id": wanted, "title": found["title"], "year": found["year"]}, "Look up the requested source identifier exactly.")


def make_tasks(seed: int = 1729) -> list[Task]:
    result = []
    for family in range(4):
        for index in range(3):
            rng = random.Random(seed + family * 1009 + index * 9176)
            result.append((_invoice, _inventory, _telemetry, _evidence)[family](rng, index))
    return result


def fixture_hash(tasks: list[Task] | None = None) -> str:
    tasks = make_tasks() if tasks is None else tasks
    payload = [{"key": t.key, "fixture": t.fixture, "expected": t.expected} for t in tasks]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def lookup(tasks: list[Task], key: str) -> Any:
    matches = [task for task in tasks if task.key == key]
    if len(matches) != 1:
        raise KeyError(key)
    return matches[0].fixture
