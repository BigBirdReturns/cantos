"""Bounded, resumable InferenceX artifact reads; see README.md. Stdlib only."""
import argparse
import datetime as dt
import email.utils
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from importer import BASE, digest, hardware

API = "https://api.github.com/repos/SemiAnalysisAI/InferenceX/actions/artifacts"
LIMIT = 64 * 1024 * 1024


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def save(path, value):
    atomic(path, (json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def transport(url):
    """One API operation; redirects to the artifact blob are part of that read."""
    if shutil.which("gh"):
        # --include exposes rate-limit headers on both success and failure.
        p = subprocess.run(["gh", "api", "--method", "GET", "--include", url], capture_output=True)
        data = p.stdout
        sep = b"\r\n\r\n" if b"\r\n\r\n" in data else b"\n\n"
        if not data.startswith(b"HTTP/") or sep not in data:
            raise RuntimeError("gh failed without HTTP headers; check GitHub authentication")
        head, body = data.split(sep, 1)
        lines = head.decode("utf-8").splitlines()
        headers = {k.lower(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:] if ":" in line)}
        return int(lines[0].split()[1]), headers, body
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("install/authenticate gh or provide GH_TOKEN")
    # Never forward API authorization to the signed artifact storage redirect.
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.startswith("https://"):
                raise ValueError("refusing non-HTTPS redirect")
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
            redirected.remove_header("Authorization")
            return redirected
    opener = urllib.request.build_opener(Redirect())
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
                                              "Accept": "application/vnd.github+json", "User-Agent": "backfill-history"})
    try:
        response = opener.open(req, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise ValueError("download exceeds 64 MiB")
        return response.status, {k.lower(): v for k, v in response.headers.items()}, body


class BudgetDone(Exception):
    pass


class Client:
    def __init__(self, maximum, request=transport, sleep=time.sleep, now=time.time):
        self.maximum, self.request, self.sleep, self.now = maximum, request, sleep, now
        self.used = 0
        self.cooldown_until = 0

    def get(self, url):
        while self.used < self.maximum:
            delay = self.cooldown_until - self.now()
            if delay > 0:
                self.sleep(delay)
            self.used += 1
            status, headers, body = self.request(url)
            headers = {k.lower(): v for k, v in headers.items()}
            if status in (403, 429):
                retry = headers.get("retry-after", "60")
                try:
                    seconds = float(retry)
                except ValueError:
                    seconds = email.utils.parsedate_to_datetime(retry).timestamp() - self.now()
                reset = float(headers.get("x-ratelimit-reset", "0")) - self.now() + 1
                self.cooldown_until = self.now() + max(1, seconds, reset)
                # Sleep even at the cap; persist cooldown for the next invocation.
                self.sleep(max(1, seconds, reset))
                continue
            if headers.get("x-ratelimit-remaining") == "0":
                self.cooldown_until = max(self.now() + 1, float(headers.get("x-ratelimit-reset", self.now() + 60)) + 1)
            if status == 410:
                return None
            if status != 200:
                raise RuntimeError("GitHub read failed: HTTP " + str(status))
            return body
        raise BudgetDone()


def matches(row, filters):
    return ((not filters["hardware"] or hardware(row.get("hw")) in filters["hardware"])
            and (not filters["model"] or any(s.lower() in row.get("model", "").lower() for s in filters["model"]))
            and (not filters["framework"] or row.get("framework") in filters["framework"])
            and (not filters["shape"] or str(row.get("isl")) + "/" + str(row.get("osl")) in filters["shape"]))


def fetch(root, client, filters, restart=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    statepath = root / "history-state.json"
    state = json.loads(statepath.read_bytes()) if statepath.exists() else {}
    client.cooldown_until = state.get("cooldown_until", 0)
    if restart or not state:
        state = {"page": 1, "pending": [], "complete": False}
    receipt = {"schema": "inferencex-fetch@1", "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "filters": filters, "fetched": [], "skipped_downloaded": [], "skipped_expired": [], "requests": 0}
    indexpath = root / "history-index.json"
    index = json.loads(indexpath.read_bytes()) if indexpath.exists() else {}
    try:
        while not state["complete"]:
            if not state["pending"]:
                raw = client.get(API + "?name=results_bmk&per_page=100&page=" + str(state["page"]))
                page = json.loads(raw)["artifacts"]
                if not isinstance(page, list):
                    raise ValueError("invalid artifacts page")
                state["pending"] = page
                state["page"] += 1
                if not page:
                    state["complete"] = True
                save(statepath, state)
                continue
            artifact = state["pending"][0]
            ident = str(int(artifact["id"]))
            if artifact["name"] != "results_bmk":
                raise ValueError("unexpected artifact name")
            folder = root / ("results_bmk_" + ident)
            path = folder / "agg_bmk.json"
            run = artifact.get("workflow_run") or {}
            meta = {"artifact_id": int(ident), "created_at": artifact["created_at"],
                    "head_sha": run.get("head_sha"), "workflow_run_id": run.get("id")}
            if path.exists():
                rows = json.loads(path.read_bytes())
                receipt["skipped_downloaded"].append(int(ident))
                sidecar = folder / "artifact.json"
                if sidecar.exists():
                    prior = json.loads(sidecar.read_bytes())
                    if prior.get("sha256") != digest(path.read_bytes()):
                        raise ValueError("cached artifact hash mismatch")
                    meta.update(prior)
            elif artifact.get("expired"):
                receipt["skipped_expired"].append(int(ident))
                rows = None
            else:
                archive = client.get(API + "/" + ident + "/zip")
                if archive is None:
                    receipt["skipped_expired"].append(int(ident))
                    rows = None
                else:
                    with zipfile.ZipFile(io.BytesIO(archive)) as z:
                        names = [n for n in z.infolist() if n.filename == "agg_bmk.json"]
                        if len(names) != 1 or names[0].file_size > LIMIT:
                            raise ValueError("expected one bounded root agg_bmk.json")
                        raw = z.read(names[0])  # never extract arbitrary archive paths
                    rows = json.loads(raw)
                    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                        raise ValueError("aggregate must be a list of objects")
                    meta.update(sha256=digest(raw), retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
                    # Metadata first makes interruption after raw commit recoverable.
                    save(folder / "artifact.json", meta)
                    atomic(path, raw)
                    receipt["fetched"].append(int(ident))
            meta["status"] = "expired" if rows is None else "downloaded"
            meta["matching_row_indices"] = [] if rows is None else [i for i, r in enumerate(rows) if matches(r, filters)]
            index[ident] = meta
            save(indexpath, index)
            state["pending"].pop(0)
            save(statepath, state)
        receipt["status"] = "complete"
    except BudgetDone:
        receipt["status"] = "request-cap"
    except Exception as error:
        receipt["status"] = "error"
        receipt["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        state["cooldown_until"] = client.cooldown_until
        save(statepath, state)
        save(indexpath, index)
        receipt.update(requests=client.used, next_page=state["page"], pending=len(state["pending"]))
        save(root / ("fetch-receipt-" + uuid.uuid4().hex + ".json"), receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=BASE / "data-raw")
    p.add_argument("--max", type=int, default=20, help="maximum API operations including pages, ZIPs and retries")
    p.add_argument("--restart", action="store_true", help="scan from page 1, preserving downloads")
    for key in ("hardware", "model", "framework", "shape"):
        p.add_argument("--" + key, action="append", default=[])
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(BASE), pattern="test_history.py")
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if a.max < 1:
        p.error("--max must be positive")
    try:
        filters = {k: getattr(a, k) for k in ("hardware", "model", "framework", "shape")}
        filters["hardware"] = [hardware(h) for h in filters["hardware"]]
        print(json.dumps(fetch(a.output_dir, Client(a.max), filters, a.restart), indent=2))
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile) as error:
        print("fetch failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
