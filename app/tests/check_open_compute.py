"""Verify the exact public download via its extracted entry and retained inputs."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def main():
    release = Path(__file__).resolve().parents[2] / "public" / "open-compute"
    archive = release / "open-compute-workbench.zip"
    digest, name = (release / "SHA256SUMS.txt").read_text().split()
    assert name == archive.name and digest == sha256(archive.read_bytes()).hexdigest()
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with ZipFile(archive) as z:
            names = z.namelist()
            assert len(set(names)) == len(names)
            assert all(n.startswith("cantos/") and ".." not in Path(n).parts for n in names)
            manifest_path = "cantos/open-compute-ledger/MANIFEST.json"
            manifest = json.loads(z.read(manifest_path))["files"]
            assert set(names) == {"cantos/" + path for path in manifest} | {manifest_path}
            for path, expected in manifest.items():
                assert sha256(z.read("cantos/" + path)).hexdigest() == expected, path
            z.extractall(root)
        kit = root / "cantos" / "open-compute-ledger"
        def call(command, request=None, *args):
            cmd = [sys.executable, "-B", str(kit / "engine/engine.py"), command, "--store", str(root / "store")]
            if request is not None:
                path = root / "request.json"
                path.write_text(json.dumps(request))
                cmd.extend(["--request", str(path)])
            return json.loads(subprocess.check_output(cmd + list(args)))
        catalog = call("catalog")
        counts = {r["id"]: r["accepted"] for r in catalog["serving_arms"] if r["workload_id"] == "run3"}
        assert counts == {"mi300x": 4351, "h100": 4296, "mi210": 136, "rtx8000": 69}
        decision = call("decide", {"kind": "serving", "workload_id": "run3", "objective": "max_acceptance"})
        assert decision["recommendation"]["id"] == "mi300x" and decision["execution"]["inference_run"] is False
        model = catalog["screening_models"][0]
        token = call("decide", {"kind":"screening","model":model["id"],"as_of":max(model["dates"]),"objective":"min_cost"})
        assert token["recommendation"]["operands"]["benchmark_provenance"]
        packet = json.loads((kit / "examples/run3-mi300x.packet.json").read_text())
        imported = call("import", packet)
        assert imported["configuration_added"] and call("import", packet)["id"] == imported["id"]
        fresh = call("catalog")
        row = next(r for r in fresh["serving_arms"] if r["id"].startswith("import-"))
        assert row["accepted"] == 4351 and row["useful_work_basis"] == "published"
        assert call("export",None,"--id",decision["id"]) == decision
        assert {r["id"] for r in call("history")["items"]} == {decision["id"], token["id"]}
    print("Public ZIP manifest, original inputs, common grades, price screening, import, history and export passed.")


if __name__ == "__main__":
    main()
