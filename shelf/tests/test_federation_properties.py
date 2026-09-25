#!/usr/bin/env python3
"""Deterministic local federation regressions; no network and no mocked engines.

The generated cases exercise captures and admission records, not whether a
source is truthful or an admission actor is authorized. On W01 all disposable
bytes live in S:\\Scratch\\Temp; elsewhere the OS temporary directory is used.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1]
EPOCH = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)
SEED = 20260924


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shelf = load_module("federation_shelf", TOOL / "scripts" / "shelf.py")
staging_check = load_module("federation_staging", TOOL / "scripts" / "check_staging.py")
SKELETON = json.loads((TOOL / "card.skeleton.json").read_text(encoding="utf-8"))


def encoded(value, **kwargs):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, **kwargs).encode("utf-8")


class FederationProperties(unittest.TestCase):
    def setUp(self):
        scratch = Path(r"S:\Scratch\Temp") if os.name == "nt" else None
        if scratch is not None and not scratch.is_dir():
            self.fail("W01 federation tests require the existing typed S:\\Scratch\\Temp")
        self.temp = tempfile.TemporaryDirectory(prefix="shelf-federation-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.rng = random.Random(SEED)
        self.serial = 0
        self.source_shelf = Path(shelf.CARDS).read_bytes()
        self.addCleanup(self.assert_source_shelf_unchanged)

    def assert_source_shelf_unchanged(self):
        self.assertEqual(Path(shelf.CARDS).read_bytes(), self.source_shelf)

    def card(self, number):
        card = copy.deepcopy(SKELETON)
        card["id"] = "generated-{:04d}".format(number)
        card["title"] = "Generated local federation case {}".format(number)
        card["dimensions"] = {key: self.rng.choice([True, False, None]) for key in shelf.DIMS}
        card["a_claim"]["results"]["example_result"]["value"] = self.rng.randrange(1, 100000) / 100
        card["a_claim"]["results"]["example_result"]["source"] = "https://example.invalid/claim/{}".format(number)
        card["a_claim"]["limits"] = ["Synthetic test input; establishes no provider fact."]
        return card

    def capture(self, data, card=None, raw=None, hub="upstream", tick=None):
        self.serial += 1
        source = self.base / "input-{}.json".format(self.serial)
        source.write_bytes(encoded(card) if raw is None else raw)
        folder, provenance = shelf.pull(
            str(source), hub, staging=str(data / "staging"),
            now=EPOCH + dt.timedelta(seconds=self.serial if tick is None else tick),
        )
        return Path(folder), provenance

    def check(self, data):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = staging_check.main(data=str(data))
        return result, stream.getvalue()

    def write_shelf(self, data, cards):
        data.mkdir(parents=True, exist_ok=True)
        (data / "cards.jsonl").write_bytes(b"".join(encoded(card) + b"\n" for card in cards))

    def promotion(self, data, folder, provenance, card):
        return {
            "id": card["id"],
            "from": folder.relative_to(data / "staging").as_posix(),
            "sha256": provenance["sha256"],
            "who": "local-test-procedure",
            "when": "2026-09-24T12:00:00Z",
            "why": "Explicit local test admission for this captured input only.",
        }

    def write_promotions(self, data, records):
        (data / "promotions.jsonl").write_bytes(b"".join(encoded(record) + b"\n" for record in records))

    def test_identical_bytes_across_hubs_remain_candidates(self):
        # 32 inputs x 3 hubs: byte identity neither erases origin nor grants standing.
        data = self.base / "same-bytes"
        for number in range(32):
            card = self.card(number)
            card["standing"] = "source-claims-accepted"
            for check in shelf.CHECKS:
                card["e_checks"][check] = {"who": "source-hub", "when": "2026-09-23", "scope": "source assertion"}
            raw = encoded(card, indent=number % 4)
            digest = hashlib.sha256(raw).hexdigest()
            for hub in ("Alpha Hub", "beta-hub", "gamma.hub"):
                with self.subTest(number=number, hub=hub):
                    folder, prov = self.capture(data, raw=raw, hub=hub)
                    self.assertEqual((folder / "source.bytes").read_bytes(), raw)
                    self.assertEqual(prov["sha256"], digest)
                    self.assertEqual(prov["hub"], hub)
                    self.assertEqual(prov["standing"], "imported/candidate")
                    self.assertEqual(shelf.read_cards(folder / "cards.jsonl"), [card])
                    self.assertFalse((data / "cards.jsonl").exists())
        self.assertEqual(self.check(data)[0], 0)

    def test_representation_changes_bytes_without_inventing_different_claims(self):
        # 24 claims x 4 encodings: raw identity differs; parsed claims agree.
        data = self.base / "representations"
        for number in range(24):
            card = self.card(number)
            representations = (encoded(card), encoded(card, indent=2), encoded([card]), encoded(card) + b"\n")
            hashes = []
            for variant, raw in enumerate(representations):
                with self.subTest(number=number, variant=variant):
                    folder, prov = self.capture(data, raw=raw, hub="encoding-{}".format(variant))
                    hashes.append(prov["sha256"])
                    self.assertEqual((folder / "source.bytes").read_bytes(), raw)
                    self.assertEqual(shelf.read_cards(folder / "cards.jsonl"), [card])
            self.assertEqual(len(set(hashes)), 4)
        self.assertEqual(self.check(data)[0], 0)

    def test_successor_captures_preserve_originals_and_local_admission_is_specific(self):
        # 24 independent histories, three retained revisions per history.
        for number in range(24):
            with self.subTest(number=number):
                data = self.base / "successor-{}".format(number)
                original = self.card(number)
                folder, prov = self.capture(data, original, tick=1)
                snapshot = {p.name: p.read_bytes() for p in folder.iterdir()}
                corrected = copy.deepcopy(original)
                corrected["a_claim"]["results"]["example_result"]["value"] += 1
                corrected["a_claim"]["limits"].append("Corrected declared number; no new measurement.")
                second, second_prov = self.capture(data, corrected, tick=2)
                metadata = copy.deepcopy(corrected)
                metadata["d_materials"]["primary_url"] = "https://example.invalid/correction/{}".format(number)
                third, third_prov = self.capture(data, metadata, tick=3)
                self.assertEqual(snapshot, {p.name: p.read_bytes() for p in folder.iterdir()})
                self.assertEqual(len({prov["sha256"], second_prov["sha256"], third_prov["sha256"]}), 3)
                self.write_shelf(data, [corrected])
                self.write_promotions(data, [self.promotion(data, folder, prov, original)])
                self.assertGreater(self.check(data)[0], 0, "old admission must not authorize a changed successor")
                self.write_promotions(data, [self.promotion(data, second, second_prov, corrected)])
                self.assertEqual(self.check(data)[0], 0, self.check(data)[1])
                self.assertEqual(snapshot, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_generated_tampering_is_rejected(self):
        mutations = ("source", "parsed", "filings", "count", "standing", "sha256", "hub", "retrieved_at")
        for number in range(8):
            for mutation in mutations:
                with self.subTest(number=number, mutation=mutation):
                    data = self.base / "tamper-{}-{}".format(number, mutation)
                    folder, prov = self.capture(data, self.card(number))
                    if mutation == "source":
                        path = folder / "source.bytes"
                        path.write_bytes(path.read_bytes() + b" ")
                    elif mutation == "parsed":
                        cards = shelf.read_cards(folder / "cards.jsonl")
                        cards[0]["title"] += " forged"
                        (folder / "cards.jsonl").write_bytes(encoded(cards[0]) + b"\n")
                    else:
                        if mutation == "filings":
                            prov["filings"][0]["errors"] = ["invented inspection"]
                        elif mutation == "count":
                            prov["cards"] += 1
                        elif mutation == "standing":
                            prov["standing"] = "accepted"
                        elif mutation == "sha256":
                            prov["sha256"] = "0" * 64
                        elif mutation == "hub":
                            prov["hub"] = "another hub"
                        elif mutation == "retrieved_at":
                            prov["retrieved_at"] = "2027-01-01T00:00:00Z"
                        (folder / "provenance.json").write_bytes(encoded(prov))
                    self.assertGreater(self.check(data)[0], 0, mutation)

    def test_generated_forged_promotions_cannot_authorize_a_card(self):
        mutations = ("id-only", "id", "from", "sha256", "who", "when", "why", "unrecorded")
        for number in range(8):
            for mutation in mutations:
                with self.subTest(number=number, mutation=mutation):
                    data = self.base / "promotion-{}-{}".format(number, mutation)
                    card = self.card(number)
                    folder, prov = self.capture(data, card)
                    self.write_shelf(data, [card])
                    decision = self.promotion(data, folder, prov, card)
                    if mutation == "id-only":
                        decision = {"id": card["id"]}
                    elif mutation == "id":
                        decision["id"] = "other-card"
                    elif mutation == "from":
                        decision["from"] = "another-hub/20260924T000000Z"
                    elif mutation == "sha256":
                        decision["sha256"] = "f" * 64
                    elif mutation in ("who", "why"):
                        decision[mutation] = "  "
                    elif mutation == "when":
                        decision["when"] = "yesterday"
                    self.write_promotions(data, [] if mutation == "unrecorded" else [decision])
                    self.assertGreater(self.check(data)[0], 0, mutation)

    def test_invalid_filings_and_duplicate_ids_are_retained_without_admission(self):
        for number in range(16):
            with self.subTest(number=number):
                data = self.base / "duplicates-{}".format(number)
                card = self.card(number)
                raw = encoded(card) + b"\n" + encoded(card) + b"\n"
                folder, prov = self.capture(data, raw=raw)
                self.assertEqual((folder / "source.bytes").read_bytes(), raw)
                self.assertEqual(prov["cards"], 2)
                self.assertTrue(all("id must be unique on a shelf" in filing["errors"] for filing in prov["filings"]))
                self.assertEqual(self.check(data)[0], 0, "invalid candidates stay inspectable")
                self.write_shelf(data, [card])
                self.write_promotions(data, [self.promotion(data, folder, prov, card)])
                self.assertGreater(self.check(data)[0], 0, "ambiguous duplicate source IDs cannot be admitted")
                self.write_shelf(data, [card, card])
                self.assertGreater(self.check(data)[0], 0, "local shelf IDs must be unique")

    def test_local_check_records_are_not_inferred_from_capture_or_admission(self):
        for number in range(16):
            with self.subTest(number=number):
                data = self.base / "local-checks-{}".format(number)
                source = self.card(number)
                for key in shelf.CHECKS:
                    source["e_checks"][key] = {"who": "remote-source", "when": "2026-09-23", "scope": "reported source check"}
                folder, prov = self.capture(data, source)
                local = copy.deepcopy(source)
                local["e_checks"] = copy.deepcopy(SKELETON["e_checks"])
                self.write_shelf(data, [local])
                self.write_promotions(data, [self.promotion(data, folder, prov, source)])
                self.assertEqual(self.check(data)[0], 0, self.check(data)[1])
                self.assertEqual(shelf.read_cards(data / "cards.jsonl")[0]["e_checks"], SKELETON["e_checks"])
                self.assertEqual(shelf.read_cards(folder / "cards.jsonl")[0]["e_checks"], source["e_checks"])

    def test_capture_collision_never_overwrites_and_hub_cannot_escape(self):
        data = self.base / "collisions"
        card = self.card(0)
        folder, _ = self.capture(data, card, hub="Some Hub", tick=7)
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        with self.assertRaises(FileExistsError):
            self.capture(data, self.card(1), hub="some-hub", tick=7)
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        for hub in (".", "..", "---", "///", "   "):
            with self.subTest(hub=hub), self.assertRaises(ValueError):
                self.capture(data, card, hub=hub, tick=8)


if __name__ == "__main__":
    unittest.main()
