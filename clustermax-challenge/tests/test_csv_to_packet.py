import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import csv_to_packet  # noqa: E402

TRANSFORM = json.loads((ROOT / 'design' / 'transform.json').read_text(encoding='utf-8'))


def make_header(**overrides):
    header = {
        'study_id': 'unit-test-study',
        'rating_name': 'ClusterMAX',
        'rating_version': '3.0',
        'frozen_at': '2026-01-01T00:00:00Z',
        'minimum_providers': 8,
        'minimum_lift': 0.01,
        'outcome_definition': 'Complete with >=90/100 accepted, p95<=500ms, cost<=$25.',
        'disclosure': {
            'relationship': 'No relationship.',
            'compensation': 'None.',
            'credits': 'None.',
            'special_support': 'None.',
            'editorial_influence': 'None.',
        },
        'binding_rules': {
            'medal_source': 'Official medal table.',
            'rubric_source': 'Official rubric.',
            'tiers': list(TRANSFORM['anchors'].keys()),
        },
        'transform': TRANSFORM,
        'baseline': {
            'description': 'baseline', 'model_sha256': hashlib.sha256(b'baseline').hexdigest(),
            'inputs': ['gpu', 'price'], 'training_providers': ['TRAIN_A'], 'frozen_at': '2025-12-01T00:00:00Z',
        },
        'with_rating': {
            'description': 'with rating', 'model_sha256': hashlib.sha256(b'with_rating').hexdigest(),
            'inputs': ['gpu', 'price', 'rating'], 'training_providers': ['TRAIN_A'], 'frozen_at': '2025-12-01T00:00:00Z',
        },
        'workload_sha256': hashlib.sha256(b'workload').hexdigest(),
        'validator_sha256': hashlib.sha256(b'validator').hexdigest(),
        'gates': {'accepted_min': 90, 'p95_max_ms': 500, 'cost_max_usd': 25.0},
        'binding': {
            'source': {'url': 'https://example.invalid/medals', 'sha256': hashlib.sha256(b's').hexdigest(),
                       'retrieved_utc': '2026-01-02T00:00:00Z'},
            'rubric': {'url': 'https://example.invalid/rubric', 'sha256': hashlib.sha256(b'r').hexdigest(),
                       'retrieved_utc': '2026-01-02T00:00:00Z'},
            'bound_at': '2026-01-02T01:00:00Z',
            'medals': {'PROVIDER_A': 'Gold'},
        },
    }
    header.update(overrides)
    return header


def make_row(**overrides):
    row = {
        'trial_id': 'T1', 'provider_id': 'PROVIDER_A', 'service_id': 'svc', 'region': 'us-east-1',
        'session_id': 'S1', 'predicted_at': '2026-01-01T12:00:00Z', 'p_baseline': '0.7',
        'started_at': '2026-01-03T00:00:00Z', 'finished_at': '2026-01-03T00:10:00Z',
        'status': 'complete', 'accepted': '95', 'attempted': '100', 'p95_ms': '410.5',
        'total_cost_usd': '21.4', 'credits_redeemed_usd': '', 'receipt_ref': 'inv-1',
        'receipt_sha256': hashlib.sha256(b'receipt').hexdigest(),
    }
    row.update(overrides)
    return row


class BuildTests(unittest.TestCase):
    def test_plan_trial_shape(self):
        header = make_header()
        row = make_row()
        trial = csv_to_packet.build_plan_trial(row, header)
        self.assertEqual(trial['trial_id'], 'T1')
        self.assertEqual(trial['customer_role'], 'ordinary_tenant')
        self.assertEqual(trial['support'], 'standard')
        self.assertEqual(trial['p_baseline'], 0.7)
        self.assertEqual(trial['gates'], header['gates'])

    def test_outcome_trial_shape_and_optional_credits(self):
        header = make_header()
        row = make_row()
        trial = csv_to_packet.build_outcome_trial(row, header)
        self.assertEqual(trial['accepted'], 95)
        self.assertEqual(trial['attempted'], 100)
        self.assertEqual(trial['p95_ms'], 410.5)
        self.assertEqual(trial['credits_redeemed_usd'], 0.0)

    def test_null_p95_for_missing_value(self):
        header = make_header()
        row = make_row(p95_ms='')
        trial = csv_to_packet.build_outcome_trial(row, header)
        self.assertIsNone(trial['p95_ms'])

    def test_duplicate_trial_id_rejected(self):
        header = make_header()
        rows = [make_row(), make_row()]
        with self.assertRaises(csv_to_packet.ConversionError):
            csv_to_packet.build(rows, header)

    def test_missing_header_field_rejected(self):
        header = make_header()
        del header['gates']
        with self.assertRaises(csv_to_packet.ConversionError):
            csv_to_packet.build([make_row()], header)

    def test_hash_cross_references(self):
        header = make_header()
        rows = [make_row()]
        plan_bytes, binding_bytes, outcomes_bytes = csv_to_packet.build(rows, header)
        plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
        binding_sha256 = hashlib.sha256(binding_bytes).hexdigest()
        binding = json.loads(binding_bytes)
        outcomes = json.loads(outcomes_bytes)
        self.assertEqual(binding['plan_sha256'], plan_sha256)
        self.assertEqual(outcomes['plan_sha256'], plan_sha256)
        self.assertEqual(outcomes['binding_sha256'], binding_sha256)

    def test_transform_sha256_matches_canonical_algorithm(self):
        header = make_header()
        plan_bytes, _, _ = csv_to_packet.build([make_row()], header)
        plan = json.loads(plan_bytes)
        expected = csv_to_packet.canonical_sha256(header['transform'])
        self.assertEqual(plan['transform_sha256'], expected)

    def test_output_is_lf_only(self):
        header = make_header()
        plan_bytes, binding_bytes, outcomes_bytes = csv_to_packet.build([make_row()], header)
        for b in (plan_bytes, binding_bytes, outcomes_bytes):
            self.assertNotIn(b'\r\n', b)


