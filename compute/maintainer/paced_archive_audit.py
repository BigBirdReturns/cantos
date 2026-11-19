#!/usr/bin/env python3
"""Read-only, source-bound replay of paired paced inference and external grades.

The ZIP is data, never executable code. Board energy is attributed to the pinned
native notice and is not silently promoted to independently metered facility power.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile


class AuditError(ValueError):
    pass


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise AuditError("invalid nonnegative " + label)
    return value


def _key(row):
    return row["task_id"], row["trial"], row["repetition"]


def _json(files, name):
    try:
        return json.loads(files[name])
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise AuditError("unreadable artifact: " + name) from exc


def _check_entries(files, entries, prefix):
    for item in entries:
        name = prefix + item["path"]
        raw = files.get(name)
        if raw is None or len(raw) != item["bytes"] or _hash(raw) != item["sha256"]:
            raise AuditError("source artifact mismatch: " + name)


def _open_archive(path, expected_sha256):
    archive = Path(path)
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise AuditError("expected SHA-256 must be a lowercase hex digest")
    if archive.stat().st_size > 64 * 1024 * 1024:
        raise AuditError("compressed archive size limit")
    if _hash(archive.read_bytes()) != expected_sha256:
        raise AuditError("archive SHA-256 mismatch")
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)) or not 2 <= len(names) <= 1200:
            raise AuditError("duplicate or excessive ZIP members")
        if sum(i.file_size for i in infos) > 64 * 1024 * 1024:
            raise AuditError("uncompressed budget exceeded")
        for item in infos:
            parts = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (not item.filename or item.filename.startswith("/") or "\\" in item.filename
                    or any(p in ("", ".", "..") for p in item.filename.split("/"))
                    or item.is_dir() or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or item.file_size > 16 * 1024 * 1024):
                raise AuditError("unsafe ZIP member")
        files = {i.filename: z.read(i) for i in infos}
    manifest = _json(files, "comparison.json")
    if manifest.get("schema") != "cantos.comparison-bundle/1":
        raise AuditError("unknown comparison bundle")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise AuditError("missing byte manifest")
    listed = [r["path"] for r in records]
    if len(listed) != len(set(listed)) or set(listed) | {"comparison.json"} != set(files):
        raise AuditError("ZIP member manifest mismatch")
    _check_entries(files, records, "")
    return files, manifest


def _arm(files, manifest, arm):
    prefix = arm + "/"
    gprefix = arm + "_grades/"
    try:
        run_name = manifest["inputs"][arm]
        grade_name = manifest["inputs"][arm + "_grades"]
    except KeyError as exc:
        raise AuditError("missing arm input") from exc
    if run_name != prefix + "run.json" or grade_name != gprefix + "grades.json":
        raise AuditError("noncanonical paired input")
    run, grade = _json(files, run_name), _json(files, grade_name)
    if (run.get("schema") != "cantos.maintainer.run/1" or run.get("arm") != arm
            or grade.get("schema") != "cantos.maintainer.grades/1"
            or grade.get("run_sha256") != _hash(files[run_name])):
        raise AuditError(arm + ": grade/capture identity")
    _check_entries(files, run["artifacts"], prefix)
    _check_entries(files, grade["artifacts"], gprefix)
    if grade.get("workload_sha256") != _hash(files[prefix + "workload.json"]):
        raise AuditError(arm + ": workload hash mismatch")
    mapping = _json(files, gprefix + "artifacts/mapping.json")
    evaluations = _json(files, gprefix + "artifacts/humaneval_eval_results.json")["eval"]
    observations = run["observations"]
    if not isinstance(mapping, list) or len(mapping) != len(observations):
        raise AuditError(arm + ": observation/mapping population mismatch")
    indexed = {}
    for m in mapping:
        key = _key(m)
        idx = m["observation_index"]
        if (key in indexed or type(idx) is not int or not 0 <= idx < len(observations)
                or not m.get("capture_eligible")):
            raise AuditError(arm + ": duplicate or invalid mapping")
        obs = observations[idx]
        if _key(obs) != key or obs.get("warmup"):
            raise AuditError(arm + ": mapping/raw observation mismatch")
        if not any(
            isinstance(a.get("response_text"), str)
            and _hash(a["response_text"].encode("utf-8")) == m["response_sha256"]
            and a.get("response_sha256") == m["response_sha256"]
            for a in obs.get("attempts", [])
        ):
            raise AuditError(arm + ": grade response not present in capture")
        samples = evaluations.get(m["task_id"])
        sample_index = m["task_solution_index"]
        if (not isinstance(samples, list) or type(sample_index) is not int
                or not 0 <= sample_index < len(samples)):
            raise AuditError(arm + ": evaluator sample missing")
        ev = samples[sample_index]
        if (ev["task_id"] != m["task_id"]
                or _hash(ev["solution"].encode("utf-8")) != m["solution_sha256"]):
            raise AuditError(arm + ": evaluator source changed")
        indexed[key] = (m, ev)
    accepted = {}
    for row in grade["results"]:
        key = _key(row)
        if key in accepted or key not in indexed or type(row.get("accepted")) is not bool:
            raise AuditError(arm + ": invalid grade record")
        m, ev = indexed[key]
        base, plus = ev.get("base_status"), ev.get("plus_status")
        if (base not in ("pass", "fail") or plus not in ("pass", "fail")
                or row["response_sha256"] != m["response_sha256"]
                or row["accepted"] != (base == "pass" and plus == "pass")):
            raise AuditError(arm + ": evaluator verdict contradiction")
        accepted[key] = row["accepted"]
    if len(accepted) != len(indexed):
        raise AuditError(arm + ": unmatched graded population")
    return accepted, grade["workload_sha256"], run["pairing"]


def audit_archive(path, expected_sha256):
    files, manifest = _open_archive(path, expected_sha256)
    base, b_work, b_pair = _arm(files, manifest, "baseline")
    cand, c_work, c_pair = _arm(files, manifest, "candidate")
    if set(base) != set(cand) or b_work != c_work or b_pair != c_pair:
        raise AuditError("unmatched paired workload/trial identity")
    original = _json(files, manifest["original_analysis"])
    notice = _json(files, "notices/ANALYSIS.json")
    if (original.get("schema") != "cantos.maintainer.verdict/1"
            or original.get("exit_code") != 0 or original.get("verdict") != "pass"
            or notice.get("schema") != "cantos.private-paced-analysis/1"
            or notice.get("native_verdict") != "pass"):
        raise AuditError("native verdict not accepted")
    contingency = {"both_accepted": 0, "baseline_only": 0,
                   "candidate_only": 0, "neither_accepted": 0}
    for k in base:
        contingency["both_accepted" if base[k] and cand[k] else
                    "baseline_only" if base[k] else
                    "candidate_only" if cand[k] else "neither_accepted"] += 1
    measured = {}
    for arm, grades in (("baseline", base), ("candidate", cand)):
        count = sum(grades.values())
        native = original[arm]
        energy = notice["board_energy"][arm]
        if (native["accepted_tasks"] != count or native["attempts"] != len(grades)
                or energy["accepted_tasks"] != count or energy.get("status") != "aligned"):
            raise AuditError(arm + ": native outcome/energy population disagreement")
        joules = _number(energy["joules"], arm + " joules")
        seconds = _number(energy["measured_duration_s"], arm + " measured duration")
        if count == 0 or seconds == 0:
            raise AuditError("accepted-work denominator or timing is zero")
        if not math.isclose(energy["joules_per_accepted"], joules/count, rel_tol=1e-10):
            raise AuditError(arm + ": joules/accepted inconsistency")
        measured[arm] = {"observed_attempts": len(grades), "accepted": count,
                         "gpu_board_joules": joules, "joules_per_accepted": joules/count,
                         "measured_trial_window_seconds": seconds}
    return {
        "schema": "cantos.paced-archive-replay/1",
        "status": "verified",
        "archive_sha256": expected_sha256,
        "workload_sha256": b_work,
        "native_analysis_sha256": _hash(files["original-analysis.json"]),
        "paced_notice_sha256": _hash(files["notices/ANALYSIS.json"]),
        "paired_attempts": len(base), "contingency": contingency,
        "arms": measured,
        "candidate_minus_baseline_gpu_board_joules":
            measured["candidate"]["gpu_board_joules"] - measured["baseline"]["gpu_board_joules"],
        "boundary": "Independent data-only archive, grader, capture and population replay; energy values are hash-bound to the original native analysis, not independently re-integrated power telemetry. Gross GPU-board trial windows only. No facility-wide or production cost claim. No inference or grading executed.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        result = audit_archive(a.archive, a.sha256)
        data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        if a.out:
            fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        print(json.dumps({"status": "verified", "sha256": _hash(data),
                          "attempts": result["paired_attempts"], "contingency": result["contingency"],
                          "delta_gpu_board_joules": result["candidate_minus_baseline_gpu_board_joules"]}))
        return 0
    except (AuditError, ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "hold", "reason": str(exc)[:500]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
