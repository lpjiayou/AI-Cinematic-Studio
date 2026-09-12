"""Pure offline source-byte verification. Never extracts or executes archives.

Historical projections use a different schema from runtime attestations. File
hashes, source-preimage hashes and contract hashes are intentionally separate.
"""
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile

from .backend_registry import canonical, digest
from .generation_dispatch_a14b_profile import _require, validate_a14b_models


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON literal: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def archive_bytes(raw, expected_sha256):
    _require(type(raw) is bytes and sha256(raw).hexdigest() == expected_sha256, "archive SHA256 mismatch")
    result, seen, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for entry in archive.infolist():
            name = entry.filename
            parts = PurePosixPath(name).parts
            _require(name and not name.startswith("/") and "\\" not in name and ":" not in name
                and all(p not in {".", ".."} for p in parts)
                and all(ord(c) >= 32 for c in name), "unsafe ZIP member")
            normalized = name.rstrip("/")
            _require(normalized.casefold() not in seen, "duplicate ZIP member")
            seen.add(normalized.casefold())
            mode = entry.external_attr >> 16
            _require(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in {0, stat.S_IFREG, stat.S_IFDIR}, "non-regular ZIP member")
            total += entry.file_size
            _require(total <= 256 * 1024 * 1024 and entry.file_size <= 64 * 1024 * 1024, "archive size bound")
            if not entry.is_dir():
                result[name] = archive.read(entry)  # CRC is checked, no filesystem path is used.
    return result


def verify_hash_list(members):
    _require("SHA256SUMS.txt" in members, "missing source hash list")
    checked = []
    for line in members["SHA256SUMS.txt"].decode("utf-8-sig").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
        _require(match is not None, "invalid source hash list")
        pin, name = match.groups()
        if name.startswith("./"):
            name = name[2:]
        _require(name in members and name not in checked and sha256(members[name]).hexdigest() == pin.lower(), "source member mismatch")
        checked.append(name)
    missing = set(members) - {"SHA256SUMS.txt"} - set(checked)
    # Consolidated originals contain an independently self-excluding runtime
    # hash list. Verify it; never ignore an arbitrary uncovered member.
    for name in missing:
        _require(name.endswith("/SHA256SUMS.txt"), "source hash list coverage incomplete")
        prefix = name[:-len("SHA256SUMS.txt")]
        verify_hash_list({k[len(prefix):]: v for k, v in members.items() if k.startswith(prefix)})
    return checked


def camera_candidate(original, old_sentence, new_sentence):
    _require(old_sentence.startswith("Camera: ") and new_sentence.startswith("Camera: "), "camera delta only")
    positive = original["20"]["inputs"]["text"]
    _require(positive.count(old_sentence) == 1, "camera source sentence mismatch")
    result = deepcopy(original)
    result["20"]["inputs"]["text"] = positive.replace(old_sentence, new_sentence, 1)
    return result


def historical_digest_map(runtime_raw, preimages_raw, models_raw, role_map):
    runtime, preimages, models = map(strict_json, (runtime_raw, preimages_raw, models_raw))
    rows = preimages["STRUCTURED_DIGESTS"]
    for row in rows:
        _require(sha256(row["preimageLiteral"].encode("utf-8")).hexdigest() == row["recordedValue"], "source digest preimage mismatch")
    argv = runtime["CANONICAL_LAUNCH_ARGV"]
    source_launch = sha256("\x1f".join(argv).encode("utf-8")).hexdigest()
    _require(source_launch == runtime["LAUNCH_CONFIG_DIGEST"], "source argv mismatch")
    env_rows = [row for row in rows if row["digest"] == "CANONICAL_ENVIRONMENT_PROJECTION.PROJECTION_DIGEST"]
    _require(len(env_rows) == 1, "environment source preimage missing or ambiguous")
    env_row = env_rows[0]
    env = strict_json(env_row["preimageLiteral"])
    launch = {"argv": argv, "environmentProjection": [{"name": k, "value": env[k]} for k in sorted(env)]}
    ordered = [{k: m[k] for k in ("MODEL_ROLE", "FILE_SHA256", "FILE_SIZE_BYTES")} for m in models["models"]]
    _require(digest(ordered) == models["MODEL_SET_DIGEST"], "source model order/digest mismatch")
    mapped = []
    _require(len(models["models"]) == len(role_map) == 6, "six source model roles required")
    for mapping in role_map:
        matches = [m for m in models["models"] if m["MODEL_ROLE"] == mapping["runtimeManifestRole"]]
        _require(len(matches) == 1, "ambiguous source model role")
        m = matches[0]
        _require(m["FILE_SHA256"] == mapping["sha256"] and m["FILE_SIZE_BYTES"] == mapping["sizeBytesAsRecorded"]
            and PurePosixPath(m["COMFYUI_PATH"]).name == mapping["name"], "source role/size/hash correspondence mismatch")
        mapped.append({"role": mapping["engineeringRole"], "name": mapping["name"],
            "sha256": m["FILE_SHA256"], "sizeBytes": m["FILE_SIZE_BYTES"]})
    validate_a14b_models(mapped)
    return {"schemaVersion": "v4.a14b-historical-source-map.v1", "currentness": "NOT_OBSERVED",
        "modelBytesVerifiedLocally": False, "sourceRuntimeFileSha256": sha256(runtime_raw).hexdigest(),
        "sourceLaunchPreimage": "\x1f".join(argv), "sourceLaunchDigest": source_launch,
        "contractLaunchPreimage": launch, "contractLaunchDigest": digest(launch),
        "sourceModelPreimage": ordered, "sourceModelSetDigest": digest(ordered),
        "contractModelPreimage": mapped, "contractModelSetDigest": digest(mapped),
        "contractSortedModelPreimage": sorted(mapped, key=lambda m: m["role"]),
        "contractSortedModelSetDigest": digest(sorted(mapped, key=lambda m: m["role"])),
        "sourceStructuredDigestsVerified": len(rows), "sourceComfyuiCommit": runtime["COMFYUI_COMMIT"],
        "historicalProcessFields": {k: runtime[k] for k in ("INSTANCE_REF", "HOST_BOOT_ID_DIGEST", "PID_NAMESPACE_ID_DIGEST", "COMFYUI_PID", "PROCESS_START_TICKS")},
        "sourcePythonEnvironment": {k: runtime[k] for k in ("CANONICAL_VENV", "CANONICAL_VENV_NOTE", "CANONICAL_PYTHON")},
        "isRuntimeAttestation": False, "systemRuntimeBound": False, "promptSubmissionAuthorized": False}
