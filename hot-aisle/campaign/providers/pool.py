#!/usr/bin/env python3
"""Co-op pooling arithmetic over staged provider offers (list price only).

Several members each need G GPUs for H hours. Offers are sold in whole units
(`gpus` per unit) and bill at least `minimum_billing`. For every offer that a
member accepts, this packs the accepting members onto whole units, bills the
term, and splits the bill: each member pays its own GPU-hours at the offer rate
plus a share of the idle remainder in proportion to its GPU-hours. Each share
is compared with that member's cheapest standalone purchase from the same file.

A plan is arithmetic on staged list prices. It is not a quote, reservation,
availability check, invoice or purchase, and it never renews a source row.

    python pool.py REQUEST.json providers.jsonl [--top N]
"""
from __future__ import annotations
import datetime, json, math, re, sys

MONTH_HOURS = 730  # 365 * 24 / 12; used only when a minimum is stated in months
UNIT_HOURS = {"second": 1 / 3600, "minute": 1 / 60, "hour": 1, "day": 24, "month": MONTH_HOURS}
MINIMUM = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(second|minute|hour|day|month)s?\b")
DEFAULT_KINDS = ("on-demand", "reserved", "capacity-block")
DEFAULT_ACCESS = ("yes", "quota")
MAX_UNITS = 64


def minimum_hours(text):
    """Return (hours or None, note or None) for a staged minimum_billing string."""
    text = (text or "").strip().lower()
    if not text or text.startswith("unknown"):
        return None, "minimum billing unknown; billed hours are a lower bound"
    found = [float(n) * UNIT_HOURS[u] for n, u in MINIMUM.findall(text)]
    if not found:
        return None, "minimum billing unparsed (" + text + "); billed hours are a lower bound"
    note = None
    if len(set(found)) > 1:
        note = "conflicting minimum statements (" + text + "); the largest is used"
    if "+" in text:
        note = "minimum stated as open-ended (" + text + "); the stated floor is used"
    return max(found), note


def offer_rate(row):
    rate = row.get("rate_usd_per_gpu_hour")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate > 0:
        return float(rate)
    inst, gpus = row.get("instance_rate_usd_per_hour"), row.get("gpus")
    if isinstance(inst, (int, float)) and isinstance(gpus, int) and gpus > 0 and inst > 0:
        return inst / gpus
    return None


def validate_request(req):
    if not isinstance(req, dict) or req.get("schema") != "capital/pool-request@1":
        raise ValueError("expected schema capital/pool-request@1")
    members = req.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("members must be a nonempty list")
    seen = set()
    for m in members:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"].strip():
            raise ValueError("every member needs a nonempty string id")
        if m["id"] in seen:
            raise ValueError("duplicate member id " + m["id"])
        seen.add(m["id"])
        if type(m.get("gpus")) is not int or m["gpus"] <= 0:
            raise ValueError(m["id"] + ": gpus must be a positive integer")
        for key in ("hours", "window_hours"):
            v = m.get(key)
            if key == "window_hours" and v is None:
                continue
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise ValueError(m["id"] + ": " + key + " must be a positive number")
        if m.get("window_hours") is not None and m["window_hours"] < m["hours"]:
            raise ValueError(m["id"] + ": window_hours shorter than hours")
        if not isinstance(m.get("accept_gpu"), list) or not m["accept_gpu"]:
            raise ValueError(m["id"] + ": accept_gpu must list at least one GPU")
    term = req.get("term_hours")
    if term is not None and (type(term) not in (int, float) or not math.isfinite(term) or term <= 0):
        raise ValueError("term_hours must be a positive number")
    as_of = req.get("as_of")
    if as_of is not None:
        try:
            stamp = datetime.datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("as_of must be an ISO timestamp") from exc
        if stamp.tzinfo is None:
            raise ValueError("as_of needs a timezone")
    cap = req.get("max_units", MAX_UNITS)
    if type(cap) is not int or cap <= 0:
        raise ValueError("max_units must be a positive integer")
    return req


def accepts(member, row):
    if row.get("gpu") not in member["accept_gpu"]:
        return False
    if row.get("kind") not in member.get("kinds", DEFAULT_KINDS):
        return False
    if row.get("self_serve") not in member.get("self_serve", DEFAULT_ACCESS):
        return False
    need = member.get("min_memory_gb")
    if need is not None and not (isinstance(row.get("memoryGB"), int) and row["memoryGB"] >= need):
        return False
    return True


