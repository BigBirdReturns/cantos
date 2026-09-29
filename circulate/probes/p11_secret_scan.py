"""p11: grep every git-tracked (and untracked-not-ignored) file under circulate/, hot-aisle/, clustermax-challenge/, research-desk/ for credential patterns."""
import re
from _common import *  # noqa

NAME = "p11_secret_scan"
DIRS = ["circulate", "hot-aisle", "clustermax-challenge", "research-desk"]
# Patterns are assembled from fragments so this file (once committed) does not match itself.
PATTERNS = {
    "slack_webhook_host": re.compile(("hooks" + r"\.slack\.com").encode()),
    "aws_access_key_id": re.compile(("AK" + "IA" + r"[0-9A-Z]{16}").encode()),
    "github_pat": re.compile(("gh" + "p_" + r"[A-Za-z0-9]{36}").encode()),
    "slack_token": re.compile(("xo" + "x" + r"[bap]-").encode()),
    "stripe_live_key": re.compile(("sk_" + "live_").encode()),
    "private_key_block": re.compile(("-----" + "BEGIN " + r"(PRIVATE|RSA) KEY").encode()),
    # a Better Stack heartbeat/webhook URL carrying a real-looking token (placeholders such as <TOKEN> or XXXX do not match)
    "betterstack_webhook_token": re.compile((r"betterstack\.com/api/v[0-9]/(?:heartbeat|webhook)s?/" + r"[A-Za-z0-9]{16,}").encode()),
}
NOTE_MAX = 25


def git_files(root, extra):
    rc, out, err = run_cmd(["git", "ls-files", "-z", *extra, "--", *DIRS], cwd=root)
    need(rc == 0, "git ls-files failed: " + err[:200])
    return [p for p in out.split("\0") if p]


def scan(root, paths):
    hits, scanned, bytes_ = [], 0, 0
    for rel in paths:
        p = root / rel
        if not p.is_file():
            continue
        data = p.read_bytes()
        scanned += 1; bytes_ += len(data)
        for name, rx in PATTERNS.items():
            for m in rx.finditer(data):
                line = data.count(b"\n", 0, m.start()) + 1
                hits.append({"file": rel, "line": line, "pattern": name})
                if len(hits) > 200:
                    return hits, scanned, bytes_
    return hits, scanned, bytes_


def body(ctx, work):
    root = ctx_root(ctx)
    tracked = git_files(root, [])
    untracked = git_files(root, ["--others", "--exclude-standard"])
    need(tracked, "git ls-files returned nothing under %s" % DIRS)
    th, ts, tb = scan(root, tracked)
    uh, us, ub = scan(root, untracked)
    hits = th + uh
    status = "FAIL" if hits else "PASS"
    err_note = ""
    if hits:
        by_file = {}
        for h in hits:
            by_file.setdefault(h["file"], []).append("%s@%d" % (h["pattern"], h["line"]))
        err_note = " Hits (file: pattern@line, no matched text): " + "; ".join("%s: %s" % (f, ", ".join(v[:3])) for f, v in list(by_file.items())[:NOTE_MAX])
    return {
        "observed": {"tracked_files_scanned": ts, "tracked_bytes": tb, "untracked_not_ignored_files_scanned": us, "untracked_bytes": ub,
                     "directories": DIRS, "patterns": sorted(PATTERNS), "hits": len(hits),
                     "tracked_hits": len(th), "untracked_hits": len(uh), "hit_locations": hits[:NOTE_MAX]},
        "status": status,
        "error": ("%d credential-pattern hit(s): %d in tracked files, %d in untracked files" % (len(hits), len(th), len(uh))) if hits else None,
        "expected": "zero hits in every tracked file (push protection would otherwise refuse the push)",
        "notes": "Binary files are scanned as raw bytes (the kit zip is stored, not compressed). Untracked-but-not-ignored files are scanned too, because circulate/ is new and not yet tracked; a hit there is treated the same as a tracked hit. Hit reports carry file, line and pattern name only, never the matched text." + err_note,
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
