"""CCV-R1 evidence utilities.

EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION

These utilities harden evidence collection for a future rerun or recovery of the
2026-08-14 external-GPU experiment.  They do not reproduce that historical run.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RIGHTS_LABELS = ("SYNTHETIC_TEST_ONLY", "NOT_FOR_PRODUCTION")
PENDING_STATUS = "EXPERIMENT_REPORTED_INDEPENDENT_REPRODUCTION_NOT_POSSIBLE"
FINAL_STATUS = "EVIDENCE_CAPTURED_NOT_VALIDATION_ACCEPTED"
PARTIAL_STATUS = "EVIDENCE_CAPTURE_PARTIAL_NOT_VALIDATION_ACCEPTED"
MAX_SAFETENSORS_HEADER_BYTES = 64 * 1024 * 1024
CONDITIONING_TENSOR_SUFFIXES = {
    "base": (".attn2.to_k.weight", ".attn2.to_v.weight"),
    "pose_control": (".attn2.to_k.weight", ".attn2.to_v.weight"),
    "identity_adapter": (".to_k_ip.weight", ".to_v_ip.weight"),
}
SAFETENSORS_DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E4M3FN": 1,
    "F8_E4M3FNUZ": 1,
    "F8_E5M2": 1,
    "F8_E5M2FNUZ": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "I64": 8,
    "U64": 8,
    "F64": 8,
}


class EvidenceError(ValueError):
    """Raised when evidence cannot be accepted without guessing."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read JSON {path}: {error}") from error
    _require(isinstance(value, dict), f"{path}: top-level value must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_safetensors_header(path: Path, label: str) -> tuple[dict[str, Any], bytes, int, int]:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            prefix = stream.read(8)
            _require(len(prefix) == 8, f"{label}: invalid safetensors header prefix")
            header_size = int.from_bytes(prefix, byteorder="little", signed=False)
            _require(header_size > 1, f"{label}: invalid safetensors header length {header_size}")
            _require(
                header_size <= MAX_SAFETENSORS_HEADER_BYTES,
                f"{label}: safetensors header exceeds {MAX_SAFETENSORS_HEADER_BYTES} bytes",
            )
            _require(header_size <= file_size - 8, f"{label}: truncated safetensors header")
            header_bytes = stream.read(header_size)
    except OSError as error:
        raise EvidenceError(f"{label}: cannot inspect safetensors file {path}: {error}") from error

    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"{label}: invalid safetensors header JSON") from error
    _require(isinstance(header, dict), f"{label}: safetensors header must be an object")
    return header, header_bytes, header_size, file_size


