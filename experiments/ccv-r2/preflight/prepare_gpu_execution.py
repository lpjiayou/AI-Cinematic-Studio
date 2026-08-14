#!/usr/bin/env python3
"""Materialize the frozen CCV-R2 request set without starting GPU work.

This program performs read-only inspection of the host and immutable G2-R1 inputs.
Its only writes are to a new preparation directory.  It never imports torch, opens a
ComfyUI connection, queues a prompt, or loads a model.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ACS-CCV-R2-EXECUTION-READINESS-1"
PREPARATION_STATE = "GPU_READY_PREPARATION_COMPLETE_NO_GPU_EXECUTION"
G1_GOVERNANCE = "ACS-CCV-R2-G1-GPU-EXECUTION-PREPARATION"
G0_CLOSEOUT = "0376ee3c5b7a4c78735a04578a9a12fa1df6c2a2"
EXPECTED_COMFY_COMMIT = "feca51a8544511dd73d43602f387def0cc601a9d"
EXPECTED_IPADAPTER_COMMIT = "a0f451a5113cf9becb0847b92884cb10cbdec0ef"
EVIDENCE_ROOT = Path("/data/ccv-r1-2026-08-14-evidence-g2-r1")
ARCHIVE_ROOT = Path("/data/ccv-r1-2026-08-14-evidence-g2-r1-archive")
DEFAULT_OUTPUT_ROOT = Path("/data/ccv-r2-2026-08-15-preparation-g1")
MINIMUM_FREE_BYTES = 1_073_741_824

IMMUTABLE_CONTROLS = (
    (
        "g2-r1-manifest",
        EVIDENCE_ROOT / "manifests/historical-evidence-manifest.json",
        "e8dfa407ebe55b190150a6e41c68403f3acbbdffd87876bcbad698e4cfa96fbf",
    ),
    (
        "g2-r1-custody-inventory",
        EVIDENCE_ROOT / "inventory/custody-copy-inventory.json",
        "2e00b4250af0a8dee9bbc25c9fcb830f333e61e7f8241abefd3a6afc59e26d95",
    ),
)

PROMPT_SOURCES = {
    "A0_TEXT_BASELINE": (
        EVIDENCE_ROOT / "raw/outputs/r1-fixed__shotId-01_medium_front.png",
        "68b3e5232718c7e4ca0582db8e9430dd7fc2862d84e11c094655ed1a19110177",
    ),
    "A1_FACE_IDENTITY": (
        EVIDENCE_ROOT
        / "raw/outputs/r2b-face-crop__ipAdapterWeight-0p6__shotId-01_medium_front.png",
        "a6805e0907fcb51baf1a1beec6a4e042abbd87eff6ced1301ba35771c8cc06ec",
    ),
    "A2_FACE_OPENPOSE": (
        EVIDENCE_ROOT
        / "raw/outputs/r3-face-pose__controlNetStrength-0p8__shotId-01_medium_front.png",
        "a21cd1bcf99c2b7fed2fbe14f5490dc638bd329ef5184fcdd0be1ef7136d2567",
    ),
}


class PreparationError(RuntimeError):
    """Fail-closed preparation error."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path, *, progress_label: str | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    next_progress = 1_073_741_824
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if progress_label and size >= next_progress:
                print(f"HASH_PROGRESS {progress_label} {size}", flush=True)
                while next_progress <= size:
                    next_progress += 1_073_741_824
    return digest.hexdigest(), size


