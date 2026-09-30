"""Read the retained bulk delivery; append attempts only in separate local state."""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from .query import row_by_id


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def row_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected a corpus row identity")
    return value


def write_fresh(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class Collection:
    def __init__(self, bundle, state):
        self.bundle = Path(bundle).resolve(strict=True)
        self.state = Path(state).resolve()
        if self.state == self.bundle or self.bundle in self.state.parents:
            raise ValueError("Attempt state must be outside the retained delivery")
        self.db = self.bundle / "corpus/corpus.sqlite"
        if not self.db.is_file():
            raise ValueError("The delivery has no corpus/corpus.sqlite")
        self.lock = threading.Lock()
        self.batch_maps = {}

    def overview(self):
        report = read_json(self.bundle / "corpus/IMPORT.json")
        return {"rows": report["rows"], "by_kind": report["by_kind"],
                "sources": report["sources"], "bundle": str(self.bundle),
                "state": str(self.state),
                "calibration": read_json(self.bundle / "verification/CALIBRATION-SHAPES.json")}

    def batch(self, row, historical=False):
        base = self.bundle / "history/initial-projection" if historical else self.bundle
        folder = base / "research-packets"
        index = read_json(folder / "INDEX.json")
        origin = row["source"]["origin"]
        key = (str(base), origin)
        if key not in self.batch_maps:
            mapping = {}
            for entry in index["batches"]:
                if origin not in entry["origins"]:
                    continue
                path = (folder / entry["file"]).resolve(strict=True)
                if path.parent != folder.resolve() or digest(path) != entry["sha256"]:
                    raise ValueError("Retained batch differs from its index")
                packet = read_json(path)
                for event in packet["workspace"]["events"]:
                    record = event.get("payload", {})
                    for item in record.get("data", {}).get("rows", []):
                        mapping[item["row_id"]] = (path, entry)
            self.batch_maps[key] = mapping
        path, entry = self.batch_maps[key][row["row_id"]]
        # Recheck the bytes when opened; the in-memory map is only an accelerator.
        if digest(path) != entry["sha256"]:
            raise ValueError("Retained batch has changed")
        packet = read_json(path)
        found = any(item == row for event in packet["workspace"]["events"]
                    for item in event.get("payload", {}).get("data", {}).get("rows", []))
        if not found:
            raise ValueError("SQLite observation differs from its retained research packet")
        return path, {"file": path.name, "sha256": entry["sha256"],
                      "workspace_sha256": packet["sha256"],
                      "events": len(packet["workspace"]["events"])}

    def attempts(self, row_id):
        records = []
        paths = sorted((self.state / row_key(row_id)).glob("*/result.json"))
        previous_sha, previous_events = None, None
        if paths:
            original = self.batch(row_by_id(self.db, row_id))[0]
            previous_sha = digest(original)
            previous_events = read_json(original)["workspace"]["events"]
        for path in paths:
            result = read_json(path)
            packet = path.parent / "attempt.research-packet.json"
            receipt = path.parent / "receipt.json"
            if digest(packet) != result["packet_sha256"] or digest(receipt) != result["receipt_sha256"]:
                raise ValueError("A retained attempt has changed; inspect the local state before extending it")
            data = read_json(receipt)
            if (result["id"] != path.parent.name or result["row_id"] != row_id
                    or data["row_id"] != row_id or result["predecessor_sha256"] != previous_sha
                    or any(result[key] != data[key] for key in
                           ("actor", "observed_at", "matches_current_projection"))):
                raise ValueError("Attempt summary differs from its receipt or predecessor")
            events = read_json(packet)["workspace"]["events"]
            if len(events) != len(previous_events) + 2 or events[:len(previous_events)] != previous_events:
                raise ValueError("Attempt does not extend the preceding native journal")
            appended = [event.get("payload", {}).get("data", {}) for event in events[-2:]]
            if not any(record.get("row_id") == row_id and record.get("before") == data["before"]
                       and record.get("rebuilt") == data["rebuilt"]
                       and record.get("matches_current_projection") == data["matches_current_projection"]
                       and record.get("actor_label") == data["actor"]
                       and record.get("observed_at") == data["observed_at"] for record in appended):
                raise ValueError("Attempt receipt differs from the appended native record")
            result["operation"] = "Rebuild observation from retained source"
            result["boundary"] = "Normalization replay; no hardware benchmark or calibration was run."
            records.append(result)
            previous_sha, previous_events = result["packet_sha256"], events
        return records

    def incomplete(self, row_id):
        return [{"id": path.name, "status": "Completion unconfirmed; retained files need inspection"}
                for path in sorted((self.state / row_key(row_id)).glob("*"))
                if path.is_dir() and not (path / "result.json").exists()]

    def history(self, row_id):
        row = row_by_id(self.db, row_key(row_id))
        _, batch = self.batch(row)
        initial_db = self.bundle / "history/initial-projection/corpus/corpus.sqlite"
        initial, changes, initial_batch = None, [], None
        if initial_db.is_file():
            try:
                initial = row_by_id(initial_db, row_id)
            except KeyError:
                pass
            if initial is not None:
                _, initial_batch = self.batch(initial, historical=True)
                changes = [{"field": key, "before": initial.get(key), "after": row.get(key)}
                           for key in sorted(set(initial) | set(row)) if initial.get(key) != row.get(key)]
        links = []
        for label, url in [("Acquired source", row["source"].get("url")),
                           ("Producer results and configuration", row["native"].get("Details")),
                           ("Producer implementation", row["native"].get("Code"))]:
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                links.append({"label": label, "url": url})
        correction = self.bundle / "correct_metric_projection.py"
        return {"row": row, "batch": batch, "initial_batch": initial_batch,
                "changes": changes, "attempts": self.attempts(row_id),
                "incomplete": self.incomplete(row_id), "links": links,
                "rationale": "The delivery does not record the producer's decision rationale.",
                "correction": ({"file": correction.name, "sha256": digest(correction),
                                "text": correction.read_text(encoding="utf-8")}
                               if changes and correction.is_file() else None)}

    def attempt(self, row_id, actor):
        from .projection import reproject
        from .history import append_projection_attempt
        from datetime import datetime, timezone
        row_key(row_id)
        if not isinstance(actor, str):
            raise ValueError("Use a text actor label")
        actor = actor.strip()
        if not actor or len(actor) > 120:
            raise ValueError("Use an actor label of 1 to 120 characters")
        with self.lock:
            current = self.history(row_id)
            previous = current["attempts"]
            packet = (self.state / row_id / previous[-1]["id"] / "attempt.research-packet.json"
                      if previous else self.batch(current["row"])[0])
            receipt = reproject(self.bundle, row_id, actor=actor)
            attempt_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex[:8]
            folder = self.state / row_id / attempt_id
            folder.mkdir(parents=True, exist_ok=False)
            receipt_path = folder / "receipt.json"
            write_fresh(receipt_path, json.dumps(receipt, indent=2, ensure_ascii=False).encode("utf-8"))
            returned = append_projection_attempt(packet, receipt_path, folder / "native", bundle=self.bundle)
            # Keep the owner's bytes unchanged at a stable export path.
            export = folder / "attempt.research-packet.json"
            write_fresh(export, Path(returned["packet_path"]).read_bytes())
            result = {"id": attempt_id, "row_id": row_id, "actor": actor,
                      "observed_at": receipt["observed_at"],
                      "operation": "Rebuild observation from retained source",
                      "matches_current_projection": receipt["matches_current_projection"],
                      "packet_sha256": digest(export), "receipt_sha256": digest(receipt_path),
                      "predecessor_sha256": digest(packet),
                      "boundary": "Normalization replay; no hardware benchmark or calibration was run."}
            # Only complete summaries become visible to readers. An interrupted
            # write leaves an explicitly unconfirmed folder, never partial JSON.
            pending = folder / "result.pending.json"
            write_fresh(pending, json.dumps(result, indent=2).encode("utf-8"))
            pending.rename(folder / "result.json")
            return result

    def export(self, row_id, attempt_id=None):
        row_key(row_id)
        if attempt_id:
            if not any(r["id"] == attempt_id for r in self.attempts(row_id)):
                raise KeyError("Unknown attempt")
            return self.state / row_id / attempt_id / "attempt.research-packet.json"
        return self.batch(row_by_id(self.db, row_id))[0]
