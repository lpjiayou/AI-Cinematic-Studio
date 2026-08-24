from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from services.v4_platform import (
    PinnedRealImageCandidateEvidence,
    REAL_IMAGE_EVIDENCE_SCHEMA,
    RealImageCandidateEvidenceConfigurationError,
    RealImageCandidateEvidenceError,
    real_image_candidate_evidence_from_environment,
)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png(width: int, height: int, value: int) -> bytes:
    scanline = b"\x00" + bytes([value, value, value]) * width
    raw = scanline * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
        + _chunk(b"IDAT", zlib.compress(raw, level=9))
        + _chunk(b"IEND", b"")
    )


class PinnedRealImageCandidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.evidence_root = self.root / "evidence"
        self.receipt_dir = self.evidence_root / "candidate-run"
        self.smoke_dir = self.evidence_root / "technical-smoke"
        self.artifact_root = self.root / "artifacts"
        self.input_root = self.root / "inputs"
        for path in (
            self.receipt_dir,
            self.smoke_dir,
            self.artifact_root,
            self.input_root,
        ):
            path.mkdir(parents=True)
        self.input_files = []
        for name, content in (
            ("lin-che.png", b"locked-reference-lin-che"),
            ("gu-yan.png", b"locked-reference-gu-yan"),
        ):
            path = self.input_root / name
            path.write_bytes(content)
            self.input_files.append(path)
        self.requests = []
        candidates = []
        for ordinal in range(1, 5):
            request_ref = f"real-image-request-{ordinal}"
            request_digest = sha256(
                f"request-{ordinal}".encode("utf-8")
            ).hexdigest()
            request = {
                "ordinal": ordinal,
                "generationRequestRef": request_ref,
                "payloadDigest": request_digest,
                "creativeShotVersionRef": f"creative-shot-version-{ordinal}",
                "identityInputs": [
                    {"referenceContentDigest": _sha(path)}
                    for path in self.input_files
                ],
                "parameters": {"width": 1280, "height": 720},
            }
            self.requests.append(request)
            workflow = {
                "load-a": {
                    "class_type": "LoadImage",
                    "inputs": {"image": self.input_files[0].name},
                },
                "load-b": {
                    "class_type": "LoadImage",
                    "inputs": {"image": self.input_files[1].name},
                },
                "mask-a": {"class_type": "SolidMask", "inputs": {}},
                "mask-b": {"class_type": "SolidMask", "inputs": {}},
                "adapter-a": {
                    "class_type": "IPAdapterAdvanced",
                    "inputs": {
                        "image": ["load-a", 0],
                        "attn_mask": ["mask-a", 0],
                    },
                },
                "adapter-b": {
                    "class_type": "IPAdapterAdvanced",
                    "inputs": {
                        "image": ["load-b", 0],
                        "attn_mask": ["mask-b", 0],
                    },
                },
                "latent": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {
                        "width": 1280,
                        "height": 720,
                    },
                },
            }
            workflow_path = self.receipt_dir / f"shot-{ordinal:02d}-workflow.json"
            workflow_path.write_text(
                json.dumps(workflow, sort_keys=True), encoding="utf-8"
            )
            artifact_path = self.artifact_root / f"shot-{ordinal:02d}.png"
            artifact_path.write_bytes(_png(1280, 720, ordinal * 20))
            candidates.append(
                {
                    "ordinal": ordinal,
                    "generationRequestRef": request_ref,
                    "generationRequestDigest": request_digest,
                    "creativeShotVersionRef": f"creative-shot-version-{ordinal}",
                    "workflowDigest": _sha(workflow_path),
                    "workflowNodeCount": len(workflow),
                    "seed": ordinal,
                    "steps": 20,
                    "submittedAt": "2026-08-23T08:10:00Z",
                    "finishedAt": "2026-08-23T08:10:10Z",
                    "latencySeconds": 10,
                    "comfyPromptId": f"comfy-prompt-{ordinal}",
                    "gpuUsed": True,
                    "maxGpuObservation": {"utilization": 90},
                    "localEvidenceCandidateKey": f"m10-candidate-{ordinal}",
                    "state": "UNSELECTED_LOCAL_EVIDENCE_CANDIDATE",
                    "validationState": "TECHNICALLY_VERIFIED",
                    "output": {
                        "contentDigest": _sha(artifact_path),
                        "byteSize": artifact_path.stat().st_size,
                        "width": 1280,
                        "height": 720,
                        "mediaType": "image/png",
                        "artifactFile": str(artifact_path),
                        "reviewFile": f"review-shot-{ordinal}.png",
                    },
                }
            )
        technical_receipt = self.smoke_dir / "receipt.json"
        technical_receipt.write_text('{"ok":true}', encoding="utf-8")
        receipt = {
            "schemaVersion": REAL_IMAGE_EVIDENCE_SCHEMA,
            "state": "FOUR_UNSELECTED_LOCAL_EVIDENCE_CANDIDATES_READY",
            "workspaceRef": "workspace-test",
            "productionRunRef": "production-run-test",
            "realImagePlanRef": "real-image-plan-test",
            "realImagePlanDigest": sha256(b"plan").hexdigest(),
            "technicalSmokeReceipt": str(technical_receipt),
            "technicalSmokeReceiptDigest": _sha(technical_receipt),
            "modelSetDigest": sha256(b"model-set").hexdigest(),
            "startedAt": "2026-08-23T08:10:00Z",
            "finishedAt": "2026-08-23T08:11:00Z",
            "repositoryCommit": "a" * 40,
            "candidateCount": 4,
            "candidates": candidates,
            "candidateSelectionState": "NOT_STARTED",
            "assetAdmissionState": "NOT_STARTED",
            "canonicalMutationCount": 0,
            "publicationAllowed": False,
        }
        self.receipt_path = self.receipt_dir / "receipt.json"
        self.receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        self.adapter = PinnedRealImageCandidateEvidence(
            self.receipt_path,
            _sha(self.receipt_path),
            self.artifact_root,
            self.input_root,
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_reverifies_four_workflows_references_and_png_artifacts(self):
        result = self.adapter.resolve_candidates(
            "workspace-test",
            "production-run-test",
            "real-image-plan-test",
            self.requests,
        )
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(
            [item["ordinal"] for item in result["candidates"]],
            [1, 2, 3, 4],
        )
        self.assertTrue(
            all(
                item["state"] == "TECHNICALLY_VERIFIED"
                and item["gpuUsed"] is True
                and item["publicationAllowed"] is False
                for item in result["candidates"]
            )
        )
        self.assertTrue(result["artifactStoreRef"].startswith("artifact-store-"))

    def test_rejects_artifact_changed_after_the_pinned_receipt(self):
        (self.artifact_root / "shot-03.png").write_bytes(b"changed")
        with self.assertRaises(RealImageCandidateEvidenceError):
            self.adapter.resolve_candidates(
                "workspace-test",
                "production-run-test",
                "real-image-plan-test",
                self.requests,
            )

    def test_rejects_changed_locked_identity_input(self):
        self.input_files[0].write_bytes(b"changed-reference")
        with self.assertRaises(RealImageCandidateEvidenceError):
            self.adapter.resolve_candidates(
                "workspace-test",
                "production-run-test",
                "real-image-plan-test",
                self.requests,
            )

    def test_rehashes_the_exact_receipt_bytes_on_every_resolution(self):
        replacement = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        replacement["repositoryCommit"] = "b" * 40
        self.receipt_path.write_text(
            json.dumps(replacement, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            RealImageCandidateEvidenceError,
            "candidate evidence digest mismatch",
        ):
            self.adapter.resolve_candidates(
                "workspace-test",
                "production-run-test",
                "real-image-plan-test",
                self.requests,
            )

    def test_environment_configuration_is_all_or_nothing(self):
        self.assertIsNone(real_image_candidate_evidence_from_environment({}))
        with self.assertRaises(RealImageCandidateEvidenceConfigurationError):
            real_image_candidate_evidence_from_environment(
                {"K2_M10_CANDIDATE_EVIDENCE_PATH": str(self.receipt_path)}
            )


if __name__ == "__main__":
    unittest.main()