class CliRoundTripTests(unittest.TestCase):
    """End-to-end: CSV + header -> csv_to_packet.py CLI -> feed straight into
    scripts/challenge.py's CLI via subprocess. We only assert the pipeline
    runs and scripts/challenge.py returns parseable JSON with a status field
    -- not a particular status -- since challenge.py's exact rules may change
    concurrently with this test."""

    def test_cli_round_trip_produces_scoreable_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            header_path = tmp / 'header.json'
            csv_path = tmp / 'jobs.csv'
            header_path.write_text(json.dumps(make_header()), encoding='utf-8')
            with csv_path.open('w', encoding='utf-8', newline='') as fh:
                writer = csv.DictWriter(fh, fieldnames=csv_to_packet.CSV_COLUMNS)
                writer.writeheader()
                writer.writerow({k: v for k, v in make_row().items() if k in csv_to_packet.CSV_COLUMNS})

            plan_out, binding_out, outcomes_out = tmp / 'plan.json', tmp / 'binding.json', tmp / 'outcomes.json'
            proc = subprocess.run(
                [sys.executable, str(ROOT / 'scripts' / 'csv_to_packet.py'),
                 '--csv', str(csv_path), '--header', str(header_path),
                 '--plan-out', str(plan_out), '--binding-out', str(binding_out),
                 '--outcomes-out', str(outcomes_out)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(plan_out.exists() and binding_out.exists() and outcomes_out.exists())

            scorer = subprocess.run(
                [sys.executable, str(ROOT / 'scripts' / 'challenge.py'),
                 '--plan', str(plan_out), '--binding', str(binding_out), '--outcomes', str(outcomes_out)],
                capture_output=True, text=True)
            self.assertIn(scorer.returncode, (0, 2), msg=scorer.stdout + scorer.stderr)
            result = json.loads(scorer.stdout)
            self.assertIn('status', result)


def make_multi_provider_header(**overrides):
    """An 8-provider, floor-meeting cohort header. rating_version is
    deliberately *not* the registered '3.0' -- see design/registry.json -- so
    the binding is scored source_unverified and no exact-provider-name /
    registered-transcription check applies; that check is exercised
    separately (see tests/test_challenge.py)."""
    medals = {f'PROVIDER_{chr(65 + i)}': csv_to_packet._challenge.MEDALS[i % 5] for i in range(8)}
    header = make_header(
        rating_version='9.9',
        binding={
            'source': {'url': 'https://example.invalid/medals', 'sha256': hashlib.sha256(b's').hexdigest(),
                       'retrieved_utc': '2026-01-01T06:00:00Z'},
            'rubric': {'url': 'https://example.invalid/rubric', 'sha256': hashlib.sha256(b'r').hexdigest(),
                       'retrieved_utc': '2026-01-01T06:00:00Z'},
            'bound_at': '2026-01-01T12:00:00Z',
            'medals': medals,
        },
        frozen_at='2026-01-01T00:00:00Z',
    )
    header.update(overrides)
    return header


def make_multi_provider_rows():
    """10 trials x 8 providers, 5 distinct sessions and 3 distinct UTC dates
    per provider -- exactly clears every v1.4 coverage floor."""
    rows = []
    for i in range(8):
        provider = f'PROVIDER_{chr(65 + i)}'
        for n in range(10):
            day = 3 + (n % 3)
            rows.append(make_row(
                trial_id=f'{provider}-T{n + 1:02d}', provider_id=provider,
                session_id=f'S{(n % 5) + 1}', predicted_at='2025-12-31T12:00:00Z',
                started_at=f'2026-01-{day:02d}T00:00:00Z', finished_at=f'2026-01-{day:02d}T00:10:00Z',
            ))
    return rows


def write_csv(csv_path: Path, rows):
    with csv_path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_to_packet.CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in row.items() if k in csv_to_packet.CSV_COLUMNS})


