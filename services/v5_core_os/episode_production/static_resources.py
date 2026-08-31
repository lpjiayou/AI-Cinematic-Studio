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


def _parse_sfnt(data: bytes, declared_media_type: str) -> dict[str, Any]:
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
        fd = self.storage.open_regular_file(candidate["storageBindingRef"])
        try:
            data = b""
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk: break
                data += chunk
            if len(data) != candidate["byteSize"] or sha256(data).hexdigest() != candidate["fileDigest"]:
                raise StaleInputError("font file changed after candidacy")
            facts = _parse_sfnt(data, candidate["mediaType"])
            os.lseek(fd, 0, os.SEEK_SET)
            probe = _renderer_probe(fd, self.ffmpeg_executable, str(command.get("testText")))
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
