from __future__ import annotations

from copy import deepcopy
import unittest

from apps.creator_workspace_mvp.server import (
    EPISODE_PRODUCTION_SUBRESOURCES,
    _DETERMINISTIC_EFFECT_KINDS,
    _contains_forbidden_deterministic_effect_claim,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)


class _DeliveryStub:
    def __init__(self) -> None:
        self.command = None

    @staticmethod
    def _private_chain() -> dict:
        return {
            "requirement": {
                "effectMode": "FACE_MARK_COMPENSATION",
                "characterRef": "character-1",
                "basePlateFileDigest": "sha256:" + "0" * 64,
                "basePlatePixelDigest": "sha256:" + "1" * 64,
                "resolvedText": "server-resolved text",
                "resolvedTextDigest": "2" * 64,
                "language": "und",
                "fontFileDigest": "3" * 64,
                "fontTechnicalValidationRef": "font-validation-private",
                "fontTechnicalValidationDigest": "4" * 64,
                "fontLicenseBindingVersionRef": "font-license-private",
                "fontLicenseBindingVersionDigest": "5" * 64,
                "markFileDigest": "sha256:" + "6" * 64,
                "markPixelDigest": "sha256:" + "7" * 64,
                "identityReferenceRef": "identity-reference-private",
                "identityReferenceVersionRef": "identity-reference-version-private",
                "identityReferenceContentDigest": "1" * 64,
                "identityReferenceProjectionDigest": "2" * 64,
                "identityLockRef": "identity-lock-private",
                "identityLockVersionRef": "identity-lock-version-private",
                "identityLockDigest": "3" * 64,
                "publicationAllowed": False,
            },
            "executionRequest": {
                "storageBindingRef": "font-storage-private",
                "fontPath": "/private/font.ttf",
                "ffmpegFilter": "private-filter",
                "argv": ["ffmpeg", "private"],
            },
            "result": {
                "resultRef": "face-mark-result-1",
                "publicationAllowed": False,
            },
        }

    def execute_deterministic_effect(self, command):
        self.command = deepcopy(dict(command))
        return {
            "idempotentReplay": False,
            "deterministicEffect": self._private_chain(),
        }

    def get_deterministic_effects(self, workspace_ref, run_ref):
        return {
            "deterministicEffects": [self._private_chain()],
            "publicationAllowed": False,
        }


def _public(stub: _DeliveryStub) -> EpisodeProductionPublicBoundary:
    boundary = object.__new__(EpisodeProductionPublicBoundary)
    setattr(boundary, "_EpisodeProductionPublicBoundary__delivery", stub)
    return boundary


def _normalized_keys(value):
    result = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            result.add(str(key).replace("_", "").replace("-", "").lower())
            result.update(_normalized_keys(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            result.update(_normalized_keys(nested))
    return result


class M13E3PublicApiContractTests(unittest.TestCase):
    def test_existing_route_retains_the_closed_effect_kind_set(self):
        self.assertIn("deterministic-effects", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertEqual(
            _DETERMINISTIC_EFFECT_KINDS,
            {
                "FLAME_EXTINGUISH",
                "SMOKE",
                "NAMEPLATE_TEXT",
                "FACE_MARK_COMPENSATION",
                "DISTANCE_STATE_TRANSITION",
            },
        )

    def test_nested_server_owned_and_execution_private_claims_are_rejected(self):
        forbidden = {
            "basePlateFileDigest": "sha256:" + "0" * 64,
            "basePlatePixelDigest": "sha256:" + "1" * 64,
            "identityVersionRef": "identity-version-client",
            "identityVersionDigest": "1" * 64,
            "identityReferenceVersionRef": "identity-reference-client",
            "identityReferenceContentDigest": "2" * 64,
            "identityReferenceProjectionDigest": "3" * 64,
            "identityLock": {"identityLockRef": "client-lock"},
            "resolvedText": "client text",
            "absolutePath": "/tmp/base.mp4",
            "fontPath": "/tmp/font.ttf",
            "markPath": "/tmp/mark.png",
            "storageBindingRef": "client-storage",
            "storageKey": "client/storage/key",
            "rawAssetVersion": {"assetVersionRef": "client-asset"},
            "rawTextSource": {"resolvedText": "client text"},
            "rawIdentityVersion": {"identityVersionRef": "client-identity"},
            "rawIdentityLock": {"identityLockRef": "client-lock"},
            "ffmpegFilter": "movie=/tmp/client.png",
            "argv": ["ffmpeg"],
            "HTML": "<b>client</b>",
            "SVG": "<svg/>",
            "CSS": "position:fixed",
            "networkUrl": "https://example.invalid/client",
            "modelPath": "/tmp/model.bin",
            "environmentOverride": {"PATH": "/tmp"},
            "actorRef": "client-actor",
            "approvalRef": "client-approval",
            "publicationAllowed": False,
            "canonicalMutations": [],
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                self.assertTrue(
                    _contains_forbidden_deterministic_effect_claim(
                        {
                            "effectKind": "FACE_MARK_COMPENSATION",
                            "requirement": {field: value},
                        }
                    )
                )

    def test_post_and_get_projections_are_deeply_redacted(self):
        stub = _DeliveryStub()
        boundary = _public(stub)
        command = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "expectedRunVersion": 1,
            "idempotencyKey": "m13-e3-public-1",
            "effectKind": "FACE_MARK_COMPENSATION",
            "requirement": {"characterRef": "character-1"},
        }
        created = boundary.execute_deterministic_effect(command)
        listed = boundary.get_deterministic_effects("workspace-1", "run-1")
        self.assertEqual(stub.command, command)
        forbidden = {
            "baseplatefiledigest",
            "baseplatepixeldigest",
            "resolvedtext",
            "resolvedtextdigest",
            "language",
            "fontfiledigest",
            "fonttechnicalvalidationref",
            "fonttechnicalvalidationdigest",
            "fontlicensebindingversionref",
            "fontlicensebindingversiondigest",
            "markfiledigest",
            "markpixeldigest",
            "identityreferenceref",
            "identityreferenceversionref",
            "identityreferencecontentdigest",
            "identityreferenceprojectiondigest",
            "identitylockref",
            "identitylockversionref",
            "identitylockdigest",
            "storagebindingref",
            "fontpath",
            "ffmpegfilter",
            "argv",
        }
        self.assertFalse(_normalized_keys(created) & forbidden)
        self.assertFalse(_normalized_keys(listed) & forbidden)
        self.assertEqual(
            created["deterministicEffect"]["requirement"]["characterRef"],
            "character-1",
        )


if __name__ == "__main__":
    unittest.main()
