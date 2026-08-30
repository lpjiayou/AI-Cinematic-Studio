"""Additive M13 glyph-reveal v2 contracts.

The v1 module remains the historical reader and execution surface.  This module
does not reinterpret or upgrade v1 objects: every v2 parser requires an exact
``.v2`` schema and every v2 builder rejects v1 input.  V5 owns only immutable
requirements, digest-pinned execution projections and candidate result facts;
it does not read media inputs, run FFmpeg, admit an AssetVersion or create a
Timeline authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping, Protocol, Sequence

from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    _digest,
    _required_ref,
)
from .glyph_reveal import (
    BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION,
    GLYPH_MASK_ASSET_ROLE,
    GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION,
    LOCAL_EVIDENCE_PROVENANCE,
    PIXEL_DIGEST_SPEC,
    PIXEL_MODE,
    BasePlateGlyphInspectionRequiredError,
    GlyphRevealArtifactError,
    GlyphRevealError,
    GlyphRevealFrameRangeError,
    GlyphRevealMaskCountError,
    GlyphRevealRequirement,
    ReadableGlyphInBasePlateError,
    _base_plate_asset,
    _frame_rate,
    _glyph_slug,
    _integer,
    _mask_assets,
    _normalize_composite_params,
    _pixel_digest,
    _raw_sha256,
    _sealed,
    _validate_geometry,
    _verify_sealed,
    _video_probe_facts,
)


GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2 = (
    "v5.m13-glyph-reveal-requirement.v2"
)
BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION_V2 = (
    "v5.m13-base-plate-glyph-inspection.v2"
)
GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2 = (
    "v5.m13-glyph-reveal-execution-request.v2"
)
GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2 = (
    "v4.m13-glyph-reveal-artifact-evidence.v2"
)
GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2 = (
    "v5.m13-glyph-reveal-composition-result.v2"
)
BASE_PLATE_GLYPH_INSPECTOR_IDENTITY_V2 = (
    "v4.local-base-plate-glyph-inspector.v2"
)
BASE_PLATE_GLYPH_INSPECTION_METHOD_V2 = (
    "DIGEST_PINNED_FULL_FRAME_GLYPH_READABILITY_INSPECTION_V2"
)
GLYPH_REVEAL_RENDERER_IDENTITY_V2 = (
    "v3.deterministic-glyph-reveal-ffmpeg"
)
GLYPH_REVEAL_RENDERER_VERSION_V2 = "2"
DECODED_FRAME_PIXEL_DIGEST_SPEC_V2 = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)
MAX_GLYPH_INSPECTION_RECORD_BYTES_V2 = 1_048_576
MAX_GLYPH_INSPECTION_SUPPORT_BYTES_V2 = 67_108_864


_SCHEDULE_FIELDS_V2 = frozenset(
    {
        "revealOrdinal",
        "maskAssetVersionRef",
        "startFrameInclusive",
        "endFrameExclusive",
    }
)
_MASK_BINDING_FIELDS_V2 = frozenset(
    {
        "assetVersionRef",
        "assetVersionDigest",
        "fileDigest",
        "pixelDigest",
        "pixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "glyphSlug",
        "revealOrdinal",
        "assetRole",
        "glyphManifestDigest",
    }
)
_REQUIREMENT_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "revealSchedule",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "maskAssetVersionBindings",
        "basePlateInspectionRef",
        "basePlateInspectionDigest",
        "compositeParams",
        "inputBindingsDigest",
        "publicationAllowed",
        "payloadDigest",
    }
)
_REQUIREMENT_COMMAND_FIELDS_V2 = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "revealSchedule",
        "basePlateAssetVersionRef",
        "basePlateInspectionRef",
        "compositeParams",
    }
)
_INSPECTION_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "inspectionRef",
        "inspectorIdentity",
        "inspectionMethod",
        "workspaceRef",
        "productionRunRef",
        "targetShotRef",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "verdict",
        "evidenceRef",
        "evidenceDigest",
        "createdAt",
        "mediaProbe",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_MEDIA_PROBE_FIELDS_V2 = frozenset(
    {"width", "height", "frameCount", "frameRate"}
)
_EXECUTION_REQUEST_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "requirementDigest",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "revealSchedule",
        "inputBindingsDigest",
        "basePlate",
        "masks",
        "basePlateInspectionRef",
        "basePlateInspectionDigest",
        "compositeParams",
        "output",
        "publicationAllowed",
        "payloadDigest",
    }
)
_EXECUTION_BASE_FIELDS_V2 = frozenset(
    {"assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest"}
)
_EXECUTION_MASK_FIELDS_V2 = _MASK_BINDING_FIELDS_V2 | {"storageKey"}
_EXECUTION_OUTPUT_FIELDS_V2 = frozenset(
    {"width", "height", "frameRate", "totalFrames"}
)
_OUTPUT_DIGEST_FIELDS_V2 = frozenset(
    {
        "fileDigest",
        "fileDigestAlgorithm",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "frameCount",
        "frameRate",
    }
)
_ARTIFACT_EVIDENCE_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "artifactEvidenceRef",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "provenance",
        "gpuUsed",
        "publicationAllowed",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "payloadDigest",
    }
)
_RESULT_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "resultRef",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_RESULT_FIELDS_V1 = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "compositionResultRef",
        "requirementRef",
        "requirementDigest",
        "executionRequestDigest",
        "inspectionDigest",
        "artifactEvidenceDigest",
        "inputBindingsDigest",
        "glyphSlug",
        "targetShotRef",
        "basePlateAssetRef",
        "maskAssetRefs",
        "artifactRef",
        "storageKey",
        "byteSize",
        "sha256",
        "outputDigest",
        "composerIdentity",
        "adapterIdentity",
        "runtimeIdentity",
        "ffmpegVersion",
        "ffprobeVersion",
        "provenance",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)


class GlyphRevealScheduleError(GlyphRevealError):
    code = "glyph_reveal_schedule_invalid"


class BasePlateGlyphInspectionEvidenceStore(Protocol):
    """Server-held reader for immutable inspection records and support bytes."""

    def read_inspection(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        inspection_ref: str,
    ) -> Mapping[str, Any] | None: ...

    def read_evidence_bytes(self, *, evidence_ref: str) -> bytes | None: ...


_FILE_STORE_INDEX_ENTRY_FIELDS = frozenset({"storageKey", "fileDigest"})


def _file_store_index_entry(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _FILE_STORE_INDEX_ENTRY_FIELDS:
        raise BasePlateGlyphInspectionRequiredError(f"{field} is invalid")
    try:
        storage_key = _storage_key_v2(value.get("storageKey"), f"{field}.storageKey")
        file_digest = _pixel_digest(value.get("fileDigest"), f"{field}.fileDigest")
    except EpisodeProductionError as exc:
        raise BasePlateGlyphInspectionRequiredError(f"{field} is invalid") from exc
    return {"storageKey": storage_key, "fileDigest": file_digest}


def _json_object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection JSON contains duplicate keys"
            )
        result[key] = value
    return result


class DigestPinnedFileBasePlateGlyphInspectionEvidenceStore:
    """Reread digest-pinned inspection evidence below one server-held root.

    Both indexes are supplied by trusted server configuration at construction;
    request data supplies only refs.  Every read walks the relative POSIX key
    with directory file descriptors and ``O_NOFOLLOW``, then verifies immutable
    file identity before and after the read and matches the configured SHA-256.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        inspection_index: Mapping[
            tuple[str, str, str], Mapping[str, str]
        ],
        evidence_index: Mapping[str, Mapping[str, str]],
    ) -> None:
        candidate = Path(root)
        if not candidate.is_absolute():
            raise BasePlateGlyphInspectionRequiredError(
                "glyph inspection evidence root must be absolute"
            )
        try:
            resolved = candidate.resolve(strict=True)
            root_lstat = candidate.lstat()
        except (OSError, RuntimeError) as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "glyph inspection evidence root is unavailable"
            ) from exc
        if (
            candidate != resolved
            or stat.S_ISLNK(root_lstat.st_mode)
            or not stat.S_ISDIR(root_lstat.st_mode)
        ):
            raise BasePlateGlyphInspectionRequiredError(
                "glyph inspection evidence root is not canonical"
            )
        if not isinstance(inspection_index, Mapping) or not isinstance(
            evidence_index, Mapping
        ):
            raise BasePlateGlyphInspectionRequiredError(
                "glyph inspection evidence indexes are invalid"
            )
        inspections: dict[tuple[str, str, str], dict[str, str]] = {}
        evidence: dict[str, dict[str, str]] = {}
        storage_keys: set[str] = set()
        for raw_key, raw_entry in inspection_index.items():
            if not isinstance(raw_key, tuple) or len(raw_key) != 3:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph inspection index key is invalid"
                )
            try:
                key = tuple(
                    _required_ref(raw_key[index], field)
                    for index, field in enumerate(
                        ("workspaceRef", "productionRunRef", "inspectionRef")
                    )
                )
            except EpisodeProductionError as exc:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph inspection index key is invalid"
                ) from exc
            if key in inspections:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph inspection index key is duplicated"
                )
            entry = _file_store_index_entry(
                raw_entry, f"inspectionIndex[{key[2]}]"
            )
            if entry["storageKey"] in storage_keys:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph inspection index storageKey is duplicated"
                )
            storage_keys.add(entry["storageKey"])
            inspections[key] = entry
        for raw_ref, raw_entry in evidence_index.items():
            try:
                evidence_ref = _required_ref(raw_ref, "evidenceRef")
            except EpisodeProductionError as exc:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph support evidence index key is invalid"
                ) from exc
            if evidence_ref in evidence:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph support evidence index key is duplicated"
                )
            entry = _file_store_index_entry(
                raw_entry, f"evidenceIndex[{evidence_ref}]"
            )
            if entry["storageKey"] in storage_keys:
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph evidence index storageKey is duplicated"
                )
            storage_keys.add(entry["storageKey"])
            evidence[evidence_ref] = entry
        self._root = resolved
        self._root_identity = (
            root_lstat.st_dev,
            root_lstat.st_ino,
            stat.S_IFMT(root_lstat.st_mode),
        )
        self._inspection_index = inspections
        self._evidence_index = evidence

    @staticmethod
    def _directory_open_flags() -> int:
        return (
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )

    @staticmethod
    def _leaf_open_flags() -> int:
        return (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )

    @staticmethod
    def _file_state(
        value: os.stat_result,
    ) -> tuple[int, int, int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    def _read_indexed_bytes(
        self,
        entry: Mapping[str, str],
        *,
        maximum_bytes: int,
        label: str,
    ) -> bytes:
        storage_key = entry["storageKey"]
        parts = PurePosixPath(storage_key).parts
        descriptors: list[int] = []
        try:
            root_descriptor = os.open(
                self._root, self._directory_open_flags()
            )
            descriptors.append(root_descriptor)
            root_state = os.fstat(root_descriptor)
            if (
                not stat.S_ISDIR(root_state.st_mode)
                or (
                    root_state.st_dev,
                    root_state.st_ino,
                    stat.S_IFMT(root_state.st_mode),
                )
                != self._root_identity
            ):
                raise BasePlateGlyphInspectionRequiredError(
                    "glyph inspection evidence root identity changed"
                )
            current_descriptor = root_descriptor
            for part in parts[:-1]:
                next_descriptor = os.open(
                    part,
                    self._directory_open_flags(),
                    dir_fd=current_descriptor,
                )
                descriptors.append(next_descriptor)
                directory_state = os.fstat(next_descriptor)
                if not stat.S_ISDIR(directory_state.st_mode):
                    raise BasePlateGlyphInspectionRequiredError(
                        f"{label} directory is invalid"
                    )
                current_descriptor = next_descriptor
            leaf_descriptor = os.open(
                parts[-1],
                self._leaf_open_flags(),
                dir_fd=current_descriptor,
            )
            descriptors.append(leaf_descriptor)
            before = os.fstat(leaf_descriptor)
            path_before = os.stat(
                parts[-1],
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(before.st_mode)
                or (before.st_dev, before.st_ino)
                != (path_before.st_dev, path_before.st_ino)
                or before.st_size < 1
                or before.st_size > maximum_bytes
            ):
                raise BasePlateGlyphInspectionRequiredError(
                    f"{label} file contract is invalid"
                )
            chunks: list[bytes] = []
            remaining = before.st_size
            digest = sha256()
            while remaining:
                chunk = os.read(leaf_descriptor, min(1_048_576, remaining))
                if not chunk:
                    raise BasePlateGlyphInspectionRequiredError(
                        f"{label} changed while being read"
                    )
                chunks.append(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            if os.read(leaf_descriptor, 1):
                raise BasePlateGlyphInspectionRequiredError(
                    f"{label} changed while being read"
                )
            after = os.fstat(leaf_descriptor)
            path_after = os.stat(
                parts[-1],
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            if (
                self._file_state(before) != self._file_state(after)
                or self._file_state(after) != self._file_state(path_after)
            ):
                raise BasePlateGlyphInspectionRequiredError(
                    f"{label} changed while being read"
                )
            payload = b"".join(chunks)
            if len(payload) != before.st_size:
                raise BasePlateGlyphInspectionRequiredError(
                    f"{label} byte size changed"
                )
            if "sha256:" + digest.hexdigest() != entry["fileDigest"]:
                raise StaleInputError(f"{label} file digest changed")
            return payload
        except EpisodeProductionError:
            raise
        except OSError as exc:
            raise BasePlateGlyphInspectionRequiredError(
                f"{label} is unavailable"
            ) from exc
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def read_inspection(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        inspection_ref: str,
    ) -> Mapping[str, Any] | None:
        try:
            key = (
                _required_ref(workspace_ref, "workspaceRef"),
                _required_ref(production_run_ref, "productionRunRef"),
                _required_ref(inspection_ref, "inspectionRef"),
            )
        except EpisodeProductionError as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "glyph inspection evidence lookup is invalid"
            ) from exc
        entry = self._inspection_index.get(key)
        if entry is None:
            return None
        payload = self._read_indexed_bytes(
            entry,
            maximum_bytes=MAX_GLYPH_INSPECTION_RECORD_BYTES_V2,
            label="base plate glyph inspection record",
        )
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_json_object_without_duplicate_keys,
            )
        except BasePlateGlyphInspectionRequiredError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection record is not valid JSON"
            ) from exc
        if not isinstance(value, Mapping):
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection record must be an object"
            )
        return deepcopy(dict(value))

    def read_evidence_bytes(self, *, evidence_ref: str) -> bytes | None:
        try:
            ref = _required_ref(evidence_ref, "evidenceRef")
        except EpisodeProductionError as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "glyph support evidence lookup is invalid"
            ) from exc
        entry = self._evidence_index.get(ref)
        if entry is None:
            return None
        return self._read_indexed_bytes(
            entry,
            maximum_bytes=MAX_GLYPH_INSPECTION_SUPPORT_BYTES_V2,
            label="base plate glyph inspection support evidence",
        )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GlyphRevealError("value is not canonical JSON") from exc


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BasePlateGlyphInspectionRequiredError(f"{field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BasePlateGlyphInspectionRequiredError(f"{field} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BasePlateGlyphInspectionRequiredError(f"{field} is invalid")
    return value


def _text_identity(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 500
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise GlyphRevealArtifactError(f"{field} is invalid")
    return value


def _storage_key_v2(value: Any, field: str) -> str:
    """Validate one canonical relative POSIX key without lexical collapse."""

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise GlyphRevealArtifactError(f"{field} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise GlyphRevealArtifactError(f"{field} is invalid")
    return value


def _frame_interval_v2(start_value: Any, end_value: Any) -> tuple[int, int]:
    start = _integer(
        start_value,
        "frameRangeStartInclusive",
        minimum=0,
        maximum=10_000_000,
        error_type=GlyphRevealFrameRangeError,
    )
    end = _integer(
        end_value,
        "frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
        error_type=GlyphRevealFrameRangeError,
    )
    if end <= start:
        raise GlyphRevealFrameRangeError("glyph reveal frame interval is empty")
    return start, end


def _normalize_schedule_v2(
    value: Any,
    *,
    range_start: int,
    range_end: int,
    expected_mask_refs: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or len(value) > 1_024
    ):
        raise GlyphRevealScheduleError("revealSchedule is invalid")
    if expected_mask_refs is not None and len(value) != len(expected_mask_refs):
        raise GlyphRevealMaskCountError(
            "revealSchedule count does not match mask binding count"
        )
    normalized: list[dict[str, Any]] = []
    previous_end = range_start
    seen_refs: set[str] = set()
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, Mapping) or set(raw) != _SCHEDULE_FIELDS_V2:
            raise GlyphRevealScheduleError(
                f"revealSchedule[{index - 1}] fields are invalid"
            )
        ordinal = _integer(
            raw.get("revealOrdinal"),
            f"revealSchedule[{index - 1}].revealOrdinal",
            minimum=1,
            maximum=1_024,
            error_type=GlyphRevealScheduleError,
        )
        if ordinal != index:
            raise GlyphRevealScheduleError(
                "revealSchedule ordinals must be continuous from one"
            )
        mask_ref = _required_ref(
            raw.get("maskAssetVersionRef"),
            f"revealSchedule[{index - 1}].maskAssetVersionRef",
        )
        if mask_ref in seen_refs:
            raise GlyphRevealMaskCountError(
                "revealSchedule mask AssetVersion refs must be unique"
            )
        seen_refs.add(mask_ref)
        start = _integer(
            raw.get("startFrameInclusive"),
            f"revealSchedule[{index - 1}].startFrameInclusive",
            minimum=0,
            maximum=10_000_000,
            error_type=GlyphRevealScheduleError,
        )
        end = _integer(
            raw.get("endFrameExclusive"),
            f"revealSchedule[{index - 1}].endFrameExclusive",
            minimum=1,
            maximum=10_000_001,
            error_type=GlyphRevealScheduleError,
        )
        if start != previous_end:
            raise GlyphRevealScheduleError(
                "revealSchedule must cover the interval without gaps or overlap"
            )
        if end <= start or start < range_start or end > range_end:
            raise GlyphRevealScheduleError(
                "revealSchedule contains an empty or out-of-range interval"
            )
        if expected_mask_refs is not None and mask_ref != expected_mask_refs[index - 1]:
            raise GlyphRevealScheduleError(
                "revealSchedule mask order is stale"
            )
        normalized.append(
            {
                "revealOrdinal": ordinal,
                "maskAssetVersionRef": mask_ref,
                "startFrameInclusive": start,
                "endFrameExclusive": end,
            }
        )
        previous_end = end
    if previous_end != range_end:
        raise GlyphRevealScheduleError(
            "revealSchedule does not completely cover the reveal interval"
        )
    return normalized


def _mask_bindings_from_assets_v2(
    mask_assets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "assetVersionRef": mask["assetVersionRef"],
            "assetVersionDigest": mask["payloadDigest"],
            "fileDigest": f"sha256:{mask['sha256']}",
            "pixelDigest": mask["pixelDigest"],
            "pixelDigestSpec": mask["pixelDigestSpec"],
            "pixelMode": mask["pixelMode"],
            "width": mask["width"],
            "height": mask["height"],
            "glyphSlug": mask["glyphSlug"],
            "revealOrdinal": mask["revealOrdinal"],
            "assetRole": mask["assetRole"],
            "glyphManifestDigest": mask["glyphManifestDigest"],
        }
        for mask in mask_assets
    ]


def _normalize_mask_bindings_v2(
    value: Any,
    *,
    glyph_slug: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or len(value) > 1_024
    ):
        raise GlyphRevealMaskCountError("maskAssetVersionBindings is invalid")
    result: list[dict[str, Any]] = []
    refs: set[str] = set()
    pixels: set[str] = set()
    manifest_digest: str | None = None
    dimensions: tuple[int, int, str, str] | None = None
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, Mapping) or set(raw) != _MASK_BINDING_FIELDS_V2:
            raise GlyphRevealMaskCountError(
                f"maskAssetVersionBindings[{index - 1}] fields are invalid"
            )
        current = deepcopy(dict(raw))
        ref = _required_ref(
            current.get("assetVersionRef"),
            f"maskAssetVersionBindings[{index - 1}].assetVersionRef",
        )
        if ref in refs:
            raise GlyphRevealMaskCountError(
                "mask AssetVersion bindings must be unique"
            )
        refs.add(ref)
        _raw_sha256(
            current.get("assetVersionDigest"),
            f"maskAssetVersionBindings[{index - 1}].assetVersionDigest",
        )
        _pixel_digest(
            current.get("fileDigest"),
            f"maskAssetVersionBindings[{index - 1}].fileDigest",
        )
        pixel = _pixel_digest(
            current.get("pixelDigest"),
            f"maskAssetVersionBindings[{index - 1}].pixelDigest",
        )
        if pixel in pixels:
            raise StaleInputError(
                "cumulative mask stages must have unique decoded pixels"
            )
        pixels.add(pixel)
        width = _integer(
            current.get("width"),
            f"maskAssetVersionBindings[{index - 1}].width",
            minimum=1,
            maximum=131_072,
        )
        height = _integer(
            current.get("height"),
            f"maskAssetVersionBindings[{index - 1}].height",
            minimum=1,
            maximum=131_072,
        )
        if (
            current.get("pixelDigestSpec") != PIXEL_DIGEST_SPEC
            or current.get("pixelMode") != PIXEL_MODE
            or current.get("glyphSlug") != glyph_slug
            or current.get("revealOrdinal") != index
            or current.get("assetRole") != GLYPH_MASK_ASSET_ROLE
        ):
            raise StaleInputError(
                "mask AssetVersion cumulative-stage binding is stale"
            )
        current_manifest = _pixel_digest(
            current.get("glyphManifestDigest"),
            f"maskAssetVersionBindings[{index - 1}].glyphManifestDigest",
        )
        if manifest_digest is None:
            manifest_digest = current_manifest
        elif current_manifest != manifest_digest:
            raise StaleInputError("mask AssetVersion glyph manifests disagree")
        current_dimensions = (
            width,
            height,
            current["pixelDigestSpec"],
            current["pixelMode"],
        )
        if dimensions is None:
            dimensions = current_dimensions
        elif current_dimensions != dimensions:
            raise GlyphRevealError("mask AssetVersion pixel contracts disagree")
        result.append(current)
    return result


