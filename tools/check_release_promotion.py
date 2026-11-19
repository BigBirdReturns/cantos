#!/usr/bin/env python3
"""Fail-closed, read-only preflight for a Cantos public promotion.

The candidate must retain the current public GitHub head AND the separate
root release owner's accepted lineage, contain the exact committed kit bytes,
and match a separately pinned expected public head. This checker never pushes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SCHEMA = "cantos.publication-promotion-preflight/1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_KIT = 64 * 1024 * 1024
PUBLIC_REMOTE = "https://github.com/BigBirdReturns/cantos.git"


def command(repo, *args, timeout=18):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], text=True,
                              capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", type(exc).__name__
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()[-240:]


def inspect(repo, candidate, expected_public, protected_root, remote, kit, expected_sha, expected_bytes):
    checks = []
    def check(name, ok, detail):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        return bool(ok)

    record = {
        "schema": SCHEMA,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "remote": remote,
        "expected_public_main": expected_public,
        "protected_root": protected_root,
        "candidate": candidate,
        "kit_path": kit,
        "kit_expected_sha256": expected_sha,
        "kit_expected_bytes": expected_bytes,
        "checks": checks,
        "evidence_class": ("public_github_and_native_git_preflight" if remote == PUBLIC_REMOTE
                           else "custom_remote_fixture_preflight"),
        "scope": "source lineage and committed artifact integrity only; hosted CI and Pages are separate gates",
    }
    valid_args = (
        all(isinstance(s, str) and SHA.fullmatch(s) for s in (candidate, expected_public, protected_root))
        and isinstance(expected_sha, str) and SHA256.fullmatch(expected_sha)
        and type(expected_bytes) is int and 0 <= expected_bytes <= MAX_KIT
        and isinstance(kit, str) and kit and not kit.startswith("/")
        and "\\" not in kit and all(part not in ("", ".", "..") for part in kit.split("/"))
    )
    if not check("bounded_inputs", valid_args, "strict hashes and safe relative path required"):
        record["verdict"] = "HOLD"
        return record
    repo = Path(repo)
    if not check("owned_git_directory", repo.is_absolute() and repo.is_dir()
                 and not repo.is_symlink(), "absolute, existing Git worktree required"):
        record["verdict"] = "HOLD"
        return record
    rc, out, err = command(repo, "rev-parse", "--show-toplevel")
    if not check("git_worktree", rc == 0 and Path(out).resolve() == repo.resolve(),
                 "candidate must be the worktree root"):
        record["verdict"] = "HOLD"
        return record

    rc, head, err = command(repo, "rev-parse", "HEAD")
    check("exact_candidate_head", rc == 0 and head == candidate, "observed=" + head[:40])
    rc, dirty, err = command(repo, "status", "--porcelain=v1", "--untracked-files=no")
    check("tracked_tree_clean", rc == 0 and not dirty, "tracked changes=" + str(len(dirty.splitlines())))

    rc, remote_result, err = command(repo, "ls-remote", "--heads", remote, "refs/heads/main")
    fields = remote_result.splitlines()
    public_head = fields[0].split()[0] if len(fields) == 1 and len(fields[0].split()) == 2 and fields[0].split()[1] == "refs/heads/main" else None
    record["observed_public_main"] = public_head
    check("live_public_main_exact", rc == 0 and public_head == expected_public,
          "observed=" + str(public_head) + (" error=" + err if rc else ""))

    for name, ancestor in (("public_lineage_preserved", expected_public),
                            ("root_owner_lineage_preserved", protected_root)):
        rc, out, err = command(repo, "merge-base", "--is-ancestor", ancestor, candidate)
        check(name, rc == 0, "ancestor=" + ancestor + " exit=" + str(rc))

    path = repo / kit
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(repo.resolve())
        info = path.lstat()
        safe = (relative.as_posix() == kit and stat.S_ISREG(info.st_mode)
                and not path.is_symlink() and info.st_size <= MAX_KIT)
    except (OSError, ValueError):
        safe = False
    if check("regular_owned_kit", safe, "committed regular file within worktree, <=64 MiB"):
        observed = 0
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                observed += len(chunk)
                if observed > MAX_KIT:
                    break
                hasher.update(chunk)
        record["observed_kit_bytes"] = observed
        record["observed_kit_sha256"] = hasher.hexdigest()
        check("exact_kit_bytes_and_sha256",
              observed == expected_bytes and hasher.hexdigest() == expected_sha,
              "bytes=" + str(observed) + " sha256=" + hasher.hexdigest())
        rc, blob, err = command(repo, "rev-parse", candidate + ":" + kit)
        rc2, disk_blob, err2 = command(repo, "hash-object", "--", str(path))
        check("kit_matches_committed_blob", rc == 0 and rc2 == 0 and blob == disk_blob,
              "source_blob=" + blob[:40] + " observed_blob=" + disk_blob[:40])
    record["verdict"] = "PASS" if all(x["pass"] for x in checks) else "HOLD"
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-public", required=True)
    parser.add_argument("--protected-root", required=True)
    parser.add_argument("--remote", default=PUBLIC_REMOTE)
    parser.add_argument("--kit", default="public/open-compute/maintainer-kit.zip")
    parser.add_argument("--kit-sha256", required=True)
    parser.add_argument("--kit-bytes", type=int, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    report = inspect(args.repo, args.candidate, args.expected_public, args.protected_root,
                     args.remote, args.kit, args.kit_sha256, args.kit_bytes)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(args.receipt, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    print(serialized)
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
