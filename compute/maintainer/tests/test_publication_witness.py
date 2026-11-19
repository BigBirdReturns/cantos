"""Source-bound GitHub CI/Pages and exact recipient-byte publication tests; offline."""
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from compute.maintainer import publication_witness as w


class PublicationWitnessTests(unittest.TestCase):
    sha = "a" * 40
    digest = "b" * 64
    size = 1234

    def expected(self):
        return w.expectation(self.sha, self.digest, self.size)

    def run_record(self, ident, event, conclusion="success", status="completed",
            sha=None, created="2026-11-18T00:00:00Z", attempt=1):
        return {"id": ident, "head_sha": sha or self.sha,
                "event": event, "conclusion": conclusion, "status": status,
                "created_at": created, "run_attempt": attempt,
                "html_url": "https://github.com/BigBirdReturns/cantos/actions/runs/" + str(ident)}

    def observations(self):
        return {
            "main_sha": self.sha,
            "qualify_runs": [self.run_record(1, "push")],
            "pages_runs": [self.run_record(2, "workflow_run")],
            "served_kit": {"url": w.PAGES_URL, "effective_url": w.PAGES_URL,
                           "http_status": 200, "bytes": self.size,
                           "sha256": self.digest},
            "api_evidence": []
        }

    def decision(self, obs=None):
        return w.evaluate(self.expected(), obs or self.observations())

    def test_exact_current_source_ci_pages_and_bytes_pass(self):
        self.assertEqual(self.decision()["state"], "PASS")

    def test_mismatched_public_main_holds_even_with_green_ci(self):
        obs = self.observations()
        obs["main_sha"] = "c" * 40
        self.assertIn("main_commit_mismatch", self.decision(obs)["findings"])
        self.assertEqual(self.decision(obs)["state"], "HOLD")

    def test_old_green_does_not_bless_new_commit(self):
        obs = self.observations()
        obs["qualify_runs"][0]["head_sha"] = "c" * 40
        self.assertEqual(self.decision(obs)["state"], "WAIT")
        self.assertIn("qualification_missing", self.decision(obs)["findings"])

    def test_newer_failed_qualification_overrides_earlier_green(self):
        obs = self.observations()
        obs["qualify_runs"].append(self.run_record(3, "push", "failure",
            created="2026-11-18T01:00:00Z"))
        self.assertEqual(self.decision(obs)["state"], "HOLD")
        self.assertEqual(self.decision(obs)["qualification_run_id"], 3)

    def test_newer_pending_pages_holds_activation_in_wait(self):
        obs = self.observations()
        obs["pages_runs"].append(self.run_record(4, "workflow_run", None, "in_progress",
            created="2026-11-18T01:00:00Z"))
        self.assertEqual(self.decision(obs)["state"], "WAIT")

    def test_retry_attempt_order_picks_later_attempt(self):
        obs = self.observations()
        obs["qualify_runs"].append(self.run_record(1, "push", "failure", attempt=2))
        self.assertEqual(self.decision(obs)["state"], "HOLD")
        self.assertEqual(self.decision(obs)["qualification_attempt"], 2)

    def test_ignored_pull_request_status(self):
        obs = self.observations()
        obs["qualify_runs"] = [self.run_record(7, "pull_request")]
        self.assertEqual(self.decision(obs)["state"], "WAIT")

    def test_served_digest_and_bytes_must_both_match(self):
        for key, value in (("sha256", "c" * 64), ("bytes", 1233)):
            with self.subTest(key=key):
                obs = self.observations()
                obs["served_kit"][key] = value
                self.assertEqual(self.decision(obs)["state"], "HOLD")

    def test_external_redirect_rejected(self):
        obs = self.observations()
        obs["served_kit"]["effective_url"] = "https://elsewhere.invalid/kit.zip"
        with self.assertRaisesRegex(w.WitnessError, "redirect"):
            self.decision(obs)

    def test_response_http_failure_holds(self):
        obs = self.observations()
        obs["served_kit"]["http_status"] = 404
        self.assertEqual(self.decision(obs)["state"], "HOLD")

    def test_missing_fields_and_unbounded_rows_rejected(self):
        obs = self.observations()
        obs["qualify_runs"] = [{}]
        with self.assertRaises(w.WitnessError):
            self.decision(obs)
        obs["qualify_runs"] = [self.run_record(i + 1, "push") for i in range(101)]
        with self.assertRaisesRegex(w.WitnessError, "bounded"):
            self.decision(obs)

    def test_false_positive_verdict_cannot_replay(self):
        obs = self.observations()
        doc = {"schema": "cantos.publication-witness/1", "expected": self.expected(),
               "observed": obs, "decision": self.decision(obs)}
        raw = w.canonical(doc)
        pin = sha256(raw).hexdigest()
        self.assertEqual(w.verify(raw, pin)["state"], "PASS")
        with self.assertRaisesRegex(w.WitnessError, "SHA-256"):
            w.verify(raw + b" ", pin)
        doc["decision"]["state"] = "HOLD"
        altered = w.canonical(doc)
        with self.assertRaisesRegex(w.WitnessError, "decision"):
            w.verify(altered, sha256(altered).hexdigest())

    def test_bounded_authorized_remote_collection(self):
        obs = self.observations()
        apis = [
            ({"object": {"sha": self.sha}}, {"url": "a"}),
            ({"workflow_runs": obs["qualify_runs"]}, {"url": "b"}),
            ({"workflow_runs": obs["pages_runs"]}, {"url": "c"})
        ]
        kit = {"effective_url": w.PAGES_URL, "status": 200, "raw": b"test"}
        with patch.object(w, "api_json", side_effect=apis) as mocked, patch.object(
            w, "get", return_value=kit
        ) as network:
            observed = w.observe(self.expected())
        self.assertEqual(mocked.call_count, 3)
        self.assertIn("head_sha=" + self.sha, mocked.call_args_list[1].args[0])
        network.assert_called_once_with(w.PAGES_URL, max_bytes=w.MAX_KIT_BYTES)
        self.assertEqual(observed["served_kit"]["sha256"], sha256(b"test").hexdigest())


if __name__ == "__main__":
    unittest.main()