def _base_binding_v2(base_plate_asset: Mapping[str, Any]) -> dict[str, str]:
    return {
        "assetVersionRef": str(base_plate_asset["assetVersionRef"]),
        "assetVersionDigest": str(base_plate_asset["payloadDigest"]),
        "fileDigest": f"sha256:{base_plate_asset['sha256']}",
    }


def _input_bindings_payload_v2(
    *,
    base_plate_asset_version_ref: str,
    base_plate_asset_version_digest: str,
    base_plate_file_digest: str,
    mask_bindings: Sequence[Mapping[str, Any]],
    inspection_ref: str,
    inspection_digest: str,
) -> dict[str, Any]:
    return {
        "basePlate": {
            "assetVersionRef": base_plate_asset_version_ref,
            "assetVersionDigest": base_plate_asset_version_digest,
            "fileDigest": base_plate_file_digest,
        },
        "masks": [deepcopy(dict(binding)) for binding in mask_bindings],
        "basePlateInspection": {
            "inspectionRef": inspection_ref,
            "inspectionDigest": inspection_digest,
        },
    }


def _expected_execution_request_ref_v2(requirement: "GlyphRevealRequirementV2") -> str:
    identity = {
        "requirementRef": requirement.requirement_ref,
        "requirementDigest": requirement.payload_digest,
        "inputBindingsDigest": requirement.input_bindings_digest,
        "basePlateInspectionDigest": requirement.base_plate_inspection_digest,
    }
    return "m13-glyph-reveal-execution-" + _digest(identity)[:32]


