"""Contract tests for the additive canonical FONT AssetVersion v2 slice."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import struct
import tempfile
import unittest

from services.v5_core_os.asset_registry import AssetRegistry, AssetRegistryDeprecatedError
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.media_candidate_review import (
    CanonicalAssetVersionAuthority,
)
from services.v5_core_os.episode_production.static_resources import (
    CanonicalStaticResourceService,
    DirectoryStaticResourceStorage,
    FontTechnicalValidationError,
    ResourceLicenseRequiredError,
    StaticDigestPinnedAuthority,
    StaticDigestPinnedReferenceEvidence,
    StaticResourceAdmissionRequiredError,
    StaticResourceError,
    _cmap_format_4_supports,
    _cmap_format_12_supports,
    _parse_sfnt,
)


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "v5_fonts"
FONT_PATH = FIXTURE_ROOT / "Geist-Regular.ttf"
FONT_DIGEST = "bde046ddd9f20be35b0bd56cc79eb752b967fb6661a3fe76cb067bb09f871d76"
LICENSE_DIGEST = "942560b236adfa83745b2c64e5fc09ebaf91cb331751b1157eb92187e5d6e930"
DIGESTS = [character * 64 for character in "123456789abcdef"]


def reference_evidence():
    return StaticDigestPinnedReferenceEvidence({
        "artifact-font-1": {"payloadDigest": DIGESTS[1]},
        "provenance-font-1": {"payloadDigest": DIGESTS[2]},
        "font-license-evidence": {"payloadDigest": DIGESTS[4]},
        "license-text:OFL-1.1": {"payloadDigest": LICENSE_DIGEST},
    })


class RootStub:
    def verify_run_current(self, workspace_ref: str, run_ref: str):
        if workspace_ref != "workspace-font" or run_ref != "run-font":
            raise StaleInputError("foreign scope")
        return {
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "projectRef": "project-font",
            "seriesRef": "series-font",
            "episodeRef": "episode-font",
            "payloadDigest": DIGESTS[0],
        }


class RefFactory:
    def __init__(self):
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


class MutableRootStub(RootStub):
    def __init__(self):
        self.calls = 0
        self.project_ref = "project-font"

    def verify_run_current(self, workspace_ref: str, run_ref: str):
        self.calls += 1
        value = super().verify_run_current(workspace_ref, run_ref)
        value["projectRef"] = self.project_ref
        return value


def candidate_command(**changes):
    value = {
        "workspaceRef": "workspace-font", "productionRunRef": "run-font",
        "idempotencyKey": "font-candidate-key", "candidateRef": "font-candidate-1",
        "candidateVersion": 1, "assetClass": "STATIC_RESOURCE", "resourceKind": "FONT",
        "artifactEvidenceRef": "artifact-font-1", "artifactEvidenceDigest": DIGESTS[1],
        "storageBindingRef": "font-fixture", "byteSize": FONT_PATH.stat().st_size,
        "fileDigest": FONT_DIGEST, "mediaType": "font/ttf",
        "sourceProvenanceRef": "provenance-font-1", "sourceProvenanceDigest": DIGESTS[2],
    }
    value.update(changes)
    return value


class StaticFontAssetContractTests(unittest.TestCase):
    def setUp(self):
        self.evidence = InMemoryEpisodeProductionEvidenceAdapter()
        self.service = CanonicalStaticResourceService(
            RootStub(), self.evidence,
            storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
            reference_evidence=reference_evidence(),
            clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
        )

    def create_candidate(self):
        return self.service.create_candidate(candidate_command())

    def validate(self, candidate):
        return self.service.validate_font({
            "workspaceRef": "workspace-font", "productionRunRef": "run-font",
            "idempotencyKey": "font-validation-key", "candidateRef": candidate["candidateRef"],
            "candidateVersion": candidate["candidateVersion"], "candidateDigest": candidate["payloadDigest"],
            "validationRef": "font-validation-1", "testText": "FONT 123",
        })

    def bind_license(self, candidate, **changes):
        subject = _digest({
            "candidateDigest": candidate["payloadDigest"],
            "fontFileDigest": candidate["fileDigest"],
            "licenseSpdxId": "OFL-1.1", "licenseTextDigest": LICENSE_DIGEST,
            "licenseEvidenceRef": "font-license-evidence",
            "licenseEvidenceDigest": DIGESTS[4],
        })
        decision = {
            "subjectDigest": subject, "decisionAuthorityRef": "rights-owner-font",
            "decisionAuthorityDigest": DIGESTS[3], "commercialUseAllowed": True,
            "technicalPreviewAllowed": True, "renderCandidateUseAllowed": True,
            "embeddingAllowed": True, "redistributionAllowed": True,
            "modificationAllowed": True, "attributionRequired": True,
            "reservedFontNames": [], "territories": ["WORLDWIDE"], "revocationState": "ACTIVE",
        }
        self.service.license_authority = StaticDigestPinnedAuthority({subject: decision})
        command = {
            "workspaceRef": "workspace-font", "productionRunRef": "run-font",
            "idempotencyKey": "font-license-key", "candidateRef": candidate["candidateRef"],
            "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
            "licenseBindingRef": "font-license-binding", "licenseBindingVersionRef": "font-license-v1",
            "versionNumber": 1, "parentLicenseBindingVersionRef": None,
            "licenseSpdxId": "OFL-1.1", "licenseTextDigest": LICENSE_DIGEST,
            "licenseEvidenceRef": "font-license-evidence", "licenseEvidenceDigest": DIGESTS[4],
            "validFrom": "2026-08-31T00:00:00Z", "expiresAt": None,
        }
        command.update(changes)
        return self.service.bind_license(command)

    def admit(self, candidate, validation, license_value):
        subject = _digest({
            "candidateDigest": candidate["payloadDigest"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionDigest": license_value["payloadDigest"],
        })
        self.service.admission_authority = StaticDigestPinnedAuthority({subject: {
            "subjectDigest": subject, "decisionAuthorityRef": "asset-admission-owner",
            "decisionAuthorityDigest": DIGESTS[5], "decisionState": "ADMIT",
        }})
        return self.service.admit({
            "workspaceRef": "workspace-font", "productionRunRef": "run-font",
            "idempotencyKey": "font-admission-key", "candidateRef": candidate["candidateRef"],
            "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
            "technicalValidationRef": validation["validationRef"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionRef": license_value["licenseBindingVersionRef"],
            "licenseBindingVersion": 1, "licenseBindingVersionDigest": license_value["payloadDigest"],
            "admissionDecisionRef": "font-admission-1", "assetRef": "font-asset-1",
            "assetVersionRef": "font-asset-version-1", "version": 1,
        })

    def create_admitted_font(self):
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        license_value = self.bind_license(candidate)
        asset = self.admit(candidate, validation, license_value)
        return candidate, validation, license_value, asset

    def test_ttf_validation_and_repeatable_renderer_probe(self):
        candidate = self.create_candidate()
        first = self.validate(candidate)
        second_service = CanonicalStaticResourceService(
            RootStub(), InMemoryEpisodeProductionEvidenceAdapter(),
            storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
            reference_evidence=reference_evidence(),
            clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
        )
        second_candidate = second_service.create_candidate(candidate_command())
        second = second_service.validate_font({
            "workspaceRef": "workspace-font", "productionRunRef": "run-font",
            "idempotencyKey": "font-validation-key", "candidateRef": second_candidate["candidateRef"],
            "candidateVersion": 1, "candidateDigest": second_candidate["payloadDigest"],
            "validationRef": "font-validation-1", "testText": "FONT 123",
        })
        self.assertEqual("PASS", first["validationState"])
        self.assertEqual("TTF", first["fontFormat"])
        self.assertEqual(first["rendererProbeDigest"], second["rendererProbeDigest"])
        self.assertEqual(FONT_DIGEST, first["fileDigest"])

    def test_valid_otf_sfnt_directory_is_recognized_without_extension_inference(self):
        data = bytearray(FONT_PATH.read_bytes())
        data[:4] = b"OTTO"
        parsed = _parse_sfnt(bytes(data), "font/otf")
        self.assertEqual("OTF", parsed["fontFormat"])
        with self.assertRaises(FontTechnicalValidationError):
            _parse_sfnt(bytes(data), "font/ttf")

    def test_stdlib_cmap_format_4_and_12_report_real_non_notdef_glyphs(self):
        format_4 = b"".join(
            (
                struct.pack(">HHHHHHH", 4, 32, 0, 4, 4, 1, 0),
                struct.pack(">2H", 0x0041, 0xFFFF),
                struct.pack(">H", 0),
                struct.pack(">2H", 0x0041, 0xFFFF),
                struct.pack(">2h", 3 - 0x0041, 1),
                struct.pack(">2H", 0, 0),
            )
        )
        supports_bmp = _cmap_format_4_supports(format_4, num_glyphs=5)
        self.assertTrue(supports_bmp(ord("A")))
        self.assertFalse(supports_bmp(ord("B")))
        self.assertFalse(supports_bmp(0xFFFF))

        format_12 = struct.pack(
            ">HHIIIIII", 12, 0, 28, 0, 1, 0x1F600, 0x1F600, 3
        )
        supports_full = _cmap_format_12_supports(format_12, num_glyphs=5)
        self.assertTrue(supports_full(0x1F600))
        self.assertFalse(supports_full(ord("A")))

        with self.assertRaises(FontTechnicalValidationError):
            _cmap_format_12_supports(format_12[:-1], num_glyphs=5)

    def test_non_font_resource_kind_and_test_markers_are_rejected(self):
        with self.assertRaises(StaticResourceError):
            self.service.create_candidate(candidate_command(resourceKind="LUT"))
        with self.assertRaises(StaticResourceError):
            self.service.create_candidate({**candidate_command(), "TECHNICAL_FIXTURE_ONLY": True})

    def test_disguised_corrupt_and_unsupported_containers_are_rejected(self):
        for signature in (b"ttcf", b"wOFF", b"wOF2", b"BAD!"):
            data = signature + FONT_PATH.read_bytes()[4:]
            with self.assertRaises(FontTechnicalValidationError):
                _parse_sfnt(data, "font/ttf")
        with self.assertRaises(FontTechnicalValidationError):
            _parse_sfnt(b"\x00\x01\x00\x00bad", "font/ttf")

    def test_symlink_non_regular_and_digest_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "font.ttf").write_bytes(FONT_PATH.read_bytes())
            (root / "link.ttf").symlink_to(root / "font.ttf")
            symlink_service = CanonicalStaticResourceService(
                RootStub(), InMemoryEpisodeProductionEvidenceAdapter(),
                storage=DirectoryStaticResourceStorage(root, {"font-fixture": "link.ttf"}),
                reference_evidence=reference_evidence(),
                clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
            )
            with self.assertRaises(FontTechnicalValidationError):
                symlink_service.create_candidate(candidate_command(byteSize=(root / "font.ttf").stat().st_size))
        with self.assertRaises(StaleInputError):
            self.service.create_candidate(candidate_command(fileDigest=DIGESTS[6]))

    def test_default_license_and_admission_authorities_reject(self):
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        with self.assertRaises(ResourceLicenseRequiredError):
            self.service.bind_license({
                "workspaceRef": "workspace-font", "productionRunRef": "run-font",
                "idempotencyKey": "font-license-key", "candidateRef": candidate["candidateRef"],
                "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
                "licenseBindingRef": "font-license-binding", "licenseBindingVersionRef": "font-license-v1",
                "versionNumber": 1, "parentLicenseBindingVersionRef": None,
                "licenseSpdxId": "OFL-1.1", "licenseTextDigest": LICENSE_DIGEST,
                "licenseEvidenceRef": "font-license-evidence", "licenseEvidenceDigest": DIGESTS[4],
                "validFrom": "2026-08-31T00:00:00Z", "expiresAt": None,
            })
        license_value = self.bind_license(candidate)
        with self.assertRaises(StaticResourceAdmissionRequiredError):
            self.service.admit({
                "workspaceRef": "workspace-font", "productionRunRef": "run-font",
                "idempotencyKey": "font-admission-key", "candidateRef": candidate["candidateRef"],
                "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
                "technicalValidationRef": validation["validationRef"],
                "technicalValidationDigest": validation["payloadDigest"],
                "licenseBindingVersionRef": license_value["licenseBindingVersionRef"],
                "licenseBindingVersion": 1, "licenseBindingVersionDigest": license_value["payloadDigest"],
                "admissionDecisionRef": "font-admission-1", "assetRef": "font-asset-1",
                "assetVersionRef": "font-asset-version-1", "version": 1,
            })

    def test_unsupported_and_revoked_license_decisions_fail(self):
        candidate = self.create_candidate()
        with self.assertRaises(ResourceLicenseRequiredError):
            self.bind_license(candidate, licenseSpdxId="MIT")
        decision = {
            "subjectDigest": _digest({
                "candidateDigest": candidate["payloadDigest"],
                "fontFileDigest": candidate["fileDigest"], "licenseSpdxId": "OFL-1.1",
                "licenseTextDigest": LICENSE_DIGEST, "licenseEvidenceRef": "font-license-evidence",
                "licenseEvidenceDigest": DIGESTS[4],
            }), "decisionAuthorityRef": "rights",
            "decisionAuthorityDigest": DIGESTS[3], "commercialUseAllowed": True,
            "technicalPreviewAllowed": True, "renderCandidateUseAllowed": True,
            "embeddingAllowed": True, "redistributionAllowed": True,
            "modificationAllowed": True, "attributionRequired": True,
            "reservedFontNames": [], "territories": ["WORLDWIDE"], "revocationState": "REVOKED",
        }
        self.service.license_authority = StaticDigestPinnedAuthority(
            {decision["subjectDigest"]: decision}
        )
        with self.assertRaises(ResourceLicenseRequiredError):
            self.service.bind_license(
                {**self._license_command(candidate), "idempotencyKey": "license-revoked"}
            )

    def test_insufficient_render_scope_blocks_admission(self):
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        decision = {
            "subjectDigest": _digest({
                "candidateDigest": candidate["payloadDigest"],
                "fontFileDigest": candidate["fileDigest"], "licenseSpdxId": "OFL-1.1",
                "licenseTextDigest": LICENSE_DIGEST, "licenseEvidenceRef": "font-license-evidence",
                "licenseEvidenceDigest": DIGESTS[4],
            }), "decisionAuthorityRef": "rights",
            "decisionAuthorityDigest": DIGESTS[3], "commercialUseAllowed": True,
            "technicalPreviewAllowed": True, "renderCandidateUseAllowed": False,
            "embeddingAllowed": True, "redistributionAllowed": True,
            "modificationAllowed": True, "attributionRequired": True,
            "reservedFontNames": [], "territories": ["WORLDWIDE"], "revocationState": "ACTIVE",
        }
        self.service.license_authority = StaticDigestPinnedAuthority(
            {decision["subjectDigest"]: decision}
        )
        license_value = self.service.bind_license(self._license_command(candidate))
        with self.assertRaises(StaleInputError):
            self.admit(candidate, validation, license_value)

    def test_license_evidence_drift_and_expiry_block_admission(self):
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        license_value = self.bind_license(candidate)
        self.service.reference_evidence = StaticDigestPinnedReferenceEvidence({
            "artifact-font-1": {"payloadDigest": DIGESTS[1]},
            "provenance-font-1": {"payloadDigest": DIGESTS[2]},
            "font-license-evidence": {"payloadDigest": DIGESTS[7]},
            "license-text:OFL-1.1": {"payloadDigest": LICENSE_DIGEST},
        })
        with self.assertRaises(StaleInputError):
            self.admit(candidate, validation, license_value)

        evidence = InMemoryEpisodeProductionEvidenceAdapter()
        expired_service = CanonicalStaticResourceService(
            RootStub(), evidence,
            storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
            reference_evidence=reference_evidence(), clock=lambda: "2026-08-31T00:00:00Z",
            ref_factory=RefFactory(),
        )
        self.service = expired_service
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        license_value = self.bind_license(candidate, expiresAt="2026-08-30T00:00:00Z")
        with self.assertRaises(StaleInputError):
            self.admit(candidate, validation, license_value)

    def test_renderer_failure_and_font_file_tamper_after_validation_fail_closed(self):
        candidate = self.create_candidate()
        broken_renderer = CanonicalStaticResourceService(
            RootStub(), self.evidence,
            storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
            reference_evidence=reference_evidence(), clock=lambda: "2026-08-31T00:00:00Z",
            ref_factory=RefFactory(), ffmpeg_executable="missing-pinned-ffmpeg",
        )
        with self.assertRaises(FontTechnicalValidationError):
            broken_renderer.validate_font({
                "workspaceRef": "workspace-font", "productionRunRef": "run-font",
                "idempotencyKey": "broken-renderer", "candidateRef": candidate["candidateRef"],
                "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
                "validationRef": "broken-validation", "testText": "FONT 123",
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mutable = root / "Geist-Regular.ttf"
            mutable.write_bytes(FONT_PATH.read_bytes())
            evidence = InMemoryEpisodeProductionEvidenceAdapter()
            service = CanonicalStaticResourceService(
                RootStub(), evidence,
                storage=DirectoryStaticResourceStorage(root, {"font-fixture": mutable.name}),
                reference_evidence=reference_evidence(), clock=lambda: "2026-08-31T00:00:00Z",
                ref_factory=RefFactory(),
            )
            self.service = service
            candidate = self.create_candidate()
            validation = self.validate(candidate)
            license_value = self.bind_license(candidate)
            mutable.write_bytes(FONT_PATH.read_bytes() + b"tamper")
            with self.assertRaises(StaleInputError):
                self.admit(candidate, validation, license_value)

    def _license_command(self, candidate):
        return {
            "workspaceRef": "workspace-font", "productionRunRef": "run-font",
            "idempotencyKey": "font-license-key", "candidateRef": candidate["candidateRef"],
            "candidateVersion": 1, "candidateDigest": candidate["payloadDigest"],
            "licenseBindingRef": "font-license-binding", "licenseBindingVersionRef": "font-license-v1",
            "versionNumber": 1, "parentLicenseBindingVersionRef": None,
            "licenseSpdxId": "OFL-1.1", "licenseTextDigest": LICENSE_DIGEST,
            "licenseEvidenceRef": "font-license-evidence", "licenseEvidenceDigest": DIGESTS[4],
            "validFrom": "2026-08-31T00:00:00Z", "expiresAt": None,
        }

    def test_asset_version_v2_chain_projection_and_v1_history(self):
        candidate = self.create_candidate()
        validation = self.validate(candidate)
        license_value = self.bind_license(candidate)
        asset = self.admit(candidate, validation, license_value)
        self.assertEqual("v5.asset-version.v2", asset["schemaVersion"])
        self.assertEqual("ADMITTED", asset["admissionState"])
        projection = self.service.project_font_asset_versions("workspace-font", "run-font")[0]
        self.assertNotIn("storageBindingRef", projection)
        self.assertFalse(projection["publicationAllowed"])
        authority = CanonicalAssetVersionAuthority(self.evidence)
        self.assertEqual([asset], authority.list_asset_versions("workspace-font", "run-font"))

    def test_current_projection_revalidates_chain_and_exact_glyph_coverage(self):
        _candidate, _validation, _license_value, asset = self.create_admitted_font()
        projection = self.service.require_current_font_asset_projection(
            "workspace-font",
            "run-font",
            asset["assetVersionRef"],
            asset["payloadDigest"],
            required_text="FONT 123",
        )
        self.assertEqual(
            asset["assetVersionRef"],
            projection["fontAssetVersion"]["assetVersionRef"],
        )
        self.assertNotIn("storageBindingRef", projection["fontAssetVersion"])
        self.assertEqual("font-fixture", projection["storageBindingRef"])
        self.assertFalse(projection["publicationAllowed"])

        with self.assertRaises(FontTechnicalValidationError):
            self.service.require_current_font_asset_projection(
                "workspace-font",
                "run-font",
                asset["assetVersionRef"],
                asset["payloadDigest"],
                required_text="长安",
            )

    def test_current_projection_rereads_root_and_external_authorities(self):
        root = MutableRootStub()
        self.service.root_service = root
        _candidate, _validation, _license_value, asset = self.create_admitted_font()
        calls_after_admission = root.calls
        self.service.require_current_font_asset_projection(
            "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"]
        )
        self.assertEqual(calls_after_admission + 1, root.calls)

        self.service.reference_evidence = StaticDigestPinnedReferenceEvidence({
            "artifact-font-1": {"payloadDigest": DIGESTS[8]},
            "provenance-font-1": {"payloadDigest": DIGESTS[2]},
            "font-license-evidence": {"payloadDigest": DIGESTS[4]},
            "license-text:OFL-1.1": {"payloadDigest": LICENSE_DIGEST},
        })
        with self.assertRaises(StaleInputError):
            self.service.require_current_font_asset_projection(
                "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"]
            )

        self.service.reference_evidence = reference_evidence()
        root.project_ref = "replaced-project"
        with self.assertRaises(StaleInputError):
            self.service.require_current_font_asset_projection(
                "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"]
            )

    def test_current_projection_redecides_license_and_admission(self):
        candidate, validation, license_value, asset = self.create_admitted_font()
        license_subject = {
            "subjectDigest": _digest({
                "candidateDigest": candidate["payloadDigest"],
                "fontFileDigest": candidate["fileDigest"],
                "licenseSpdxId": license_value["licenseSpdxId"],
                "licenseTextDigest": license_value["licenseTextDigest"],
                "licenseEvidenceRef": license_value["licenseEvidenceRef"],
                "licenseEvidenceDigest": license_value["licenseEvidenceDigest"],
            }),
            "candidateRef": candidate["candidateRef"],
            "fontFileDigest": candidate["fileDigest"],
            "licenseSpdxId": license_value["licenseSpdxId"],
            "licenseTextDigest": license_value["licenseTextDigest"],
            "licenseEvidenceRef": license_value["licenseEvidenceRef"],
            "licenseEvidenceDigest": license_value["licenseEvidenceDigest"],
        }
        stale_license = dict(self.service.license_authority.decide(license_subject))
        stale_license["renderCandidateUseAllowed"] = False
        self.service.license_authority = StaticDigestPinnedAuthority(
            {license_subject["subjectDigest"]: stale_license}
        )
        with self.assertRaises(StaleInputError):
            self.service.require_current_font_asset_projection(
                "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"]
            )

        self.service.license_authority = StaticDigestPinnedAuthority({
            license_subject["subjectDigest"]: {
                field: deepcopy(license_value[field])
                for field in {
                    "decisionAuthorityRef", "decisionAuthorityDigest",
                    "commercialUseAllowed", "technicalPreviewAllowed",
                    "renderCandidateUseAllowed", "embeddingAllowed",
                    "redistributionAllowed", "modificationAllowed",
                    "attributionRequired", "reservedFontNames", "territories",
                    "revocationState",
                }
            }
            | {"subjectDigest": license_subject["subjectDigest"]}
        })
        admission_subject = _digest({
            "candidateDigest": candidate["payloadDigest"],
            "technicalValidationDigest": validation["payloadDigest"],
            "licenseBindingVersionDigest": license_value["payloadDigest"],
        })
        self.service.admission_authority = StaticDigestPinnedAuthority({
            admission_subject: {
                "subjectDigest": admission_subject,
                "decisionAuthorityRef": "asset-admission-owner",
                "decisionAuthorityDigest": DIGESTS[5],
                "decisionState": "REJECT",
            }
        })
        with self.assertRaises(StaleInputError):
            self.service.require_current_font_asset_projection(
                "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"]
            )

    def test_current_projection_and_held_fd_remeasure_storage_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mutable = root / "font.ttf"
            mutable.write_bytes(FONT_PATH.read_bytes())
            self.evidence = InMemoryEpisodeProductionEvidenceAdapter()
            self.service = CanonicalStaticResourceService(
                RootStub(), self.evidence,
                storage=DirectoryStaticResourceStorage(root, {"font-fixture": mutable.name}),
                reference_evidence=reference_evidence(),
                clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
            )
            _candidate, _validation, _license_value, asset = self.create_admitted_font()
            projection = self.service.require_current_font_asset_projection(
                "workspace-font", "run-font", asset["assetVersionRef"], asset["payloadDigest"],
                required_text="FONT",
            )
            fd = self.service.open_current_font_file(
                projection["storageBindingRef"],
                expected_file_digest=asset["fileDigest"],
                expected_byte_size=asset["byteSize"],
                declared_media_type=asset["mediaType"],
                required_text="FONT",
            )
            try:
                self.assertEqual(b"\x00\x01\x00\x00", os.read(fd, 4))
            finally:
                os.close(fd)

            mutable.write_bytes(FONT_PATH.read_bytes() + b"tamper")
            with self.assertRaises(StaleInputError):
                self.service.require_current_font_asset_projection(
                    "workspace-font", "run-font", asset["assetVersionRef"],
                    asset["payloadDigest"], required_text="FONT",
                )
            with self.assertRaises(StaleInputError):
                self.service.open_current_font_file(
                    projection["storageBindingRef"],
                    expected_file_digest=asset["fileDigest"],
                    expected_byte_size=asset["byteSize"],
                    declared_media_type=asset["mediaType"],
                    required_text="FONT",
                )

    def test_exact_replay_changed_replay_and_foreign_workspace(self):
        first = self.create_candidate()
        second = self.service.create_candidate(candidate_command())
        self.assertEqual(first, second)
        self.service.reference_evidence = StaticDigestPinnedReferenceEvidence({
            "artifact-font-1": {"payloadDigest": DIGESTS[1]},
            "provenance-font-1": {"payloadDigest": DIGESTS[8]},
        })
        with self.assertRaises(IdempotencyConflictError):
            self.service.create_candidate(candidate_command(sourceProvenanceDigest=DIGESTS[8]))
        with self.assertRaises(StaleInputError):
            self.service.create_candidate(candidate_command(workspaceRef="foreign-workspace"))

    def test_sqlite_restart_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "font-evidence.sqlite3"
            repository = SqliteEpisodeProductionEvidenceAdapter(database, initialize_if_missing=True)
            service = CanonicalStaticResourceService(
                RootStub(), repository,
                storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
                reference_evidence=reference_evidence(),
                clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
            )
            candidate = service.create_candidate(candidate_command())
            restarted = SqliteEpisodeProductionEvidenceAdapter(database, initialize_if_missing=False)
            record = restarted.get_record("workspace-font", "run-font", candidate["candidateRef"], 1)
            self.assertEqual(candidate["payloadDigest"], record["payloadDigest"])
            with self.assertRaises(StaleInputError):
                CanonicalStaticResourceService(
                    RootStub(), restarted,
                    storage=DirectoryStaticResourceStorage(FIXTURE_ROOT, {"font-fixture": "Geist-Regular.ttf"}),
                    reference_evidence=reference_evidence(),
                    clock=lambda: "2026-08-31T00:00:00Z", ref_factory=RefFactory(),
                ).validate_font({
                    "workspaceRef": "workspace-font", "productionRunRef": "run-font",
                    "idempotencyKey": "font-validation-key", "candidateRef": candidate["candidateRef"],
                    "candidateVersion": 1, "candidateDigest": DIGESTS[9],
                    "validationRef": "font-validation-1", "testText": "FONT 123",
                })

    def test_deprecated_registry_remains_fail_closed_and_no_live_store_exists(self):
        with self.assertRaises(AssetRegistryDeprecatedError):
            AssetRegistry().create_asset(asset_id="font", asset_type="font", version_id="v2")
        records = self.evidence.list_records("workspace-font", "run-font")
        self.assertEqual([], records)


if __name__ == "__main__":
    unittest.main()
