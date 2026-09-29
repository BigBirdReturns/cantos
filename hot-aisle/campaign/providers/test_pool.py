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


def reconciles(test, part):
    test.assertEqual(sum(u["charge_cents"] for u in part["schedule"]), part["pool_cost_cents"])
    test.assertEqual(sum(s["share_cents"] for s in part["shares"]), part["pool_cost_cents"])
    test.assertEqual(round(part["pool_cost_cents"] / 100, 2), part["pool_cost_usd"])


class Charges(unittest.TestCase):
    """Boundary failures found on 43f42bf; see round2/opus/probe-before.json."""

    def test_cents_reconcile_to_the_rounded_bill_by_largest_remainder(self):
        rows = [offer("u-3", gpus=3, rate=0.3333333), offer("s-1", gpus=1, rate=2.0)]
        part = pool.plan(request(member("a"), member("b"), member("c")), rows)["plans"][0]["all_accepting"]
        self.assertEqual(part["pool_cost_cents"], 1000)  # 3 x 0.3333333 x 10 h = 9.999999
        self.assertEqual([s["share_cents"] for s in part["shares"]], [334, 333, 333])  # tie goes to lowest id
        reconciles(self, part)

    def test_per_unit_rounding_is_not_negative_idle_cost(self):
        rows = [offer("tiny-2", gpus=2, rate=1.0, minimum="1 second"),
                offer("single-1", gpus=1, rate=2.0, minimum="1 second")]
        req = request(*[member("m%d" % i, hours=0.002) for i in range(4)])
        p = pool.plan(req, rows)["plans"][0]["all_accepting"]
        self.assertEqual(p["idle_gpu_hours"], 0)
        self.assertEqual(p["idle_cost_usd"], 0)
        self.assertEqual(p["pool_cost_cents"], 0)
        self.assertEqual(p["cost_components_cents"]["per_unit_rounding_adjustment"], -1)
        self.assertEqual(sum(p["cost_components_cents"].values()), p["pool_cost_cents"])
        reconciles(self, p)

    def test_money_is_exact_decimal_not_binary_float(self):
        rows = [offer("u-2", gpus=2, rate=1.99, minimum="1 hour"), offer("s-1", gpus=1, rate=2.49)]
        part = pool.plan(request(member("a", hours=7), member("b", hours=7)), rows)["plans"][0]["all_accepting"]
        self.assertEqual((part["pool_cost_cents"], [s["share_cents"] for s in part["shares"]]), (2786, [1393, 1393]))

    def test_many_irregular_pools_always_reconcile(self):
        for rate in (0.3333333, 1.11, 1.99, 2.59, 6.155):
            for gpus in (2, 3, 8):
                members = [member("m%d" % i, gpus=1 + i % 2, hours=1.7 + 3.3 * i, window_hours=40)
                           for i in range(7)]
                rows = [offer("u-%d" % gpus, gpus=gpus, rate=rate, minimum="20 minutes"),
                        offer("s-1", gpus=1, rate=rate * 1.3), offer("s-2", gpus=2, rate=rate * 1.2)]
                for p in pool.plan(request(*members), rows)["plans"]:
                    for part in (p["all_accepting"], p["coalition"]):
                        if part is not None:
                            with self.subTest(rate=rate, gpus=gpus, offer=p["offer_id"]):
                                reconciles(self, part)

    def test_each_whole_unit_is_released_when_its_last_member_ends(self):
        members = [*[member("long%d" % i, hours=100) for i in range(8)], *[member("s%d" % i) for i in range(8)]]
        part = pool.plan(request(*members), [offer("big-8", rate=1.0), offer("s-1", gpus=1, rate=2.0)])["plans"][0]
        part = part["all_accepting"]
        self.assertEqual([u["charge_cents"] for u in part["schedule"]], [80000, 8000])  # was 2 x $800
        self.assertEqual((part["pool_cost_usd"], part["utilization"]), (880.0, 1.0))

    def test_tight_window_is_not_pushed_onto_a_second_minimum_billed_unit(self):
        members = [member("tight", hours=10, window_hours=10), member("long", hours=20, window_hours=168)]
        part = pool.plan(request(*members), [offer("mo-1", gpus=1, rate=1.0, minimum="1 month")])["plans"][0]
        part = part["all_accepting"]
        self.assertEqual((part["units"], part["pool_cost_usd"]), (1, 730.0))  # was 2 units, $1,460
        self.assertEqual([(r["member"], r["start_hour"]) for r in part["schedule"][0]["runs"]],
                         [("tight", 0.0), ("long", 10.0)])


