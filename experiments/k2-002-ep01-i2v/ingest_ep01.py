#!/usr/bin/env python3
"""Validate, stage, execute, and record the K2-002 EP01 I2V experiment.

Despite the filename, "ingest" here means only copying digest-pinned candidate
PNG bytes into the local ComfyUI input directory.  This program never imports
Creator/V5 services, never writes a canonical database, and never creates an
AssetVersion, admission, master, export, or publication fact.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from urllib import error, parse, request
import zipfile


EXPERIMENT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXPERIMENT_ROOT.parents[1]
WORKFLOW_PATH = EXPERIMENT_ROOT / "workflow.json"
SHOTS_PATH = EXPERIMENT_ROOT / "shots.json"

AUTHORITY_STATE = "TECHNICAL_EVIDENCE_ONLY"
EXPERIMENT_ID = "K2-002-EP01-I2V-49F-704X1280-V1"
PACKAGE_SHA256 = "532765d91b56692e611cabb9fcbd3d8ecc916f169f5c4e2b3b9e82a56bbe99c6"
PACKAGE_ROOT = "final-assets-v1.2"

MODEL_FILES = (
    (
        "UNET",
        "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
        "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e",
    ),
    (
        "TEXT_ENCODER",
        "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68",
    ),
    (
        "VAE",
        "vae/wan2.2_vae.safetensors",
        "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156",
    ),
)

EXPECTED_CLASS_TYPES = {
    "1": "UNETLoader",
    "2": "CLIPLoader",
    "3": "VAELoader",
    "4": "ModelSamplingSD3",
    "5": "CLIPTextEncode",
    "6": "CLIPTextEncode",
    "7": "Wan22ImageToVideoLatent",
    "8": "KSampler",
    "9": "VAEDecode",
    "10": "CreateVideo",
    "11": "SaveVideo",
    "12": "LoadImage",
}

SAFE_SHOT_ID = re.compile(r"EP01_SH(?:0[1-9]|1[0-2])\Z")
SAFE_OUTPUT_PREFIX = re.compile(r"EP01_SH(?:0[1-9]|1[0-2])-technical-evidence\Z")


class ExperimentError(RuntimeError):
    """Fail-closed experiment preparation or execution error."""


class _NoRedirectHandler(request.HTTPRedirectHandler):
    """Keep the loopback-only execution transport on its verified origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


HTTP_OPENER = request.build_opener(_NoRedirectHandler())


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ExperimentError(f"{label} must be a JSON object")
    return value