def expected_glyph_reveal_output_storage_key_v2(
    workspace_ref: str,
    production_run_ref: str,
    execution_request_digest: str,
) -> str:
    """Return the exact V3 workspace/run-scoped candidate storage key."""

    workspace = _required_ref(workspace_ref, "workspaceRef")
    run = _required_ref(production_run_ref, "productionRunRef")
    digest = _raw_sha256(execution_request_digest, "executionRequestDigest")
    workspace_scope = sha256(workspace.encode("utf-8")).hexdigest()[:20]
    run_scope = sha256(run.encode("utf-8")).hexdigest()[:20]
    return str(
        PurePosixPath(
            workspace_scope,
            run_scope,
            "glyph-reveal",
            f"glyph-reveal-{digest}.mp4",
        )
    )


def _runtime_evidence_digest_v2(
    *, renderer_identity: str, renderer_version: str, ffmpeg_identity: str
) -> str:
    payload = json.dumps(
        {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": renderer_identity,
            "rendererVersion": renderer_version,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


class DigestPinnedBasePlateGlyphInspectionAdapter:
    """Resolve no-glyph facts only from a server-held, rereadable store."""

    def __init__(self, store: BasePlateGlyphInspectionEvidenceStore) -> None:
        if (
            store is None
            or not callable(getattr(store, "read_inspection", None))
            or not callable(getattr(store, "read_evidence_bytes", None))
        ):
            raise BasePlateGlyphInspectionRequiredError(
                "server-held glyph inspection evidence store is required"
            )
        self._store = store

    def resolve_inspection(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        target_shot_ref: str,
        base_plate_asset: Mapping[str, Any],
        inspection_ref: str,
        expected_payload_digest: str | None = None,
    ) -> tuple[dict[str, Any], tuple[int, int, int, int]]:
        inspection_ref = _required_ref(inspection_ref, "basePlateInspectionRef")
        if expected_payload_digest is not None:
            _raw_sha256(expected_payload_digest, "basePlateInspectionDigest")
        try:
            raw = self._store.read_inspection(
                workspace_ref=workspace_ref,
                production_run_ref=production_run_ref,
                inspection_ref=inspection_ref,
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection evidence cannot be reread"
            ) from exc
        if raw is None:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection evidence is missing"
            )
        try:
            evidence = _verify_sealed(raw, "basePlateGlyphInspectionV2")
        except EpisodeProductionError as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection evidence seal is invalid"
            ) from exc
        if set(evidence) != _INSPECTION_FIELDS_V2:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection evidence fields are invalid"
            )
        if (
            evidence.get("schemaVersion")
            != BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION_V2
            or evidence.get("inspectionRef") != inspection_ref
            or evidence.get("inspectorIdentity")
            != BASE_PLATE_GLYPH_INSPECTOR_IDENTITY_V2
            or evidence.get("inspectionMethod")
            != BASE_PLATE_GLYPH_INSPECTION_METHOD_V2
            or evidence.get("provenance") != LOCAL_EVIDENCE_PROVENANCE
            or evidence.get("publicationAllowed") is not False
        ):
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection evidence is unsupported"
            )
        _timestamp(evidence.get("createdAt"), "basePlateGlyphInspection.createdAt")
        evidence_ref = _required_ref(
            evidence.get("evidenceRef"), "basePlateGlyphInspection.evidenceRef"
        )
        evidence_digest = _pixel_digest(
            evidence.get("evidenceDigest"),
            "basePlateGlyphInspection.evidenceDigest",
        )
        _raw_sha256(
            evidence.get("basePlateAssetVersionDigest"),
            "basePlateGlyphInspection.basePlateAssetVersionDigest",
        )
        _pixel_digest(
            evidence.get("basePlateFileDigest"),
            "basePlateGlyphInspection.basePlateFileDigest",
        )
        if (
            evidence.get("workspaceRef") != workspace_ref
            or evidence.get("productionRunRef") != production_run_ref
            or evidence.get("targetShotRef") != target_shot_ref
            or evidence.get("basePlateAssetVersionRef")
            != base_plate_asset.get("assetVersionRef")
            or evidence.get("basePlateAssetVersionDigest")
            != base_plate_asset.get("payloadDigest")
            or evidence.get("basePlateFileDigest")
            != f"sha256:{base_plate_asset.get('sha256')}"
        ):
            raise StaleInputError(
                "base plate glyph inspection subject binding is stale"
            )
        if (
            expected_payload_digest is not None
            and evidence.get("payloadDigest") != expected_payload_digest
        ):
            raise StaleInputError(
                "base plate glyph inspection evidence was replaced"
            )
        try:
            support = self._store.read_evidence_bytes(evidence_ref=evidence_ref)
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection support evidence cannot be reread"
            ) from exc
        if (
            not isinstance(support, bytes)
            or not support
            or len(support) > 64 * 1024 * 1024
        ):
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection support evidence is unavailable"
            )
        actual_support_digest = "sha256:" + sha256(support).hexdigest()
        if actual_support_digest != evidence_digest:
            raise StaleInputError(
                "base plate glyph inspection support evidence digest changed"
            )
        verdict = evidence.get("verdict")
        if verdict == "READABLE_GLYPH_PRESENT":
            raise ReadableGlyphInBasePlateError(
                "base plate already contains a readable glyph"
            )
        if verdict != "NO_READABLE_GLYPH":
            raise BasePlateGlyphInspectionRequiredError(
                "base plate has no conclusive no-glyph inspection"
            )
        probe = evidence.get("mediaProbe")
        if not isinstance(probe, Mapping) or set(probe) != _MEDIA_PROBE_FIELDS_V2:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection mediaProbe is invalid"
            )
        try:
            dimensions = _video_probe_facts(
                probe, field="basePlateGlyphInspectionV2.mediaProbe"
            )
        except GlyphRevealError as exc:
            raise BasePlateGlyphInspectionRequiredError(
                "base plate glyph inspection mediaProbe is invalid"
            ) from exc
        if "probe" in base_plate_asset:
            base_dimensions = _video_probe_facts(
                base_plate_asset.get("probe"), field="basePlateAsset.probe"
            )
            if base_dimensions != dimensions:
                raise StaleInputError(
                    "base plate glyph inspection mediaProbe is stale"
                )
        return evidence, dimensions