def run_csv_to_packet(tmp: Path, header: dict, rows) -> tuple[Path, Path, Path]:
    header_path, csv_path = tmp / 'header.json', tmp / 'jobs.csv'
    header_path.write_text(json.dumps(header), encoding='utf-8')
    write_csv(csv_path, rows)
    plan_out, binding_out, outcomes_out = tmp / 'plan.json', tmp / 'binding.json', tmp / 'outcomes.json'
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'csv_to_packet.py'),
         '--csv', str(csv_path), '--header', str(header_path),
         '--plan-out', str(plan_out), '--binding-out', str(binding_out),
         '--outcomes-out', str(outcomes_out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return plan_out, binding_out, outcomes_out


def run_challenge(plan_out: Path, binding_out: Path, outcomes_out: Path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'challenge.py'),
         '--plan', str(plan_out), '--binding', str(binding_out), '--outcomes', str(outcomes_out)],
        capture_output=True, text=True)
    return proc, json.loads(proc.stdout) if proc.stdout.strip() else {}


class MultiProviderCliRoundTripTests(unittest.TestCase):
    """A full 8-provider, coverage-floor-meeting cohort taken through the real
    submitter pipeline: CSV + header -> `python scripts/csv_to_packet.py` ->
    `python scripts/challenge.py`. Unlike CliRoundTripTests above (one
    provider, always HOLD on the provider-count floor regardless of anything
    else), this exercises an otherwise-valid v1.4 packet end to end."""

    def test_valid_cohort_is_not_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan_out, binding_out, outcomes_out = run_csv_to_packet(
                tmp, make_multi_provider_header(), make_multi_provider_rows())
            proc, result = run_challenge(plan_out, binding_out, outcomes_out)
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertNotEqual(result.get('status'), 'HOLD', msg=result)
            self.assertEqual(result.get('providers'), 8)
            self.assertEqual(result.get('source_verification'), 'source_unverified')

    def test_gate_mismatch_holds(self):
        """gates must be byte-identical across every trial sharing a
        workload_sha256 (all trials here share the one header-level
        workload_sha256); a single trial with a different cost gate must
        HOLD the whole packet, not just that row."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan_out, binding_out, outcomes_out = run_csv_to_packet(
                tmp, make_multi_provider_header(), make_multi_provider_rows())

            plan = json.loads(plan_out.read_bytes())
            plan['trials'][5]['gates'] = dict(plan['trials'][5]['gates'], cost_max_usd=999.0)
            plan_bytes = csv_to_packet.dump_bytes(plan)
            plan_out.write_bytes(plan_bytes)
            plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()

            binding = json.loads(binding_out.read_bytes())
            binding['plan_sha256'] = plan_sha256
            binding_bytes = csv_to_packet.dump_bytes(binding)
            binding_out.write_bytes(binding_bytes)
            binding_sha256 = hashlib.sha256(binding_bytes).hexdigest()

            outcomes = json.loads(outcomes_out.read_bytes())
            outcomes['plan_sha256'] = plan_sha256
            outcomes['binding_sha256'] = binding_sha256
            outcomes_out.write_bytes(csv_to_packet.dump_bytes(outcomes))

            proc, result = run_challenge(plan_out, binding_out, outcomes_out)
            self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
            self.assertEqual(result.get('status'), 'HOLD')
            self.assertIn('gates differ', result.get('reason', ''))


class TemplatesAreHashConsistent(unittest.TestCase):
    """submissions/templates/{plan,binding,outcomes}.template.json are a
    hand-shipped worked example -- they must stay hash-consistent with each
    other even though they will never independently pass evaluate() (one
    trial, one provider, well under every coverage floor)."""

    def test_templates_cross_reference_correctly(self):
        templates = ROOT / 'submissions' / 'templates'
        plan_bytes = (templates / 'plan.template.json').read_bytes()
        binding_bytes = (templates / 'binding.template.json').read_bytes()
        binding = json.loads(binding_bytes)
        outcomes = json.loads((templates / 'outcomes.template.json').read_bytes())
        self.assertEqual(binding['plan_sha256'], hashlib.sha256(plan_bytes).hexdigest())
        self.assertEqual(outcomes['plan_sha256'], hashlib.sha256(plan_bytes).hexdigest())
        self.assertEqual(outcomes['binding_sha256'], hashlib.sha256(binding_bytes).hexdigest())

    def test_templates_are_lf_only(self):
        templates = ROOT / 'submissions' / 'templates'
        for name in ('plan.template.json', 'binding.template.json', 'outcomes.template.json'):
            self.assertNotIn(b'\r\n', (templates / name).read_bytes(), msg=name)

    def test_templates_run_through_challenge_cli(self):
        templates = ROOT / 'submissions' / 'templates'
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'challenge.py'),
             '--plan', str(templates / 'plan.template.json'),
             '--binding', str(templates / 'binding.template.json'),
             '--outcomes', str(templates / 'outcomes.template.json')],
            capture_output=True, text=True)
        self.assertIn(proc.returncode, (0, 2), msg=proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertIn('status', result)


if __name__ == '__main__':
    unittest.main()
