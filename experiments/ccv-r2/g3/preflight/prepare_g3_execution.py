#!/usr/bin/env python3
"""Prepare the frozen CCV-R2 G3 request set without touching GPU execution."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import secrets
import shutil
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ACS-CCV-R2-G3-READINESS-1"
PROTOCOL_VERSION = "g3-rcr-v1"
PREPARATION_STATE = "G3_GPU_READY_PREPARATION_COMPLETE_NO_GPU_EXECUTION"
GOVERNANCE = "ACS-CCV-R2-G3-G1-NO-GPU-PREPARATION"
G0_COMMIT = "41faaadf4c959944da3afd8c1d52b3e2429da68c"
DEFAULT_G2_PREPARATION = Path("/data/ccv-r2-2026-08-15-preparation-g1")
DEFAULT_G2_RESULTS = Path("/data/ccv-r2-2026-08-15-results-g2")
DEFAULT_M1_REFERENCE = Path(
    "/data/coding/apps/ComfyUI/input/ccv-r2-g3-reference-face-collar-free.png"
)
DEFAULT_EXTERNAL_REFERENCE = Path("/data/ccv-r5-clean-reference/reference_face_v2.png")
DEFAULT_OUTPUT_ROOT = Path("/data/ccv-r2-2026-08-15-preparation-g3-g1")
EXPECTED_G2_RECEIPT_SHA = "995035ee1169b7335d7c0707ea6adc31e36cd342c2a281f475fd66b7f4952c05"
EXPECTED_G2_PREPARATION_INVENTORY_SHA = (
    "95e1257003b28aced87719d31b4caba2eabc5a18995d2d9b98dbfb20157db40a"
)
EXPECTED_G2_RESULT_INVENTORY_SHA = (
    "704451a5133c00b29e73eeb756e738646a812ab71ce7f77d0a17ccc20f7705f9"
)
MINIMUM_FREE_BYTES = 1_073_741_824


class PreparationError(RuntimeError):
    """Fail-closed G3 preparation error."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_file(
    path: Path, expected_sha: str, label: str, expected_size: int | None = None
) -> dict[str, Any]:
    if not path.is_file():
        raise PreparationError(f"{label}: missing file: {path}")
    actual_sha, actual_size = sha256_file(path)
    if expected_size is not None and actual_size != expected_size:
        raise PreparationError(
            f"{label}: size mismatch: {actual_size} != {expected_size}"
        )
    if actual_sha != expected_sha:
        raise PreparationError(f"{label}: sha256 mismatch: {actual_sha} != {expected_sha}")
    print(f"BYTE_VERIFY=PASS {label} {actual_size} {actual_sha}", flush=True)
    return {
        "label": label,
        "path": str(path),
        "sizeBytes": actual_size,
        "sha256": actual_sha,
    }