@dataclass(frozen=True, slots=True)
class GlyphRevealRequirementV2:
    workspace_ref: str
    production_run_ref: str
    requirement_ref: str
    glyph_slug: str
    target_shot_ref: str
    frame_range_start_inclusive: int
    frame_range_end_exclusive: int
    _reveal_schedule_json: str
    base_plate_asset_version_ref: str
    base_plate_asset_version_digest: str
    base_plate_file_digest: str
    _mask_bindings_json: str
    base_plate_inspection_ref: str
    base_plate_inspection_digest: str
    _composite_params_json: str
    input_bindings_digest: str
    payload_digest: str

    @property
    def reveal_schedule(self) -> list[dict[str, Any]]:
        return json.loads(self._reveal_schedule_json)

    @property
    def mask_asset_version_bindings(self) -> list[dict[str, Any]]:
        return json.loads(self._mask_bindings_json)

    @property
    def composite_params(self) -> dict[str, Any]:
        return json.loads(self._composite_params_json)

    @property
    def reveal_frame_count(self) -> int:
        return len(self.reveal_schedule)

    @property
    def mask_asset_version_refs(self) -> tuple[str, ...]:
        return tuple(
            binding["assetVersionRef"]
            for binding in self.mask_asset_version_bindings
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GlyphRevealRequirementV2":
        requirement = _verify_sealed(value, "GlyphRevealRequirementV2")
        if (
            set(requirement) != _REQUIREMENT_FIELDS_V2
            or requirement.get("schemaVersion")
            != GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2
            or requirement.get("publicationAllowed") is not False
        ):
            raise GlyphRevealError("GlyphRevealRequirementV2 fields are invalid")
        workspace_ref = _required_ref(requirement.get("workspaceRef"), "workspaceRef")
        production_run_ref = _required_ref(
            requirement.get("productionRunRef"), "productionRunRef"
        )
        requirement_ref = _required_ref(
            requirement.get("requirementRef"), "requirementRef"
        )
        glyph_slug = _glyph_slug(requirement.get("glyphSlug"))
        target_shot_ref = _required_ref(
            requirement.get("targetShotRef"), "targetShotRef"
        )
        start, end = _frame_interval_v2(
            requirement.get("frameRangeStartInclusive"),
            requirement.get("frameRangeEndExclusive"),
        )
        base_ref = _required_ref(
            requirement.get("basePlateAssetVersionRef"),
            "basePlateAssetVersionRef",
        )
        base_digest = _raw_sha256(
            requirement.get("basePlateAssetVersionDigest"),
            "basePlateAssetVersionDigest",
        )
        base_file_digest = _pixel_digest(
            requirement.get("basePlateFileDigest"), "basePlateFileDigest"
        )
        mask_bindings = _normalize_mask_bindings_v2(
            requirement.get("maskAssetVersionBindings"), glyph_slug=glyph_slug
        )
        mask_refs = [binding["assetVersionRef"] for binding in mask_bindings]
        if base_ref in mask_refs:
            raise GlyphRevealError(
                "basePlateAssetVersionRef cannot also be a mask"
            )
        schedule = _normalize_schedule_v2(
            requirement.get("revealSchedule"),
            range_start=start,
            range_end=end,
            expected_mask_refs=mask_refs,
        )
        inspection_ref = _required_ref(
            requirement.get("basePlateInspectionRef"), "basePlateInspectionRef"
        )
        inspection_digest = _raw_sha256(
            requirement.get("basePlateInspectionDigest"),
            "basePlateInspectionDigest",
        )
        params = _normalize_composite_params(requirement.get("compositeParams"))
        input_digest = _raw_sha256(
            requirement.get("inputBindingsDigest"), "inputBindingsDigest"
        )
        binding_payload = _input_bindings_payload_v2(
            base_plate_asset_version_ref=base_ref,
            base_plate_asset_version_digest=base_digest,
            base_plate_file_digest=base_file_digest,
            mask_bindings=mask_bindings,
            inspection_ref=inspection_ref,
            inspection_digest=inspection_digest,
        )
        if input_digest != _digest(binding_payload):
            raise StaleInputError(
                "GlyphRevealRequirementV2 inputBindingsDigest is invalid"
            )
        return cls(
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            requirement_ref=requirement_ref,
            glyph_slug=glyph_slug,
            target_shot_ref=target_shot_ref,
            frame_range_start_inclusive=start,
            frame_range_end_exclusive=end,
            _reveal_schedule_json=_canonical_json(schedule),
            base_plate_asset_version_ref=base_ref,
            base_plate_asset_version_digest=base_digest,
            base_plate_file_digest=base_file_digest,
            _mask_bindings_json=_canonical_json(mask_bindings),
            base_plate_inspection_ref=inspection_ref,
            base_plate_inspection_digest=inspection_digest,
            _composite_params_json=_canonical_json(params),
            input_bindings_digest=input_digest,
            payload_digest=requirement["payloadDigest"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2,
            "workspaceRef": self.workspace_ref,
            "productionRunRef": self.production_run_ref,
            "requirementRef": self.requirement_ref,
            "glyphSlug": self.glyph_slug,
            "targetShotRef": self.target_shot_ref,
            "frameRangeStartInclusive": self.frame_range_start_inclusive,
            "frameRangeEndExclusive": self.frame_range_end_exclusive,
            "revealSchedule": self.reveal_schedule,
            "basePlateAssetVersionRef": self.base_plate_asset_version_ref,
            "basePlateAssetVersionDigest": self.base_plate_asset_version_digest,
            "basePlateFileDigest": self.base_plate_file_digest,
            "maskAssetVersionBindings": self.mask_asset_version_bindings,
            "basePlateInspectionRef": self.base_plate_inspection_ref,
            "basePlateInspectionDigest": self.base_plate_inspection_digest,
            "compositeParams": self.composite_params,
            "inputBindingsDigest": self.input_bindings_digest,
            "publicationAllowed": False,
            "payloadDigest": self.payload_digest,
        }


def read_glyph_reveal_requirement(
    value: GlyphRevealRequirement | GlyphRevealRequirementV2 | Mapping[str, Any],
) -> GlyphRevealRequirement | GlyphRevealRequirementV2:
    """Read an exact historical v1 or exact v2 object without conversion."""

    if isinstance(value, GlyphRevealRequirement):
        return GlyphRevealRequirement.from_mapping(value.as_dict())
    if isinstance(value, GlyphRevealRequirementV2):
        return GlyphRevealRequirementV2.from_mapping(value.as_dict())
    if not isinstance(value, Mapping):
        raise GlyphRevealError("GlyphRevealRequirement must be an object")
    schema = value.get("schemaVersion")
    if schema == BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION:
        raise GlyphRevealError("inspection evidence is not a requirement")
    if schema == GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2:
        return GlyphRevealRequirementV2.from_mapping(value)
    # The historical class owns the exact v1 schema check and field semantics.
    return GlyphRevealRequirement.from_mapping(value)


def _requirement_v2_value(
    value: GlyphRevealRequirementV2 | Mapping[str, Any],
) -> GlyphRevealRequirementV2:
    if isinstance(value, GlyphRevealRequirementV2):
        return GlyphRevealRequirementV2.from_mapping(value.as_dict())
    if isinstance(value, GlyphRevealRequirement):
        raise GlyphRevealError("v1 GlyphRevealRequirement cannot execute as v2")
    if not isinstance(value, Mapping) or value.get(
        "schemaVersion"
    ) != GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2:
        raise GlyphRevealError("v2 GlyphRevealRequirement is required")
    return GlyphRevealRequirementV2.from_mapping(value)


def build_glyph_reveal_requirement_v2(
    command: Mapping[str, Any],
    *,
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_adapter: DigestPinnedBasePlateGlyphInspectionAdapter,
) -> GlyphRevealRequirementV2:
    if (
        not isinstance(command, Mapping)
        or set(command) != _REQUIREMENT_COMMAND_FIELDS_V2
    ):
        raise GlyphRevealError(
            "glyph reveal v2 requirement command fields are invalid"
        )
    if not isinstance(inspection_adapter, DigestPinnedBasePlateGlyphInspectionAdapter):
        raise BasePlateGlyphInspectionRequiredError(
            "server-held glyph inspection adapter is required"
        )
    workspace_ref = _required_ref(command.get("workspaceRef"), "workspaceRef")
    production_run_ref = _required_ref(
        command.get("productionRunRef"), "productionRunRef"
    )
    requirement_ref = _required_ref(command.get("requirementRef"), "requirementRef")
    target_shot_ref = _required_ref(command.get("targetShotRef"), "targetShotRef")
    glyph_slug = _glyph_slug(command.get("glyphSlug"))
    start, end = _frame_interval_v2(
        command.get("frameRangeStartInclusive"),
        command.get("frameRangeEndExclusive"),
    )
    preliminary_schedule = _normalize_schedule_v2(
        command.get("revealSchedule"), range_start=start, range_end=end
    )
    expected_mask_refs = [
        entry["maskAssetVersionRef"] for entry in preliminary_schedule
    ]
    base_ref = _required_ref(
        command.get("basePlateAssetVersionRef"), "basePlateAssetVersionRef"
    )
    inspection_ref = _required_ref(
        command.get("basePlateInspectionRef"), "basePlateInspectionRef"
    )
    params = _normalize_composite_params(command.get("compositeParams"))
    base = _base_plate_asset(
        base_plate_asset,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        target_shot_ref=target_shot_ref,
    )
    if base["assetVersionRef"] != base_ref:
        raise StaleInputError("basePlateAssetVersionRef binding is stale")
    masks = _mask_assets(
        mask_assets,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        glyph_slug=glyph_slug,
        expected_refs=expected_mask_refs,
    )
    mask_bindings = _normalize_mask_bindings_v2(
        _mask_bindings_from_assets_v2(masks), glyph_slug=glyph_slug
    )
    schedule = _normalize_schedule_v2(
        preliminary_schedule,
        range_start=start,
        range_end=end,
        expected_mask_refs=[binding["assetVersionRef"] for binding in mask_bindings],
    )
    inspection, dimensions = inspection_adapter.resolve_inspection(
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        target_shot_ref=target_shot_ref,
        base_plate_asset=base,
        inspection_ref=inspection_ref,
    )
    if dimensions[2] < end:
        raise GlyphRevealFrameRangeError(
            "frameRangeEndExclusive exceeds the base plate frameCount"
        )
    _validate_geometry(
        params, base_width=dimensions[0], base_height=dimensions[1]
    )
    base_binding = _base_binding_v2(base)
    binding_payload = _input_bindings_payload_v2(
        base_plate_asset_version_ref=base_binding["assetVersionRef"],
        base_plate_asset_version_digest=base_binding["assetVersionDigest"],
        base_plate_file_digest=base_binding["fileDigest"],
        mask_bindings=mask_bindings,
        inspection_ref=inspection["inspectionRef"],
        inspection_digest=inspection["payloadDigest"],
    )
    unsigned = {
        "schemaVersion": GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2,
        "workspaceRef": workspace_ref,
        "productionRunRef": production_run_ref,
        "requirementRef": requirement_ref,
        "glyphSlug": glyph_slug,
        "targetShotRef": target_shot_ref,
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "revealSchedule": schedule,
        "basePlateAssetVersionRef": base_binding["assetVersionRef"],
        "basePlateAssetVersionDigest": base_binding["assetVersionDigest"],
        "basePlateFileDigest": base_binding["fileDigest"],
        "maskAssetVersionBindings": mask_bindings,
        "basePlateInspectionRef": inspection["inspectionRef"],
        "basePlateInspectionDigest": inspection["payloadDigest"],
        "compositeParams": params,
        "inputBindingsDigest": _digest(binding_payload),
        "publicationAllowed": False,
    }
    return GlyphRevealRequirementV2.from_mapping(_sealed(unsigned))


def _validate_current_bindings_v2(
    requirement: GlyphRevealRequirementV2,
    *,
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_adapter: DigestPinnedBasePlateGlyphInspectionAdapter,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    tuple[int, int, int, int],
]:
    if not isinstance(inspection_adapter, DigestPinnedBasePlateGlyphInspectionAdapter):
        raise BasePlateGlyphInspectionRequiredError(
            "server-held glyph inspection adapter is required"
        )
    base = _base_plate_asset(
        base_plate_asset,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        target_shot_ref=requirement.target_shot_ref,
    )
    masks = _mask_assets(
        mask_assets,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        glyph_slug=requirement.glyph_slug,
        expected_refs=requirement.mask_asset_version_refs,
    )
    inspection, dimensions = inspection_adapter.resolve_inspection(
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        target_shot_ref=requirement.target_shot_ref,
        base_plate_asset=base,
        inspection_ref=requirement.base_plate_inspection_ref,
        expected_payload_digest=requirement.base_plate_inspection_digest,
    )
    if dimensions[2] < requirement.frame_range_end_exclusive:
        raise GlyphRevealFrameRangeError(
            "frameRangeEndExclusive exceeds the base plate frameCount"
        )
    _validate_geometry(
        requirement.composite_params,
        base_width=dimensions[0],
        base_height=dimensions[1],
    )
    base_binding = _base_binding_v2(base)
    mask_bindings = _normalize_mask_bindings_v2(
        _mask_bindings_from_assets_v2(masks), glyph_slug=requirement.glyph_slug
    )
    if (
        base_binding["assetVersionRef"]
        != requirement.base_plate_asset_version_ref
        or base_binding["assetVersionDigest"]
        != requirement.base_plate_asset_version_digest
        or base_binding["fileDigest"] != requirement.base_plate_file_digest
        or mask_bindings != requirement.mask_asset_version_bindings
        or inspection["inspectionRef"] != requirement.base_plate_inspection_ref
        or inspection["payloadDigest"]
        != requirement.base_plate_inspection_digest
    ):
        raise StaleInputError("GlyphRevealRequirementV2 bindings are stale")
    bindings = _input_bindings_payload_v2(
        base_plate_asset_version_ref=base_binding["assetVersionRef"],
        base_plate_asset_version_digest=base_binding["assetVersionDigest"],
        base_plate_file_digest=base_binding["fileDigest"],
        mask_bindings=mask_bindings,
        inspection_ref=inspection["inspectionRef"],
        inspection_digest=inspection["payloadDigest"],
    )
    if _digest(bindings) != requirement.input_bindings_digest:
        raise StaleInputError("GlyphRevealRequirementV2 input bindings are stale")
    return base, masks, inspection, dimensions


def build_glyph_reveal_execution_request_v2(
    requirement: GlyphRevealRequirementV2 | Mapping[str, Any],
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_adapter: DigestPinnedBasePlateGlyphInspectionAdapter,
) -> dict[str, Any]:
    current = _requirement_v2_value(requirement)
    base, masks, inspection, dimensions = _validate_current_bindings_v2(
        current,
        base_plate_asset=base_plate_asset,
        mask_assets=mask_assets,
        inspection_adapter=inspection_adapter,
    )
    execution = {
        "schemaVersion": GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2,
        "executionRequestRef": _expected_execution_request_ref_v2(current),
        "workspaceRef": current.workspace_ref,
        "productionRunRef": current.production_run_ref,
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "glyphSlug": current.glyph_slug,
        "targetShotRef": current.target_shot_ref,
        "frameRangeStartInclusive": current.frame_range_start_inclusive,
        "frameRangeEndExclusive": current.frame_range_end_exclusive,
        "revealSchedule": current.reveal_schedule,
        "inputBindingsDigest": current.input_bindings_digest,
        "basePlate": {
            "assetVersionRef": base["assetVersionRef"],
            "assetVersionDigest": base["payloadDigest"],
            "storageKey": base["storageKey"],
            "fileDigest": f"sha256:{base['sha256']}",
        },
        "masks": [
            {
                **binding,
                "storageKey": mask["storageKey"],
            }
            for binding, mask in zip(
                current.mask_asset_version_bindings, masks
            )
        ],
        "basePlateInspectionRef": inspection["inspectionRef"],
        "basePlateInspectionDigest": inspection["payloadDigest"],
        "compositeParams": current.composite_params,
        "output": {
            "width": dimensions[0],
            "height": dimensions[1],
            "frameRate": dimensions[3],
            "totalFrames": dimensions[2],
        },
        "publicationAllowed": False,
    }
    return _validate_execution_request_v2(_sealed(execution), requirement=current)


def _validate_execution_request_v2(
    value: Any, *, requirement: GlyphRevealRequirementV2
) -> dict[str, Any]:
    request = _verify_sealed(value, "glyphRevealExecutionRequestV2")
    if (
        set(request) != _EXECUTION_REQUEST_FIELDS_V2
        or request.get("schemaVersion")
        != GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2
        or request.get("executionRequestRef")
        != _expected_execution_request_ref_v2(requirement)
        or request.get("workspaceRef") != requirement.workspace_ref
        or request.get("productionRunRef") != requirement.production_run_ref
        or request.get("requirementRef") != requirement.requirement_ref
        or request.get("requirementDigest") != requirement.payload_digest
        or request.get("glyphSlug") != requirement.glyph_slug
        or request.get("targetShotRef") != requirement.target_shot_ref
        or request.get("frameRangeStartInclusive")
        != requirement.frame_range_start_inclusive
        or request.get("frameRangeEndExclusive")
        != requirement.frame_range_end_exclusive
        or request.get("inputBindingsDigest")
        != requirement.input_bindings_digest
        or request.get("basePlateInspectionRef")
        != requirement.base_plate_inspection_ref
        or request.get("basePlateInspectionDigest")
        != requirement.base_plate_inspection_digest
        or request.get("publicationAllowed") is not False
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 execution request is not bound to the requirement"
        )
    schedule = _normalize_schedule_v2(
        request.get("revealSchedule"),
        range_start=requirement.frame_range_start_inclusive,
        range_end=requirement.frame_range_end_exclusive,
        expected_mask_refs=requirement.mask_asset_version_refs,
    )
    if schedule != requirement.reveal_schedule:
        raise GlyphRevealArtifactError("glyph reveal v2 schedule is stale")
    if _normalize_composite_params(
        request.get("compositeParams")
    ) != requirement.composite_params:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 compositeParams are stale"
        )
    base = request.get("basePlate")
    masks = request.get("masks")
    if (
        not isinstance(base, Mapping)
        or set(base) != _EXECUTION_BASE_FIELDS_V2
        or not isinstance(masks, list)
        or len(masks) != requirement.reveal_frame_count
        or any(
            not isinstance(mask, Mapping)
            or set(mask) != _EXECUTION_MASK_FIELDS_V2
            for mask in masks
        )
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 execution input fields are invalid"
        )
    _storage_key_v2(base.get("storageKey"), "basePlate.storageKey")
    base_binding = {
        "assetVersionRef": _required_ref(
            base.get("assetVersionRef"), "basePlate.assetVersionRef"
        ),
        "assetVersionDigest": _raw_sha256(
            base.get("assetVersionDigest"), "basePlate.assetVersionDigest"
        ),
        "fileDigest": _pixel_digest(
            base.get("fileDigest"), "basePlate.fileDigest"
        ),
    }
    execution_mask_bindings: list[dict[str, Any]] = []
    for index, mask in enumerate(masks):
        _storage_key_v2(mask.get("storageKey"), f"masks[{index}].storageKey")
        execution_mask_bindings.append(
            {field: deepcopy(mask[field]) for field in _MASK_BINDING_FIELDS_V2}
        )
    normalized_mask_bindings = _normalize_mask_bindings_v2(
        execution_mask_bindings, glyph_slug=requirement.glyph_slug
    )
    if (
        base_binding
        != {
            "assetVersionRef": requirement.base_plate_asset_version_ref,
            "assetVersionDigest": requirement.base_plate_asset_version_digest,
            "fileDigest": requirement.base_plate_file_digest,
        }
        or normalized_mask_bindings
        != requirement.mask_asset_version_bindings
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 execution AssetVersion bindings are stale"
        )
    binding_payload = _input_bindings_payload_v2(
        base_plate_asset_version_ref=base_binding["assetVersionRef"],
        base_plate_asset_version_digest=base_binding["assetVersionDigest"],
        base_plate_file_digest=base_binding["fileDigest"],
        mask_bindings=normalized_mask_bindings,
        inspection_ref=requirement.base_plate_inspection_ref,
        inspection_digest=requirement.base_plate_inspection_digest,
    )
    if _digest(binding_payload) != requirement.input_bindings_digest:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 execution inputBindingsDigest is stale"
        )
    output = request.get("output")
    if not isinstance(output, Mapping) or set(output) != _EXECUTION_OUTPUT_FIELDS_V2:
        raise GlyphRevealArtifactError("glyph reveal v2 output contract is invalid")
    width = _integer(
        output.get("width"),
        "output.width",
        minimum=1,
        maximum=131_072,
        error_type=GlyphRevealArtifactError,
    )
    height = _integer(
        output.get("height"),
        "output.height",
        minimum=1,
        maximum=131_072,
        error_type=GlyphRevealArtifactError,
    )
    _frame_rate(output.get("frameRate"), "output.frameRate")
    total_frames = _integer(
        output.get("totalFrames"),
        "output.totalFrames",
        minimum=1,
        maximum=10_000_000,
        error_type=GlyphRevealArtifactError,
    )
    if total_frames < requirement.frame_range_end_exclusive:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 execution truncates the reveal interval"
        )
    _validate_geometry(
        requirement.composite_params, base_width=width, base_height=height
    )
    return request


