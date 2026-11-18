"""Export one data-only, independently verifiable baseline/candidate review ZIP."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

try:
    from .common import _safe, producer_records
    from .packets import _checked_analysis
except ImportError:
    from common import _safe, producer_records
    from packets import _checked_analysis


def export_comparison(analysis, destination):
    path, result, pol, runs, workloads, grades = _checked_analysis(analysis)
    destination = Path(destination)
    files, inputs = {}, {}

    def add(name, source):
        data = Path(source).read_bytes()
        if name in files and files[name] != data:
            raise ValueError("Conflicting evidence path: " + name)
        files[name] = data
        return name

    for arm in ("baseline", "candidate"):
        for key, receipt in ((arm, runs[arm]), (arm + "_grades", grades[arm])):
            if receipt is None:
                continue
            source = Path(result["inputs"][key]["path"])
            prefix = key + "/"
            inputs[key] = add(prefix + source.name, source)
            for entry in receipt["artifacts"]:
                add(prefix + entry["path"], _safe(source.parent, entry["path"]))
    policy_path = _safe(path.parent, result["ocl_exports"]["policy"]["path"])
    inputs["policy"] = add("policy.json", policy_path)
    if "grading_contract" in result["inputs"]:
        inputs["grading_contract"] = add("grading-contract.json", result["inputs"]["grading_contract"]["path"])
    add("original-analysis.json", path)
    manifest = {
        "schema": "cantos.comparison-bundle/1",
        "title": workloads["baseline"]["name"] + " — baseline / candidate",
        "inputs": inputs,
        "original_analysis": "original-analysis.json",
        "producer_files": producer_records(),
        "scope": "Retained observations and bound grades. Import validates data with the installed native analyzer; it executes no uploaded code and makes no inference requests.",
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())],
    }
    files["comparison.json"] = (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 18, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = destination.read_bytes()
    return {"schema": "cantos.comparison-export/1", "archive": str(destination),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "verdict": result["verdict"], "new_inference_requests": 0}
