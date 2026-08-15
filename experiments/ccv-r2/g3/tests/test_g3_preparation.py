#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


HERE = Path(__file__).resolve()
PREFLIGHT = HERE.parents[1] / "preflight"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PREFLIGHT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


prepare = load_module("g3_prepare", "prepare_g3_execution.py")
validate = load_module("g3_validate", "validate_g3_preparation.py")


def minimal_protocol():
    return {
        "schemaVersion": "ACS-CCV-R2-G3-PROTOCOL-1",
        "protocolVersion": "g3-rcr-v1",
        "state": "G0_FROZEN_NO_GPU",
        "expectedUniqueRequestCount": 51,
        "claims": {
            "gpuExecutionAuthorized": False,
            "gpuExecutionStarted": False,
            "comfyUiQueueTouched": False,
            "modelLoaded": False,
            "imageGenerated": False,
            "validationAccepted": False,
            "productionReady": False,
            "productCodeChanged": False,
            "schemaChanged": False,
        },
        "shots": [
            "01_medium_front", "02_closeup_side", "03_full_walking",
            "04_back_turning", "05_sitting_high",
        ],
        "seeds": [123456, 223456, 323456],
        "fixedParameters": {"ipAdapterWeight": 0.6, "controlNetStrength": 0.8},
        "references": [
            {"armId": "G3_M0_G2_REFERENCE_CONTROL", "runtimePath": "/m0.png"},
            {"armId": "G3_M1_SAME_IDENTITY_COLLAR_FREE", "runtimePath": "/m1.png"},
            {"armId": "G3_P0_EXTERNAL_REFERENCE_PROBE", "runtimePath": "/p0.png"},
        ],
        "backTurningSweep": {
            "armId": "G3_M1_SAME_IDENTITY_COLLAR_FREE",
            "shotId": "04_back_turning",
            "ipAdapterWeights": [0.3, 0.45, 0.6],
            "controlNetStrength": 0.8,
            "reuseMainRowsAtWeight": 0.6,
        },
    }


class ProtocolTests(unittest.TestCase):
    def test_frozen_plan_has_51_unique_requests(self):
        protocol = minimal_protocol()
        prepare.validate_protocol(protocol)
        runs = prepare.build_run_plan(protocol)
        self.assertEqual(51, len(runs))
        self.assertEqual(45, sum(row["phase"] == "MAIN" for row in runs))
        self.assertEqual(6, sum(row["phase"] == "BACK_TURNING_SWEEP" for row in runs))
        self.assertEqual(51, len({row["technicalId"] for row in runs}))
        self.assertEqual(6, sum(row["ipAdapterWeight"] in {0.3, 0.45} for row in runs))
        self.assertTrue(all(row["controlNetStrength"] == 0.8 for row in runs))

    def test_positive_gpu_claim_fails_closed(self):
        protocol = minimal_protocol()
        protocol["claims"]["gpuExecutionStarted"] = True
        with self.assertRaises(prepare.PreparationError):
            prepare.validate_protocol(protocol)


class CropCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        self.output = self.root / "collar-free.png"
        self.receipt = self.root / "collar-free.derivation.json"
        image = Image.new("RGB", (12, 12))
        for y in range(12):
            for x in range(12):
                image.putpixel((x, y), (x * 17, y * 17, (x + y) * 9))
        image.save(self.source)
        crop = image.crop((3, 1, 9, 7)).resize((8, 8), Image.Resampling.LANCZOS)
        crop.save(self.output)
        source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        output_sha = hashlib.sha256(self.output.read_bytes()).hexdigest()
        pixel_sha = hashlib.sha256(crop.convert("RGB").tobytes()).hexdigest()
        self.source_sha = source_sha
        self.receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": "ACS-CCV-R2-G3-CROP-DERIVATION-1",
                    "method": "RECTANGULAR_CROP_AND_RESIZE_ONLY",
                    "sourcePath": str(self.source),
                    "sourceSha256": source_sha,
                    "sourceDimensions": [12, 12],
                    "cropBoxPixels": [3, 1, 9, 7],
                    "outputPath": str(self.output),
                    "outputDimensions": [8, 8],
                    "resizeAlgorithm": "LANCZOS",
                    "outputSha256": output_sha,
                    "outputPixelSha256": pixel_sha,
                    "collarExcludedAttestation": True,
                    "operatorAttestation": True,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_crop_and_resize_passes(self):
        result = prepare.verify_crop_derivation(
            self.source, self.output, self.receipt, self.source_sha
        )
        self.assertEqual([3, 1, 9, 7], result["cropBoxPixels"])

    def test_tampered_output_fails_closed(self):
        with Image.open(self.output) as image:
            changed = image.convert("RGB")
        changed.putpixel((0, 0), (255, 0, 0))
        changed.save(self.output)
        with self.assertRaises(prepare.PreparationError):
            prepare.verify_crop_derivation(
                self.source, self.output, self.receipt, self.source_sha
            )

    def test_derivation_requires_explicit_attestation(self):
        candidate = self.root / "new.png"
        receipt = self.root / "new.derivation.json"
        with self.assertRaisesRegex(prepare.PreparationError, "attest-collar"):
            prepare.derive_crop_reference(
                self.source, candidate, receipt, self.source_sha,
                [3, 1, 9, 7], [8, 8], False,
            )
        self.assertFalse(candidate.exists())
        self.assertFalse(receipt.exists())

    def test_derivation_writes_self_verifying_receipt(self):
        candidate = self.root / "new.png"
        receipt = self.root / "new.derivation.json"
        prepare.derive_crop_reference(
            self.source, candidate, receipt, self.source_sha,
            [3, 1, 9, 7], [8, 8], True,
        )
        verified = prepare.verify_crop_derivation(
            self.source, candidate, receipt, self.source_sha
        )
        self.assertEqual([8, 8], verified["outputDimensions"])
        with self.assertRaisesRegex(prepare.PreparationError, "refuses to overwrite"):
            prepare.derive_crop_reference(
                self.source, candidate, receipt, self.source_sha,
                [3, 1, 9, 7], [8, 8], True,
            )


