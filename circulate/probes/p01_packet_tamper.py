"""p01: flip one byte in a copy of the standing packet; validate_packet.js must exit nonzero naming the failed check."""
import shutil
from _common import *  # noqa

NAME = "p01_packet_tamper"
PACKET_REL = "research-desk/packets/PUBLIC-TAIL-2026-09-29.research-packet.json"
VALIDATOR_REL = "research-desk/packets/validate_packet.js"


def body(ctx, work):
    root = ctx_root(ctx)
    packet = root / PACKET_REL
    validator = root / VALIDATOR_REL
    need(packet.is_file() and validator.is_file(), "packet or validator missing")
    orig_sha = sha256_file(packet)
    raw = packet.read_bytes()
    tampered = flip_byte_in_json_value(raw, b'"html_sha256": "')
    need(tampered != raw and len(tampered) == len(raw), "tamper did not change exactly one byte")
    diff = [i for i in range(len(raw)) if raw[i] != tampered[i]]
    need(len(diff) == 1, "expected one flipped byte, got %d" % len(diff))
    copy = work / "tampered.research-packet.json"
    copy.write_bytes(tampered)
    rc, out, err = run_cmd(["node", validator, copy], cwd=root, timeout=600)
    text = out + err
    named = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- ")]
    need(rc != 0, "validate_packet.js accepted a tampered packet (exit 0)")
    need("PASS" not in out.split("\n")[-2:] and "FAIL" in err, "no FAIL line on stderr: %r" % err[:200])
    need(any("checksum" in n.lower() or "hash" in n.lower() for n in named), "failure did not name a checksum/hash check: %r" % named[:3])
    need(sha256_file(packet) == orig_sha, "the real packet changed")
    return {
        "observed": {"exit_code": rc, "failed_checks": named[:5], "flipped_byte_offset": diff[0],
                     "tampered_sha256": sha256_bytes(tampered), "original_sha256": orig_sha,
                     "stderr_first_line": err.splitlines()[0] if err else None},
        "expected": "validate_packet.js exits nonzero and names the failed check (workspace checksum)",
        "notes": "Tamper lands inside a source record's html_sha256 string so the JSON still parses and the failure must come from the "
                 "integrity check. The untampered packet is not re-validated here (a full validate is ~75 s because it replays 1847 events "
                 "through the app's own verifyPacket); the standing 'tests' stage does that.",
    }


def run(ctx=None):
    return execute(NAME, body, ctx)
