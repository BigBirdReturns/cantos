"""p07: double one provider's incidents in a temp copy; R2 rho must change, classification recorded, frozen R2 files hash-identical."""
import copy
import importlib.util
import json
import shutil
import sys
from _common import *  # noqa

NAME = "p07_r2_perturb"


def load_r2(retro):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("circ_probe_run_r2", retro / "run_r2.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["circ_probe_run_r2"] = mod
    spec.loader.exec_module(mod)
    return mod


def primary(r2, plan, pm, hot, ratings, inc_dir):
    """The front half of run_r2.evaluate (eligibility per provider, then analyse on the primary measure), skipping the
    pre-declared sensitivity block, which is minutes of bootstrap work and not what this probe perturbs."""
    R = r2.R
    r = R.load_json(ratings)
    window_end = R.parse_date(plan["window_end_date"])
    window_start = window_end - r2.timedelta(days=plan["window_days"])
    provs, included = [], []
    for p in r["providers"]:
        name, tier = p["name"], p["tier"]
        if tier not in plan["ordinal"]:
            continue
        slug = pm.get(name, R.slugify(name))
        entry, _doc = r2.load_provider(name, tier, slug, inc_dir, window_start, window_end, plan, {})
        if entry["status"] == "eligible" and not (name in hot or slug == "hot-aisle"):
            entry["included_in_correlation"] = True
            included.append(entry)
        provs.append(entry)
    need(len(included) >= plan["minimum_providers"], "fewer than the plan minimum of providers are eligible")
    a = r2.analyse(included, plan["primary_measure"], plan)
    return ({"providers": provs, "included_count": len(included), "release": r.get("release")},
            {"rho": a["spearman_rho"], "reading": a["reading"], "bootstrap_95ci": a["bootstrap_95ci"]["interval"],
             "permutation_p": a["permutation"]["p_value"], "n": len(included)})


def body(ctx, work):
    root = ctx_root(ctx)
    retro = root / "clustermax-challenge" / "retrospective"
    r2 = load_r2(retro)
    R = r2.R
    plan = R.load_json(retro / "plan-R2.json")
    pmap = dict(R.load_json(retro / "provider_map.json")); pmap.update(R.load_json(retro / plan["provider_map_r2_file"]))
    hot = set(plan.get("excluded_by_design", []))
    ratings = (retro.parent / plan["ratings_files"]["primary"]).resolve()
    need(ratings.is_file(), "3.0 ratings file missing: %s" % ratings)
    inc = work / "incidents"
    inc.mkdir()
    for f in (retro / "incidents").glob("*.json"):
        shutil.copy2(f, inc / f.name)
    base_out, base = primary(r2, plan, pmap, hot, ratings, inc)
    need(base["rho"] is not None, "baseline rho undefined")
    included = sorted([p for p in base_out["providers"] if p.get("included_in_correlation")],
                      key=lambda p: -p["major_or_critical_incident_count"])
    tried = []
    chosen = None
    for e in included[:6]:
        f = inc / (e["slug"] + ".json")
        orig = f.read_bytes()
        doc = json.loads(orig)
        dup = []
        for i in doc["incidents"]:
            j = copy.deepcopy(i); j["id"] = str(i["id"]) + "-probe-dup"; dup.append(j)
        doc["incidents"] = doc["incidents"] + dup
        f.write_text(json.dumps(doc), encoding="utf-8")
        _, after = primary(r2, plan, pmap, hot, ratings, inc)
        f.write_bytes(orig)   # restore the temp copy before the next candidate
        row = {"provider": e["name"], "slug": e["slug"], "major_or_critical_before": e["major_or_critical_incident_count"],
               "incidents_before": len(doc["incidents"]) // 2, "rho_after": after["rho"], "reading_after": after["reading"],
               "rho_changed": after["rho"] != base["rho"], "reading_changed": after["reading"] != base["reading"]}
        tried.append(row)
        if row["rho_changed"]:
            chosen = dict(row, after=after)
            break
    need(chosen, "doubling any of %d tried providers left rho unchanged (%r)" % (len(tried), [t["provider"] for t in tried]))
    return {
        "observed": {"perturbed_provider": chosen["provider"], "rho_before": base["rho"], "rho_after": chosen["rho_after"],
                     "rho_delta": round(chosen["rho_after"] - base["rho"], 6),
                     "classification_before": base["reading"], "classification_after": chosen["reading_after"],
                     "classification_changed": chosen["reading_changed"],
                     "bootstrap_95ci_before": base["bootstrap_95ci"], "bootstrap_95ci_after": chosen["after"]["bootstrap_95ci"],
                     "permutation_p_before": base["permutation_p"], "permutation_p_after": chosen["after"]["permutation_p"],
                     "included_providers": base["n"], "candidates_tried": tried,
                     "measure": plan["primary_measure"], "release": base_out["release"]},
        "expected": "rho differs after one provider's incident list is doubled; the reading is recorded; frozen R2 files are byte-identical",
        "notes": "run_r2.load_provider and run_r2.analyse (the frozen runner's own functions, imported, not executed; the sensitivity block is skipped) run against a temp copy of retrospective/incidents/*.json; "
                 "duplicates get a '-probe-dup' id suffix. Providers are tried in descending major/critical count until rho moves. Nothing is written to results/.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