def _validate_output_digest_v2(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OUTPUT_DIGEST_FIELDS_V2:
        raise GlyphRevealArtifactError("outputDigest v2 fields are invalid")
    result = deepcopy(dict(value))
    if (
        result.get("fileDigestAlgorithm") != "sha256"
        or result.get("decodedFramePixelDigestSpec")
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or result.get("pixelMode") != "RGBA"
    ):
        raise GlyphRevealArtifactError("outputDigest v2 algorithms are invalid")
    _pixel_digest(result.get("fileDigest"), "outputDigest.fileDigest")
    _pixel_digest(
        result.get("decodedFramePixelDigest"),
        "outputDigest.decodedFramePixelDigest",
    )
    for field, maximum in (
        ("width", 131_072),
        ("height", 131_072),
        ("frameCount", 10_000_000),
    ):
        _integer(
            result.get(field),
            f"outputDigest.{field}",
            minimum=1,
            maximum=maximum,
            error_type=GlyphRevealArtifactError,
        )
    _frame_rate(result.get("frameRate"), "outputDigest.frameRate")
    return result


def _normalized_media_probe_v2(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MEDIA_PROBE_FIELDS_V2:
        raise GlyphRevealArtifactError(f"{field} fields are invalid")
    width, height, frame_count, frame_rate = _video_probe_facts(value, field=field)
    return {
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "frameRate": frame_rate,
    }


def _validate_artifact_evidence_v2(
    value: Any,
    *,
    requirement: GlyphRevealRequirementV2,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        artifact = _verify_sealed(value, "GlyphRevealArtifactEvidenceV2")
    except StaleInputError as exc:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 artifact evidence seal is invalid"
        ) from exc
    if (
        set(artifact) != _ARTIFACT_EVIDENCE_FIELDS_V2
        or artifact.get("schemaVersion")
        != GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2
        or artifact.get("requirementRef") != requirement.requirement_ref
        or artifact.get("requirementDigest") != requirement.payload_digest
        or artifact.get("executionRequestRef")
        != execution.get("executionRequestRef")
        or artifact.get("executionRequestDigest")
        != execution.get("payloadDigest")
        or artifact.get("provenance") != LOCAL_EVIDENCE_PROVENANCE
        or artifact.get("gpuUsed") is not False
        or artifact.get("publicationAllowed") is not False
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 artifact evidence is not bound to execution"
        )
    storage_key = _storage_key_v2(
        artifact.get("outputStorageKey"), "artifact.outputStorageKey"
    )
    expected_key = expected_glyph_reveal_output_storage_key_v2(
        requirement.workspace_ref,
        requirement.production_run_ref,
        execution["payloadDigest"],
    )
    if storage_key != expected_key:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 artifact escaped the workspace/run output scope"
        )
    _integer(
        artifact.get("outputByteSize"),
        "artifact.outputByteSize",
        minimum=1,
        maximum=10**12,
        error_type=GlyphRevealArtifactError,
    )
    probe = _normalized_media_probe_v2(
        artifact.get("outputMediaProbe"), "artifact.outputMediaProbe"
    )
    output_digest = _validate_output_digest_v2(artifact.get("outputDigest"))
    if (
        probe["width"] != output_digest["width"]
        or probe["height"] != output_digest["height"]
        or probe["frameCount"] != output_digest["frameCount"]
        or probe["frameRate"] != output_digest["frameRate"]
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 probe and outputDigest disagree"
        )
    expected_output = execution["output"]
    if (
        probe["width"] != expected_output["width"]
        or probe["height"] != expected_output["height"]
        or probe["frameCount"] != expected_output["totalFrames"]
        or probe["frameRate"] != expected_output["frameRate"]
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 artifact media contract is stale"
        )
    renderer_identity = _text_identity(
        artifact.get("rendererIdentity"), "artifact.rendererIdentity"
    )
    renderer_version = _text_identity(
        artifact.get("rendererVersion"), "artifact.rendererVersion"
    )
    ffmpeg_identity = _text_identity(
        artifact.get("ffmpegIdentity"), "artifact.ffmpegIdentity"
    )
    if (
        renderer_identity != GLYPH_REVEAL_RENDERER_IDENTITY_V2
        or renderer_version != GLYPH_REVEAL_RENDERER_VERSION_V2
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 renderer identity is unsupported"
        )
    runtime_digest = _pixel_digest(
        artifact.get("runtimeEvidenceDigest"),
        "artifact.runtimeEvidenceDigest",
    )
    if runtime_digest != _runtime_evidence_digest_v2(
        renderer_identity=renderer_identity,
        renderer_version=renderer_version,
        ffmpeg_identity=ffmpeg_identity,
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal v2 runtime evidence digest is invalid"
        )
    artifact_ref = _required_ref(
        artifact.get("artifactEvidenceRef"), "artifact.artifactEvidenceRef"
    )
    expected_artifact_ref = "m13-glyph-reveal-artifact-evidence-" + _digest(
        {
            "executionRequestDigest": execution["payloadDigest"],
            "fileDigest": output_digest["fileDigest"],
        }
    )[:32]
    if artifact_ref != expected_artifact_ref:
        raise GlyphRevealArtifactError(
            "glyph reveal v2 artifactEvidenceRef is invalid"
        )
    return artifact


@dataclass(frozen=True, slots=True)
class GlyphRevealCompositionResultV2:
    _value_json: str

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "GlyphRevealCompositionResultV2":
        result = _verify_sealed(value, "GlyphRevealCompositionResultV2")
        if (
            set(result) != _RESULT_FIELDS_V2
            or result.get("schemaVersion")
            != GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2
            or result.get("state") != "COMPOSED_CANDIDATE"
            or result.get("publicationAllowed") is not False
        ):
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 fields are invalid"
            )
        for field in (
            "workspaceRef",
            "productionRunRef",
            "resultRef",
            "requirementRef",
            "executionRequestRef",
            "artifactEvidenceRef",
        ):
            _required_ref(result.get(field), field)
        for field in (
            "requirementDigest",
            "executionRequestDigest",
            "artifactEvidenceDigest",
        ):
            _raw_sha256(result.get(field), field)
        _storage_key_v2(result.get("outputStorageKey"), "outputStorageKey")
        _integer(
            result.get("outputByteSize"),
            "outputByteSize",
            minimum=1,
            maximum=10**12,
            error_type=GlyphRevealArtifactError,
        )
        probe = _normalized_media_probe_v2(
            result.get("outputMediaProbe"), "outputMediaProbe"
        )
        output_digest = _validate_output_digest_v2(result.get("outputDigest"))
        if (
            probe["width"] != output_digest["width"]
            or probe["height"] != output_digest["height"]
            or probe["frameCount"] != output_digest["frameCount"]
            or probe["frameRate"] != output_digest["frameRate"]
        ):
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 output facts disagree"
            )
        renderer_identity = _text_identity(
            result.get("rendererIdentity"), "rendererIdentity"
        )
        renderer_version = _text_identity(
            result.get("rendererVersion"), "rendererVersion"
        )
        ffmpeg_identity = _text_identity(
            result.get("ffmpegIdentity"), "ffmpegIdentity"
        )
        runtime_digest = _pixel_digest(
            result.get("runtimeEvidenceDigest"), "runtimeEvidenceDigest"
        )
        if (
            renderer_identity != GLYPH_REVEAL_RENDERER_IDENTITY_V2
            or renderer_version != GLYPH_REVEAL_RENDERER_VERSION_V2
            or runtime_digest
            != _runtime_evidence_digest_v2(
                renderer_identity=renderer_identity,
                renderer_version=renderer_version,
                ffmpeg_identity=ffmpeg_identity,
            )
        ):
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 runtime identity is invalid"
            )
        expected_key = expected_glyph_reveal_output_storage_key_v2(
            result["workspaceRef"],
            result["productionRunRef"],
            result["executionRequestDigest"],
        )
        if result["outputStorageKey"] != expected_key:
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 output scope is invalid"
            )
        expected_artifact_ref = (
            "m13-glyph-reveal-artifact-evidence-"
            + _digest(
                {
                    "executionRequestDigest": result["executionRequestDigest"],
                    "fileDigest": output_digest["fileDigest"],
                }
            )[:32]
        )
        if result["artifactEvidenceRef"] != expected_artifact_ref:
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 artifactEvidenceRef is invalid"
            )
        semantic = {
            "requirementRef": result["requirementRef"],
            "requirementDigest": result["requirementDigest"],
            "executionRequestRef": result["executionRequestRef"],
            "executionRequestDigest": result["executionRequestDigest"],
            "artifactEvidenceRef": result["artifactEvidenceRef"],
            "artifactEvidenceDigest": result["artifactEvidenceDigest"],
            "fileDigest": output_digest["fileDigest"],
            "decodedFramePixelDigest": output_digest[
                "decodedFramePixelDigest"
            ],
        }
        if result["resultRef"] != (
            "m13-glyph-reveal-result-" + _digest(semantic)[:32]
        ):
            raise GlyphRevealArtifactError(
                "GlyphRevealCompositionResultV2 resultRef is invalid"
            )
        return cls(_canonical_json(result))

    @property
    def payload_digest(self) -> str:
        return str(self.as_dict()["payloadDigest"])

    @property
    def result_ref(self) -> str:
        return str(self.as_dict()["resultRef"])

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._value_json)


