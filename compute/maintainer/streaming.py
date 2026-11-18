"""Bounded streamed OpenAI-compatible requests with retained wire evidence.

TTFT means first nonempty visible content delta. Chunk gaps are not token gaps.
No retries, redirects, proxy inheritance, speculative token counts or code execution.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from .common import canonical, now
    from .owner_ocl.runner import _strict_loads, NoRedirect, endpoint
except ImportError:
    from common import canonical, now
    from owner_ocl.runner import _strict_loads, NoRedirect, endpoint

MAX_BYTES = 16 * 1024 * 1024


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def headers(config):
    out = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    secret = os.environ.get(config.get("auth_env", "OCL_API_KEY"))
    if secret:
        out["Authorization"] = "Bearer " + secret
    return out


def probe(config, timeout):
    parsed = urllib.parse.urlsplit(config["base_url"])
    root = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    observed = {"captured_at": now()}
    for key, suffix in (("version", "/version"), ("models", "/v1/models")):
        try:
            req = urllib.request.Request(root + suffix, headers=headers(config))
            with opener().open(req, timeout=min(timeout, 10)) as r:
                data = r.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError("probe body exceeds bound")
                observed[key] = {"http_status": r.status, "body": _strict_loads(data.decode("utf-8"))}
        except Exception as exc:
            # Endpoint probes are observations, not attestations of weights or hardware.
            observed[key] = {"error": type(exc).__name__, "http_status": getattr(exc, "code", None)}
    return observed


def _events(chunks):
    """SSE framing, preserving time at which each complete event became visible."""
    buffer = b""
    fields = []
    last_time = 0.0
    for chunk in chunks:
        at = chunk["at_s"]
        if type(at) not in (int, float) or at < last_time:
            raise ValueError("nonmonotonic chunk timestamps")
        last_time = at
        buffer += base64.b64decode(chunk["data_b64"], validate=True)
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.rstrip(b"\r")
            if not line:
                if fields:
                    yield at, b"\n".join(fields).decode("utf-8")
                    fields = []
            elif line.startswith(b"data:"):
                fields.append(line[5:].lstrip(b" "))
            elif line.startswith(b":"):
                pass
            elif line.split(b":", 1)[0] not in (b"event", b"id", b"retry"):
                raise ValueError("invalid SSE field")
    if buffer or fields:
        raise ValueError("unterminated SSE event")


def parse_capture(raw):
    text = ""
    finish = None
    done = False
    times = []
    models = set()
    usage = {}
    parse_error = None
    try:
        if raw.get("http_status") != 200:
            raise ValueError("HTTP status " + str(raw.get("http_status")))
        if "text/event-stream" not in raw.get("content_type", "").lower():
            raise ValueError("response is not text/event-stream")
        for at, payload in _events(raw["chunks"]):
            if done:
                raise ValueError("data after DONE")
            if payload == "[DONE]":
                done = True
                continue
            obj = _strict_loads(payload)
            if not isinstance(obj, dict) or obj.get("error"):
                raise ValueError("server error or non-object SSE event")
            if obj.get("model") is not None:
                if not isinstance(obj["model"], str):
                    raise ValueError("invalid response model")
                models.add(obj["model"])
            if obj.get("usage") is not None:
                if not isinstance(obj["usage"], dict):
                    raise ValueError("invalid usage")
                usage = obj["usage"]
            choices = obj.get("choices")
            if not isinstance(choices, list) or len(choices) > 1:
                raise ValueError("expected one completion choice")
            if not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                raise ValueError("invalid completion choice")
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                raise ValueError("missing delta object")
            if delta.get("tool_calls") or delta.get("function_call"):
                raise ValueError("structured tool-call streaming requires a task-specific adapter")
            content = delta.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("non-text content delta")
            if content:
                if finish is not None:
                    raise ValueError("content after finish reason")
                text += content
                times.append(at)
            reason = choice.get("finish_reason")
            if reason is not None:
                if not isinstance(reason, str) or not reason or finish is not None:
                    raise ValueError("invalid or repeated finish reason")
                finish = reason
        if not done:
            raise ValueError("stream ended without DONE")
        if finish is None:
            raise ValueError("stream ended without finish reason")
        if not times:
            raise ValueError("stream contained no visible answer content")
    except Exception as exc:
        parse_error = type(exc).__name__ + ": " + str(exc)[:300]
    error = raw.get("transport_error") or parse_error
    def count(key):
        n = usage.get(key)
        return n if type(n) is int and n >= 0 else None
    duration = raw["ended_monotonic_s"] - raw["started_monotonic_s"]
    if duration <= 0 or any(x > duration + 1e-6 for x in times):
        raise ValueError("capture timing outside request interval")
    return {"stage": raw["stage"], "request": raw["request"], "response_text": text,
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "error": error, "transport_error": raw.get("transport_error"), "stream_error": parse_error,
            "duration_s": duration, "ttft_s": times[0] if times else None,
            "content_chunk_times_s": times,
            "inter_content_chunk_s": [b-a for a, b in zip(times, times[1:])],
            "input_tokens": count("prompt_tokens"), "output_tokens": count("completion_tokens"),
            "token_count_source": "server usage; unverified tokenization", "usage": usage,
            "finish_reason": finish, "stream_done": done, "response_models": sorted(models),
            "started_monotonic_s": raw["started_monotonic_s"],
            "ended_monotonic_s": raw["ended_monotonic_s"]}


def capture(config, proto, messages, stage):
    body = {"model": config["model"], "messages": messages, "temperature": 0,
            "seed": proto["seed"], "max_tokens": proto["max_tokens"], "stream": True,
            "stream_options": {"include_usage": True}, **proto["extra_body"]}
    encoded = canonical(body)
    if len(encoded) > MAX_BYTES:
        raise ValueError("request exceeds 16MiB bound")
    start = time.monotonic()
    raw = {"schema": "cantos.maintainer.stream/1", "stage": stage, "started_at": now(),
           "started_monotonic_s": start, "request": body, "chunks": [],
           "http_status": None, "content_type": None, "transport_error": None}
    try:
        request = urllib.request.Request(endpoint(config["base_url"], config.get("allow_remote", False)),
                                         encoded, headers(config), method="POST")
        with opener().open(request, timeout=proto["timeout_s"]) as response:
            raw["http_status"] = response.status
            raw["content_type"] = response.headers.get("Content-Type", "")
            total = 0
            tail = b""
            done = False
            done_line = False
            while not done:
                remaining = proto["timeout_s"] - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError("total request deadline exceeded")
                # read1 makes one buffered/socket read, so a slow endless stream
                # cannot reset the total deadline as readline can.
                try:
                    response.fp.raw._sock.settimeout(remaining)
                except AttributeError:
                    pass
                data = response.read1(min(65536, MAX_BYTES - total + 1))
                at = time.monotonic() - start
                if not data:
                    break
                total += len(data)
                raw["chunks"].append({"at_s": at, "data_b64": base64.b64encode(data).decode("ascii")})
                if total > MAX_BYTES:
                    raise ValueError("stream exceeds 16MiB bound")
                tail += data
                while b"\n" in tail:
                    line, tail = tail.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if not line and done_line:
                        done = True
                    if line.strip() == b"data: [DONE]":
                        done_line = True
                if done and tail.strip():
                    raise ValueError("trailing nonframed bytes after DONE")
    except urllib.error.HTTPError as exc:
        raw["http_status"] = exc.code
        raw["content_type"] = exc.headers.get("Content-Type", "") if exc.headers else ""
        # Store bounded server response bytes without printing auth or exception URL.
        try:
            raw["http_error_body_b64"] = base64.b64encode(exc.read(65536)).decode("ascii")
        finally:
            exc.close()
        raw["transport_error"] = "HTTPError: " + str(exc.code)
    except Exception as exc:
        raw["transport_error"] = type(exc).__name__ + ": request failed"
    raw["ended_monotonic_s"] = time.monotonic()
    raw["ended_at"] = now()
    return raw, parse_capture(raw)
