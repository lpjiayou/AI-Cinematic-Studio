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

    _require(manifest.get("status") == FINAL_STATUS, "finalized manifest has an invalid status")
    created_at = manifest.get("manifestCreatedAt")
    _require(isinstance(created_at, str) and created_at, "finalized manifestCreatedAt is required")
    try:
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError as error:
        raise EvidenceError("finalized manifestCreatedAt must be an ISO-8601 timestamp") from error
    _require(parsed_created_at.tzinfo is not None, "finalized manifestCreatedAt must include a timezone")
    for collection_name in ("hardenedSuccessorScripts", "models", "artifacts"):
        collection = manifest.get(collection_name)
        _require(isinstance(collection, list), f"manifest.{collection_name} must be a list")
        for index, record in enumerate(collection):
            label = f"{collection_name}[{index}]"
            _require(isinstance(record.get("sizeBytes"), int) and record["sizeBytes"] > 0, f"{label}: positive sizeBytes is required")
            _require(_is_sha256(record.get("sha256")), f"{label}: lowercase SHA-256 is required")
            if collection_name in {"models", "artifacts"}:
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
        _require(isinstance(seed, int) and seed >= 0, f"{run_id}: exact non-negative seed is required")
        _require(run.get("runState") == "CAPTURED", f"{run_id}: runState must be CAPTURED")
        output = run.get("output", {})
        _require(isinstance(output.get("sizeBytes"), int) and output["sizeBytes"] > 0, f"{run_id}: positive output sizeBytes is required")
        _require(_is_sha256(output.get("sha256")), f"{run_id}: lowercase output SHA-256 is required")


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
            _require(isinstance(seed, int) and seed >= 0, f"{run['runId']}: exact non-negative seed is required")
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

    manifest = {
        "$schema": "./experiment-manifest.schema.json",
        "manifestVersion": "1.0",
        "experimentId": config["experimentId"],
        "roundId": config["roundId"],
        "status": FINAL_STATUS if finalized else PENDING_STATUS,
        "rightsLabels": list(RIGHTS_LABELS),
        "historicalExecutionDate": "2026-08-14",
        "manifestCreatedAt": datetime.now(timezone.utc).isoformat() if finalized else None,
        "historicalScriptBytesRecovered": False,
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
