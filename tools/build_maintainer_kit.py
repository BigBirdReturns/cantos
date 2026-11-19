"""Build the independent maintainer kit from tracked public source."""
from __future__ import annotations
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "public/open-compute"
ARCHIVE = DEST / "maintainer-kit.zip"
CHECKSUM = DEST / "MAINTAINER-SHA256SUMS.txt"
REQUIRED = (
    "MAINTAINER-START.md", "DELIVERY.md", "DELIVERY.json",
    "AGENTS.md", "CLAUDE.md",
    "app/tests/check_maintainer_evidence.py",
    "app/tests/check_comparison_workbench.py",
    "app/tests/check_deployment_workbench.py",
    "integration/work.py", "integration/task_maintainer.py",
    "integration/WORK.md", "integration/examples/maintainer-work.json",
    "integration/tests/test_maintainer_work.py",
    "integration/tests/test_maintainer_dependency_boundary.py",
    "public/open-compute/open-compute-workbench.zip",
    "public/open-compute/SHA256SUMS.txt",
    "public/open-compute/WORKBENCH-RELEASE.json",
    "hot-aisle/campaign/run3/grade.sh",
    "hot-aisle/campaign/run3/grader.Dockerfile",
    "tools/check_release_promotion.py",
)
PREFIX = "compute/maintainer/"

def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

def build_bytes():
    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0"))
    selected = sorted({p for p in tracked if p.startswith(PREFIX)} | set(REQUIRED))
    missing = [p for p in REQUIRED if p not in tracked or not (ROOT / p).is_file()]
    if missing:
        raise ValueError("Required public source is missing or untracked: " + ", ".join(missing))
    if not any(p.endswith("/maintainer.py") for p in selected):
        raise ValueError("Maintainer producer source is absent")
    # The Git index is the source-of-truth for the shipped bytes. Windows
    # worktree CRLF conversion must not change the reproducible ZIP.
    unstaged = subprocess.run(["git", "diff", "--quiet", "--", *selected], cwd=ROOT)
    if unstaged.returncode:
        raise ValueError("Stage intended maintainer source edits before building the kit")
    files = {}
    for rel in selected:
        path = ROOT / rel
        if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(ROOT.resolve()) is False:
            raise ValueError("Source must be a regular in-tree file: " + rel)
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            raise ValueError("Generated cache cannot enter the public kit: " + rel)
        files[rel] = subprocess.check_output(["git", "show", ":" + rel], cwd=ROOT)
    manifest = {
        "schema": "cantos.maintainer-kit/1",
        "files": {rel: {"sha256": sha256(data).hexdigest(), "bytes": len(data)} for rel, data in files.items()},
        "scope": "Streamed baseline/candidate observations, joined operational and economic decisions, retained reanalysis, bounded data-only transport, explicit external grading and SecondRun retention/invalidation; source examples require explicit serving configuration. Other SecondRun adapters require the full source checkout.",
    }
    manifest["source_tree_sha256"] = sha256(encoded(manifest["files"])).hexdigest()
    files["MAINTAINER-MANIFEST.json"] = encoded(manifest) + b"\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, data in sorted(files.items()):
            info = zipfile.ZipInfo("cantos/" + rel, date_time=(2026, 11, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    content = out.getvalue()
    checksum = (sha256(content).hexdigest() + "  " + ARCHIVE.name + "\n").encode()
    return content, checksum, manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content, checksum, manifest = build_bytes()
    if args.check:
        if not ARCHIVE.exists() or ARCHIVE.read_bytes() != content:
            raise SystemExit("Public maintainer kit differs from tracked source; rebuild with tools/build_maintainer_kit.py")
        if not CHECKSUM.exists() or CHECKSUM.read_bytes() != checksum:
            raise SystemExit("Public maintainer checksum differs from exact kit")
    else:
        DEST.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_bytes(content)
        CHECKSUM.write_bytes(checksum)
    print(json.dumps({"source_files": len(manifest["files"]), "source_tree_sha256": manifest["source_tree_sha256"],
                      "zip_bytes": len(content), "sha256": sha256(content).hexdigest(), "mode": "check" if args.check else "build"}))

if __name__ == "__main__":
    main()
