#!/usr/bin/env python3
"""Reproducible no-GPU checks for the CCV-R1 evidence harness.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_common import (  # noqa: E402
    EvidenceError,
    build_manifest,
    load_json,
    sha256_file,
    validate_config,
    validate_manifest_consistency,
    validate_model_compatibility,
    verify_file_record,
    verify_model_record,
)


def expect_failure(label: str, expected_text: str, operation) -> None:
    try:
        operation()
    except EvidenceError as error:
        if expected_text not in str(error):
            raise AssertionError(f"{label}: unexpected error: {error}") from error
        print(f"PASS {label}: {error}")
        return
    raise AssertionError(f"{label}: operation unexpectedly passed")


def write_safetensors_fixture(path: Path, tensor_name: str, conditioning_dimension: int) -> None:
    shape = [2, conditioning_dimension]
    tensor_bytes = shape[0] * shape[1] * 2
    header = {
        tensor_name: {
            "dtype": "F16",
            "shape": shape,
            "data_offsets": [0, tensor_bytes],
        }
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(len(encoded).to_bytes(8, byteorder="little") + encoded + bytes(tensor_bytes))


def file_record(path: Path, *, role: str, family: str, dimension: int) -> dict:
    return {
        "role": role,
        "logicalName": path.name,
        "filePath": str(path),
        "sizeBytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "modelFamily": family,
        "conditioningDimension": dimension,
    }


def combined_pending_manifest(configs: list[dict], all_runs: list[dict]) -> dict:
    models = []
    artifacts = []
    for config in configs:
        for model in config["models"]:
            models.append({"roundId": config["roundId"], **model})
        for artifact in config.get("artifacts", []):
            artifacts.append({"roundId": config["roundId"], **artifact})
    return {
        "$schema": "./experiment-manifest.schema.json",
        "manifestVersion": "1.0",
        "experimentId": "acs-ccv-r1",
        "roundId": "all-rounds",
        "status": "EXPERIMENT_REPORTED_INDEPENDENT_REPRODUCTION_NOT_POSSIBLE",
        "rightsLabels": ["SYNTHETIC_TEST_ONLY", "NOT_FOR_PRODUCTION"],
        "historicalExecutionDate": "2026-08-14",
        "manifestCreatedAt": None,
        "historicalScriptBytesRecovered": False,
        "hardenedSuccessorScripts": [
            {
                "role": "hardened_successor_script",
                "logicalName": script_name,
                "sizeBytes": (ROOT / "scripts" / script_name).stat().st_size,
                "sha256": sha256_file(ROOT / "scripts" / script_name),
            }
            for script_name in (
                "character_consistency_test.py",
                "ipadapter_face_test.py",
                "ipadapter_pose_test.py",
                "evidence_common.py",
            )
        ],
        "environment": {config["roundId"]: config["environment"] for config in configs},
        "models": models,
        "artifacts": artifacts,
        "expectedRunCount": len(all_runs),
        "runs": all_runs,
        "claims": {
            "validationAccepted": False,
            "independentReproductionPossible": False,
            "schemaChangeAuthorized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CCV-R1 no-GPU validation and optionally write the combined pending manifest")
    parser.add_argument("--write-pending-manifest", type=Path)
    args = parser.parse_args()

    counts: list[int] = []
    configs: list[dict] = []
    all_runs: list[dict] = []
    for round_id in ("round-1", "round-2", "round-3"):
        config = load_json(ROOT / "configs" / f"{round_id}.json")
        runs = validate_config(config, round_id)
        validate_model_compatibility(config["models"])
        configs.append(config)
        all_runs.extend(runs)
        counts.append(len(runs))
    if counts != [10, 25, 15] or sum(counts) != 50:
        raise AssertionError(f"unexpected run matrix: {counts}")
    print("PASS run matrix: round-1=10, round-2=25, round-3=15, total=50")
    round_three = configs[2]
    skeletons = [artifact for artifact in round_three["artifacts"] if artifact["role"] == "pose_skeleton"]
    skeleton_names = {artifact["logicalName"] for artifact in skeletons}
    run_skeleton_names = {run["parameters"]["poseSkeletonLogicalName"] for run in all_runs if run["roundId"] == "round-3"}
    if len(skeletons) != 5 or skeleton_names != run_skeleton_names:
        raise AssertionError("Round 3 pose skeleton evidence is not a five-file one-to-one register")
    print("PASS Round 3 five pose skeleton files are individually registered and linked to runs")

    pending_manifest = combined_pending_manifest(configs, all_runs)
    validate_manifest_consistency(pending_manifest, finalized=False)
    print("PASS pending manifest count and uniqueness validation")
    wrong_count = copy.deepcopy(pending_manifest)
    wrong_count["expectedRunCount"] = 49
    expect_failure(
        "manifest count mismatch fails closed",
        "does not match runs",
        lambda: validate_manifest_consistency(wrong_count, finalized=False),
    )
    captured_with_nulls = copy.deepcopy(pending_manifest)
    captured_with_nulls["status"] = "EVIDENCE_CAPTURED_NOT_VALIDATION_ACCEPTED"
    captured_with_nulls["manifestCreatedAt"] = "2026-08-14T00:00:00+00:00"
    expect_failure(
        "captured manifest null evidence fails closed",
        "positive sizeBytes is required",
        lambda: validate_manifest_consistency(captured_with_nulls, finalized=True),
    )

    schema = load_json(ROOT / "experiment-manifest.schema.json")
    seed_schema = schema["$defs"]["runEvidence"]["properties"]["parameters"]["properties"]["seed"]
    finalized_seed = schema["$defs"]["finalizedRunEvidence"]["allOf"][1]["properties"]["parameters"]["properties"]["seed"]
    captured_rule = next(
        rule
        for rule in schema.get("allOf", [])
        if rule.get("if", {}).get("properties", {}).get("status", {}).get("const")
        == "EVIDENCE_CAPTURED_NOT_VALIDATION_ACCEPTED"
    )
    captured_properties = captured_rule["then"]["properties"]
    if (
        seed_schema.get("type") != ["integer", "null"]
        or finalized_seed.get("type") != "integer"
        or captured_properties["models"]["items"].get("$ref") != "#/$defs/finalizedModelEvidence"
        or captured_properties["runs"]["items"].get("$ref") != "#/$defs/finalizedRunEvidence"
    ):
        raise AssertionError("manifest schema lacks pending/finalized seed or status conditions")
    print("PASS manifest schema declares seed types and finalized-status conditions")

    with tempfile.TemporaryDirectory(prefix="ccv-r1-") as temp:
        temp_root = Path(temp)
        empty = temp_root / "empty.safetensors"
        empty.touch()
        empty_record = {
            "filePath": str(empty),
            "sizeBytes": 1,
            "sha256": "0" * 64,
        }
        expect_failure(
            "zero-byte model fails closed",
            "zero-byte file rejected",
            lambda: verify_file_record(empty_record, "pose_control"),
        )

        nonempty = temp_root / "model.safetensors"
        nonempty.write_bytes(b"ccv-r1-validation-fixture")
        payload = nonempty.read_bytes()
        valid_record = {
            "filePath": str(nonempty),
            "sizeBytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        verify_file_record(valid_record, "fixture")
        print("PASS non-empty file size and SHA-256 verification")
        missing_sha_record = {
            "filePath": str(nonempty),
            "sizeBytes": len(payload),
            "sha256": None,
        }
        expect_failure(
            "missing checksum fails closed",
            "SHA-256 is required",
            lambda: verify_file_record(missing_sha_record, "fixture"),
        )

        arbitrary = temp_root / "arbitrary.safetensors"
        arbitrary.write_bytes(b"not-a-safetensors-model")
        arbitrary_record = file_record(arbitrary, role="base", family="sdxl", dimension=2048)
        expect_failure(
            "arbitrary bytes cannot masquerade as a model",
            "safetensors header",
            lambda: verify_model_record(arbitrary_record, "base fixture"),
        )
        encoder_record = file_record(arbitrary, role="image_encoder", family="clip-vit-h", dimension=1024)
        expect_failure(
            "arbitrary bytes cannot masquerade as an image encoder",
            "safetensors header",
            lambda: verify_model_record(encoder_record, "image encoder fixture"),
        )

        sd15 = temp_root / "sd15-disguised-as-sdxl.safetensors"
        write_safetensors_fixture(sd15, "model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight", 768)
        disguised_record = file_record(sd15, role="base", family="sdxl", dimension=2048)
        expect_failure(
            "actual SD1.5 width cannot masquerade as declared SDXL",
            "actual conditioning dimension 768 does not match declaration 2048",
            lambda: verify_model_record(disguised_record, "base fixture"),
        )

        sdxl = temp_root / "sdxl.safetensors"
        write_safetensors_fixture(sdxl, "model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight", 2048)
        valid_sdxl = file_record(sdxl, role="base", family="sdxl", dimension=2048)
        _, digest, architecture = verify_model_record(valid_sdxl, "base fixture")
        if architecture is None or architecture["modelSha256"] != digest or architecture["conditioningDimension"] != 2048:
            raise AssertionError("actual safetensors architecture evidence was not tied to the model digest")
        print("PASS actual safetensors header evidence is tied to model SHA-256")

        unknown = temp_root / "unknown.safetensors"
        write_safetensors_fixture(unknown, "unrelated.weight", 2048)
        unknown_record = file_record(unknown, role="base", family="sdxl", dimension=2048)
        expect_failure(
            "unknown model architecture fails closed",
            "no recognized conditioning tensor",
            lambda: verify_model_record(unknown_record, "base fixture"),
        )

        finalized_config = copy.deepcopy(round_three)
        model_tensor_names = {
            "base": "model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight",
            "identity_adapter": "ip_adapter.1.to_k_ip.weight",
            "pose_control": "control_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight",
        }
        for index, model in enumerate(finalized_config["models"]):
            model_path = temp_root / f"model-{index}.safetensors"
            tensor_name = model_tensor_names.get(model["role"])
            if tensor_name is None:
                write_safetensors_fixture(model_path, "text_model.encoder.layer.weight", model["conditioningDimension"])
            else:
                write_safetensors_fixture(model_path, tensor_name, model["conditioningDimension"])
            model["filePath"] = str(model_path)
            model["sizeBytes"] = model_path.stat().st_size
            model["sha256"] = sha256_file(model_path)

        for index, artifact in enumerate(finalized_config["artifacts"]):
            artifact_path = temp_root / f"artifact-{index}.bin"
            artifact_path.write_bytes(f"artifact-{index}".encode("utf-8"))
            artifact["filePath"] = str(artifact_path)
            artifact["sizeBytes"] = artifact_path.stat().st_size
            artifact["sha256"] = sha256_file(artifact_path)

        finalized_config["matrices"][0]["fixedParameters"]["seed"] = 123456
        finalized_runs = validate_config(finalized_config, "round-3")
        output_root = temp_root / "outputs-root"
        for run in finalized_runs:
            output_path = output_root / run["output"]["logicalPath"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(run["runId"].encode("utf-8"))
        finalized_manifest = build_manifest(
            finalized_config,
            finalized_runs,
            finalized=True,
            runner_script=ROOT / "scripts" / "ipadapter_pose_test.py",
            output_root=output_root,
        )
        architecture_records = [
            model for model in finalized_manifest["models"] if "architectureEvidence" in model
        ]
        finalized_skeletons = [
            artifact for artifact in finalized_manifest["artifacts"] if artifact["role"] == "pose_skeleton"
        ]
        if len(architecture_records) != 3 or len(finalized_skeletons) != 5:
            raise AssertionError("finalized evidence manifest lost architecture or skeleton records")
        print("PASS complete Round 3 manifest finalization with three model attestations and five skeleton digests")
        unlinked_architecture = copy.deepcopy(finalized_manifest)
        unlinked_architecture["models"][0]["architectureEvidence"]["modelSha256"] = "0" * 64
        expect_failure(
            "architecture attestation must remain tied to model digest",
            "architecture evidence is not tied to model SHA-256",
            lambda: validate_manifest_consistency(unlinked_architecture, finalized=True),
        )

    mismatched = [
        {
            "role": "base",
            "modelFamily": "sdxl",
            "conditioningDimension": 2048,
        },
        {
            "role": "pose_control",
            "modelFamily": "sd15",
            "conditioningDimension": 768,
        },
    ]
    expect_failure(
        "SD1.5/SDXL mismatch fails closed",
        "does not match base",
        lambda: validate_model_compatibility(mismatched),
    )

    if args.write_pending_manifest:
        args.write_pending_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_pending_manifest.write_text(
            json.dumps(pending_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"PASS wrote combined pending manifest with {len(all_runs)} run rows")

    print("CCV-R1 no-GPU fail-closed validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
