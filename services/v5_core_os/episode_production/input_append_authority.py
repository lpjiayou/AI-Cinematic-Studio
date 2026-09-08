"""Digest-pinned authority for bounded manifest-v2 technical input append.

The authority is deliberately independent from transport authentication, external
human selection approval, and media execution configuration.  A verified grant is
an internal capability object for one exact current input subject; persisted
authority evidence never becomes a live grant by itself.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Protocol, Sequence

from .foundation import ExecutionNotAuthorizedError, _digest, _required_ref


BUNDLE_SCHEMA = "v5.m10-input-append-authority-bundle.v1"
GRANT_SCHEMA = "v5.m10-input-append-authority-grant.v1"
SUBJECT_SCHEMA = "v5.m10-input-append-authority-subject.v1"
EVIDENCE_SCHEMA = "v5.method-aware-input-append-authority-decision.v1"
EVIDENCE_RECORD_KIND = "MethodAwareInputAppendAuthority"
CONFIG_NAMES = (
    "CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_PATH",
    "CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_SHA256",
)
MAX_BUNDLE_BYTES = 1024 * 1024
MAX_GRANTS = 1000
ALLOWED_OPERATIONS = (
    "TECHNICAL_INPUT_INTAKE",
    "SEMANTIC_VISUAL_QC",
    "HUMAN_SELECTION",
    "INPUT_ADMISSION",
    "METHOD_AWARE_INPUT_PLAN",
)
EXCLUDED_OPERATIONS = (
    "PROVIDER_PROCESSING",
    "MEDIA_GENERATION",
    "VIDEO_RESULT_INTAKE",
    "OUTPUT_SELECTION",
    "OUTPUT_ADMISSION",
    "EXECUTION_DISPATCH",
    "MASTER_OR_EXPORT",
    "PUBLICATION",
)

SCOPE_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
    }
)
M6_FIELDS = frozenset(
    {
        "m6ConsumerBindingDigest",
        "m6BaselineSnapshotRef",
        "m6BaselineCanonicalDigest",
        "activationRevision",
        "seriesPlanVersionRef",
        "seriesPlanVersionDigest",
        "seriesBibleVersionRef",
        "seriesBibleVersionDigest",
        "characterContinuityVersionRef",
        "characterContinuityVersionDigest",
    }
)
SOURCE_SPAN_FIELDS = frozenset(
    {
        "scriptSceneRef",
        "sourceField",
        "sourceIndex",
        "startOffsetInclusive",
        "endOffsetExclusive",
    }
)
SUBJECT_FIELDS = frozenset(
    {
        "schemaVersion",
        *SCOPE_FIELDS,
        "productionRunPayloadDigest",
        "manifestSchemaVersion",
        "manifestDigest",
        "upstreamDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        *M6_FIELDS,
        "consistencyValidationVersionRef",
        "consistencyValidationDigest",
        "executionMethodPlanVersionRef",
        "executionMethodPlanDigest",
        "visualExecutionRequirementRef",
        "visualExecutionRequirementDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "actionExecutionBeatRef",
        "actionExecutionBeatDigest",
        "sourceSpan",
        "sourceTextDigest",
        "executionClass",
        "executionMethod",
        "inputRequirementKey",
        "stagedArtifactRef",
        "stagedArtifactDigest",
        "artifactContentDigest",
        "artifactMediaType",
        "artifactByteSize",
        "mediaKind",
        "inputRole",
        "authorityState",
        "shotPlanAuthorityState",
        "shotPlanApprovalState",
        "cameraContractState",
        "dispatchAllowed",
        "providerProcessingAuthorized",
        "publicationAllowed",
        "payloadDigest",
    }
)
GRANT_FIELDS = frozenset(
    {
        "schemaVersion",
        "inputAppendAuthorityRef",
        "version",
        "subject",
        "subjectDigest",
        "allowedOperations",
        "excludedOperations",
        "decision",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "decidedAt",
        "payloadDigest",
    }
)
EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        *SCOPE_FIELDS,
        "inputAppendAuthorityRef",
        "version",
        "authorityRef",
        "subject",
        "subjectDigest",
        "allowedOperations",
        "excludedOperations",
        "decision",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "decidedAt",
        "providerProcessingAuthorized",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class InputAppendAuthorityConfigurationError(ValueError):
    """The configured authority source is incomplete or invalid."""


def _hex_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise InputAppendAuthorityConfigurationError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except (TypeError, ValueError) as exc:
        raise InputAppendAuthorityConfigurationError(f"{field} is invalid") from exc


def _positive_int(value: Any, field: str, maximum: int = 10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise InputAppendAuthorityConfigurationError(f"{field} is invalid")
    return value


def _exact(value: Any, fields: Sequence[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise InputAppendAuthorityConfigurationError(f"{label} fields are invalid")
    return value


def _strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InputAppendAuthorityConfigurationError(
                    "authority bundle contains duplicate JSON keys"
                )
            result[key] = value
        return result

    def invalid_number(value: str) -> None:
        raise InputAppendAuthorityConfigurationError(
            "authority bundle contains a non-canonical number"
        )

    def integer(value: str) -> int:
        if len(value) > 128:
            invalid_number(value)
        return int(value)

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_number,
            parse_float=invalid_number,
            parse_int=integer,
        )

        def depth(item: Any, level: int = 0) -> None:
            if level > 64:
                raise InputAppendAuthorityConfigurationError(
                    "authority bundle is nested too deeply"
                )
            if isinstance(item, dict):
                for nested in item.values():
                    depth(nested, level + 1)
            elif isinstance(item, list):
                for nested in item:
                    depth(nested, level + 1)

        depth(value)
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return value
    except InputAppendAuthorityConfigurationError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise InputAppendAuthorityConfigurationError(
            "authority bundle JSON is invalid"
        ) from exc


def _open_regular(path: Path) -> int:
    if not path.is_absolute():
        raise InputAppendAuthorityConfigurationError(
            "authority bundle path must be absolute"
        )
    normalized = Path(os.path.abspath(path))
    descriptor = os.open(normalized.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in normalized.parts[1:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            normalized.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            os.close(file_descriptor)
            raise InputAppendAuthorityConfigurationError(
                "authority bundle must be a regular file"
            )
        return file_descriptor
    except OSError as exc:
        raise InputAppendAuthorityConfigurationError(
            "authority bundle cannot be opened safely"
        ) from exc
    finally:
        os.close(descriptor)


def _read_regular(path: Path) -> bytes:
    descriptor = _open_regular(path)
    try:
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not 0 < before.st_size <= MAX_BUNDLE_BYTES:
                raise InputAppendAuthorityConfigurationError(
                    "authority bundle size is invalid"
                )
            data = stream.read(MAX_BUNDLE_BYTES + 1)
            after = os.fstat(stream.fileno())
            stable_fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if len(data) != before.st_size or any(
                getattr(before, field) != getattr(after, field)
                for field in stable_fields
            ):
                raise InputAppendAuthorityConfigurationError(
                    "authority bundle changed during read"
                )
            return data
    except OSError as exc:
        raise InputAppendAuthorityConfigurationError(
            "authority bundle cannot be read safely"
        ) from exc


def validate_subject(value: Any) -> dict[str, Any]:
    subject = deepcopy(dict(_exact(value, SUBJECT_FIELDS, "authority subject")))
    if subject["schemaVersion"] != SUBJECT_SCHEMA:
        raise InputAppendAuthorityConfigurationError(
            "authority subject schema is invalid"
        )
    for field in SCOPE_FIELDS | {
        "scriptVersionRef",
        "m6BaselineSnapshotRef",
        "seriesPlanVersionRef",
        "seriesBibleVersionRef",
        "characterContinuityVersionRef",
        "consistencyValidationVersionRef",
        "executionMethodPlanVersionRef",
        "visualExecutionRequirementRef",
        "creativeShotVersionRef",
        "actionExecutionBeatRef",
        "inputRequirementKey",
        "stagedArtifactRef",
    }:
        _ref(subject[field], field)
    for field in {
        "productionRunPayloadDigest",
        "manifestDigest",
        "upstreamDigest",
        "scriptVersionDigest",
        "m6ConsumerBindingDigest",
        "m6BaselineCanonicalDigest",
        "seriesPlanVersionDigest",
        "seriesBibleVersionDigest",
        "characterContinuityVersionDigest",
        "consistencyValidationDigest",
        "executionMethodPlanDigest",
        "visualExecutionRequirementDigest",
        "creativeShotVersionDigest",
        "actionExecutionBeatDigest",
        "sourceTextDigest",
        "stagedArtifactDigest",
        "artifactContentDigest",
        "payloadDigest",
    }:
        _hex_digest(subject[field], field)
    _positive_int(subject["activationRevision"], "activationRevision", 1_000_000)
    _positive_int(subject["artifactByteSize"], "artifactByteSize")
    span = _exact(subject["sourceSpan"], SOURCE_SPAN_FIELDS, "sourceSpan")
    _ref(span["scriptSceneRef"], "sourceSpan.scriptSceneRef")
    if span["sourceField"] not in {"ACTION", "DIALOGUE", "NARRATION", "SUBTITLE_TEXT"}:
        raise InputAppendAuthorityConfigurationError("sourceSpan.sourceField is invalid")
    for field in ("sourceIndex", "startOffsetInclusive", "endOffsetExclusive"):
        if isinstance(span[field], bool) or not isinstance(span[field], int) or span[field] < 0:
            raise InputAppendAuthorityConfigurationError(f"sourceSpan.{field} is invalid")
    if span["endOffsetExclusive"] <= span["startOffsetInclusive"]:
        raise InputAppendAuthorityConfigurationError("sourceSpan range is invalid")
    fixed = {
        "manifestSchemaVersion": "k2.golden-episode.manifest.v2",
        "executionClass": "MICRO_MOTION",
        "executionMethod": "SINGLE_ANCHOR_I2V",
        "mediaKind": "IMAGE",
        "inputRole": "ACTION_READY_ANCHOR",
        "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        "shotPlanAuthorityState": "LOCAL_STRUCTURAL_REPRESENTATION_ONLY",
        "shotPlanApprovalState": "NOT_VERIFIED",
        "cameraContractState": "NOT_READY",
    }
    if any(subject[field] != expected for field, expected in fixed.items()):
        raise InputAppendAuthorityConfigurationError(
            "authority subject fixed safety fields are invalid"
        )
    if subject["artifactMediaType"] not in {"image/png", "image/jpeg"}:
        raise InputAppendAuthorityConfigurationError(
            "authority subject artifactMediaType is invalid"
        )
    if any(
        subject[field] is not False
        for field in (
            "dispatchAllowed",
            "providerProcessingAuthorized",
            "publicationAllowed",
        )
    ):
        raise InputAppendAuthorityConfigurationError(
            "authority subject permission fields are invalid"
        )
    expected_key = (
        "action-ready-anchor:" + subject["visualExecutionRequirementRef"]
    )
    if subject["inputRequirementKey"] != expected_key:
        raise InputAppendAuthorityConfigurationError(
            "authority subject inputRequirementKey is invalid"
        )
    embedded = dict(subject)
    payload_digest = embedded.pop("payloadDigest")
    if payload_digest != _digest(embedded):
        raise InputAppendAuthorityConfigurationError(
            "authority subject payloadDigest is invalid"
        )
    return subject


def seal_subject(value: Mapping[str, Any]) -> dict[str, Any]:
    if "payloadDigest" in value:
        raise InputAppendAuthorityConfigurationError(
            "unsealed authority subject fields are invalid"
        )
    subject = deepcopy(dict(value))
    subject["payloadDigest"] = _digest(subject)
    return validate_subject(subject)


def _decision_digest(
    *,
    authority_ref: str,
    input_append_authority_ref: str,
    version: int,
    subject_digest: str,
    allowed_operations: Sequence[str],
    excluded_operations: Sequence[str],
    decision: str,
    authority_decision_ref: str,
    decided_at: str,
) -> str:
    return _digest(
        {
            "authorityRef": authority_ref,
            "inputAppendAuthorityRef": input_append_authority_ref,
            "version": version,
            "subjectDigest": subject_digest,
            "allowedOperations": list(allowed_operations),
            "excludedOperations": list(excluded_operations),
            "decision": decision,
            "authorityDecisionRef": authority_decision_ref,
            "decidedAt": decided_at,
        }
    )


@dataclass(frozen=True, slots=True)
class VerifiedInputAppendAuthority:
    authority_ref: str
    input_append_authority_ref: str
    version: int
    subject: Mapping[str, Any]
    subject_digest: str
    allowed_operations: tuple[str, ...]
    excluded_operations: tuple[str, ...]
    decision: str
    authority_decision_ref: str
    authority_decision_digest: str
    decided_at: str

    def permits(self, *, subject: Mapping[str, Any], operation: str) -> bool:
        try:
            candidate = validate_subject(subject)
        except InputAppendAuthorityConfigurationError:
            return False
        return (
            self.decision == "APPROVED"
            and operation in self.allowed_operations
            and operation not in self.excluded_operations
            and candidate == self.subject
            and candidate["payloadDigest"] == self.subject_digest
        )

    def matches_run(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        operation: str,
    ) -> bool:
        return (
            operation in self.allowed_operations
            and self.subject.get("workspaceRef") == workspace_ref
            and self.subject.get("productionRunRef") == production_run_ref
        )

    def matches_input_candidate(self, candidate: Mapping[str, Any]) -> bool:
        """Bind the internal review exception to its one deterministic input."""
        subject = self.subject
        identity = _digest(
            {
                **{field: subject.get(field) for field in SCOPE_FIELDS},
                "executionMethodPlanVersionRef": subject.get(
                    "executionMethodPlanVersionRef"
                ),
                "executionMethodPlanDigest": subject.get(
                    "executionMethodPlanDigest"
                ),
                "visualExecutionRequirementRef": subject.get(
                    "visualExecutionRequirementRef"
                ),
                "visualExecutionRequirementDigest": subject.get(
                    "visualExecutionRequirementDigest"
                ),
                "stagedArtifactRef": subject.get("stagedArtifactRef"),
                "stagedArtifactDigest": subject.get("stagedArtifactDigest"),
            }
        )[:40]
        expected = {
            "schemaVersion": "v5.k2-media-candidate.v1",
            "candidateRef": "input-candidate-" + identity,
            "candidateVersion": 1,
            "rootPayloadDigest": subject.get("productionRunPayloadDigest"),
            "revisionRef": "input-artifact-" + identity,
            "mediaKind": "IMAGE",
            "slotRef": subject.get("creativeShotVersionRef"),
            "sourceRequestRef": subject.get("visualExecutionRequirementRef"),
            "sourceRequestDigest": subject.get(
                "visualExecutionRequirementDigest"
            ),
            "artifactRef": subject.get("stagedArtifactRef"),
            "artifactDigest": subject.get("artifactContentDigest"),
            "artifactByteSize": subject.get("artifactByteSize"),
            "sourceAssetVersions": [],
            "provenance": "IMPORTED",
            "lifecycleState": "CANDIDATE_RECORDED",
            "publicationAllowed": False,
        }
        return isinstance(candidate, Mapping) and all(
            candidate.get(field) == value for field, value in expected.items()
        )

    def evidence_payload(self, *, created_at: str) -> dict[str, Any]:
        payload = {
            "schemaVersion": EVIDENCE_SCHEMA,
            **{field: self.subject[field] for field in SCOPE_FIELDS},
            "inputAppendAuthorityRef": self.input_append_authority_ref,
            "version": self.version,
            "authorityRef": self.authority_ref,
            "subject": deepcopy(dict(self.subject)),
            "subjectDigest": self.subject_digest,
            "allowedOperations": list(self.allowed_operations),
            "excludedOperations": list(self.excluded_operations),
            "decision": self.decision,
            "authorityDecisionRef": self.authority_decision_ref,
            "authorityDecisionDigest": self.authority_decision_digest,
            "decidedAt": self.decided_at,
            "providerProcessingAuthorized": False,
            "publicationAllowed": False,
            "createdAt": created_at,
        }
        payload["payloadDigest"] = _digest(payload)
        validate_evidence(payload)
        return payload


def _validated_grant(
    authority_ref: str, value: Any
) -> VerifiedInputAppendAuthority:
    grant = deepcopy(dict(_exact(value, GRANT_FIELDS, "authority grant")))
    if (
        grant["schemaVersion"] != GRANT_SCHEMA
        or type(grant["version"]) is not int
        or grant["version"] != 1
    ):
        raise InputAppendAuthorityConfigurationError(
            "authority grant schema or version is invalid"
        )
    input_ref = _ref(
        grant["inputAppendAuthorityRef"], "inputAppendAuthorityRef"
    )
    subject = validate_subject(grant["subject"])
    subject_digest = _hex_digest(grant["subjectDigest"], "subjectDigest")
    if subject_digest != subject["payloadDigest"]:
        raise InputAppendAuthorityConfigurationError(
            "authority grant subjectDigest is invalid"
        )
    if grant["allowedOperations"] != list(ALLOWED_OPERATIONS):
        raise InputAppendAuthorityConfigurationError(
            "authority grant allowedOperations are invalid"
        )
    if grant["excludedOperations"] != list(EXCLUDED_OPERATIONS):
        raise InputAppendAuthorityConfigurationError(
            "authority grant excludedOperations are invalid"
        )
    if grant["decision"] != "APPROVED":
        raise InputAppendAuthorityConfigurationError(
            "authority grant decision is invalid"
        )
    decision_ref = _ref(grant["authorityDecisionRef"], "authorityDecisionRef")
    decided_at = _ref(grant["decidedAt"], "decidedAt")
    decision_digest = _hex_digest(
        grant["authorityDecisionDigest"], "authorityDecisionDigest"
    )
    expected_decision_digest = _decision_digest(
        authority_ref=authority_ref,
        input_append_authority_ref=input_ref,
        version=1,
        subject_digest=subject_digest,
        allowed_operations=ALLOWED_OPERATIONS,
        excluded_operations=EXCLUDED_OPERATIONS,
        decision="APPROVED",
        authority_decision_ref=decision_ref,
        decided_at=decided_at,
    )
    if decision_digest != expected_decision_digest:
        raise InputAppendAuthorityConfigurationError(
            "authority grant decision digest is invalid"
        )
    embedded = dict(grant)
    payload_digest = _hex_digest(embedded.pop("payloadDigest"), "payloadDigest")
    if payload_digest != _digest(embedded):
        raise InputAppendAuthorityConfigurationError(
            "authority grant payloadDigest is invalid"
        )
    return VerifiedInputAppendAuthority(
        authority_ref=authority_ref,
        input_append_authority_ref=input_ref,
        version=1,
        subject=subject,
        subject_digest=subject_digest,
        allowed_operations=ALLOWED_OPERATIONS,
        excluded_operations=EXCLUDED_OPERATIONS,
        decision="APPROVED",
        authority_decision_ref=decision_ref,
        authority_decision_digest=decision_digest,
        decided_at=decided_at,
    )


def create_grant(
    *,
    authority_ref: str,
    input_append_authority_ref: str,
    subject: Mapping[str, Any],
    authority_decision_ref: str,
    decided_at: str,
) -> dict[str, Any]:
    authority = _ref(authority_ref, "authorityRef")
    input_ref = _ref(input_append_authority_ref, "inputAppendAuthorityRef")
    decision_ref = _ref(authority_decision_ref, "authorityDecisionRef")
    timestamp = _ref(decided_at, "decidedAt")
    normalized_subject = validate_subject(subject)
    grant = {
        "schemaVersion": GRANT_SCHEMA,
        "inputAppendAuthorityRef": input_ref,
        "version": 1,
        "subject": normalized_subject,
        "subjectDigest": normalized_subject["payloadDigest"],
        "allowedOperations": list(ALLOWED_OPERATIONS),
        "excludedOperations": list(EXCLUDED_OPERATIONS),
        "decision": "APPROVED",
        "authorityDecisionRef": decision_ref,
        "authorityDecisionDigest": _decision_digest(
            authority_ref=authority,
            input_append_authority_ref=input_ref,
            version=1,
            subject_digest=normalized_subject["payloadDigest"],
            allowed_operations=ALLOWED_OPERATIONS,
            excluded_operations=EXCLUDED_OPERATIONS,
            decision="APPROVED",
            authority_decision_ref=decision_ref,
            decided_at=timestamp,
        ),
        "decidedAt": timestamp,
    }
    grant["payloadDigest"] = _digest(grant)
    _validated_grant(authority, grant)
    return grant


def create_bundle(
    *, authority_ref: str, grants: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    bundle = {
        "schemaVersion": BUNDLE_SCHEMA,
        "authorityRef": _ref(authority_ref, "authorityRef"),
        "grants": [deepcopy(dict(grant)) for grant in grants],
    }
    _authority_from_bundle(bundle)
    return bundle


def validate_evidence(value: Any) -> dict[str, Any]:
    evidence = deepcopy(dict(_exact(value, EVIDENCE_FIELDS, "authority evidence")))
    if (
        evidence["schemaVersion"] != EVIDENCE_SCHEMA
        or type(evidence["version"]) is not int
        or evidence["version"] != 1
        or evidence["decision"] != "APPROVED"
        or evidence["allowedOperations"] != list(ALLOWED_OPERATIONS)
        or evidence["excludedOperations"] != list(EXCLUDED_OPERATIONS)
        or evidence["providerProcessingAuthorized"] is not False
        or evidence["publicationAllowed"] is not False
    ):
        raise InputAppendAuthorityConfigurationError(
            "authority evidence fixed fields are invalid"
        )
    for field in SCOPE_FIELDS | {
        "inputAppendAuthorityRef",
        "authorityRef",
        "authorityDecisionRef",
        "decidedAt",
        "createdAt",
    }:
        _ref(evidence[field], field)
    subject = validate_subject(evidence["subject"])
    if any(evidence[field] != subject[field] for field in SCOPE_FIELDS):
        raise InputAppendAuthorityConfigurationError(
            "authority evidence scope is invalid"
        )
    if evidence["subjectDigest"] != subject["payloadDigest"]:
        raise InputAppendAuthorityConfigurationError(
            "authority evidence subjectDigest is invalid"
        )
    _hex_digest(evidence["subjectDigest"], "subjectDigest")
    expected_decision = _decision_digest(
        authority_ref=evidence["authorityRef"],
        input_append_authority_ref=evidence["inputAppendAuthorityRef"],
        version=1,
        subject_digest=evidence["subjectDigest"],
        allowed_operations=ALLOWED_OPERATIONS,
        excluded_operations=EXCLUDED_OPERATIONS,
        decision="APPROVED",
        authority_decision_ref=evidence["authorityDecisionRef"],
        decided_at=evidence["decidedAt"],
    )
    if evidence["authorityDecisionDigest"] != expected_decision:
        raise InputAppendAuthorityConfigurationError(
            "authority evidence decision digest is invalid"
        )
    embedded = dict(evidence)
    payload_digest = _hex_digest(embedded.pop("payloadDigest"), "payloadDigest")
    if payload_digest != _digest(embedded):
        raise InputAppendAuthorityConfigurationError(
            "authority evidence payloadDigest is invalid"
        )
    return evidence


class InputAppendAuthorityPort(Protocol):
    def verify(
        self, *, subject: Mapping[str, Any], operation: str
    ) -> VerifiedInputAppendAuthority: ...


class RejectingInputAppendAuthority:
    def verify(
        self, *, subject: Mapping[str, Any], operation: str
    ) -> VerifiedInputAppendAuthority:
        raise ExecutionNotAuthorizedError(
            "manifest v2 technical input append authority is required"
        )


class DigestPinnedInputAppendAuthority:
    def __init__(self, bundle_path: Path | str, expected_sha256: str) -> None:
        self._bundle_path = Path(bundle_path)
        if not self._bundle_path.is_absolute():
            raise InputAppendAuthorityConfigurationError(
                "authority bundle path must be absolute"
            )
        self._expected_sha256 = _hex_digest(
            expected_sha256, "authority bundle SHA-256"
        )
        self._load()

    def _load(self) -> dict[str, VerifiedInputAppendAuthority]:
        data = _read_regular(self._bundle_path)
        if sha256(data).hexdigest() != self._expected_sha256:
            raise InputAppendAuthorityConfigurationError(
                "authority bundle SHA-256 does not match"
            )
        return _authority_from_bundle(_strict_json(data))

    def verify(
        self, *, subject: Mapping[str, Any], operation: str
    ) -> VerifiedInputAppendAuthority:
        try:
            normalized = validate_subject(subject)
            if operation not in ALLOWED_OPERATIONS:
                raise InputAppendAuthorityConfigurationError(
                    "authority operation is not allowed"
                )
            grants = self._load()
            grant = grants.get(normalized["payloadDigest"])
            if grant is None or not grant.permits(
                subject=normalized, operation=operation
            ):
                raise InputAppendAuthorityConfigurationError(
                    "authority was not resolved for the exact subject"
                )
            return grant
        except InputAppendAuthorityConfigurationError as exc:
            raise ExecutionNotAuthorizedError(
                "manifest v2 technical input append authority is invalid"
            ) from exc


def _authority_from_bundle(
    value: Any,
) -> dict[str, VerifiedInputAppendAuthority]:
    bundle = _exact(
        value, {"schemaVersion", "authorityRef", "grants"}, "authority bundle"
    )
    if bundle["schemaVersion"] != BUNDLE_SCHEMA:
        raise InputAppendAuthorityConfigurationError(
            "authority bundle schema is invalid"
        )
    authority_ref = _ref(bundle["authorityRef"], "authorityRef")
    raw_grants = bundle["grants"]
    if (
        not isinstance(raw_grants, list)
        or not raw_grants
        or len(raw_grants) > MAX_GRANTS
    ):
        raise InputAppendAuthorityConfigurationError(
            "authority bundle grants are invalid"
        )
    grants: dict[str, VerifiedInputAppendAuthority] = {}
    input_refs: set[str] = set()
    decision_refs: set[str] = set()
    decision_digests: set[str] = set()
    for raw in raw_grants:
        grant = _validated_grant(authority_ref, raw)
        if (
            grant.subject_digest in grants
            or grant.input_append_authority_ref in input_refs
            or grant.authority_decision_ref in decision_refs
            or grant.authority_decision_digest in decision_digests
        ):
            raise InputAppendAuthorityConfigurationError(
                "authority bundle grant identity is duplicated"
            )
        grants[grant.subject_digest] = grant
        input_refs.add(grant.input_append_authority_ref)
        decision_refs.add(grant.authority_decision_ref)
        decision_digests.add(grant.authority_decision_digest)
    return grants


def input_append_authority_from_environment(
    environ: Mapping[str, str],
) -> InputAppendAuthorityPort:
    configured = {
        name: str(environ.get(name, "")).strip() for name in CONFIG_NAMES
    }
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingInputAppendAuthority()
    if len(present) != len(CONFIG_NAMES):
        raise InputAppendAuthorityConfigurationError(
            "input append authority configuration is incomplete"
        )
    return DigestPinnedInputAppendAuthority(
        configured[CONFIG_NAMES[0]], configured[CONFIG_NAMES[1]]
    )


__all__ = [
    "ALLOWED_OPERATIONS",
    "BUNDLE_SCHEMA",
    "CONFIG_NAMES",
    "DigestPinnedInputAppendAuthority",
    "EVIDENCE_FIELDS",
    "EVIDENCE_RECORD_KIND",
    "EVIDENCE_SCHEMA",
    "EXCLUDED_OPERATIONS",
    "GRANT_SCHEMA",
    "InputAppendAuthorityConfigurationError",
    "InputAppendAuthorityPort",
    "RejectingInputAppendAuthority",
    "SUBJECT_FIELDS",
    "SUBJECT_SCHEMA",
    "VerifiedInputAppendAuthority",
    "create_bundle",
    "create_grant",
    "input_append_authority_from_environment",
    "seal_subject",
    "validate_evidence",
    "validate_subject",
]
