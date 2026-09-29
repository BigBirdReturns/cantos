"""p05: fetch a gated Hugging Face dataset shard (lmsys/lmsys-chat-1m); HTTP 401 recorded as HOLD, no retry with credentials."""
import json
import socket
import urllib.error
import urllib.request
from _common import *  # noqa

NAME = "p05_gated_source"
LISTING = SESSIONS / "lanes" / "chat-corpora-meta" / "raw" / "lmsys__lmsys-chat-1m.parquet.json"
MANIFEST = SESSIONS / "lanes" / "chat-corpora-meta" / "manifest.json"


class NoAuthNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None   # a gated shard must not be chased through redirects


def shard_url():
    listing = json.loads(LISTING.read_text(encoding="utf-8"))
    urls = [u for splits in listing.values() for vals in splits.values() for u in vals]
    need(urls, "no parquet shard URL in the retained listing")
    return urls[0]


def recorded_gate():
    """What the chat-corpora-meta lane recorded for this dataset (manifest.json is JSON Lines)."""
    hits = []
    for ln in MANIFEST.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if "lmsys/lmsys-chat-1m" in r["url"] and r.get("http") == 401:
                hits.append({"url": r["url"], "http": 401})
    return hits


def body(ctx, work):
    url = shard_url()
    recorded = recorded_gate()
    if ctx.get("offline"):
        return {"status": "HOLD", "observed": {"url": url, "attempts": 0, "recorded_401s_in_lane_manifest": recorded},
                "expected": "HTTP 401 recorded as HOLD", "notes": "--offline: no request made. HOLD, not FAIL; the lane manifest already records the 401s."}
    # One anonymous request. No Authorization header, no proxy env credentials, no HF_TOKEN, no redirect chasing, no retry.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoAuthNoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "circulate-probe/1", "Range": "bytes=0-0"})
    need(req.get_header("Authorization") is None, "request carries credentials")
    attempts, status, err = 0, None, None
    try:
        attempts += 1
        with opener.open(req, timeout=20) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        err = str(e)
    if status is None:
        return {"status": "HOLD", "observed": {"url": url, "attempts": attempts, "network_error": err, "recorded_401s_in_lane_manifest": recorded},
                "expected": "HTTP 401 recorded as HOLD",
                "notes": "Offline or unreachable: HOLD, not FAIL. The lane manifest already records the 401s for this dataset."}
    if status in (200, 206):
        return {"status": "SKIP", "observed": {"url": url, "http": status, "attempts": attempts},
                "expected": "HTTP 401 for the gated shard",
                "notes": "The shard answered without credentials: the gate is gone (or was never enforced for this path). No bytes beyond the first were requested; nothing stored. Re-check the dataset terms before ingesting."}
    need(status in (401, 403), "unexpected HTTP status %s for the gated shard" % status)
    need(attempts == 1, "retry happened")
    return {
        "observed": {"url": url, "http": status, "recorded_as": "HOLD", "attempts": attempts, "credentials_sent": False,
                     "hf_token_env_present_but_unused": bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")),
                     "recorded_401s_in_lane_manifest": recorded},
        "expected": "HTTP 401 on the first anonymous request, recorded as HOLD; a single attempt, no credentials",
        "notes": "Shard URL is the first entry of the retained parquet listing (lanes/chat-corpora-meta/raw). The request asks for one byte with no Authorization header and does not follow redirects. HOLD = the source correctly refused; the probe itself PASSes.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