def _read_result_v1(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _verify_sealed(value, "GlyphRevealCompositionResultV1")
    if (
        set(result) != _RESULT_FIELDS_V1
        or result.get("schemaVersion")
        != GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION
        or result.get("state") != "COMPOSED_CANDIDATE"
        or result.get("publicationAllowed") is not False
    ):
        raise GlyphRevealArtifactError(
            "GlyphRevealCompositionResultV1 fields are invalid"
        )
    return result


def read_glyph_reveal_composition_result(
    value: GlyphRevealCompositionResultV2 | Mapping[str, Any],
) -> GlyphRevealCompositionResultV2 | dict[str, Any]:
    """Read v1 or v2 result evidence without semantic conversion."""

    if isinstance(value, GlyphRevealCompositionResultV2):
        return GlyphRevealCompositionResultV2.from_mapping(value.as_dict())
    if not isinstance(value, Mapping):
        raise GlyphRevealArtifactError(
            "GlyphRevealCompositionResult must be an object"
        )
    if (
        value.get("schemaVersion")
        == GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2
    ):
        return GlyphRevealCompositionResultV2.from_mapping(value)
    return _read_result_v1(value)


def build_glyph_reveal_composition_result_v2(
    requirement: GlyphRevealRequirementV2 | Mapping[str, Any],
    execution_request: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> GlyphRevealCompositionResultV2:
    current = _requirement_v2_value(requirement)
    execution = _validate_execution_request_v2(
        execution_request, requirement=current
    )
    evidence = _validate_artifact_evidence_v2(
        artifact, requirement=current, execution=execution
    )
    semantic = {
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "executionRequestRef": execution["executionRequestRef"],
        "executionRequestDigest": execution["payloadDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
        "fileDigest": evidence["outputDigest"]["fileDigest"],
        "decodedFramePixelDigest": evidence["outputDigest"][
            "decodedFramePixelDigest"
        ],
    }
    result = {
        "schemaVersion": GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2,
        "workspaceRef": current.workspace_ref,
        "productionRunRef": current.production_run_ref,
        "resultRef": "m13-glyph-reveal-result-" + _digest(semantic)[:32],
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "executionRequestRef": execution["executionRequestRef"],
        "executionRequestDigest": execution["payloadDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
        "outputStorageKey": evidence["outputStorageKey"],
        "outputByteSize": evidence["outputByteSize"],
        "outputMediaProbe": deepcopy(evidence["outputMediaProbe"]),
        "outputDigest": deepcopy(evidence["outputDigest"]),
        "rendererIdentity": evidence["rendererIdentity"],
        "rendererVersion": evidence["rendererVersion"],
        "ffmpegIdentity": evidence["ffmpegIdentity"],
        "runtimeEvidenceDigest": evidence["runtimeEvidenceDigest"],
        "state": "COMPOSED_CANDIDATE",
        "publicationAllowed": False,
    }
    return GlyphRevealCompositionResultV2.from_mapping(_sealed(result))


__all__ = [
    "BASE_PLATE_GLYPH_INSPECTION_METHOD_V2",
    "BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION_V2",
    "BASE_PLATE_GLYPH_INSPECTOR_IDENTITY_V2",
    "DECODED_FRAME_PIXEL_DIGEST_SPEC_V2",
    "GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2",
    "GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2",
    "GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2",
    "GLYPH_REVEAL_RENDERER_IDENTITY_V2",
    "GLYPH_REVEAL_RENDERER_VERSION_V2",
    "GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2",
    "BasePlateGlyphInspectionEvidenceStore",
    "DigestPinnedBasePlateGlyphInspectionAdapter",
    "DigestPinnedFileBasePlateGlyphInspectionEvidenceStore",
    "GlyphRevealCompositionResultV2",
    "GlyphRevealRequirementV2",
    "GlyphRevealScheduleError",
    "build_glyph_reveal_composition_result_v2",
    "build_glyph_reveal_execution_request_v2",
    "build_glyph_reveal_requirement_v2",
    "expected_glyph_reveal_output_storage_key_v2",
    "read_glyph_reveal_composition_result",
    "read_glyph_reveal_requirement",
]
