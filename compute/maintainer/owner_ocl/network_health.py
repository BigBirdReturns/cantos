"""Bounded authorized TLS health-route audit and offline evidence verifier.

This measures a specifically named owned responder, never model success or SLA.
Self-signed TLS is accepted only with an independently declared exact DER pin.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import http.server
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import ssl
import threading
import tempfile
import time
from urllib.parse import urlsplit
import uuid

SCHEMA = "ocl.owned-network-health/1"
CHECKS = ("owned_network.failure_count", "owned_network.latency_p95_ms")
LIMIT = 4096
SHA = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def bad(_):
        raise ValueError("Nonfinite JSON")
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    canonical(result)  # Also reject overflow such as 1e309 in any nested field.
    return result


def number(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid finite " + label)
    return value


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def date(value):
    if not isinstance(value, str):
        raise ValueError("Network timestamp must be UTC text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Network timestamps must use UTC")
    return parsed


def target(value):
    fields = {"id", "url", "collector_host_id_sha256", "responder_host_id_sha256", "responder_instance_id",
              "responder_source_sha256", "tls_certificate_sha256", "resource_identity_sha256", "scope"}
    if not isinstance(value, dict) or set(value) != fields or value["scope"] != "owned_named_health_route":
        raise ValueError("Expected exact owned named-route network target")
    if not isinstance(value["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", value["id"]):
        raise ValueError("Invalid named target ID")
    for key in fields - {"id", "url", "responder_instance_id", "scope"}:
        if not isinstance(value[key], str) or not SHA.fullmatch(value[key]):
            raise ValueError("Target requires exact " + key)
    if not isinstance(value["responder_instance_id"], str) or str(uuid.UUID(value["responder_instance_id"])) != value["responder_instance_id"]:
        raise ValueError("Responder instance must be canonical UUID")
    if not isinstance(value["url"], str):
        raise ValueError("Network URL must be explicit text")
    parsed = urlsplit(value["url"])
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.hostname or parsed.port is None or not 1024 <= parsed.port <= 65535
            or not re.fullmatch(r"/[A-Za-z0-9/_-]{1,128}", parsed.path)):
        raise ValueError("Target requires exact HTTPS literal-IP, unprivileged port and bounded named route")
    address = ipaddress.ip_address(parsed.hostname)
    if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_link_local or address.is_loopback:
        raise ValueError("Cross-host target requires an explicit unicast non-loopback IPv4")
    return value


def protocol(value):
    if not isinstance(value, dict) or set(value) != {"samples", "timeout_s", "interval_s"}:
        raise ValueError("Network protocol needs samples, timeout_s, interval_s")
    if type(value["samples"]) is not int or not 1 <= value["samples"] <= 20:
        raise ValueError("Network samples must be 1..20")
    number(value["timeout_s"], .1, 3, "request timeout")
    number(value["interval_s"], 0, 1, "request interval")
    return value


def identity(value):
    return {key: value[key] for key in ("id", "responder_host_id_sha256", "responder_instance_id", "responder_source_sha256", "scope")}


def response_body(expected, nonce):
    return canonical({"schema": "ocl.owned-health-response/1", "healthy": True, "nonce": nonce,
                      "responder": identity(expected)})


def request_record(expected, nonce):
    return {"method": "GET", "url": expected["url"], "headers": {"Host": urlsplit(expected["url"]).netloc, "Connection": "close", "Accept": "application/json",
            "X-Cantos-Nonce": nonce}, "body_base64": ""}


def probe_one(expected, nonce, timeout):
    """Direct pinned TLS, with one absolute TCP+handshake+HTTP/body deadline."""
    parsed = urlsplit(expected["url"])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # Exact DER pin checked before any HTTP.
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    connection.auto_open = 0  # A closed pinned TLS socket must never reconnect as plain HTTP.
    observed = {"request_sent": False, "response": None, "peer_certificate_base64": None, "error": None}
    sockets, mutex, expired = [], threading.Lock(), threading.Event()
    deadline = time.monotonic() + timeout
    def register(sock):
        with mutex:
            if expired.is_set():
                sock.close()
                raise TimeoutError("Absolute request deadline exhausted before socket ownership")
            sockets.append(sock)
        return sock
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0 or expired.is_set():
            raise TimeoutError("Absolute request deadline exhausted")
        return value
    def stop():
        expired.set()
        with mutex:
            owned = list(sockets)
        for sock in owned:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        connection.close()
    timer = threading.Timer(timeout, stop)
    timer.daemon = True
    timer.start()
    try:
        raw = register(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        raw.settimeout(remaining())
        raw.connect((parsed.hostname, parsed.port))
        # No implicit handshake: register the wrapped socket before it can block.
        tls = register(context.wrap_socket(raw, do_handshake_on_connect=False))
        tls.settimeout(remaining())
        tls.do_handshake()
        certificate = tls.getpeercert(binary_form=True)
        observed["peer_certificate_base64"] = base64.b64encode(certificate).decode()
        if sha(certificate) != expected["tls_certificate_sha256"]:
            raise ValueError("TLS peer DER certificate pin mismatch; HTTP was not sent")
        tls.settimeout(remaining())
        connection.sock = tls
        request = request_record(expected, nonce)
        connection.putrequest("GET", parsed.path, skip_host=True, skip_accept_encoding=True)
        for key, value in request["headers"].items():
            connection.putheader(key, value)
        connection.endheaders()
        observed["request_sent"] = True
        tls.settimeout(remaining())
        response = connection.getresponse()
        observed["response"] = {"status": response.status, "headers": response.getheaders(), "body_base64": ""}
        data = bytearray()
        while len(data) <= LIMIT:
            # HTTPResponse owns its file reader after getresponse may close the
            # connection socket reference (HTTP/1.0 or Connection: close). Never
            # mutate that closed socket. The registered absolute watchdog still
            # bounds header/body reads, including a blocked response reader.
            remaining()
            block = response.read1(min(1024, LIMIT + 1 - len(data)))
            if not block:
                break
            data.extend(block)
            observed["response"]["body_base64"] = base64.b64encode(data).decode()
        if len(data) > LIMIT:
            raise ValueError("Response exceeds bounded body size")
    except Exception as error:
        observed["error"] = type(error).__name__ + ": " + str(error)[:300]
    finally:
        timer.cancel()
        stop()
        timer.join(.1)
    return observed


def acquire(expected, settings, authorize_target, *, exchange=None, on_event=None):
    expected, settings = target(expected), protocol(settings)
    if authorize_target != sha(canonical(expected)):
        raise ValueError("Explicit authorization must match exact target SHA256")
    collector = sha(socket.gethostname().encode())
    if collector != expected["collector_host_id_sha256"]:
        raise ValueError("Collector host differs from authorized contract")
    if collector == expected["responder_host_id_sha256"]:
        raise ValueError("Cross-host collector and responder identities must differ")
    exchange = exchange or probe_one
    start, monotonic = utc(), time.monotonic()
    rows = []
    for index in range(settings["samples"]):
        nonce = secrets.token_hex(32)
        before, began = utc(), time.monotonic()
        if on_event:
            on_event({"event": "attempt_started", "index": index, "nonce": nonce,
                      "started_at": before, "started_monotonic_s": began, "request": request_record(expected, nonce)})
        observed = exchange(expected, nonce, settings["timeout_s"])
        ended, after = time.monotonic(), utc()
        rows.append({"index": index, "nonce": nonce, "started_at": before, "ended_at": after,
            "started_monotonic_s": began, "ended_monotonic_s": ended, "latency_ms": (ended - began) * 1000,
            "request": request_record(expected, nonce), **observed})
        if on_event:
            on_event({"event": "attempt_completed", "attempt": rows[-1]})
        if index + 1 < settings["samples"]:
            time.sleep(settings["interval_s"])
    return {"schema": SCHEMA, "status": "complete", "target": expected, "protocol": settings,
            "collector_host_id_sha256": collector, "started_at": start, "ended_at": utc(),
            "started_monotonic_s": monotonic, "ended_monotonic_s": time.monotonic(), "attempts": rows,
            "producer_sha256": sha(Path(__file__).read_bytes()),
            "limitations": ["Exact certificate pin authenticates the designated key-holding route, not host ownership, CA hostname validity or provider security.",
                "Collector timestamps and declared source/resource origins are not remote attestation. This bounded route sample establishes no SLA, model endpoint health, application quality or general provider rating."]}


def verify(raw, expected, settings, *, producer_sha256):
    expected, settings = target(expected), protocol(settings)
    if (not isinstance(raw, dict) or raw.get("schema") != SCHEMA or raw.get("status") != "complete"
            or raw.get("target") != expected or raw.get("protocol") != settings
            or raw.get("producer_sha256") != producer_sha256
            or raw.get("collector_host_id_sha256") != expected["collector_host_id_sha256"]):
        raise ValueError("Network source, collector, target, protocol or completion identity mismatch")
    if expected["collector_host_id_sha256"] == expected["responder_host_id_sha256"]:
        raise ValueError("Cross-host identities must differ")
    start, end = date(raw["started_at"]), date(raw["ended_at"])
    left = number(raw["started_monotonic_s"], 0, 1e12, "capture start")
    right = number(raw["ended_monotonic_s"], left, 1e12, "capture end")
    bound = settings["samples"] * (settings["timeout_s"] + .25) + (settings["samples"] - 1) * settings["interval_s"] + 1
    if end < start or right - left > bound or abs((end - start).total_seconds() - (right - left)) > 1:
        raise ValueError("Network UTC/monotonic interval mismatch or finite budget exceeded")
    rows = raw.get("attempts")
    if not isinstance(rows, list) or len(rows) != settings["samples"]:
        raise ValueError("Incomplete network attempt population")
    nonces, failures, latencies, prior_end = set(), [], [], left
    for index, row in enumerate(rows):
        nonce = row.get("nonce")
        if not isinstance(nonce, str) or not SHA.fullmatch(nonce) or nonce in nonces:
            raise ValueError("Missing, duplicate or replayed network nonce")
        nonces.add(nonce)
        if row.get("index") != index or row.get("request") != request_record(expected, nonce):
            raise ValueError("Network raw request differs from authorized route/nonce")
        a = number(row["started_monotonic_s"], prior_end, right, "attempt start")
        if index and a + 1e-6 < prior_end + settings["interval_s"]:
            raise ValueError("Network attempt cadence differs from declared interval (1us float tolerance)")
        b = number(row["ended_monotonic_s"], a, right, "attempt end")
        elapsed = (b - a) * 1000
        number(row["latency_ms"], 0, (settings["timeout_s"] + .25) * 1000, "latency")
        if abs(row["latency_ms"] - elapsed) > 1e-6:
            raise ValueError("Network latency differs from raw local monotonic interval")
        at, bt = date(row["started_at"]), date(row["ended_at"])
        if not start <= at <= bt <= end or abs((bt - at).total_seconds() * 1000 - elapsed) > 1000:
            raise ValueError("Attempt UTC timestamps disagree with local capture clock")
        prior_end = b
        ok = row.get("error") is None and row.get("request_sent") is True
        try:
            certificate = base64.b64decode(row["peer_certificate_base64"], validate=True)
            if not 1 <= len(certificate) <= 65536 or sha(certificate) != expected["tls_certificate_sha256"]:
                ok = False
            response = row["response"]
            body = base64.b64decode(response["body_base64"], validate=True)
            headers = response["headers"]
            if (not isinstance(headers, list) or len(headers) > 100
                    or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                           or not all(isinstance(value, str) for value in pair) for pair in headers)
                    or sum(len(key) + len(value) for key, value in headers) > 65536):
                raise ValueError("Invalid response headers")
            types = [value for key, value in headers if key.lower() == "content-type"]
            if (response["status"] != 200 or types != ["application/json"] or len(body) > LIMIT
                    or body != response_body(expected, nonce)):
                ok = False
            strict(body)  # Duplicate keys/trailing data/nonfinite values never accepted.
        except (ValueError, TypeError, KeyError):
            ok = False
        if ok:
            latencies.append(elapsed)
        else:
            failures.append(index)
    ordered = sorted(latencies)
    p95 = ordered[max(0, math.ceil(.95 * len(ordered)) - 1)] if ordered and not failures else None
    return {"attempts": len(rows), "successes": len(latencies), "failure_count": len(failures),
            "failed_attempt_indices": failures, "latency_p95_ms": p95,
            "observed_window": {"start": raw["started_at"], "end": raw["ended_at"]},
            "scope": "Named owned TLS health route only; no model endpoint health, uptime SLA or general provider qualification.",
            "latency_basis": "Collector local monotonic request interval including connection/TLS/body; p95 nearest rank, unavailable if any attempt failed."}


def verify_packet(raw_bytes, summary_bytes, events_bytes, packet_bytes, expected, settings,
                  *, collector_sha256, producer_sha256):
    """Only retained bytes; no uploaded path, certificate or code is executed."""
    if any(not isinstance(value, bytes) or len(value) > 2 * 1024 * 1024
           for value in (raw_bytes, summary_bytes, events_bytes, packet_bytes)):
        raise ValueError("Network evidence exceeds bounded closure")
    packet = strict(packet_bytes)
    provenance = packet.get("provenance", {})
    if (packet.get("schema") != "ocl.instrument-packet/1" or packet.get("status") != "collected"
            or provenance.get("source_sha256") != collector_sha256
            or provenance.get("network_module_sha256") != producer_sha256):
        raise ValueError("Network packet requires exact pinned collector/source closure")
    entries = packet.get("files")
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValueError("Network packet needs bounded source manifest")
    indexed = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in indexed:
            raise ValueError("Invalid duplicate network packet source entry")
        indexed[entry["path"]] = entry
    for name, data in (("network/raw.json", raw_bytes), ("network/summary.json", summary_bytes),
                       ("network/attempt-events.jsonl", events_bytes)):
        if indexed.get(name, {}).get("sha256") != sha(data) or indexed[name].get("bytes") != len(data):
            raise ValueError("Network packet source hash/size mismatch")
    raw, summary = strict(raw_bytes), strict(summary_bytes)
    checked = verify(raw, expected, settings, producer_sha256=producer_sha256)
    if summary != checked or packet.get("operations", {}).get("owned_network") != checked:
        raise ValueError("Network summary differs from trusted raw recomputation")
    events = [strict(line) for line in events_bytes.splitlines()]
    wanted = []
    for row in raw["attempts"]:
        wanted.extend([{"event": "attempt_started", **{key: row[key] for key in
            ("index", "nonce", "started_at", "started_monotonic_s", "request")}},
            {"event": "attempt_completed", "attempt": row}])
    if events != wanted:
        raise ValueError("Network retained attempt journal is incomplete or changed")
    if not date(provenance["captured_at"]) <= date(raw["started_at"]) <= date(raw["ended_at"]) <= date(provenance["completed_at"]):
        raise ValueError("Network raw observation lies outside original collector window")
    return checked


def publish_new(path, value):
    """Atomically publish an owner-selected new receipt without replacing it."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".network-ready-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)  # Atomic exclusive publication, no replace race.
    finally:
        temporary.unlink()


