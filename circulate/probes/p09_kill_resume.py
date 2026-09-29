"""p09: start the driver --offline with an injected sleeping stage, kill it, rerun --resume.

Completed stages must be reused by hash, the killed stage re-run, and the receipt complete.
SKIPs with a note when circulate.py does not exist yet.

Environment contract with the driver (CIRCULATE_INJECT_SLEEP_STAGE=<name>:<seconds>):
  the driver appends one extra stage called <name> AFTER all normal stages; its run() sleeps <seconds> and returns OK.
  With seconds == 0 (or the variable unset) it returns OK at once. Its StageResult is recorded like any other.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from _common import *  # noqa

NAME = "p09_kill_resume"
STAGE = "probe_sleep"
SLEEP_S = 120
WAIT_START_S = 120


def stage_records(receipt_dir: Path) -> dict:
    """Every StageResult-shaped dict ({name,status,finished_utc,...}) found in JSON files of a receipt dir, keyed by stage name."""
    found = {}
    files = sorted(receipt_dir.rglob("*.json")) if receipt_dir.is_dir() else []
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        stack = [doc]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if {"name", "status", "finished_utc"} <= set(x) and isinstance(x.get("name"), str) and "observed" not in x:
                    found[x["name"]] = x
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
            elif isinstance(x, list):
                stack.extend(x)
    return found


def dir_hashes(d: Path) -> dict:
    if not d.is_dir():
        return {}
    return {p.relative_to(d).as_posix(): sha256_file(p) for p in sorted(d.rglob("*")) if p.is_file()}


def mentions_stage(day_dir: Path) -> bool:
    if not day_dir.is_dir():
        return False
    for p in day_dir.rglob("*"):
        if p.is_file() and p.stat().st_size < 2_000_000:
            if STAGE in p.name or STAGE in p.read_text(encoding="utf-8", errors="ignore"):
                return True
    return False


def kill_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except Exception:
        pass
    try:
        proc.stdout.close()
    except Exception:
        pass


def porcelain(root, ddir):
    return set(run_cmd(["git", "status", "--porcelain", "--untracked-files=all", "--", str(ddir)], cwd=root)[1].splitlines())


def body(ctx, work):
    driver = Path(ctx.get("circulate_py") or (CIRCULATE / "circulate.py"))
    if not driver.is_file():
        return {"status": "SKIP", "observed": {"driver": str(driver), "exists": False},
                "expected": "circulate.py present so it can be started, killed and resumed",
                "notes": "circulate.py does not exist yet; nothing to kill. Re-run once the driver lands. Assumed env contract: "
                         "CIRCULATE_INJECT_SLEEP_STAGE=%s:%d appends a final stage that sleeps; seconds 0 = no sleep." % (STAGE, SLEEP_S)}
    root = ctx_root(ctx)
    ddir = driver.parent
    receipts = ddir / "receipts"
    today = ctx.get("date") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    day_dir = receipts / today
    sleep_s = int(ctx.get("sleep_seconds", SLEEP_S))
    wait_s = int(ctx.get("wait_start_seconds", WAIT_START_S))
    # Snapshot what the driver may write outside a dated dir, plus today's dated dir, so all of it can be put back.
    saved = work / "saved"
    saved.mkdir()
    touched = {}
    if (receipts / "index.json").is_file():
        touched[receipts / "index.json"] = saved / "receipts-index.json"
    if (ddir / "LATEST.md").is_file():
        touched[ddir / "LATEST.md"] = saved / "LATEST.md"
    for src, dst in touched.items():
        shutil.copy2(src, dst)
    had_day = day_dir.is_dir()
    if had_day:
        shutil.copytree(day_dir, saved / "day")
        shutil.rmtree(day_dir)
    git_before = porcelain(root, ddir)
    retained = work / "retained"
    retained.mkdir()
    e = dict(os.environ)
    e.update({"CIRCULATE_INJECT_SLEEP_STAGE": "%s:%d" % (STAGE, sleep_s), "PYTHONDONTWRITEBYTECODE": "1"})
    obs = {"driver": str(driver), "date": today}
    proc = None
    try:
        t0 = time.time()
        proc = subprocess.Popen([sys.executable, str(driver), "--offline", "--retained", str(retained)], cwd=str(ddir), env=e,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines, seen = [], threading.Event()

        def pump():
            for raw in iter(proc.stdout.readline, b""):
                t = raw.decode("utf-8", "replace").rstrip()
                lines.append(t)
                if STAGE in t:
                    seen.set()
        threading.Thread(target=pump, daemon=True).start()
        started = False
        while time.time() - t0 < wait_s and proc.poll() is None:
            if seen.is_set() or mentions_stage(day_dir):
                started = True
                break
            time.sleep(0.5)
        exited_early = proc.poll() is not None
        time.sleep(1.0)                      # let the stage's 'started' state reach disk
        kill_tree(proc)
        obs["driver_output_tail_before_kill"] = lines[-8:]
        need(started, "the injected stage never started (driver exited early=%s after %.0fs; is CIRCULATE_INJECT_SLEEP_STAGE honoured?)"
             % (exited_early, time.time() - t0))
        killed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        need(day_dir.is_dir(), "killed driver left no receipt directory %s" % day_dir)
        pre = stage_records(day_dir)
        pre_hash = dir_hashes(day_dir)
        done_before = sorted(n for n, r in pre.items() if n != STAGE and r.get("status") in ("OK", "HOLD", "SKIP", "FAIL"))
        obs["stages_recorded_at_kill"] = {n: pre[n]["status"] for n in sorted(pre)}
        obs["receipt_json_present_at_kill"] = (day_dir / "RECEIPT.json").is_file()
        need(done_before, "no completed stage record was on disk when the driver was killed, so reuse cannot be observed (found: %s)" % sorted(pre))
        need(STAGE not in pre or pre[STAGE].get("status") != "OK", "killed stage is recorded OK before it could finish")

        e2 = dict(os.environ)
        e2.update({"CIRCULATE_INJECT_SLEEP_STAGE": "%s:0" % STAGE, "PYTHONDONTWRITEBYTECODE": "1"})
        r = subprocess.run([sys.executable, str(driver), "--offline", "--resume", today, "--retained", str(retained)], cwd=str(ddir), env=e2,
                           capture_output=True, timeout=900)
        obs["resume_exit"] = r.returncode
        obs["resume_output_tail"] = r.stdout.decode("utf-8", "replace").splitlines()[-6:]
        need(r.returncode in (0, 2), "--resume driver error, exit %s: %s" % (r.returncode, r.stderr.decode("utf-8", "replace")[-300:]))
        rj = day_dir / "RECEIPT.json"
        need(rj.is_file(), "no RECEIPT.json after resume")
        receipt = json.loads(rj.read_text(encoding="utf-8"))
        post = stage_records(day_dir)
        stages = receipt.get("stages")
        names = sorted(s.get("name") for s in stages) if isinstance(stages, list) else sorted(stages or [])
        obs["receipt_stage_names"] = names
        need(STAGE in names, "killed stage %s missing from the final receipt" % STAGE)
        missing = [n for n in done_before if n not in names]
        need(not missing, "completed stages dropped from receipt: %s" % missing)
        reused = [n for n in done_before if post.get(n, {}).get("finished_utc") == pre[n]["finished_utc"]]
        rerun = [n for n in done_before if n not in reused]
        obs["reused_by_hash"] = reused
        obs["completed_stages_rerun"] = rerun
        need(not rerun, "completed stages were re-run instead of reused: %s" % rerun)
        after_hash = dir_hashes(day_dir)
        changed = [k for k, v in pre_hash.items()
                   if after_hash.get(k) != v and not k.startswith(("RECEIPT", "PROBES", "index")) and STAGE not in k]
        obs["completed_stage_files_changed"] = changed[:10]
        need(not changed, "files of completed stages changed on resume: %s" % changed[:5])
        s = post.get(STAGE, {})
        obs["killed_stage_after_resume"] = {"status": s.get("status"), "finished_utc": s.get("finished_utc")}
        need(s.get("status") in ("OK", "HOLD", "SKIP"), "killed stage not re-run to completion: %r" % s)
        fin = dt.datetime.strptime(s["finished_utc"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        need(fin >= killed_at, "killed stage's finished_utc predates the kill, so it was not re-run")
        obs["receipt_overall"] = receipt.get("overall")
    finally:
        kill_tree(proc)
        if day_dir.is_dir():
            shutil.rmtree(day_dir, ignore_errors=True)
        if had_day:
            shutil.copytree(saved / "day", day_dir)
        for src, dst in touched.items():
            shutil.copy2(dst, src)
        obs["other_paths_changed_under_circulate"] = sorted(porcelain(root, ddir) - git_before)[:10]
    return {"observed": obs,
            "expected": "after kill: completed stages recorded; after --resume: those stages reused (finished_utc and files unchanged), "
                        "killed stage re-run to completion, RECEIPT.json lists every stage",
            "notes": "Driver run with cwd=circulate/ and --retained in a temp dir; receipts/%s, receipts/index.json and LATEST.md are snapshotted "
                     "first and restored afterwards. Assumed contract with the driver: CIRCULATE_INJECT_SLEEP_STAGE=%s:<seconds> adds a last "
                     "stage that sleeps; per-stage StageResult JSON lands under receipts/<date>/ as it completes; RECEIPT.json has a 'stages' "
                     "list or map." % (today, STAGE)}


def run(ctx=None):
    return execute(NAME, body, ctx)
