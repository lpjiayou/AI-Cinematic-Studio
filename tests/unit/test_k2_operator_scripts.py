from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from services.v4_platform.comfyui import REQUIRED_NODES


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class K2OperatorScriptTests(unittest.TestCase):
    def test_external_authority_script_resolves_repository_imports(self):
        self._assert_help("k2_external_authority_activate.py")

    def test_runtime_attestation_script_resolves_repository_imports(self):
        self._assert_help("k2_comfyui_runtime_attestation.py")

    def test_runtime_evidence_archive_script_resolves_repository_imports(self):
        self._assert_help("k2_comfyui_runtime_evidence_archive.py")

    def test_runtime_attestation_reports_the_real_cli_option(self):
        environment = os.environ.copy()
        for name in list(environment):
            if name.startswith("COMFYUI_"):
                environment.pop(name)
        with tempfile.TemporaryDirectory() as model_root:
            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        REPOSITORY_ROOT
                        / "scripts"
                        / "k2_comfyui_runtime_attestation.py"
                    ),
                    "--model-root",
                    model_root,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=environment,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--base-url or COMFYUI_BASE_URL is required", result.stderr)
        self.assertNotIn("--comfyui-base-url", result.stderr)

    def test_runtime_evidence_archive_validates_and_packages_exact_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._runtime_evidence(root)
            output = root / "runtime-evidence.tar.gz"
            result = self._archive(paths, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_name(output.name + ".sha256").is_file())
            self.assertIn("AUTHORITY_STATE=TECHNICAL_EVIDENCE_ONLY", result.stdout)
            self.assertIn("PUBLICATION_ALLOWED=false", result.stdout)
            with tarfile.open(output, "r:gz") as archive:
                self.assertEqual(
                    sorted(archive.getnames()),
                    [
                        "attestation.json",
                        "comfyui-object-info.json",
                        "comfyui-system-stats.json",
                        "model-files.sha256",
                        "runtime-evidence-manifest.json",
                    ],
                )
                manifest = json.load(
                    archive.extractfile("runtime-evidence-manifest.json")
                )
                model_digests = archive.extractfile("model-files.sha256").read()
            self.assertEqual(
                manifest["schemaVersion"],
                "v4.comfyui-runtime-evidence-archive.v1",
            )
            self.assertFalse(manifest["publicationAllowed"])
            self.assertNotIn(b"/models/", model_digests)

            second_output = root / "runtime-evidence-copy.tar.gz"
            second_result = self._archive(paths, second_output)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(output.read_bytes(), second_output.read_bytes())

    def test_runtime_evidence_archive_rejects_cross_file_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._runtime_evidence(root)
            paths["object_info"].write_text(
                json.dumps({"tampered": True}), encoding="utf-8"
            )
            output = root / "runtime-evidence.tar.gz"
            result = self._archive(paths, output)

            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "object info digest does not match attestation", result.stderr
            )
            self.assertFalse(output.exists())

    def test_runtime_evidence_archive_rejects_self_consistent_extra_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._runtime_evidence(root)
            attestation = json.loads(paths["attestation"].read_text(encoding="utf-8"))
            attestation["facts"]["unexpectedFact"] = "not-part-of-the-schema"
            attestation["factsDigest"] = self._canonical_digest(attestation["facts"])
            attestation.pop("payloadDigest")
            attestation["payloadDigest"] = self._canonical_digest(attestation)
            paths["attestation"].write_text(
                json.dumps(attestation, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

            result = self._archive(paths, root / "runtime-evidence.tar.gz")

            self.assertEqual(result.returncode, 2)
            self.assertIn("attestation facts fields are invalid", result.stderr)

    def test_runtime_evidence_archive_rejects_missing_native_node(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._runtime_evidence(root)
            object_info = json.loads(paths["object_info"].read_text(encoding="utf-8"))
            object_info.pop(REQUIRED_NODES[-1])
            paths["object_info"].write_text(
                json.dumps(object_info, sort_keys=True), encoding="utf-8"
            )
            attestation = json.loads(paths["attestation"].read_text(encoding="utf-8"))
            attestation["facts"]["objectInfoDigest"] = self._canonical_digest(
                object_info
            )
            attestation["factsDigest"] = self._canonical_digest(attestation["facts"])
            attestation.pop("payloadDigest")
            attestation["payloadDigest"] = self._canonical_digest(attestation)
            paths["attestation"].write_text(
                json.dumps(attestation, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

            result = self._archive(paths, root / "runtime-evidence.tar.gz")

            self.assertEqual(result.returncode, 2)
            self.assertIn("object info is missing required nodes", result.stderr)

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

    @staticmethod
    def _canonical_digest(value):
        return sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def _runtime_evidence(self, root: Path):
        models = {
            "wan2.2_ti2v_5B_fp16.safetensors": "1" * 64,
            "umt5_xxl_fp8_e4m3fn_scaled.safetensors": "2" * 64,
            "wan2.2_vae.safetensors": "3" * 64,
        }
        object_info = {
            node: {"input": {"required": {}}} for node in REQUIRED_NODES
        }
        facts = {
            "providerId": "self-hosted-comfyui",
            "modelId": "wan2.2-ti2v-5b-fp16",
            "region": "provider-not-disclosed",
            "endpointClass": "local-loopback",
            "comfyuiVersion": "0.28.0",
            "pythonVersion": "3.12.7",
            "pytorchVersion": "2.11.0+cu126",
            "deviceName": "cuda:0 NVIDIA A100-PCIE-40GB",
            "deviceType": "cuda",
            "vramTotalBytes": 42_405_855_232,
            "requiredNodes": list(REQUIRED_NODES),
            "modelFiles": [
                {"role": "UNET", "name": name, "sha256": digest}
                if index == 0
                else {
                    "role": "TEXT_ENCODER" if index == 1 else "VAE",
                    "name": name,
                    "sha256": digest,
                }
                for index, (name, digest) in enumerate(models.items())
            ],
            "objectInfoDigest": self._canonical_digest(object_info),
            "modelDigestVerification": "LOCAL_FILE_SHA256_VERIFIED",
        }
        attestation = {
            "schemaVersion": "v4.comfyui-runtime-attestation.v1",
            "attestationRef": "technical-k2-runtime-test-v1",
            "observedAt": "2026-08-20T14:17:08Z",
            "factsDigest": self._canonical_digest(facts),
            "facts": facts,
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            "publicationAllowed": False,
        }
        attestation["payloadDigest"] = self._canonical_digest(attestation)
        system_stats = {
            "system": {
                "comfyui_version": facts["comfyuiVersion"],
                "python_version": facts["pythonVersion"],
                "pytorch_version": facts["pytorchVersion"],
            },
            "devices": [
                {
                    "name": facts["deviceName"],
                    "type": "cuda",
                    "vram_total": facts["vramTotalBytes"],
                }
            ],
        }
        paths = {
            "attestation": root / "attestation.json",
            "model_digests": root / "models.sha256",
            "system_stats": root / "system-stats.json",
            "object_info": root / "object-info.json",
        }
        paths["attestation"].write_text(
            json.dumps(attestation, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        paths["model_digests"].write_text(
            "".join(
                f"{digest}  /models/{name}\n" for name, digest in models.items()
            ),
            encoding="utf-8",
        )
        paths["system_stats"].write_text(
            json.dumps(system_stats, sort_keys=True), encoding="utf-8"
        )
        paths["object_info"].write_text(
            json.dumps(object_info, sort_keys=True), encoding="utf-8"
        )
        return paths

    @staticmethod
    def _archive(paths, output: Path):
        return subprocess.run(
            [
                sys.executable,
                str(
                    REPOSITORY_ROOT
                    / "scripts"
                    / "k2_comfyui_runtime_evidence_archive.py"
                ),
                "--attestation",
                str(paths["attestation"]),
                "--model-digests",
                str(paths["model_digests"]),
                "--system-stats",
                str(paths["system_stats"]),
                "--object-info",
                str(paths["object_info"]),
                "--output",
                str(output),
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