def validate_safetensors_container(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    header, header_bytes, header_size, file_size = read_safetensors_header(path, label)
    tensor_count = 0
    data_ranges: list[tuple[int, int, str]] = []
    for tensor_name, tensor in header.items():
        if tensor_name == "__metadata__":
            continue
        tensor_count += 1
        _require(isinstance(tensor, dict), f"{label}: invalid tensor record {tensor_name}")
        shape = tensor.get("shape")
        _require(
            isinstance(shape, list)
            and all(isinstance(dimension, int) and dimension >= 0 for dimension in shape),
            f"{label}: invalid tensor shape for {tensor_name}",
        )
        dtype = tensor.get("dtype")
        offsets = tensor.get("data_offsets")
        _require(dtype in SAFETENSORS_DTYPE_BYTES, f"{label}: unsupported dtype for {tensor_name}")
        _require(
            isinstance(offsets, list)
            and len(offsets) == 2
            and all(isinstance(offset, int) and offset >= 0 for offset in offsets)
            and offsets[0] <= offsets[1],
            f"{label}: invalid data_offsets for {tensor_name}",
        )
        element_count = 1
        for dimension in shape:
            element_count *= dimension
        expected_bytes = element_count * SAFETENSORS_DTYPE_BYTES[dtype]
        _require(offsets[1] - offsets[0] == expected_bytes, f"{label}: tensor byte length mismatch for {tensor_name}")
        _require(8 + header_size + offsets[1] <= file_size, f"{label}: truncated tensor data for {tensor_name}")
        data_ranges.append((offsets[0], offsets[1], tensor_name))
    _require(tensor_count > 0, f"{label}: safetensors file has no tensors")
    cursor = 0
    for start, end, tensor_name in sorted(data_ranges):
        _require(start == cursor, f"{label}: non-contiguous or overlapping data before {tensor_name}")
        cursor = end
    _require(8 + header_size + cursor == file_size, f"{label}: unregistered bytes after safetensors tensor data")
    return header, header_bytes


def inspect_safetensors_architecture(path: Path, role: str, model_sha256: str) -> dict[str, Any]:
    """Derive conditioning width from the actual safetensors header.

    The declared family and width are not accepted as architecture evidence.  The
    role-specific tensor suffixes identify the cross-attention inputs whose final
    shape dimension distinguishes the supported SD1.5 and SDXL families.
    """

    suffixes = CONDITIONING_TENSOR_SUFFIXES.get(role)
    _require(suffixes is not None, f"{role}: no safetensors architecture rule")
    header, header_bytes = validate_safetensors_container(path, role)

    matched: list[tuple[str, int]] = []
    for tensor_name, tensor in header.items():
        if tensor_name == "__metadata__" or not any(tensor_name.endswith(suffix) for suffix in suffixes):
            continue
        shape = tensor.get("shape")
        _require(
            isinstance(shape, list)
            and shape
            and all(isinstance(dimension, int) and dimension > 0 for dimension in shape),
            f"{role}: invalid tensor shape for {tensor_name}",
        )
        matched.append((tensor_name, shape[-1]))

    _require(matched, f"{role}: no recognized conditioning tensor in safetensors header")
    dimensions = {dimension for _, dimension in matched}
    _require(len(dimensions) == 1, f"{role}: ambiguous conditioning dimensions {sorted(dimensions)}")
    dimension = next(iter(dimensions))
    _require(dimension in {768, 2048}, f"{role}: unsupported conditioning dimension {dimension}")
    return {
        "format": "safetensors",
        "modelSha256": model_sha256,
        "headerSha256": hashlib.sha256(header_bytes).hexdigest(),
        "conditioningDimension": dimension,
        "evidenceTensorKeys": [name for name, _ in sorted(matched)],
    }


def validate_config(config: dict[str, Any], expected_round: str) -> list[dict[str, Any]]:
    _require(config.get("configVersion") == "1.0", "configVersion must be 1.0")
    _require(config.get("roundId") == expected_round, f"roundId must be {expected_round}")
    _require(config.get("experimentId") == "acs-ccv-r1", "unexpected experimentId")
    _require(config.get("evidenceStatus") == "PENDING_EXTERNAL_EVIDENCE", "evidenceStatus must remain pending")
    _require(tuple(config.get("rightsLabels", ())) == RIGHTS_LABELS, "rightsLabels must be the frozen synthetic-only labels")

    parameters = config.get("globalParameters")
    _require(isinstance(parameters, dict), "globalParameters must be an object")
    for key in ("positivePrompt", "negativePrompt", "width", "height", "steps", "cfg", "sampler", "scheduler"):
        _require(key in parameters, f"globalParameters.{key} is required")
    _require(isinstance(parameters["width"], int) and parameters["width"] > 0, "width must be a positive integer")
    _require(isinstance(parameters["height"], int) and parameters["height"] > 0, "height must be a positive integer")
    _require(isinstance(parameters["steps"], int) and parameters["steps"] > 0, "steps must be a positive integer")
    _require(isinstance(parameters["cfg"], (int, float)) and parameters["cfg"] > 0, "cfg must be positive")

    shots = config.get("shots")
    _require(isinstance(shots, list) and shots, "shots must be a non-empty list")
    shot_ids = [shot.get("shotId") for shot in shots if isinstance(shot, dict)]
    _require(len(shot_ids) == len(shots), "each shot must be an object with shotId")
    _require(len(set(shot_ids)) == len(shot_ids), "shotId values must be unique")
    shot_set = set(shot_ids)

    models = config.get("models")
    _require(isinstance(models, list) and models, "models must be a non-empty list")
    for index, model in enumerate(models):
        _require(isinstance(model, dict), f"models[{index}] must be an object")
        for key in ("role", "logicalName", "modelFamily", "conditioningDimension", "source", "licenseStatus"):
            _require(key in model, f"models[{index}].{key} is required")

    artifacts = config.get("artifacts", [])
    _require(isinstance(artifacts, list), "artifacts must be a list")
    for index, artifact in enumerate(artifacts):
        _require(isinstance(artifact, dict), f"artifacts[{index}] must be an object")
        _require(isinstance(artifact.get("role"), str) and artifact["role"], f"artifacts[{index}].role is required")
        _require(
            isinstance(artifact.get("logicalName"), str) and artifact["logicalName"],
            f"artifacts[{index}].logicalName is required",
        )
    if expected_round == "round-3":
        skeletons = [artifact for artifact in artifacts if artifact.get("role") == "pose_skeleton"]
        _require(len(skeletons) == len(shots), "round-3 requires one pose_skeleton artifact per shot")
        skeleton_names = [artifact.get("logicalName") for artifact in skeletons]
        _require(all(isinstance(name, str) and name for name in skeleton_names), "pose_skeleton logicalName is required")
        _require(len(set(skeleton_names)) == len(skeleton_names), "pose_skeleton logicalName values must be unique")

    matrices = config.get("matrices")
    _require(isinstance(matrices, list) and matrices, "matrices must be a non-empty list")
    runs: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    output_paths: set[str] = set()
    for matrix_index, matrix in enumerate(matrices):
        _require(isinstance(matrix, dict), f"matrices[{matrix_index}] must be an object")
        batch_id = matrix.get("batchId")
        axes = matrix.get("axes")
        output_pattern = matrix.get("outputPattern")
        _require(isinstance(batch_id, str) and batch_id, f"matrices[{matrix_index}].batchId is required")
        _require(isinstance(axes, dict) and axes, f"{batch_id}.axes must be a non-empty object")
        _require(isinstance(output_pattern, str) and output_pattern.endswith(".png"), f"{batch_id}.outputPattern must name a PNG")
        axis_names = list(axes)
        axis_values: list[list[Any]] = []
        for axis_name in axis_names:
            values = axes[axis_name]
            _require(isinstance(values, list) and values, f"{batch_id}.axes.{axis_name} must be non-empty")
            axis_values.append(values)
        for combination in itertools.product(*axis_values):
            axis_parameters = dict(zip(axis_names, combination, strict=True))
            shot_id = axis_parameters.get("shotId")
            _require(shot_id in shot_set, f"{batch_id}: unknown shotId {shot_id!r}")
            run_parameters = dict(matrix.get("fixedParameters", {}))
            run_parameters.update(axis_parameters)
            per_shot = matrix.get("perShotParameters", {})
            _require(isinstance(per_shot, dict), f"{batch_id}.perShotParameters must be an object")
            for parameter_name, values_by_shot in per_shot.items():
                _require(isinstance(values_by_shot, dict), f"{batch_id}.{parameter_name} per-shot values must be an object")
                _require(shot_id in values_by_shot, f"{batch_id}.{parameter_name} missing {shot_id}")
                run_parameters[parameter_name] = values_by_shot[shot_id]
            if expected_round == "round-3":
                skeleton_name = run_parameters.get("poseSkeletonLogicalName")
                _require(skeleton_name in skeleton_names, f"{batch_id}: unknown pose skeleton {skeleton_name!r}")
            substitutions = {key: _path_token(value) for key, value in run_parameters.items()}
            substitutions["batchId"] = batch_id
            try:
                output_path = output_pattern.format(**substitutions)
            except KeyError as error:
                raise EvidenceError(f"{batch_id}.outputPattern missing substitution {error}") from error
            run_suffix = "__".join(f"{key}-{_path_token(value)}" for key, value in axis_parameters.items())
            run_id = f"{batch_id}__{run_suffix}"
            _require(run_id not in run_ids, f"duplicate runId {run_id}")
            _require(output_path not in output_paths, f"duplicate output path {output_path}")
            run_ids.add(run_id)
            output_paths.add(output_path)
            all_parameters = dict(parameters)
            all_parameters.update(run_parameters)
            runs.append(
                {
                    "runId": run_id,
                    "roundId": expected_round,
                    "batchId": batch_id,
                    "shotId": shot_id,
                    "parameters": all_parameters,
                    "output": {
                        "logicalPath": output_path,
                        "sizeBytes": None,
                        "sha256": None,
                    },
                    "runState": "PENDING_EXTERNAL_EVIDENCE",
                    "failure": None,
                    "retryOfRunId": None,
                    "excluded": False,
                    "exclusionReason": None,
                }
            )
    return runs


def _path_token(value: Any) -> str:
    if value is None:
        return "PENDING"
    if isinstance(value, float):
        return format(value, "g").replace(".", "p")
    return str(value).replace("/", "-").replace(" ", "-")


def validate_model_compatibility(models: list[dict[str, Any]]) -> None:
    """Validate declaration-to-declaration compatibility before evidence exists."""

    conditioning = [model for model in models if model["role"] in {"base", "identity_adapter", "pose_control"}]
    _require(any(model["role"] == "base" for model in conditioning), "one base model is required")
    base = next(model for model in conditioning if model["role"] == "base")
    base_family = base["modelFamily"]
    base_dimension = base["conditioningDimension"]
    _require(base_family in {"sd15", "sdxl"}, "base modelFamily must be sd15 or sdxl")
    _require(base_dimension in {768, 2048}, "base conditioningDimension must be 768 or 2048")
    expected_dimension = 768 if base_family == "sd15" else 2048
    _require(base_dimension == expected_dimension, f"{base_family} must declare conditioningDimension {expected_dimension}")
    for model in conditioning:
        _require(model["modelFamily"] == base_family, f"{model['role']} modelFamily {model['modelFamily']} does not match base {base_family}")
        _require(model["conditioningDimension"] == base_dimension, f"{model['role']} conditioning dimension {model['conditioningDimension']} does not match base {base_dimension}")


def verify_file_record(record: dict[str, Any], label: str) -> tuple[int, str]:
    file_path = record.get("filePath")
    expected_size = record.get("sizeBytes")
    expected_sha = record.get("sha256")
    _require(isinstance(file_path, str) and file_path, f"{label}: filePath is required for finalization")
    _require(isinstance(expected_size, int) and expected_size > 0, f"{label}: positive sizeBytes is required")
    _require(_is_sha256(expected_sha), f"{label}: lowercase SHA-256 is required")
    path = Path(file_path).expanduser()
    _require(path.is_file(), f"{label}: file does not exist: {path}")
    actual_size = path.stat().st_size
    _require(actual_size > 0, f"{label}: zero-byte file rejected: {path}")
    _require(actual_size == expected_size, f"{label}: size mismatch expected {expected_size}, got {actual_size}")
    actual_sha = sha256_file(path)
    _require(actual_sha == expected_sha.lower(), f"{label}: SHA-256 mismatch")
    return actual_size, actual_sha


def verify_model_record(record: dict[str, Any], label: str) -> tuple[int, str, dict[str, Any] | None]:
    size, digest = verify_file_record(record, label)
    role = record.get("role")
    if role not in CONDITIONING_TENSOR_SUFFIXES:
        validate_safetensors_container(Path(record["filePath"]).expanduser(), str(role))
        return size, digest, None
    path = Path(record["filePath"]).expanduser()
    architecture = inspect_safetensors_architecture(path, role, digest)
    declared_dimension = record.get("conditioningDimension")
    actual_dimension = architecture["conditioningDimension"]
    _require(
        actual_dimension == declared_dimension,
        f"{label}: actual conditioning dimension {actual_dimension} does not match declaration {declared_dimension}",
    )
    expected_family = "sd15" if actual_dimension == 768 else "sdxl"
    _require(
        record.get("modelFamily") == expected_family,
        f"{label}: actual model family {expected_family} does not match declaration {record.get('modelFamily')}",
    )
    return size, digest, architecture


def historical_script_bytes_recovered(records: list[dict[str, Any]]) -> bool:
    """Derive historical-script custody from the exact three script records."""

    expected = {
        "character_consistency_test.py",
        "ipadapter_face_test.py",
        "ipadapter_pose_test.py",
    }
    by_name = {
        record.get("logicalName"): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("logicalName"), str)
    }
    if set(by_name) != expected:
        return False
    return all(
        record.get("collectionState") == "RECOVERED"
        and isinstance(record.get("sizeBytes"), int)
        and record["sizeBytes"] > 0
        and _is_sha256(record.get("sha256"))
        for record in by_name.values()
    )


