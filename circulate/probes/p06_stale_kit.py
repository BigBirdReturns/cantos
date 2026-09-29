"""p06: edit a kit source in a temp copy of hot-aisle/; build_kit --check must fail; a rebuild must pass."""
import shutil
from _common import *  # noqa

NAME = "p06_stale_kit"


def body(ctx, work):
    root = ctx_root(ctx)
    ha = root / "hot-aisle"
    real_before = {n: sha256_file(ha / n) for n in ("MANIFEST.json", "workload-report.zip", "README.md")}
    tmp = work / "hot-aisle"
    # everything the kit builds from, without the multi-hundred-MB campaign tree
    shutil.copytree(ha, tmp, ignore=shutil.ignore_patterns("campaign", "__pycache__", "node_modules", ".git"))
    build = tmp / "scripts" / "build_kit.py"

    def kit(*a):
        return run_cmd(["python", build, *a], cwd=tmp, timeout=180)

    real_state = run_cmd(["python", ha / "scripts" / "build_kit.py", "--check"], cwd=ha, timeout=180)
    rc0, out0, _ = kit("--check")
    baseline_note = "temp copy matches its source" if rc0 == 0 else "temp copy was stale before the edit (real kit %s); rebuilt first" % ("stale" if real_state[0] else "current")
    if rc0 != 0:
        rcb, ob, eb = kit()
        need(rcb == 0, "baseline rebuild failed: " + (eb or ob)[:200])
        rc0, out0, _ = kit("--check")
    need(rc0 == 0, "baseline --check does not pass after a rebuild: " + out0[:200])
    readme = tmp / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\n<!-- probe edit: this line is not in the committed kit -->\n")
    rc1, out1, err1 = kit("--check")
    need(rc1 == 1 and "KIT STALE" in out1, "--check did not fail on an edited kit source: rc=%s %r" % (rc1, out1[:200]))
    need("MANIFEST.json differs" in out1 and "workload-report.zip differs" in out1, "stale report did not name both manifest and archive: %r" % out1)
    rc2, out2, err2 = kit()
    need(rc2 == 0, "rebuild failed: " + (err2 or out2)[:200])
    rc3, out3, _ = kit("--check")
    need(rc3 == 0, "--check still failing after rebuild: " + out3[:200])
    real_after = {n: sha256_file(ha / n) for n in real_before}
    need(real_before == real_after, "real kit files changed")
    return {
        "observed": {"baseline_check": {"exit": rc0, "message": out0.strip()}, "after_edit_check": {"exit": rc1, "message": out1.strip()},
                     "rebuild": {"exit": rc2, "message": out2.strip()}, "after_rebuild_check": {"exit": rc3, "message": out3.strip()},
                     "real_kit_check_exit": real_state[0], "real_kit_files_unchanged": True},
        "expected": "--check exits 1 with 'KIT STALE' naming MANIFEST.json and workload-report.zip after the edit; rebuild then --check exits 0",
        "notes": baseline_note + ". The edit appends one comment line to README.md (an INCLUDE file) in a temp copy that excludes hot-aisle/campaign; the real kit was checked read-only.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
