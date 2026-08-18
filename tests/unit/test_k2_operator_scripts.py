from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class K2OperatorScriptTests(unittest.TestCase):
    def test_external_authority_script_resolves_repository_imports(self):
        self._assert_help("k2_external_authority_activate.py")

    def test_runtime_attestation_script_resolves_repository_imports(self):
        self._assert_help("k2_comfyui_runtime_attestation.py")

    def _assert_help(self, name: str) -> None:
        with tempfile.TemporaryDirectory() as outside_repository:
            result = subprocess.run(
                [sys.executable, str(REPOSITORY_ROOT / "scripts" / name), "--help"],
                cwd=outside_repository,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
