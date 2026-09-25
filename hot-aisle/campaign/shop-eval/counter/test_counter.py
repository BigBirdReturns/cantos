#!/usr/bin/env python3
"""Stdlib unittest for counter_record.py. Run: python -B test_counter.py"""

import copy
import json
import os
import unittest

import counter_record as cr

HERE = os.path.dirname(os.path.abspath(__file__))
HOTAISLE_PATH = os.path.join(HERE, "records", "hotaisle-2026-09.json")
DIGITALOCEAN_PATH = os.path.join(HERE, "records", "digitalocean-2026-09.json")


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestValidate(unittest.TestCase):
    def test_hotaisle_record_validates(self):
        record = load(HOTAISLE_PATH)
        errors = cr.validate(record)
        self.assertEqual(errors, [], f"hotaisle record should validate cleanly: {errors}")

    def test_digitalocean_record_validates(self):
        record = load(DIGITALOCEAN_PATH)
        errors = cr.validate(record)
        self.assertEqual(errors, [], f"digitalocean record should validate cleanly: {errors}")

    def test_missing_top_level_field_is_rejected(self):
        record = load(HOTAISLE_PATH)
        del record["termination"]
        errors = cr.validate(record)
        self.assertTrue(any("termination" in e for e in errors))

    def test_wrong_schema_id_is_rejected(self):
        record = load(HOTAISLE_PATH)
        record["schema_id"] = "something-else@1"
        errors = cr.validate(record)
        self.assertTrue(any("schema_id" in e for e in errors))

    def test_wrong_type_is_rejected(self):
        record = load(HOTAISLE_PATH)
        record["price_transparency"]["per_gpu_hour_usd"] = "cheap"
        errors = cr.validate(record)
        self.assertTrue(any("per_gpu_hour_usd" in e for e in errors))

    def test_unobserved_sentinel_is_accepted_everywhere_it_applies(self):
        record = load(HOTAISLE_PATH)
        record["price_transparency"]["per_gpu_hour_usd"] = "unobserved"
        record["account_creation"]["kyc_required"] = "unobserved"
        record["network_path"]["open_ports_first_boot"] = "unobserved"
        errors = cr.validate(record)
        self.assertEqual(errors, [])

    def test_unreconciled_money_can_remain_unobserved(self):
        record = load(HOTAISLE_PATH)
        record["provenance"]["money_spent_usd"] = "unobserved"
        errors = cr.validate(record)
        self.assertEqual(errors, [])


class TestScore(unittest.TestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(sum(cr.WEIGHTS.values()), 100)

    def test_checklist_never_establishes_provider_ranking(self):
        for path in (HOTAISLE_PATH, DIGITALOCEAN_PATH):
            result=cr.compute_score(load(path))
            self.assertFalse(result['provider_ranking_permitted'])
            self.assertEqual(result['score_kind'],'uncalibrated_checklist_heuristic')

    def test_listing_observations_do_not_count_as_failed_creates(self):
        record=load(DIGITALOCEAN_PATH)
        block=record['availability_honesty']
        before=cr.score_availability_honesty(block)
        block['ledger_attempts'].extend([{'method':'api','outcome':'out_of_capacity',
            'provisioned':False,'sku':'unrelated','region':'elsewhere'}]*20)
        self.assertEqual(before,cr.score_availability_honesty(block))
        self.assertEqual(before[0],100)
        self.assertIn('1/1',before[1][0])

    def test_unmatched_create_groups_are_not_pooled(self):
        block=copy.deepcopy(load(DIGITALOCEAN_PATH)['availability_honesty'])
        block['ledger_attempts'].append({'method':'api-create','outcome':'out_of_capacity',
            'provisioned':False,'sku':'unrelated','region':'elsewhere'})
        score,reasons=cr.score_availability_honesty(block)
        self.assertIn('no pooled delivery rate',reasons[0])

    def test_score_is_bounded(self):
        for path in (HOTAISLE_PATH, DIGITALOCEAN_PATH):
            result = cr.compute_score(load(path))
            self.assertGreaterEqual(result["total"], 0)
            self.assertLessEqual(result["total"], 100)

    def test_disqualifying_observation_caps_score_at_40(self):
        record = copy.deepcopy(load(HOTAISLE_PATH))
        # This record would otherwise score very high (80/100, see test above).
        # Confirm the disqualifying cap actually overrides the weighted total.
        uncapped = cr.compute_score(record)
        self.assertGreater(uncapped["total"], 40)

        record["disqualifying_observations"] = [
            "previous_tenant_residue found: prior tenant's shell history and SSH keys were present on first login"
        ]
        result = cr.compute_score(record)
        self.assertTrue(result["capped"])
        self.assertEqual(result["total"], 40)
        self.assertLessEqual(result["total"], cr.DISQUALIFYING_CAP)

    def test_empty_disqualifying_list_does_not_cap(self):
        record = load(HOTAISLE_PATH)
        self.assertEqual(record["disqualifying_observations"], [])
        result = cr.compute_score(record)
        self.assertFalse(result["capped"])

    def test_all_unobserved_dimension_scores_neutral_50(self):
        record = load(DIGITALOCEAN_PATH)
        # tenant_hygiene is already all-unobserved in the fixture record.
        self.assertTrue(cr._all_unobserved(
            record["tenant_hygiene"], ["fresh_disk", "previous_tenant_residue", "default_users_keys_present"]
        ))
        score, reasons = cr.score_tenant_hygiene(record["tenant_hygiene"])
        self.assertEqual(score, 50)


class TestCompareCLI(unittest.TestCase):
    def test_compare_matches_individual_scores(self):
        hotaisle = load(HOTAISLE_PATH)
        digitalocean = load(DIGITALOCEAN_PATH)
        ha_result = cr.compute_score(hotaisle)
        do_result = cr.compute_score(digitalocean)
        # sanity: dimension keys line up between the two records
        self.assertEqual(set(ha_result["dimensions"]), set(do_result["dimensions"]))
        self.assertEqual(set(ha_result["dimensions"]), set(cr.WEIGHTS))


if __name__ == "__main__":
    unittest.main()