def _validate_historical_capture_manifest(manifest: dict[str, Any]) -> None:
    scripts = manifest.get("historicalScripts")
    _require(isinstance(scripts, list), "historical capture requires historicalScripts")
    expected_scripts = {
        "character_consistency_test.py",
        "ipadapter_face_test.py",
        "ipadapter_pose_test.py",
    }
    _require(
        {record.get("logicalName") for record in scripts if isinstance(record, dict)} == expected_scripts,
        "historicalScripts must contain the exact three historical scripts",
    )
    derived_script_state = historical_script_bytes_recovered(scripts)
    _require(
        manifest.get("historicalScriptBytesRecovered") is derived_script_state,
        "historicalScriptBytesRecovered must be derived from the three historical-script records",
    )

    models = manifest.get("models")
    artifacts = manifest.get("artifacts")
    _require(isinstance(models, list) and isinstance(artifacts, list), "historical evidence collections are required")
    evidence_records = scripts + models + artifacts
    evidence_refs = [record.get("evidenceRef") for record in evidence_records]
    _require(len(evidence_records) == 27, "historical capture must contain exactly 27 non-output evidence records")
    _require(
        len(evidence_refs) == len(set(evidence_refs)) and all(isinstance(ref, str) and ref for ref in evidence_refs),
        "historical evidenceRef values must be unique",
    )
    evidence_by_ref = {record["evidenceRef"]: record for record in evidence_records}

    allowed_states = {"RECOVERED", "MISSING", "AMBIGUOUS"}
    allowed_usage_states = {"VERIFIED", "UNVERIFIED", "NOT_APPLICABLE"}
    for record in evidence_records:
        label = record.get("evidenceRef", "unknown-evidence")
        state = record.get("collectionState")
        _require(state in allowed_states, f"{label}: invalid collectionState")
        _require(record.get("usageLinkState") in allowed_usage_states, f"{label}: invalid usageLinkState")
        usage_refs = record.get("usageLinkEvidenceRefs")
        _require(
            isinstance(usage_refs, list)
            and len(usage_refs) == len(set(usage_refs))
            and all(ref in evidence_refs for ref in usage_refs),
            f"{label}: invalid usageLinkEvidenceRefs",
        )
        if record.get("usageLinkState") == "VERIFIED":
            _require(usage_refs, f"{label}: VERIFIED usage requires evidence references")
            _require(
                all(evidence_by_ref[ref].get("collectionState") == "RECOVERED" for ref in usage_refs),
                f"{label}: VERIFIED usage cannot reference unavailable evidence",
            )
        if state == "RECOVERED":
            _require(isinstance(record.get("filePath"), str) and record["filePath"], f"{label}: recovered filePath is required")
            _require(isinstance(record.get("sizeBytes"), int) and record["sizeBytes"] > 0, f"{label}: recovered sizeBytes is required")
            _require(_is_sha256(record.get("sha256")), f"{label}: recovered SHA-256 is required")
            _require(isinstance(record.get("storageRef"), str) and record["storageRef"], f"{label}: recovered storageRef is required")
        else:
            _require(record.get("filePath") is None, f"{label}: unavailable filePath must be null")
            _require(record.get("sizeBytes") is None and record.get("sha256") is None, f"{label}: unavailable digest fields must be null")

    model_roles = {"base", "identity_adapter", "image_encoder", "pose_control"}
    for model in models:
        if model.get("collectionState") != "RECOVERED":
            continue
        label = model.get("evidenceRef", "unknown-model")
        _require(model.get("role") in model_roles, f"{label}: unexpected model role")
        _require(
            isinstance(model.get("source"), str) and model["source"] and not model["source"].startswith("PENDING"),
            f"{label}: recovered model source must be explicit",
        )
        _require(
            isinstance(model.get("licenseStatus"), str)
            and model["licenseStatus"]
            and not model["licenseStatus"].startswith("PENDING"),
            f"{label}: recovered model licenseStatus must be explicit",
        )

    face_crop = next(record for record in evidence_records if record.get("evidenceRef") == "ccv-r1-reference-face-crop")
    if face_crop.get("collectionState") == "RECOVERED":
        lineage = face_crop.get("lineage")
        _require(isinstance(lineage, dict), "face crop requires explicit lineage")
        _require(
            lineage.get("parentEvidenceRef") == "ccv-r1-reference-full-body"
            and lineage.get("operation") == "FACE_CROP",
            "face crop lineage must reference the full-body source",
        )
        _require(
            evidence_by_ref["ccv-r1-reference-full-body"].get("collectionState") == "RECOVERED",
            "face crop lineage parent must be recovered",
        )

    receipt = manifest.get("captureReceipt")
    _require(isinstance(receipt, dict), "historical capture requires captureReceipt")
    recovered_count = sum(record.get("collectionState") == "RECOVERED" for record in evidence_records)
    _require(receipt.get("recordCount") == 27, "captureReceipt.recordCount must be 27")
    _require(receipt.get("recoveredRecordCount") == recovered_count, "captureReceipt recovered count mismatch")

    runs = manifest["runs"]
    run_ids = {run["runId"] for run in runs}
    for run in runs:
        label = run["runId"]
        output = run.get("output")
        _require(isinstance(output, dict), f"{label}: output is required")
        state = output.get("collectionState")
        expected_run_state = {
            "RECOVERED": "CAPTURED",
            "MISSING": "MISSING_EVIDENCE",
            "AMBIGUOUS": "AMBIGUOUS_EVIDENCE",
        }.get(state)
        _require(expected_run_state is not None and run.get("runState") == expected_run_state, f"{label}: output/run state mismatch")
        usage_refs = output.get("usageLinkEvidenceRefs")
        _require(
            isinstance(usage_refs, list)
            and len(usage_refs) == len(set(usage_refs))
            and all(ref in evidence_by_ref for ref in usage_refs),
            f"{label}: invalid output usageLinkEvidenceRefs",
        )
        if output.get("usageLinkState") == "VERIFIED":
            _require(usage_refs, f"{label}: VERIFIED output usage requires evidence references")
            _require(
                all(evidence_by_ref[ref].get("collectionState") == "RECOVERED" for ref in usage_refs),
                f"{label}: VERIFIED output usage cannot reference unavailable evidence",
            )
        if state == "RECOVERED":
            _require(isinstance(output.get("filePath"), str) and output["filePath"], f"{label}: recovered output filePath is required")
            _require(isinstance(output.get("sizeBytes"), int) and output["sizeBytes"] > 0, f"{label}: recovered output sizeBytes is required")
            _require(_is_sha256(output.get("sha256")), f"{label}: recovered output SHA-256 is required")
        else:
            _require(output.get("filePath") is None, f"{label}: unavailable output filePath must be null")
            _require(output.get("sizeBytes") is None and output.get("sha256") is None, f"{label}: unavailable output digest fields must be null")
    failure_ledger = manifest.get("failureLedger")
    _require(isinstance(failure_ledger, list) and failure_ledger, "failureLedger must be a non-empty list")
    event_ids = [event.get("eventId") for event in failure_ledger]
    _require(
        len(event_ids) == len(set(event_ids)) and all(isinstance(event_id, str) and event_id for event_id in event_ids),
        "failureLedger eventId values must be unique",
    )
    event_types = {"FAILURE", "RETRY", "EXCLUSION"}
    event_states = {"RECOVERED", "MISSING", "AMBIGUOUS"}
    known_failure_refs = {
        "ccv-r1-failure-zero-byte-controlnet",
        "ccv-r1-failure-sd15-sdxl",
    }
    linked_failure_refs: set[str] = set()
    for event in failure_ledger:
        label = event.get("eventId", "unknown-event")
        _require(event.get("eventType") in event_types, f"{label}: invalid eventType")
        _require(event.get("eventState") in event_states, f"{label}: invalid eventState")
        for field in ("runId", "relatedRunId"):
            value = event.get(field)
            _require(value is None or value in run_ids, f"{label}: unknown {field}")
        source_refs = event.get("sourceEvidenceRefs")
        _require(
            isinstance(source_refs, list)
            and len(source_refs) == len(set(source_refs))
            and all(ref in evidence_refs for ref in source_refs),
            f"{label}: invalid sourceEvidenceRefs",
        )
        linked_failure_refs.update(ref for ref in source_refs if ref in known_failure_refs)
        if event.get("eventState") == "RECOVERED":
            _require(
                all(evidence_by_ref[ref].get("collectionState") == "RECOVERED" for ref in source_refs),
                f"{label}: recovered event cannot reference unavailable evidence",
            )
        _require(isinstance(event.get("summary"), str) and event["summary"], f"{label}: summary is required")
    _require(linked_failure_refs == known_failure_refs, "failureLedger must retain both known failure records")

    complete = (
        recovered_count == 27
        and all(run.get("runState") == "CAPTURED" for run in runs)
        and all(type(run.get("parameters", {}).get("seed")) is int for run in runs)
        and all(run.get("excluded") is False for run in runs)
        and all(event.get("eventState") == "RECOVERED" for event in failure_ledger)
    )
    _require(receipt.get("captureComplete") is complete, "captureReceipt.captureComplete must be derived")
    expected_status = FINAL_STATUS if complete else PARTIAL_STATUS
    _require(manifest.get("status") == expected_status, "historical capture status must be derived from completeness")
    claims = manifest.get("claims")
    _require(isinstance(claims, dict), "historical capture claims are required")
    _require(claims.get("captureComplete") is complete, "claims.captureComplete must be derived")
    verified_usage = all(
        record.get("collectionState") == "RECOVERED"
        and record.get("usageLinkState") in {"VERIFIED", "NOT_APPLICABLE"}
        for record in evidence_records
    ) and all(
        run.get("runState") == "CAPTURED"
        and run.get("output", {}).get("usageLinkState") in {"VERIFIED", "NOT_APPLICABLE"}
        for run in runs
    ) and all(event.get("eventState") == "RECOVERED" for event in failure_ledger)
    _require(claims.get("historicalUsageVerified") is verified_usage, "historicalUsageVerified must be derived")
    _require(claims.get("validationAccepted") is False, "capture cannot accept validation")
    _require(claims.get("independentReproductionPossible") is False, "capture cannot claim reproduction")
    _require(claims.get("schemaChangeAuthorized") is False, "capture cannot authorize schema change")
    _require(claims.get("ccvR2Authorized") is False, "capture cannot authorize CCV-R2")


