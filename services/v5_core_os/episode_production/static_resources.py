"""Canonical static-resource admission capability (FONT-only v1 slice).

The existing Episode Production evidence journal remains the sole persistence
authority.  This module creates additive AssetVersion v2 evidence; it never
uses the retired AssetRegistry, a process-local font registry, or system font
fallback.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import stat
import struct
import subprocess
import shutil
import unicodedata
from typing import Any, Callable, Mapping, Protocol, Sequence

from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)


STATIC_RESOURCE_CANDIDATE_SCHEMA_VERSION = "v5.static-resource-candidate.v1"
FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION = "v5.font-technical-validation.v1"
RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION = (
    "v5.resource-license-binding-version.v1"
)
STATIC_RESOURCE_ADMISSION_DECISION_SCHEMA_VERSION = (
    "v5.static-resource-admission-decision.v1"
)
ASSET_VERSION_V2_SCHEMA_VERSION = "v5.asset-version.v2"
FONT_ASSET_VERSION_PROJECTION_SCHEMA_VERSION = (
    "v5.font-asset-version-projection.v1"
)

STATIC_RESOURCE_CANDIDATE = "StaticResourceCandidate"
FONT_TECHNICAL_VALIDATION = "FontTechnicalValidation"
RESOURCE_LICENSE_BINDING_VERSION = "ResourceLicenseBindingVersion"
STATIC_RESOURCE_ADMISSION_DECISION = "StaticResourceAdmissionDecision"
ASSET_VERSION = "AssetVersion"

TECHNICAL_FIXTURE_MARKERS = frozenset(
    {
        "TECHNICAL_FIXTURE_ONLY",
        "NOT_LIVE_ASSET",
        "NOT_SELECTED_FOR_PRODUCTION",
        "NOT_PUBLICATION_ASSET",
    }
)
SUPPORTED_LICENSES = frozenset({"OFL-1.1"})
SUPPORTED_MEDIA_TYPES = frozenset({"font/ttf", "font/otf"})
_SHA256 = frozenset("0123456789abcdef")


class StaticResourceError(EpisodeProductionError):
    code = "static_resource_invalid"


class FontTechnicalValidationError(StaticResourceError):
    code = "font_technical_validation_failed"


class ResourceLicenseRequiredError(StaticResourceError):
    code = "resource_license_required"


class StaticResourceAdmissionRequiredError(StaticResourceError):
    code = "static_resource_admission_required"


class StaticResourceStoragePort(Protocol):
    def open_regular_file(self, storage_binding_ref: str) -> int: ...


class ResourceLicenseAuthorityPort(Protocol):
    def decide(self, subject: Mapping[str, Any]) -> Mapping[str, Any]: ...


class StaticResourceAdmissionAuthorityPort(Protocol):
    def decide(self, subject: Mapping[str, Any]) -> Mapping[str, Any]: ...


class DigestPinnedReferenceEvidencePort(Protocol):
    def require_current(self, reference: str, digest: str, purpose: str) -> Mapping[str, Any]: ...


class RejectingDigestPinnedReferenceEvidence:
    def require_current(self, reference: str, digest: str, purpose: str) -> Mapping[str, Any]:
        del reference, digest, purpose
        raise UpstreamNotReadyError("digest-pinned reference evidence is unavailable")


class StaticDigestPinnedReferenceEvidence:
    """Test-only reader for exact existing evidence; it owns no persistence."""

    def __init__(self, values: Mapping[str, Mapping[str, Any]]) -> None:
        self._values = deepcopy(dict(values))

    def require_current(self, reference: str, digest: str, purpose: str) -> Mapping[str, Any]:
        del purpose
        value = self._values.get(reference)
        if not isinstance(value, Mapping) or value.get("payloadDigest") != digest:
            raise StaleInputError("digest-pinned reference evidence is stale")
        return deepcopy(dict(value))


class RejectingResourceLicenseAuthority:
    def decide(self, subject: Mapping[str, Any]) -> Mapping[str, Any]:
        del subject
        raise ResourceLicenseRequiredError("resource license authority is unavailable")


class RejectingStaticResourceAdmissionAuthority:
    def decide(self, subject: Mapping[str, Any]) -> Mapping[str, Any]:
        del subject
        raise StaticResourceAdmissionRequiredError(
            "static resource admission authority is unavailable"
        )


class StaticDigestPinnedAuthority:
    """Exact injectable decision authority for tests and bounded evidence."""

    def __init__(self, decisions: Mapping[str, Mapping[str, Any]]) -> None:
        self._decisions = deepcopy(dict(decisions))

    def decide(self, subject: Mapping[str, Any]) -> Mapping[str, Any]:
        digest = subject.get("subjectDigest")
        if not isinstance(digest, str) or digest not in self._decisions:
            raise StaticResourceAdmissionRequiredError("subject was not authorized")
        return deepcopy(dict(self._decisions[digest]))


@dataclass(frozen=True, slots=True)
class DirectoryStaticResourceStorage:
    """Server-held storage bindings rooted below one controlled directory."""

    root: Path
    bindings: Mapping[str, str]

    def open_regular_file(self, storage_binding_ref: str) -> int:
        relative = self.bindings.get(storage_binding_ref)
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith(("/", "\\"))
            or "\\" in relative
            or ".." in Path(relative).parts
        ):
            raise FontTechnicalValidationError("storage binding is unavailable")
        root = self.root.resolve(strict=True)
        candidate = root.joinpath(relative)
        try:
            fd = os.open(candidate, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        except OSError as exc:
            raise FontTechnicalValidationError(
                "font storage binding is not a readable regular file"
            ) from exc
        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode):
                raise FontTechnicalValidationError("font storage binding is not regular")
            resolved = Path(f"/proc/self/fd/{fd}").resolve(strict=True)
            if root != resolved and root not in resolved.parents:
                raise FontTechnicalValidationError("font storage binding escaped its root")
            return fd
        except Exception:
            os.close(fd)
            raise


def _sha(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise StaleInputError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StaticResourceError(f"{field} must be a positive integer")
    return value


def _closed(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise StaticResourceError(f"{label} is not closed-world")


def _sealed(value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    payload = deepcopy(dict(value))
    digest = _digest(payload)
    payload["payloadDigest"] = digest
    return payload, digest


def _record(
    *,
    workspace: str,
    run_ref: str,
    kind: str,
    ref: str,
    version: int,
    key: str,
    created_at: str,
    payload: Mapping[str, Any],
) -> EvidenceRecord:
    sealed, digest = _sealed(payload)
    return EvidenceRecord(
        workspaceRef=workspace,
        productionRunRef=run_ref,
        recordKind=kind,
        recordRef=ref,
        recordVersion=version,
        idempotencyKey=key,
        requestDigest=_digest(
            {
                "recordKind": kind,
                "recordRef": ref,
                "recordVersion": version,
                "payloadDigest": digest,
            }
        ),
        createdAt=created_at,
        payload=sealed,
        payloadDigest=digest,
    )


def _record_payload(record: Mapping[str, Any], kind: str) -> dict[str, Any]:
    payload = record.get("payload")
    if record.get("recordKind") != kind or not isinstance(payload, Mapping):
        raise StaleInputError(f"{kind} evidence is invalid")
    value = deepcopy(dict(payload))
    digest = value.pop("payloadDigest", None)
    if digest != record.get("payloadDigest") or _digest(value) != digest:
        raise StaleInputError(f"{kind} evidence digest is stale")
    value["payloadDigest"] = digest
    return value


def _read_exact(
    evidence: EpisodeProductionEvidenceRepository,
    workspace: str,
    run_ref: str,
    ref: Any,
    version: Any,
    digest: Any,
    kind: str,
) -> dict[str, Any]:
    selected_ref = _required_ref(ref, f"{kind}Ref")
    selected_version = _positive_int(version, f"{kind}Version")
    selected_digest = _sha(digest, f"{kind}Digest")
    record = evidence.get_record(workspace, run_ref, selected_ref, selected_version)
    if record is None:
        raise UpstreamNotReadyError(f"{kind} evidence is required")
    if record.get("payloadDigest") != selected_digest:
        raise StaleInputError(f"{kind} evidence digest is stale")
    return _record_payload(record, kind)


def _read_exact_by_ref_digest(
    evidence: EpisodeProductionEvidenceRepository,
    workspace: str,
    run_ref: str,
    ref: Any,
    digest: Any,
    kind: str,
) -> dict[str, Any]:
    """Read one immutable journal fact when the caller owns no version selector."""

    selected_ref = _required_ref(ref, f"{kind}Ref")
    selected_digest = _sha(digest, f"{kind}Digest")
    matches = [
        record
        for record in evidence.list_records(workspace, run_ref, record_kind=kind)
        if record.get("recordRef") == selected_ref
        and record.get("payloadDigest") == selected_digest
    ]
    if len(matches) != 1:
        raise UpstreamNotReadyError(f"exact {kind} evidence is required")
    return _record_payload(matches[0], kind)


def _exact_replay(
    evidence: EpisodeProductionEvidenceRepository,
    workspace: str,
    run_ref: str,
    key: str,
    kind: str,
    expected: Mapping[str, Any],
) -> dict[str, Any] | None:
    record = evidence.get_record_by_idempotency_key(workspace, run_ref, key)
    if record is None:
        return None
    value = _record_payload(record, kind)
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise IdempotencyConflictError("static resource idempotency content changed")
    return value


def _decode_name(raw: bytes, platform_id: int) -> str:
    try:
        return raw.decode("utf-16-be" if platform_id in {0, 3} else "latin-1").strip()
    except UnicodeDecodeError as exc:
        raise FontTechnicalValidationError("font name table is invalid") from exc


def _cmap_format_4_supports(
    subtable: bytes,
    *,
    num_glyphs: int,
) -> Callable[[int], bool]:
    """Parse one BMP Unicode cmap without importing a font runtime.

    The returned predicate reports actual, non-.notdef glyph coverage.  All
    offset arithmetic is checked while parsing so a malformed subtable cannot
    become an implicit renderer fallback.
    """

    if len(subtable) < 16:
        raise FontTechnicalValidationError("font cmap format 4 is truncated")
    format_number, declared_length, _language, segment_count_x2 = struct.unpack_from(
        ">HHHH", subtable, 0
    )
    if format_number != 4 or declared_length != len(subtable):
        raise FontTechnicalValidationError("font cmap format 4 length is invalid")
    if segment_count_x2 < 2 or segment_count_x2 % 2:
        raise FontTechnicalValidationError("font cmap format 4 segments are invalid")
    segment_count = segment_count_x2 // 2
    minimum_length = 16 + 8 * segment_count
    if minimum_length > len(subtable):
        raise FontTechnicalValidationError("font cmap format 4 arrays are truncated")

    end_offset = 14
    reserved_offset = end_offset + 2 * segment_count
    start_offset = reserved_offset + 2
    delta_offset = start_offset + 2 * segment_count
    range_offset = delta_offset + 2 * segment_count
    glyph_array_offset = range_offset + 2 * segment_count
    if struct.unpack_from(">H", subtable, reserved_offset)[0] != 0:
        raise FontTechnicalValidationError("font cmap format 4 reserved pad is invalid")

    end_codes = struct.unpack_from(f">{segment_count}H", subtable, end_offset)
    start_codes = struct.unpack_from(f">{segment_count}H", subtable, start_offset)
    deltas = struct.unpack_from(f">{segment_count}h", subtable, delta_offset)
    range_offsets = struct.unpack_from(f">{segment_count}H", subtable, range_offset)
    if end_codes[-1] != 0xFFFF or any(
        end_codes[index] >= end_codes[index + 1]
        for index in range(segment_count - 1)
    ):
        raise FontTechnicalValidationError("font cmap format 4 ordering is invalid")

    segments: list[tuple[int, int, int, int, int]] = []
    for index, (start, end, delta, relative) in enumerate(
        zip(start_codes, end_codes, deltas, range_offsets)
    ):
        if start > end:
            raise FontTechnicalValidationError("font cmap format 4 range is invalid")
        relative_word = range_offset + 2 * index
        if relative:
            first_glyph = relative_word + relative
            last_glyph = first_glyph + 2 * (end - start)
            if first_glyph < glyph_array_offset or last_glyph + 2 > len(subtable):
                raise FontTechnicalValidationError(
                    "font cmap format 4 glyph offsets are invalid"
                )
        segments.append((start, end, delta, relative, relative_word))

    def supports(codepoint: int) -> bool:
        if codepoint > 0xFFFF:
            return False
        for start, end, delta, relative, relative_word in segments:
            if codepoint > end:
                continue
            if codepoint < start:
                return False
            if relative == 0:
                glyph = (codepoint + delta) & 0xFFFF
            else:
                glyph_position = relative_word + relative + 2 * (codepoint - start)
                glyph = struct.unpack_from(">H", subtable, glyph_position)[0]
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            return 0 < glyph < num_glyphs
        return False

    return supports


def _cmap_format_12_supports(
    subtable: bytes,
    *,
    num_glyphs: int,
) -> Callable[[int], bool]:
    """Parse one full-Unicode grouped cmap and return a coverage predicate."""

    if len(subtable) < 16:
        raise FontTechnicalValidationError("font cmap format 12 is truncated")
    format_number, reserved, declared_length, _language, group_count = struct.unpack_from(
        ">HHIII", subtable, 0
    )
    if (
        format_number != 12
        or reserved != 0
        or declared_length != len(subtable)
        or 16 + group_count * 12 != len(subtable)
    ):
        raise FontTechnicalValidationError("font cmap format 12 length is invalid")

    groups: list[tuple[int, int, int]] = []
    previous_end = -1
    for index in range(group_count):
        start, end, start_glyph = struct.unpack_from(">III", subtable, 16 + 12 * index)
        final_glyph = start_glyph + (end - start) if start <= end else num_glyphs
        if (
            start > end
            or end > 0x10FFFF
            or start <= previous_end
            or (start <= 0xDFFF and end >= 0xD800)
            or final_glyph >= num_glyphs
        ):
            raise FontTechnicalValidationError("font cmap format 12 groups are invalid")
        groups.append((start, end, start_glyph))
        previous_end = end

    def supports(codepoint: int) -> bool:
        for start, end, start_glyph in groups:
            if codepoint > end:
                continue
            if codepoint < start:
                return False
            glyph = start_glyph + codepoint - start
            return 0 < glyph < num_glyphs
        return False

    return supports


def _unicode_cmap_predicates(
    data: bytes,
    tables: Mapping[bytes, tuple[int, int]],
) -> tuple[Callable[[int], bool], ...]:
    if b"cmap" not in tables or b"maxp" not in tables:
        raise FontTechnicalValidationError("font cmap and maxp tables are required")
    maxp_offset, maxp_length = tables[b"maxp"]
    if maxp_length < 6:
        raise FontTechnicalValidationError("font maxp table is invalid")
    num_glyphs = struct.unpack_from(">H", data, maxp_offset + 4)[0]
    if num_glyphs < 1:
        raise FontTechnicalValidationError("font has no glyphs")

    cmap_offset, cmap_length = tables[b"cmap"]
    cmap = data[cmap_offset : cmap_offset + cmap_length]
    if len(cmap) < 4:
        raise FontTechnicalValidationError("font cmap table is invalid")
    version, encoding_count = struct.unpack_from(">HH", cmap, 0)
    records_end = 4 + encoding_count * 8
    if version != 0 or encoding_count < 1 or records_end > len(cmap):
        raise FontTechnicalValidationError("font cmap encoding records are invalid")

    predicates: list[Callable[[int], bool]] = []
    parsed_offsets: set[int] = set()
    for index in range(encoding_count):
        platform, encoding, relative_offset = struct.unpack_from(
            ">HHI", cmap, 4 + index * 8
        )
        unicode_record = platform == 0 or (platform == 3 and encoding in {1, 10})
        if not unicode_record:
            continue
        if (
            relative_offset < records_end
            or relative_offset + 2 > len(cmap)
            or relative_offset in parsed_offsets
        ):
            if relative_offset in parsed_offsets:
                continue
            raise FontTechnicalValidationError("font cmap subtable offset is invalid")
        parsed_offsets.add(relative_offset)
        format_number = struct.unpack_from(">H", cmap, relative_offset)[0]
        if format_number == 4:
            if relative_offset + 6 > len(cmap):
                raise FontTechnicalValidationError("font cmap format 4 is truncated")
            subtable_length = struct.unpack_from(">H", cmap, relative_offset + 2)[0]
            end = relative_offset + subtable_length
            if subtable_length < 16 or end > len(cmap):
                raise FontTechnicalValidationError("font cmap format 4 bounds are invalid")
            predicates.append(
                _cmap_format_4_supports(
                    cmap[relative_offset:end], num_glyphs=num_glyphs
                )
            )
        elif format_number == 12:
            if relative_offset + 16 > len(cmap):
                raise FontTechnicalValidationError("font cmap format 12 is truncated")
            subtable_length = struct.unpack_from(">I", cmap, relative_offset + 4)[0]
            end = relative_offset + subtable_length
            if subtable_length < 16 or end > len(cmap):
                raise FontTechnicalValidationError("font cmap format 12 bounds are invalid")
            predicates.append(
                _cmap_format_12_supports(
                    cmap[relative_offset:end], num_glyphs=num_glyphs
                )
            )
    if not predicates:
        raise FontTechnicalValidationError(
            "font has no supported Unicode cmap format 4 or 12"
        )
    return tuple(predicates)


def _required_visible_scalars(required_text: str) -> tuple[int, ...]:
    if not isinstance(required_text, str):
        raise FontTechnicalValidationError("required text must be a string")
    visible: set[int] = set()
    for character in required_text:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise FontTechnicalValidationError("required text contains a surrogate")
        category = unicodedata.category(character)
        if character.isspace() or category in {"Cc", "Cf", "Cn"}:
            continue
        if 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF:
            continue
        visible.add(codepoint)
    return tuple(sorted(visible))


def _parse_sfnt(
    data: bytes,
    declared_media_type: str,
    *,
    required_text: str | None = None,
) -> dict[str, Any]:
    if len(data) < 12:
        raise FontTechnicalValidationError("font is not a complete SFNT file")
    signature = data[:4]
    if signature in {b"ttcf", b"wOFF", b"wOF2"}:
        raise FontTechnicalValidationError("font container is unsupported")
    if signature in {b"\x00\x01\x00\x00", b"true"}:
        font_format, expected_media = "TTF", "font/ttf"
    elif signature == b"OTTO":
        font_format, expected_media = "OTF", "font/otf"
    else:
        raise FontTechnicalValidationError("font SFNT signature is unsupported")
    if declared_media_type != expected_media:
        raise FontTechnicalValidationError("font media type disguises its SFNT format")
    table_count = struct.unpack_from(">H", data, 4)[0]
    if table_count < 1 or 12 + table_count * 16 > len(data):
        raise FontTechnicalValidationError("font table directory is invalid")
    tables: dict[bytes, tuple[int, int]] = {}
    for index in range(table_count):
        tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if offset + length > len(data) or tag in tables:
            raise FontTechnicalValidationError("font table bounds are invalid")
        tables[tag] = (offset, length)
    cmap_predicates = _unicode_cmap_predicates(data, tables)
    if required_text is not None:
        missing = [
            codepoint
            for codepoint in _required_visible_scalars(required_text)
            if not any(predicate(codepoint) for predicate in cmap_predicates)
        ]
        if missing:
            rendered = ", ".join(f"U+{codepoint:04X}" for codepoint in missing[:8])
            raise FontTechnicalValidationError(
                f"font lacks required visible glyphs: {rendered}"
            )
    if b"name" not in tables:
        raise FontTechnicalValidationError("font name table is required")
    offset, length = tables[b"name"]
    table = data[offset : offset + length]
    if len(table) < 6:
        raise FontTechnicalValidationError("font name table is invalid")
    _format, count, strings_offset = struct.unpack_from(">HHH", table, 0)
    if 6 + count * 12 > len(table) or strings_offset > len(table):
        raise FontTechnicalValidationError("font name records are invalid")
    names: dict[int, str] = {}
    for index in range(count):
        platform, encoding, language, name_id, size, start = struct.unpack_from(
            ">HHHHHH", table, 6 + index * 12
        )
        del encoding
        begin = strings_offset + start
        end = begin + size
        if end > len(table):
            raise FontTechnicalValidationError("font name string is out of bounds")
        if name_id in {1, 2, 6} and (
            name_id not in names or (platform == 3 and language in {0x409, 0})
        ):
            text = _decode_name(table[begin:end], platform)
            if text:
                names[name_id] = text
    if any(item not in names for item in (1, 2, 6)):
        raise FontTechnicalValidationError("font identity names are incomplete")
    return {
        "fontFormat": font_format,
        "sfntSignature": signature.hex(),
        "fontFamily": names[1],
        "fontSubfamily": names[2],
        "postScriptName": names[6],
        "nameTableDigest": sha256(table).hexdigest(),
        "variableFont": b"fvar" in tables,
        "variationAxesDigest": (
            sha256(data[tables[b"fvar"][0] : sum(tables[b"fvar"])]).hexdigest()
            if b"fvar" in tables
            else sha256(b"").hexdigest()
        ),
    }


def _renderer_probe(fd: int, ffmpeg_executable: str, test_text: str) -> dict[str, str]:
    resolved_executable = shutil.which(ffmpeg_executable) if "/" not in ffmpeg_executable else ffmpeg_executable
    if not resolved_executable:
        raise FontTechnicalValidationError("fixed renderer executable is unavailable")
    executable = Path(resolved_executable).resolve(strict=True)
    version = subprocess.run(
        [str(executable), "-hide_banner", "-version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout.splitlines()[0]
    fd_path = f"/proc/self/fd/{fd}"
    escaped = test_text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    command = [
        str(executable), "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "color=c=black:s=320x96:r=1:d=1", "-vf",
        f"drawtext=fontfile='{fd_path}':text='{escaped}':fontcolor=white:fontsize=40:x=12:y=24",
        "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1",
    ]
    try:
        pixels = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(fd,),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FontTechnicalValidationError("fixed renderer could not load the font") from exc
    if len(pixels) != 320 * 96 * 4:
        raise FontTechnicalValidationError("renderer probe pixel output is incomplete")
    identity_digest = sha256((str(executable) + "\n" + version).encode()).hexdigest()
    return {
        "rendererProbeDigest": sha256(pixels).hexdigest(),
        "rendererIdentity": f"v3.ffmpeg-drawtext-held-font.v1:{identity_digest}",
        "rendererVersion": version,
        "ffmpegIdentity": f"sha256:{identity_digest}",
        "freetypeIdentity": f"libfreetype-via-ffmpeg:sha256:{identity_digest}",
    }


def sanitize_font_asset_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    public = deepcopy(dict(value))
    public.pop("storageBindingRef", None)
    public.pop("absolutePath", None)
    public.pop("sourcePath", None)
    public.pop("rendererArgv", None)
    public["schemaVersion"] = FONT_ASSET_VERSION_PROJECTION_SCHEMA_VERSION
    return public


class CanonicalStaticResourceService:
    def __init__(
        self,
        root_service: Any,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        storage: StaticResourceStoragePort,
        license_authority: ResourceLicenseAuthorityPort | None = None,
        admission_authority: StaticResourceAdmissionAuthorityPort | None = None,
        reference_evidence: DigestPinnedReferenceEvidencePort | None = None,
        clock: Callable[[], str],
        ref_factory: Callable[[str], str],
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.storage = storage
        self.license_authority = license_authority or RejectingResourceLicenseAuthority()
        self.admission_authority = (
            admission_authority or RejectingStaticResourceAdmissionAuthority()
        )
        self.reference_evidence = (
            reference_evidence or RejectingDigestPinnedReferenceEvidence()
        )
        self.clock = clock
        self.ref_factory = ref_factory
        self.ffmpeg_executable = ffmpeg_executable

    def _scope(self, command: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], str]:
        if not isinstance(command, Mapping):
            raise StaticResourceError("command must be an object")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        key = _idempotency_key(command.get("idempotencyKey"))
        root = deepcopy(dict(self.root_service.verify_run_current(workspace, run_ref)))
        return workspace, run_ref, root, key

    def create_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {
            "workspaceRef", "productionRunRef", "idempotencyKey", "candidateRef",
            "candidateVersion", "assetClass", "resourceKind", "artifactEvidenceRef",
            "artifactEvidenceDigest", "storageBindingRef", "byteSize", "fileDigest",
            "mediaType", "sourceProvenanceRef", "sourceProvenanceDigest",
        }
        _closed(command, fields, "StaticResourceCandidate command")
        workspace, run_ref, root, key = self._scope(command)
        if command.get("assetClass") != "STATIC_RESOURCE" or command.get("resourceKind") != "FONT":
            raise StaticResourceError("only STATIC_RESOURCE/FONT is supported")
        media_type = command.get("mediaType")
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise StaticResourceError("font media type is unsupported")
        artifact_ref = _required_ref(command.get("artifactEvidenceRef"), "artifactEvidenceRef")
        artifact_digest = _sha(command.get("artifactEvidenceDigest"), "artifactEvidenceDigest")
        provenance_ref = _required_ref(command.get("sourceProvenanceRef"), "sourceProvenanceRef")
        provenance_digest = _sha(command.get("sourceProvenanceDigest"), "sourceProvenanceDigest")
        self.reference_evidence.require_current(artifact_ref, artifact_digest, "FONT_ARTIFACT")
        self.reference_evidence.require_current(provenance_ref, provenance_digest, "FONT_PROVENANCE")
        fd = self.storage.open_regular_file(
            _required_ref(command.get("storageBindingRef"), "storageBindingRef")
        )
        try:
            data = b""
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
        if len(data) != _positive_int(command.get("byteSize"), "byteSize"):
            raise StaleInputError("font byteSize is stale")
        if sha256(data).hexdigest() != _sha(command.get("fileDigest"), "fileDigest"):
            raise StaleInputError("font fileDigest is stale")
        _parse_sfnt(data, str(media_type))
        replay = _exact_replay(
            self.evidence, workspace, run_ref, key, STATIC_RESOURCE_CANDIDATE,
            {"candidateRef": command.get("candidateRef"), "candidateVersion": command.get("candidateVersion"),
             "artifactEvidenceRef": artifact_ref, "artifactEvidenceDigest": artifact_digest,
             "storageBindingRef": command.get("storageBindingRef"), "byteSize": command.get("byteSize"),
             "fileDigest": command.get("fileDigest"), "mediaType": media_type,
             "sourceProvenanceRef": provenance_ref, "sourceProvenanceDigest": provenance_digest},
        )
        if replay is not None:
            return replay
        payload = {
            "schemaVersion": STATIC_RESOURCE_CANDIDATE_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "projectRef": root["projectRef"], "seriesRef": root["seriesRef"],
            "episodeRef": root["episodeRef"],
            "candidateRef": _required_ref(command.get("candidateRef"), "candidateRef"),
            "candidateVersion": _positive_int(command.get("candidateVersion"), "candidateVersion"),
            "assetClass": "STATIC_RESOURCE", "resourceKind": "FONT",
            "artifactEvidenceRef": artifact_ref,
            "artifactEvidenceDigest": artifact_digest,
            "storageBindingRef": command["storageBindingRef"],
            "byteSize": len(data), "fileDigest": sha256(data).hexdigest(),
            "mediaType": media_type,
            "sourceProvenanceRef": provenance_ref,
            "sourceProvenanceDigest": provenance_digest,
            "createdAt": self.clock(), "publicationAllowed": False,
        }
        record = _record(workspace=workspace, run_ref=run_ref, kind=STATIC_RESOURCE_CANDIDATE,
            ref=payload["candidateRef"], version=payload["candidateVersion"], key=key,
            created_at=payload["createdAt"], payload=payload)
        stored, _ = self.evidence.append_record(record)
        return _record_payload(stored, STATIC_RESOURCE_CANDIDATE)

    def validate_font(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {"workspaceRef", "productionRunRef", "idempotencyKey", "candidateRef",
            "candidateVersion", "candidateDigest", "validationRef", "testText"}
        _closed(command, fields, "FontTechnicalValidation command")
        workspace, run_ref, _root, key = self._scope(command)
        candidate = _read_exact(self.evidence, workspace, run_ref, command.get("candidateRef"),
            command.get("candidateVersion"), command.get("candidateDigest"), STATIC_RESOURCE_CANDIDATE)
        test_text = command.get("testText")
        fd = self.storage.open_regular_file(candidate["storageBindingRef"])
        try:
            data = b""
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk: break
                data += chunk
            if len(data) != candidate["byteSize"] or sha256(data).hexdigest() != candidate["fileDigest"]:
                raise StaleInputError("font file changed after candidacy")
            facts = _parse_sfnt(
                data, candidate["mediaType"], required_text=test_text
            )
            os.lseek(fd, 0, os.SEEK_SET)
            probe = _renderer_probe(fd, self.ffmpeg_executable, test_text)
        finally:
            os.close(fd)
        replay = _exact_replay(
            self.evidence, workspace, run_ref, key, FONT_TECHNICAL_VALIDATION,
            {"validationRef": command.get("validationRef"), "candidateRef": candidate["candidateRef"],
             "candidateDigest": candidate["payloadDigest"],
             "rendererProbeDigest": probe["rendererProbeDigest"],
             "rendererIdentity": probe["rendererIdentity"]},
        )
        if replay is not None:
            return replay
        payload = {"schemaVersion": FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION,
            "workspaceRef": workspace, "productionRunRef": run_ref,
            "validationRef": _required_ref(command.get("validationRef"), "validationRef"),
            "candidateRef": candidate["candidateRef"], "candidateDigest": candidate["payloadDigest"],
            "fileDigest": candidate["fileDigest"], "byteSize": candidate["byteSize"], **facts,
            "rendererProbeRef": self.ref_factory("font-renderer-probe"), **probe,
            "validationState": "PASS", "failureReasons": [], "createdAt": self.clock(),
            "publicationAllowed": False}
        record = _record(workspace=workspace, run_ref=run_ref, kind=FONT_TECHNICAL_VALIDATION,
            ref=payload["validationRef"], version=1, key=key, created_at=payload["createdAt"], payload=payload)
        stored, _ = self.evidence.append_record(record)
        return _record_payload(stored, FONT_TECHNICAL_VALIDATION)

    def bind_license(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {"workspaceRef", "productionRunRef", "idempotencyKey", "candidateRef",
            "candidateVersion", "candidateDigest", "licenseBindingRef", "licenseBindingVersionRef",
            "versionNumber", "parentLicenseBindingVersionRef", "licenseSpdxId", "licenseTextDigest",
            "licenseEvidenceRef", "licenseEvidenceDigest", "validFrom", "expiresAt"}
        _closed(command, fields, "ResourceLicenseBindingVersion command")
        workspace, run_ref, _root, key = self._scope(command)
        candidate = _read_exact(self.evidence, workspace, run_ref, command.get("candidateRef"),
            command.get("candidateVersion"), command.get("candidateDigest"), STATIC_RESOURCE_CANDIDATE)
        if command.get("licenseSpdxId") not in SUPPORTED_LICENSES:
            raise ResourceLicenseRequiredError("license SPDX identifier is unsupported")
        license_text_digest = _sha(command.get("licenseTextDigest"), "licenseTextDigest")
        license_evidence_ref = _required_ref(command.get("licenseEvidenceRef"), "licenseEvidenceRef")
        license_evidence_digest = _sha(command.get("licenseEvidenceDigest"), "licenseEvidenceDigest")
        self.reference_evidence.require_current(
            license_evidence_ref, license_evidence_digest, "FONT_LICENSE_EVIDENCE"
        )
        self.reference_evidence.require_current(
            f"license-text:{command.get('licenseSpdxId')}", license_text_digest, "FONT_LICENSE_TEXT"
        )
        authority_subject_digest = _digest({
            "candidateDigest": candidate["payloadDigest"],
            "fontFileDigest": candidate["fileDigest"],
            "licenseSpdxId": command.get("licenseSpdxId"),
            "licenseTextDigest": license_text_digest,
            "licenseEvidenceRef": license_evidence_ref,
            "licenseEvidenceDigest": license_evidence_digest,
        })
        subject = {"subjectDigest": authority_subject_digest, "candidateRef": candidate["candidateRef"],
            "fontFileDigest": candidate["fileDigest"], "licenseSpdxId": command.get("licenseSpdxId"),
            "licenseTextDigest": license_text_digest,
            "licenseEvidenceRef": license_evidence_ref,
            "licenseEvidenceDigest": license_evidence_digest}
        decision = self.license_authority.decide(subject)
        required = {"subjectDigest", "decisionAuthorityRef", "decisionAuthorityDigest",
            "commercialUseAllowed", "technicalPreviewAllowed", "renderCandidateUseAllowed",
            "embeddingAllowed", "redistributionAllowed", "modificationAllowed",
            "attributionRequired", "reservedFontNames", "territories", "revocationState"}
        _closed(decision, required, "license authority decision")
        if decision.get("subjectDigest") != authority_subject_digest:
            raise StaleInputError("license authority subject is stale")
        if decision.get("revocationState") != "ACTIVE":
            raise ResourceLicenseRequiredError("license decision is not active")
        replay = _exact_replay(
            self.evidence, workspace, run_ref, key, RESOURCE_LICENSE_BINDING_VERSION,
            {"licenseBindingRef": command.get("licenseBindingRef"),
             "licenseBindingVersionRef": command.get("licenseBindingVersionRef"),
             "versionNumber": command.get("versionNumber"), "candidateDigest": candidate["payloadDigest"],
             "fontFileDigest": candidate["fileDigest"], "licenseSpdxId": command.get("licenseSpdxId"),
             "licenseTextDigest": license_text_digest, "licenseEvidenceRef": license_evidence_ref,
             "licenseEvidenceDigest": license_evidence_digest},
        )
        if replay is not None:
            return replay
        payload = {"schemaVersion": RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION,
            "workspaceRef": workspace, "productionRunRef": run_ref,
            "licenseBindingRef": _required_ref(command.get("licenseBindingRef"), "licenseBindingRef"),
            "licenseBindingVersionRef": _required_ref(command.get("licenseBindingVersionRef"), "licenseBindingVersionRef"),
            "versionNumber": _positive_int(command.get("versionNumber"), "versionNumber"),
            "parentLicenseBindingVersionRef": command.get("parentLicenseBindingVersionRef"),
            "candidateRef": candidate["candidateRef"], "candidateDigest": candidate["payloadDigest"],
            "fontFileDigest": candidate["fileDigest"], "licenseSpdxId": command["licenseSpdxId"],
            "licenseTextDigest": license_text_digest,
            "licenseEvidenceRef": license_evidence_ref,
            "licenseEvidenceDigest": license_evidence_digest,
            **{name: deepcopy(decision[name]) for name in required if name != "subjectDigest"},
            "validFrom": command.get("validFrom"), "expiresAt": command.get("expiresAt"),
            "createdAt": self.clock(), "publicationAllowed": False}
        record = _record(workspace=workspace, run_ref=run_ref, kind=RESOURCE_LICENSE_BINDING_VERSION,
            ref=payload["licenseBindingVersionRef"], version=payload["versionNumber"], key=key,
            created_at=payload["createdAt"], payload=payload)
        stored, _ = self.evidence.append_record(record)
        return _record_payload(stored, RESOURCE_LICENSE_BINDING_VERSION)

    def admit(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {"workspaceRef", "productionRunRef", "idempotencyKey", "candidateRef",
            "candidateVersion", "candidateDigest", "technicalValidationRef", "technicalValidationDigest",
            "licenseBindingVersionRef", "licenseBindingVersion", "licenseBindingVersionDigest",
            "admissionDecisionRef", "assetRef", "assetVersionRef", "version"}
        _closed(command, fields, "StaticResourceAdmission command")
        workspace, run_ref, root, key = self._scope(command)
        candidate = _read_exact(self.evidence, workspace, run_ref, command.get("candidateRef"),
            command.get("candidateVersion"), command.get("candidateDigest"), STATIC_RESOURCE_CANDIDATE)
        validation = _read_exact(self.evidence, workspace, run_ref, command.get("technicalValidationRef"),
            1, command.get("technicalValidationDigest"), FONT_TECHNICAL_VALIDATION)
        license_value = _read_exact(self.evidence, workspace, run_ref, command.get("licenseBindingVersionRef"),
            command.get("licenseBindingVersion"), command.get("licenseBindingVersionDigest"),
            RESOURCE_LICENSE_BINDING_VERSION)
        self.reference_evidence.require_current(
            candidate["artifactEvidenceRef"], candidate["artifactEvidenceDigest"], "FONT_ARTIFACT"
        )
        self.reference_evidence.require_current(
            candidate["sourceProvenanceRef"], candidate["sourceProvenanceDigest"], "FONT_PROVENANCE"
        )
        self.reference_evidence.require_current(
            license_value["licenseEvidenceRef"], license_value["licenseEvidenceDigest"],
            "FONT_LICENSE_EVIDENCE",
        )
        self.reference_evidence.require_current(
            f"license-text:{license_value['licenseSpdxId']}", license_value["licenseTextDigest"],
            "FONT_LICENSE_TEXT",
        )
        fd = self.storage.open_regular_file(candidate["storageBindingRef"])
        try:
            hasher = sha256()
            measured_size = 0
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                measured_size += len(chunk)
        finally:
            os.close(fd)
        if measured_size != candidate["byteSize"] or hasher.hexdigest() != candidate["fileDigest"]:
            raise StaleInputError("font file changed before admission")
        now = datetime.fromisoformat(self.clock().replace("Z", "+00:00"))
        valid_from = datetime.fromisoformat(str(license_value["validFrom"]).replace("Z", "+00:00"))
        expires_at = license_value.get("expiresAt")
        expiry = (
            datetime.max.replace(tzinfo=timezone.utc)
            if expires_at is None
            else datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        )
        if (validation.get("candidateDigest") != candidate["payloadDigest"]
            or validation.get("fileDigest") != candidate["fileDigest"]
            or validation.get("validationState") != "PASS"
            or license_value.get("candidateDigest") != candidate["payloadDigest"]
            or license_value.get("fontFileDigest") != candidate["fileDigest"]
            or license_value.get("revocationState") != "ACTIVE"
            or not license_value.get("commercialUseAllowed")
            or not license_value.get("technicalPreviewAllowed")
            or not license_value.get("renderCandidateUseAllowed")
            or now < valid_from or now >= expiry):
            raise StaleInputError("font admission lineage is stale or insufficient")
        subject = {"subjectDigest": _digest({"candidateDigest": candidate["payloadDigest"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionDigest": license_value["payloadDigest"]}),
            "workspaceRef": workspace, "productionRunRef": run_ref, "resourceKind": "FONT"}
        decision = self.admission_authority.decide(subject)
        _closed(decision, {"subjectDigest", "decisionAuthorityRef", "decisionAuthorityDigest",
            "decisionState"}, "admission authority decision")
        if decision.get("subjectDigest") != subject["subjectDigest"] or decision.get("decisionState") != "ADMIT":
            raise StaticResourceAdmissionRequiredError("font admission was not authorized")
        replay = _exact_replay(
            self.evidence, workspace, run_ref, f"{key}:asset", ASSET_VERSION,
            {"assetRef": command.get("assetRef"), "assetVersionRef": command.get("assetVersionRef"),
             "version": command.get("version"), "candidateDigest": candidate["payloadDigest"],
             "technicalValidationDigest": validation["payloadDigest"],
             "licenseBindingVersionDigest": license_value["payloadDigest"]},
        )
        if replay is not None:
            return replay
        created = self.clock()
        decision_payload = {"schemaVersion": STATIC_RESOURCE_ADMISSION_DECISION_SCHEMA_VERSION,
            "workspaceRef": workspace, "productionRunRef": run_ref,
            "admissionDecisionRef": _required_ref(command.get("admissionDecisionRef"), "admissionDecisionRef"),
            "candidateRef": candidate["candidateRef"], "candidateDigest": candidate["payloadDigest"],
            "technicalValidationRef": validation["validationRef"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionRef": license_value["licenseBindingVersionRef"],
            "licenseBindingVersionDigest": license_value["payloadDigest"],
            "resourceKind": "FONT", **decision, "createdAt": created, "publicationAllowed": False}
        decision_record = _record(workspace=workspace, run_ref=run_ref,
            kind=STATIC_RESOURCE_ADMISSION_DECISION, ref=decision_payload["admissionDecisionRef"],
            version=1, key=f"{key}:decision", created_at=created, payload=decision_payload)
        decision_sealed = deepcopy(dict(decision_record.payload))
        asset_payload = {"schemaVersion": ASSET_VERSION_V2_SCHEMA_VERSION,
            "workspaceRef": workspace, "productionRunRef": run_ref,
            "projectRef": root["projectRef"], "seriesRef": root["seriesRef"], "episodeRef": root["episodeRef"],
            "assetRef": _required_ref(command.get("assetRef"), "assetRef"),
            "assetVersionRef": _required_ref(command.get("assetVersionRef"), "assetVersionRef"),
            "version": _positive_int(command.get("version"), "version"),
            "assetClass": "STATIC_RESOURCE", "resourceKind": "FONT",
            "candidateRef": candidate["candidateRef"], "candidateDigest": candidate["payloadDigest"],
            "technicalValidationRef": validation["validationRef"], "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionRef": license_value["licenseBindingVersionRef"],
            "licenseBindingVersionDigest": license_value["payloadDigest"],
            "admissionDecisionRef": decision_payload["admissionDecisionRef"],
            "admissionDecisionDigest": decision_sealed["payloadDigest"],
            "mediaType": candidate["mediaType"], "fontFormat": validation["fontFormat"],
            "byteSize": candidate["byteSize"], "fileDigest": candidate["fileDigest"],
            "storageBindingRef": candidate["storageBindingRef"], "state": "REGISTERED",
            "admissionState": "ADMITTED", "publicationAllowed": False, "createdAt": created}
        asset_record = _record(workspace=workspace, run_ref=run_ref, kind=ASSET_VERSION,
            ref=asset_payload["assetVersionRef"], version=asset_payload["version"], key=f"{key}:asset",
            created_at=created, payload=asset_payload)
        stored, _ = self.evidence.append_records([decision_record, asset_record])
        return _record_payload(stored[1], ASSET_VERSION)

    def project_font_asset_versions(self, workspace: str, run_ref: str) -> list[dict[str, Any]]:
        result = []
        for record in self.evidence.list_records(workspace, run_ref, record_kind=ASSET_VERSION):
            value = _record_payload(record, ASSET_VERSION)
            if value.get("schemaVersion") != ASSET_VERSION_V2_SCHEMA_VERSION:
                continue
            if value.get("assetClass") != "STATIC_RESOURCE" or value.get("resourceKind") != "FONT":
                raise StaleInputError("AssetVersion v2 static resource is unsupported")
            result.append(sanitize_font_asset_projection(value))
        return sorted(result, key=lambda item: (item["assetRef"], item["version"]))

    def require_current_font_asset_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        asset_version_ref: str,
        asset_version_digest: str,
        *,
        required_text: str | None = None,
    ) -> dict[str, Any]:
        """Revalidate one admitted FONT and every authority fact it depends on.

        The returned ``storageBindingRef`` is an internal server binding used only
        for controlled execution staging.  ``sanitize_font_asset_projection``
        remains the public/read projection and never exposes that binding.
        """

        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        version_ref = _required_ref(asset_version_ref, "fontAssetVersionRef")
        version_digest = _sha(
            asset_version_digest, "fontAssetVersionDigest"
        )
        root = deepcopy(
            dict(self.root_service.verify_run_current(workspace, run_ref))
        )
        asset = _read_exact_by_ref_digest(
            self.evidence,
            workspace,
            run_ref,
            version_ref,
            version_digest,
            ASSET_VERSION,
        )
        _closed(
            asset,
            {
                "schemaVersion", "workspaceRef", "productionRunRef", "projectRef",
                "seriesRef", "episodeRef", "assetRef", "assetVersionRef", "version",
                "assetClass", "resourceKind", "candidateRef", "candidateDigest",
                "technicalValidationRef", "technicalValidationDigest",
                "licenseBindingVersionRef", "licenseBindingVersionDigest",
                "admissionDecisionRef", "admissionDecisionDigest", "mediaType",
                "fontFormat", "byteSize", "fileDigest", "storageBindingRef", "state",
                "admissionState", "publicationAllowed", "createdAt", "payloadDigest",
            },
            "current FONT AssetVersion",
        )
        if (
            asset.get("schemaVersion") != ASSET_VERSION_V2_SCHEMA_VERSION
            or asset.get("workspaceRef") != workspace
            or asset.get("productionRunRef") != run_ref
            or asset.get("projectRef") != root.get("projectRef")
            or asset.get("seriesRef") != root.get("seriesRef")
            or asset.get("episodeRef") != root.get("episodeRef")
            or asset.get("assetVersionRef") != version_ref
            or asset.get("payloadDigest") != version_digest
            or isinstance(asset.get("version"), bool)
            or not isinstance(asset.get("version"), int)
            or asset.get("version", 0) < 1
            or asset.get("assetClass") != "STATIC_RESOURCE"
            or asset.get("resourceKind") != "FONT"
            or asset.get("state") != "REGISTERED"
            or asset.get("admissionState") != "ADMITTED"
            or asset.get("publicationAllowed") is not False
        ):
            raise StaleInputError("FONT AssetVersion is stale")

        candidate = _read_exact_by_ref_digest(
            self.evidence,
            workspace,
            run_ref,
            asset.get("candidateRef"),
            asset.get("candidateDigest"),
            STATIC_RESOURCE_CANDIDATE,
        )
        validation = _read_exact_by_ref_digest(
            self.evidence,
            workspace,
            run_ref,
            asset.get("technicalValidationRef"),
            asset.get("technicalValidationDigest"),
            FONT_TECHNICAL_VALIDATION,
        )
        license_value = _read_exact_by_ref_digest(
            self.evidence,
            workspace,
            run_ref,
            asset.get("licenseBindingVersionRef"),
            asset.get("licenseBindingVersionDigest"),
            RESOURCE_LICENSE_BINDING_VERSION,
        )
        admission = _read_exact_by_ref_digest(
            self.evidence,
            workspace,
            run_ref,
            asset.get("admissionDecisionRef"),
            asset.get("admissionDecisionDigest"),
            STATIC_RESOURCE_ADMISSION_DECISION,
        )

        _closed(
            candidate,
            {
                "schemaVersion", "workspaceRef", "productionRunRef", "projectRef",
                "seriesRef", "episodeRef", "candidateRef", "candidateVersion",
                "assetClass", "resourceKind", "artifactEvidenceRef",
                "artifactEvidenceDigest", "storageBindingRef", "byteSize", "fileDigest",
                "mediaType", "sourceProvenanceRef", "sourceProvenanceDigest", "createdAt",
                "publicationAllowed", "payloadDigest",
            },
            "current FONT candidate",
        )
        _closed(
            validation,
            {
                "schemaVersion", "workspaceRef", "productionRunRef", "validationRef",
                "candidateRef", "candidateDigest", "fileDigest", "byteSize", "fontFormat",
                "sfntSignature", "fontFamily", "fontSubfamily", "postScriptName",
                "nameTableDigest", "variableFont", "variationAxesDigest", "rendererProbeRef",
                "rendererProbeDigest", "rendererIdentity", "rendererVersion", "ffmpegIdentity",
                "freetypeIdentity", "validationState", "failureReasons", "createdAt",
                "publicationAllowed", "payloadDigest",
            },
            "current FONT technical validation",
        )
        _closed(
            license_value,
            {
                "schemaVersion", "workspaceRef", "productionRunRef", "licenseBindingRef",
                "licenseBindingVersionRef", "versionNumber", "parentLicenseBindingVersionRef",
                "candidateRef", "candidateDigest", "fontFileDigest", "licenseSpdxId",
                "licenseTextDigest", "licenseEvidenceRef", "licenseEvidenceDigest",
                "decisionAuthorityRef", "decisionAuthorityDigest", "commercialUseAllowed",
                "technicalPreviewAllowed", "renderCandidateUseAllowed", "embeddingAllowed",
                "redistributionAllowed", "modificationAllowed", "attributionRequired",
                "reservedFontNames", "territories", "revocationState", "validFrom",
                "expiresAt", "createdAt", "publicationAllowed", "payloadDigest",
            },
            "current FONT license binding",
        )
        _closed(
            admission,
            {
                "schemaVersion", "workspaceRef", "productionRunRef", "admissionDecisionRef",
                "candidateRef", "candidateDigest", "technicalValidationRef",
                "technicalValidationDigest", "licenseBindingVersionRef",
                "licenseBindingVersionDigest", "resourceKind", "subjectDigest",
                "decisionAuthorityRef", "decisionAuthorityDigest", "decisionState", "createdAt",
                "publicationAllowed", "payloadDigest",
            },
            "current FONT admission decision",
        )
        if (
            candidate.get("schemaVersion")
            != STATIC_RESOURCE_CANDIDATE_SCHEMA_VERSION
            or candidate.get("workspaceRef") != workspace
            or candidate.get("productionRunRef") != run_ref
            or candidate.get("projectRef") != root.get("projectRef")
            or candidate.get("seriesRef") != root.get("seriesRef")
            or candidate.get("episodeRef") != root.get("episodeRef")
            or candidate.get("assetClass") != "STATIC_RESOURCE"
            or candidate.get("resourceKind") != "FONT"
            or candidate.get("candidateRef") != asset.get("candidateRef")
            or candidate.get("payloadDigest") != asset.get("candidateDigest")
            or candidate.get("fileDigest") != asset.get("fileDigest")
            or candidate.get("byteSize") != asset.get("byteSize")
            or candidate.get("mediaType") != asset.get("mediaType")
            or candidate.get("storageBindingRef")
            != asset.get("storageBindingRef")
            or candidate.get("publicationAllowed") is not False
            or validation.get("schemaVersion")
            != FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION
            or validation.get("workspaceRef") != workspace
            or validation.get("productionRunRef") != run_ref
            or validation.get("validationRef")
            != asset.get("technicalValidationRef")
            or validation.get("candidateRef") != candidate.get("candidateRef")
            or validation.get("candidateDigest")
            != candidate.get("payloadDigest")
            or validation.get("fileDigest") != candidate.get("fileDigest")
            or validation.get("byteSize") != candidate.get("byteSize")
            or validation.get("validationState") != "PASS"
            or validation.get("failureReasons") != []
            or validation.get("publicationAllowed") is not False
            or license_value.get("schemaVersion")
            != RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION
            or license_value.get("workspaceRef") != workspace
            or license_value.get("productionRunRef") != run_ref
            or license_value.get("licenseBindingVersionRef")
            != asset.get("licenseBindingVersionRef")
            or license_value.get("candidateRef") != candidate.get("candidateRef")
            or license_value.get("candidateDigest")
            != candidate.get("payloadDigest")
            or license_value.get("fontFileDigest")
            != candidate.get("fileDigest")
            or license_value.get("licenseSpdxId") not in SUPPORTED_LICENSES
            or license_value.get("revocationState") != "ACTIVE"
            or license_value.get("commercialUseAllowed") is not True
            or license_value.get("technicalPreviewAllowed") is not True
            or license_value.get("renderCandidateUseAllowed") is not True
            or license_value.get("publicationAllowed") is not False
            or admission.get("schemaVersion")
            != STATIC_RESOURCE_ADMISSION_DECISION_SCHEMA_VERSION
            or admission.get("workspaceRef") != workspace
            or admission.get("productionRunRef") != run_ref
            or admission.get("admissionDecisionRef")
            != asset.get("admissionDecisionRef")
            or admission.get("candidateRef") != candidate.get("candidateRef")
            or admission.get("candidateDigest") != candidate.get("payloadDigest")
            or admission.get("technicalValidationRef")
            != validation.get("validationRef")
            or admission.get("technicalValidationDigest")
            != validation.get("payloadDigest")
            or admission.get("licenseBindingVersionRef")
            != license_value.get("licenseBindingVersionRef")
            or admission.get("licenseBindingVersionDigest")
            != license_value.get("payloadDigest")
            or admission.get("resourceKind") != "FONT"
            or admission.get("decisionState") != "ADMIT"
            or admission.get("publicationAllowed") is not False
        ):
            raise StaleInputError("FONT admission lineage is stale")

        self.reference_evidence.require_current(
            candidate["artifactEvidenceRef"],
            candidate["artifactEvidenceDigest"],
            "FONT_ARTIFACT",
        )
        self.reference_evidence.require_current(
            candidate["sourceProvenanceRef"],
            candidate["sourceProvenanceDigest"],
            "FONT_PROVENANCE",
        )
        self.reference_evidence.require_current(
            license_value["licenseEvidenceRef"],
            license_value["licenseEvidenceDigest"],
            "FONT_LICENSE_EVIDENCE",
        )
        self.reference_evidence.require_current(
            f"license-text:{license_value['licenseSpdxId']}",
            license_value["licenseTextDigest"],
            "FONT_LICENSE_TEXT",
        )

        license_subject = {
            "subjectDigest": _digest(
                {
                    "candidateDigest": candidate["payloadDigest"],
                    "fontFileDigest": candidate["fileDigest"],
                    "licenseSpdxId": license_value["licenseSpdxId"],
                    "licenseTextDigest": license_value["licenseTextDigest"],
                    "licenseEvidenceRef": license_value["licenseEvidenceRef"],
                    "licenseEvidenceDigest": license_value[
                        "licenseEvidenceDigest"
                    ],
                }
            ),
            "candidateRef": candidate["candidateRef"],
            "fontFileDigest": candidate["fileDigest"],
            "licenseSpdxId": license_value["licenseSpdxId"],
            "licenseTextDigest": license_value["licenseTextDigest"],
            "licenseEvidenceRef": license_value["licenseEvidenceRef"],
            "licenseEvidenceDigest": license_value["licenseEvidenceDigest"],
        }
        current_license = self.license_authority.decide(license_subject)
        license_decision_fields = {
            "subjectDigest",
            "decisionAuthorityRef",
            "decisionAuthorityDigest",
            "commercialUseAllowed",
            "technicalPreviewAllowed",
            "renderCandidateUseAllowed",
            "embeddingAllowed",
            "redistributionAllowed",
            "modificationAllowed",
            "attributionRequired",
            "reservedFontNames",
            "territories",
            "revocationState",
        }
        _closed(
            current_license,
            license_decision_fields,
            "current license authority decision",
        )
        if any(
            current_license.get(field) != license_value.get(field)
            for field in license_decision_fields - {"subjectDigest"}
        ) or current_license.get("subjectDigest") != license_subject[
            "subjectDigest"
        ]:
            raise StaleInputError("FONT license authority decision is stale")

        admission_subject = {
            "subjectDigest": _digest(
                {
                    "candidateDigest": candidate["payloadDigest"],
                    "technicalValidationDigest": validation["payloadDigest"],
                    "licenseBindingVersionDigest": license_value[
                        "payloadDigest"
                    ],
                }
            ),
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "resourceKind": "FONT",
        }
        current_admission = self.admission_authority.decide(admission_subject)
        _closed(
            current_admission,
            {
                "subjectDigest",
                "decisionAuthorityRef",
                "decisionAuthorityDigest",
                "decisionState",
            },
            "current admission authority decision",
        )
        if (
            current_admission.get("subjectDigest")
            != admission_subject["subjectDigest"]
            or current_admission.get("decisionAuthorityRef")
            != admission.get("decisionAuthorityRef")
            or current_admission.get("decisionAuthorityDigest")
            != admission.get("decisionAuthorityDigest")
            or current_admission.get("decisionState") != "ADMIT"
        ):
            raise StaleInputError("FONT admission authority decision is stale")

        try:
            now = datetime.fromisoformat(self.clock().replace("Z", "+00:00"))
            valid_from = datetime.fromisoformat(
                str(license_value["validFrom"]).replace("Z", "+00:00")
            )
            expires_at = license_value.get("expiresAt")
            expiry = (
                datetime.max.replace(tzinfo=timezone.utc)
                if expires_at is None
                else datetime.fromisoformat(
                    str(expires_at).replace("Z", "+00:00")
                )
            )
            if any(value.tzinfo is None for value in (now, valid_from, expiry)):
                raise ValueError("timezone is required")
        except (TypeError, ValueError) as exc:
            raise StaleInputError("FONT license validity is invalid") from exc
        if now < valid_from or now >= expiry:
            raise StaleInputError("FONT license validity is stale")

        fd = self.storage.open_regular_file(candidate["storageBindingRef"])
        try:
            data = b""
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
        if (
            len(data) != candidate["byteSize"]
            or sha256(data).hexdigest() != candidate["fileDigest"]
        ):
            raise StaleInputError("FONT storage bytes are stale")
        facts = _parse_sfnt(
            data, candidate["mediaType"], required_text=required_text
        )
        if facts["fontFormat"] != asset.get("fontFormat") or any(
            facts.get(field) != validation.get(field) for field in facts
        ):
            raise StaleInputError("FONT technical facts are stale")

        return {
            "fontAssetVersion": sanitize_font_asset_projection(asset),
            "fontTechnicalValidation": deepcopy(validation),
            "fontLicenseBindingVersion": deepcopy(license_value),
            "storageBindingRef": candidate["storageBindingRef"],
            "publicationAllowed": False,
        }

    def open_current_font_file(
        self,
        storage_binding_ref: str,
        *,
        expected_file_digest: str,
        expected_byte_size: int,
        declared_media_type: str,
        required_text: str | None = None,
    ) -> int:
        """Return one remeasured held FONT descriptor for synchronous staging.

        Callers first resolve the canonical projection, then pass its exact file
        facts here.  Rehashing the already-open inode closes the projection-to-use
        replacement window without exposing a filesystem path.
        """

        binding = _required_ref(storage_binding_ref, "storageBindingRef")
        digest = _sha(expected_file_digest, "expectedFileDigest")
        size = _positive_int(expected_byte_size, "expectedByteSize")
        if declared_media_type not in SUPPORTED_MEDIA_TYPES:
            raise FontTechnicalValidationError("font media type is unsupported")
        fd = self.storage.open_regular_file(binding)
        try:
            data = b""
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                data += chunk
            if len(data) != size or sha256(data).hexdigest() != digest:
                raise StaleInputError("FONT storage bytes are stale")
            _parse_sfnt(
                data, declared_media_type, required_text=required_text
            )
            os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except Exception:
            os.close(fd)
            raise


__all__ = [
    "ASSET_VERSION_V2_SCHEMA_VERSION", "CanonicalStaticResourceService",
    "DirectoryStaticResourceStorage", "FONT_ASSET_VERSION_PROJECTION_SCHEMA_VERSION",
    "FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION", "FontTechnicalValidationError",
    "RejectingDigestPinnedReferenceEvidence",
    "RejectingResourceLicenseAuthority", "RejectingStaticResourceAdmissionAuthority",
    "RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION", "ResourceLicenseRequiredError",
    "STATIC_RESOURCE_ADMISSION_DECISION_SCHEMA_VERSION", "STATIC_RESOURCE_CANDIDATE_SCHEMA_VERSION",
    "StaticDigestPinnedAuthority", "StaticDigestPinnedReferenceEvidence",
    "StaticResourceAdmissionRequiredError", "StaticResourceError",
    "TECHNICAL_FIXTURE_MARKERS", "sanitize_font_asset_projection",
]
