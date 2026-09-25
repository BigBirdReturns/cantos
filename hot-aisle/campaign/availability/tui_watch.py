#!/usr/bin/env python3
"""One read-only Hot Aisle listing observation; scheduling belongs to the caller.

Private JSON configuration owns all connection locations. This program can send
only n (after proving the loaded, idle team dashboard), Escape, and Ctrl-C. It
never selects a resource, provisions, purchases, deletes, or invokes a model.
Raw terminal captures contain account information: keep state_dir private.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid


SCHEMA = "second-run/tui-capacity-observation@1"
KNOWN = {"no_offer", "candidate", "candidate_review_required", "active_resources",
         "expired", "stopped", "interval_hold", "locked"}
REQUIRED = ("estate_root", "state_dir", "provider_host", "team_name", "team_handle",
            "ssh_identity", "known_hosts", "expires_utc", "interval_seconds")


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must have a UTC offset")
    return parsed.astimezone(timezone.utc)


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or any(k not in config for k in REQUIRED):
        raise ValueError("configuration lacks required fields: " + ", ".join(REQUIRED))
    for key in REQUIRED:
        if key != "interval_seconds" and (not isinstance(config[key], str) or not config[key]):
            raise ValueError(key + " must be a nonempty string")
    interval = config["interval_seconds"]
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1800:
        raise ValueError("interval_seconds must be at least 1800")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", config["provider_host"]):
        raise ValueError("provider_host must be a DNS name or address, without SSH options")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", config["team_handle"]):
        raise ValueError("team_handle must not contain whitespace or control characters")
    if any(ord(c) < 32 for c in config["team_name"]):
        raise ValueError("team_name contains a control character")
    timestamp(config["expires_utc"])
    for key in ("estate_root", "state_dir", "ssh_identity", "known_hosts"):
        p = Path(config[key]).expanduser()
        if not p.is_absolute() or any(c in str(p) for c in '\r\n"'):
            raise ValueError(key + " must be an absolute path without quotes/newlines")
        config[key] = str(p)
    for key in ("ssh_identity", "known_hosts"):
        if not Path(config[key]).is_file():
            raise ValueError(key + " does not exist")
    if not (Path(config["estate_root"]) / "estate_peer.py").is_file():
        raise ValueError("estate_root has no estate_peer.py")
    return config


def clean_terminal(raw):
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    # Kitty graphics, OSC, and other terminal control strings never carry rows.
    text = re.sub(r"\x1b_[\s\S]*?\x1b\\", "", text)
    text = re.sub(r"\x1b\][\s\S]*?(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "\n", text)
    text = re.sub(r"\x1b[()][A-Za-z0-9]|\x1b.", "", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\r]+", " ", line).strip()
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)


def dashboard_state(text, config):
    """Accumulated capture: only the most recent breadcrumb is actionable."""
    header = re.compile(r"Hot Aisle\s*›\s*" + re.escape(config["team_name"]) + r"\s*[\u2800-\u28ff]*\s*$")
    headers = list(re.finditer(r"Hot Aisle[^\n]*", text))
    if not headers or not header.search(headers[-1].group()):
        return "unknown"
    if "Provision" in headers[-1].group():
        return "unknown"
    # The observed root view identifies the handle before automatic team entry.
    if not re.search(r"@" + re.escape(config["team_handle"]) + r"(?=\W|$)", text):
        return "unknown"
    start = next((h.start() for h in headers if header.search(h.group())), len(text))
    dashboard = text[start:]
    balances = list(re.finditer(r"Account Balance", dashboard))
    if not balances:
        return "unknown"
    loaded = dashboard[balances[-1].start():]
    rates = re.findall(r"Hourly Rate:\s*\$([\d,]+(?:\.\d+)?)\s*/hour", loaded)
    if not rates:
        return "unknown"
    if float(rates[-1].replace(",", "")) != 0:
        return "active_resources"
    if "No active resources" not in loaded:
        return "unknown"
    if not re.search(r"Available Balance:\s*\$[\d,.]+", loaded):
        return "unknown"
    if "Loading balance" in loaded or "n provision new resources" not in dashboard:
        return "unknown"
    if "No virtual machines" not in dashboard or "No bare metal servers" not in dashboard:
        return "unknown"
    return "ready"


def classify_menu(text, config):
    marker = re.search(r"Provision Resources - " + re.escape(config["team_name"]) + r"\s*[\u2800-\u28ff]*\s*(?=\n|$)", text)
    if marker is None:
        return {"classification": "unknown", "reason": "expected provisioning page absent"}
    section = text[marker.start():]
    match = re.search(r"Available Resources\s*\n", section)
    if not match:
        return {"classification": "unknown", "reason": "resource list not loaded"}
    menu = section[match.end():]
    # Stop at the first new breadcrumb; subsequent dashboard/root text is not a row.
    menu = re.split(r"(?:[^\n]*Hot Aisle[^\n]*|So long, Hot Aisle)", menu, maxsplit=1)[0].strip()
    if not menu or re.search(r"loading|fetching|please wait", menu, re.I):
        return {"classification": "unknown", "reason": "resource list is incomplete"}
    lines = [line for line in menu.splitlines() if "MI300X" in line.upper()]
    if re.fullmatch(r"No items\.?\s*(?:enter provision selected VM\s*)?", menu) and not lines:
        return {"classification": "no_offer", "reason": "loaded resource list says No items", "menu_text": menu}
    if lines:
        exact, uncertain, other = [], [], []
        for line in lines:
            counts = [int(x) for x in re.findall(r"\b(\d+)\s*(?:[x×]\s*(?:AMD\s+)?MI300X|GPUs?\b)", line, re.I)]
            counts += [int(x) for x in re.findall(r"MI300X\s*[x×]\s*(\d+)\b", line, re.I)]
            if counts and set(counts) != {1}:
                other.append(line)
            elif counts and re.search(r"\bVM\b|Virtual Machine", line, re.I) and not re.search(r"bare\s*metal", line, re.I):
                exact.append(line)
            else:
                uncertain.append(line)
        if exact:
            return {"classification": "candidate", "reason": "explicit one-GPU MI300X VM listing; acquisition untested", "candidate_rows": exact, "menu_text": menu}
        if uncertain:
            return {"classification": "candidate_review_required", "reason": "MI300X listing needs GPU-count or VM-kind review", "candidate_rows": uncertain, "menu_text": menu}
        if other:
            if re.search(r"more below|next page", menu, re.I):
                return {"classification": "unknown", "reason": "partial list shows other GPU counts; hidden rows unobserved", "menu_text": menu}
            return {"classification": "no_offer", "reason": "MI300X rows list only other GPU counts", "menu_text": menu}
    return {"classification": "unknown", "reason": "unrecognized resource list", "menu_text": menu}


def abort_reason(config, now=None):
    if (Path(config["state_dir"]) / "STOP").exists():
        return "stopped"
    if (now or utcnow()) >= timestamp(config["expires_utc"]):
        return "expired"
    return None


@contextmanager
def sample_lock(state):
    path = state / "sample.lock"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (str(os.getpid()) + "\n").encode())
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        path.unlink()


def atomic_json(path, body):
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with tmp.open("x", encoding="utf-8") as out:
        json.dump(body, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)


def load_estate(config):
    path = Path(config["estate_root"]) / "estate_peer.py"
    spec = importlib.util.spec_from_file_location("estate_peer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ssh_arguments(config, estate, registry, ssh_config):
    return [estate.ssh_binary(), "-F", Path(ssh_config).as_posix(), "-J", estate.front_door_id(registry),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", 'UserKnownHostsFile="' + Path(config["known_hosts"]).as_posix() + '"',
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
            "-tt", "-i", Path(config["ssh_identity"]).as_posix(), config["provider_host"]]


def capture(config, argv, raw_path):
    chunks, reader_errors, guard = [], [], threading.Lock()
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, **kwargs)
    def reader():
        try:
            with raw_path.open("xb") as saved:
                total = 0
                while True:
                    block = os.read(proc.stdout.fileno(), 65536)
                    if not block:
                        break
                    total += len(block)
                    if total > 8 * 1024 * 1024:
                        raise RuntimeError("terminal capture exceeded 8 MiB")
                    saved.write(block)
                    saved.flush()
                    with guard:
                        chunks.append(block)
                os.fsync(saved.fileno())
        except (OSError, RuntimeError) as exc:
            with guard:
                reader_errors.append(str(exc))
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    sent_n = False
    result = {"classification": "unknown", "reason": "terminal deadline elapsed"}
    stable = None
    stable_since = None
    started = time.monotonic()
    def send(keys):
        if keys not in (b"n", b"\x1b", b"\x03"):
            raise ValueError("read-only key boundary")
        if proc.poll() is None:
            try:
                proc.stdin.write(keys)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
    try:
        while time.monotonic() - started < 50:
            cancelled = abort_reason(config)
            if cancelled:
                result = {"classification": cancelled, "reason": "capture cancelled"}
                break
            with guard:
                text = clean_terminal(b"".join(chunks))
                failed_reader = bool(reader_errors)
            if failed_reader:
                result = {"classification": "unknown", "reason": "terminal capture failed"}
                break
            if not sent_n:
                state = dashboard_state(text, config)
                if state == "active_resources":
                    result = {"classification": state, "reason": "team already has a nonzero hourly rate"}
                    break
                if state == "ready":
                    send(b"n")
                    sent_n = True
            else:
                candidate = classify_menu(text, config)
                if candidate["classification"] != "unknown":
                    signature = json.dumps(candidate, sort_keys=True)
                    if signature != stable:
                        stable, stable_since = signature, time.monotonic()
                    elif time.monotonic() - stable_since >= 3:
                        result = candidate
                        break
            if proc.poll() is not None:
                result = {"classification": "unknown", "reason": "SSH exited before a stable listing", "ssh_exit_code": proc.returncode}
                break
            time.sleep(0.2)
    finally:
        if sent_n:
            send(b"\x1b")
        send(b"\x03")
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        thread.join(timeout=3)
        proc.stdin.close()
        proc.stdout.close()
    result["sent_provision_menu_key"] = sent_n
    if thread.is_alive() or reader_errors:
        result = {"classification": "unknown", "reason": "capture reader failed or did not close"}
    return result


def run_once(config, force=False):
    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True)
    try:
        with sample_lock(state):
            reason = abort_reason(config)
            if reason:
                return {"classification": reason, "reason": "no connection attempted"}
            latest_path = state / "latest.json"
            latest = json.loads(latest_path.read_text()) if latest_path.exists() else None
            if latest and not force:
                elapsed = (utcnow() - timestamp(latest["started_utc"])).total_seconds()
                if elapsed < config["interval_seconds"]:
                    return {"classification": "interval_hold", "reason": "minimum sampling interval has not elapsed", "next_sample_utc": latest.get("next_sample_utc")}
            started = utcnow()
            capture_id = started.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
            raw_path = state / (capture_id + ".raw")
            observation = {"schema": SCHEMA, "started_utc": started.isoformat(), "provider": "hotaisle",
                           "method": "tui-provision-list", "layer": "listed", "provisioned": False,
                           "synthetic": False, "forced": bool(force)}
            try:
                estate = load_estate(config)
                registry = estate.load_registry(Path(config["estate_root"]) / "estate_peer_registry.json")
                ssh_config, _ = estate.write_artifacts(registry, state / "peer-control")
                probe = estate.run_peer_script(estate.front_door_id(registry), "hostname\n", registry, ssh_config, timeout_seconds=20)
                observation["front_door"] = {k: probe.get(k) for k in ("peer", "ok", "classification", "canonical_ingress")}
                if not probe.get("ok"):
                    result = {"classification": "unknown", "reason": "N01 front door probe failed; provider was not contacted"}
                elif abort_reason(config):
                    result = {"classification": abort_reason(config), "reason": "cancelled after front door probe"}
                else:
                    result = capture(config, ssh_arguments(config, estate, registry, ssh_config), raw_path)
                observation.update(result)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                observation.update(classification="unknown", reason="observation failed", error=type(exc).__name__ + ": " + str(exc))
            if raw_path.exists():
                raw = raw_path.read_bytes()
                clean_path = raw_path.with_suffix(".txt")
                clean_path.write_text(clean_terminal(raw), encoding="utf-8")
                observation["capture"] = {"raw_path": str(raw_path), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                          "text_path": str(clean_path), "text_sha256": hashlib.sha256(clean_path.read_bytes()).hexdigest()}
            observation["completed_utc"] = utcnow().isoformat()
            from datetime import timedelta
            observation["next_sample_utc"] = (started + timedelta(seconds=config["interval_seconds"])).isoformat()
            with (state / "observations.jsonl").open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps(observation, sort_keys=True) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            atomic_json(latest_path, observation)
            return observation
    except FileExistsError:
        return {"classification": "locked", "reason": "another sample or retained orphan lock exists"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--force", action="store_true", help="explicitly bypass the minimum interval, never STOP/expiry")
    args = parser.parse_args(argv)
    try:
        result = run_once(load_config(args.config), args.force)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"classification": "configuration_error", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["classification"] in KNOWN else 1


if __name__ == "__main__":
    raise SystemExit(main())
