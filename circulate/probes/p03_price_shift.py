"""p03: +10% Hot Aisle price in a copy of one snapshot; economics recompute moves cost per 1k by the ratio, comparator unchanged."""
import json
import shutil
from _common import *  # noqa

NAME = "p03_price_shift"
RETAINED = lane("lanes", "opencomputeprices", "price-history")
ARM_FILES = ["detailed.json", "grade/evaluation.json", "ledger-times.json", "closure.json"]
ARMS = ["run3-scored-a-t0", "run3-scored-n-t0"]


def economics(tree):
    rc, out, err = run_cmd(["node", tree / "campaign/market/economics_by_date.cjs"], cwd=tree, timeout=180)
    need(rc == 0, "economics_by_date.cjs failed: " + (err or out)[:400])
    rows = [json.loads(x) for x in (tree / "campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["date"]: r for r in rows if r["kind"] == "dated"}, [r for r in rows if r["kind"] == "as_run_reference"][0]


def body(ctx, work):
    root = ctx_root(ctx)
    ha = root / "hot-aisle"
    idx = json.loads((ha / "data/price-history/INDEX.json").read_text(encoding="utf-8"))
    ha_days = [f["date"] for f in idx["providers"]["hot_aisle"]["files"]]
    do_days = {f["date"] for f in idx["providers"]["digitalocean"]["files"]}
    common = [d for d in reversed(ha_days) if d in do_days][:6]
    need(common, "INDEX lists no day with both Hot Aisle and DigitalOcean files")
    src_dir = Path(ctx.get("price_history_dir") or RETAINED)
    constructed_from_index = False   # True: snapshots rebuilt from RUN3-ECONOMICS-BY-DATE.jsonl rows
    tree = work / "hot-aisle"
    (tree / "campaign/market").mkdir(parents=True)
    for n in ("economics_by_date.cjs", "run3_engine_accept.cjs"):
        shutil.copy2(ha / "campaign/market" / n, tree / "campaign/market" / n)
    shutil.copy2(ha / "index.html", tree / "index.html")
    for arm in ARMS:
        for f in ARM_FILES:
            dst = tree / "campaign/results" / arm / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ha / "campaign/results" / arm / f, dst)
    ph = tree / "data/price-history"
    used = []
    for d in common:
        a, b = src_dir / "hot_aisle" / (d + ".json"), src_dir / "digitalocean" / (d + ".json")
        if a.is_file() and b.is_file():
            for prov, s in (("hot_aisle", a), ("digitalocean", b)):
                (ph / prov).mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, ph / prov / (d + ".json"))
            used.append(d)
    if not used:
        # Retained per-day files absent: build a minimal snapshot per day from the dated rows the repo already carries
        # (RUN3-ECONOMICS-BY-DATE.jsonl holds the Hot Aisle and comparator $/GPU-hr that economics_by_date.cjs selected for each day).
        # Nothing is invented: each snapshot restates those recorded rates in the product shape the script reads.
        rows = {}
        for ln in (ha / "campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                if r.get("kind") == "dated":
                    rows[r["date"]] = r
        for d in common:
            r = rows.get(d)
            if not r or r.get("hot_aisle_gpu_hour") is None or r.get("comparator_gpu_hour") is None:
                continue
            ts = d + "T00:00:00Z"
            ha_prod = [{"gpu": "MI300X", "gpu_count": 1, "price_type": "on_demand", "hourly_price_usd": r["hot_aisle_gpu_hour"],
                        "source": r.get("hot_aisle_price_source"), "snapshot_ts": ts}]
            cmp_src = r.get("comparator_all_source_values") or {r.get("comparator_source"): r["comparator_gpu_hour"]}
            cmp_prod = [{"gpu": "H100", "gpu_count": 1, "price_type": "on_demand", "hourly_price_usd": v, "source": k, "snapshot_ts": ts}
                        for k, v in cmp_src.items()]
            write_json(ph / "hot_aisle" / (d + ".json"), {"products": ha_prod})
            write_json(ph / "digitalocean" / (d + ".json"), {"products": cmp_prod})
            used.append(d)
            constructed_from_index = True
    if not used:
        # Retained per-day files absent: nothing to construct a price from (INDEX carries counts and hashes, not prices).
        return {"status": "SKIP", "observed": {"retained_dir": str(src_dir), "candidate_days": common},
                "expected": "a retained per-day snapshot for Hot Aisle and DigitalOcean",
                "notes": "Retained per-day files are absent and RUN3-ECONOMICS-BY-DATE.jsonl has no usable dated row for the candidate days; a snapshot cannot be constructed without inventing values."}
    trimmed = json.loads(json.dumps(idx))
    trimmed["providers"]["hot_aisle"]["files"] = [f for f in trimmed["providers"]["hot_aisle"]["files"] if f["date"] in used]
    write_json(ph / "INDEX.json", trimmed)
    # hash check against INDEX for the files we use (the snapshot must be the bytes INDEX describes)
    hash_ok = {}
    for prov in ("hot_aisle", "digitalocean"):
        want = {f["date"]: f["sha256"] for f in idx["providers"][prov]["files"]}
        for d in used:
            hash_ok["%s/%s" % (prov, d)] = sha256_file(ph / prov / (d + ".json")) == want[d]
    base, ref = economics(tree)
    day = next((d for d in used if base[d]["cost_per_1k_accepted_hot_aisle"] is not None and base[d]["cost_per_1k_accepted_comparator"] is not None), None)
    need(day, "no usable baseline day among %s" % used)
    b = base[day]
    snap_path = ph / "hot_aisle" / (day + ".json")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    n_shift = 0
    for p in snap["products"]:
        if p.get("hourly_price_usd") is not None:
            p["hourly_price_usd"] = round(p["hourly_price_usd"] * 1.1, 10)
            n_shift += 1
    need(n_shift, "no priced products to shift")
    snap_path.write_text(json.dumps(snap), encoding="utf-8")
    shifted, ref2 = economics(tree)
    s = shifted[day]
    ratio_rate = s["hot_aisle_gpu_hour"] / b["hot_aisle_gpu_hour"]
    ratio_cost = s["cost_per_1k_accepted_hot_aisle"] / b["cost_per_1k_accepted_hot_aisle"]
    need(abs(ratio_rate - 1.1) < 1e-9, "Hot Aisle rate ratio %r != 1.1" % ratio_rate)
    tol = 1.1e-4   # both figures are rounded to 4 dp by the script
    need(abs(s["cost_per_1k_accepted_hot_aisle"] - b["cost_per_1k_accepted_hot_aisle"] * 1.1) <= tol,
         "cost per 1k did not scale by 1.1: %r -> %r" % (b["cost_per_1k_accepted_hot_aisle"], s["cost_per_1k_accepted_hot_aisle"]))
    for k in ("comparator_gpu_hour", "cost_per_1k_accepted_comparator", "comparator_source"):
        need(s[k] == b[k], "comparator field %s changed: %r -> %r" % (k, b[k], s[k]))
    need(ref == ref2 or {k: v for k, v in ref.items()} == {k: v for k, v in ref2.items()}, "as-run reference row changed")
    need(s["source_sha256"]["hot_aisle_price_file"] != b["source_sha256"]["hot_aisle_price_file"], "shifted file hash not recorded")
    need(s["source_sha256"]["comparator_price_file"] == b["source_sha256"]["comparator_price_file"], "comparator file hash changed")
    return {
        "observed": {"day": day, "hot_aisle_gpu_hour": [b["hot_aisle_gpu_hour"], s["hot_aisle_gpu_hour"]],
                     "cost_per_1k_hot_aisle": [b["cost_per_1k_accepted_hot_aisle"], s["cost_per_1k_accepted_hot_aisle"]],
                     "cost_ratio_from_rounded_4dp": round(ratio_cost, 6), "rate_ratio": round(ratio_rate, 10),
                     "comparator_gpu_hour": [b["comparator_gpu_hour"], s["comparator_gpu_hour"]],
                     "cost_per_1k_comparator": [b["cost_per_1k_accepted_comparator"], s["cost_per_1k_accepted_comparator"]],
                     "products_shifted": n_shift, "days_in_temp_tree": used,
                     "snapshot_bytes_match_INDEX_sha256": all(hash_ok.values()),
                     "snapshot_source": ("dated rows of hot-aisle/campaign/market/RUN3-ECONOMICS-BY-DATE.jsonl (retained per-day files absent)" if constructed_from_index else "retained per-day files: " + str(src_dir)),
                     "constructed_from_dated_rows": constructed_from_index},
        "expected": "Hot Aisle cost per 1k = baseline x 1.1 (to the script's 4-decimal rounding); comparator fields byte-identical",
        "notes": "economics_by_date.cjs run unmodified inside a temp copy of the tree it expects (index.html engine, the two Run 3 arms' result files, one price-history day). "
                 "The script rounds costs to 4 decimals, so the cost ratio is exact only to that rounding (tolerance 1.1e-4); the rate ratio is exact.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
