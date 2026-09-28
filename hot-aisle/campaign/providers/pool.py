#!/usr/bin/env python3
"""Co-op pooling arithmetic over staged provider offers (list price only).

Several members each need G GPUs for H hours. Offers are sold in whole units
(`gpus` per unit) and bill at least `minimum_billing`. For every offer that a
member accepts, this packs the accepting members onto whole units, bills each
unit until its last member ends (or its minimum), and splits the cent-rounded
bill in proportion to GPU-hours, with shares that sum exactly to the bill. Each
share is compared with that member's cheapest standalone purchase from the same
file and with its cheapest standalone purchase that carries no hold; the holds
on both sides travel into the plan's conclusion.

A plan is arithmetic on staged list prices. It is not a quote, reservation,
availability check, invoice or purchase, and it never renews a source row.

    python pool.py REQUEST.json providers.jsonl [--top N] [--offer OFFER_ID]
"""
from __future__ import annotations
import datetime, json, math, re, sys
from decimal import Decimal
from fractions import Fraction

MONTH_HOURS = 730  # 365 * 24 / 12; used only when a minimum is stated in months
UNIT_HOURS = {"second": Fraction(1, 3600), "minute": Fraction(1, 60), "hour": Fraction(1),
              "day": Fraction(24), "month": Fraction(MONTH_HOURS)}
MINIMUM = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(second|minute|hour|day|month)s?\b")
DEFAULT_KINDS = ("on-demand", "reserved", "capacity-block")
DEFAULT_ACCESS = ("yes", "quota")
MAX_UNITS = 64


def exact(value):
    """A JSON number as the exact decimal it was written as (1.99 -> 199/100)."""
    return Fraction(Decimal(str(value)))


def to_cents(amount):
    """Round a nonnegative exact dollar amount half-up to integer cents."""
    return math.floor(amount * 100 + Fraction(1, 2))


def dollars(cents):
    return cents / 100


def minimum_exact(text):
    """Return (exact hours or None, note or None) for a staged minimum_billing string."""
    text = (text or "").strip().lower()
    if not text or text.startswith("unknown"):
        return None, "minimum billing unknown; billed hours are a lower bound"
    found = [Fraction(n) * UNIT_HOURS[u] for n, u in MINIMUM.findall(text)]
    if not found:
        return None, "minimum billing unparsed (" + text + "); billed hours are a lower bound"
    note = None
    if len(set(found)) > 1:
        note = "conflicting minimum statements (" + text + "); the largest is used"
    if "+" in text:
        note = "minimum stated as open-ended (" + text + "); the stated floor is used"
    return max(found), note


def minimum_hours(text):
    hours, note = minimum_exact(text)
    return (None if hours is None else float(hours)), note


def offer_rate(row):
    rate = row.get("rate_usd_per_gpu_hour")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate > 0:
        return float(rate)
    inst, gpus = row.get("instance_rate_usd_per_hour"), row.get("gpus")
    if isinstance(inst, (int, float)) and isinstance(gpus, int) and gpus > 0 and inst > 0:
        return inst / gpus
    return None


def unit_rate(row):
    """Exact list dollars per unit-hour: per-GPU rate x unit GPUs, else the instance rate as quoted."""
    rate = row.get("rate_usd_per_gpu_hour")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate > 0:
        return exact(rate) * row["gpus"]
    return exact(row["instance_rate_usd_per_hour"])


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
    """First-fit (widest, then earliest deadline, then longest) onto whole units; a member's GPUs share one unit and one start.

    Hours are exact Fractions measured from a common pool start (hour 0)."""
    units, placed, unplaced = [], {}, {}

    def deadline_of(m):
        return min(term, exact(m["window_hours"]) if m.get("window_hours") else term)

    # Tighter windows go first within a width, so a short-deadline member is not
    # pushed onto a fresh (possibly minimum-billed) unit behind a long one.
    order = sorted(members, key=lambda m: (-m["gpus"], deadline_of(m), -exact(m["hours"]), m["id"]))
    for m in order:
        hours = exact(m["hours"])
        if m["gpus"] > unit:
            unplaced[m["id"]] = f"needs {m['gpus']} co-located GPUs; unit has {unit}"
            continue
        deadline = deadline_of(m)
        if hours > deadline:
            unplaced[m["id"]] = "hours exceed the pool term or member window"
            continue
        for index in range(max_units):
            if index == len(units):
                units.append([Fraction(0)] * unit)
            lanes = sorted(range(unit), key=lambda i: (units[index][i], i))[:m["gpus"]]
            start = max(units[index][i] for i in lanes)
            if start + hours <= deadline:
                for i in lanes:
                    units[index][i] = start + hours
                placed[m["id"]] = {"unit": index, "lanes": sorted(lanes), "start": start, "end": start + hours}
                break
        else:
            unplaced[m["id"]] = f"no room within max_units={max_units}"
    while units and not any(units[-1]):
        units.pop()
    return len(units), placed, unplaced