def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ExperimentError(f"{field} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ExperimentError(f"{field} is unsafe")
    return value


def _png_dimensions(payload: bytes, field: str) -> tuple[int, int]:
    if (
        len(payload) < 24
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
    ):
        raise ExperimentError(f"{field} is not a PNG")
    width, height = struct.unpack(">II", payload[16:24])
    if width < 1 or height < 1:
        raise ExperimentError(f"{field} has invalid dimensions")
    return width, height


class AssetPackage(AbstractContextManager["AssetPackage"]):
    """Read exact asset members without extracting an archive."""

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()
        self._zip: zipfile.ZipFile | None = None
        self._root: Path | None = None

        if self.source.is_file():
            if self.source.suffix.lower() != ".zip":
                raise ExperimentError("asset package file must be a ZIP archive")
            if _file_sha256(self.source) != PACKAGE_SHA256:
                raise ExperimentError("asset package SHA-256 does not match v1.2")
            try:
                self._zip = zipfile.ZipFile(self.source, "r")
                corrupt = self._zip.testzip()
            except (OSError, zipfile.BadZipFile) as exc:
                raise ExperimentError("asset package ZIP is invalid") from exc
            if corrupt is not None:
                raise ExperimentError("asset package ZIP contains corrupt data")
        elif self.source.is_dir():
            nested = self.source / PACKAGE_ROOT
            self._root = nested.resolve() if nested.is_dir() else self.source
        else:
            raise ExperimentError("asset package path does not exist")

    @property
    def source_kind(self) -> str:
        return "ZIP_SHA256_VERIFIED" if self._zip is not None else "DIRECTORY_MEMBERS_VERIFIED"

    def read(self, relative: str) -> bytes:
        member = _safe_relative_path(relative, "startAnchorPath")
        if self._zip is not None:
            archive_member = f"{PACKAGE_ROOT}/{member}"
            try:
                info = self._zip.getinfo(archive_member)
                if info.is_dir() or info.file_size > 100_000_000:
                    raise ExperimentError("asset package member is invalid")
                return self._zip.read(info)
            except KeyError as exc:
                raise ExperimentError(
                    f"asset package member is missing: {member}"
                ) from exc

        assert self._root is not None
        candidate = (self._root / Path(*PurePosixPath(member).parts)).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ExperimentError("asset package member escaped its root") from exc
        if not candidate.is_file():
            raise ExperimentError(f"asset package member is missing: {member}")
        try:
            return candidate.read_bytes()
        except OSError as exc:
            raise ExperimentError(f"asset package member could not be read: {member}") from exc

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._zip is not None:
            self._zip.close()


def _node_inputs(workflow: Mapping[str, Any], node_id: str) -> Mapping[str, Any]:
    node = workflow.get(node_id)
    if not isinstance(node, Mapping) or not isinstance(node.get("inputs"), Mapping):
        raise ExperimentError(f"workflow node {node_id} is invalid")
    return node["inputs"]


def _validate_workflow(workflow: Mapping[str, Any]) -> None:
    if set(workflow) != set(EXPECTED_CLASS_TYPES):
        raise ExperimentError("workflow node set changed")
    for node_id, class_type in EXPECTED_CLASS_TYPES.items():
        node = workflow.get(node_id)
        if not isinstance(node, Mapping) or node.get("class_type") != class_type:
            raise ExperimentError(f"workflow node {node_id} changed")

    if _node_inputs(workflow, "1") != {
        "unet_name": MODEL_FILES[0][1].split("/", 1)[1],
        "weight_dtype": "default",
    }:
        raise ExperimentError("workflow UNET parameters changed")
    if _node_inputs(workflow, "2") != {
        "clip_name": MODEL_FILES[1][1].split("/", 1)[1],
        "type": "wan",
        "device": "default",
    }:
        raise ExperimentError("workflow text-encoder parameters changed")
    if _node_inputs(workflow, "3") != {
        "vae_name": MODEL_FILES[2][1].split("/", 1)[1]
    }:
        raise ExperimentError("workflow VAE parameters changed")

    latent = _node_inputs(workflow, "7")
    if any(
        latent.get(field) != expected
        for field, expected in (
            ("width", 704),
            ("height", 1280),
            ("length", 49),
            ("batch_size", 1),
            ("start_image", ["12", 0]),
        )
    ):
        raise ExperimentError("workflow is not one native 704x1280 49-frame segment")

    sampler = _node_inputs(workflow, "8")
    for field, expected in (
        ("steps", 20),
        ("cfg", 5.0),
        ("sampler_name", "uni_pc"),
        ("scheduler", "simple"),
        ("denoise", 1.0),
    ):
        if sampler.get(field) != expected:
            raise ExperimentError(f"workflow sampler {field} changed")
    if _node_inputs(workflow, "4").get("shift") != 8.0:
        raise ExperimentError("workflow model shift changed")
    if _node_inputs(workflow, "10") != {
        "images": ["9", 0], "fps": 24, "bit_depth": 8
    }:
        raise ExperimentError("workflow video parameters changed")
    save = _node_inputs(workflow, "11")
    if save.get("format") != "mp4" or save.get("codec") != "h264":
        raise ExperimentError("workflow output format changed")


def _validate_contract(contract: Mapping[str, Any], workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    required_false = (
        "publicationAllowed",
        "canonicalMutationAllowed",
        "assetVersionCreationAllowed",
        "admissionAllowed",
        "masterExportAllowed",
    )
    if (
        contract.get("schemaVersion") != "k2-002.ep01-i2v-technical-batch.v1"
        or contract.get("experimentId") != EXPERIMENT_ID
        or contract.get("projectId") != "K2-002-CHANGAN"
        or contract.get("episodeId") != "EP01"
        or contract.get("authorityState") != AUTHORITY_STATE
        or any(contract.get(field) is not False for field in required_false)
    ):
        raise ExperimentError("shots.json technical-only boundary changed")

    package = contract.get("sourcePackage")
    if not isinstance(package, Mapping) or any(
        package.get(field) != expected
        for field, expected in (
            ("filename", "final-assets-v1.2.zip"),
            ("sha256", PACKAGE_SHA256),
            ("archiveRoot", PACKAGE_ROOT),
            ("assetState", "CANDIDATE_NOT_CANONICAL"),
        )
    ):
        raise ExperimentError("shots.json source package changed")

    profile = contract.get("workflow")
    if not isinstance(profile, Mapping) or any(
        profile.get(field) != expected
        for field, expected in (
            ("width", 704),
            ("height", 1280),
            ("nativeFrames", 49),
            ("frameRate", 24),
            ("segmentsPerShot", 1),
            ("steps", 20),
            ("cfg", 5.0),
            ("sampler", "uni_pc"),
            ("scheduler", "simple"),
            ("modelShift", 8.0),
            ("denoise", 1.0),
        )
    ):
        raise ExperimentError("shots.json workflow profile changed")

    execution = contract.get("execution")
    if not isinstance(execution, Mapping) or any(
        execution.get(field) != expected
        for field, expected in (
            ("shotCount", 12),
            ("sequential", True),
            ("parallelism", 1),
            ("automaticRetryCount", 0),
            ("chainedSegmentsAllowed", False),
            ("stitchingAllowed", False),
            ("motionPolicy", "LOW_MOTION_ONLY"),
        )
    ):
        raise ExperimentError("shots.json execution boundary changed")

    raw_shots = contract.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) != 12:
        raise ExperimentError("shots.json must contain exactly twelve shots")
    shots: list[dict[str, Any]] = []
    for expected_ordinal, raw in enumerate(raw_shots, start=1):
        if not isinstance(raw, dict):
            raise ExperimentError("shot entry is invalid")
        shot_id = raw.get("shotId")
        digest = raw.get("startAnchorSha256")
        prompt = raw.get("positivePrompt")
        negative = raw.get("negativePrompt")
        source_action = raw.get("sourceAction")
        output_prefix = raw.get("outputPrefix")
        if (
            not isinstance(shot_id, str)
            or not SAFE_SHOT_ID.fullmatch(shot_id)
            or raw.get("ordinal") != expected_ordinal
            or shot_id != f"EP01_SH{expected_ordinal:02d}"
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or raw.get("startAnchorWidth") != 704
            or raw.get("startAnchorHeight") != 1280
            or raw.get("seed") != int(digest[:13], 16)
            or not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > 4000
            or not isinstance(negative, str)
            or not negative.strip()
            or len(negative) > 4000
            or not isinstance(source_action, str)
            or not source_action.strip()
            or source_action in prompt
            or not isinstance(output_prefix, str)
            or not SAFE_OUTPUT_PREFIX.fullmatch(output_prefix)
        ):
            raise ExperimentError(f"shot {expected_ordinal:02d} contract is invalid")
        _safe_relative_path(raw.get("startAnchorPath"), "startAnchorPath")
        shots.append(raw)

    first = shots[0]
    if (
        _node_inputs(workflow, "5").get("text") != first["positivePrompt"]
        or _node_inputs(workflow, "6").get("text") != first["negativePrompt"]
        or _node_inputs(workflow, "8").get("seed") != first["seed"]
        or _node_inputs(workflow, "11").get("filename_prefix")
        != f"k2-002-ep01-i2v/{first['outputPrefix']}"
        or _node_inputs(workflow, "12").get("image")
        != f"k2-002-ep01-i2v/{first['startAnchorSha256']}.png"
    ):
        raise ExperimentError("workflow.json is not the importable SH01 instance")
    return shots


def _validate_assets(package: AssetPackage, shots: Sequence[Mapping[str, Any]]) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for shot in shots:
        payload = package.read(str(shot["startAnchorPath"]))
        if sha256(payload).hexdigest() != shot["startAnchorSha256"]:
            raise ExperimentError(f"{shot['shotId']} start-anchor SHA-256 changed")
        if _png_dimensions(payload, str(shot["shotId"])) != (704, 1280):
            raise ExperimentError(f"{shot['shotId']} start anchor is not 704x1280")
        payloads[str(shot["shotId"])] = payload
    return payloads


def _verify_models(model_root: Path) -> list[dict[str, Any]]:
    root = model_root.resolve()
    if not root.is_dir():
        raise ExperimentError("model root is unavailable")
    facts: list[dict[str, Any]] = []
    for role, relative, expected_digest in MODEL_FILES:
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ExperimentError("model path escaped its root") from exc
        if not path.is_file():
            raise ExperimentError(f"{role} model file is missing")
        actual_digest = _file_sha256(path)
        if actual_digest != expected_digest:
            raise ExperimentError(f"{role} model SHA-256 does not match")
        facts.append(
            {
                "role": role,
                "name": path.name,
                "sha256": actual_digest,
                "bytes": path.stat().st_size,
            }
        )
    return facts


def _loopback_base_url(value: str) -> str:
    parsed = parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ExperimentError("ComfyUI URL must be credential-free loopback HTTP")
    return value.rstrip("/")


def _json_request(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json", "User-Agent": "ACS-K2-002-I2V/1"}
    if payload is not None:
        body = _canonical_bytes(payload)
        headers["Content-Type"] = "application/json"
    call = request.Request(
        f"{base_url}{path}", data=body, method=method, headers=headers
    )
    try:
        with HTTP_OPENER.open(call, timeout=timeout) as response:
            raw = response.read(16_000_001)
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ExperimentError("ComfyUI request failed") from exc
    if len(raw) > 16_000_000:
        raise ExperimentError("ComfyUI JSON response exceeded the size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentError("ComfyUI returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExperimentError("ComfyUI JSON response is not an object")
    return value


def _combo_values(object_info: Mapping[str, Any], node: str, field: str) -> set[str]:
    try:
        definition = object_info[node]["input"]["required"][field]
    except (KeyError, TypeError, IndexError):
        return set()
    if not isinstance(definition, list) or not definition:
        return set()
    values = definition[0]
    return set(values) if isinstance(values, list) else set()


def _probe_runtime(base_url: str) -> dict[str, Any]:
    stats = _json_request(base_url, "GET", "/system_stats")
    object_info = _json_request(base_url, "GET", "/object_info")
    missing = [
        class_type
        for class_type in set(EXPECTED_CLASS_TYPES.values())
        if class_type not in object_info
    ]
    if missing:
        raise ExperimentError("ComfyUI is missing required native nodes")
    if "start_image" not in (
        object_info.get("Wan22ImageToVideoLatent", {})
        .get("input", {})
        .get("optional", {})
    ):
        raise ExperimentError("Wan22ImageToVideoLatent.start_image is unavailable")
    for node, field, expected in (
        ("UNETLoader", "unet_name", MODEL_FILES[0][1].split("/", 1)[1]),
        ("CLIPLoader", "clip_name", MODEL_FILES[1][1].split("/", 1)[1]),
        ("VAELoader", "vae_name", MODEL_FILES[2][1].split("/", 1)[1]),
    ):
        if expected not in _combo_values(object_info, node, field):
            raise ExperimentError(f"ComfyUI does not recognize the configured {field}")
    devices = stats.get("devices")
    if not isinstance(devices, list):
        raise ExperimentError("ComfyUI device facts are unavailable")
    cuda = [
        item
        for item in devices
        if isinstance(item, Mapping) and item.get("type") == "cuda"
    ]
    if len(cuda) != 1 or "A100" not in str(cuda[0].get("name", "")).upper():
        raise ExperimentError("exactly one A100 CUDA device is required")
    system = stats.get("system")
    if not isinstance(system, Mapping):
        raise ExperimentError("ComfyUI system facts are unavailable")
    facts = {
        "comfyuiVersion": str(system.get("comfyui_version", "")),
        "pythonVersion": str(system.get("python_version", "")),
        "pytorchVersion": str(system.get("pytorch_version", "")),
        "deviceName": str(cuda[0].get("name", "")),
        "deviceType": "cuda",
        "vramTotalBytes": int(cuda[0].get("vram_total", 0)),
        "objectInfoDigest": _canonical_digest(object_info),
        "requiredNodes": sorted(set(EXPECTED_CLASS_TYPES.values())),
    }
    if facts["vramTotalBytes"] <= 0:
        raise ExperimentError("A100 VRAM facts are invalid")
    return facts


def _stage_input(comfyui_root: Path, shot: Mapping[str, Any], payload: bytes) -> str:
    root = comfyui_root.resolve()
    input_root = (root / "input").resolve()
    if not input_root.is_dir():
        raise ExperimentError("ComfyUI input directory is unavailable")
    stage_root = (input_root / "k2-002-ep01-i2v").resolve()
    try:
        stage_root.relative_to(input_root)
    except ValueError as exc:
        raise ExperimentError("ComfyUI input staging escaped its root") from exc
    stage_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = stage_root / f"{shot['startAnchorSha256']}.png"
    if destination.exists():
        if not destination.is_file() or _file_sha256(destination) != shot["startAnchorSha256"]:
            raise ExperimentError(f"{shot['shotId']} staged input conflicts")
    else:
        temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            if _file_sha256(temporary) != shot["startAnchorSha256"]:
                raise ExperimentError(f"{shot['shotId']} staged input digest changed")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination.relative_to(input_root).as_posix()


def _shot_workflow(
    template: Mapping[str, Any], shot: Mapping[str, Any], staged_image: str
) -> dict[str, Any]:
    workflow = json.loads(json.dumps(template, ensure_ascii=False))
    workflow["5"]["inputs"]["text"] = shot["positivePrompt"]
    workflow["6"]["inputs"]["text"] = shot["negativePrompt"]
    workflow["8"]["inputs"]["seed"] = shot["seed"]
    workflow["11"]["inputs"]["filename_prefix"] = (
        f"k2-002-ep01-i2v/{shot['outputPrefix']}"
    )
    workflow["12"]["inputs"]["image"] = staged_image
    _validate_workflow(workflow)
    return workflow


def _find_video(value: Any) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        filename = value.get("filename")
        subfolder = value.get("subfolder", "")
        output_type = value.get("type")
        if (
            isinstance(filename, str)
            and filename.lower().endswith(".mp4")
            and PurePosixPath(filename).name == filename
            and isinstance(subfolder, str)
            and not PurePosixPath(subfolder).is_absolute()
            and ".." not in PurePosixPath(subfolder).parts
            and output_type == "output"
        ):
            return {"filename": filename, "subfolder": subfolder, "type": output_type}
        for nested in value.values():
            found = _find_video(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_video(nested)
            if found is not None:
                return found
    return None


def _wait_for_video(
    base_url: str,
    prompt_id: str,
    expected_prefix: str,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, str]:
    started = time.monotonic()
    while True:
        if time.monotonic() - started > timeout_seconds:
            raise ExperimentError("ComfyUI shot execution timed out")
        history = _json_request(
            base_url,
            "GET",
            f"/history/{parse.quote(prompt_id, safe='')}",
        )
        entry = history.get(prompt_id)
        if entry is not None and not isinstance(entry, Mapping):
            raise ExperimentError("ComfyUI history entry is invalid")
        if isinstance(entry, Mapping):
            outputs = entry.get("outputs")
            output = _find_video(outputs.get("11") if isinstance(outputs, Mapping) else None)
            if (
                output is not None
                and output["subfolder"] == "k2-002-ep01-i2v"
                and output["filename"].startswith(f"{expected_prefix}_")
            ):
                return output
            status = entry.get("status")
            if isinstance(status, Mapping):
                messages = status.get("messages")
                if isinstance(messages, list) and any(
                    isinstance(item, list)
                    and item
                    and item[0] in {"execution_error", "execution_interrupted"}
                    for item in messages
                ):
                    raise ExperimentError("ComfyUI shot execution failed")
                if status.get("completed") is True:
                    raise ExperimentError("ComfyUI completed without the expected MP4")
        time.sleep(poll_seconds)


def _download(base_url: str, file_info: Mapping[str, str], destination: Path) -> None:
    query = parse.urlencode(
        {
            "filename": file_info["filename"],
            "subfolder": file_info["subfolder"],
            "type": file_info["type"],
        }
    )
    call = request.Request(
        f"{base_url}/view?{query}",
        method="GET",
        headers={"Accept": "video/mp4", "User-Agent": "ACS-K2-002-I2V/1"},
    )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    total = 0
    try:
        with HTTP_OPENER.open(call, timeout=60) as response, temporary.open("xb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 2_000_000_000:
                    raise ExperimentError("ComfyUI MP4 exceeded the size limit")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if total == 0:
            raise ExperimentError("ComfyUI MP4 is empty")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ExperimentError("ComfyUI MP4 download failed") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _probe_video(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = json.loads(result.stdout)
    except (
        FileNotFoundError,
        subprocess.SubprocessError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ExperimentError("generated MP4 could not be probed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ExperimentError("generated MP4 stream facts are invalid")
    video = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    if len(video) != 1 or audio:
        raise ExperimentError("generated MP4 must contain one video stream and no audio")
    stream = video[0]
    try:
        frame_count = int(stream.get("nb_read_frames") or stream.get("nb_frames"))
        frame_rate = Fraction(str(stream["avg_frame_rate"]))
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ExperimentError("generated MP4 probe is incomplete") from exc
    if (
        width != 704
        or height != 1280
        or frame_count != 49
        or frame_rate != Fraction(24, 1)
        or not (1.9 <= duration <= 2.2)
    ):
        raise ExperimentError("generated MP4 does not match 704x1280/49f/24fps")
    return {
        "codec": str(stream.get("codec_name", "")),
        "pixelFormat": str(stream.get("pix_fmt", "")),
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "frameRate": "24/1",
        "durationSeconds": duration,
        "audioStreamCount": 0,
    }


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    payload += "\n"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except FileExistsError as exc:
        raise ExperimentError(f"evidence file already exists: {path.name}") from exc


def _existing_evidence_is_exact(
    record_path: Path, media_path: Path, shot: Mapping[str, Any]
) -> bool:
    if not record_path.is_file() or not media_path.is_file():
        return False
    record = _load_json(record_path, "existing evidence")
    return (
        record.get("schemaVersion") == "k2-002.ep01-i2v-technical-evidence.v1"
        and record.get("experimentId") == EXPERIMENT_ID
        and record.get("shotId") == shot["shotId"]
        and record.get("authorityState") == AUTHORITY_STATE
        and record.get("publicationAllowed") is False
        and record.get("canonicalMutationCount") == 0
        and record.get("input", {}).get("sha256") == shot["startAnchorSha256"]
        and record.get("output", {}).get("sha256") == _file_sha256(media_path)
    )


def _run_shot(
    *,
    base_url: str,
    comfyui_root: Path,
    evidence_root: Path,
    template: Mapping[str, Any],
    shot: Mapping[str, Any],
    payload: bytes,
    runtime_facts: Mapping[str, Any],
    timeout_seconds: int,
    poll_seconds: float,
    skip_existing: bool,
) -> dict[str, Any]:
    record_path = evidence_root / "records" / f"{shot['shotId']}.json"
    media_path = evidence_root / "media" / f"{shot['shotId']}.mp4"
    if skip_existing and _existing_evidence_is_exact(record_path, media_path, shot):
        return _load_json(record_path, "existing evidence")
    if record_path.exists() or media_path.exists():
        raise ExperimentError(f"{shot['shotId']} evidence already exists or is partial")

    staged_image = _stage_input(comfyui_root, shot, payload)
    workflow = _shot_workflow(template, shot, staged_image)
    workflow_digest = _canonical_digest(workflow)
    started = time.monotonic()
    submitted = _json_request(
        base_url,
        "POST",
        "/prompt",
        payload={
            "prompt": workflow,
            "client_id": f"k2-002-ep01-i2v-{str(shot['shotId']).lower()}",
        },
    )
    prompt_id = submitted.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 200:
        raise ExperimentError("ComfyUI prompt reference is invalid")
    file_info = _wait_for_video(
        base_url,
        prompt_id,
        str(shot["outputPrefix"]),
        timeout_seconds,
        poll_seconds,
    )
    _download(base_url, file_info, media_path)
    probe = _probe_video(media_path)
    latency_ms = max(0, round((time.monotonic() - started) * 1000))
    record = {
        "schemaVersion": "k2-002.ep01-i2v-technical-evidence.v1",
        "experimentId": EXPERIMENT_ID,
        "projectId": "K2-002-CHANGAN",
        "episodeId": "EP01",
        "shotId": shot["shotId"],
        "ordinal": shot["ordinal"],
        "authorityState": AUTHORITY_STATE,
        "publicationAllowed": False,
        "canonicalMutationCount": 0,
        "assetVersionCreated": False,
        "admissionCreated": False,
        "masterExportCreated": False,
        "observedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input": {
            "state": "CANDIDATE_NOT_CANONICAL",
            "relativePath": shot["startAnchorPath"],
            "sha256": shot["startAnchorSha256"],
            "bytes": len(payload),
            "width": 704,
            "height": 1280,
        },
        "workflow": {
            "format": "COMFYUI_API_PROMPT",
            "sha256": workflow_digest,
            "templateSha256": _file_sha256(WORKFLOW_PATH),
            "shotsContractSha256": _file_sha256(SHOTS_PATH),
            "width": 704,
            "height": 1280,
            "nativeFrames": 49,
            "frameRate": 24,
            "segments": 1,
            "stitching": False,
            "seed": shot["seed"],
            "steps": 20,
            "cfg": 5.0,
            "sampler": "uni_pc",
            "scheduler": "simple",
            "modelShift": 8.0,
            "sourceAction": shot["sourceAction"],
            "positivePrompt": shot["positivePrompt"],
            "negativePrompt": shot["negativePrompt"],
        },
        "runtime": {
            "transport": "LOCAL_LOOPBACK_COMFYUI",
            "promptRef": prompt_id,
            "latencyMs": latency_ms,
            "facts": dict(runtime_facts),
            "factsDigest": _canonical_digest(runtime_facts),
        },
        "output": {
            "state": "UNSELECTED_TECHNICAL_EVIDENCE",
            "relativePath": f"media/{shot['shotId']}.mp4",
            "sha256": _file_sha256(media_path),
            "bytes": media_path.stat().st_size,
            "probe": probe,
        },
    }
    _write_json_exclusive(record_path, record)
    return record


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or execute the non-canonical K2-002 EP01 Wan2.2 I2V "
            "technical experiment."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--asset-package", type=Path, required=True)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--comfyui-root", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--shot-id", action="append", default=[])
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.timeout_seconds < 60 or args.poll_seconds <= 0:
        parser.error("timeout and poll interval must be positive")
    if args.execute and (
        args.model_root is None
        or args.comfyui_root is None
        or args.evidence_root is None
    ):
        parser.error("--execute requires --model-root, --comfyui-root and --evidence-root")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        workflow = _load_json(WORKFLOW_PATH, "workflow.json")
        contract = _load_json(SHOTS_PATH, "shots.json")
        _validate_workflow(workflow)
        shots = _validate_contract(contract, workflow)
        selected_ids = set(args.shot_id)
        known_ids = {str(shot["shotId"]) for shot in shots}
        if selected_ids - known_ids:
            raise ExperimentError("an unknown --shot-id was requested")
        selected = [shot for shot in shots if not selected_ids or shot["shotId"] in selected_ids]
        with AssetPackage(args.asset_package) as package:
            payloads = _validate_assets(package, shots)
            model_facts = (
                _verify_models(args.model_root)
                if args.model_root is not None
                else []
            )
            if args.validate_only:
                print("VALIDATION=PASS")
                print(f"EXPERIMENT_ID={EXPERIMENT_ID}")
                print(f"AUTHORITY_STATE={AUTHORITY_STATE}")
                print("PUBLICATION_ALLOWED=false")
                print(f"SOURCE_PACKAGE_MODE={package.source_kind}")
                print("SHOT_COUNT=12")
                print("OUTPUT_PROFILE=704x1280/49f/24fps/ONE_SEGMENT")
                print("GPU_OR_PROVIDER_CALLS=0")
                print("CANONICAL_MUTATIONS=0")
                return 0

        base_url = _loopback_base_url(args.base_url)
        assert args.comfyui_root is not None
        assert args.evidence_root is not None
        evidence_root = args.evidence_root.resolve()
        if evidence_root == REPOSITORY_ROOT or REPOSITORY_ROOT in evidence_root.parents:
            raise ExperimentError("runtime evidence must be written outside the repository")
        evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_facts = _probe_runtime(base_url)
        results: list[dict[str, Any]] = []
        for shot in selected:
            print(f"START {shot['shotId']}", flush=True)
            result = _run_shot(
                base_url=base_url,
                comfyui_root=args.comfyui_root,
                evidence_root=evidence_root,
                template=workflow,
                shot=shot,
                payload=payloads[str(shot["shotId"])],
                runtime_facts=runtime_facts,
                timeout_seconds=args.timeout_seconds,
                poll_seconds=args.poll_seconds,
                skip_existing=args.skip_existing,
            )
            results.append(result)
            print(f"COMPLETE {shot['shotId']}", flush=True)

        manifest = {
            "schemaVersion": "k2-002.ep01-i2v-technical-session.v1",
            "experimentId": EXPERIMENT_ID,
            "authorityState": AUTHORITY_STATE,
            "publicationAllowed": False,
            "canonicalMutationCount": 0,
            "assetVersionCreated": False,
            "admissionCreated": False,
            "masterExportCreated": False,
            "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "workflowTemplateSha256": _file_sha256(WORKFLOW_PATH),
            "shotsContractSha256": _file_sha256(SHOTS_PATH),
            "modelFiles": model_facts,
            "runtimeFacts": runtime_facts,
            "runtimeFactsDigest": _canonical_digest(runtime_facts),
            "requestedShotIds": [item["shotId"] for item in selected],
            "completedShotIds": [item["shotId"] for item in results],
            "evidenceRecordDigests": [
                _canonical_digest(item) for item in results
            ],
        }
        manifest_name = (
            "session-manifest.json"
            if len(selected) == 12
            else "session-manifest-" + "-".join(item["shotId"] for item in selected) + ".json"
        )
        manifest_path = evidence_root / manifest_name
        if manifest_path.exists() and args.skip_existing:
            existing = _load_json(manifest_path, "existing session manifest")
            if existing != manifest:
                raise ExperimentError("existing session manifest conflicts")
        elif not manifest_path.exists():
            _write_json_exclusive(manifest_path, manifest)
        else:
            raise ExperimentError("session manifest already exists")
        print("SESSION=COMPLETE")
        print(f"AUTHORITY_STATE={AUTHORITY_STATE}")
        print("PUBLICATION_ALLOWED=false")
        print("CANONICAL_MUTATIONS=0")
        return 0
    except ExperimentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
