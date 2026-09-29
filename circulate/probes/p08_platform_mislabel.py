"""p08: status-pages.json copy with a wrong platform; collect_status auto mode detects the real platform or records UNSUPPORTED, never a silent zero-incident file."""
import contextlib
import io
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from _common import *  # noqa

NAME = "p08_platform_mislabel"
RAW = SESSIONS / "lanes" / "clustermax-r2-raw"


def make_server(routes):
    """routes: fn(path, query) -> bytes | None. Serves 127.0.0.1 on an ephemeral port."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlsplit(self.path)
            data = routes(u.path, parse_qs(u.query))
            if data is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def atlassian_routes(d):
    def routes(path, q):
        if path == "/history.json":
            f = d / ("history-page-%s.json" % q.get("page", ["1"])[0])
        else:
            m = re.fullmatch(r"/incidents/([a-z0-9]+)\.json", path)
            f = d / ("incident-%s.json" % m.group(1)) if m else None
        return f.read_bytes() if f and f.is_file() else None
    return routes


def collect(cs, slug, url, out_root):
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
        rc = cs.main(["--slug", slug, "--url", url, "--mode", "auto", "--out-root", str(out_root)])
    f = out_root / (slug + ".json")
    return rc, buf_o.getvalue(), buf_e.getvalue(), (json.loads(f.read_text(encoding="utf-8")) if f.exists() else None)


def body(ctx, work):
    root = ctx_root(ctx)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / "clustermax-challenge" / "scripts"))
    try:
        import collect_status as cs
    finally:
        sys.path.remove(str(root / "clustermax-challenge" / "scripts"))
    cs.MIN_REQUEST_INTERVAL = 0.0          # local server; the politeness pacing is for real status pages
    real = json.loads((root / "clustermax-challenge/retrospective/status-pages.json").read_text(encoding="utf-8"))
    truth = {p["rating_name"]: p["platform"] for p in real["providers"]}
    need(RAW.is_dir(), "saved pages not found under " + str(RAW))
    servers, obs = [], {}
    try:
        # A: a real Atlassian-history page (Crusoe's saved history.json + incident files) labelled 'betterstack'
        crusoe = RAW / "crusoe"
        srv = make_server(atlassian_routes(crusoe)); servers.append(srv)
        urlA = "http://127.0.0.1:%d" % srv.server_address[1]
        sp = {"schema": real["schema"], "providers": [{"rating_name": "ProbeAtlassian", "status_url": urlA, "platform": "betterstack",
                                                          "note": "platform deliberately wrong; real platform is atlassian-history"}]}
        write_json(work / "status-pages.json", sp)
        entry = json.loads((work / "status-pages.json").read_text(encoding="utf-8"))["providers"][0]
        rc, so, se, doc = collect(cs, "probe-atlassian", entry["status_url"], work / "outA")
        need(doc is not None, "no output file written for case A")
        mode = re.match(r"\[([a-z-]+)\]", so.strip()).group(1) if re.match(r"\[([a-z-]+)\]", so.strip()) else None
        A = {"labelled_platform": entry["platform"], "detected_mode": mode, "exit": rc, "incidents": len(doc["incidents"]),
             "coverage": [doc.get("coverage_start"), doc.get("coverage_end")], "notes": doc.get("notes", [])[:2]}
        obs["case_A_atlassian_labelled_betterstack"] = A
        need(mode == "atlassian-history" and A["incidents"] > 0,
             "auto mode neither detected the real platform nor produced incidents: %r" % A)

        # B: a status.io page (CoreWeave's saved page) labelled 'atlassian': not machine-readable by this collector
        cw = (RAW / "coreweave" / "history_2026-09.html").read_bytes()
        srv2 = make_server(lambda path, q: cw if path in ("/", "") else None); servers.append(srv2)
        urlB = "http://127.0.0.1:%d" % srv2.server_address[1]
        rc, so, se, doc = collect(cs, "probe-statusio", urlB, work / "outB")
        need(doc is not None, "no output file written for case B (a missing file is also a silent failure)")
        mode = re.match(r"\[([a-z-]+)\]", so.strip()).group(1) if re.match(r"\[([a-z-]+)\]", so.strip()) else None
        text = " ".join(doc.get("notes", []))
        B = {"labelled_platform": "atlassian", "true_platform": truth.get("CoreWeave"), "detected_mode": mode, "exit": rc,
             "incidents": len(doc["incidents"]), "coverage_end": doc.get("coverage_end"), "notes": doc.get("notes", [])[:1]}
        obs["case_B_statusio_labelled_atlassian"] = B
        silent_zero = (not doc["incidents"]) and doc.get("coverage_end") and not doc.get("notes")
        need(not silent_zero, "zero-incident file with a coverage window and no note: a silent zero")
        unsupported = (not doc["incidents"]) and doc.get("coverage_end") is None and ("no automated" in text or "UNSUPPORTED" in text.upper())
        need(unsupported or doc["incidents"], "case B neither parsed incidents nor recorded the platform as unsupported: %r" % B)
        B["recorded_as"] = "UNSUPPORTED (generic fallback: no incidents, coverage_end null, note says no automated parser)" if unsupported else "parsed"
        # the entry's claimed platform must not have been trusted
        need(mode != "atlassian" or doc["incidents"], "trusted the wrong label and returned nothing")
    finally:
        for s in servers:
            s.shutdown(); s.server_close()
    return {
        "observed": obs,
        "expected": "auto mode ignores the mislabelled platform: detects the real one (case A) or leaves an explicit UNSUPPORTED-style record with null coverage and a note (case B); never an empty incident file that looks like a clean history",
        "notes": "collect_status.main() called in-process against a local http.server on 127.0.0.1 serving saved pages from lanes/clustermax-r2-raw (Crusoe's Atlassian history.json + incident files; CoreWeave's status.io page). "
                 "Output goes to temp dirs. collect_status.py does not itself read status-pages.json; the temp entry supplies the URL and the wrong 'platform' label, which is the input the driver's status stage will read. "
                 "The current script has three modes (atlassian-history, atlassian, generic); it has no betterstack/instatus/sorryapp mode yet, so 'UNSUPPORTED' is expressed as the generic fallback record.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
