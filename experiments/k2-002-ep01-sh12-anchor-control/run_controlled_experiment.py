#!/usr/bin/env python3
"""Execute the one-shot K2-002 EP01_SH12 R5 anchor-only experiment.

The deployed CLI has no batch, retry, force, unlock, seed-override, prompt, or
workflow arguments.  Its production policy is compiled below.  Unit tests may
inject a temporary policy through Python calls, but ``main`` always uses the
compiled R5 policy.
"""

from __future__ import annotations

import argparse
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from types import MappingProxyType
from urllib import error, parse, request
import zlib

from control_runner_core import (
    ALLOWED_DIFF,
    AUTHORITY_STATE,
    BaselineFacts,
    ControlError,
    EXPECTED_MODEL_LOADERS,
    EXPERIMENT_ID,
    RunCountLock,
    canonical_bytes,
    canonical_sha256,
    prepare_fixed_baseline_run,
    text_sha256,
)


RUNNER_ROOT = Path(__file__).absolute().parent
EXPECTED_RUNNER_ROOT = Path(
    "/data/coding/AI-Cinematic-Studio-main-2701/experiments/"
    "k2-002-ep01-sh12-anchor-control"
)
EXPECTED_PACKAGE_ROOT = Path("/data/coding/k2-002-ep01-i2v-v2")
EXPECTED_EVIDENCE_ROOT = Path(
    "/data/k2-technical-evidence/k2-002-ep01-i2v-v2-sh12-r5-anchor-only"
)
EXPECTED_MODEL_ROOT = Path("/data/coding/apps/ComfyUI/models")
EXPECTED_COMFYUI_ROOT = Path("/data/coding/apps/ComfyUI")
EXPECTED_BASE_URL = "http://127.0.0.1:8188"
EXPECTED_MANIFEST_PATH = (
    EXPECTED_RUNNER_ROOT / "experiments" / "EP01_SH12_R5_ANCHOR_ONLY.json"
)
ALLOWED_COMFYUI_UNTRACKED_SHA256 = MappingProxyType({
    "api_workflows/R5C-1-GPU-OpenPose-ControlNet-Closeout.md": (
        "1371589bfc191274e467b53ba475cc8e15129f4961c5164bed9889f592e22dfc"
    ),
    "api_workflows/r5c1_openpose_runner.py": (
        "df018bb287c1d1025eab9bcab79e084a2f498271dc3e0a9e1e82ce394652de33"
    ),
    "api_workflows/r5c1_sd15_openpose_api.json": (
        "e76bd44d2818be1b8e57c4e856cdd41d3046a62f433001608d492e659757052b"
    ),
    "api_workflows/run_openpose_api.py": (
        "4d20be5f720bd31bb3e87b314e033cba10399a886299afaf65e7bfc80bade6fc"
    ),
    "api_workflows/run_openpose_api_flexible.py": (
        "df018bb287c1d1025eab9bcab79e084a2f498271dc3e0a9e1e82ce394652de33"
    ),
})


@dataclass(frozen=True)
class RunnerPolicy:
    package_root: Path
    evidence_root: Path
    model_root: Path
    comfyui_root: Path
    manifest_path: Path
    base_url: str
    shots_sha256: str
    workflow_file_sha256: str
    workflow_canonical_sha256: str
    old_anchor_sha256: str
    positive_prompt_sha256: str
    negative_prompt_sha256: str
    model_sha256: Mapping[str, str]
    comfyui_commit: str
    comfyui_branch: str = "master"
    comfyui_version: str = "0.28.0"
    poll_seconds: float = 2.0
    timeout_seconds: float = 3600.0
    strict_deployment_paths: bool = True


R5_POLICY = RunnerPolicy(
    package_root=EXPECTED_PACKAGE_ROOT,
    evidence_root=EXPECTED_EVIDENCE_ROOT,
    model_root=EXPECTED_MODEL_ROOT,
    comfyui_root=EXPECTED_COMFYUI_ROOT,
    manifest_path=EXPECTED_MANIFEST_PATH,
    base_url=EXPECTED_BASE_URL,
    shots_sha256="52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9",
    workflow_file_sha256="374533b301660ce77b645fc706c185efb9cc3cf070330c4bae44078d0d34bb65",
    workflow_canonical_sha256="ead8128c3625e9ecea76fe18059ae0439136134aa1af1c4b44a2861f359122cd",
    old_anchor_sha256="21ef1ff9b874bf8be850702afd34acc1885bb22cd909b8587097b092eaea2827",
    positive_prompt_sha256="c321d403fe740753a807033b490c181d431ccc03b22924ef7da44940dfbf3f85",
    negative_prompt_sha256="02064208e66afa23a1290b1c2f79c71126267c93d2465081849e20f25265c75e",
    model_sha256={
        "UNET": "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e",
        "TEXT_ENCODER": "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68",
        "VAE": "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156",
    },
    comfyui_commit="feca51a8544511dd73d43602f387def0cc601a9d",
)

TOP_KEYS = {
    "schemaVersion",
    "experimentId",
    "authorityState",
    "publicationAllowed",
    "canonicalMutations",
    "shotId",
    "changedVariable",
    "maxRuns",
    "baseline",
    "variant",
    "allowedWorkflowDiffPointers",
}
BASELINE_KEYS = {
    "shotsSha256",
    "workflowFileSha256",
    "workflowCanonicalSha256",
    "anchorSha256",
    "seed",
    "positivePromptSha256",
    "negativePromptSha256",
    "modelSha256",
    "comfyuiCommit",
}
VARIANT_KEYS = {"anchorPath", "anchorSha256", "seedPolicy", "seed"}
PROVENANCE_KEYS = {
    "schemaVersion",
    "experimentId",
    "authorityState",
    "publicationAllowed",
    "canonicalMutations",
    "assetState",
    "source",
    "output",
    "editMethod",
    "reviewer",
    "reviewedAt",
    "anchorReadiness",
}
READINESS_CRITERIA = (
    "BODY_OUTSIDE_OR_AT_THRESHOLD",
    "REAR_FOOT_WEIGHT_BEARING_OUTSIDE",
    "REAR_FOOT_FULLY_VISIBLE",
    "FRONT_FOOT_PRE_STEP_NEAR_THRESHOLD",
    "BOTH_BOOTS_VISIBLE_NOT_OVERLAPPING",
    "ROBE_HEM_REVEALS_LEG_RELATION",
    "THRESHOLD_LINE_CLEAR_BETWEEN_FEET",
    "BODY_TURNED_20_TO_30_DEGREES_INWARD",
    "PELVIS_AND_SHOULDERS_LEAN_FORWARD",
    "INTERIOR_LANDING_SPACE_RESERVED",
    "CANONICAL_IDENTITY_AND_WARDROBE_STABLE",
    "NO_EXAGGERATED_STEP_EXTRA_LIMBS_OR_BAD_PROPORTIONS",
)