def billed_hours(used, min_hours):
    return max(used, min_hours) if min_hours is not None else used


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


def standalone(member, offers, clean_only=False):
    """Cheapest single-unit purchase for one member; clean_only skips offers carrying any hold."""
    best = None
    hours = exact(member["hours"])
    for row, per_unit, min_hours, min_note in offers:
        if not accepts(member, row) or member["gpus"] > row["gpus"]:
            continue
        holds = holds_for(row, min_note)
        if clean_only and holds:
            continue
        billed = billed_hours(hours, min_hours)
        cents = to_cents(per_unit * billed)
        if best is None or (cents, row["offer_id"]) < best[0]:
            best = ((cents, row["offer_id"]), {
                "offer_id": row["offer_id"], "cost_usd": dollars(cents), "cost_cents": cents,
                "billed_hours": float(billed), "gpus_bought": row["gpus"],
                "minimum_known": min_hours is not None, "qualifications": holds})
    return best[1] if best else None


def allocate(total_cents, weights):
    """Split integer cents in proportion to exact weights; largest remainder, ties by key.

    The parts always sum to total_cents exactly."""
    whole = sum(weights.values())
    raw = {k: Fraction(total_cents) * w / whole for k, w in weights.items()}
    parts = {k: math.floor(v) for k, v in raw.items()}
    left = total_cents - sum(parts.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - parts[k]), k))[:left]:
        parts[k] += 1
    return parts


def evaluate(pool, row, per_unit, min_hours, refs, req, cap):
    term = exact(req["term_hours"]) if req.get("term_hours") else max(
        exact(m.get("window_hours") or m["hours"]) for m in pool)
    count, placed, unplaced = pack(pool, row["gpus"], term, cap)
    served = [m for m in pool if m["id"] in placed]
    if len(served) < 2:
        return None
    # Each whole unit is released when its last member finishes and bills at least the minimum.
    schedule, bought = [], Fraction(0)
    for index in range(count):
        on_unit = sorted((m for m in served if placed[m["id"]]["unit"] == index),
                         key=lambda m: (placed[m["id"]]["start"], m["id"]))
        end = max(placed[m["id"]]["end"] for m in on_unit)
        billed = billed_hours(end, min_hours)
        bought += row["gpus"] * billed
        charge = to_cents(per_unit * billed)
        schedule.append({"unit": index, "gpus": row["gpus"], "end_hour": float(end),
                         "billed_hours": float(billed), "charge_cents": charge, "charge_usd": dollars(charge),
                         "runs": [{"member": m["id"], "lanes": placed[m["id"]]["lanes"],
                                   "start_hour": float(placed[m["id"]]["start"]),
                                   "end_hour": float(placed[m["id"]]["end"])} for m in on_unit]})
    bill_cents = sum(u["charge_cents"] for u in schedule)
    used = {m["id"]: m["gpus"] * exact(m["hours"]) for m in served}
    total_used = sum(used.values())
    share_cents = allocate(bill_cents, used)
    per_gpu = per_unit / row["gpus"]
    shares, worse, saving, ref_total = [], [], 0, 0
    for m in served:
        listed, clean = refs[m["id"]]
        delta = listed["cost_cents"] - share_cents[m["id"]]
        saving += delta
        ref_total += listed["cost_cents"]
        if delta < 0:
            worse.append(m["id"])
        shares.append({"member": m["id"], "gpu_hours": float(used[m["id"]]),
                       "unit": placed[m["id"]]["unit"], "lanes": placed[m["id"]]["lanes"],
                       "start_hour": float(placed[m["id"]]["start"]), "end_hour": float(placed[m["id"]]["end"]),
                       "share_cents": share_cents[m["id"]], "share_usd": dollars(share_cents[m["id"]]),
                       "standalone": listed, "standalone_unqualified": clean,
                       "saving_vs_standalone_usd": dollars(delta),
                       "saving_vs_unqualified_usd": None if clean is None else dollars(clean["cost_cents"] - share_cents[m["id"]])})
    if sum(s["share_cents"] for s in shares) != bill_cents:
        raise AssertionError("member shares do not reconcile to the modeled bill")
    return {"members_served": [m["id"] for m in served], "members_unplaced": unplaced,
            "units": count, "gpus_bought": count * row["gpus"],
            "term_used_hours": float(max(placed[m["id"]]["end"] for m in served)),
            "billed_hours": max(u["billed_hours"] for u in schedule), "billed_gpu_hours": float(bought),
            "pool_cost_usd": dollars(bill_cents), "pool_cost_cents": bill_cents,
            "used_gpu_hours": float(total_used), "idle_gpu_hours": float(bought - total_used),
            "idle_cost_usd": dollars(bill_cents - to_cents(per_gpu * total_used)),
            "utilization": round(float(total_used / bought), 4),
            "break_even_utilization": round(float(per_gpu * total_used * 100 / ref_total), 4) if ref_total else None,
            "schedule": schedule, "shares": shares,
            "reconciliation": {"unit_charges_cents": bill_cents, "share_cents": sum(share_cents.values()),
                               "rule": "each unit rounded half-up to cents; shares by largest remainder"},
            "total_saving_vs_standalone_usd": dollars(saving),
            "every_member_no_worse": not worse, "worse": worse}