class Qualifications(unittest.TestCase):
    def test_held_cheapest_reference_travels_into_the_conclusion(self):
        rows = [offer("big-8", rate=1.0), offer("cheap-1", gpus=1, rate=1.2, availability_observed="out_of_stock"),
                offer("ok-1", gpus=1, rate=2.0)]
        result = pool.plan(request(*[member("m%d" % i) for i in range(8)]), rows)
        self.assertEqual(result["standalone"]["m0"]["offer_id"], "cheap-1")
        self.assertEqual(result["standalone_unqualified"]["m0"]["offer_id"], "ok-1")
        p = result["plans"][0]
        verdict = p["conclusion"]
        self.assertEqual(verdict["status"], "conditional")
        self.assertTrue(verdict["no_worse_vs_unqualified_references"])
        self.assertEqual({q["scope"] for q in verdict["qualifications"]}, {"reference:m%d" % i for i in range(8)})
        self.assertTrue(all("out_of_stock" in q["hold"] for q in verdict["qualifications"]))
        share = p["coalition"]["shares"][0]
        self.assertEqual((share["saving_vs_standalone_usd"], share["saving_vs_unqualified_usd"]), (2.0, 10.0))

    def test_unknown_pool_minimum_makes_the_bill_a_lower_bound(self):
        rows = [offer("mystery-8", rate=1.0, minimum="unknown"), offer("ok-1", gpus=1, rate=2.0)]
        verdict = pool.plan(request(*[member("m%d" % i) for i in range(8)]), rows)["plans"][0]["conclusion"]
        self.assertTrue(verdict["arithmetic_no_worse"])
        self.assertTrue(verdict["pool_bill_is_lower_bound"])
        self.assertEqual(verdict["status"], "conditional")
        self.assertEqual(verdict["qualifications"][0]["effect"], pool.POOL_SIDE)

    def test_unqualified_list_arithmetic_still_has_no_authority(self):
        rows = [offer("big-8", rate=1.0), offer("ok-1", gpus=1, rate=2.0)]
        p = pool.plan(request(*[member("m%d" % i) for i in range(8)]), rows)["plans"][0]
        self.assertEqual(p["conclusion"]["status"], "modeled_no_worse")
        self.assertEqual(p["conclusion"]["qualifications"], [])
        self.assertFalse(p["bindable_at_list"])
        self.assertFalse(p["execution_authority"])

    def test_no_unqualified_alternative_leaves_the_comparison_open(self):
        rows = [offer("spot-8", rate=0.5, kind="spot"), offer("spot-1", gpus=1, rate=1.0, kind="spot")]
        members = [member("m%d" % i, kinds=["spot"]) for i in range(8)]
        verdict = pool.plan(request(*members), rows)["plans"][0]["conclusion"]
        self.assertIsNone(verdict["no_worse_vs_unqualified_references"])
        self.assertEqual(len(verdict["members_without_unqualified_reference"]), 8)


class StagedCharges(unittest.TestCase):
    def test_committed_offers_reconcile_and_carry_conclusions(self):
        rows = pool.load_rows(HERE / "providers.jsonl")
        with open(HERE.parents[2] / "integration/examples/pool-request.json", encoding="utf-8") as stream:
            import json
            example = json.load(stream)
        dense = request(*[member("m%d" % i, hours=168, kinds=["on-demand", "spot"]) for i in range(8)])
        for req in (example, dense):
            result = pool.plan(req, rows)
            for p in result["plans"]:
                self.assertFalse(p["bindable_at_list"] or p["execution_authority"])
                self.assertIn(p["conclusion"]["status"], ("no_coalition", "not_no_worse", "conditional", "modeled_no_worse"))
                for part in (p["all_accepting"], p["coalition"]):
                    if part is not None:
                        reconciles(self, part)


if __name__ == "__main__":
    unittest.main()