def verify_file(path: Path, expected_size: int | None, expected_sha: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PreparationError(f"{label}: missing file: {path}")
    actual_sha, actual_size = sha256_file(path, progress_label=label)
    if expected_size is not None and actual_size != expected_size:
        raise PreparationError(f"{label}: size mismatch: {actual_size} != {expected_size}")
    if actual_sha != expected_sha:
        raise PreparationError(f"{label}: sha256 mismatch: {actual_sha} != {expected_sha}")
    print(f"BYTE_VERIFY=PASS {label} {actual_size} {actual_sha}", flush=True)
    return {"label": label, "path": str(path), "sizeBytes": actual_size, "sha256": actual_sha}


def read_png_text(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise PreparationError(f"not a PNG: {path}")
        while True:
            raw_length = handle.read(4)
            if not raw_length:
                break
            if len(raw_length) != 4:
                raise PreparationError(f"truncated PNG chunk length: {path}")
            length = struct.unpack(">I", raw_length)[0]
            chunk_type = handle.read(4)
            data = handle.read(length)
            crc = handle.read(4)
            if len(chunk_type) != 4 or len(data) != length or len(crc) != 4:
                raise PreparationError(f"truncated PNG chunk: {path}")
            if chunk_type == b"tEXt":
                key, sep, value = data.partition(b"\x00")
                if sep:
                    result[key.decode("latin-1")] = value.decode("latin-1")
            elif chunk_type == b"zTXt":
                key, sep, rest = data.partition(b"\x00")
                if sep and len(rest) >= 2 and rest[0] == 0:
                    result[key.decode("latin-1")] = zlib.decompress(rest[1:]).decode("utf-8")
            elif chunk_type == b"iTXt":
                parts = data.split(b"\x00", 5)
                if len(parts) == 6:
                    key, compressed, method, _language, _translated, value = parts
                    if compressed == b"\x01" and method == b"\x00":
                        value = zlib.decompress(value)
                    result[key.decode("utf-8")] = value.decode("utf-8")
            if chunk_type == b"IEND":
                break
    return result


def extract_prompt(path: Path) -> dict[str, Any]:
    metadata = read_png_text(path)
    raw = metadata.get("prompt")
    if raw is None:
        raise PreparationError(f"PNG prompt metadata missing: {path}")
    try:
        prompt = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PreparationError(f"invalid prompt JSON in {path}: {exc}") from exc
    if not isinstance(prompt, dict) or not prompt:
        raise PreparationError(f"prompt graph must be a non-empty object: {path}")
    return prompt


def node_type(node: dict[str, Any]) -> str:
    return str(node.get("class_type", ""))


def matching_nodes(prompt: dict[str, Any], predicate: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(key, node) for key, node in prompt.items() if isinstance(node, dict) and predicate(node_type(node))]


def require_nodes(prompt: dict[str, Any], class_name: str, minimum: int = 1) -> list[tuple[str, dict[str, Any]]]:
    nodes = matching_nodes(prompt, lambda value: value == class_name)
    if len(nodes) < minimum:
        raise PreparationError(f"required node {class_name!r} count {len(nodes)} < {minimum}")
    return nodes


def linked_node_id(value: Any) -> str:
    if not isinstance(value, list) or len(value) < 1:
        raise PreparationError(f"expected ComfyUI node link, got {value!r}")
    return str(value[0])


def conditioning_text_node(
    prompt: dict[str, Any], link: Any, field: str
) -> dict[str, Any]:
    node_id = linked_node_id(link)
    output_index = int(link[1]) if isinstance(link, list) and len(link) > 1 else 0
    node = prompt.get(node_id)
    if not isinstance(node, dict):
        raise PreparationError(f"missing conditioning node: {node_id}")
    if node_type(node) == "CLIPTextEncode":
        return node
    if "controlnetapply" in node_type(node).lower():
        next_field = field
        if "positive" in node.get("inputs", {}) and "negative" in node.get("inputs", {}):
            next_field = "positive" if output_index == 0 else "negative"
        next_link = node.get("inputs", {}).get(next_field)
        if next_link is None:
            raise PreparationError(
                f"{node_type(node)} lacks {next_field} conditioning input"
            )
        return conditioning_text_node(prompt, next_link, field)
    raise PreparationError(
        f"unsupported {field} conditioning chain node: {node_type(node)}"
    )


def set_prompt_text(prompt: dict[str, Any], sampler: dict[str, Any], field: str, value: str) -> None:
    node = conditioning_text_node(prompt, sampler.get("inputs", {}).get(field), field)
    node.setdefault("inputs", {})["text"] = value


def classify_graph(prompt: dict[str, Any]) -> tuple[bool, bool]:
    class_types = [node_type(node).lower() for node in prompt.values() if isinstance(node, dict)]
    has_ipadapter = any("ipadapter" in value and "loader" not in value for value in class_types)
    has_controlnet = any("controlnetapply" in value for value in class_types)
    return has_ipadapter, has_controlnet


def assert_arm_semantics(prompt: dict[str, Any], arm_id: str) -> None:
    actual = classify_graph(prompt)
    expected = {
        "A0_TEXT_BASELINE": (False, False),
        "A1_FACE_IDENTITY": (True, False),
        "A2_FACE_OPENPOSE": (True, True),
    }[arm_id]
    if actual != expected:
        raise PreparationError(f"{arm_id}: graph semantics {actual} != expected {expected}")


def set_load_images(prompt: dict[str, Any], arm_id: str, pose_name: str | None) -> None:
    loads = matching_nodes(prompt, lambda value: value == "LoadImage")
    if arm_id == "A0_TEXT_BASELINE":
        if loads:
            raise PreparationError("A0 graph unexpectedly contains LoadImage")
        return
    if arm_id == "A1_FACE_IDENTITY":
        if len(loads) != 1:
            raise PreparationError(f"A1 requires exactly one LoadImage, found {len(loads)}")
        loads[0][1].setdefault("inputs", {})["image"] = "reference_face.png"
        return
    if len(loads) < 2 or pose_name is None:
        raise PreparationError(f"A2 requires reference and pose LoadImage nodes, found {len(loads)}")
    pose_nodes = []
    other_nodes = []
    for _, node in loads:
        current = str(node.get("inputs", {}).get("image", ""))
        if current.startswith("pose_"):
            pose_nodes.append(node)
        else:
            other_nodes.append(node)
    if len(pose_nodes) != 1 or len(other_nodes) != 1:
        raise PreparationError("A2 LoadImage roles are ambiguous; refusing to guess")
    pose_nodes[0].setdefault("inputs", {})["image"] = pose_name
    other_nodes[0].setdefault("inputs", {})["image"] = "reference_face.png"


def materialize_graph(source: dict[str, Any], run: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    prompt = copy.deepcopy(source)
    arm_id = run["armId"]
    params = manifest["parameters"]
    shot = next(item for item in manifest["shots"] if item["shotId"] == run["shotId"])
    positive = f"{params['positivePrompt']}, {shot['description']}"
    sampler_nodes = require_nodes(prompt, "KSampler", 1)
    if len(sampler_nodes) != 1:
        raise PreparationError(f"{arm_id}: expected exactly one KSampler, found {len(sampler_nodes)}")
    sampler = sampler_nodes[0][1]
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
    set_prompt_text(prompt, sampler, "positive", positive)
    set_prompt_text(prompt, sampler, "negative", params["negativePrompt"])
    for _, node in require_nodes(prompt, "CheckpointLoaderSimple", 1):
        node.setdefault("inputs", {})["ckpt_name"] = "sd_xl_base_1.0.safetensors"
    for _, node in matching_nodes(prompt, lambda value: value == "IPAdapterModelLoader"):
        inputs = node.setdefault("inputs", {})
        for key in ("ipadapter_file", "ipadapter_name"):
            if key in inputs:
                inputs[key] = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
    for _, node in matching_nodes(prompt, lambda value: value == "CLIPVisionLoader"):
        inputs = node.setdefault("inputs", {})
        for key in ("clip_name", "clip_vision"):
            if key in inputs:
                inputs[key] = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
    for _, node in matching_nodes(prompt, lambda value: value == "ControlNetLoader"):
        node.setdefault("inputs", {})["control_net_name"] = "controlnet-openpose-sdxl.safetensors"
    for _, node in require_nodes(prompt, "EmptyLatentImage", 1):
        node.setdefault("inputs", {}).update(
            {"width": params["width"], "height": params["height"], "batch_size": params["batchSize"]}
        )
    save_nodes = require_nodes(prompt, "SaveImage", 1)
    if len(save_nodes) != 1:
        raise PreparationError(f"{arm_id}: expected exactly one SaveImage, found {len(save_nodes)}")
    save_nodes[0][1].setdefault("inputs", {})["filename_prefix"] = (
        f"ccv-r2/{run['blindLabel']}__{run['runId']}"
    )
    ip_nodes = matching_nodes(
        prompt,
        lambda value: "ipadapter" in value.lower() and "loader" not in value.lower(),
    )
    for _, node in ip_nodes:
        inputs = node.setdefault("inputs", {})
        if "weight" in inputs:
            inputs["weight"] = params["ipAdapterWeight"]
        if "weight_type" in inputs:
            inputs["weight_type"] = params["ipAdapterWeightType"]
    control_nodes = matching_nodes(prompt, lambda value: "controlnetapply" in value.lower())
    for _, node in control_nodes:
        inputs = node.setdefault("inputs", {})
        if "strength" in inputs:
            inputs["strength"] = params["controlNetStrength"]
        if "start_percent" in inputs:
            inputs["start_percent"] = params["controlNetStartPercent"]
        if "end_percent" in inputs:
            inputs["end_percent"] = params["controlNetEndPercent"]
    pose_name = None
    if run.get("poseInputId"):
        input_row = next(item for item in manifest["inputs"] if item["inputId"] == run["poseInputId"])
        pose_name = Path(input_row["runtimePath"]).name
    set_load_images(prompt, arm_id, pose_name)
    assert_arm_semantics(prompt, arm_id)
    return prompt


def git_commit(path: Path) -> str:
    if not (path / ".git").exists():
        raise PreparationError(f"git checkout missing: {path}")
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def read_gpu_metadata() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,uuid",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PreparationError(f"read-only nvidia-smi preflight failed: {exc}") from exc
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise PreparationError(f"expected exactly one GPU, found {len(rows)}")
    parts = [part.strip() for part in rows[0].split(",")]
    if len(parts) != 4:
        raise PreparationError(f"unexpected nvidia-smi row: {rows[0]}")
    if parts[0] != "NVIDIA A100-PCIE-40GB":
        raise PreparationError(f"GPU class mismatch: {parts[0]}")
    return {"name": parts[0], "driver": parts[1], "memoryMiB": int(parts[2]), "uuid": parts[3]}


def validate_register(register: dict[str, Any]) -> None:
    runs = register.get("runs")
    if not isinstance(runs, list) or len(runs) != 45:
        raise PreparationError(f"run register must contain 45 rows, got {len(runs) if isinstance(runs, list) else None}")
    for field in ("runId", "blindLabel", "plannedOutputPath"):
        values = [row[field] for row in runs]
        if len(values) != len(set(values)):
            raise PreparationError(f"run register {field} values are not unique")
    expected = {
        (arm, shot, seed)
        for arm in register["design"]["arms"]
        for shot in register["design"]["shots"]
        for seed in register["design"]["seeds"]
    }
    actual = {(row["armId"], row["shotId"], row["seed"]) for row in runs}
    if actual != expected:
        raise PreparationError("run register is not the complete 3 x 5 x 3 matrix")
    for row in runs:
        should_pose = row["armId"] == "A2_FACE_OPENPOSE"
        if bool(row.get("poseInputId")) != should_pose:
            raise PreparationError(f"{row['runId']}: poseInputId violates arm contract")


def write_json(path: Path, value: Any) -> dict[str, Any]:
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": str(path), "sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def tree_inventory(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = exclude or set()
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        digest, size = sha256_file(path)
        rows.append({"path": relative, "sizeBytes": size, "sha256": digest})
    return rows


def ensure_output_boundary(output_root: Path) -> None:
    resolved = output_root.resolve()
    forbidden = [EVIDENCE_ROOT.resolve(), ARCHIVE_ROOT.resolve()]
    for root in forbidden:
        if resolved == root or root in resolved.parents or resolved in root.parents:
            raise PreparationError(f"preparation output overlaps immutable root: {resolved} / {root}")
    if output_root.exists():
        raise PreparationError(f"preparation output already exists: {output_root}")
    usage = shutil.disk_usage(output_root.parent if output_root.parent.exists() else Path("/data"))
    if usage.free < MINIMUM_FREE_BYTES:
        raise PreparationError(f"less than {MINIMUM_FREE_BYTES} free bytes available")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    try:
        ensure_output_boundary(output_root)
        manifest = json.loads((repo_root / "experiments/ccv-r2/experiment-manifest.template.json").read_text("utf-8"))
        register = json.loads((repo_root / "experiments/ccv-r2/run-register.template.json").read_text("utf-8"))
        validate_register(register)
        if manifest.get("claims", {}).get("gpuExecutionAuthorized") is not False:
            raise PreparationError("design manifest must not authorize GPU execution")
        verified_controls = [verify_file(path, None, sha, label) for label, path, sha in IMMUTABLE_CONTROLS]
        verified_assets = []
        for item in [*manifest["models"], *manifest["inputs"]]:
            verified_assets.append(
                verify_file(Path(item["runtimePath"]), item["sizeBytes"], item["sha256"], item.get("modelId") or item["inputId"])
            )
        source_graphs: dict[str, dict[str, Any]] = {}
        verified_sources = []
        for arm_id, (path, expected_sha) in PROMPT_SOURCES.items():
            verified_sources.append(verify_file(path, None, expected_sha, f"prompt-source-{arm_id}"))
            graph = extract_prompt(path)
            assert_arm_semantics(graph, arm_id)
            source_graphs[arm_id] = graph
        comfy_commit = git_commit(Path("/data/coding/apps/ComfyUI"))
        ipadapter_commit = git_commit(Path("/data/coding/apps/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus"))
        if comfy_commit != EXPECTED_COMFY_COMMIT:
            raise PreparationError(f"ComfyUI commit mismatch: {comfy_commit}")
        if ipadapter_commit != EXPECTED_IPADAPTER_COMMIT:
            raise PreparationError(f"IPAdapter node commit mismatch: {ipadapter_commit}")
        gpu = read_gpu_metadata()
        stage_parent = output_root.parent
        stage = Path(tempfile.mkdtemp(prefix=output_root.name + ".staging-", dir=stage_parent))
        try:
            base_graph_records = []
            first_by_arm = {arm: next(row for row in register["runs"] if row["armId"] == arm) for arm in source_graphs}
            for arm_id, source in source_graphs.items():
                base = materialize_graph(source, first_by_arm[arm_id], manifest)
                record = write_json(stage / "workflows" / f"{arm_id.lower()}.api.json", base)
                record["path"] = Path(record["path"]).relative_to(stage).as_posix()
                base_graph_records.append(record)
            payload_records = []
            for index, run in enumerate(register["runs"], start=1):
                graph = materialize_graph(source_graphs[run["armId"]], run, manifest)
                payload = {
                    "prompt": graph,
                    "extra_data": {
                        "extra_pnginfo": {
                            "ccvR2": {
                                "runId": run["runId"],
                                "blindLabel": run["blindLabel"],
                                "armId": run["armId"],
                                "shotId": run["shotId"],
                                "seed": run["seed"],
                                "protocolVersion": manifest["protocolVersion"],
                            }
                        }
                    },
                }
                record = write_json(stage / "requests" / f"{run['blindLabel']}__{run['runId']}.json", payload)
                record["path"] = Path(record["path"]).relative_to(stage).as_posix()
                record.update({key: run[key] for key in ("runId", "blindLabel", "armId", "shotId", "seed", "plannedOutputPath")})
                payload_records.append(record)
                print(f"MATERIALIZE {index}/45 {run['runId']}", flush=True)
            receipt = {
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": manifest["experimentId"],
                "protocolVersion": manifest["protocolVersion"],
                "state": PREPARATION_STATE,
                "governanceCheckpoint": G1_GOVERNANCE,
                "g0CloseoutCommit": G0_CLOSEOUT,
                "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "host": {"hostname": socket.gethostname(), "python": sys.version.split()[0], "gpu": gpu},
                "software": {"comfyUiCommit": comfy_commit, "ipAdapterNodeCommit": ipadapter_commit},
                "immutableControls": verified_controls,
                "verifiedAssets": verified_assets,
                "promptSources": verified_sources,
                "baseWorkflows": base_graph_records,
                "requests": payload_records,
                "counts": {"arms": 3, "shots": 5, "seeds": 3, "runs": len(payload_records)},
                "provenanceLimitations": [
                    "CLIP Vision exact local packaging source is not proven",
                    "OpenPose exact converted local byte source is not proven",
                    "reference_face.png historical crop lineage is ambiguous; bytes are fixed for this synthetic test",
                ],
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
            write_json(stage / "execution-readiness.json", receipt)
            inventory = tree_inventory(stage, exclude={"preparation-inventory.json", "preparation-inventory.sha256"})
            inventory_record = write_json(stage / "preparation-inventory.json", {"entries": inventory})
            (stage / "preparation-inventory.sha256").write_text(
                f"{inventory_record['sha256']}  preparation-inventory.json\n", encoding="utf-8"
            )
            os.replace(stage, output_root)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        print("CCV_R2_G1_PREPARATION=PASS")
        print(f"PREPARATION_ROOT={output_root}")
        print("REQUEST_COUNT=45")
        print("GPU_EXECUTION_STARTED=false")
        print("COMFYUI_QUEUE_TOUCHED=false")
        return 0
    except (OSError, KeyError, ValueError, PreparationError, subprocess.SubprocessError) as exc:
        print("CCV_R2_G1_PREPARATION=FAIL")
        print(f"ERROR={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
