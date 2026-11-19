from hashlib import sha256
import csv
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from compute.maintainer.provider_cur import (
    CURAuditError, audit, pinned, SESSION_SCHEMA
)

COLS = ["identity/LineItemId", "lineItem/UsageAccountId", "lineItem/ResourceId",
        "lineItem/LineItemType", "lineItem/UsageStartDate", "lineItem/UsageEndDate",
        "lineItem/CurrencyCode", "lineItem/UnblendedCost"]
ACCOUNT = "123456789012"
RESOURCE = "i-0123456789abcdef0"


def line(i="line-1", a=ACCOUNT, r=RESOURCE, kind="Usage",
         start="2026-11-19T01:00:00Z", end="2026-11-19T02:00:00Z", cost="0.123456789"):
    return dict(zip(COLS, (i, a, r, kind, start, end, "USD", cost)))


def export(rows):
    text = StringIO()
    writer = csv.DictWriter(text, fieldnames=COLS)
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode()


def manifest():
    return {"schema": SESSION_SCHEMA, "sessions": [{
        "session_id": "job-a", "account_id": ACCOUNT, "resource_id": RESOURCE,
        "start_utc": "2026-11-19T00:00:00Z",
        "end_utc": "2026-11-19T03:00:00Z",
        "observation_sha256": "1" * 64,
    }]}


def run(rows, document=None):
    c = export(rows)
    m = json.dumps(manifest() if document is None else document).encode()
    return audit(c, sha256(c).hexdigest(), m, sha256(m).hexdigest())


class TestAWSCUR(unittest.TestCase):
    def test_decimal_exact_and_source_class(self):
        r = run([line(), line(i="line-2", cost="0.01")])
        self.assertEqual(r["sessions"]["job-a"]["unblended_usage_usd"], "0.133456789")
        self.assertEqual(r["counts"]["matched"], 2)
        self.assertEqual(r["verdict"], "direct_usage_subset")
        self.assertIn("not_AWS_authenticated", r["evidence_class"])
        self.assertEqual(r["scope"]["export_completeness"], "unknown")

    def test_partial_overlap_does_not_prorate(self):
        r = run([line(start="2026-11-18T23:00:00Z")])
        self.assertEqual(r["counts"]["held_target"], 1)
        self.assertEqual(r["totals"]["direct_usage_usd"], "0")
        self.assertEqual(r["verdict"], "hold_unresolved_allocation")

    def test_reservation_fee_held(self):
        r = run([line(kind="RIFee", cost="19.25")])
        self.assertEqual(r["held_charge_types"]["RIFee"], 1)
        self.assertEqual(r["totals"]["unattributed_usd"], "19.25")
        self.assertEqual(r["verdict"], "hold_unresolved_allocation")

    def test_missing_resource_held(self):
        r = run([line(r="")])
        self.assertEqual(r["counts"]["missing_resource_id"], 1)
        self.assertEqual(r["verdict"], "hold_unresolved_allocation")

    def test_unrelated_cost_unallocated(self):
        r = run([line(a="222222222222")])
        self.assertEqual(r["counts"]["other_account_or_resource"], 1)
        self.assertEqual(r["totals"]["unattributed_usd"], "0.123456789")

    def test_duplicate_line_rejected(self):
        with self.assertRaisesRegex(CURAuditError, "duplicate"):
            run([line(), line()])

    def test_nonfinite_cost_rejected(self):
        with self.assertRaisesRegex(CURAuditError, "nonfinite"):
            run([line(cost="NaN")])

    def test_overlap_manifest_rejected(self):
        m = manifest()
        second = dict(m["sessions"][0])
        second["session_id"] = "job-b"
        m["sessions"].append(second)
        with self.assertRaisesRegex(CURAuditError, "overlapping"):
            run([line()], m)

    def test_wrong_currency_rejected(self):
        row = line()
        row["lineItem/CurrencyCode"] = "EUR"
        with self.assertRaisesRegex(CURAuditError, "USD-only"):
            run([row])

    def test_wrong_pin_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            file = Path(t) / "cur.csv"
            file.write_bytes(export([line()]))
            with self.assertRaisesRegex(CURAuditError, "SHA-256 mismatch"):
                pinned(file, "0" * 64, 10000)

    def test_outside_session_held(self):
        r = run([line(start="2026-11-19T04:00:00Z", end="2026-11-19T05:00:00Z")])
        self.assertEqual(r["counts"]["held_target"], 1)

    def test_source_pin_tampering(self):
        c = export([line()])
        m = json.dumps(manifest()).encode()
        with self.assertRaisesRegex(CURAuditError, "CUR SHA-256"):
            audit(c + b" ", sha256(c).hexdigest(), m, sha256(m).hexdigest())


if __name__ == "__main__":
    unittest.main()
