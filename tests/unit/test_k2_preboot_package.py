import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "k2_preboot_validate.py"
MANIFEST = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-preboot"
    / "k2-001-preproduction-candidate.v1.json"
)
SPEC = importlib.util.spec_from_file_location("k2_preboot_validate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class K2PrebootPackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_checked_in_candidate_is_valid_and_fail_closed(self):
        result = MODULE.validate_preboot_manifest(self.manifest)

        self.assertEqual(result["schemaVersion"], "k2.preboot-candidate.v1")
        self.assertEqual(result["budgetHardCapMinor"], 100_000)
        self.assertEqual(result["shotCount"], 4)
        self.assertEqual(result["totalFrames"], 720)
        self.assertEqual(result["gate"], "P1_NOT_PASSED")
        self.assertFalse(result["publicationAllowed"])
        self.assertEqual(len(result["manifestSha256"]), 64)

    def test_cli_can_run_outside_repository_without_provider_access(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--manifest",
                    str(MANIFEST),
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("K2_PREBOOT_PACKAGE=PASS", result.stdout)
        self.assertIn("BUDGET_HARD_CAP=CNY_1000", result.stdout)
        self.assertIn("PAID_CALLS_EXECUTED=0", result.stdout)
        self.assertIn("P1_GATE=NOT_PASSED", result.stdout)
        self.assertIn("PUBLICATION_ALLOWED=false", result.stdout)

    def test_rejects_budget_above_project_lead_ceiling(self):
        self.manifest["budget"]["hardCapMinor"] = 100_001

        with self.assertRaisesRegex(
            MODULE.PrebootValidationError, "CNY 1,000 ceiling"
        ):
            MODULE.validate_preboot_manifest(self.manifest)

    def test_rejects_spend_or_paid_call_claim(self):
        for field, value in (
            ("committedSpendMinor", 1),
            ("paidCallsAllowedNow", True),
        ):
            candidate = copy.deepcopy(self.manifest)
            candidate["budget"][field] = value
            with self.subTest(field=field), self.assertRaises(
                MODULE.PrebootValidationError
            ):
                MODULE.validate_preboot_manifest(candidate)

    def test_rejects_missing_character_angle(self):
        self.manifest["characters"][0]["requiredViews"].pop()

        with self.assertRaisesRegex(
            MODULE.PrebootValidationError, "frozen package"
        ):
            MODULE.validate_preboot_manifest(self.manifest)

    def test_rejects_external_audio_or_voice_cloning(self):
        for field, value in (
            ("externalAudioRef", "external-audio-not-allowed"),
            ("voiceCloning", True),
        ):
            candidate = copy.deepcopy(self.manifest)
            candidate["shots"][0]["audioExperimentDraft"][field] = value
            with self.subTest(field=field), self.assertRaises(
                MODULE.PrebootValidationError
            ):
                MODULE.validate_preboot_manifest(candidate)

    def test_rejects_publication_or_admission_claims(self):
        mutations = (
            ("truthBoundary", "publicationAllowed"),
            ("truthBoundary", "domainFact"),
        )
        for section, field in mutations:
            candidate = copy.deepcopy(self.manifest)
            candidate[section][field] = True
            with self.subTest(field=field), self.assertRaises(
                MODULE.PrebootValidationError
            ):
                MODULE.validate_preboot_manifest(candidate)

        candidate = copy.deepcopy(self.manifest)
        candidate["experiments"][1]["assetAdmitted"] = True
        with self.assertRaises(MODULE.PrebootValidationError):
            MODULE.validate_preboot_manifest(candidate)

    def test_rejects_model_or_runtime_digest_tampering(self):
        mutations = (
            ("models", 0, "sha256"),
            ("technicalEvidence", None, "attestationPayloadDigest"),
        )
        for section, index, field in mutations:
            candidate = copy.deepcopy(self.manifest)
            target = candidate[section] if index is None else candidate[section][index]
            target[field] = "0" * 64
            with self.subTest(section=section), self.assertRaises(
                MODULE.PrebootValidationError
            ):
                MODULE.validate_preboot_manifest(candidate)

    def test_rejects_non_contiguous_or_wrong_frame_accounting(self):
        mutations = (
            (0, "durationFrames", 167),
            (1, "startFrame", 169),
            (3, "frameRate", 25),
        )
        for index, field, value in mutations:
            candidate = copy.deepcopy(self.manifest)
            candidate["shots"][index][field] = value
            with self.subTest(index=index, field=field), self.assertRaises(
                MODULE.PrebootValidationError
            ):
                MODULE.validate_preboot_manifest(candidate)

    def test_rejects_duplicate_or_reordered_shot_identity(self):
        self.manifest["shots"][1]["globalOrder"] = 1
        self.manifest["shots"][1]["shotKey"] = "K2-001-SH-010"

        with self.assertRaises(MODULE.PrebootValidationError):
            MODULE.validate_preboot_manifest(self.manifest)

    def test_preserves_missing_current_g4_image_request_as_a_blocker(self):
        self.manifest["experiments"][0][
            "generationRequestResolution"
        ] = "AT_RUNTIME_FROM_CURRENT_G4"

        with self.assertRaisesRegex(
            MODULE.PrebootValidationError, "generationRequestResolution"
        ):
            MODULE.validate_preboot_manifest(self.manifest)

    def test_rejects_secret_shaped_fields_and_duplicate_json_keys(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["apiKey"] = "do-not-store"
        with self.assertRaisesRegex(
            MODULE.PrebootValidationError, "secret-shaped field"
        ):
            MODULE._reject_secrets(candidate)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schemaVersion":"a","schemaVersion":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.PrebootValidationError, "duplicate keys"
            ):
                MODULE.load_manifest(path.resolve())


if __name__ == "__main__":
    unittest.main()