def pack(members, unit, term, max_units):
    """First-fit-decreasing onto whole units; a member's GPUs share one unit and one start."""
    units, placed, unplaced = [], {}, {}
    order = sorted(members, key=lambda m: (-m["gpus"], -m["hours"], m["id"]))
    for m in order:
        if m["gpus"] > unit:
            unplaced[m["id"]] = f"needs {m['gpus']} co-located GPUs; unit has {unit}"
            continue
        deadline = min(term, m.get("window_hours") or term)
        if m["hours"] > deadline + 1e-9:
            unplaced[m["id"]] = "hours exceed the pool term or member window"
            continue
        for index in range(max_units):
            if index == len(units):
                units.append([0.0] * unit)
            lanes = sorted(range(unit), key=lambda i: (units[index][i], i))[:m["gpus"]]
            start = max(units[index][i] for i in lanes)
            if start + m["hours"] <= deadline + 1e-9:
                for i in lanes:
                    units[index][i] = start + m["hours"]
                placed[m["id"]] = {"unit": index, "lanes": sorted(lanes), "start_hour": start}
                break
        else:
            unplaced[m["id"]] = f"no room within max_units={max_units}"
    while units and not any(units[-1]):
        units.pop()
    return len(units), placed, unplaced


def bill(rate, gpus_bought, hours, min_hours):
    billed = max(hours, min_hours) if min_hours is not None else hours
    return billed, rate * gpus_bought * billed


def holds_for(row, min_note):
    holds = []
    if min_note:
        holds.append(min_note)
    if row.get("availability_observed") != "available":
        holds.append("availability observed: " + str(row.get("availability_observed")))
    if row.get("kind") in ("spot", "marketplace"):
        holds.append(row["kind"] + " pricing: eviction or price movement not modeled")
    if row.get("self_serve") != "yes":
        holds.append("access: self_serve=" + str(row.get("self_serve")))
    if not (row.get("source_quote") or "").strip():
        holds.append("no source quotation retained")
    return holds


def standalone(member, offers):
    best = None
    for row, rate, min_hours, _ in offers:
        if not accepts(member, row) or member["gpus"] > row["gpus"]:
            continue
        gpus_bought = row["gpus"] * math.ceil(member["gpus"] / row["gpus"])
        billed, cost = bill(rate, gpus_bought, member["hours"], min_hours)
        key = (cost, row["offer_id"])
        if best is None or key < best[0]:
            best = (key, {"offer_id": row["offer_id"], "cost_usd": round(cost, 2),
                          "billed_hours": billed, "gpus_bought": gpus_bought,
                          "minimum_known": min_hours is not None})
    return best[1] if best else None


def evaluate(pool, row, rate, min_hours, alone, req, cap):
    term = req.get("term_hours") or max(m.get("window_hours") or m["hours"] for m in pool)
    count, placed, unplaced = pack(pool, row["gpus"], term, cap)
    served = [m for m in pool if m["id"] in placed]
    if len(served) < 2:
        return None
    used_to = max(placed[m["id"]]["start_hour"] + m["hours"] for m in served)
    gpus_bought = count * row["gpus"]
    billed, cost = bill(rate, gpus_bought, used_to, min_hours)
    used = {m["id"]: m["gpus"] * m["hours"] for m in served}
    total_used = sum(used.values())
    idle_cost = cost - rate * total_used
    shares, worse, savings, reference = [], [], 0.0, 0.0
    for m in served:
        share = rate * used[m["id"]] + idle_cost * used[m["id"]] / total_used
        ref = alone[m["id"]]
        delta = None if ref is None else ref["cost_usd"] - share
        if delta is not None:
            savings += delta
            reference += ref["cost_usd"]
            if delta < -0.005:
                worse.append(m["id"])
        shares.append({"member": m["id"], "gpu_hours": used[m["id"]], **placed[m["id"]],
                       "share_usd": round(share, 2), "standalone": ref,
                       "saving_vs_standalone_usd": None if delta is None else round(delta, 2)})
    comparable = all(s["standalone"] is not None for s in shares)
    return {"members_served": [m["id"] for m in served], "members_unplaced": unplaced,
            "units": count, "gpus_bought": gpus_bought, "term_used_hours": used_to,
            "billed_hours": billed, "pool_cost_usd": round(cost, 2), "used_gpu_hours": total_used,
            "idle_gpu_hours": round(gpus_bought * billed - total_used, 4),
            "idle_cost_usd": round(idle_cost, 2),
            "utilization": round(total_used / (gpus_bought * billed), 4),
            "break_even_utilization": round(rate * total_used / reference, 4) if comparable and reference else None,
            "shares": shares, "total_saving_vs_standalone_usd": round(savings, 2),
            "every_member_no_worse": not worse, "worse": worse}