def write_json(path: Path, value: Any) -> dict[str, Any]:
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": str(path),
        "sizeBytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def pixel_sha(image: Any) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def derive_crop_reference(
    source_path: Path,
    output_path: Path,
    receipt_path: Path,
    expected_source_sha: str,
    crop_box: list[int],
    output_dimensions: list[int],
    collar_excluded_attestation: bool,
) -> None:
    """Create a byte-bound crop only from an explicit operator-selected rectangle."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise PreparationError("Pillow is required for crop derivation") from exc
    if collar_excluded_attestation is not True:
        raise PreparationError("--attest-collar-excluded is required for crop derivation")
    if output_path.exists() or receipt_path.exists():
        raise PreparationError("crop derivation refuses to overwrite output or receipt")
    verify_file(source_path, expected_source_sha, "g3-m1-source")
    if len(crop_box) != 4 or len(output_dimensions) != 2:
        raise PreparationError("crop box/output dimensions have invalid arity")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in crop_box):
        raise PreparationError("crop box must contain integers")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in output_dimensions
    ):
        raise PreparationError("output dimensions must contain positive integers")
    try:
        with Image.open(source_path) as source_image:
            source = source_image.convert("RGB")
    except OSError as exc:
        raise PreparationError(f"crop source decode failed: {exc}") from exc
    left, top, right, bottom = crop_box
    if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
        raise PreparationError("crop box is outside the source image")
    output = source.crop(tuple(crop_box)).resize(
        tuple(output_dimensions), Image.Resampling.LANCZOS
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, format="PNG")
    output_sha, _ = sha256_file(output_path)
    receipt = {
        "schemaVersion": "ACS-CCV-R2-G3-CROP-DERIVATION-1",
        "method": "RECTANGULAR_CROP_AND_RESIZE_ONLY",
        "sourcePath": str(source_path.resolve()),
        "sourceSha256": expected_source_sha,
        "sourceDimensions": list(source.size),
        "cropBoxPixels": crop_box,
        "outputPath": str(output_path.resolve()),
        "outputDimensions": output_dimensions,
        "resizeAlgorithm": "LANCZOS",
        "outputSha256": output_sha,
        "outputPixelSha256": pixel_sha(output),
        "collarExcludedAttestation": True,
        "operatorAttestation": True,
    }
    try:
        write_json(receipt_path, receipt)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    print(f"CROP_DERIVATION=PASS {crop_box} {output_sha}", flush=True)


def verify_crop_derivation(
    source_path: Path, output_path: Path, receipt_path: Path, expected_source_sha: str
) -> dict[str, Any]:
    try:
        from PIL import Image, __version__ as pillow_version
    except ImportError as exc:
        raise PreparationError("Pillow is required for exact crop verification") from exc

    if not receipt_path.is_file():
        raise PreparationError(f"crop derivation receipt missing: {receipt_path}")
    try:
        receipt = json.loads(receipt_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreparationError(f"invalid crop receipt: {exc}") from exc
    required = {
        "schemaVersion",
        "method",
        "sourcePath",
        "sourceSha256",
        "sourceDimensions",
        "cropBoxPixels",
        "outputPath",
        "outputDimensions",
        "resizeAlgorithm",
        "outputSha256",
        "outputPixelSha256",
        "collarExcludedAttestation",
        "operatorAttestation",
    }
    if set(receipt) != required:
        raise PreparationError(
            f"crop receipt keys mismatch: {sorted(set(receipt) ^ required)}"
        )
    if receipt["schemaVersion"] != "ACS-CCV-R2-G3-CROP-DERIVATION-1":
        raise PreparationError("crop receipt schemaVersion mismatch")
    if receipt["method"] != "RECTANGULAR_CROP_AND_RESIZE_ONLY":
        raise PreparationError("crop receipt method is not frozen")
    if receipt["resizeAlgorithm"] != "LANCZOS":
        raise PreparationError("crop resize algorithm must be LANCZOS")
    if receipt["collarExcludedAttestation"] is not True:
        raise PreparationError("collar-excluded attestation is required")
    if receipt["operatorAttestation"] is not True:
        raise PreparationError("operator derivation attestation is required")
    if Path(receipt["sourcePath"]).resolve() != source_path.resolve():
        raise PreparationError("crop source path mismatch")
    if Path(receipt["outputPath"]).resolve() != output_path.resolve():
        raise PreparationError("crop output path mismatch")

    source_control = verify_file(source_path, expected_source_sha, "g3-m1-source")
    output_control = verify_file(output_path, receipt["outputSha256"], "g3-m1-reference")
    if receipt["sourceSha256"] != expected_source_sha:
        raise PreparationError("crop receipt source digest mismatch")

    try:
        with Image.open(source_path) as source_image:
            source = source_image.convert("RGB")
        with Image.open(output_path) as output_image:
            output = output_image.convert("RGB")
    except OSError as exc:
        raise PreparationError(f"crop image decode failed: {exc}") from exc
    if list(source.size) != receipt["sourceDimensions"]:
        raise PreparationError("crop source dimensions mismatch")
    if list(output.size) != receipt["outputDimensions"]:
        raise PreparationError("crop output dimensions mismatch")
    box = receipt["cropBoxPixels"]
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in box)
    ):
        raise PreparationError("cropBoxPixels must contain four integers")
    left, top, right, bottom = box
    if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
        raise PreparationError("cropBoxPixels is outside the source image")
    expected = source.crop(tuple(box)).resize(output.size, Image.Resampling.LANCZOS)
    actual_pixel_sha = pixel_sha(output)
    if actual_pixel_sha != receipt["outputPixelSha256"]:
        raise PreparationError("crop output pixel digest mismatch")
    if pixel_sha(expected) != actual_pixel_sha:
        raise PreparationError("output pixels are not the declared crop-and-resize")
    return {
        **receipt,
        "verifiedPillowVersion": pillow_version,
        "sourceSizeBytes": source_control["sizeBytes"],
        "outputSizeBytes": output_control["sizeBytes"],
    }


def validate_protocol(protocol: dict[str, Any]) -> None:
    if protocol.get("schemaVersion") != "ACS-CCV-R2-G3-PROTOCOL-1":
        raise PreparationError("protocol schemaVersion mismatch")
    if protocol.get("protocolVersion") != PROTOCOL_VERSION:
        raise PreparationError("protocolVersion mismatch")
    if protocol.get("state") != "G0_FROZEN_NO_GPU":
        raise PreparationError("protocol state mismatch")
    if protocol.get("expectedUniqueRequestCount") != 51:
        raise PreparationError("protocol must freeze 51 unique requests")
    claims = protocol.get("claims", {})
    prohibited = (
        "gpuExecutionAuthorized",
        "gpuExecutionStarted",
        "comfyUiQueueTouched",
        "modelLoaded",
        "imageGenerated",
        "validationAccepted",
        "productionReady",
        "productCodeChanged",
        "schemaChanged",
    )
    if any(claims.get(key) is not False for key in prohibited):
        raise PreparationError("protocol contains a prohibited positive claim")


def build_run_plan(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    shots = protocol["shots"]
    seeds = protocol["seeds"]
    references = protocol["references"]
    runs: list[dict[str, Any]] = []
    for reference in references:
        arm_id = reference["armId"]
        arm_slug = arm_id.lower()
        for seed in seeds:
            for shot in shots:
                runs.append(
                    {
                        "technicalId": f"{arm_slug}__seed-{seed}__shot-{shot}",
                        "armId": arm_id,
                        "shotId": shot,
                        "seed": seed,
                        "ipAdapterWeight": protocol["fixedParameters"]["ipAdapterWeight"],
                        "controlNetStrength": protocol["fixedParameters"]["controlNetStrength"],
                        "referencePath": reference["runtimePath"],
                        "phase": "MAIN",
                        "plannedOutputPath": f"outputs/{arm_slug}/seed-{seed}/{shot}.png",
                    }
                )
    sweep = protocol["backTurningSweep"]
    reference = next(item for item in references if item["armId"] == sweep["armId"])
    for weight in sweep["ipAdapterWeights"]:
        if weight == sweep["reuseMainRowsAtWeight"]:
            continue
        weight_slug = str(weight).replace(".", "p")
        for seed in seeds:
            runs.append(
                {
                    "technicalId": (
                        f"g3_backturning_sweep__ip-{weight_slug}__seed-{seed}"
                        f"__shot-{sweep['shotId']}"
                    ),
                    "armId": sweep["armId"],
                    "shotId": sweep["shotId"],
                    "seed": seed,
                    "ipAdapterWeight": weight,
                    "controlNetStrength": sweep["controlNetStrength"],
                    "referencePath": reference["runtimePath"],
                    "phase": "BACK_TURNING_SWEEP",
                    "plannedOutputPath": (
                        f"outputs/back_turning_sweep/ip-{weight_slug}/seed-{seed}/"
                        f"{sweep['shotId']}.png"
                    ),
                }
            )
    if len(runs) != 51:
        raise PreparationError(f"run plan must contain 51 rows, got {len(runs)}")
    for field in ("technicalId", "plannedOutputPath"):
        values = [row[field] for row in runs]
        if len(values) != len(set(values)):
            raise PreparationError(f"run plan {field} values are not unique")
    return runs


def node_type(node: dict[str, Any]) -> str:
    return str(node.get("class_type", ""))


def matching_nodes(prompt: dict[str, Any], predicate: Any) -> list[dict[str, Any]]:
    return [
        node
        for node in prompt.values()
        if isinstance(node, dict) and predicate(node_type(node))
    ]


def require_one(prompt: dict[str, Any], class_name: str) -> dict[str, Any]:
    nodes = matching_nodes(prompt, lambda value: value == class_name)
    if len(nodes) != 1:
        raise PreparationError(
            f"expected one {class_name}, found {len(nodes)}"
        )
    return nodes[0]


def linked_text_node(prompt: dict[str, Any], link: Any, field: str) -> dict[str, Any]:
    if not isinstance(link, list) or not link:
        raise PreparationError(f"invalid {field} conditioning link")
    node = prompt.get(str(link[0]))
    if not isinstance(node, dict):
        raise PreparationError(f"missing {field} conditioning node")
    if node_type(node) == "CLIPTextEncode":
        return node
    if "controlnetapply" in node_type(node).lower():
        next_link = node.get("inputs", {}).get(field)
        if next_link is None:
            output_index = int(link[1]) if len(link) > 1 else 0
            next_link = node.get("inputs", {}).get(
                "positive" if output_index == 0 else "negative"
            )
        return linked_text_node(prompt, next_link, field)
    raise PreparationError(f"unsupported {field} conditioning chain")


def materialize_graph(
    source: dict[str, Any],
    run: dict[str, Any],
    g2_manifest: dict[str, Any],
    blind_label: str,
    run_id: str,
) -> dict[str, Any]:
    prompt = copy.deepcopy(source)
    sampler = require_one(prompt, "KSampler")
    params = g2_manifest["parameters"]
    shot = next(item for item in g2_manifest["shots"] if item["shotId"] == run["shotId"])
    sinputs = sampler.setdefault("inputs", {})
    sinputs.update(
        {
            "seed": run["seed"],
            "steps": params["steps"],
            "cfg": params["cfg"],
            "sampler_name": params["sampler"],
            "scheduler": params["scheduler"],
        }
    )
    positive = linked_text_node(prompt, sinputs.get("positive"), "positive")
    negative = linked_text_node(prompt, sinputs.get("negative"), "negative")
    positive.setdefault("inputs", {})["text"] = (
        f"{params['positivePrompt']}, {shot['description']}"
    )
    negative.setdefault("inputs", {})["text"] = params["negativePrompt"]

    load_nodes = matching_nodes(prompt, lambda value: value == "LoadImage")
    pose_nodes = [
        node
        for node in load_nodes
        if str(node.get("inputs", {}).get("image", "")).startswith("pose_")
    ]
    reference_nodes = [node for node in load_nodes if node not in pose_nodes]
    if len(pose_nodes) != 1 or len(reference_nodes) != 1:
        raise PreparationError("A2 workflow LoadImage roles are ambiguous")
    pose = next(item for item in g2_manifest["shots"] if item["shotId"] == run["shotId"])
    pose_input = next(
        item for item in g2_manifest["inputs"] if item["inputId"] == pose["poseInputId"]
    )
    pose_nodes[0].setdefault("inputs", {})["image"] = Path(
        pose_input["runtimePath"]
    ).name
    reference_nodes[0].setdefault("inputs", {})["image"] = Path(
        run["referencePath"]
    ).name

    ip_nodes = matching_nodes(
        prompt,
        lambda value: "ipadapter" in value.lower() and "loader" not in value.lower(),
    )
    control_nodes = matching_nodes(
        prompt, lambda value: "controlnetapply" in value.lower()
    )
    if not ip_nodes or not control_nodes:
        raise PreparationError("base workflow lacks IP-Adapter or ControlNet")
    for node in ip_nodes:
        if "weight" in node.setdefault("inputs", {}):
            node["inputs"]["weight"] = run["ipAdapterWeight"]
    for node in control_nodes:
        if "strength" in node.setdefault("inputs", {}):
            node["inputs"]["strength"] = run["controlNetStrength"]
    save = require_one(prompt, "SaveImage")
    save.setdefault("inputs", {})["filename_prefix"] = f"ccv-r2-g3/{blind_label}__{run_id}"
    return prompt


def ensure_output_boundary(output_root: Path, protected: list[Path]) -> None:
    resolved = output_root.resolve()
    for path in protected:
        root = path.resolve()
        if resolved == root or root in resolved.parents or resolved in root.parents:
            raise PreparationError(f"G3 output overlaps protected root: {resolved} / {root}")
    if output_root.exists():
        raise PreparationError(f"G3 preparation output already exists: {output_root}")
    parent = output_root.parent if output_root.parent.exists() else Path("/data")
    if shutil.disk_usage(parent).free < MINIMUM_FREE_BYTES:
        raise PreparationError("insufficient free space for G3 preparation")


def tree_inventory(root: Path, excluded: set[str]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        digest, size = sha256_file(path)
        rows.append({"path": relative, "sizeBytes": size, "sha256": digest})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--g2-preparation-root", type=Path, default=DEFAULT_G2_PREPARATION)
    parser.add_argument("--g2-result-root", type=Path, default=DEFAULT_G2_RESULTS)
    parser.add_argument("--m1-reference", type=Path, default=DEFAULT_M1_REFERENCE)
    parser.add_argument("--crop-receipt", type=Path)
    parser.add_argument("--derive-crop-box", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--output-dimensions", type=int, nargs=2, default=[512, 512], metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--attest-collar-excluded", action="store_true")
    parser.add_argument("--external-reference", type=Path, default=DEFAULT_EXTERNAL_REFERENCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    g2_preparation = args.g2_preparation_root.resolve()
    g2_results = args.g2_result_root.resolve()
    output_root = args.output_root.resolve()
    crop_receipt = (
        args.crop_receipt.resolve()
        if args.crop_receipt
        else args.m1_reference.with_suffix(".derivation.json").resolve()
    )
    try:
        ensure_output_boundary(output_root, [g2_preparation, g2_results])
        protocol = json.loads(
            (repo_root / "experiments/ccv-r2/g3/protocol.template.json").read_text("utf-8")
        )
        g2_manifest = json.loads(
            (repo_root / "experiments/ccv-r2/experiment-manifest.template.json").read_text("utf-8")
        )
        validate_protocol(protocol)
        runs = build_run_plan(protocol)

        parent_controls = [
            verify_file(
                g2_preparation / "execution-readiness.json",
                EXPECTED_G2_RECEIPT_SHA,
                "g2-execution-readiness",
            ),
            verify_file(
                g2_preparation / "preparation-inventory.json",
                EXPECTED_G2_PREPARATION_INVENTORY_SHA,
                "g2-preparation-inventory",
            ),
            verify_file(
                g2_results / "result-inventory.json",
                EXPECTED_G2_RESULT_INVENTORY_SHA,
                "g2-result-inventory",
            ),
        ]
        g2_receipt = json.loads(
            (g2_preparation / "execution-readiness.json").read_text("utf-8")
        )
        if g2_receipt.get("counts", {}).get("runs") != 45:
            raise PreparationError("G2 readiness receipt does not bind 45 runs")
        verified_g2_assets = []
        for asset in g2_receipt.get("verifiedAssets", []):
            verified_g2_assets.append(
                verify_file(
                    Path(asset["path"]),
                    asset["sha256"],
                    f"g2-asset-{asset['label']}",
                    asset["sizeBytes"],
                )
            )
        if len(verified_g2_assets) < 11:
            raise PreparationError("G2 receipt contains fewer than 11 verified assets")

        m1_protocol = next(
            item
            for item in protocol["references"]
            if item["armId"] == "G3_M1_SAME_IDENTITY_COLLAR_FREE"
        )
        if args.derive_crop_box is not None:
            derive_crop_reference(
                Path(m1_protocol["sourcePath"]),
                args.m1_reference.resolve(),
                crop_receipt,
                m1_protocol["sourceSha256"],
                args.derive_crop_box,
                args.output_dimensions,
                args.attest_collar_excluded,
            )
        crop_derivation = verify_crop_derivation(
            Path(m1_protocol["sourcePath"]),
            args.m1_reference.resolve(),
            crop_receipt,
            m1_protocol["sourceSha256"],
        )
        references = []
        for item in protocol["references"]:
            path = (
                args.m1_reference.resolve()
                if item["armId"] == "G3_M1_SAME_IDENTITY_COLLAR_FREE"
                else args.external_reference.resolve()
                if item["armId"] == "G3_P0_EXTERNAL_REFERENCE_PROBE"
                else Path(item["runtimePath"])
            )
            expected_sha = (
                crop_derivation["outputSha256"]
                if item["armId"] == "G3_M1_SAME_IDENTITY_COLLAR_FREE"
                else item["sha256"]
            )
            control = verify_file(path, expected_sha, f"reference-{item['armId']}")
            control.update(
                {
                    "armId": item["armId"],
                    "role": item["role"],
                    "primaryAcceptanceEligible": item["primaryAcceptanceEligible"],
                }
            )
            references.append(control)
        reference_by_arm = {item["armId"]: item["path"] for item in references}
        for run in runs:
            run["referencePath"] = reference_by_arm[run["armId"]]

        base_path = g2_preparation / "workflows/a2_face_openpose.api.json"
        base_record = next(
            (
                item
                for item in g2_receipt.get("baseWorkflows", [])
                if item.get("path") == "workflows/a2_face_openpose.api.json"
            ),
            None,
        )
        if not base_record:
            raise PreparationError("G2 A2 base workflow record is missing")
        base_control = verify_file(
            base_path,
            base_record["sha256"],
            "g2-a2-base-workflow",
            base_record["sizeBytes"],
        )
        base_graph = json.loads(base_path.read_text("utf-8"))

        stage = Path(
            tempfile.mkdtemp(prefix=output_root.name + ".staging-", dir=output_root.parent)
        )
        try:
            labels = [f"G3B{index:03d}" for index in range(1, 52)]
            secrets.SystemRandom().shuffle(labels)
            technical_rows = []
            request_rows = []
            issued_run_ids: set[str] = set()
            for index, (run, blind_label) in enumerate(zip(runs, labels), start=1):
                while True:
                    run_id = f"G3R{secrets.token_hex(8).upper()}"
                    if run_id not in issued_run_ids:
                        issued_run_ids.add(run_id)
                        break
                graph = materialize_graph(base_graph, run, g2_manifest, blind_label, run_id)
                payload = {
                    "prompt": graph,
                    "extra_data": {
                        "extra_pnginfo": {
                            "ccvR2G3": {
                                "runId": run_id,
                                "blindLabel": blind_label,
                                "shotId": run["shotId"],
                                "seed": run["seed"],
                                "protocolVersion": PROTOCOL_VERSION,
                            }
                        }
                    },
                }
                record = write_json(
                    stage / "requests" / f"{blind_label}__{run_id}.json", payload
                )
                record["path"] = Path(record["path"]).relative_to(stage).as_posix()
                public_row = {
                    **record,
                    "runId": run_id,
                    "blindLabel": blind_label,
                    "shotId": run["shotId"],
                    "seed": run["seed"],
                    "phase": run["phase"],
                    "plannedOutputPath": run["plannedOutputPath"],
                }
                request_rows.append(public_row)
                technical_rows.append({**run, "runId": run_id, "blindLabel": blind_label})
                print(f"MATERIALIZE {index}/51 {run_id}", flush=True)

            technical_map = {
                "schemaVersion": "ACS-CCV-R2-G3-TECHNICAL-MAP-1",
                "state": "SEALED_BEFORE_GPU_DO_NOT_SEND_TO_REVIEWERS",
                "itemCount": 51,
                "items": technical_rows,
            }
            map_record = write_json(stage / "technical-map.sealed.json", technical_map)
            (stage / "technical-map.sealed.json.sha256").write_text(
                f"{map_record['sha256']}  technical-map.sealed.json\n", encoding="utf-8"
            )
            review_template = {
                "schemaVersion": "ACS-CCV-R2-G3-REVIEW-TEMPLATE-1",
                "state": "LOCKED_EMPTY_BEFORE_GPU",
                "reviewerCount": 3,
                "criteria": [
                    "identityContinuity",
                    "shotPoseAdherence",
                    "anatomyArtifactFreedom",
                    "referenceContaminationControl",
                ],
                "labels": sorted(labels),
                "entries": [],
            }
            review_record = write_json(stage / "review-score-lock.template.json", review_template)
            (stage / "review-score-lock.template.json.sha256").write_text(
                f"{review_record['sha256']}  review-score-lock.template.json\n",
                encoding="utf-8",
            )
            receipt = {
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": "acs-ccv-r2",
                "protocolVersion": PROTOCOL_VERSION,
                "state": PREPARATION_STATE,
                "governanceCheckpoint": GOVERNANCE,
                "g0Commit": G0_COMMIT,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "host": {"hostname": socket.gethostname(), "python": sys.version.split()[0]},
                "parentControls": parent_controls,
                "verifiedG2Assets": verified_g2_assets,
                "references": references,
                "cropDerivation": crop_derivation,
                "baseWorkflow": base_control,
                "requests": request_rows,
                "counts": {"main": 45, "additionalSweep": 6, "uniqueRequests": 51},
                "technicalMapLock": {
                    "path": "technical-map.sealed.json",
                    "sha256": map_record["sha256"],
                },
                "reviewTemplateLock": {
                    "path": "review-score-lock.template.json",
                    "sha256": review_record["sha256"],
                },
                "claims": {
                    "gpuExecutionAuthorized": False,
                    "gpuExecutionStarted": False,
                    "comfyUiQueueTouched": False,
                    "modelLoaded": False,
                    "imageGenerated": False,
                    "validationAccepted": False,
                    "productionReady": False,
                },
            }
            write_json(stage / "g3-readiness.json", receipt)
            inventory = tree_inventory(
                stage,
                {"preparation-inventory.json", "preparation-inventory.sha256"},
            )
            inventory_record = write_json(
                stage / "preparation-inventory.json", {"entries": inventory}
            )
            (stage / "preparation-inventory.sha256").write_text(
                f"{inventory_record['sha256']}  preparation-inventory.json\n",
                encoding="utf-8",
            )
            os.replace(stage, output_root)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        readiness_sha, _ = sha256_file(output_root / "g3-readiness.json")
        print("CCV_R2_G3_G1_PREPARATION=PASS")
        print(f"PREPARATION_ROOT={output_root}")
        print(f"READINESS_SHA256={readiness_sha}")
        print("REQUEST_COUNT=51")
        print("GPU_EXECUTION_STARTED=false")
        print("COMFYUI_QUEUE_TOUCHED=false")
        return 0
    except (OSError, KeyError, ValueError, PreparationError) as exc:
        print("CCV_R2_G3_G1_PREPARATION=FAIL")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