def serve(expected, certificate, key, authorize_target, *, max_seconds=120, max_requests=40, ready_file=None):
    """Explicit finite owned responder; never invoked by collect/import/verify."""
    expected = target(expected)
    if authorize_target != sha(canonical(expected)) or sha(socket.gethostname().encode()) != expected["responder_host_id_sha256"]:
        raise ValueError("Explicit exact responder target/host authorization required")
    if expected["responder_source_sha256"] != sha(Path(__file__).read_bytes()):
        raise ValueError("Responder source differs from expected contract")
    number(max_seconds, 1, 300, "responder lifetime")
    if type(max_requests) is not int or not 1 <= max_requests <= 40:
        raise ValueError("Responder request bound must be 1..40")
    for path in (Path(certificate), Path(key)):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("Responder certificate/key must be bounded explicit regular files")
    pem = Path(certificate).read_text(encoding="ascii")
    if sha(ssl.PEM_cert_to_DER_cert(pem)) != expected["tls_certificate_sha256"]:
        raise ValueError("Responder certificate differs from authorized DER pin")
    parsed = urlsplit(expected["url"])
    class Handler(http.server.BaseHTTPRequestHandler):
        def handle(self):
            def close():
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()
            timer = threading.Timer(min(2, max(.01, deadline - time.monotonic())), close)
            timer.daemon = True
            timer.start()
            try:
                super().handle()
            finally:
                timer.cancel()
        def do_GET(self):
            values = self.headers.get_all("X-Cantos-Nonce", [])
            if self.path != parsed.path or len(values) != 1 or not SHA.fullmatch(values[0]):
                self.send_error(400)
                return
            body = response_body(expected, values[0])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key, password="")  # Never prompt for a passphrase.
    deadline = time.monotonic() + max_seconds
    accepted = 0
    server = http.server.HTTPServer((parsed.hostname, parsed.port), Handler)
    server.timeout = .25
    try:
        # TLS handshake is per accepted socket with a finite timeout; wrapping
        # the listening socket would permit an unbounded handshake in accept.
        original = server.get_request
        def accept():
            nonlocal accepted
            sock, address = original()
            accepted += 1
            sock.settimeout(min(2, max(.01, deadline - time.monotonic())))
            try:
                return context.wrap_socket(sock, server_side=True), address
            except BaseException:
                sock.close()
                raise
        server.get_request = accept
        if ready_file:
            publish_new(ready_file, {"schema": "ocl.owned-network-ready/1", "state": "ready", "pid": os.getpid(),
                "started_at": utc(), "target_sha256": sha(canonical(expected)), "responder": identity(expected),
                "listen_address": [parsed.hostname, parsed.port], "max_seconds": max_seconds,
                "max_requests": max_requests, "source_sha256": sha(Path(__file__).read_bytes())})
        while time.monotonic() < deadline and accepted < max_requests:
            server.handle_request()
    finally:
        server.server_close()
        if ready_file:
            publish_new(str(ready_file) + ".terminal.json", {"schema": "ocl.owned-network-terminal/1", "state": "stopped",
                "ended_at": utc(), "pid": os.getpid(), "accepted_connections": accepted,
                "target_sha256": sha(canonical(expected)), "scope": "Owned responder listener closed; no model service is owned by this process."})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("probe", "serve"):
        command = sub.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--authorize-target", required=True, help="SHA256 of canonical exact network_target")
    probe = sub.choices["probe"]
    probe.add_argument("--out", required=True)
    responder = sub.choices["serve"]
    responder.add_argument("--certificate", required=True)
    responder.add_argument("--key", required=True)
    responder.add_argument("--max-seconds", type=float, default=120)
    responder.add_argument("--max-requests", type=int, default=40)
    responder.add_argument("--ready-file", help="Owner-selected new readiness JSON, atomically published after bind/listen/TLS setup")
    args = parser.parse_args(argv)
    config = strict(Path(args.config).read_bytes())
    if set(config) != {"network_target", "network_protocol"}:
        raise ValueError("Expected explicit network_target and network_protocol")
    if args.command == "serve":
        def terminated(signum, frame):
            raise KeyboardInterrupt("Owned responder termination")
        prior = signal.signal(signal.SIGTERM, terminated)
        try:
            serve(config["network_target"], args.certificate, args.key, args.authorize_target,
                  max_seconds=args.max_seconds, max_requests=args.max_requests, ready_file=args.ready_file)
        except KeyboardInterrupt:
            return 143
        finally:
            signal.signal(signal.SIGTERM, prior)
    else:
        out = Path(args.out)
        if out.exists():
            raise ValueError("Network raw output must be new")
        result = acquire(config["network_target"], config["network_protocol"], args.authorize_target)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("xb") as stream:
            stream.write(canonical(result) + b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