def plan(request, rows):
    req = validate_request(request)
    as_of = req.get("as_of")
    as_of = as_of and datetime.datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    members = req["members"]
    cap = req.get("max_units", MAX_UNITS)
    usable, excluded = [], []
    for row in rows:
        rate = offer_rate(row)
        if rate is None or not isinstance(row.get("gpus"), int) or row["gpus"] <= 0:
            excluded.append({"offer_id": row.get("offer_id"),
                             "reason": "no public rate" if rate is None else "smallest rentable unit unknown"})
            continue
        min_hours, min_note = minimum_hours(row.get("minimum_billing"))
        usable.append((row, rate, min_hours, min_note))
    alone = {m["id"]: standalone(m, usable) for m in members}
    plans, no_effect = [], []
    shortest = min(m["hours"] for m in members)
    for row, rate, min_hours, min_note in usable:
        pool = [m for m in members if accepts(m, row)]
        if len(pool) < 2:
            continue
        if row["gpus"] == 1 and (min_hours is None or min_hours <= shortest):
            # One-GPU units without a binding minimum: pooling equals buying separately.
            no_effect.append(row["offer_id"])
            continue
        full = evaluate(pool, row, rate, min_hours, alone, req, cap)
        if full is None:
            continue
        # Coalition: a co-op does not admit a member it makes worse off. Drop the
        # worst-off member and recompute until everyone left is no worse, or < 2 remain.
        current, dropped = full, []
        while current is not None and current["worse"]:
            worst = min(current["shares"], key=lambda x: (x["saving_vs_standalone_usd"], x["member"]))
            dropped.append(worst["member"])
            pool = [m for m in pool if m["id"] != worst["member"]]
            current = evaluate(pool, row, rate, min_hours, alone, req, cap) if len(pool) >= 2 else None
        holds = holds_for(row, min_note)
        age = None
        if as_of:
            seen = datetime.datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
            age = round((as_of - seen).total_seconds() / 86400, 1)
        for part in (full, current):
            if part is not None:
                part.pop("worse", None)
        plans.append({
            "offer_id": row["offer_id"], "provider_id": row["provider_id"], "gpu": row["gpu"],
            "kind": row["kind"], "unit_gpus": row["gpus"], "rate_usd_per_gpu_hour": rate,
            "minimum_billing": row.get("minimum_billing"),
            "all_accepting": full, "coalition": current, "dropped_for_coalition": dropped,
            "coalition_saving_usd": current["total_saving_vs_standalone_usd"] if current else None,
            "holds": holds,
            "arithmetic_no_worse": bool(current) and current["every_member_no_worse"],
            "bindable_at_list": False,
            "binding_status": "unverified: retained list arithmetic cannot establish a current offer, account eligibility, reservation or authority to purchase",
            "source": {"source_url": row.get("source_url"), "source_quote": row.get("source_quote"),
                       "retrieved_at": row.get("retrieved_at"), "age_days": age}})
    plans.sort(key=lambda p: (p["coalition"] is None, -(p["coalition_saving_usd"] or 0), p["offer_id"]))
    return {"schema": "capital/pool-result@1", "members": [m["id"] for m in members],
            "standalone": alone, "plans": plans, "plan_count": len(plans),
            "offers_considered": len(usable), "offers_excluded": excluded,
            "offers_without_pooling_effect": no_effect,
            "assumptions": [
                "List price times whole units times billed hours; no discounts, taxes, storage, egress or support.",
                "A member's GPUs are co-located on one unit and start together; members may run back to back on a lane only within their window_hours.",
                "Billed hours = max(term actually used, stated minimum); billing quantum beyond the minimum is not in the staging schema.",
                "Idle cost is split in proportion to GPU-hours used. all_accepting keeps every accepting member even when worse off; coalition drops the worst-off member until none is worse off.",
                "break_even_utilization is the fraction of bought GPU-hours the pool must use for its bill to equal its members' summed standalone costs.",
                f"A minimum stated in months uses {MONTH_HOURS} hours per month."],
            "boundary": "Staged list-price arithmetic only. Not a quote, reservation, availability check, invoice, purchase or co-op agreement; source rows are not renewed or verified."}


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 10
    with open(argv[1], encoding="utf-8-sig") as stream:
        request = json.load(stream)
    result = plan(request, load_rows(argv[2]))
    for p in result["plans"][:top]:
        full, coal = p["all_accepting"], p["coalition"]
        tail = "no coalition" if coal is None else (
            f"coalition {'+'.join(coal['members_served'])} saves ${coal['total_saving_vs_standalone_usd']:.2f}"
            f" (util {coal['utilization']:.2f}, break-even {coal['break_even_utilization']})")
        print(f"{p['offer_id']:30} {p['unit_gpus']}-GPU unit ${p['rate_usd_per_gpu_hour']:.2f}/GPU-h | all: "
              f"${full['pool_cost_usd']:.2f} saves ${full['total_saving_vs_standalone_usd']:.2f} "
              f"(util {full['utilization']:.2f}, break-even {full['break_even_utilization']}) | {tail} | holds={len(p['holds'])}")
    print(f"{result['plan_count']} pool plans, {result['offers_considered']} offers priced, "
          f"{len(result['offers_excluded'])} excluded")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
