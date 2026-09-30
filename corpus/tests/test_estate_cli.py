"""Direct-entry smoke test for the estate capture-lane CLI."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "corpus" / "estate_bundle.py"


class EstateBundleCliTests(unittest.TestCase):
    def test_direct_script_help_works_outside_checkout(self):
        scratch = Path(r"S:\Scratch\Runs")
        if not scratch.is_dir():
            scratch = Path(tempfile.gettempdir())
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--help"],
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--lane LANE", result.stdout)
        self.assertIn("--out OUT", result.stdout)


if __name__ == "__main__":
    unittest.main()