def validate_manifest_consistency(manifest: dict[str, Any], *, finalized: bool) -> None:
    runs = manifest.get("runs")
    _require(isinstance(runs, list) and runs, "manifest.runs must be a non-empty list")
    expected = manifest.get("expectedRunCount")
    _require(expected == len(runs), f"expectedRunCount {expected} does not match runs {len(runs)}")
    expected_by_round = {"round-1": 10, "round-2": 25, "round-3": 15, "all-rounds": 50}
    round_id = manifest.get("roundId")
    _require(expected == expected_by_round.get(round_id), f"{round_id}: expectedRunCount must be {expected_by_round.get(round_id)}")

    run_ids = [run.get("runId") for run in runs]
    output_paths = [run.get("output", {}).get("logicalPath") for run in runs]
    _require(len(set(run_ids)) == len(run_ids), "manifest runId values must be unique")
    _require(len(set(output_paths)) == len(output_paths), "manifest output logicalPath values must be unique")
    if not finalized:
        _require(manifest.get("status") == PENDING_STATUS, "pending manifest has an invalid status")
        return

    status = manifest.get("status")
    _require(status in {FINAL_STATUS, PARTIAL_STATUS}, "finalized manifest has an invalid status")
    created_at = manifest.get("manifestCreatedAt")
    _require(isinstance(created_at, str) and created_at, "finalized manifestCreatedAt is required")
    try:
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError as error:
        raise EvidenceError("finalized manifestCreatedAt must be an ISO-8601 timestamp") from error
    _require(parsed_created_at.tzinfo is not None, "finalized manifestCreatedAt must include a timezone")
    historical_capture = round_id == "all-rounds" and (
        status == PARTIAL_STATUS
        or "historicalScripts" in manifest
        or "captureReceipt" in manifest
        or "failureLedger" in manifest
    )
    for collection_name in ("hardenedSuccessorScripts", "models", "artifacts"):
        collection = manifest.get(collection_name)
        _require(isinstance(collection, list), f"manifest.{collection_name} must be a list")
        for index, record in enumerate(collection):
            label = f"{collection_name}[{index}]"
            recovered_historical = historical_capture and record.get("collectionState") == "RECOVERED"
            strict_record = collection_name == "hardenedSuccessorScripts" or not historical_capture or recovered_historical
            if strict_record:
                _require(isinstance(record.get("sizeBytes"), int) and record["sizeBytes"] > 0, f"{label}: positive sizeBytes is required")
                _require(_is_sha256(record.get("sha256")), f"{label}: lowercase SHA-256 is required")
            if collection_name in {"models", "artifacts"} and strict_record:
                _require(isinstance(record.get("filePath"), str) and record["filePath"], f"{label}: filePath is required")
            if collection_name == "models" and record.get("role") in CONDITIONING_TENSOR_SUFFIXES:
                architecture = record.get("architectureEvidence")
                _require(isinstance(architecture, dict), f"{label}: architectureEvidence is required")
                _require(architecture.get("modelSha256") == record["sha256"], f"{label}: architecture evidence is not tied to model SHA-256")
                _require(_is_sha256(architecture.get("headerSha256")), f"{label}: architecture header SHA-256 is required")
                _require(architecture.get("format") == "safetensors", f"{label}: architecture format must be safetensors")
                _require(
                    architecture.get("conditioningDimension") == record.get("conditioningDimension"),
                    f"{label}: architecture dimension does not match model record",
                )
                evidence_keys = architecture.get("evidenceTensorKeys")
                _require(
                    isinstance(evidence_keys, list)
                    and evidence_keys
                    and len(set(evidence_keys)) == len(evidence_keys)
                    and all(isinstance(key, str) and key for key in evidence_keys),
                    f"{label}: architecture evidence tensor keys are required",
                )
    for run in runs:
        run_id = run.get("runId", "unknown-run")
        seed = run.get("parameters", {}).get("seed")
        if historical_capture and status == PARTIAL_STATUS and run.get("runState") != "CAPTURED":
            _require(seed is None or (type(seed) is int and seed >= 0), f"{run_id}: seed must be pending or exact")
            continue
        _require(type(seed) is int and seed >= 0, f"{run_id}: exact non-negative seed is required")
        _require(run.get("runState") == "CAPTURED", f"{run_id}: runState must be CAPTURED")
        output = run.get("output", {})
        _require(isinstance(output.get("sizeBytes"), int) and output["sizeBytes"] > 0, f"{run_id}: positive output sizeBytes is required")
        _require(_is_sha256(output.get("sha256")), f"{run_id}: lowercase output SHA-256 is required")
    if historical_capture:
        _validate_historical_capture_manifest(manifest)


