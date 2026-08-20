#!/usr/bin/env python3
"""Validate and archive secret-free K2 ComfyUI runtime evidence.

This tool accepts an already generated technical attestation plus the exact
``system_stats``, ``object_info`` and model-digest files observed on the same
compute host.  It verifies their cross-file facts before creating a deterministic
archive and SHA-256 sidecar.  It does not approve a provider, grant rights, or make
the attestation publishable.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v4_platform.comfyui import (
    COMFYUI_RUNTIME_ATTESTATION_SCHEMA,
    REQUIRED_NODES,
)


EVIDENCE_ARCHIVE_SCHEMA = "v4.comfyui-runtime-evidence-archive.v1"
MAX_INPUT_BYTES = {
    "attestation": 2_000_000,
    "model digests": 128_000,
    "system stats": 8_000_000,
    "object info": 128_000_000,
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FACT_FIELDS = {
    "providerId",
    "modelId",
    "region",
    "endpointClass",
    "comfyuiVersion",
    "pythonVersion",
    "pytorchVersion",
    "deviceName",
    "deviceType",
    "vramTotalBytes",
    "requiredNodes",
    "modelFiles",
    "objectInfoDigest",
    "modelDigestVerification",
}


class EvidenceArchiveError(ValueError):
    """The supplied evidence cannot form a trustworthy archive."""


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise EvidenceArchiveError(f"{field} is invalid")
    return value


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 500
        or any(ord(character) < 32 for character in value)
    ):
        raise EvidenceArchiveError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceArchiveError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise EvidenceArchiveError(f"{field} must include a timezone")
    return text


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceArchiveError("evidence JSON contains duplicate keys")
        result[key] = value
    return result


def _absolute_file(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise EvidenceArchiveError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvidenceArchiveError(f"{label} path is unavailable") from exc
    if not resolved.is_file():
        raise EvidenceArchiveError(f"{label} path is unavailable")
    return resolved


def _read_file(path: Path, label: str) -> bytes:
    resolved = _absolute_file(path, label)
    try:
        size = resolved.stat().st_size
        if size < 1 or size > MAX_INPUT_BYTES[label]:
            raise EvidenceArchiveError(f"{label} size is invalid")
        return resolved.read_bytes()
    except OSError as exc:
        raise EvidenceArchiveError(f"{label} cannot be read") from exc


def _json_object(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceArchiveError(f"{label} is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise EvidenceArchiveError(f"{label} root is invalid")
    return value


def _validate_attestation(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_fields = {
        "schemaVersion",
        "attestationRef",
        "observedAt",
        "factsDigest",
        "facts",
        "authorityState",
        "publicationAllowed",
        "payloadDigest",
    }
    if set(value) != expected_fields:
        raise EvidenceArchiveError("attestation fields are invalid")
    if value["schemaVersion"] != COMFYUI_RUNTIME_ATTESTATION_SCHEMA:
        raise EvidenceArchiveError("attestation schema is invalid")
    _text(value["attestationRef"], "attestationRef")
    _timestamp(value["observedAt"], "observedAt")
    if (
        value["authorityState"] != "TECHNICAL_EVIDENCE_ONLY"
        or value["publicationAllowed"] is not False
    ):
        raise EvidenceArchiveError("attestation authority state is unsafe")
    facts = value["facts"]
    if not isinstance(facts, Mapping):
        raise EvidenceArchiveError("attestation facts are invalid")
    if set(facts) != EXPECTED_FACT_FIELDS:
        raise EvidenceArchiveError("attestation facts fields are invalid")
    if _canonical_digest(facts) != _sha256(value["factsDigest"], "factsDigest"):
        raise EvidenceArchiveError("attestation facts digest does not match")
    unsigned = dict(value)
    payload_digest = _sha256(unsigned.pop("payloadDigest"), "payloadDigest")
    if _canonical_digest(unsigned) != payload_digest:
        raise EvidenceArchiveError("attestation payload digest does not match")
    for field in (
        "providerId",
        "modelId",
        "region",
        "endpointClass",
        "comfyuiVersion",
        "pythonVersion",
        "pytorchVersion",
        "deviceName",
    ):
        _text(facts[field], field)
    if facts["deviceType"] != "cuda":
        raise EvidenceArchiveError("attestation device type is invalid")
    vram_total = facts["vramTotalBytes"]
    if isinstance(vram_total, bool) or not isinstance(vram_total, int) or vram_total <= 0:
        raise EvidenceArchiveError("attestation VRAM facts are invalid")
    if facts["requiredNodes"] != list(REQUIRED_NODES):
        raise EvidenceArchiveError("attestation required nodes are invalid")
    _sha256(facts["objectInfoDigest"], "objectInfoDigest")
    if facts["modelDigestVerification"] != "LOCAL_FILE_SHA256_VERIFIED":
        raise EvidenceArchiveError("model digest verification is incomplete")
    return facts


def _model_files(facts: Mapping[str, Any]) -> dict[str, str]:
    items = facts.get("modelFiles")
    if not isinstance(items, list) or len(items) != 3:
        raise EvidenceArchiveError("attested model files are invalid")
    expected_roles = {"UNET", "TEXT_ENCODER", "VAE"}
    result: dict[str, str] = {}
    roles: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"role", "name", "sha256"}:
            raise EvidenceArchiveError("attested model file is invalid")
        role = _text(item["role"], "model role")
        name = _text(item["name"], "model name")
        if role in roles or name in result:
            raise EvidenceArchiveError("attested model file is duplicated")
        roles.add(role)
        result[name] = _sha256(item["sha256"], "model sha256")
    if roles != expected_roles:
        raise EvidenceArchiveError("attested model roles are invalid")
    return result


def _validate_model_digests(payload: bytes, expected: Mapping[str, str]) -> None:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise EvidenceArchiveError("model digests are not UTF-8") from exc
    observed: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise EvidenceArchiveError("model digest line is invalid")
        digest = _sha256(parts[0], "model digest")
        name = Path(parts[1].strip().lstrip("*")).name
        if not name or name in observed:
            raise EvidenceArchiveError("model digest name is invalid")
        observed[name] = digest
    if observed != dict(expected):
        raise EvidenceArchiveError("model digest file does not match attestation")


def _normalized_model_digests(expected: Mapping[str, str]) -> bytes:
    return "".join(
        f"{digest}  {name}\n" for name, digest in sorted(expected.items())
    ).encode("utf-8")


def _validate_system_stats(
    stats: Mapping[str, Any], facts: Mapping[str, Any]
) -> None:
    system = stats.get("system")
    devices = stats.get("devices")
    if not isinstance(system, Mapping) or not isinstance(devices, list):
        raise EvidenceArchiveError("system stats facts are unavailable")
    expected_system = {
        "comfyui_version": facts.get("comfyuiVersion"),
        "python_version": facts.get("pythonVersion"),
        "pytorch_version": facts.get("pytorchVersion"),
    }
    if any(str(system.get(key, "")) != value for key, value in expected_system.items()):
        raise EvidenceArchiveError("system stats do not match attestation")
    cuda_devices = [
        item
        for item in devices
        if isinstance(item, Mapping) and item.get("type") == "cuda"
    ]
    if len(cuda_devices) != 1:
        raise EvidenceArchiveError("system stats CUDA device count is invalid")
    device = cuda_devices[0]
    vram_total = device.get("vram_total")
    if (
        device.get("name") != facts.get("deviceName")
        or isinstance(vram_total, bool)
        or not isinstance(vram_total, int)
        or vram_total != facts.get("vramTotalBytes")
    ):
        raise EvidenceArchiveError("system stats device does not match attestation")


def _validate_object_info(
    object_info: Mapping[str, Any], facts: Mapping[str, Any]
) -> None:
    expected = _sha256(facts.get("objectInfoDigest"), "objectInfoDigest")
    if _canonical_digest(object_info) != expected:
        raise EvidenceArchiveError("object info digest does not match attestation")
    missing_nodes = [node for node in REQUIRED_NODES if node not in object_info]
    if missing_nodes:
        raise EvidenceArchiveError("object info is missing required nodes")


def _manifest(
    attestation: Mapping[str, Any], files: Mapping[str, bytes]
) -> bytes:
    value = {
        "schemaVersion": EVIDENCE_ARCHIVE_SCHEMA,
        "attestationRef": attestation["attestationRef"],
        "attestationPayloadDigest": attestation["payloadDigest"],
        "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        "publicationAllowed": False,
        "files": {
            name: {"sha256": _digest(payload), "byteSize": len(payload)}
            for name, payload in sorted(files.items())
        },
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode(
        "utf-8"
    ) + b"\n"


def _tar_info(name: str, payload: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o600
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _write_archive(output: Path, files: Mapping[str, bytes]) -> str:
    if not output.is_absolute() or output.name.endswith(".tar.gz") is False:
        raise EvidenceArchiveError("output must be an absolute .tar.gz path")
    sidecar = output.with_name(output.name + ".sha256")
    if output.exists() or sidecar.exists():
        raise EvidenceArchiveError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.tmp-{os.getpid()}")
    sidecar_temporary = sidecar.with_name(f"{sidecar.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w") as archive:
                    for name, payload in sorted(files.items()):
                        archive.addfile(_tar_info(name, payload), io.BytesIO(payload))
        os.chmod(temporary, 0o600)
        archive_digest = _digest(temporary.read_bytes())
        sidecar_temporary.write_text(
            f"{archive_digest}  {output.name}\n", encoding="utf-8"
        )
        os.chmod(sidecar_temporary, 0o600)
        temporary.replace(output)
        sidecar_temporary.replace(sidecar)
        return archive_digest
    except OSError:
        temporary.unlink(missing_ok=True)
        sidecar_temporary.unlink(missing_ok=True)
        raise


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and archive a secret-free K2 ComfyUI technical runtime "
            "attestation without granting production authority."
        )
    )
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--model-digests", type=Path, required=True)
    parser.add_argument("--system-stats", type=Path, required=True)
    parser.add_argument("--object-info", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        attestation_payload = _read_file(args.attestation, "attestation")
        model_digest_payload = _read_file(args.model_digests, "model digests")
        system_stats_payload = _read_file(args.system_stats, "system stats")
        object_info_payload = _read_file(args.object_info, "object info")

        attestation = _json_object(attestation_payload, "attestation")
        facts = _validate_attestation(attestation)
        expected_models = _model_files(facts)
        _validate_model_digests(model_digest_payload, expected_models)
        _validate_system_stats(
            _json_object(system_stats_payload, "system stats"), facts
        )
        _validate_object_info(
            _json_object(object_info_payload, "object info"), facts
        )

        files = {
            "attestation.json": attestation_payload,
            "comfyui-object-info.json": object_info_payload,
            "comfyui-system-stats.json": system_stats_payload,
            "model-files.sha256": _normalized_model_digests(expected_models),
        }
        files["runtime-evidence-manifest.json"] = _manifest(attestation, files)
        archive_digest = _write_archive(args.output, files)
    except (EvidenceArchiveError, OSError) as exc:
        print(f"runtime evidence archive failed: {exc}", file=sys.stderr)
        return 2

    print(f"EVIDENCE_ARCHIVE={args.output}")
    print(f"EVIDENCE_ARCHIVE_SHA256={archive_digest}")
    print(f"ATTESTATION_REF={attestation['attestationRef']}")
    print(f"PAYLOAD_DIGEST={attestation['payloadDigest']}")
    print("AUTHORITY_STATE=TECHNICAL_EVIDENCE_ONLY")
    print("PUBLICATION_ALLOWED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
