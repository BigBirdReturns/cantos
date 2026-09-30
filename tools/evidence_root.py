"""Single resolver for evidence inputs (stdlib only, no packaging).

Import by relative path insertion, e.g.

    sys.path.insert(0, str(Path(__file__).resolve().parents[N] / "tools"))
    import evidence_root

Order of resolution for a path such as ("clustermax-cloudreview-20260929", "claims.all.jsonl"):
  1. $CANTOS_EVIDENCE (default: <repo>/evidence) / path
  2. only if that copy is missing: the original session folder at LEGACY_SESSIONS / path
  3. if neither exists, the (missing) primary path is returned, so callers can report it and SKIP.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEGACY_SESSIONS = Path("D:/Projects/Organs/AXM/axm-tools/sessions")


def root() -> Path:
    return Path(os.environ.get("CANTOS_EVIDENCE") or (REPO / "evidence"))


def resolve(*parts) -> Path:
    rel = Path(*parts)
    primary = root() / rel
    if primary.exists():
        return primary
    if os.environ.get("CANTOS_NO_LEGACY"):      # verification switch: prove a clean clone works
        return primary
    legacy = LEGACY_SESSIONS / rel
    return legacy if legacy.exists() else primary


def sessions_dir(*required) -> Path:
    """A folder to hand to code that wants a whole sessions tree (CIRCULATE_SESSIONS wins). Prefers the evidence root,
    then the old session folder, but only one that actually holds every `required` relative path; else the evidence root."""
    env = os.environ.get("CIRCULATE_SESSIONS")
    if env:
        return Path(env)
    for base in ((root(),) if os.environ.get("CANTOS_NO_LEGACY") else (root(), LEGACY_SESSIONS)):
        if all((base / q).exists() for q in required):
            return base
    return root()


def available(*parts) -> bool:
    return resolve(*parts).exists()


def skip_message(*parts) -> str:
    return "SKIP: evidence input %s not found under %s (bulk input not shipped with this repo; set CANTOS_EVIDENCE to a folder holding it)" % (
        Path(*parts).as_posix(), root())
