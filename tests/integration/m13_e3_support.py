"""Shared real-boundary fixtures for the M13-E3 vertical integration test.

Everything in this module is test-only authority data.  It deliberately uses
the production readers and evidence journal, but never writes to a live asset,
identity, master, export, or publication repository.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.static_resources import (
    CanonicalStaticResourceService,
    DirectoryStaticResourceStorage,
    FontTechnicalValidationError,
    StaticDigestPinnedAuthority,
    StaticDigestPinnedReferenceEvidence,
    _parse_sfnt,
)


TEXT = "长安"
LANGUAGE = "und"
CHARACTER_REF = "character-lin"
SCRIPT_REF = "script-m13-e3"
SCRIPT_VERSION_REF = "script-version-m13-e3"
CREATED_AT = "2026-08-31T10:00:00Z"
FONT_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "v5_fonts"


def script_version() -> dict[str, Any]:
    """Return the exact current ScriptVersion projected by the test reader."""

    return {
        "scriptVersionRef": SCRIPT_VERSION_REF,
        "title": TEXT,
    }


SCRIPT_VERSION_DIGEST = _digest(script_version())


class CurrentScriptTextReader:
    """Small current-reader double with observable fresh read behavior."""

    def __init__(self, run: Mapping[str, Any]) -> None:
        self.run = deepcopy(dict(run))
        self.calls: list[tuple[str, str, str]] = []
        self.available = True
        self.version = script_version()

    def get_workspace(
        self, workspace_ref: str, series_ref: str, episode_ref: str
    ) -> dict[str, Any]:
        self.calls.append((workspace_ref, series_ref, episode_ref))
        if not self.available:
            raise RepositoryUnavailableError("SCRIPT_TEXT authority unavailable")
        if (workspace_ref, series_ref, episode_ref) != (
            self.run["workspaceRef"],
            self.run["seriesRef"],
            self.run["episodeRef"],
        ):
            raise StaleInputError("SCRIPT_TEXT scope drifted")
        return {
            "script": {
                "scriptRef": SCRIPT_REF,
                "confirmedScriptVersionRef": SCRIPT_VERSION_REF,
            },
            "versions": [deepcopy(self.version)],
        }


def identity_decision() -> dict[str, str]:
    return {
        "referenceRef": "identity-reference-character-lin",
        "referenceVersionRef": "identity-reference-version-character-lin-1",
        "contentDigest": sha256(b"character-lin:local-reference:v1").hexdigest(),
        "mediaType": "image",
        "rightsState": "LOCAL_EVIDENCE_ONLY",
        "provenance": "LOCAL_EVIDENCE",
        "approvalRef": "local-evidence-approval-character-lin",
    }


class CurrentIdentityProjectionReader:
    """Fresh-reader fixture implementing the exact seven-field decision."""

    def __init__(self, run: Mapping[str, Any]) -> None:
        self.run = deepcopy(dict(run))
        self.decision = identity_decision()
        self.available = True
        self.calls: list[tuple[str, str, str]] = []

    def require_current_identity_reference_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        character_ref: str,
    ) -> dict[str, Any]:
        self.calls.append((workspace_ref, production_run_ref, character_ref))
        if not self.available:
            raise RepositoryUnavailableError("identity authority unavailable")
        if (workspace_ref, production_run_ref, character_ref) != (
            self.run["workspaceRef"],
            self.run["productionRunRef"],
            CHARACTER_REF,
        ):
            raise StaleInputError("identity projection scope drifted")
        base = {
            "schemaVersion": "v5.identity-reference-version-projection.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "characterRef": character_ref,
            "scriptCharacterName": "林澈",
            "identityLockRef": "identity-lock-m13-e3",
            "identityLockVersionRef": "identity-lock-version-m13-e3-1",
            "identityLockDigest": "1" * 64,
            **deepcopy(self.decision),
            "externalDecisionDigest": _digest(self.decision),
        }
        return {
            **base,
            "projectionCheckedAt": CREATED_AT,
            "projectionDigest": _digest(base),
        }


class CurrentRealMediaAuthority:
    """One current real-video base and one canonical RGBA image mark."""

    def __init__(
        self,
        run: Mapping[str, Any],
        base: Mapping[str, Any],
        mark: Mapping[str, Any],
    ) -> None:
        self.run = deepcopy(dict(run))
        self.base = deepcopy(dict(base))
        self.mark = deepcopy(dict(mark))
        self.calls: list[Any] = []

    def get_revision_bundle(
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        evidence_snapshot=None,
    ) -> dict[str, Any]:
        if (workspace_ref, production_run_ref) != (
            self.run["workspaceRef"],
            self.run["productionRunRef"],
        ):
            raise StaleInputError("real media authority scope drifted")
        self.calls.append(evidence_snapshot)
        return {
            "videoAssetVersions": [deepcopy(self.base)],
            "assetVersions": [deepcopy(self.mark)],
            "videoLineageState": {"state": "CURRENT"},
            "publicationAllowed": False,
        }


def canonical_mark_asset(
    *, run: Mapping[str, Any], base: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    value = {
        "schemaVersion": "v5.k2-real-image-asset-version.v1",
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "creativeShotRef": base["creativeShotRef"],
        "creativeShotVersionRef": base["creativeShotVersionRef"],
        "creativeShotDigest": base["creativeShotDigest"],
        "assetVersionRef": "asset-version-m13-e3-canonical-face-mark",
        "mediaKind": "IMAGE",
        "mediaType": "image/png",
        "state": "REGISTERED",
        "immutable": True,
        "storageKey": source["storageKey"],
        "byteSize": source["byteSize"],
        "sha256": source["sha256"],
        "publicationAllowed": False,
    }
    return {**value, "payloadDigest": _digest(value)}


class _CurrentRoot:
    def __init__(self, run: Mapping[str, Any]) -> None:
        self.run = deepcopy(dict(run))
        self.calls = 0

    def verify_run_current(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        self.calls += 1
        if (workspace_ref, production_run_ref) != (
            self.run["workspaceRef"],
            self.run["productionRunRef"],
        ):
            raise StaleInputError("FONT root scope drifted")
        return deepcopy(self.run)


class _Refs:
    def __init__(self) -> None:
        self.next = 0

    def __call__(self, prefix: str) -> str:
        self.next += 1
        return f"{prefix}-m13-e3-{self.next}"


def find_cjk_font_fixture() -> Path:
    for path in sorted(FONT_FIXTURE_ROOT.glob("*.ttf")):
        try:
            _parse_sfnt(path.read_bytes(), "font/ttf", required_text=TEXT)
        except FontTechnicalValidationError:
            continue
        return path
    raise AssertionError(
        "M13-E3 requires a licensed technical TTF fixture with 长安 glyphs"
    )


@dataclass(frozen=True)
class FontAuthorityFixture:
    service: CanonicalStaticResourceService
    asset: dict[str, Any]
    font_path: Path
    reference_facts: dict[str, dict[str, str]]
    license_decision: dict[str, Any]
    admission_decision: dict[str, Any]


def _font_service(
    *,
    run: Mapping[str, Any],
    evidence,
    font_path: Path,
    reference_facts: Mapping[str, Mapping[str, str]],
    license_decision: Mapping[str, Any] | None = None,
    admission_decision: Mapping[str, Any] | None = None,
) -> CanonicalStaticResourceService:
    return CanonicalStaticResourceService(
        _CurrentRoot(run),
        evidence,
        storage=DirectoryStaticResourceStorage(
            font_path.parent, {"font-m13-e3": font_path.name}
        ),
        reference_evidence=StaticDigestPinnedReferenceEvidence(reference_facts),
        license_authority=(
            StaticDigestPinnedAuthority(
                {license_decision["subjectDigest"]: license_decision}
            )
            if license_decision is not None
            else None
        ),
        admission_authority=(
            StaticDigestPinnedAuthority(
                {admission_decision["subjectDigest"]: admission_decision}
            )
            if admission_decision is not None
            else None
        ),
        clock=lambda: CREATED_AT,
        ref_factory=_Refs(),
    )


def admit_canonical_font(*, run: Mapping[str, Any], evidence) -> FontAuthorityFixture:
    font_path = find_cjk_font_fixture()
    font_bytes = font_path.read_bytes()
    font_digest = sha256(font_bytes).hexdigest()
    license_path = FONT_FIXTURE_ROOT / "OFL.txt"
    license_digest = sha256(license_path.read_bytes()).hexdigest()
    reference_facts = {
        "artifact-font-m13-e3": {"payloadDigest": "2" * 64},
        "provenance-font-m13-e3": {"payloadDigest": "3" * 64},
        "font-license-evidence-m13-e3": {"payloadDigest": "4" * 64},
        "license-text:OFL-1.1": {"payloadDigest": license_digest},
    }
    service = _font_service(
        run=run,
        evidence=evidence,
        font_path=font_path,
        reference_facts=reference_facts,
    )
    candidate = service.create_candidate(
        {
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "m13-e3-font-candidate",
            "candidateRef": "font-candidate-m13-e3",
            "candidateVersion": 1,
            "assetClass": "STATIC_RESOURCE",
            "resourceKind": "FONT",
            "artifactEvidenceRef": "artifact-font-m13-e3",
            "artifactEvidenceDigest": "2" * 64,
            "storageBindingRef": "font-m13-e3",
            "byteSize": len(font_bytes),
            "fileDigest": font_digest,
            "mediaType": "font/ttf",
            "sourceProvenanceRef": "provenance-font-m13-e3",
            "sourceProvenanceDigest": "3" * 64,
        }
    )
    validation = service.validate_font(
        {
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "m13-e3-font-validation",
            "candidateRef": candidate["candidateRef"],
            "candidateVersion": candidate["candidateVersion"],
            "candidateDigest": candidate["payloadDigest"],
            "validationRef": "font-validation-m13-e3",
            "testText": TEXT,
        }
    )
    license_subject = _digest(
        {
            "candidateDigest": candidate["payloadDigest"],
            "fontFileDigest": candidate["fileDigest"],
            "licenseSpdxId": "OFL-1.1",
            "licenseTextDigest": license_digest,
            "licenseEvidenceRef": "font-license-evidence-m13-e3",
            "licenseEvidenceDigest": "4" * 64,
        }
    )
    license_decision = {
        "subjectDigest": license_subject,
        "decisionAuthorityRef": "rights-owner-m13-e3",
        "decisionAuthorityDigest": "5" * 64,
        "commercialUseAllowed": True,
        "technicalPreviewAllowed": True,
        "renderCandidateUseAllowed": True,
        "embeddingAllowed": True,
        "redistributionAllowed": True,
        "modificationAllowed": True,
        "attributionRequired": True,
        "reservedFontNames": [],
        "territories": ["WORLDWIDE"],
        "revocationState": "ACTIVE",
    }
    service.license_authority = StaticDigestPinnedAuthority(
        {license_subject: license_decision}
    )
    license_value = service.bind_license(
        {
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "m13-e3-font-license",
            "candidateRef": candidate["candidateRef"],
            "candidateVersion": 1,
            "candidateDigest": candidate["payloadDigest"],
            "licenseBindingRef": "font-license-binding-m13-e3",
            "licenseBindingVersionRef": "font-license-binding-version-m13-e3-1",
            "versionNumber": 1,
            "parentLicenseBindingVersionRef": None,
            "licenseSpdxId": "OFL-1.1",
            "licenseTextDigest": license_digest,
            "licenseEvidenceRef": "font-license-evidence-m13-e3",
            "licenseEvidenceDigest": "4" * 64,
            "validFrom": "2026-08-31T00:00:00Z",
            "expiresAt": None,
        }
    )
    admission_subject = _digest(
        {
            "candidateDigest": candidate["payloadDigest"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionDigest": license_value["payloadDigest"],
        }
    )
    admission_decision = {
        "subjectDigest": admission_subject,
        "decisionAuthorityRef": "asset-admission-owner-m13-e3",
        "decisionAuthorityDigest": "6" * 64,
        "decisionState": "ADMIT",
    }
    service.admission_authority = StaticDigestPinnedAuthority(
        {admission_subject: admission_decision}
    )
    asset = service.admit(
        {
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "m13-e3-font-admission",
            "candidateRef": candidate["candidateRef"],
            "candidateVersion": 1,
            "candidateDigest": candidate["payloadDigest"],
            "technicalValidationRef": validation["validationRef"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionRef": license_value["licenseBindingVersionRef"],
            "licenseBindingVersion": 1,
            "licenseBindingVersionDigest": license_value["payloadDigest"],
            "admissionDecisionRef": "font-admission-m13-e3",
            "assetRef": "font-asset-m13-e3",
            "assetVersionRef": "font-asset-version-m13-e3-1",
            "version": 1,
        }
    )
    return FontAuthorityFixture(
        service=service,
        asset=asset,
        font_path=font_path,
        reference_facts=reference_facts,
        license_decision=license_decision,
        admission_decision=admission_decision,
    )


def restart_font_authority(
    *, run: Mapping[str, Any], evidence, fixture: FontAuthorityFixture
) -> CanonicalStaticResourceService:
    return _font_service(
        run=run,
        evidence=evidence,
        font_path=fixture.font_path,
        reference_facts=fixture.reference_facts,
        license_decision=fixture.license_decision,
        admission_decision=fixture.admission_decision,
    )


def point_keyframes(start: int, end: int, x: int, y: int) -> list[dict[str, Any]]:
    return [
        {"frame": frame, "xPermille": x, "yPermille": y, "interpolation": "LINEAR"}
        for frame in (start, end - 1)
    ]


def scale_keyframes(start: int, end: int, value: int = 1000) -> list[dict[str, Any]]:
    return point_keyframes(start, end, value, value)


def rotation_keyframes(start: int, end: int) -> list[dict[str, Any]]:
    return [
        {"frame": frame, "degreesMilli": 0, "interpolation": "LINEAR"}
        for frame in (start, end - 1)
    ]


def opacity_keyframes(start: int, end: int) -> list[dict[str, Any]]:
    return [
        {"frame": frame, "valuePermille": 1000, "interpolation": "LINEAR"}
        for frame in (start, end - 1)
    ]


def perspective_keyframes(start: int, end: int) -> list[dict[str, Any]]:
    quad = [0, 0, 1000, 0, 0, 1000, 1000, 1000]
    return [
        {"frame": frame, "quadPermille": quad, "interpolation": "LINEAR"}
        for frame in (start, end - 1)
    ]


__all__ = [
    "CHARACTER_REF",
    "CREATED_AT",
    "CurrentIdentityProjectionReader",
    "CurrentRealMediaAuthority",
    "CurrentScriptTextReader",
    "FontAuthorityFixture",
    "LANGUAGE",
    "SCRIPT_REF",
    "SCRIPT_VERSION_DIGEST",
    "SCRIPT_VERSION_REF",
    "TEXT",
    "admit_canonical_font",
    "canonical_mark_asset",
    "opacity_keyframes",
    "perspective_keyframes",
    "point_keyframes",
    "restart_font_authority",
    "rotation_keyframes",
    "scale_keyframes",
]