@dataclass(frozen=True)
class PreparedRun:
    manifest: Mapping[str, Any]
    baseline_workflow: Mapping[str, Any]
    variant_workflow: Mapping[str, Any]
    variant_anchor_path: Path
    variant_anchor_sha256: str
    provenance_path: Path
    baseline_package_snapshot: Mapping[str, Any]
    model_facts: Mapping[str, Mapping[str, Any]]
    git_facts: Mapping[str, Any]
    gates: Mapping[str, str]
    control_receipt: Mapping[str, Any]
    initial_state: Mapping[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_json_constant(value: str) -> None:
    raise ControlError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ControlError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_json_strict(path: Path, label: str) -> Any:
    raw = _stable_read(path, max_bytes=16_000_000)
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlError(f"{label} is not strict UTF-8 JSON") from exc


def _strict_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ControlError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ControlError(
            f"{label} keys changed; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )
    return value


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_symlink_chain(path: Path) -> None:
    absolute = _absolute_lexical(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ControlError(f"symlink path component is forbidden: {current}")


def _assert_regular_file(path: Path, label: str) -> None:
    _assert_no_symlink_chain(path)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ControlError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ControlError(f"{label} is not a regular file: {path}")


def _require_under(path: Path, root: Path, label: str) -> Path:
    absolute = _absolute_lexical(path)
    expected_root = _absolute_lexical(root)
    try:
        absolute.relative_to(expected_root)
    except ValueError as exc:
        raise ControlError(f"{label} escaped its fixed root") from exc
    _assert_no_symlink_chain(absolute)
    return absolute


def _stable_read(path: Path, *, max_bytes: int | None = None) -> bytes:
    _assert_regular_file(path, "input file")
    path_info = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (path_info.st_dev, path_info.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise ControlError(f"input path changed before open: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ControlError(f"file exceeds size limit: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after or total != after.st_size:
            raise ControlError(f"file changed while it was read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def file_sha256(path: Path) -> str:
    _assert_regular_file(path, "hash input")
    path_info = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = sha256()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (path_info.st_dev, path_info.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise ControlError(f"hash path changed before open: {path}")
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or total != after.st_size
        ):
            raise ControlError(f"file changed while it was hashed: {path}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _parse_png(payload: bytes, label: str) -> dict[str, Any]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ControlError(f"{label} is not a PNG")
    offset = 8
    chunks: list[str] = []
    width = height = color_type = None
    saw_iend = False
    saw_ihdr = False
    idat_parts: list[bytes] = []
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ControlError(f"{label} has a truncated PNG chunk")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(payload):
            raise ControlError(f"{label} has an invalid PNG chunk length")
        data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
        actual_crc = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ControlError(f"{label} PNG CRC is invalid")
        name = chunk_type.decode("ascii", errors="replace")
        chunks.append(name)
        if len(chunks) == 1:
            if chunk_type != b"IHDR" or length != 13:
                raise ControlError(f"{label} PNG must begin with IHDR")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            saw_ihdr = True
            if compression != 0 or filtering != 0 or interlace != 0:
                raise ControlError(f"{label} PNG IHDR is unsupported")
            if bit_depth != 8 or color_type != 2:
                raise ControlError(f"{label} must be non-interlaced 8-bit RGB PNG")
        elif chunk_type == b"IHDR":
            raise ControlError(f"{label} contains multiple IHDR chunks")
        if chunk_type == b"IDAT":
            idat_parts.append(data)
        if chunk_type == b"acTL":
            raise ControlError(f"{label} must be a static PNG, not APNG")
        if chunk_type == b"IEND":
            if length != 0 or end != len(payload):
                raise ControlError(f"{label} PNG IEND is invalid")
            saw_iend = True
            break
        offset = end
    if not saw_iend or not saw_ihdr or not idat_parts or width is None or height is None:
        raise ControlError(f"{label} PNG is incomplete")
    if (width, height) != (704, 1280):
        raise ControlError(f"{label} must be exactly 704x1280")
    try:
        pixels = zlib.decompress(b"".join(idat_parts))
    except zlib.error as exc:
        raise ControlError(f"{label} PNG IDAT stream is corrupt") from exc
    row_bytes = 1 + width * 3
    if len(pixels) != row_bytes * height or any(
        pixels[offset] > 4 for offset in range(0, len(pixels), row_bytes)
    ):
        raise ControlError(f"{label} PNG raster layout is invalid")
    return {
        "width": width,
        "height": height,
        "colorType": color_type,
        "staticPng": True,
        "sha256": sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _package_snapshot(root: Path) -> dict[str, Any]:
    root = _absolute_lexical(root)
    _assert_no_symlink_chain(root)
    if not root.is_dir():
        raise ControlError("baseline package root is unavailable")
    rows: list[dict[str, Any]] = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        for name in list(names):
            candidate = base / name
            if candidate.is_symlink():
                raise ControlError(f"baseline package contains a symlink: {candidate}")
        for name in sorted(files):
            candidate = base / name
            _assert_regular_file(candidate, "baseline package file")
            rows.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "bytes": candidate.stat().st_size,
                    "sha256": file_sha256(candidate),
                }
            )
    rows.sort(key=lambda item: item["path"])
    return {"fileCount": len(rows), "treeSha256": canonical_sha256(rows), "files": rows}


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_secure_directory(path: Path) -> None:
    _assert_no_symlink_chain(path.parent)
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        _fsync_directory(path.parent)
    except FileExistsError:
        pass
    _assert_no_symlink_chain(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ControlError(f"evidence path is not a directory: {path}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ControlError(f"evidence directory is group/world writable: {path}")


def _write_bytes_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    _ensure_secure_directory(path.parent)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError as exc:
        raise ControlError(f"refusing to overwrite evidence: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes_exclusive(
        path,
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n",
    )


def _validate_compiled_policy(policy: RunnerPolicy) -> None:
    if policy.strict_deployment_paths:
        if _absolute_lexical(RUNNER_ROOT) != _absolute_lexical(EXPECTED_RUNNER_ROOT):
            raise ControlError("control runner is not installed at its versioned fixed path")
        expected = {
            "package_root": EXPECTED_PACKAGE_ROOT,
            "evidence_root": EXPECTED_EVIDENCE_ROOT,
            "model_root": EXPECTED_MODEL_ROOT,
            "comfyui_root": EXPECTED_COMFYUI_ROOT,
            "manifest_path": EXPECTED_MANIFEST_PATH,
        }
        for field, required in expected.items():
            if _absolute_lexical(getattr(policy, field)) != _absolute_lexical(required):
                raise ControlError(f"compiled deployment {field} changed")
        if policy.base_url != EXPECTED_BASE_URL:
            raise ControlError("compiled loopback URL changed")
    parsed = parse.urlsplit(policy.base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ControlError("ComfyUI endpoint must be exact credential-free IPv4 loopback HTTP")


def _validate_manifest_pins(
    manifest: Any, policy: RunnerPolicy
) -> Mapping[str, Any]:
    manifest = _strict_keys(manifest, TOP_KEYS, "experiment manifest")
    baseline = _strict_keys(manifest["baseline"], BASELINE_KEYS, "manifest baseline")
    variant = _strict_keys(manifest["variant"], VARIANT_KEYS, "manifest variant")
    models = _strict_keys(
        baseline["modelSha256"], set(EXPECTED_MODEL_LOADERS), "manifest modelSha256"
    )
    pins = {
        "shotsSha256": policy.shots_sha256,
        "workflowFileSha256": policy.workflow_file_sha256,
        "workflowCanonicalSha256": policy.workflow_canonical_sha256,
        "anchorSha256": policy.old_anchor_sha256,
        "positivePromptSha256": policy.positive_prompt_sha256,
        "negativePromptSha256": policy.negative_prompt_sha256,
        "comfyuiCommit": policy.comfyui_commit,
    }
    for field, expected in pins.items():
        if baseline.get(field) != expected:
            raise ControlError(f"manifest cannot redefine frozen {field}")
    if dict(models) != dict(policy.model_sha256):
        raise ControlError("manifest cannot redefine frozen model digests")
    if type(baseline.get("seed")) is not int or baseline.get("seed") != 596974677755723:
        raise ControlError("manifest cannot redefine frozen baseline seed")
    if type(variant.get("seed")) is not int:
        raise ControlError("variant seed must be an exact integer")
    return manifest


def _validate_provenance(
    path: Path,
    *,
    anchor_path: Path,
    anchor_sha256: str,
    old_anchor_sha256: str,
) -> dict[str, Any]:
    value = _strict_keys(load_json_strict(path, "anchor provenance"), PROVENANCE_KEYS, "anchor provenance")
    if type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 1:
        raise ControlError("anchor provenance schemaVersion changed")
    if (
        value.get("experimentId") != EXPERIMENT_ID
        or value.get("authorityState") != AUTHORITY_STATE
        or value.get("publicationAllowed") is not False
        or type(value.get("canonicalMutations")) is not int
        or value.get("canonicalMutations") != 0
        or value.get("assetState") != "DERIVED_TECHNICAL_CANDIDATE_NOT_CANONICAL"
    ):
        raise ControlError("anchor provenance governance boundary changed")
    source = _strict_keys(value.get("source"), {"path", "sha256"}, "provenance source")
    output = _strict_keys(
        value.get("output"), {"path", "sha256", "width", "height"}, "provenance output"
    )
    if (
        source.get("sha256") != old_anchor_sha256
        or source.get("path") != "anchors/EP01_SH12_anchor_v2.png"
    ):
        raise ControlError("provenance source is not the frozen R3 anchor")
    if (
        _absolute_lexical(Path(str(output.get("path")))) != _absolute_lexical(anchor_path)
        or output.get("sha256") != anchor_sha256
        or type(output.get("width")) is not int
        or type(output.get("height")) is not int
        or (output.get("width"), output.get("height")) != (704, 1280)
    ):
        raise ControlError("provenance output does not bind the verified R5 anchor")
    if not isinstance(value.get("editMethod"), str) or not value["editMethod"].strip():
        raise ControlError("provenance editMethod is missing")
    if not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip():
        raise ControlError("provenance reviewer is missing")
    if not isinstance(value.get("reviewedAt"), str) or not value["reviewedAt"].strip():
        raise ControlError("provenance reviewedAt is missing")
    try:
        reviewed_at = datetime.fromisoformat(value["reviewedAt"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlError("provenance reviewedAt is not ISO-8601") from exc
    if reviewed_at.tzinfo is None:
        raise ControlError("provenance reviewedAt must include a timezone")
    readiness = _strict_keys(
        value.get("anchorReadiness"), {"passed", "score", "checks"}, "anchorReadiness"
    )
    checks = readiness.get("checks")
    if (
        readiness.get("passed") is not True
        or readiness.get("score") != "12/12"
        or not isinstance(checks, list)
        or len(checks) != 12
    ):
        raise ControlError("ANCHOR_READINESS must be exactly 12/12")
    for expected_id, item in enumerate(checks, start=1):
        item = _strict_keys(
            item,
            {"id", "criterion", "passed", "finding"},
            f"readiness check {expected_id}",
        )
        if (
            type(item.get("id")) is not int
            or item.get("id") != expected_id
            or item.get("criterion") != READINESS_CRITERIA[expected_id - 1]
            or item.get("passed") is not True
            or not isinstance(item.get("finding"), str)
            or not item["finding"].strip()
        ):
            raise ControlError(f"readiness check {expected_id} did not pass its fixed criterion")
    return {"sha256": file_sha256(path), "anchorReadiness": "12/12"}


def _git_command(root: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ControlError("git executable is unavailable")
    try:
        completed = subprocess.run(
            [git, "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ControlError("ComfyUI Git facts are unavailable") from exc
    return completed.stdout.rstrip("\n")


def _parse_comfyui_worktree_status(worktree_status: str) -> set[str]:
    actual_untracked: set[str] = set()
    for record in worktree_status.split("\0"):
        if not record:
            continue
        if not record.startswith("?? "):
            raise ControlError("ComfyUI tracked worktree is dirty")
        relative = record[3:]
        if not relative or relative in actual_untracked:
            raise ControlError("ComfyUI untracked status is malformed")
        actual_untracked.add(relative)
    return actual_untracked


def _git_facts(root: Path, policy: RunnerPolicy) -> dict[str, Any]:
    _assert_no_symlink_chain(root)
    if not root.is_dir():
        raise ControlError("ComfyUI root is unavailable")
    commit = _git_command(root, "rev-parse", "HEAD")
    branch = _git_command(root, "branch", "--show-current")
    worktree_status = _git_command(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != policy.comfyui_commit:
        raise ControlError("ComfyUI commit changed")
    if branch != policy.comfyui_branch:
        raise ControlError("ComfyUI branch changed")
    actual_untracked = _parse_comfyui_worktree_status(worktree_status)

    expected_untracked = set(ALLOWED_COMFYUI_UNTRACKED_SHA256)
    if actual_untracked != expected_untracked:
        raise ControlError(
            "ComfyUI untracked path set changed; "
            f"missing={sorted(expected_untracked-actual_untracked)}, "
            f"extra={sorted(actual_untracked-expected_untracked)}"
        )

    attested_untracked: list[dict[str, str]] = []
    for relative, expected_sha256 in sorted(ALLOWED_COMFYUI_UNTRACKED_SHA256.items()):
        relative_path = PurePosixPath(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != relative
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ControlError("compiled ComfyUI untracked allowlist is invalid")
        path = _require_under(
            root / Path(*relative_path.parts),
            root,
            "allowed ComfyUI untracked file",
        )
        _assert_regular_file(path, "allowed ComfyUI untracked file")
        actual_sha256 = file_sha256(path)
        if actual_sha256 != expected_sha256:
            raise ControlError(f"allowed ComfyUI untracked SHA-256 changed: {relative}")
        attested_untracked.append(
            {"path": relative, "sha256": actual_sha256}
        )

    final_worktree_status = _git_command(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if _parse_comfyui_worktree_status(final_worktree_status) != expected_untracked:
        raise ControlError("ComfyUI worktree changed during untracked attestation")

    return {
        "commit": commit,
        "branch": branch,
        "trackedWorktreeClean": True,
        "untrackedPolicy": "EXACT_CODE_PINNED_ALLOWLIST",
        "untrackedPathsExact": True,
        "worktreeStatusRechecked": True,
        "allowedUntracked": attested_untracked,
    }


def _model_facts(policy: RunnerPolicy) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for role, (_, _, filename) in EXPECTED_MODEL_LOADERS.items():
        relative_root = {
            "UNET": "diffusion_models",
            "TEXT_ENCODER": "text_encoders",
            "VAE": "vae",
        }[role]
        path = _require_under(policy.model_root / relative_root / filename, policy.model_root, f"{role} model")
        actual = file_sha256(path)
        if actual != policy.model_sha256[role]:
            raise ControlError(f"{role} model SHA-256 changed")
        facts[role] = {
            "path": str(path),
            "filename": filename,
            "sha256": actual,
            "bytes": path.stat().st_size,
        }
    return facts


def _ancestor_pids() -> set[int]:
    ancestors: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in ancestors:
        ancestors.add(pid)
        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            right = raw.rfind(")")
            pid = int(raw[right + 2 :].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return ancestors


def _find_conflicting_processes() -> list[dict[str, Any]]:
    ignored = _ancestor_pids()
    conflicts: list[dict[str, Any]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        raise ControlError("/proc is unavailable for concurrency validation")
    for candidate in proc.iterdir():
        if not candidate.name.isdigit() or int(candidate.name) in ignored:
            continue
        try:
            command = (candidate / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if "EP01_SH12" in command and any(
            marker in command
            for marker in ("run_ep01.sh", "ingest_ep01.py", "run_controlled_experiment.py")
        ):
            conflicts.append({"pid": int(candidate.name), "command": command[:1000]})
    return sorted(conflicts, key=lambda item: item["pid"])


def _gpu_compute_pids() -> list[int]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        raise ControlError("nvidia-smi is unavailable")
    try:
        result = subprocess.run(
            [
                executable,
                "--query-compute-apps=pid",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ControlError("GPU process facts are unavailable") from exc
    pids: list[int] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if value and value != "[N/A]":
            try:
                pids.append(int(value))
            except ValueError as exc:
                raise ControlError("GPU process facts are malformed") from exc
    return sorted(set(pids))


def _list_tcp_listeners(port: int) -> list[str]:
    listeners: list[str] = []
    sources = ((Path("/proc/net/tcp"), False), (Path("/proc/net/tcp6"), True))
    for source, ipv6 in sources:
        try:
            lines = source.read_text(encoding="ascii").splitlines()[1:]
        except OSError as exc:
            raise ControlError("TCP listener facts are unavailable") from exc
        for line in lines:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            address_hex, port_hex = fields[1].split(":", 1)
            if int(port_hex, 16) != port:
                continue
            if not ipv6 and len(address_hex) == 8:
                address = socket.inet_ntoa(struct.pack("<I", int(address_hex, 16)))
            else:
                address = f"ipv6:{address_hex}"
            listeners.append(address)
    return sorted(set(listeners))


def _base_23_gates() -> dict[str, str]:
    return {
        "G01_TECHNICAL_EVIDENCE_ACK": "PASS",
        "G02_FIXED_BASELINE_EXPERIMENT_ACK": "PASS",
        "G03_AUTHORITY_TECHNICAL_ONLY": "PASS",
        "G04_PUBLICATION_FALSE": "PASS",
        "G05_CANONICAL_MUTATIONS_ZERO": "PASS",
        "G06_SHOT_EP01_SH12_ONLY": "PASS",
        "G07_CHANGED_VARIABLE_START_ANCHOR_ONLY": "PASS",
        "G08_MAX_RUNS_ONE": "PASS",
        "G09_BASELINE_SHOTS_SHA": "PASS",
        "G10_BASELINE_WORKFLOW_RAW_AND_CANONICAL_SHA": "PASS",
        "G11_BASELINE_ANCHOR_SHA": "PASS",
        "G12_VARIANT_ANCHOR_DIFFERS": "PASS",
        "G13_VARIANT_SEED_EQUALS_BASELINE": "PASS",
        "G14_POSITIVE_AND_NEGATIVE_PROMPT_SHA": "PASS",
        "G15_SAMPLING_AND_OUTPUT_PROFILE_UNCHANGED": "PASS",
        "G16_MODEL_HASHES_UNCHANGED": "PASS",
        "G17_WORKFLOW_DIFF_NODE12_IMAGE_ONLY": "PASS",
        "G18_BATCH_FORBIDDEN": "PASS",
        "G19_SECOND_RUN_FORBIDDEN": "PASS",
        "G20_NO_EXISTING_COMPLETE_RECEIPT": "PASS",
        "G21_ORIGINAL_MATERIALIZED_WORKFLOW_UNMODIFIED": "PASS",
        "G22_ORIGINAL_SHOTS_JSON_UNMODIFIED": "PASS",
        "G23_PRE_SUBMIT_FAILURE_HAS_ZERO_GPU_PROVIDER_CALLS": "PASS",
    }


def _validate_shots_binding(
    shots_value: Any,
    workflow: Mapping[str, Any],
    policy: RunnerPolicy,
) -> Mapping[str, Any]:
    if not isinstance(shots_value, Mapping):
        raise ControlError("shots.json root is invalid")
    rows = shots_value.get("shots")
    if not isinstance(rows, list) or len(rows) != 18:
        raise ControlError("shots.json must retain exactly 18 shots")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("shotId") == "EP01_SH12"]
    if len(matches) != 1:
        raise ControlError("shots.json must contain exactly one EP01_SH12")
    shot = matches[0]
    positive = workflow.get("5", {}).get("inputs", {}).get("text")
    negative = workflow.get("6", {}).get("inputs", {}).get("text")
    if (
        shot.get("startAnchorPath") != "anchors/EP01_SH12_anchor_v2.png"
        or shot.get("startAnchorSha256") != policy.old_anchor_sha256
        or type(shot.get("seed")) is not int
        or shot.get("seed") != 596974677755723
        or shot.get("positivePrompt") != positive
        or shot.get("negativePrompt") != negative
    ):
        raise ControlError("shots.json SH12 binding changed")
    return shot


def _prepare(
    *,
    manifest_path: Path,
    policy: RunnerPolicy,
    require_initial_closed: bool,
    allow_reserved_attempt: bool = False,
) -> PreparedRun:
    _validate_compiled_policy(policy)
    if _absolute_lexical(manifest_path) != _absolute_lexical(policy.manifest_path):
        raise ControlError("only the fixed R5 experiment manifest is permitted")
    if _absolute_lexical(policy.evidence_root) == _absolute_lexical(policy.package_root):
        raise ControlError("evidence root cannot equal the baseline package")
    _ensure_secure_directory(policy.evidence_root)
    if os.path.lexists(policy.evidence_root / "COMPLETE.json"):
        raise ControlError("existing COMPLETE receipt forbids execution")
    if os.path.lexists(policy.evidence_root / "media" / "EP01_SH12_R5_ANCHOR_ONLY.mp4"):
        raise ControlError("existing R5 evidence video forbids a new run")
    attempt_path = policy.evidence_root / "RUN_ATTEMPT_1.json"
    if os.path.lexists(attempt_path) and not allow_reserved_attempt:
        raise ControlError("maxRuns=1 attempt is already consumed")

    conflicts = _find_conflicting_processes()
    if conflicts:
        raise ControlError(f"concurrent SH12 process detected: {conflicts}")
    parsed_url = parse.urlsplit(policy.base_url)
    assert parsed_url.port is not None
    listeners = _list_tcp_listeners(parsed_url.port)
    gpu_pids: list[int] | None = None
    if require_initial_closed:
        if listeners:
            raise ControlError(f"ComfyUI port must initially be closed: {listeners}")
        gpu_pids = _gpu_compute_pids()
        if gpu_pids:
            raise ControlError(f"GPU compute process list is not empty: {gpu_pids}")
    elif listeners != ["127.0.0.1"]:
        raise ControlError(f"ComfyUI must listen only on 127.0.0.1:{parsed_url.port}: {listeners}")

    package_before = _package_snapshot(policy.package_root)
    manifest = _validate_manifest_pins(
        load_json_strict(manifest_path, "experiment manifest"), policy
    )

    shots_path = policy.package_root / "shots.json"
    workflow_path = policy.package_root / "materialized" / "EP01_SH12.workflow.json"
    old_anchor_path = policy.package_root / "anchors" / "EP01_SH12_anchor_v2.png"
    shots_digest = file_sha256(shots_path)
    workflow_file_digest = file_sha256(workflow_path)
    if shots_digest != policy.shots_sha256:
        raise ControlError("frozen shots.json SHA-256 changed")
    if workflow_file_digest != policy.workflow_file_sha256:
        raise ControlError("frozen R3 workflow file SHA-256 changed")

    workflow = load_json_strict(workflow_path, "R3 materialized workflow")
    if not isinstance(workflow, Mapping):
        raise ControlError("R3 workflow root is invalid")
    workflow_canonical = canonical_sha256(workflow)
    if workflow_canonical != policy.workflow_canonical_sha256:
        raise ControlError("frozen R3 workflow canonical SHA-256 changed")
    positive = workflow.get("5", {}).get("inputs", {}).get("text")
    negative = workflow.get("6", {}).get("inputs", {}).get("text")
    if (
        not isinstance(positive, str)
        or text_sha256(positive) != policy.positive_prompt_sha256
        or not isinstance(negative, str)
        or text_sha256(negative) != policy.negative_prompt_sha256
    ):
        raise ControlError("frozen R3 prompt hashes changed")
    shots = load_json_strict(shots_path, "shots.json")
    _validate_shots_binding(shots, workflow, policy)

    old_payload = _stable_read(old_anchor_path, max_bytes=200_000_000)
    old_png = _parse_png(old_payload, "R3 anchor")
    if old_png["sha256"] != policy.old_anchor_sha256:
        raise ControlError("frozen R3 anchor SHA-256 changed")

    variant_spec = manifest["variant"]
    variant_anchor_path = _absolute_lexical(Path(str(variant_spec["anchorPath"])))
    inputs_root = _absolute_lexical(policy.evidence_root / "inputs")
    _require_under(variant_anchor_path, inputs_root, "variant anchor")
    if variant_anchor_path.parent != inputs_root or variant_anchor_path.suffix.lower() != ".png":
        raise ControlError("variant anchor must be a direct PNG child of the fixed inputs root")
    variant_payload = _stable_read(variant_anchor_path, max_bytes=200_000_000)
    variant_png = _parse_png(variant_payload, "R5 anchor")
    if variant_png["sha256"] != variant_spec["anchorSha256"]:
        raise ControlError("variant anchor bytes do not match manifest SHA-256")
    if variant_png["sha256"] == policy.old_anchor_sha256:
        raise ControlError("variant anchor must differ from the R3 anchor")
    provenance_path = variant_anchor_path.with_suffix(".provenance.json")
    provenance = _validate_provenance(
        provenance_path,
        anchor_path=variant_anchor_path,
        anchor_sha256=variant_png["sha256"],
        old_anchor_sha256=policy.old_anchor_sha256,
    )

    model_facts = _model_facts(policy)
    git_facts = _git_facts(policy.comfyui_root, policy)
    facts = BaselineFacts(
        shots_sha256=shots_digest,
        workflow_file_sha256=workflow_file_digest,
        workflow_canonical_sha256=workflow_canonical,
        anchor_sha256=old_png["sha256"],
        model_sha256={role: item["sha256"] for role, item in model_facts.items()},
    )
    variant_workflow, control_receipt = prepare_fixed_baseline_run(
        manifest=manifest,
        baseline_workflow=workflow,
        facts=facts,
        environ=os.environ,
    )
    package_after = _package_snapshot(policy.package_root)
    if package_after != package_before:
        raise ControlError("baseline package changed during validation")

    gates = _base_23_gates()
    initial_state = {
        "conflictingSh12Processes": conflicts,
        "port": parsed_url.port,
        "listeners": listeners,
        "portInitiallyClosed": require_initial_closed and not listeners,
        "gpuComputePids": gpu_pids,
    }
    enriched_control = {
        **dict(control_receipt),
        "baselineShotsSha256": shots_digest,
        "baselineWorkflowFileSha256": workflow_file_digest,
        "positivePromptSha256": policy.positive_prompt_sha256,
        "negativePromptSha256": policy.negative_prompt_sha256,
        "oldAnchor": old_png,
        "variantAnchor": variant_png,
        "provenance": {"path": str(provenance_path), **provenance},
        "modelFacts": model_facts,
        "comfyuiGit": git_facts,
        "baselinePackageTreeSha256": package_before["treeSha256"],
        "baselineUnchanged": True,
        "defaultAnchorDerivedPolicyPreserved": True,
        "sampling": {
            "seed": 596974677755723,
            "cfg": 5.0,
            "steps": 20,
            "shift": 8.0,
            "sampler": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
            "width": 704,
            "height": 1280,
            "frames": 49,
            "fps": 24,
        },
    }
    return PreparedRun(
        manifest=manifest,
        baseline_workflow=workflow,
        variant_workflow=variant_workflow,
        variant_anchor_path=variant_anchor_path,
        variant_anchor_sha256=variant_png["sha256"],
        provenance_path=provenance_path,
        baseline_package_snapshot=package_before,
        model_facts=model_facts,
        git_facts=git_facts,
        gates=gates,
        control_receipt=enriched_control,
        initial_state=initial_state,
    )


def _materialized_path(policy: RunnerPolicy) -> Path:
    return policy.evidence_root / "materialized" / "EP01_SH12_R5.workflow.json"


def _dry_receipt_path(policy: RunnerPolicy) -> Path:
    return policy.evidence_root / "receipts" / "DRY_RUN.json"


def run_dry_run(manifest_path: Path, policy: RunnerPolicy = R5_POLICY) -> Mapping[str, Any]:
    prepared = _prepare(
        manifest_path=manifest_path,
        policy=policy,
        require_initial_closed=True,
    )
    workflow_payload = (
        json.dumps(prepared.variant_workflow, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    materialized = _materialized_path(policy)
    _write_bytes_exclusive(materialized, workflow_payload)
    if (policy.evidence_root / "RUN_ATTEMPT_1.json").exists():
        raise ControlError("dry-run must not create a run-count lock")
    post_snapshot = _package_snapshot(policy.package_root)
    if post_snapshot != prepared.baseline_package_snapshot:
        raise ControlError("baseline package changed during dry-run")
    receipt = {
        "schemaVersion": 1,
        "experimentId": EXPERIMENT_ID,
        "mode": "DRY_RUN",
        "dryRun": "PASS",
        "authorityState": AUTHORITY_STATE,
        "publicationAllowed": False,
        "canonicalMutations": 0,
        "batchAdvanced": False,
        "networkCalls": 0,
        "gpuOrProviderCalls": 0,
        "runLockCreated": False,
        "observedAt": utc_now(),
        "manifestPath": str(_absolute_lexical(manifest_path)),
        "manifestSha256": file_sha256(manifest_path),
        "runnerSha256": file_sha256(Path(__file__)),
        "controlCoreSha256": file_sha256(RUNNER_ROOT / "control_runner_core.py"),
        "materializedWorkflowPath": str(materialized),
        "materializedWorkflowFileSha256": sha256(workflow_payload).hexdigest(),
        "materializedWorkflowCanonicalSha256": canonical_sha256(prepared.variant_workflow),
        "initialState": prepared.initial_state,
        "gates": dict(prepared.gates),
        "control": dict(prepared.control_receipt),
    }
    _write_json_exclusive(_dry_receipt_path(policy), receipt)
    return receipt


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class ComfyTransport:
    """Bounded, no-proxy, no-redirect loopback client with one-POST budget."""

    def __init__(self, base_url: str) -> None:
        parsed = parse.urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ControlError("transport is not exact IPv4 loopback")
        self.base_url = base_url.rstrip("/")
        self.opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
        self.network_calls = 0
        self.prompt_posts = 0

    def json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if method == "POST":
            if path != "/prompt" or self.prompt_posts != 0:
                raise ControlError("only one POST /prompt is permitted")
            self.prompt_posts += 1
        elif method != "GET":
            raise ControlError("unsupported HTTP method")
        body = None if payload is None else canonical_bytes(payload)
        headers = {"Accept": "application/json", "User-Agent": "K2-SH12-R5-Control/1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        call = request.Request(f"{self.base_url}{path}", data=body, method=method, headers=headers)
        self.network_calls += 1
        try:
            with self.opener.open(call, timeout=30) as response:
                raw = response.read(16_000_001)
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise ControlError(f"ComfyUI request failed without retry: {exc}") from exc
        if len(raw) > 16_000_000:
            raise ControlError("ComfyUI JSON response exceeded 16 MB")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ControlError("ComfyUI response is not strict JSON") from exc
        if not isinstance(value, Mapping):
            raise ControlError("ComfyUI response is not an object")
        return value


REQUIRED_NODES = {
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "ModelSamplingSD3",
    "CLIPTextEncode",
    "Wan22ImageToVideoLatent",
    "KSampler",
    "VAEDecode",
    "CreateVideo",
    "SaveVideo",
    "LoadImage",
}
CLIENT_ID = "k2-002-ep01-sh12-r5-anchor-only"
OUTPUT_MTIME_GRANULARITY_TOLERANCE_NS = 2_000_000_000


@dataclass(frozen=True)
class SaveVideoOutputSnapshot:
    expected_subfolder: str
    filename_prefix: str
    existing_candidate_paths: frozenset[str]
    captured_at_ns: int


def _savevideo_output_spec(
    workflow: Mapping[str, Any], policy: RunnerPolicy
) -> tuple[Path, str, str]:
    prefix = workflow.get("11", {}).get("inputs", {}).get("filename_prefix")
    if not isinstance(prefix, str) or not prefix:
        raise ControlError("baseline SaveVideo prefix is unavailable")
    prefix_path = PurePosixPath(prefix)
    if (
        prefix_path.is_absolute()
        or ".." in prefix_path.parts
        or prefix_path.name in {"", ".", ".."}
    ):
        raise ControlError("baseline SaveVideo prefix is unsafe")
    expected_subfolder = (
        "" if str(prefix_path.parent) == "." else str(prefix_path.parent)
    )
    output_root = _absolute_lexical(policy.comfyui_root / "output")
    _assert_no_symlink_chain(output_root)
    try:
        root_info = output_root.lstat()
    except FileNotFoundError as exc:
        raise ControlError("ComfyUI output root is unavailable") from exc
    if not stat.S_ISDIR(root_info.st_mode):
        raise ControlError("ComfyUI output root is not a directory")
    output_directory = _require_under(
        output_root / Path(*PurePosixPath(expected_subfolder).parts),
        output_root,
        "SaveVideo output directory",
    )
    return output_directory, expected_subfolder, prefix_path.name


def _is_exact_savevideo_candidate(filename: str, filename_prefix: str) -> bool:
    return (
        PurePosixPath(filename).name == filename
        and filename.startswith(f"{filename_prefix}_")
        and filename.lower().endswith(".mp4")
    )


def _snapshot_savevideo_candidates(
    workflow: Mapping[str, Any], policy: RunnerPolicy
) -> SaveVideoOutputSnapshot:
    output_directory, expected_subfolder, filename_prefix = _savevideo_output_spec(
        workflow, policy
    )
    try:
        path_info = output_directory.lstat()
    except FileNotFoundError:
        return SaveVideoOutputSnapshot(
            expected_subfolder=expected_subfolder,
            filename_prefix=filename_prefix,
            existing_candidate_paths=frozenset(),
            captured_at_ns=time.time_ns(),
        )
    if not stat.S_ISDIR(path_info.st_mode):
        raise ControlError("SaveVideo output directory is not a directory")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(output_directory, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(before.st_mode)
            or (path_info.st_dev, path_info.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise ControlError("SaveVideo output directory changed before snapshot")
        existing = frozenset(
            (
                PurePosixPath(expected_subfolder) / name
                if expected_subfolder
                else PurePosixPath(name)
            ).as_posix()
            for name in os.listdir(descriptor)
            if _is_exact_savevideo_candidate(name, filename_prefix)
        )
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ControlError("SaveVideo output directory changed during snapshot")
    finally:
        os.close(descriptor)
    return SaveVideoOutputSnapshot(
        expected_subfolder=expected_subfolder,
        filename_prefix=filename_prefix,
        existing_candidate_paths=existing,
        captured_at_ns=time.time_ns(),
    )


def _verify_live_runtime(transport: ComfyTransport, policy: RunnerPolicy) -> Mapping[str, Any]:
    stats = transport.json("GET", "/system_stats")
    object_info = transport.json("GET", "/object_info")
    system = stats.get("system")
    devices = stats.get("devices")
    if not isinstance(system, Mapping) or system.get("comfyui_version") != policy.comfyui_version:
        raise ControlError("live ComfyUI version changed")
    if not str(system.get("python_version", "")).startswith("3.12.7"):
        raise ControlError("live Python version changed")
    if str(system.get("pytorch_version", "")) != "2.11.0+cu126":
        raise ControlError("live PyTorch/CUDA runtime changed")
    if not isinstance(devices, list):
        raise ControlError("live ComfyUI device facts are missing")
    cuda = [
        row
        for row in devices
        if isinstance(row, Mapping) and row.get("type") == "cuda"
    ]
    if len(cuda) != 1 or "A100-PCIE-40GB" not in str(cuda[0].get("name", "")).upper():
        raise ControlError("live runtime must expose exactly one A100-PCIE-40GB CUDA device")
    if not REQUIRED_NODES.issubset(set(object_info)):
        raise ControlError("live ComfyUI required native nodes changed")
    for _, (_, field, filename) in EXPECTED_MODEL_LOADERS.items():
        node_name = {
            "unet_name": "UNETLoader",
            "clip_name": "CLIPLoader",
            "vae_name": "VAELoader",
        }[field]
        try:
            definition = object_info[node_name]["input"]["required"][field]
            options = definition[0]
        except (KeyError, TypeError, IndexError) as exc:
            raise ControlError(f"live {node_name}.{field} options are unavailable") from exc
        if not isinstance(options, list) or filename not in options:
            raise ControlError(f"live ComfyUI does not recognize frozen model {filename}")
    return {
        "comfyuiVersion": system.get("comfyui_version"),
        "pythonVersion": system.get("python_version"),
        "pytorchVersion": system.get("pytorch_version"),
        "deviceName": cuda[0].get("name"),
        "objectInfoSha256": canonical_sha256(object_info),
    }


def _verify_queue_empty(transport: ComfyTransport) -> Mapping[str, Any]:
    queue = transport.json("GET", "/queue")
    running = queue.get("queue_running")
    pending = queue.get("queue_pending")
    if not isinstance(running, list) or not isinstance(pending, list):
        raise ControlError("ComfyUI queue facts are malformed")
    if running or pending:
        raise ControlError("ComfyUI queue is not empty; concurrent work is forbidden")
    return {"running": 0, "pending": 0}


def _collect_output_candidates(value: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        if {"filename", "subfolder", "type"}.issubset(value):
            filename = value.get("filename")
            subfolder = value.get("subfolder")
            output_type = value.get("type")
            if all(isinstance(item, str) for item in (filename, subfolder, output_type)):
                found.append(
                    {"filename": filename, "subfolder": subfolder, "type": output_type}
                )
        for nested in value.values():
            found.extend(_collect_output_candidates(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_collect_output_candidates(nested))
    return found


def _validate_output_candidate(
    candidate: Mapping[str, str],
    workflow: Mapping[str, Any],
    policy: RunnerPolicy,
    submitted_at_ns: int,
    pre_submit_snapshot: SaveVideoOutputSnapshot,
) -> Path:
    filename = candidate["filename"]
    subfolder = candidate["subfolder"]
    if (
        candidate["type"] != "output"
        or PurePosixPath(filename).name != filename
        or not filename.lower().endswith(".mp4")
        or PurePosixPath(subfolder).is_absolute()
        or ".." in PurePosixPath(subfolder).parts
    ):
        raise ControlError("ComfyUI output metadata is unsafe")
    output_directory, expected_folder, filename_prefix = _savevideo_output_spec(
        workflow, policy
    )
    if (
        pre_submit_snapshot.expected_subfolder != expected_folder
        or pre_submit_snapshot.filename_prefix != filename_prefix
        or pre_submit_snapshot.captured_at_ns > submitted_at_ns
    ):
        raise ControlError("pre-submit SaveVideo snapshot does not bind this submission")
    if subfolder != expected_folder or not _is_exact_savevideo_candidate(
        filename, filename_prefix
    ):
        raise ControlError("ComfyUI output does not match the unchanged R3 SaveVideo prefix")
    relative_posix = (
        PurePosixPath(subfolder) / filename if subfolder else PurePosixPath(filename)
    ).as_posix()
    if relative_posix in pre_submit_snapshot.existing_candidate_paths:
        raise ControlError("ComfyUI history points to an output path that existed before submission")
    source = _require_under(
        output_directory / filename,
        policy.comfyui_root / "output",
        "ComfyUI output",
    )
    _assert_regular_file(source, "ComfyUI output")
    source_info = source.lstat()
    if (
        source_info.st_mtime_ns + OUTPUT_MTIME_GRANULARITY_TOLERANCE_NS
        < submitted_at_ns
    ):
        raise ControlError("ComfyUI history points to an output older than this submission")
    _validate_mp4_header(source)
    return source


def _validate_mp4_header(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        header = os.read(descriptor, 32)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size < 12
        or len(header) < 12
        or header[4:8] != b"ftyp"
        or struct.unpack(">I", header[:4])[0] < 8
    ):
        raise ControlError("ComfyUI output is not an ISO-BMFF MP4")


def _wait_for_unique_output(
    transport: ComfyTransport,
    *,
    prompt_id: str,
    workflow: Mapping[str, Any],
    policy: RunnerPolicy,
    submitted_at_ns: int,
    pre_submit_snapshot: SaveVideoOutputSnapshot,
) -> tuple[Path, str]:
    started = time.monotonic()
    while True:
        if time.monotonic() - started > policy.timeout_seconds:
            raise ControlError("ComfyUI prompt timed out; submission will not be retried")
        history = transport.json(
            "GET", f"/history/{parse.quote(prompt_id, safe='')}"
        )
        entry = history.get(prompt_id)
        if entry is not None and not isinstance(entry, Mapping):
            raise ControlError("ComfyUI history entry is malformed")
        if isinstance(entry, Mapping):
            prompt = entry.get("prompt")
            if (
                not isinstance(prompt, list)
                or len(prompt) < 3
                or prompt[1] != workflow
                or not isinstance(prompt[2], Mapping)
                or prompt[2].get("client_id") != CLIENT_ID
            ):
                raise ControlError("history entry is not bound to the submitted R5 workflow/client")
            status = entry.get("status")
            if isinstance(status, Mapping):
                messages = status.get("messages")
                if isinstance(messages, list) and any(
                    isinstance(row, list)
                    and row
                    and row[0] in {"execution_error", "execution_interrupted"}
                    for row in messages
                ):
                    raise ControlError("ComfyUI reported execution failure; no retry is permitted")
            if not isinstance(status, Mapping) or status.get("completed") is not True:
                time.sleep(policy.poll_seconds)
                continue
            outputs = entry.get("outputs")
            node_output = outputs.get("11") if isinstance(outputs, Mapping) else None
            candidates = _collect_output_candidates(node_output)
            unique = {
                (row["filename"], row["subfolder"], row["type"]): row for row in candidates
            }
            if len(unique) > 1:
                raise ControlError("ComfyUI returned ambiguous node-11 outputs")
            if len(unique) == 1:
                source = _validate_output_candidate(
                    next(iter(unique.values())),
                    workflow,
                    policy,
                    submitted_at_ns,
                    pre_submit_snapshot,
                )
                return source, canonical_sha256(entry)
            raise ControlError("ComfyUI completed without one unique node-11 MP4")
        time.sleep(policy.poll_seconds)


def _stage_variant(prepared: PreparedRun, policy: RunnerPolicy) -> Path:
    input_root = _absolute_lexical(policy.comfyui_root / "input")
    _assert_no_symlink_chain(input_root)
    if not input_root.is_dir():
        raise ControlError("ComfyUI input root is unavailable")
    stage_root = input_root / "k2-002-ep01-i2v-r5-anchor-only"
    _ensure_secure_directory(stage_root)
    destination = stage_root / f"{prepared.variant_anchor_sha256}.png"
    payload = _stable_read(prepared.variant_anchor_path, max_bytes=200_000_000)
    if destination.exists():
        if file_sha256(destination) != prepared.variant_anchor_sha256:
            raise ControlError("existing staged R5 anchor has conflicting bytes")
    else:
        _write_bytes_exclusive(destination, payload)
    if file_sha256(destination) != prepared.variant_anchor_sha256:
        raise ControlError("staged R5 anchor digest changed")
    expected = prepared.variant_workflow.get("12", {}).get("inputs", {}).get("image")
    relative = destination.relative_to(input_root).as_posix()
    if expected != relative:
        raise ControlError("staged image path does not match the validated workflow")
    return destination


def _copy_output_exclusive(source: Path, destination: Path) -> dict[str, Any]:
    _assert_regular_file(source, "ComfyUI output")
    _ensure_secure_directory(destination.parent)
    if destination.exists():
        raise ControlError("R5 evidence video already exists")
    partial = destination.with_name(f".{destination.name}.partial-{os.getpid()}")
    flags_in = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags_in)
    output_fd = None
    digest = sha256()
    total = 0
    try:
        before = os.fstat(source_fd)
        output_fd = os.open(
            partial,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 2_000_000_000:
                raise ControlError("ComfyUI output exceeded 2 GB")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(output_fd, view)
                if written <= 0:
                    raise ControlError("evidence output write made no progress")
                view = view[written:]
        os.fsync(output_fd)
        after = os.fstat(source_fd)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or total != after.st_size
            or total == 0
        ):
            raise ControlError("ComfyUI output changed during evidence copy")
        os.close(output_fd)
        output_fd = None
        try:
            os.link(partial, destination, follow_symlinks=False)
        except FileExistsError as exc:
            raise ControlError("R5 evidence video appeared concurrently") from exc
        _fsync_directory(destination.parent)
        partial.unlink()
        _fsync_directory(destination.parent)
        return {
            "sourcePath": str(source),
            "path": str(destination),
            "sha256": digest.hexdigest(),
            "bytes": total,
        }
    finally:
        os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)
        # A partial file is retained as explicit invalid evidence on failure.


def _load_valid_dry_receipt(policy: RunnerPolicy) -> Mapping[str, Any]:
    path = _dry_receipt_path(policy)
    receipt = load_json_strict(path, "dry-run receipt")
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("experimentId") != EXPERIMENT_ID
        or receipt.get("dryRun") != "PASS"
        or receipt.get("networkCalls") != 0
        or receipt.get("gpuOrProviderCalls") != 0
        or receipt.get("runLockCreated") is not False
        or receipt.get("initialState", {}).get("portInitiallyClosed") is not True
        or receipt.get("initialState", {}).get("gpuComputePids") != []
    ):
        raise ControlError("valid zero-call dry-run receipt is required")
    return receipt


def _contexts_match(first: PreparedRun, second: PreparedRun) -> bool:
    return canonical_sha256(
        {
            "manifest": first.manifest,
            "variant": first.variant_workflow,
            "package": first.baseline_package_snapshot,
            "models": first.model_facts,
            "git": first.git_facts,
            "control": first.control_receipt,
        }
    ) == canonical_sha256(
        {
            "manifest": second.manifest,
            "variant": second.variant_workflow,
            "package": second.baseline_package_snapshot,
            "models": second.model_facts,
            "git": second.git_facts,
            "control": second.control_receipt,
        }
    )


def _validate_attempt_receipt(policy: RunnerPolicy) -> None:
    value = load_json_strict(policy.evidence_root / "RUN_ATTEMPT_1.json", "run attempt")
    if (
        not isinstance(value, Mapping)
        or value.get("experimentId") != EXPERIMENT_ID
        or type(value.get("runNumber")) is not int
        or value.get("runNumber") != 1
        or value.get("state") != "RESERVED_BEFORE_COMFYUI_SUBMIT"
    ):
        raise ControlError("atomic run-attempt receipt changed")


def run_execute(manifest_path: Path, policy: RunnerPolicy = R5_POLICY) -> Mapping[str, Any]:
    dry_receipt = _load_valid_dry_receipt(policy)
    first = _prepare(
        manifest_path=manifest_path,
        policy=policy,
        require_initial_closed=False,
    )
    if (
        dry_receipt.get("manifestSha256") != file_sha256(manifest_path)
        or dry_receipt.get("runnerSha256") != file_sha256(Path(__file__))
        or dry_receipt.get("controlCoreSha256")
        != file_sha256(RUNNER_ROOT / "control_runner_core.py")
        or dry_receipt.get("gates") != dict(first.gates)
        or dry_receipt.get("control") != dict(first.control_receipt)
    ):
        raise ControlError("dry-run receipt no longer binds the fresh R5 control facts")
    materialized_path = _materialized_path(policy)
    materialized = load_json_strict(materialized_path, "dry-run materialized workflow")
    if materialized != first.variant_workflow:
        raise ControlError("dry-run materialized workflow differs from fresh validation")
    if (
        file_sha256(materialized_path)
        != dry_receipt.get("materializedWorkflowFileSha256")
        or canonical_sha256(materialized)
        != dry_receipt.get("materializedWorkflowCanonicalSha256")
    ):
        raise ControlError("dry-run materialized workflow receipt no longer matches")

    lock = RunCountLock(policy.evidence_root)
    reserved = False
    transport: ComfyTransport | None = None
    started_at = utc_now()
    try:
        lock.reserve()
        reserved = True
        _stage_variant(first, policy)

        transport = ComfyTransport(policy.base_url)
        runtime = dict(_verify_live_runtime(transport, policy))
        runtime["initialQueue"] = _verify_queue_empty(transport)

        # Full second pass after staging and reservation closes the file/config
        # TOCTOU window immediately before the sole POST. Any failure consumes
        # the one-run budget but performs no GPU/provider submission.
        second = _prepare(
            manifest_path=manifest_path,
            policy=policy,
            require_initial_closed=False,
            allow_reserved_attempt=True,
        )
        if not _contexts_match(first, second):
            raise ControlError("TOCTOU revalidation facts changed")
        _validate_attempt_receipt(policy)
        if load_json_strict(materialized_path, "materialized workflow") != second.variant_workflow:
            raise ControlError("materialized variant changed after TOCTOU validation")
        staged_path = (
            policy.comfyui_root
            / "input"
            / "k2-002-ep01-i2v-r5-anchor-only"
            / f"{second.variant_anchor_sha256}.png"
        )
        if file_sha256(staged_path) != second.variant_anchor_sha256:
            raise ControlError("staged anchor changed after TOCTOU validation")

        runtime["preSubmitQueue"] = _verify_queue_empty(transport)

        pre_submit_snapshot = _snapshot_savevideo_candidates(
            second.variant_workflow, policy
        )
        runtime["preSubmitOutputSnapshot"] = {
            "saveVideoSubfolder": pre_submit_snapshot.expected_subfolder,
            "filenamePrefix": pre_submit_snapshot.filename_prefix,
            "candidatePathCount": len(pre_submit_snapshot.existing_candidate_paths),
            "candidatePathsSha256": canonical_sha256(
                sorted(pre_submit_snapshot.existing_candidate_paths)
            ),
            "capturedAtNs": pre_submit_snapshot.captured_at_ns,
            "mtimeGranularityToleranceNs": OUTPUT_MTIME_GRANULARITY_TOLERANCE_NS,
        }

        print("START EP01_SH12_R5_ANCHOR_ONLY", flush=True)
        submitted_at_ns = time.time_ns()
        submitted = transport.json(
            "POST",
            "/prompt",
            payload={
                "prompt": second.variant_workflow,
                "client_id": CLIENT_ID,
            },
        )
        prompt_id = submitted.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 200:
            raise ControlError("ComfyUI returned an invalid prompt_id; no retry is permitted")
        source_output, history_sha256 = _wait_for_unique_output(
            transport,
            prompt_id=prompt_id,
            workflow=second.variant_workflow,
            policy=policy,
            submitted_at_ns=submitted_at_ns,
            pre_submit_snapshot=pre_submit_snapshot,
        )
        media_path = policy.evidence_root / "media" / "EP01_SH12_R5_ANCHOR_ONLY.mp4"
        output = _copy_output_exclusive(source_output, media_path)

        package_after = _package_snapshot(policy.package_root)
        if package_after != second.baseline_package_snapshot:
            raise ControlError("baseline package changed after R5 execution")
        if transport.prompt_posts != 1:
            raise ControlError("exactly one /prompt submission was not observed")
        completed_at = utc_now()
        complete = {
            "schemaVersion": 1,
            "session": "COMPLETE",
            "experimentId": EXPERIMENT_ID,
            "experimentValidity": "CONTROLLED_EXECUTION_COMPLETE_PENDING_VISUAL_QC",
            "authorityState": AUTHORITY_STATE,
            "publicationAllowed": False,
            "canonicalMutations": 0,
            "batchAdvanced": False,
            "runCount": 1,
            "startedAt": started_at,
            "completedAt": completed_at,
            "manifestPath": str(_absolute_lexical(manifest_path)),
            "manifestSha256": file_sha256(manifest_path),
            "dryRunReceiptSha256": file_sha256(_dry_receipt_path(policy)),
            "runnerSha256": file_sha256(Path(__file__)),
            "controlCoreSha256": file_sha256(RUNNER_ROOT / "control_runner_core.py"),
            "gates": dict(second.gates),
            "control": dict(second.control_receipt),
            "runtime": runtime,
            "transport": {
                "baseUrl": policy.base_url,
                "promptId": prompt_id,
                "submittedPayloadSha256": canonical_sha256(
                    {"prompt": second.variant_workflow, "client_id": CLIENT_ID}
                ),
                "completedHistoryEntrySha256": history_sha256,
                "promptPostCount": transport.prompt_posts,
                "networkCallCount": transport.network_calls,
                "automaticRetryCount": 0,
            },
            "output": output,
            "postrunBaselinePackageTreeSha256": package_after["treeSha256"],
            "postrunShotsSha256": file_sha256(policy.package_root / "shots.json"),
            "postrunR3WorkflowSha256": file_sha256(
                policy.package_root / "materialized" / "EP01_SH12.workflow.json"
            ),
            "baselineUnchanged": True,
            "gpuOrProviderCalls": 1,
            "visualQc": "NOT_RUN",
        }
        _validate_attempt_receipt(policy)
        lock.complete(complete)
        print("COMPLETE EP01_SH12_R5_ANCHOR_ONLY", flush=True)
        return complete
    except Exception as exc:
        if reserved:
            failure = {
                "schemaVersion": 1,
                "experimentId": EXPERIMENT_ID,
                "state": "FAILED_AFTER_RUN_ATTEMPT_RESERVED",
                "failedAt": utc_now(),
                "errorType": type(exc).__name__,
                "error": str(exc)[:12000],
                "promptPostCount": 0 if transport is None else transport.prompt_posts,
                "networkCallCount": 0 if transport is None else transport.network_calls,
                "automaticRetryCount": 0,
                "gpuOrProviderCalls": 0
                if transport is None or transport.prompt_posts == 0
                else 1,
                "runBudgetConsumed": True,
                "completeReceiptCreated": False,
            }
            try:
                _write_json_exclusive(
                    policy.evidence_root / "FAILED_AFTER_RESERVATION.json", failure
                )
            except ControlError:
                pass
        raise


def _print_gate_receipt(receipt: Mapping[str, Any]) -> None:
    for name, state in receipt.get("gates", {}).items():
        print(f"{name}={state}")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot governed EP01_SH12 R5 anchor-only control runner"
    )
    parser.add_argument("manifest", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.dry_run:
            receipt = run_dry_run(args.manifest, R5_POLICY)
            print("DRY_RUN=PASS")
            print("GPU_OR_PROVIDER_CALLS=0")
            print("RUN_LOCK_CREATED=false")
        else:
            receipt = run_execute(args.manifest, R5_POLICY)
            print("SESSION=COMPLETE")
            print("RUN_COUNT=1")
            print(f"OUTPUT_PATH={receipt['output']['path']}")
            print(f"OUTPUT_SHA256={receipt['output']['sha256']}")
        _print_gate_receipt(receipt)
        print(f"AUTHORITY_STATE={AUTHORITY_STATE}")
        print("PUBLICATION_ALLOWED=false")
        print("CANONICAL_MUTATIONS=0")
        print("BATCH_ADVANCED=false")
        return 0
    except ControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("AUTOMATIC_RETRY_COUNT=0", file=sys.stderr)
        if not (R5_POLICY.evidence_root / "RUN_ATTEMPT_1.json").exists():
            print("GPU_OR_PROVIDER_CALLS=0", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
