import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "validate_experiment_package_schema.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_experiment_package_schema", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExperimentPackageSchemaGateTests(unittest.TestCase):
    def test_accepts_domain_fields_and_extension_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root)

            result = MODULE.validate_new_package(root)

        self.assertEqual(
            result["domainCameraFields"],
            ["shotSize", "movement", "angle", "lensMm", "intent"],
        )
        self.assertEqual(result["shotsCameraCount"], 0)
        self.assertEqual(result["cameraContractCameraCount"], 1)
        self.assertEqual(result["discoveredPackageCount"], 0)

    def test_rejects_legacy_camera_aliases(self):
        aliases = {
            "framing": "shotSize",
            "primaryMove": "movement",
            "lensMmEquivalent": "lensMm",
        }
        for alias, replacement in aliases.items():
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._write_package(root, camera_extra={alias: "legacy-value"})

                with self.assertRaisesRegex(
                    MODULE.ExperimentSchemaGateError,
                    rf"{alias} is prohibited; use {replacement}",
                ):
                    MODULE.validate_new_package(root)

    def test_rejects_missing_or_invalid_domain_camera_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root, camera_remove="angle")
            with self.assertRaisesRegex(
                MODULE.ExperimentSchemaGateError,
                "missing domain camera fields: angle",
            ):
                MODULE.validate_new_package(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root, camera_extra={"lensMm": True})
            with self.assertRaisesRegex(
                MODULE.ExperimentSchemaGateError,
                "camera.*invalid",
            ):
                MODULE.validate_new_package(root)

    def test_validates_camera_payloads_in_shots_json_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root, shots_camera={"movement": "pan"})

            with self.assertRaisesRegex(
                MODULE.ExperimentSchemaGateError,
                "missing domain camera fields",
            ):
                MODULE.validate_new_package(root)

    def test_cli_scans_only_the_explicit_new_package(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            selected = parent / "new-package"
            frozen = parent / "frozen-v2-promptfix-r1"
            self._write_package(selected)
            self._write_package(
                frozen,
                camera_extra={"framing": "legacy frozen value"},
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--new-package-root",
                    str(selected),
                ],
                cwd=frozen,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EXPERIMENT_PACKAGE_SCHEMA_GATE=PASS", result.stdout)
        self.assertIn("SCOPE=EXPLICIT_NEW_PACKAGE_ONLY", result.stdout)
        self.assertIn("DISCOVERED_PACKAGE_COUNT=0", result.stdout)
        self.assertNotIn(str(frozen), result.stdout)

    def test_cli_requires_an_explicit_new_package_root(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--new-package-root", result.stderr)

    def test_rejects_duplicate_fields_and_non_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root)
            (root / "shots.json").write_text(
                '{"shots":[],"shots":[]}', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                MODULE.ExperimentSchemaGateError,
                "duplicate JSON field: shots",
            ):
                MODULE.validate_new_package(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_package(root)
            (root / "camera_contract.json").write_bytes(b"\xff")
            with self.assertRaisesRegex(
                MODULE.ExperimentSchemaGateError,
                "not valid UTF-8 JSON",
            ):
                MODULE.validate_new_package(root)

    @staticmethod
    def _write_package(
        root: Path,
        *,
        camera_extra=None,
        camera_remove=None,
        shots_camera=None,
    ):
        root.mkdir(parents=True, exist_ok=True)
        camera = {
            "shotSize": "wide",
            "movement": "lateral-track",
            "angle": "eye-level",
            "lensMm": 35,
            "intent": "establish-space",
            "heightMeters": 0.9,
            "focus": "hold subject",
            "endCondition": "subject reaches mark",
        }
        if camera_extra:
            camera.update(camera_extra)
        if camera_remove:
            camera.pop(camera_remove)
        shot = {"shotId": "EP02_SH01", "positivePrompt": "test prompt"}
        if shots_camera is not None:
            shot["camera"] = shots_camera
        (root / "shots.json").write_text(
            json.dumps({"episodeId": "EP02", "shots": [shot]}),
            encoding="utf-8",
        )
        (root / "camera_contract.json").write_text(
            json.dumps(
                {
                    "contractId": "K2-002-EP02-CAMERA-CONTRACT",
                    "shots": [{"shotId": "EP02_SH01", "camera": camera}],
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