class WorkflowTests(unittest.TestCase):
    def test_materialization_binds_frozen_factors_and_opaque_output(self):
        graph = {
            "1": {"class_type": "KSampler", "inputs": {"positive": [2, 0], "negative": [3, 0]}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
            "4": {"class_type": "LoadImage", "inputs": {"image": "reference_face.png"}},
            "5": {"class_type": "LoadImage", "inputs": {"image": "pose_01_medium_front.png"}},
            "6": {"class_type": "IPAdapterAdvanced", "inputs": {"weight": 0.1}},
            "7": {"class_type": "ControlNetApplyAdvanced", "inputs": {"strength": 0.1}},
            "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
        }
        manifest = {
            "parameters": {
                "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                "positivePrompt": "same person", "negativePrompt": "bad anatomy",
            },
            "shots": [
                {"shotId": "01_medium_front", "description": "front", "poseInputId": "pose-1"}
            ],
            "inputs": [
                {"inputId": "pose-1", "runtimePath": "/data/input/pose_01_medium_front.png"}
            ],
        }
        run = {
            "shotId": "01_medium_front", "seed": 223456,
            "ipAdapterWeight": 0.6, "controlNetStrength": 0.8,
            "referencePath": "/data/input/m1.png",
        }
        out = prepare.materialize_graph(graph, run, manifest, "G3B007", "G3R0123456789ABCDEF")
        self.assertEqual(223456, out["1"]["inputs"]["seed"])
        self.assertEqual("m1.png", out["4"]["inputs"]["image"])
        self.assertEqual("pose_01_medium_front.png", out["5"]["inputs"]["image"])
        self.assertEqual(0.6, out["6"]["inputs"]["weight"])
        self.assertEqual(0.8, out["7"]["inputs"]["strength"])
        self.assertEqual(
            "ccv-r2-g3/G3B007__G3R0123456789ABCDEF",
            out["8"]["inputs"]["filename_prefix"],
        )


class EndToEndTests(unittest.TestCase):
    def test_synthetic_preparation_validates_independently(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            prep = root / "g2-preparation"
            results = root / "g2-results"
            output = root / "g3-preparation"
            runtime = root / "runtime"
            for path in (repo, prep, results, runtime):
                path.mkdir(parents=True)

            source = runtime / "reference_character.png"
            m0 = runtime / "reference_face.png"
            m1 = runtime / "ccv-r2-g3-reference-face-collar-free.png"
            external = runtime / "external.png"
            image = Image.new("RGB", (24, 32), (20, 40, 80))
            for y in range(32):
                for x in range(24):
                    image.putpixel((x, y), (x * 8, y * 6, (x + y) * 4))
            image.save(source)
            image.crop((6, 2, 18, 14)).resize((16, 16), Image.Resampling.LANCZOS).save(m0)
            Image.new("RGB", (16, 16), (90, 20, 20)).save(external)
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            m0_sha = hashlib.sha256(m0.read_bytes()).hexdigest()
            external_sha = hashlib.sha256(external.read_bytes()).hexdigest()

            protocol = minimal_protocol()
            protocol.update({
                "schemaVersion": "ACS-CCV-R2-G3-PROTOCOL-1",
                "experimentId": "acs-ccv-r2",
                "references": [
                    {
                        "armId": "G3_M0_G2_REFERENCE_CONTROL", "runtimePath": str(m0),
                        "sha256": m0_sha, "role": "PRIMARY_CONTROL",
                        "primaryAcceptanceEligible": True,
                    },
                    {
                        "armId": "G3_M1_SAME_IDENTITY_COLLAR_FREE", "runtimePath": str(m1),
                        "sha256": None, "sourcePath": str(source), "sourceSha256": source_sha,
                        "role": "PRIMARY_REMEDIATION", "primaryAcceptanceEligible": True,
                    },
                    {
                        "armId": "G3_P0_EXTERNAL_REFERENCE_PROBE", "runtimePath": str(external),
                        "sha256": external_sha, "role": "SECONDARY_MECHANISM_PROBE",
                        "primaryAcceptanceEligible": False,
                    },
                ],
            })
            protocol_path = repo / "experiments/ccv-r2/g3/protocol.template.json"
            protocol_path.parent.mkdir(parents=True)
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

            shots = []
            inputs = []
            for index, shot in enumerate(protocol["shots"], start=1):
                pose = runtime / f"pose_{shot}.png"
                Image.new("RGB", (8, 8), (index, index, index)).save(pose)
                shots.append({"shotId": shot, "description": shot, "poseInputId": f"pose-{index}"})
                inputs.append({"inputId": f"pose-{index}", "runtimePath": str(pose)})
            manifest = {
                "parameters": {
                    "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
                    "positivePrompt": "same person", "negativePrompt": "bad anatomy",
                },
                "shots": shots,
                "inputs": inputs,
            }
            manifest_path = repo / "experiments/ccv-r2/experiment-manifest.template.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            graph = {
                "1": {"class_type": "KSampler", "inputs": {"positive": [2, 0], "negative": [3, 0]}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
                "4": {"class_type": "LoadImage", "inputs": {"image": "reference_face.png"}},
                "5": {"class_type": "LoadImage", "inputs": {"image": "pose_01_medium_front.png"}},
                "6": {"class_type": "IPAdapterAdvanced", "inputs": {"weight": 0.6}},
                "7": {"class_type": "ControlNetApplyAdvanced", "inputs": {"strength": 0.8}},
                "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
            }
            base_path = prep / "workflows/a2_face_openpose.api.json"
            base_path.parent.mkdir(parents=True)
            base_path.write_bytes(prepare.canonical_bytes(graph))
            base_sha, base_size = prepare.sha256_file(base_path)

            verified_assets = []
            for index, path in enumerate([m0, source, external, *[Path(item["runtimePath"]) for item in inputs]], start=1):
                digest, size = prepare.sha256_file(path)
                verified_assets.append({
                    "label": f"asset-{index}", "path": str(path),
                    "sizeBytes": size, "sha256": digest,
                })
            while len(verified_assets) < 11:
                path = runtime / f"model-{len(verified_assets)}.bin"
                path.write_bytes(f"model-{len(verified_assets)}".encode())
                digest, size = prepare.sha256_file(path)
                verified_assets.append({
                    "label": f"asset-{len(verified_assets)}", "path": str(path),
                    "sizeBytes": size, "sha256": digest,
                })
            readiness = {
                "counts": {"runs": 45}, "verifiedAssets": verified_assets,
                "baseWorkflows": [{
                    "path": "workflows/a2_face_openpose.api.json",
                    "sizeBytes": base_size, "sha256": base_sha,
                }],
            }
            readiness_path = prep / "execution-readiness.json"
            readiness_path.write_bytes(prepare.canonical_bytes(readiness))
            prep_inventory_path = prep / "preparation-inventory.json"
            prep_inventory_path.write_bytes(prepare.canonical_bytes({"entries": []}))
            result_inventory_path = results / "result-inventory.json"
            result_inventory_path.write_bytes(prepare.canonical_bytes({"items": []}))
            receipt_path = m1.with_suffix(".derivation.json")
            prepare.derive_crop_reference(
                source, m1, receipt_path, source_sha, [6, 2, 18, 14], [16, 16], True
            )

            receipt_sha, _ = prepare.sha256_file(readiness_path)
            prep_sha, _ = prepare.sha256_file(prep_inventory_path)
            result_sha, _ = prepare.sha256_file(result_inventory_path)
            argv = [
                "prepare", "--repo-root", str(repo), "--g2-preparation-root", str(prep),
                "--g2-result-root", str(results), "--m1-reference", str(m1),
                "--external-reference", str(external), "--output-root", str(output),
            ]
            with (
                patch.object(prepare, "EXPECTED_G2_RECEIPT_SHA", receipt_sha),
                patch.object(prepare, "EXPECTED_G2_PREPARATION_INVENTORY_SHA", prep_sha),
                patch.object(prepare, "EXPECTED_G2_RESULT_INVENTORY_SHA", result_sha),
                patch("sys.argv", argv),
            ):
                self.assertEqual(0, prepare.main())
            readiness_sha, inventory_sha = validate.validate(output)
            self.assertEqual(64, len(readiness_sha))
            self.assertEqual(64, len(inventory_sha))


class ValidatorBoundaryTests(unittest.TestCase):
    def test_relative_path_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(validate.ValidationError):
                validate.confined(Path(temp), "../outside.json")

    def test_nonopaque_run_id_fails_closed_before_file_read(self):
        row = {
            "path": "requests/x.json", "sizeBytes": 1, "sha256": "0" * 64,
            "runId": "g3_m1__seed-123456", "blindLabel": "G3B001",
            "shotId": "01_medium_front", "seed": 123456, "phase": "MAIN",
            "plannedOutputPath": "outputs/x.png",
        }
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(validate.ValidationError, "non-opaque runId"):
                validate.validate_request(Path(temp), row)


if __name__ == "__main__":
    unittest.main()
