from hashlib import sha256
from io import StringIO
import csv
import json
from pathlib import Path
from pathlib import PurePosixPath
from zipfile import ZipFile
import tempfile
import unittest
from unittest.mock import patch

from compute.maintainer.provider_cost_join import audit, JOIN_SCHEMA
from compute.maintainer.provider_cur import CURAuditError, SESSION_SCHEMA


ACCOUNT = "123456789012"
COLS = [
    "identity/LineItemId", "lineItem/UsageAccountId", "lineItem/ResourceId",
    "lineItem/LineItemType", "lineItem/UsageStartDate", "lineItem/UsageEndDate",
    "lineItem/CurrencyCode", "lineItem/UnblendedCost"
]


def canonical(obj):
    return json.dumps(obj, sort_keys=True).encode()


def fixture(receipt_hash, partial=False):
    source = {"schema": SESSION_SCHEMA, "sessions": []}
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=COLS)
    writer.writeheader()
    for arm, i in (("baseline", 1), ("candidate", 2)):
        source["sessions"].append(dict(
            session_id=arm, account_id=ACCOUNT, resource_id="i-" + str(i),
            observation_sha256=receipt_hash,
            start_utc="2026-11-19T01:00:00Z", end_utc="2026-11-19T03:00:00Z"))
        writer.writerow(dict(zip(COLS, [arm, ACCOUNT, "i-" + str(i), "Usage",
            "2026-11-19T00:30:00Z" if partial and i == 2 else "2026-11-19T01:00:00Z",
            "2026-11-19T02:00:00Z", "USD", "1.25" if i == 1 else "2.50"])))
    bind = {"schema": JOIN_SCHEMA, "campaign_receipt_sha256": receipt_hash,
            "bindings": [{"arm": arm, "session_id": arm} for arm in ("baseline", "candidate")]}
    return output.getvalue().encode(), canonical(source), canonical(bind)


def observed(*args, **kwargs):
    return {"observed": {"arms": {
        "baseline": {"accepted": 2, "attempts": 3},
        "candidate": {"accepted": 5, "attempts": 6}}}}


class CostJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.campaign = Path(self.tmp.name)
        (self.campaign / "VLLM-EMPIRICAL-RECEIPT.json").write_text('{"fixture":true}')
        self.campaign_hash = sha256((self.campaign / "VLLM-EMPIRICAL-RECEIPT.json").read_bytes()).hexdigest()

    def run_audit(self, partial=False, mutate=None):
        cur, sessions, bind = fixture(self.campaign_hash, partial)
        if mutate:
            cur, sessions, bind = mutate(cur, sessions, bind)
        with patch("compute.maintainer.provider_cost_join.empirical_audit", side_effect=observed):
            return audit(cur, sha256(cur).hexdigest(), sessions, sha256(sessions).hexdigest(),
                         bind, sha256(bind).hexdigest(), self.campaign)

    def test_exact_decimal_join_with_grader_counts(self):
        out = self.run_audit()
        self.assertEqual(out["arms"]["baseline"]["unblended_usage_subset_usd_per_accepted"], "0.625")
        self.assertEqual(out["arms"]["candidate"]["unblended_usage_subset_usd_per_accepted"], "0.50")
        self.assertEqual(out["arms"]["candidate"]["accepted_attempts"], 5)
        self.assertIn("operator_pinned", out["evidence_class"])

    def test_held_partial_interval_cannot_emit_ratio(self):
        out = self.run_audit(partial=True)
        self.assertEqual(out["arms"]["candidate"]["status"], "hold_uncovered_or_zero_accepted")
        self.assertIsNone(out["arms"]["baseline"]["unblended_usage_subset_usd_per_accepted"])
        self.assertEqual(out["cur_counts"]["held_target"], 1)

    def test_wrong_campaign_receipt_cannot_bind(self):
        def mutate(c, s, b):
            doc = json.loads(b)
            doc["campaign_receipt_sha256"] = "0" * 64
            return c, s, canonical(doc)
        with self.assertRaisesRegex(CURAuditError, "campaign receipt"):
            self.run_audit(mutate=mutate)

    def test_wrong_resource_observation_cannot_bind(self):
        def mutate(c, s, b):
            doc = json.loads(s)
            doc["sessions"][0]["observation_sha256"] = "0" * 64
            return c, canonical(doc), b
        with self.assertRaisesRegex(CURAuditError, "resource session"):
            self.run_audit(mutate=mutate)

    def test_same_session_cannot_double_attribute(self):
        def mutate(c, s, b):
            doc = json.loads(b)
            doc["bindings"][1]["session_id"] = "baseline"
            return c, s, canonical(doc)
        with self.assertRaisesRegex(CURAuditError, "distinct"):
            self.run_audit(mutate=mutate)

    def test_unknown_session_rejected(self):
        def mutate(c, s, b):
            doc = json.loads(b)
            doc["bindings"][1]["session_id"] = "not-a-session"
            return c, s, canonical(doc)
        with self.assertRaisesRegex(CURAuditError, "unknown resource"):
            self.run_audit(mutate=mutate)

    def test_real_retained_grader_join(self):
        archive = Path(__file__).resolve().parents[1] / "evidence/vllm-humaneval-20261118.zip"
        if not archive.exists():
            self.skipTest("optional pinned public empirical archive absent")
        with tempfile.TemporaryDirectory() as work:
            with ZipFile(archive) as z:
                names = z.namelist()
                self.assertTrue(all(".." not in PurePosixPath(n).parts and
                                    not n.startswith("/") for n in names))
                z.extractall(work)
            dirs = list(Path(work).glob("*/VLLM-EMPIRICAL-RECEIPT.json"))
            self.assertEqual(len(dirs), 1)
            campaign = dirs[0].parent
            campaign_hash = sha256(dirs[0].read_bytes()).hexdigest()
            cur, sessions, bind = fixture(campaign_hash)
            from compute.maintainer.empirical_economics import audit as audited
            underlying = audited(campaign)["observed"]["arms"]
            out = audit(cur, sha256(cur).hexdigest(), sessions, sha256(sessions).hexdigest(),
                        bind, sha256(bind).hexdigest(), campaign)
            for arm in ("baseline", "candidate"):
                self.assertEqual(out["arms"][arm]["accepted_attempts"],
                                 underlying[arm]["accepted"])
                self.assertEqual(out["arms"][arm]["attempts"], underlying[arm]["attempts"])
                self.assertEqual(out["arms"][arm]["status"], "subset_observed")

    def test_zero_accepted_is_hold(self):
        def zero(*args, **kwargs):
            d = observed()
            d["observed"]["arms"]["baseline"]["accepted"] = 0
            return d
        cur, sessions, bind = fixture(self.campaign_hash)
        with patch("compute.maintainer.provider_cost_join.empirical_audit", side_effect=zero):
            out = audit(cur, sha256(cur).hexdigest(), sessions, sha256(sessions).hexdigest(),
                        bind, sha256(bind).hexdigest(), self.campaign)
        self.assertIsNone(out["arms"]["baseline"]["unblended_usage_subset_usd_per_accepted"])


if __name__ == "__main__":
    unittest.main()
