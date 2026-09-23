#!/usr/bin/env python3
"""WATERLINE: feasibility before price. Stdlib only.

    python waterline.py plan <knot.json> [--seats seats.json] [--availability observations.jsonl]
                                         [--start-at 2026-09-29T10:00:00Z] [--json out.json]
    python waterline.py check-seats [seats.json]
    python waterline.py --selftest

Input: a Knot spec (model bytes per format, batch depths or a closures-per-traversal curve, deadline,
evaluator, count), seats.json and the availability observations.
Output: feasible seats; a written reason for every infeasible one; three plans (fastest, cheapest,
most efficient by closures per traversal, tie-broken per $). Every plan carries estimated wall clock,
cost, and a success probability from the availability data, and says when that data is too thin.
Refusals are always written reasons, never a bare "does not fit".

Exit codes: 0 plans produced; 2 refused (no feasible seat); 1 error.
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.dirname(HERE)
DEFAULT_SEATS = os.path.join(HERE, "seats.json")
DEFAULT_AVAIL = os.path.join(CAMPAIGN, "availability", "observations.jsonl")
THIN_PROBES = 5           # fewer probes than this -> "too thin"
ATTEMPT_METHODS = {"console-create", "tui-provision", "api-create", "estate-lease"}
LISTING_METHODS = {"console-plan-list", "tui-provision-list", "api", "prior-session-note"}


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_jsonl(path):
    out = []
    if path and os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            if ln.strip():
                out.append(json.loads(ln))
    return out


def fmt_s(s):
    if s is None:
        return "unestimated"
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.1f} min"
    return f"{s / 3600:.2f} h"


def gb(b):
    return f"{b / 1e9:.1f} GB"


# ---------------------------------------------------------------- availability
def availability_for(seat, observations, start_at):
    """Listed fraction (probes) and delivered fraction (attempts) for a cloud seat; declared for estate seats."""
    av = seat.get("availability") or {}
    busy = av.get("declared_busy_until")
    if seat.get("provider") == "estate":
        if busy and start_at and parse_iso(busy) > start_at:
            return {"probability": 0.0, "basis": f"declared busy until {busy} ({av.get('note', '')})", "thin": True, "probes": 0, "attempts": 0, "busy_until": busy}
        return {"probability": 1.0, "basis": "operator declaration, not a probe; no estate availability data", "thin": True, "probes": 0, "attempts": 0, "busy_until": busy}
    key = av.get("key") or {}
    rows = [o for o in observations if all(o.get(k) == v for k, v in key.items())]
    probes = [o for o in rows if o.get("method") in LISTING_METHODS or o.get("method") in ATTEMPT_METHODS]
    listed = sum(1 for o in probes if o.get("outcome") == "available")
    attempts = [o for o in rows if o.get("method") in ATTEMPT_METHODS or o.get("provisioned") is True]
    delivered = sum(1 for o in attempts if o.get("provisioned") is True)
    if not probes:
        return {"probability": None, "basis": "no observations for this SKU", "thin": True, "probes": 0, "attempts": 0}
    p_listed = listed / len(probes)
    p_deliv = (delivered / len(attempts)) if attempts else None
    p = p_listed * (p_deliv if p_deliv is not None else 1.0)
    return {
        "probability": round(p, 3), "probes": len(probes), "listed": listed, "attempts": len(attempts), "delivered": delivered,
        "thin": len(probes) < THIN_PROBES,
        "basis": (f"listed {listed}/{len(probes)} probes; delivered {delivered}/{len(attempts)} attempts"
                  + (f" -- TOO THIN: {len(probes)} probes (< {THIN_PROBES}); treat as a guess until the heatmap has data" if len(probes) < THIN_PROBES else "")),
    }


# ---------------------------------------------------------------- traversal time
def curve_for(seat, model_class, fmt):
    for c in (seat.get("traversal") or {}).get("curves") or []:
        if c.get("model_class") == model_class and (fmt is None or c.get("format") == fmt):
            return c
    for c in (seat.get("traversal") or {}).get("curves") or []:
        if c.get("model_class") == model_class:
            return c
    return None


def interp(by_depth, depth):
    """Linear interpolation on the measured depth curve; beyond the last point returns (value, 'extrapolated')."""
    pts = sorted((p["depth"], p["seconds"]) for p in by_depth)
    if depth <= pts[0][0]:
        return pts[0][1], ("measured" if depth == pts[0][0] else "below measured depth")
    for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
        if d0 <= depth <= d1:
            return s0 + (s1 - s0) * (depth - d0) / (d1 - d0), ("measured" if depth in (d0, d1) else "interpolated")
    d_last, s_last = pts[-1]
    return s_last * (depth / d_last) ** 0.5, f"extrapolated beyond measured depth {d_last} (sqrt scaling, an assumption)"


def compute_seconds_per_traversal(seat, knot_fmt, model_class, depth, resident):
    """Return (seconds, basis) for one traversal at this depth, or (None, reason)."""
    curve = curve_for(seat, model_class, knot_fmt["format"])
    if curve:
        s, how = interp(curve["by_depth"], depth)
        return s, f"{how} from the seat's {model_class}/{curve.get('format')} curve ({curve.get('receipt')})"
    # no curve for this model class: scale a resident bandwidth estimate, and say so
    tr = seat.get("traversal") or {}
    bps = tr.get("resident_bytes_per_second_estimate")
    if resident and bps:
        s1 = knot_fmt["bytes"] / bps
        other = (tr.get("curves") or [None])[0]
        if other and len(other["by_depth"]) > 1:
            base = other["by_depth"][0]["seconds"]
            sd, how = interp(other["by_depth"], depth)
            return s1 * (sd / base), f"ASSUMED: bytes / resident-bandwidth estimate ({tr.get('resident_bytes_per_second_basis')}), depth scaling borrowed from the {other['model_class']} curve ({how})"
        return s1 * (1.0 if depth == 1 else 1.0), f"ASSUMED: bytes / resident-bandwidth estimate ({tr.get('resident_bytes_per_second_basis')}); depth {depth} assumed free (UNMEASURED beyond depth 1)"
    if resident:
        # cloud HBM seat with a curve for a different model class: borrow with a loud flag
        curves = tr.get("curves") or []
        if curves:
            c = curves[0]
            ratio = knot_fmt["bytes"] / max(1, c.get("model_bytes", knot_fmt["bytes"]))
            sd, how = interp(c["by_depth"], depth)
            return sd * ratio, f"ASSUMED: borrowed the {c['model_class']} curve ({how}) with no byte scaling ({c.get('receipt')}); a pilot cell should replace this"
    return None, "no traversal curve for this model class on this seat and no bandwidth estimate; wall clock cannot be estimated"


# ---------------------------------------------------------------- evaluation
def evaluate_seat(seat_id, seat, knot, observations, start_at, kwh_usd):
    """Returns {'feasible': bool, 'reasons': [...], 'candidates': [...]} for one seat."""
    reasons = []
    roles = seat.get("roles") or []
    if "execute" not in roles:
        return {"feasible": False, "reasons": [f"{seat_id}: roles {roles} -- validator-only or support seat, not qualified for execution (SYNTHESIS: iGPUs and the NPU are validator seats until qualified)"], "candidates": []}
    if seat.get("status") == "unavailable":
        note = (seat.get("availability") or {}).get("note") or seat.get("identity_reason") or ""
        return {"feasible": False, "reasons": [f"{seat_id}: unavailable -- {note}"], "candidates": []}
    av = availability_for(seat, observations, start_at)
    hard_reasons = []
    if av.get("probability") == 0.0:
        # busy is a hard refusal, but keep evaluating so the memory / recipe verdict is written too
        hard_reasons.append(f"{seat_id}: {av['basis']}")

    # recipe / format match
    sw = seat.get("software") or {}
    seat_recipes = set(sw.get("recipes") or [])
    seat_formats = set(sw.get("formats_supported") or [])
    usable = (seat.get("accelerator") or {}).get("usable_for_weights_bytes")
    link = seat.get("link") or {}
    link_bps = link.get("bytes_per_second")
    candidates = []
    fmt_reasons = []
    for f in knot["model"]["formats"]:
        if not (set(f["recipes"]) & seat_recipes) or f["format"] not in seat_formats:
            fmt_reasons.append(f"format {f['format']} needs recipes {f['recipes']} / seat runs {sorted(seat_recipes)} and supports {sorted(seat_formats)}")
            continue
        if usable is None:
            fmt_reasons.append(f"format {f['format']}: seat has no usable_for_weights_bytes ({(seat.get('accelerator') or {}).get('memory_reason', 'unknown memory')})")
            continue
        resident = f["bytes"] <= usable
        mode = "resident"
        if not resident:
            host_ram = ((seat.get("host") or {}).get("ram_bytes"))
            if curve_for(seat, knot["model"]["class"], f["format"]) and (host_ram is None or f["bytes"] <= host_ram + usable):
                mode = "split"          # measured partial-offload curve for this model class on this seat
            elif link_bps:
                mode = "streamed"       # measured link rate: non-resident bytes cross the link every traversal
            else:
                extra = f"; host RAM {gb(host_ram)} {'also too small for a split' if host_ram and f['bytes'] > host_ram else 'could hold a split but no split curve exists for this model class'}" if host_ram else ""
                fmt_reasons.append(f"format {f['format']} ({gb(f['bytes'])}) exceeds the seat's usable weight memory ({gb(usable)}, {(seat.get('accelerator') or {}).get('usable_basis', '')}) and the seat has no measured streamed link (link.bytes_per_second null: {link.get('bytes_per_second_reason', 'unmeasured')}){extra}")
                continue
        candidates.append((f, mode))
    if not candidates:
        return {"feasible": False, "reasons": hard_reasons + [f"{seat_id}: " + r for r in fmt_reasons], "candidates": []}

    # per (format, depth) plans
    plans = []
    depth_reasons = []
    count = knot["count"]
    t_out = knot.get("tokens_out_per_closure", 256)
    depths = (knot.get("traversal_profile") or {}).get("batch_depths") or [1]
    setup = (seat.get("setup") or {}).get("t_request_to_ready_s")
    setup_basis = (seat.get("setup") or {}).get("basis") or (seat.get("setup") or {}).get("reason")
    setup_s = setup if setup is not None else 0.0
    setup_note = f"setup {fmt_s(setup)} ({setup_basis})" if setup is not None else f"setup UNKNOWN, counted as 0 ({setup_basis})"
    price = seat.get("price") or {}
    rate = price.get("list_rate_per_gpu_hr")
    prior = ((seat.get("priors") or {}).get(knot["task_class"]) or {})
    accept_rate = prior.get("accept_rate")
    accept_basis = f"prior from {prior.get('receipt')}" if accept_rate is not None else f"no prior for task class '{knot['task_class']}' on this seat; assumed 1.0"
    if accept_rate is None:
        accept_rate = 1.0
    for f, mode in candidates:
        resident = mode == "resident"
        for d in depths:
            s_comp, basis = compute_seconds_per_traversal(seat, f, knot["model"]["class"], d, resident or mode == "split")
            if s_comp is None and mode == "streamed":
                # the link term alone is a lower bound on a streamed traversal; plan on it and say so
                s_comp, basis = 0.0, f"compute time unknown ({basis}); LOWER BOUND from the link term only"
            if s_comp is None:
                depth_reasons.append(f"{seat_id} {f['format']} depth {d}: {basis}")
                continue
            path = ("resident-hbm" if "hbm" in (link.get("path") or "") else "resident-gddr") if resident else (link.get("path") or ("split-vram-ram" if mode == "split" else "streamed"))
            s_link = 0.0
            if mode == "streamed":
                nonres = f["bytes"] - usable
                s_link = nonres / link_bps
            elif mode == "split":
                basis += f"; SPLIT: {gb(f['bytes'] - usable)} of weights live in host RAM and are computed by the CPU, nothing streams per step"
            s_trav = max(s_comp, s_link)
            waves = math.ceil(count / d)
            traversals = waves * (t_out + 1)      # +1: prefill counted as one traversal per wave (chunked prefill not separated)
            work_s = traversals * s_trav
            wall_s = setup_s + work_s
            usd = None
            cost_basis = None
            if rate is not None:
                billable = wall_s
                mins = price.get("minimum_s")
                if mins:
                    billable = max(billable, mins)
                if price.get("billing") == "per-minute":
                    billable = math.ceil(billable / 60) * 60
                usd = rate * (seat.get("accelerator") or {}).get("count", 1) * billable / 3600
                cost_basis = f"list ${rate}/GPU-hr x {fmt_s(billable)} ({price.get('billing')}); modeled, not billed"
            else:
                watts = price.get("nameplate_watts")
                if watts is not None and kwh_usd is not None:
                    usd = watts * wall_s / 3600 / 1000 * kwh_usd
                    cost_basis = f"energy: nameplate {watts} W (NOT metered) x {fmt_s(wall_s)} x ${kwh_usd}/kWh (assumed tariff)"
                else:
                    cost_basis = "owned seat; no nameplate watts or tariff -> cost unestimated"
            exp_acc = count * accept_rate
            plan = {
                "seat_id": seat_id, "format": f["format"], "bytes": f["bytes"], "resident": resident, "mode": mode, "path": path, "depth": d,
                "traversals": traversals, "seconds_per_traversal": round(s_trav, 6),
                "seconds_per_traversal_basis": basis + (f"; link-bound: {gb(f['bytes'] - usable)} non-resident / {link_bps / 1e6:.0f} MB/s = {s_link:.2f} s per traversal" if mode == "streamed" else ""),
                "setup_s": setup, "setup_note": setup_note, "work_s": round(work_s, 1), "wall_s": round(wall_s, 1),
                "usd": round(usd, 4) if usd is not None else None, "cost_basis": cost_basis,
                "expected_accepted": round(exp_acc, 1), "accept_basis": accept_basis,
                "closures_per_traversal": round(exp_acc / traversals, 6),
                "closures_per_usd": round(exp_acc / usd, 3) if usd else None,
                "availability": av, "success_probability": av.get("probability"),
                "deadline_s": knot["deadline_s"], "deadline_margin_s": round(knot["deadline_s"] - wall_s, 1),
                "assumptions": [a for a in [basis if "ASSUMED" in basis or "extrapolated" in basis else None,
                                            "setup counted as 0" if setup is None else None,
                                            "accept rate assumed 1.0" if "assumed" in accept_basis else None,
                                            "grading time on the grader seat is not modeled (runs concurrently on CPU)"] if a],
            }
            if wall_s > knot["deadline_s"]:
                depth_reasons.append(
                    f"{seat_id} {f['format']} depth {d}: traversal time exceeds the deadline -- {traversals} traversals x {s_trav:.4f} s "
                    f"= {fmt_s(work_s)} of work{' (link-bound: ' + gb(f['bytes'] - usable) + ' non-resident per traversal over ' + f'{link_bps / 1e6:.0f} MB/s)' if mode == 'streamed' else ''} "
                    f"+ {setup_note} = {fmt_s(wall_s)} against a {fmt_s(knot['deadline_s'])} deadline")
                continue
            max_usd = (knot.get("policy") or {}).get("max_usd")
            if usd is not None and max_usd is not None and usd > max_usd:
                depth_reasons.append(f"{seat_id} {f['format']} depth {d}: modeled cost ${usd:.2f} exceeds the Knot's max_usd ${max_usd:.2f} ({cost_basis})")
                continue
            plans.append(plan)
    if hard_reasons:
        summary = ([f"{seat_id}: memory/recipe verdict if it were free: feasible ({len(plans)} depth plans)"] if plans else []) + depth_reasons
        return {"feasible": False, "reasons": hard_reasons + summary, "candidates": []}
    if not plans:
        return {"feasible": False, "reasons": depth_reasons or [f"{seat_id}: no depth produced a plan"], "candidates": []}
    return {"feasible": True, "reasons": depth_reasons, "candidates": plans}


def grader_seats(seats, knot):
    role = (knot.get("evaluator") or {}).get("needs_seat_role")
    if not role:
        return []
    return [sid for sid, s in seats.items() if role in (s.get("roles") or [])]


def plan(knot, seats, observations, start_at=None, kwh_usd=None):
    start_at = start_at or parse_iso(knot["start_at"]) if knot.get("start_at") else start_at
    kwh_usd = kwh_usd if kwh_usd is not None else (knot.get("policy") or {}).get("kwh_usd")
    feasible, infeasible, all_cands = {}, {}, []
    for sid, seat in seats.items():
        r = evaluate_seat(sid, seat, knot, observations, start_at, kwh_usd)
        if r["feasible"]:
            feasible[sid] = {"depths_refused": r["reasons"], "plans": r["candidates"]}
            all_cands.extend(r["candidates"])
        else:
            infeasible[sid] = r["reasons"]
    graders = grader_seats(seats, knot)
    out = {
        "schema": "second-run/waterline-plan@1", "knot_id": knot["knot_id"], "start_at": start_at.strftime("%Y-%m-%dT%H:%M:%SZ") if start_at else None,
        "deadline_s": knot["deadline_s"], "count": knot["count"],
        "grader_seats": graders,
        "feasible_seats": sorted(feasible), "infeasible": infeasible,
        "feasible_detail": feasible,
        "plans": {}, "refused": False, "refusal_reasons": [], "data_thin": any(c["availability"].get("thin") for c in all_cands),
    }
    if (knot.get("evaluator") or {}).get("needs_seat_role") and not graders:
        out["refused"] = True
        out["refusal_reasons"].append(f"no seat carries the grader role '{knot['evaluator']['needs_seat_role']}' the evaluator needs")
    if not all_cands:
        out["refused"] = True
        out["refusal_reasons"].append("no seat is feasible for this Knot; see infeasible[] for each seat's written reason")
        return out
    with_cost = [c for c in all_cands if c["usd"] is not None]
    fastest = min(all_cands, key=lambda c: c["wall_s"])
    cheapest = min(with_cost, key=lambda c: c["usd"]) if with_cost else None
    efficient = max(all_cands, key=lambda c: (c["closures_per_traversal"], c["closures_per_usd"] or 0))
    out["plans"] = {"fastest": fastest, "cheapest": cheapest, "most_efficient": efficient}
    if cheapest is None:
        out["refusal_reasons"].append("no candidate had an estimable cost; 'cheapest' is empty")
    return out


def render(p):
    lines = [f"WATERLINE plan for {p['knot_id']}  (count {p['count']}, deadline {fmt_s(p['deadline_s'])}, start {p['start_at']})"]
    lines.append(f"grader seats: {', '.join(p['grader_seats']) or 'NONE'}")
    lines.append("")
    lines.append("Infeasible seats:")
    for sid, rs in p["infeasible"].items():
        for r in rs:
            lines.append(f"  - {r}")
    lines.append("")
    lines.append(f"Feasible seats: {', '.join(p['feasible_seats']) or 'none'}")
    for sid, d in p["feasible_detail"].items():
        for r in d["depths_refused"]:
            lines.append(f"  (refused depth) {r}")
    lines.append("")
    if p["refused"]:
        lines.append("REFUSED:")
        for r in p["refusal_reasons"]:
            lines.append(f"  - {r}")
        return "\n".join(lines)
    for name in ("fastest", "cheapest", "most_efficient"):
        c = p["plans"].get(name)
        if not c:
            lines.append(f"{name}: none ({'; '.join(p['refusal_reasons'])})")
            continue
        lines.append(f"{name.upper()}: {c['seat_id']} {c['format']} depth {c['depth']} ({c['path']})")
        lines.append(f"    wall {fmt_s(c['wall_s'])} = {c['setup_note']} + {c['traversals']} traversals x {c['seconds_per_traversal']} s; margin {fmt_s(c['deadline_margin_s'])}")
        lines.append(f"    cost {'$%.2f' % c['usd'] if c['usd'] is not None else 'unestimated'} ({c['cost_basis']})")
        lines.append(f"    closures/traversal {c['closures_per_traversal']}  closures/$ {c['closures_per_usd']}  expected accepted {c['expected_accepted']} ({c['accept_basis']})")
        lines.append(f"    success probability {c['success_probability']} -- {c['availability']['basis']}")
        if c["assumptions"]:
            lines.append(f"    assumptions: {'; '.join(c['assumptions'])}")
    if p["data_thin"]:
        lines.append("")
        lines.append("NOTE: availability data is too thin for a real probability on at least one plan; run the heatmap probe before trusting these numbers.")
    return "\n".join(lines)


# ---------------------------------------------------------------- seats check
def check_seats(seats_doc):
    """Measured fields must cite a basis/receipt; nulls must carry a reason. Returns error list."""
    errs = []
    for sid, s in (seats_doc.get("seats") or {}).items():
        for k in ("provider", "sku", "kind", "accelerator", "link", "software", "price", "setup", "traversal", "availability", "roles", "status", "power"):
            if k not in s:
                errs.append(f"{sid}: missing {k}")
        acc = s.get("accelerator") or {}
        if acc.get("usable_for_weights_bytes") is not None and not acc.get("usable_basis"):
            errs.append(f"{sid}: usable_for_weights_bytes without usable_basis")
        pr = s.get("price") or {}
        if pr.get("list_rate_per_gpu_hr") is not None and not pr.get("source"):
            errs.append(f"{sid}: list rate without source")
        if pr.get("nameplate_watts") is not None and not pr.get("nameplate_basis"):
            errs.append(f"{sid}: nameplate_watts without nameplate_basis")
        st = s.get("setup") or {}
        if st.get("t_request_to_ready_s") is not None and not st.get("basis"):
            errs.append(f"{sid}: setup time without basis")
        if st.get("t_request_to_ready_s") is None and not (st.get("reason") or st.get("basis") is None and st.get("reason")):
            if not st.get("reason"):
                errs.append(f"{sid}: setup time null without reason")
        ln = s.get("link") or {}
        for k in ("bytes_per_second", "bytes_per_second_cold", "bytes_per_second_warm"):
            if ln.get(k) is not None and not (ln.get("bytes_per_second_basis") or ln.get("receipts")):
                errs.append(f"{sid}: link.{k} without basis/receipts")
        if ln.get("bytes_per_second") is None and not ln.get("bytes_per_second_reason"):
            errs.append(f"{sid}: link.bytes_per_second null without reason")
        tr = s.get("traversal") or {}
        for i, c in enumerate(tr.get("curves") or []):
            if not c.get("receipt") or not c.get("basis"):
                errs.append(f"{sid}: traversal.curves[{i}] without receipt/basis")
            if not c.get("by_depth"):
                errs.append(f"{sid}: traversal.curves[{i}] has no by_depth")
        for i, m in enumerate(tr.get("measured") or []):
            if not m.get("receipt"):
                errs.append(f"{sid}: traversal.measured[{i}] without receipt")
        pw = s.get("power") or {}
        if pw.get("watts_mean") is None and not pw.get("reason"):
            errs.append(f"{sid}: power.watts_mean null without reason")
        if "execute" in (s.get("roles") or []) and s.get("status") != "unavailable" and acc.get("usable_for_weights_bytes") is None:
            errs.append(f"{sid}: execute seat without usable_for_weights_bytes")
    return errs


# ---------------------------------------------------------------- self-test
def selftest():
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
        ok = ok and cond
    seats_doc = json.load(open(DEFAULT_SEATS, encoding="utf-8"))
    seats = seats_doc["seats"]
    obs = load_jsonl(os.path.join(HERE, "fixtures", "availability-2026-09-23.jsonl"))
    errs = check_seats(seats_doc)
    check(not errs, f"seats.json: measured fields cite receipts, nulls carry reasons ({errs[:3] if errs else 'clean'})")
    k30 = json.load(open(os.path.join(HERE, "fixtures", "knots", "knot-30b-coding.json"), encoding="utf-8"))
    k70 = json.load(open(os.path.join(HERE, "fixtures", "knots", "knot-70b-dense.json"), encoding="utf-8"))

    # 1. 70B dense on 2026-09-24: 3090s refused with a memory reason; H100 refused on 72 GB; H200 unavailable; MI300X plans
    p = plan(k70, seats, obs)
    check(not p["refused"], "70B: not refused outright (a seat exists)")
    r3090 = " ".join(p["infeasible"].get("estate-w01-3090", []))
    check("exceeds the seat's usable weight memory" in r3090 and "no measured streamed link" in r3090, "70B: W01 3090 refused with a written memory + no-streamed-link reason")
    check("busy" in " ".join(p["infeasible"].get("estate-n01-3090-egpu", [])) or "exceeds" in " ".join(p["infeasible"].get("estate-n01-3090-egpu", [])), "70B: N01 eGPU 3090 refused (busy or memory)")
    check("72.0 GB" in " ".join(p["infeasible"].get("do-h100-nyc2", [])), "70B: H100 refused: 72.7 GB > 72.0 GB usable")
    check("unavailable" in " ".join(p["infeasible"].get("do-h200-any", [])), "70B: H200 refused as unavailable (0/6 regions)")
    check("validator-only" in " ".join(p["infeasible"].get("estate-npu", [])), "70B: NPU refused as validator-only")
    check(p["feasible_seats"] == ["hotaisle-mi300x-1x-enc1"], f"70B: only Hot Aisle MI300X feasible ({p['feasible_seats']})")
    f = p["plans"]["fastest"]
    check(f["seat_id"] == "hotaisle-mi300x-1x-enc1" and f["wall_s"] < k70["deadline_s"], f"70B: fastest plan on MI300X within deadline ({fmt_s(f['wall_s'])}, ${f['usd']})")
    check(p["data_thin"] and f["availability"]["thin"], "70B: availability flagged as too thin (n < 5 probes)")

    # 2. 30B coding on 2026-09-24: cloud feasible, estate 3090s busy, 4060 link-bound past the deadline
    p = plan(k30, seats, obs)
    check(set(p["feasible_seats"]) == {"hotaisle-mi300x-1x-enc1", "do-h100-nyc2"}, f"30B 09-24: feasible = both cloud seats ({p['feasible_seats']})")
    check("declared busy until 2026-09-28" in " ".join(p["infeasible"].get("estate-w01-3090", [])), "30B 09-24: W01 3090 refused as busy until 09-28")
    r4060 = " ".join(p["infeasible"].get("estate-w01-4060", []))
    check("traversal time exceeds the deadline" in r4060 and "link-bound" in r4060, "30B 09-24: 4060 refused: streamed traversal time exceeds the deadline (written)")
    check(p["plans"]["most_efficient"]["depth"] == 64, f"30B: most efficient plan is the deepest batch (depth {p['plans']['most_efficient']['depth']})")
    check(p["plans"]["cheapest"]["seat_id"] == "hotaisle-mi300x-1x-enc1", f"30B: cheapest cloud plan is Hot Aisle ({p['plans']['cheapest']['seat_id']} ${p['plans']['cheapest']['usd']})")
    check(p["plans"]["fastest"]["seat_id"] == "do-h100-nyc2", f"30B: fastest is the H100 ({p['plans']['fastest']['seat_id']} {fmt_s(p['plans']['fastest']['wall_s'])})")
    check(all(c["success_probability"] is not None for c in p["plans"].values()), "30B: every plan carries a success probability")
    check("grader" in (k30["evaluator"]["needs_seat_role"]) and set(p["grader_seats"]) >= {"estate-w01-cpu"}, f"30B: grader seats found ({p['grader_seats']})")

    # 3. 30B coding after the 3090s free up (09-29, 2 h): estate 3090 feasible via gguf-q4 and is cheapest (energy), cloud fastest
    p = plan(k30, seats, obs, start_at=parse_iso("2026-09-29T10:00:00Z"))
    check("estate-w01-3090" in p["feasible_seats"], f"30B 09-29: W01 3090 feasible ({p['feasible_seats']})")
    c = p["plans"]["cheapest"]
    check(c["seat_id"] == "estate-w01-3090" and "NOT metered" in c["cost_basis"], f"30B 09-29: cheapest is the estate 3090 on assumed energy ({c['seat_id']} ${c['usd']}), flagged not metered")
    e3090 = [x for x in p["feasible_detail"]["estate-w01-3090"]["plans"]]
    check(all("ASSUMED" in x["seconds_per_traversal_basis"] for x in e3090), "30B 09-29: estate 3090 timing carries an ASSUMED basis (no 30B curve on that seat)")

    # 4. Impossible deadline: everything refused with written reasons, exit code path
    k = json.loads(json.dumps(k30)); k["deadline_s"] = 60
    p = plan(k, seats, obs)
    check(p["refused"] and all("exceeds the deadline" in " ".join(v) for sid, v in p["infeasible"].items() if sid in ("hotaisle-mi300x-1x-enc1", "do-h100-nyc2")), "60 s deadline: refused, cloud seats say 'traversal time exceeds the deadline'")
    # 5. Budget refusal
    k = json.loads(json.dumps(k30)); k["policy"]["max_usd"] = 0.10
    p = plan(k, seats, obs)
    check(p["refused"] and "exceeds the Knot's max_usd" in " ".join(p["infeasible"].get("do-h100-nyc2", [])), "max_usd $0.10: refused with the cost written")
    # 6. Missing grader role
    k = json.loads(json.dumps(k30)); k["evaluator"]["needs_seat_role"] = "notary"
    p = plan(k, seats, obs)
    check(p["refused"] and "grader role" in p["refusal_reasons"][0], "evaluator needing an unknown role: refused with reason")
    # 7. Estate arm Knot (gpt-oss-120B Q2, does not fit a 3090): refused while busy, planned on the measured split curve after 09-28
    ke = json.load(open(os.path.join(HERE, "fixtures", "knots", "knot-estate-arm-120b.json"), encoding="utf-8"))
    p = plan(ke, seats, obs)
    r = " ".join(p["infeasible"].get("estate-w01-3090", []))
    check("declared busy until 2026-09-28" in r and "feasible" in r, "estate arm 09-24: W01 3090 refused as busy, memory verdict still written")
    p = plan(ke, seats, obs, start_at=parse_iso("2026-09-29T10:00:00Z"))
    check(p["feasible_seats"] == ["estate-w01-3090"], f"estate arm 09-29: only the W01 3090 is feasible ({p['feasible_seats']})")
    c = p["plans"]["fastest"]
    check(c["mode"] == "split" and c["path"] == "split-vram-ram" and "SPLIT" in c["seconds_per_traversal_basis"], "estate arm: plan names the split-vram-ram path, not streaming")
    d1 = [x for x in p["feasible_detail"]["estate-w01-3090"]["plans"] if x["depth"] == 1][0]
    check(abs(d1["seconds_per_traversal"] - 0.0804) < 1e-6 and abs(d1["work_s"] - 164 * 301 * 0.0804) < 1, f"estate arm depth 1: {d1['traversals']} traversals x 0.0804 s = {fmt_s(d1['work_s'])} from the B1 receipt")
    check(all("extrapolated" in x["seconds_per_traversal_basis"] for x in p["feasible_detail"]["estate-w01-3090"]["plans"] if x["depth"] > 1), "estate arm depths 4/16: flagged as extrapolated beyond the measured depth")

    # 8. Interpolation sanity
    s, how = interp([{"depth": 1, "seconds": 1.0}, {"depth": 8, "seconds": 2.0}], 4)
    check(abs(s - 1.4286) < 1e-3 and how == "interpolated", "interp: linear between measured depths")
    s, how = interp([{"depth": 1, "seconds": 1.0}, {"depth": 8, "seconds": 2.0}], 32)
    check("extrapolated" in how and s == 4.0, "interp: extrapolation flagged beyond measured depth")
    print(f"waterline selftest: {'all passed' if ok else 'FAILURES'}")
    return ok


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--selftest":
        return 0 if selftest() else 1
    if argv[0] == "check-seats":
        path = argv[1] if len(argv) > 1 else DEFAULT_SEATS
        errs = check_seats(json.load(open(path, encoding="utf-8")))
        print("seats.json: clean" if not errs else "\n".join(errs)); return 0 if not errs else 1
    if argv[0] == "plan":
        args = argv[1:]
        knot_path = args[0]
        seats_path, avail_path, start_at, out_json = DEFAULT_SEATS, DEFAULT_AVAIL, None, None
        i = 1
        while i < len(args):
            if args[i] == "--seats": seats_path = args[i + 1]; i += 2
            elif args[i] == "--availability": avail_path = args[i + 1]; i += 2
            elif args[i] == "--start-at": start_at = parse_iso(args[i + 1]); i += 2
            elif args[i] == "--json": out_json = args[i + 1]; i += 2
            else: print(f"unknown arg {args[i]}"); return 1
        knot = json.load(open(knot_path, encoding="utf-8"))
        seats = json.load(open(seats_path, encoding="utf-8"))["seats"]
        obs = load_jsonl(avail_path)
        p = plan(knot, seats, obs, start_at=start_at)
        print(render(p))
        if out_json:
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=1)
        return 2 if p["refused"] else 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
