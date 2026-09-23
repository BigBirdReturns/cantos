"""Compare imported summaries to retained campaign cells without qualifying results."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
from importer import BASE, UNKNOWN, digest, hardware, model_class, number, precision, self_test, stamp

ARMS = {"do-h100": "H100", "hotaisle-mi300x": "MI300X",
        "run2-hotaisle-mi300x": "MI300X", "run2-explore-hotaisle-mi300x": "MI300X"}


def measured_cells(root):
    cells = []
    for arm, gpu in ARMS.items():
        folder = Path(root) / arm
        if not folder.exists():
            continue
        envpath = folder / "env.normalized.json"
        if not envpath.exists():
            envpath = folder / "env.json"
        envraw = envpath.read_bytes()
        env = json.loads(envraw)
        logpath = folder / "serve.log"
        log = logpath.read_text(encoding="utf-8") if logpath.exists() else ""
        backend = UNKNOWN
        if arm.startswith("run2"):
            # Do not confuse the HTTP bench backend 'openai' with attention selection.
            patterns = re.findall(r"(?:Using |Overriding with )(ROCM_AITER_FA|ROCM_ATTN)\b", log)
            backend = patterns[-1] if patterns else UNKNOWN
        for path in sorted(folder.glob("cell-*.json")):
            raw = path.read_bytes()
            d = json.loads(raw)
            profile = dict(re.findall(r"(in|out)=(\d+)", d.get("load_profile", "")))
            shape = d.get("shape")
            lengths = (8192, 512) if shape == "long" else (2048, 256) if shape == "short" else (None, None)
            inp, output = int(profile.get("in", lengths[0])) if profile.get("in", lengths[0]) else None, int(profile.get("out", lengths[1])) if profile.get("out", lengths[1]) else None
            cells.append({"id": arm + "/" + path.name, "tier": "measured", "hardware": gpu,
                          "hardware_evidence": "env.normalized.json" if "run2" not in arm else "run2/PREREG.md and DISCLOSURES.md; env.gpu is N/A",
                          "gpus": env.get("gpus", 1), "model": d["model_id"], "model_class": model_class(d["model_id"]),
                          "precision": precision(d.get("precision", UNKNOWN)), "precision_detail": d.get("precision", UNKNOWN),
                          "framework": "vllm", "framework_version": env.get("vllm_version", UNKNOWN),
                          "model_revision": env.get("revision", UNKNOWN), "image_digest": env.get("image", UNKNOWN),
                          "backend": backend, "config": {"serve_flags": env.get("serve_flags", UNKNOWN), "env": env.get("env", UNKNOWN),
                                                          "cache_policy": d.get("cache_policy", UNKNOWN)},
                          "workload": {"input_tokens": inp, "output_tokens": output, "concurrency": d.get("max_concurrency"),
                                       "dataset": "random", "scenario": "fixed-sequence", "request_rate": d.get("request_rate")},
                          "gates": {"ttft_ms": 3000 if shape == "long" else 1000, "e2e_ms": 40000 if shape == "long" else 15000,
                                    "failed_pct": 1, "basis": "registered cell gates; ratios use raw metrics"},
                          "posthoc": "explore" in arm, "raw": d,
                          "provenance": {"path": str(path), "sha256": digest(raw), "environment_sha256": digest(envraw),
                                         "serve_log_sha256": digest(logpath.read_bytes()) if logpath.exists() else None}})
    if not cells:
        raise ValueError("no supported campaign cells found")
    return cells


def measured_metric(cell, metric):
    name, units = metric["name"], metric["units"]
    mappings = {"request_throughput": ("requests/s", "request_throughput", 1),
                "output_throughput": ("tokens/s", "output_throughput", 1),
                "output_throughput_per_gpu": ("tokens/s/GPU", "output_throughput", cell["gpus"]),
                "total_token_throughput_per_gpu": ("tokens/s/GPU", "total_token_throughput", cell["gpus"]),
                "p95_ttft_ms": ("ms", "p95_ttft_ms", 1), "median_ttft_ms": ("ms", "median_ttft_ms", 1),
                "median_tpot_ms": ("ms", "median_tpot_ms", 1)}
    if name not in mappings:
        return None
    expected, key, denominator = mappings[name]
    value = cell["raw"].get(key)
    return number(value) / number(denominator, True) if units == expected and value is not None else None


def compare(imported, cell):
    blockers, caveats = [], []
    for key in ("hardware", "gpus", "precision"):
        a, b = imported.get(key), cell.get(key)
        if a in (None, UNKNOWN) or a != b:
            blockers.append(key + " differs or is unknown")
    if imported.get("model") != cell["model"]:
        if imported.get("model_class") and imported["model_class"] == cell["model_class"]:
            caveats.append("model class only; checkpoints/architectures may differ")
        else:
            blockers.append("model/model class differs or is unknown")
    for key in ("input_tokens", "output_tokens", "concurrency", "scenario"):
        a, b = imported.get("workload", {}).get(key), cell["workload"].get(key)
        if a in (None, UNKNOWN) or a != b:
            blockers.append(key + " differs or is unknown")
    for key in ("framework", "framework_version", "backend", "model_revision", "image_digest", "precision_detail", "config", "gates"):
        a, b = imported.get(key), cell.get(key)
        if a in (None, UNKNOWN) or b in (None, UNKNOWN) or a != b:
            caveats.append(key + " differs or is UNVERIFIED")
    for key in ("dataset", "request_rate"):
        a, b = imported.get("workload", {}).get(key), cell["workload"].get(key)
        if a in (None, UNKNOWN) or a != b:
            caveats.append(key + " differs or is UNVERIFIED")
    if cell["posthoc"]:
        caveats.append("our cell is post-hoc exploration; one repeat, reused seed")
    caveats.append("raw performance only; no correctness, accepted work, acquisition cost or traversal equivalence")
    if imported.get("comparison_hold"):
        blockers.append(imported["comparison_hold"])
    ours = measured_metric(cell, imported["metric"])
    if ours is None:
        blockers.append("metric semantics/units unsupported")
    theirs = number(imported["metric"]["value"])
    if theirs == 0:
        blockers.append("zero source denominator")
    return blockers, caveats, ours


def report(imports, cells, as_of, allow_fixtures=False):
    gaps, checkpoints, seen = [], [], set()
    for r in imports:
        if r.get("schema") != "imported-observation@1" or r.get("tier") != "imported":
            raise ValueError("delta accepts imported-observation@1 only")
        if r.get("fixture") and not allow_fixtures:
            raise ValueError("fixture input requires --allow-fixtures; never publish fixture ratios")
        if r["id"] in seen:
            raise ValueError("duplicate observation id")
        seen.add(r["id"])
        matches, nearest = [], None
        for c in cells:
            blockers, caveats, ours = compare(r, c)
            if nearest is None or len(blockers) < len(nearest[0]):
                nearest = (blockers, c["id"])
            if blockers:
                continue
            ratio = ours / number(r["metric"]["value"], True)
            match = {"imported_id": r["id"], "measured_cell": c["id"], "ours_div_theirs": ratio,
                     "ours": ours, "theirs": r["metric"]["value"], "metric": r["metric"]["name"], "units": r["metric"]["units"],
                     "interpretation": "lower is faster" if r["metric"]["units"] == "ms" else "higher is faster",
                     "comparison": "contextual; not a reproduction", "not_like_for_like": caveats,
                     "fixture": r.get("fixture", False), "imported_provenance": r["provenance"], "measured_provenance": c["provenance"]}
            matches.append(match)
            gaps.append(match)
        reasons, score = [], 0
        if any(r.get("hardware") == c["hardware"] for c in cells):
            reasons.append("hardware already measured (+20)"); score += 20
        if r.get("model_class") and any(r["model_class"] == c["model_class"] for c in cells):
            reasons.append("model class already measured (+20)"); score += 20
        if matches:
            reasons.append("matching shape/precision/concurrency (+20)"); score += 20
            if any(abs(m["ours_div_theirs"] - 1) > .20 for m in matches):
                reasons.append("absolute ratio gap exceeds 20% (+30)"); score += 30
            if any("framework_version differs or is UNVERIFIED" in m["not_like_for_like"] or "backend differs or is UNVERIFIED" in m["not_like_for_like"] for m in matches):
                reasons.append("runtime/backend verification needed (+10)"); score += 10
        observed = r.get("observed_at")
        if observed:
            age = (as_of - stamp(observed).date()).days
            if age < 0:
                raise ValueError("observation is after --as-of")
            if age >= 90:
                reasons.append("checkpoint at least 90 days old (+10)"); score += 10
        else:
            age = None
            reasons.append("measurement date UNVERIFIED; retrieval date is not measurement age")
        if not matches:
            reasons.append("no comparable cell; fill metadata or design new workload first")
        checkpoints.append({"imported_id": r["id"], "source": r["source"], "provenance": r["provenance"],
                            "hardware": r.get("hardware"), "model": r.get("model"), "metric": r["metric"],
                            "reproduced": False, "score": score, "rank_reasons": reasons, "age_days": age,
                            "comparison_count": len(matches), "nearest_cell": nearest[1] if nearest else None,
                            "blockers": nearest[0] if nearest and not matches else [], "fixture": r.get("fixture", False)})
    checkpoints.sort(key=lambda c: (-c["score"], c["imported_id"]))
    for i, checkpoint in enumerate(checkpoints, 1):
        checkpoint["rank"] = i
    return {"schema": "backfill-delta@1", "as_of": as_of.isoformat(), "measured_cells": len(cells),
            "imported_source_rows": len({(r["provenance"]["sha256"], r["provenance"].get("artifact_id"), r["row_index"]) for r in imports}),
            "comparable_observations": len({g["imported_id"] for g in gaps}),
            "comparable_source_rows": len({(r["provenance"]["sha256"], r["provenance"].get("artifact_id"), r["row_index"])
                                            for r in imports if r["id"] in {g["imported_id"] for g in gaps}}),
            "imported_observations": len(imports), "fixture": any(r.get("fixture", False) for r in imports),
            "notice": "Contextual raw gaps and rerun candidates only. No imported checkpoint is certified reproduced by these campaign cells.",
            "gaps": gaps, "unreproduced": checkpoints}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--imports", type=Path)
    p.add_argument("--results", type=Path, default=BASE.parent / "results")
    p.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    p.add_argument("--output", type=Path)
    p.add_argument("--allow-fixtures", action="store_true")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not a.imports:
        p.error("--imports required")
    try:
        imports = [json.loads(line) for line in a.imports.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if not imports:
            raise ValueError("empty imports")
        result = report(imports, measured_cells(a.results), a.as_of, a.allow_fixtures)
        content = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if a.output:
            a.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("delta failed: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