def build_manifest(
    config: dict[str, Any],
    runs: list[dict[str, Any]],
    *,
    finalized: bool,
    runner_script: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    models = [dict(model) for model in config["models"]]
    artifacts = [dict(artifact) for artifact in config.get("artifacts", [])]
    if finalized:
        validate_model_compatibility(models)
        for index, model in enumerate(models):
            size, digest, architecture = verify_model_record(model, f"models[{index}]/{model['role']}")
            model["sizeBytes"] = size
            model["sha256"] = digest
            if architecture is not None:
                model["architectureEvidence"] = architecture
        for index, artifact in enumerate(artifacts):
            size, digest = verify_file_record(artifact, f"artifacts[{index}]/{artifact.get('role', 'artifact')}")
            artifact["sizeBytes"] = size
            artifact["sha256"] = digest
        _require(output_root is not None and output_root.is_dir(), "--output-root must be an existing directory")
        for run in runs:
            seed = run["parameters"].get("seed")
            _require(type(seed) is int and seed >= 0, f"{run['runId']}: exact non-negative seed is required")
            relative = Path(run["output"]["logicalPath"])
            _require(not relative.is_absolute() and ".." not in relative.parts, f"{run['runId']}: unsafe output path")
            output = output_root / relative
            _require(output.is_file(), f"{run['runId']}: missing output {relative}")
            size = output.stat().st_size
            _require(size > 0, f"{run['runId']}: zero-byte output rejected")
            run["output"]["sizeBytes"] = size
            run["output"]["sha256"] = sha256_file(output)
            run["runState"] = "CAPTURED"
    else:
        validate_model_compatibility(models)

    historical_scripts: list[dict[str, Any]] = []
    manifest = {
        "$schema": "./experiment-manifest.schema.json",
        "manifestVersion": "1.0",
        "experimentId": config["experimentId"],
        "roundId": config["roundId"],
        "status": FINAL_STATUS if finalized else PENDING_STATUS,
        "rightsLabels": list(RIGHTS_LABELS),
        "historicalExecutionDate": "2026-08-14",
        "manifestCreatedAt": datetime.now(timezone.utc).isoformat() if finalized else None,
        "historicalScriptBytesRecovered": historical_script_bytes_recovered(historical_scripts),
        "historicalScripts": historical_scripts,
        "hardenedSuccessorScripts": [
            {
                "role": "hardened_successor_script",
                "logicalName": script.name,
                "sizeBytes": script.stat().st_size,
                "sha256": sha256_file(script),
            }
            for script in (runner_script, Path(__file__).resolve())
        ],
        "environment": config.get("environment", {}),
        "models": models,
        "artifacts": artifacts,
        "expectedRunCount": len(runs),
        "runs": runs,
        "claims": {
            "validationAccepted": False,
            "independentReproductionPossible": False,
            "schemaChangeAuthorized": False,
        },
    }
    validate_manifest_consistency(manifest, finalized=finalized)
    return manifest


def run_cli(expected_round: str, default_config: Path) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"Validate or finalize {expected_round} CCV-R1 evidence. "
            "EXPERIMENT EVIDENCE; SYNTHETIC_TEST_ONLY; NOT FOR PRODUCTION."
        )
    )
    parser.add_argument("--config", type=Path, default=default_config, help="JSON run configuration")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--validate-only", action="store_true", help="validate configuration without GPU or evidence files")
    action.add_argument("--write-pending-manifest", action="store_true", help="write a manifest with explicit pending fields")
    action.add_argument("--finalize-manifest", action="store_true", help="fail closed unless every required file, seed and digest is present")
    parser.add_argument("--manifest-out", type=Path, help="manifest destination for write/finalize actions")
    parser.add_argument("--output-root", type=Path, help="external output root used only for finalization")
    args = parser.parse_args()

    config = load_json(args.config)
    runs = validate_config(config, expected_round)
    validate_model_compatibility(config["models"])
    if args.validate_only:
        print(f"{expected_round}: configuration valid; planned runs={len(runs)}; evidence remains pending")
        return 0

    _require(args.manifest_out is not None, "--manifest-out is required")
    manifest = build_manifest(
        config,
        runs,
        finalized=args.finalize_manifest,
        runner_script=Path(__file__).resolve().parent / {
            "round-1": "character_consistency_test.py",
            "round-2": "ipadapter_face_test.py",
            "round-3": "ipadapter_pose_test.py",
        }[expected_round],
        output_root=args.output_root,
    )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.manifest_out} with {len(runs)} runs; status={manifest['status']}")
    return 0
