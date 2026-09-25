#!/usr/bin/env python3
"""Every staged import must carry provenance whose sha256 matches source.bytes, its cards.jsonl
must be the canonical rendering of those bytes (an edited staged card is caught), its standing
must still read imported/candidate, and no staged card may appear on the shelf without a
recorded input-specific promotion in data/promotions.jsonl. Exit code counts violations.

This establishes neither an actor's authority nor source truth, and does not
infer local inspection, recomputation or repetition from a source assertion.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

_spec = importlib.util.spec_from_file_location("staging_shelf", os.path.join(HERE, "shelf.py"))
shelf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shelf)


def load_jsonl(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return [json.loads(l) for l in f if l.strip()]


def parse_cards(text):
    text = text.lstrip("﻿")
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    except ValueError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def canonical_jsonl(cards):
    return "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cards)


def identity(value):
    """Compare JSON without Python's True == 1 or permissive NaN equality."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def claim_identity(card):
    # Local checks are separately recorded; other source fields stay unchanged.
    return identity({key: value for key, value in card.items() if key != "e_checks"})


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def dated(value):
    if not nonempty(value):
        return False
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            dt.date.fromisoformat(value)
        else:
            dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def main_for(staging, cards_path, promotions_path, say=print):
    bad = 0
    staging = Path(staging)

    def fail(label, reason):
        nonlocal bad
        bad += 1
        say(f"[FAIL   ] {label}: {reason}")

    def read_records(path):
        try:
            return load_jsonl(path)
        except (OSError, UnicodeError, ValueError) as error:
            fail(Path(path).name, f"cannot read records: {error}")
            return []

    local_cards = read_records(cards_path)
    local_errors = shelf.validate_cards(local_cards)
    for card, errors in zip(local_cards, local_errors):
        if errors:
            cid = card.get("id", "?") if isinstance(card, dict) else "?"
            fail("cards.jsonl", f"{cid}: {'; '.join(errors)}")
    promotions = read_records(promotions_path)
    captures = {}
    imported_ids = set()
    if staging.exists() and not staging.is_dir():
        fail("staging", "must be a directory")
    elif staging.is_dir():
        for hub in sorted(staging.iterdir()):
            if not hub.is_dir():
                fail(hub.name, "expected a hub directory")
                continue
            for folder in sorted(hub.iterdir()):
                coordinate = folder.relative_to(staging).as_posix()
                if not folder.is_dir():
                    fail(coordinate, "expected a capture directory")
                    continue
                files = {path.name for path in folder.iterdir()}
                if files != {"cards.jsonl", "provenance.json", "source.bytes"}:
                    fail(coordinate, f"expected exactly cards.jsonl, provenance.json, source.bytes; found {sorted(files)}")
                    continue
                before = bad
                try:
                    prov = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
                    raw = (folder / "source.bytes").read_bytes()
                    source_cards = parse_cards(raw.decode("utf-8"))
                    if not isinstance(prov, dict):
                        raise ValueError("provenance must be an object")
                    digest = hashlib.sha256(raw).hexdigest()
                    if prov.get("sha256") != digest:
                        fail(coordinate, f"provenance sha256 {prov.get('sha256')} != source.bytes {digest}")
                    expected = canonical_jsonl(source_cards)
                    with open(folder / "cards.jsonl", encoding="utf-8", newline="") as f:
                        actual = f.read()
                    if actual != expected:
                        fail(coordinate, "cards.jsonl is not the canonical rendering of source.bytes; a staged card was edited after import")
                    if prov.get("standing") != "imported/candidate":
                        fail(coordinate, f"standing must be imported/candidate, not {prov.get('standing')!r}")
                    if not nonempty(prov.get("location")):
                        fail(coordinate, "source location must be recorded")
                    if not nonempty(prov.get("hub")) or shelf.hub_slug(prov["hub"]) != hub.name:
                        fail(coordinate, "provenance hub does not identify its capture directory")
                    retrieved = prov.get("retrieved_at")
                    if not isinstance(retrieved, str):
                        raise ValueError("retrieved_at must be a UTC timestamp")
                    dt.datetime.strptime(retrieved, "%Y-%m-%dT%H:%M:%SZ")
                    if retrieved.replace(":", "").replace("-", "") != folder.name:
                        fail(coordinate, "retrieved_at does not identify its capture directory")
                    errors = shelf.validate_cards(source_cards)
                    filings = [{"id": card.get("id") if isinstance(card, dict) else None, "errors": error}
                               for card, error in zip(source_cards, errors)]
                    if type(prov.get("cards")) is not int or prov["cards"] != len(source_cards):
                        fail(coordinate, "provenance card count does not match source.bytes")
                    if identity(prov.get("filings")) != identity(filings):
                        fail(coordinate, "provenance filings do not match checks of source.bytes")
                    imported_ids.update(card["id"] for card in source_cards
                                        if isinstance(card, dict) and isinstance(card.get("id"), str))
                    if bad == before:
                        captures[coordinate] = {"sha256": digest, "cards": source_cards, "errors": errors}
                        say(f"[PASS   ] {coordinate}: {len(source_cards)} card(s), sha256 {digest[:12]}, standing imported/candidate, cards.jsonl matches source bytes")
                except (OSError, UnicodeError, ValueError, TypeError) as error:
                    fail(coordinate, f"cannot verify capture: {error}")

    decisions = []
    for index, promotion in enumerate(promotions, 1):
        label = f"promotions.jsonl:{index}"
        if not isinstance(promotion, dict) or not all(nonempty(promotion.get(key)) for key in ("id", "from", "sha256", "who", "when", "why")):
            fail(label, "requires nonempty id/from/sha256/who/when/why")
            continue
        capture = captures.get(promotion["from"])
        if capture is None:
            fail(label, "from must name an exact verified hub/capture directory relative to staging")
            continue
        if promotion["sha256"] != capture["sha256"]:
            fail(label, "sha256 does not match the named captured input")
            continue
        if not dated(promotion["when"]):
            fail(label, "when must be an ISO date or datetime")
            continue
        matches = [(card, errors) for card, errors in zip(capture["cards"], capture["errors"])
                   if isinstance(card, dict) and card.get("id") == promotion["id"]]
        if len(matches) != 1 or matches[0][1]:
            fail(label, "id must identify exactly one passing filing in the captured input")
            continue
        decisions.append((promotion["id"], matches[0][0]))

    for card, errors in zip(local_cards, local_errors):
        if errors or card["id"] not in imported_ids:
            continue
        matches = [source for cid, source in decisions if cid == card["id"]]
        if not any(claim_identity(card) == claim_identity(source) for source in matches):
            fail("cards.jsonl", f"{card['id']}: staged identity collision without a matching input-specific admission; local claim must match the admitted source outside e_checks")
    if not staging.exists() and not promotions:
        say("[PASS   ] no staging directory; nothing imported")
    return bad


def main(data=None):
    data = DATA if data is None else data
    return main_for(os.path.join(data, "staging"), os.path.join(data, "cards.jsonl"), os.path.join(data, "promotions.jsonl"))


if __name__ == "__main__":
    sys.exit(main())
