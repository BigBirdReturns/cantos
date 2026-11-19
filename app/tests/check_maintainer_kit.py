"""Verify the exact downloadable maintainer kit as an independent recipient."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]

def main():
    release = ROOT / "public/open-compute"
    archive = release / "maintainer-kit.zip"
    digest, name = (release / "MAINTAINER-SHA256SUMS.txt").read_text().split()
    assert name == archive.name and digest == sha256(archive.read_bytes()).hexdigest()
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with ZipFile(archive) as z:
            names = z.namelist()
            assert len(names) == len(set(names))
            assert all(n.startswith("cantos/") and ".." not in PurePosixPath(n).parts and "\\" not in n for n in names)
            manifest_path = "cantos/MAINTAINER-MANIFEST.json"
            manifest = json.loads(z.read(manifest_path))
            assert manifest["schema"] == "cantos.maintainer-kit/1"
            files = manifest["files"]
            assert set(names) == {"cantos/" + p for p in files} | {manifest_path}
            for path, record in files.items():
                data = z.read("cantos/" + path)
                assert len(data) == record["bytes"] and sha256(data).hexdigest() == record["sha256"], path
            encoded = json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
            assert sha256(encoded).hexdigest() == manifest["source_tree_sha256"]
            z.extractall(root)
        kit = root / "cantos"
        def call(*args):
            proc = subprocess.run([sys.executable, "-B", *args], cwd=kit, text=True, capture_output=True, timeout=180)
            if proc.returncode:
                raise AssertionError(proc.stdout + "\n" + proc.stderr)
            return proc.stdout
        call("compute/maintainer/maintainer.py", "--help")
        call("compute/maintainer/retry.py", "--help")
        call("compute/maintainer/retry_resources.py", "--help")
        call("compute/maintainer/job.py", "--help")
        call("compute/maintainer/operational_http.py", "--help")
        call("compute/maintainer/operational_http_verify.py", "--help")
        call("compute/maintainer/operational_http_ledger.py", "--help")
        call("compute/maintainer/operational_tls.py", "--help")
        call("compute/maintainer/operational_https_joint.py", "--help")
        call("compute/maintainer/operational_https_ledger.py", "--help")
        call("compute/maintainer/operational_storage.py", "--help")
        call("compute/maintainer/operational_process.py", "--help")
        call("compute/maintainer/publication_witness.py", "--help")
        call("compute/maintainer/external_grader.py", "--help")
        call("compute/maintainer/diagnose_grades.py", "--help")
        call("-m", "compute.maintainer.empirical_economics", "--help")
        call("-m", "compute.maintainer.ownership_economics", "--help")
        call("-m", "compute.maintainer.provider_cur", "--help")
        call("compute/maintainer/owner_ocl/network_health.py", "--help")
        catalog = json.loads(call("integration/work.py", "--catalog"))
        names = {entry["task_class"] for entry in catalog["operations"]}
        assert {"maintainer-observe", "maintainer-compare"} <= names
        # Exercise the extracted dependency closure using an explicitly authored
        # HTTP/SSE fixture; this is software verification, not model performance.
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_retry.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_retry_resources.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_http.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_http_get.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_http_verify.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_http_ledger.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_tls.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_https_joint.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_https_ledger.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_storage.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_operational_process.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_publication_witness.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_job.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_external_grader.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_diagnose_grades.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_empirical_economics.py", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/tests", "-p", "test_ownership_economics.py", "-v")
        call("-m", "unittest", "compute.maintainer.tests.test_network_health", "-v")
        call("-m", "unittest", "discover", "-s", "compute/maintainer/experiments/hy4-flash/tests", "-p", "test_preflight.py", "-v")
        call("-m", "unittest", "discover", "-s", "integration/tests", "-p", "test_maintainer_work.py", "-v")
        call("-m", "unittest", "discover", "-s", "integration/tests", "-p", "test_maintainer_dependency_boundary.py", "-v")
        # Independently replay four captured real HTTPS observations from the
        # extracted kit. These are sparse endpoint samples, never an SLA claim.
        evidence = root / "https-temporal-replay"
        evidence.mkdir()
        with ZipFile(kit / "compute/maintainer/evidence/https-temporal-20261119.zip") as z:
            members = z.namelist()
            assert set(members) == {"manifest.json", "manifest.sha256",
                                    "receipt-1.json", "receipt-2.json", "ledger-report.json"}
            assert all("/" not in x and "\\" not in x for x in members)
            z.extractall(evidence)
        pinned_manifest = (evidence / "manifest.sha256").read_text().strip()
        replay = json.loads(call("compute/maintainer/operational_https_ledger.py",
            "--manifest", str(evidence / "manifest.json"),
            "--expected-manifest-sha256", pinned_manifest,
            "--evidence-directory", str(evidence)))
        assert replay["verdict"] == "pass"
        assert replay["samples"]["attempts"] == 4 and replay["samples"]["successes"] == 4
        assert replay == json.loads((evidence / "ledger-report.json").read_text())
        # Recompute reserved-capacity economics from original retained real
        # external grades/board telemetry in the extracted recipient package.
        retained = root / "ownership-retained"
        retained.mkdir()
        with ZipFile(kit / "compute/maintainer/evidence/vllm-humaneval-20261118.zip") as z:
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
                       and "\\" not in n for n in z.namelist())
            z.extractall(retained)
        ownership = json.loads(call("-m", "compute.maintainer.ownership_economics",
            str(retained / "cantos-vllm-humaneval-evidence-20261118"),
            "--scenario", str(kit / "compute/maintainer/examples/ownership-scenario.json")))
        assert [ownership["arms"][a]["observed"]["accepted"]
                for a in ("baseline", "candidate")] == [21, 21]
        assert ownership["comparison"]["decision"] == "hold_both_below_observed_acceptance_floor"
        assert len(ownership["original_source_sha256"]) >= 10
        call("app/tests/check_maintainer_evidence.py")
        call("app/tests/check_comparison_workbench.py")
        call("app/tests/check_deployment_workbench.py")
    print("Exact public maintainer kit: manifest, executable CLIs, operation discovery, joined job/grading/retry/resource/Hy4 contracts, streamed-fixture regression/reuse/fresh/custody and retained live-evidence deployment import passed. No new model measurement is asserted.")

if __name__ == "__main__":
    main()
