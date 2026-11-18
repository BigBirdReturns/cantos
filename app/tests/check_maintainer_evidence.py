"""Verify retained live evidence through the delivered analyzer and decision engine."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def execute(root, *args, expected=0):
    result = subprocess.run([sys.executable, "-B", *map(str, args)], cwd=root,
                            capture_output=True, text=True, timeout=180)
    if result.returncode != expected:
        raise AssertionError(f"Expected exit {expected}, received {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result

def main():
    evidence_dir = ROOT / "compute/maintainer/evidence"
    digest, name = (evidence_dir / "SHA256SUMS.txt").read_text(encoding="utf-8").split()
    archive = evidence_dir / name
    assert archive.is_file() and sha256(archive.read_bytes()).hexdigest() == digest
    cli = ROOT / "compute/maintainer/maintainer.py"
    bundle = ROOT / "public/open-compute/open-compute-workbench.zip"
    with TemporaryDirectory(prefix="cantos-recipient-evidence-") as temporary:
        target = Path(temporary)
        evidence = target / "evidence"
        with ZipFile(archive) as zipped:
            names = zipped.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
                       and "\\" not in n and ":" not in n for n in names)
            zipped.extractall(evidence)
        evidence = evidence / "cantos-vllm-humaneval-evidence-20261118"
        execute(evidence, evidence / "verify.py")
        base_run = evidence / "vllm-capture/baseline/run.json"
        candidate_run = evidence / "vllm-capture/candidate/run.json"
        arguments = ["--baseline", base_run, "--candidate", candidate_run,
                     "--baseline-grades", evidence / "grade-baseline/grades.json",
                     "--candidate-grades", evidence / "grade-candidate/grades.json"]
        analysis = target / "analysis"
        execute(ROOT, cli, "analyze", *arguments, "--policy", evidence / "policy-vllm.json",
                "--out", analysis, expected=2)
        verdict = read(analysis / "verdict.json")
        assert verdict["verdict"] == "incomparable" and verdict["new_inference_requests"] == 0
        assert verdict["policy"]["min_baseline_acceptance"] == .8
        assert verdict["policy"]["min_candidate_acceptance"] == .8
        for arm in ("baseline", "candidate"):
            assert verdict[arm]["accepted_tasks"] == 21 and verdict[arm]["total_tasks"] == 96
            assert verdict[arm]["estimated_cost"] is None and verdict[arm]["cost_per_accepted"] is None
        exported = target / "export"
        execute(ROOT, cli, "export-packets", "--analysis", analysis, "--bundle", bundle, "--out", exported)
        receipt = read(exported / "workbench-import.json")
        assert receipt["inference_requests"] == 0
        assert receipt["decision"]["status"] == "no_eligible_configuration"
        assert len(receipt["history"]["items"]) == 1 and len(receipt["imports"]) == 2
        assert len(receipt["rows"]) == 2
        for row in receipt["rows"]:
            assert row["accepted"] == 21 and row["offered"] == 96
            assert row["cost_usd"] is None and row["cost_per_1000_accepted_usd"] is None
        for arm, run in (("baseline", base_run), ("candidate", candidate_run)):
            packet = read(exported / arm / "packet.json")
            assert packet["acceptance"]["accepted"] == 21 and packet["acceptance"]["scheduled"] == 96
            assert packet["provenance"]["maintainer"]["verdict"] == "incomparable"
            assert packet["provenance"]["maintainer"]["source_run_sha256"] == sha256(run.read_bytes()).hexdigest()
        # A new price scenario reuses exactly the same observations and retains
        # the original quality floor. A lower cost cannot qualify failed work.
        policy = read(evidence / "policy-vllm.json")
        policy["prices"] = {"baseline_per_hour": 2.0, "candidate_per_hour": 4.0}
        priced_policy = target / "priced-policy.json"
        priced_policy.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        priced_analysis = target / "priced-analysis"
        execute(ROOT, cli, "analyze", *arguments, "--policy", priced_policy, "--out", priced_analysis, expected=2)
        priced = read(priced_analysis / "verdict.json")
        assert priced["new_inference_requests"] == 0 and priced["verdict"] == "incomparable"
        for arm, rate in (("baseline", 2.0), ("candidate", 4.0)):
            assert priced[arm]["accepted_tasks"] == 21 and priced[arm]["cost_assumption_per_hour"] == rate
            assert priced[arm]["estimated_cost"] > 0
        priced_export = target / "priced-export"
        execute(ROOT, cli, "export-packets", "--analysis", priced_analysis, "--bundle", bundle,
                "--policy-prices-usd", "--out", priced_export)
        priced_import = read(priced_export / "workbench-import.json")
        assert priced_import["inference_requests"] == 0
        assert priced_import["decision"]["status"] == "no_eligible_configuration"
        assert all(row["accepted"] == 21 and row["offered"] == 96 for row in priced_import["rows"])
        print(json.dumps({"status":"passed", "observations_per_arm":96, "accepted_per_arm":21,
                          "decision":"no_eligible_configuration", "retained_acceptance_floor":.8,
                          "price_only_scenario":"recalculated_without_inference",
                          "new_inference_requests":0,
                          "scope":"Original and delivered-analyzer validation, source-bound grades, native collector import, decision history and portable packets."}))

if __name__ == "__main__":
    main()
