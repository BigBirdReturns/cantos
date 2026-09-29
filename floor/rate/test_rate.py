"""Tests for the desk-tier rating.  stdlib unittest; run from floor/rate:  python -m unittest test_rate"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rate  # noqa: E402

ROWS = None
INP = None


def setUpModule():
    global ROWS, INP
    INP = rate.load_inputs()
    INP["manifest"] = {s: rate.manifest_entries(s) for s in INP["headers"]}
    ROWS = [rate.rate_provider(s, INP) for s in sorted(INP["headers"])]


class Invariants(unittest.TestCase):
    def test_85_rows_unique(self):
        self.assertEqual(len(ROWS), 85)
        self.assertEqual(len({r["slug"] for r in ROWS}), 85)

    def test_every_short_has_evidence_id(self):
        n_short = 0
        for r in ROWS:
            ids = {e["id"] for e in r["evidence"]}
            for d, D in r["dimensions"].items():
                if D["status"] != "SHORT":
                    self.assertEqual(D["shortfalls"], [], (r["slug"], d))
                    continue
                n_short += 1
                self.assertTrue(D["shortfalls"], (r["slug"], d, "SHORT without shortfall label"))
                for s in D["shortfalls"]:
                    self.assertTrue(s["label"], (r["slug"], d))
                    self.assertGreaterEqual(len(s["evidence_ids"]), 1, (r["slug"], d, s["label"]))
                    for eid in s["evidence_ids"]:
                        self.assertIn(eid, ids, (r["slug"], d, eid))
                        self.assertIn(eid, D["evidence_ids"], (r["slug"], d, eid))
        self.assertGreater(n_short, 50)      # the run is not vacuous

    def test_short_labels_belong_to_their_dimension(self):
        mirrored = {"no_status_history", "undisclosed_provider"}   # transparency facets repeat these
        for r in ROWS:
            for d, D in r["dimensions"].items():
                for s in D["shortfalls"]:
                    home = rate.DIM_OF_LABEL[s["label"]]
                    self.assertTrue(home == d or (d == "transparency" and s["label"] in mirrored), (r["slug"], d, s["label"]))

    def test_unknown_never_counts_toward_distance(self):
        for r in ROWS:
            statuses = [r["dimensions"][d]["status"] for d in rate.DIMENSIONS]
            self.assertEqual(r["distance_to_floor"], statuses.count("SHORT"), r["slug"])
            self.assertEqual(r["unknown_count"], statuses.count("UNKNOWN"), r["slug"])
            self.assertEqual(r["distance_to_floor"], len(r["short_dimensions"]))
            self.assertLessEqual(r["distance_to_floor"] + r["unknown_count"], 6)
            self.assertTrue(set(statuses) <= {"MEETS", "SHORT", "UNKNOWN"})

    def test_unknown_not_promoted_by_synthetic_input(self):
        inp = {"headers": {"x": {"provider": "X"}}, "tiers": {}, "claims": {"x": [
            {"id": "cmcr-x-01", "quote": "X is a cloud.", "topic": "business", "stance": 0}]},
            "manifest": {}, "incidents": {}, "status_pages": {}, "campaign": {}, "price": {"entries": {}}}
        r = rate.rate_provider("x", inp)
        self.assertEqual(r["distance_to_floor"], 0)
        self.assertEqual(r["unknown_count"], 6)

    def test_zero_evidence_provider(self):
        r = rate.rate_provider("no-such-provider", {})
        self.assertEqual(r["evidence_count"], 0)
        self.assertEqual(r["evidence"], [])
        self.assertEqual(r["distance_to_floor"], 0)
        self.assertEqual(r["unknown_count"], 6)
        for d in rate.DIMENSIONS:
            self.assertEqual(r["dimensions"][d]["status"], "UNKNOWN")
            self.assertEqual(r["dimensions"][d]["evidence_count"], 0)
            self.assertEqual(r["dimensions"][d]["shortfalls"], [])

    def test_real_zero_evidence_rows_are_all_unknown(self):
        zero = [r for r in ROWS if r["evidence_count"] == 0]
        self.assertTrue(zero, "expected at least one review page with no dimension-bearing sentence")
        for r in zero:
            self.assertEqual((r["distance_to_floor"], r["unknown_count"]), (0, 6), r["slug"])

    def test_evidence_count_is_consistent(self):
        for r in ROWS:
            self.assertEqual(r["evidence_count"], len(r["evidence"]))
            self.assertEqual(r["evidence_count"], len({i for D in r["dimensions"].values() for i in D["evidence_ids"]}))

    def test_imported_context_is_not_a_score_input(self):
        for slug in [ROWS[0]["slug"], "hotaisle", "coreweave"]:
            inp2 = copy.deepcopy(INP)
            for t in inp2["tiers"].values():
                t["tier"], t["tier_3_0"] = "ZZZ", "ZZZ"
            for h in inp2["headers"].values():
                h["tier_on_page"] = "ZZZ"
            a = rate.rate_provider(slug, INP)
            b = rate.rate_provider(slug, inp2)
            self.assertEqual(a["dimensions"], b["dimensions"], slug)
            self.assertEqual(b["imported_context"]["clustermax_3_0_medal"], "ZZZ")


class HotAisle(unittest.TestCase):
    def row(self):
        return next(r for r in ROWS if r["slug"] == "hotaisle")

    def test_disclosure_present(self):
        r = self.row()
        self.assertIn("disclosure", r)
        self.assertIn("Hot Aisle", r["disclosure"])
        self.assertIn("ONLY from public evidence", r["disclosure"])
        for other in ROWS:
            if other["slug"] != "hotaisle":
                self.assertNotIn("disclosure", other)

    def test_only_public_evidence(self):
        r = self.row()
        self.assertTrue(r["evidence_public_only"])
        self.assertTrue(r["evidence"])
        for e in r["evidence"]:
            self.assertIn(e["kind"], rate.PUBLIC_KINDS, e["id"])
            blob = json.dumps(e).lower()
            for banned in ("run3", "run 3", "run1", "records/", "counter_record", "telemetry", "invoice", "private"):
                self.assertNotIn(banned, blob, e["id"])
            if e["kind"] == "claim":
                self.assertTrue(e["id"].startswith("cmcr-hotaisle-"), e["id"])
            if e["kind"] == "surface":
                self.assertTrue(e["id"].startswith("surf:hotaisle:"), e["id"])
            if e["kind"] == "campaign_public_listing":
                self.assertIn("http", e.get("detail", ""))          # source is a public pricing URL
        for e in INP["campaign"]["hotaisle"]:
            self.assertTrue(e["source_url"].startswith("https://"), e["offer_id"])

    def test_row_content(self):
        r = self.row()
        self.assertEqual(r["imported_context"]["clustermax_3_0_medal"], "NOT IN 3.0 TABLE")
        self.assertIn("delivery", r["short_dimensions"])
        self.assertIn("cmcr-hotaisle-09", r["dimensions"]["delivery"]["shortfalls"][0]["evidence_ids"])


class Classifier(unittest.TestCase):
    def labels(self, quote, stance=-1, topic="criticism"):
        return sorted({h["label"] for h in rate.classify_claim({"quote": quote, "stance": stance, "topic": topic}) if h["polarity"] == "short"})

    def test_multi_label_sentence(self):
        q = ("At this time, Hot Aisle does not have shared storage, monitoring dashboards, health checks, "
             "modern security practices, RBAC, vertically integrated support, or the ability to run at scale.")
        self.assertEqual(self.labels(q), ["no_health_checks", "no_monitoring", "no_rbac", "no_shared_storage"])

    def test_word_boundary_false_positives(self):
        self.assertEqual(self.labels("Capacity is constrained for Hopper and Blackwell, and the CycleCloud slurm provisioning process needs an update."), [])
        self.assertEqual(self.labels("yet with no mention of EFA or HyperPod/Slurm in the announcement."), [])

    def test_positive_stance_never_short(self):
        self.assertEqual(self.labels("This directly addresses a criticism regarding a lack of monitoring in their offering.", stance=1, topic="praise"), [])

    def test_scope_of_test_is_not_a_gap(self):
        self.assertEqual(self.labels("We have not been able to test kubernetes, or verify any monitoring and health checks in place.", stance=-1, topic="access"), [])


class Prices(unittest.TestCase):
    def test_artefact_rows_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.jsonl"
            rows = []
            for v in (3.36, 3.36, 3.36):
                rows.append({"snapshot_ts": "2026-06-10T00:00:00Z", "provider": "acme", "gpu": "H100", "price_type": "on_demand", "hourly_price_usd": v})
            for v in (3.99, 3.99, 100.0, 100.0, 4.1):
                rows.append({"snapshot_ts": "2026-07-10T00:00:00Z", "provider": "acme", "gpu": "H100", "price_type": "on_demand", "hourly_price_usd": v})
            rows.append({"snapshot_ts": "2026-07-10T00:00:00Z", "provider": "acme", "gpu": "H100", "price_type": "spot", "hourly_price_usd": 0.5})
            p.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows), encoding="utf-8")
            agg = rate.build_price_agg(p)["entries"]["acme|H100"]
            self.assertEqual(agg["rows_dropped_artefact"], 2)
            self.assertEqual(agg["july_median"], 3.99)

    def test_percentile_and_band(self):
        price = {"entries": {("p%d|H100" % i): {"provider": "p%d" % i, "gpu": "H100", "rows_kept": 10, "rows_total": 10,
                                                "rows_dropped_artefact": 0, "june_median": None, "july_median": float(i + 1)} for i in range(10)}}
        gpu, med, pct, n, _ = rate.price_position(price, "p9")
        self.assertEqual((gpu, med, n), ("H100", 10.0, 10))
        self.assertEqual(pct, 100.0)
        _, _, pct0, _, _ = rate.price_position(price, "p0")
        self.assertEqual(pct0, 0.0)
        self.assertIsNone(rate.price_position(price, "missing"))


class Outputs(unittest.TestCase):
    def test_committed_outputs_match_recompute(self):
        j = HERE / "RATINGS.jsonl"
        m = HERE / "RATINGS.md"
        self.assertTrue(j.exists() and m.exists(), "run rate.py first")
        with tempfile.TemporaryDirectory() as d:
            rate.run(out=d)
            self.assertEqual((Path(d) / "RATINGS.jsonl").read_text(encoding="utf-8"), j.read_text(encoding="utf-8"))
            self.assertEqual((Path(d) / "RATINGS.md").read_text(encoding="utf-8"), m.read_text(encoding="utf-8"))
        rows = [json.loads(x) for x in j.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 85)
        keys = [(r["distance_to_floor"], r["unknown_count"], r["provider"].lower()) for r in rows]
        self.assertEqual(keys, sorted(keys))

    def test_md_has_required_sections(self):
        t = (HERE / "RATINGS.md").read_text(encoding="utf-8")
        for h in ("## Table", "## Per-provider blocks", "## Distance to floor against the 3.0 medal"):
            self.assertIn(h, t)
        self.assertIn("Nothing below validates either measure", t)


if __name__ == "__main__":
    unittest.main()