POOL_SIDE = "pool bill or execution may be worse than modeled; savings are an upper bound"
REFERENCE_SIDE = ("standalone reference is a lower bound or may not be purchasable; the listed "
                  "saving is conservative but the reference may not be a real alternative")


def conclusion(coalition, holds):
    """Carry every assumption behind a no-worse claim, labelled by the direction it can move."""
    if coalition is None:
        return {"status": "no_coalition", "arithmetic_no_worse": False,
                "no_worse_vs_unqualified_references": None, "qualifications": []}
    quals = [{"scope": "pool_offer", "hold": h, "effect": POOL_SIDE} for h in holds]
    missing_clean = []
    for s in coalition["shares"]:
        for h in s["standalone"]["qualifications"]:
            quals.append({"scope": "reference:" + s["member"], "offer_id": s["standalone"]["offer_id"],
                          "hold": h, "effect": REFERENCE_SIDE})
        if s["standalone_unqualified"] is None:
            missing_clean.append(s["member"])
    vs_clean = None if missing_clean else all(s["saving_vs_unqualified_usd"] >= 0 for s in coalition["shares"])
    status = ("not_no_worse" if not coalition["every_member_no_worse"]
              else "qualified" if quals else "unqualified_at_list")
    return {"status": status, "arithmetic_no_worse": coalition["every_member_no_worse"],
            "no_worse_vs_unqualified_references": vs_clean,
            "members_without_unqualified_reference": missing_clean,
            "pool_bill_is_lower_bound": any(h.startswith("minimum billing un") for h in holds),
            "qualifications": quals}


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
        min_hours, min_note = minimum_exact(row.get("minimum_billing"))
        usable.append((row, unit_rate(row), min_hours, min_note))
    refs = {m["id"]: (standalone(m, usable), standalone(m, usable, clean_only=True)) for m in members}
    plans, no_effect = [], []
    shortest = min(exact(m["hours"]) for m in members)
    for row, per_unit, min_hours, min_note in usable:
        pool = [m for m in members if accepts(m, row)]
        if len(pool) < 2:
            continue
        if row["gpus"] == 1 and (min_hours is None or min_hours <= shortest):
            # One-GPU units without a binding minimum: pooling equals buying separately.
            no_effect.append(row["offer_id"])
            continue
        full = evaluate(pool, row, per_unit, min_hours, refs, req, cap)
        if full is None:
            continue
        # Coalition: a co-op does not admit a member it makes worse off. Drop the
        # worst-off member and recompute until everyone left is no worse, or < 2 remain.
        current, dropped = full, []
        while current is not None and current["worse"]:
            worst = min(current["shares"], key=lambda x: (x["saving_vs_standalone_usd"], x["member"]))
            dropped.append(worst["member"])
            pool = [m for m in pool if m["id"] != worst["member"]]
            current = evaluate(pool, row, per_unit, min_hours, refs, req, cap) if len(pool) >= 2 else None
        holds = holds_for(row, min_note)
        age = None
        if as_of and row.get("retrieved_at"):
            seen = datetime.datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
            age = round((as_of - seen).total_seconds() / 86400, 1)
        for part in (full, current):
            if part is not None:
                part.pop("worse", None)
        verdict = conclusion(current, holds)
        plans.append({
            "offer_id": row["offer_id"], "provider_id": row["provider_id"], "gpu": row["gpu"],
            "kind": row["kind"], "unit_gpus": row["gpus"], "rate_usd_per_gpu_hour": offer_rate(row),
            "minimum_billing": row.get("minimum_billing"),
            "all_accepting": full, "coalition": current, "dropped_for_coalition": dropped,
            "coalition_saving_usd": current["total_saving_vs_standalone_usd"] if current else None,
            "holds": holds, "conclusion": verdict,
            "arithmetic_no_worse": verdict["arithmetic_no_worse"],
            "bindable_at_list": False, "execution_authority": False,
            "binding_status": "unverified: retained list arithmetic cannot establish a current offer, account eligibility, reservation or authority to purchase",
            "source": {"source_url": row.get("source_url"), "source_quote": row.get("source_quote"),
                       "retrieved_at": row.get("retrieved_at"), "age_days": age}})
    plans.sort(key=lambda p: (p["coalition"] is None, -(p["coalition_saving_usd"] or 0), p["offer_id"]))
    return {"schema": "capital/pool-result@1", "members": [m["id"] for m in members],
            "standalone": {k: v[0] for k, v in refs.items()},
            "standalone_unqualified": {k: v[1] for k, v in refs.items()},
            "plans": plans, "plan_count": len(plans),
            "offers_considered": len(usable), "offers_excluded": excluded,
            "offers_without_pooling_effect": no_effect,
            "assumptions": [
                "List price times whole units times billed hours; no discounts, volume or term pricing, taxes, storage, egress or support.",
                "Money is exact decimal arithmetic on the quoted figures. Each unit's charge is rounded half-up to cents; the modeled bill is the sum of unit charges.",
                "A member's GPUs are co-located on one unit and start together. All windows are measured from one common pool start; members may run back to back on a lane only within their window_hours.",
                "Each unit is released when its last member finishes: billed hours = max(that unit's used span, stated minimum). Billing quantum beyond the minimum is not in the staging schema.",
                "The bill is split in proportion to GPU-hours used (own GPU-hours at list plus an idle share by GPU-hours); cents go by largest remainder, ties by member id, so shares sum exactly to the bill.",
                "standalone is each member's cheapest listed single-unit purchase, holds included; standalone_unqualified skips offers with any hold and may be null. Coalitions are formed against standalone.",
                "all_accepting keeps every accepting member even when worse off; coalition drops the worst-off member until none is worse off.",
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
              f"(util {full['utilization']:.2f}, break-even {full['break_even_utilization']}) | {tail} | "
              f"{p['conclusion']['status']}, holds={len(p['holds'])}")
    print(f"{result['plan_count']} pool plans, {result['offers_considered']} offers priced, "
          f"{len(result['offers_excluded'])} excluded")
    if "--offer" in argv:
        wanted = argv[argv.index("--offer") + 1]
        chosen = [p for p in result["plans"] if p["offer_id"] == wanted]
        if not chosen:
            print("no pool plan for offer " + wanted, file=sys.stderr)
            return 1
        print_allocation(chosen[0])
    return 0


def print_allocation(p):
    part, label = (p["coalition"], "coalition") if p["coalition"] else (p["all_accepting"], "all accepting (no coalition)")
    print(f"\n{p['offer_id']}: {label}, conclusion {p['conclusion']['status']}; not a quote, reservation or purchase")
    for u in part["schedule"]:
        runs = ", ".join(f"{r['member']} lanes {r['lanes']} h{r['start_hour']:g}-{r['end_hour']:g}" for r in u["runs"])
        print(f"  unit {u['unit']}: billed {u['billed_hours']:g} h, ${u['charge_usd']:.2f} | {runs}")
    for s in part["shares"]:
        ref, clean = s["standalone"], s["standalone_unqualified"]
        alt = "none without holds" if clean is None else f"{clean['offer_id']} ${clean['cost_usd']:.2f}"
        print(f"  {s['member']:12} pays ${s['share_usd']:.2f} | listed alone {ref['offer_id']} ${ref['cost_usd']:.2f}"
              f" ({len(ref['qualifications'])} holds) | unqualified alone {alt}")
    print(f"  total ${part['pool_cost_usd']:.2f} = unit charges {part['reconciliation']['unit_charges_cents']} c"
          f" = shares {part['reconciliation']['share_cents']} c")
    for q in p["conclusion"]["qualifications"]:
        print(f"  qualification [{q['scope']}] {q['hold']}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
