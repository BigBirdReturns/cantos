"""Pooling arithmetic checks on synthetic offers plus the staged providers.jsonl."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pool


def offer(offer_id, gpu="MI300X", gpus=8, rate=1.0, kind="on-demand", minimum="1 minute", **extra):
    row = {"provider_id": offer_id.split("-")[0], "provider_name": "Synthetic", "offer_id": offer_id,
           "gpu": gpu, "vendor": "AMD", "memoryGB": 192, "gpus": gpus, "rate_usd_per_gpu_hour": rate,
           "rate_basis": "per_gpu_hour", "kind": kind, "minimum_billing": minimum, "regions": [],
           "self_serve": "yes", "availability_observed": "available", "availability_ts": None,
           "source_url": "https://example.invalid/synthetic", "source_quote": "$" + str(rate),
           "retrieved_at": "2026-09-24T00:00:00Z", "campaign_role": "other", "notes": "synthetic"}
    row.update(extra)
    return row


def member(mid, gpus=1, hours=10.0, **extra):
    return {"id": mid, "gpus": gpus, "hours": hours, "accept_gpu": ["MI300X"], **extra}


def request(*members, **extra):
    return {"schema": "capital/pool-request@1", "members": list(members), **extra}


class Minimums(unittest.TestCase):
    def test_parses_staged_forms(self):
        self.assertEqual(pool.minimum_hours("1 minute"), (1 / 60, None))
        self.assertEqual(pool.minimum_hours("1 month")[0], pool.MONTH_HOURS)
        self.assertIsNone(pool.minimum_hours("unknown (pricing page said one month)")[0])
        hours, note = pool.minimum_hours("5 minutes (pricing page) / 60 seconds (docs)")
        self.assertAlmostEqual(hours, 5 / 60)
        self.assertIn("conflicting", note)
        hours, note = pool.minimum_hours("181+ days")
        self.assertEqual(hours, 181 * 24)
        self.assertIn("open-ended", note)


class Pooling(unittest.TestCase):
    def test_eight_way_unit_beats_single_gpu_list_and_splits_exactly(self):
        rows = [offer("big-8", rate=1.0), offer("small-1", gpus=1, rate=2.0)]
        result = pool.plan(request(*[member("m%d" % i) for i in range(8)]), rows)
        (plan,) = result["plans"]
        coal = plan["coalition"]
        self.assertEqual(coal["units"], 1)
        self.assertEqual(coal["pool_cost_usd"], 80.0)
        self.assertEqual(coal["utilization"], 1.0)
        self.assertEqual(coal["break_even_utilization"], 0.5)
        self.assertEqual(sum(s["share_usd"] for s in coal["shares"]), 80.0)
        self.assertTrue(all(s["saving_vs_standalone_usd"] == 10.0 for s in coal["shares"]))
        self.assertEqual(result["offers_without_pooling_effect"], ["small-1"])

    def test_idle_is_shared_by_gpu_hours_and_worse_off_member_is_dropped(self):
        rows = [offer("big-8", rate=1.0), offer("small-1", gpus=1, rate=1.5)]
        members = [member("long", hours=40), *[member("s%d" % i, hours=10) for i in range(7)]]
        plan = pool.plan(request(*members), rows)["plans"][0]
        full = plan["all_accepting"]
        # 8 GPUs x 40h billed, 110 GPU-hours used: 210 idle GPU-hours at $1.
        self.assertEqual((full["pool_cost_usd"], full["idle_cost_usd"]), (320.0, 210.0))
        self.assertFalse(full["every_member_no_worse"])
        self.assertEqual(plan["dropped_for_coalition"][0], "long")
        self.assertIsNotNone(plan["coalition"])
        self.assertTrue(plan["coalition"]["every_member_no_worse"])

    def test_multi_gpu_member_needs_one_unit_and_windows_allow_back_to_back(self):
        rows = [offer("pair-2", gpus=2, rate=1.0, minimum="1 hour")]
        members = [member("wide", gpus=4), member("a", hours=5, window_hours=10),
                   member("b", hours=5, window_hours=10)]
        plan = pool.plan(request(*members), rows)["plans"][0]["all_accepting"]
        self.assertIn("wide", plan["members_unplaced"])
        self.assertEqual(plan["units"], 1)

    def test_minimum_binds_and_unknowns_are_held(self):
        rows = [offer("month-8", rate=1.0, minimum="1 month"), offer("mystery-8", rate=1.0, minimum="unknown"),
                offer("spot-8", rate=0.5, kind="spot", availability_observed="out_of_stock")]
        members = [member("m%d" % i, kinds=["on-demand", "spot"]) for i in range(8)]
        plans = {p["offer_id"]: p for p in pool.plan(request(*members), rows)["plans"]}
        self.assertEqual(plans["month-8"]["all_accepting"]["billed_hours"], pool.MONTH_HOURS)
        self.assertIsNone(plans["month-8"]["coalition"])
        self.assertIn("minimum billing unknown; billed hours are a lower bound", plans["mystery-8"]["holds"])
        self.assertFalse(plans["spot-8"]["bindable_at_list"])
        self.assertTrue(any("out_of_stock" in h for h in plans["spot-8"]["holds"]))

    def test_rejects_malformed_requests(self):
        for bad in ({"schema": "other", "members": [member("a")]},
                    request(member("a"), member("a")),
                    request(member("a", gpus=True)),
                    request(member("a", hours=10, window_hours=5)),
                    request(member("a"), as_of="yesterday")):
            with self.assertRaises(ValueError):
                pool.validate_request(bad)


class StagedOffers(unittest.TestCase):
    """The committed staging file, read only; figures move if staging is re-merged."""

    def test_committed_offers_run_and_keep_sources(self):
        rows = pool.load_rows(HERE / "providers.jsonl")
        members = [member("m%d" % i, hours=168, kinds=["on-demand", "spot"]) for i in range(8)]
        result = pool.plan(request(*members), rows)
        self.assertEqual(result["offers_considered"] + len(result["offers_excluded"]), len(rows))
        self.assertTrue(result["plans"])
        for p in result["plans"]:
            self.assertTrue(p["source"]["source_url"].strip())  # live TUI rows cite ssh, not a URL
            if p["kind"] == "spot":
                self.assertFalse(p["bindable_at_list"])


class BindingBoundary(unittest.TestCase):
    def test_profitable_list_scenario_never_grants_binding(self):
        for stamp in (None, "2026-09-24T00:00:00Z", "2026-09-27T00:00:00Z"):
            with self.subTest(availability_ts=stamp):
                rows = [offer("big-8", rate=1.0, availability_ts=stamp),
                        offer("small-1", gpus=1, rate=2.0, availability_ts=stamp)]
                p = pool.plan(request(*[member("m%d" % i) for i in range(8)],
                                      as_of="2026-09-27T00:00:00Z"), rows)["plans"][0]
                self.assertTrue(p["arithmetic_no_worse"])
                self.assertEqual(p["coalition"]["total_saving_vs_standalone_usd"], 80.0)
                self.assertFalse(p["bindable_at_list"])
                self.assertIn("reservation", p["binding_status"])


if __name__ == "__main__":
    unittest.main()
