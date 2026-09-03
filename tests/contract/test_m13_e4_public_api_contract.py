from __future__ import annotations

from copy import deepcopy
import math
import unittest

from apps.creator_workspace_mvp.server import (
    EPISODE_PRODUCTION_SUBRESOURCES,
    _DETERMINISTIC_EFFECT_KINDS,
    _contains_forbidden_deterministic_effect_claim,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)


EFFECT_KIND = "DISTANCE_STATE_TRANSITION"


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


class _DeliveryStub:
    def __init__(self) -> None:
        self.command = None

    @staticmethod
    def _private_chain() -> dict:
        return {
            "requirement": {
                "effectMode": EFFECT_KIND,
                "targetKind": "OVERLAY_LAYER",
                "coordinateSpace": "CANVAS_PIXELS",
                "basePlateAssetVersionRef": "base-version-1",
                "subjectLayerAssetVersionRef": "subject-version-1",
                "maskAssetVersionRef": "mask-version-1",
                "basePlateFileDigest": "sha256:" + "0" * 64,
                "basePlatePixelDigest": "sha256:" + "1" * 64,
                "subjectLayerFileDigest": "sha256:" + "2" * 64,
                "subjectLayerPixelDigest": "sha256:" + "3" * 64,
                "maskFileDigest": "sha256:" + "4" * 64,
                "maskPixelDigest": "sha256:" + "5" * 64,
                "visualStateDefinitions": [
                    {
                        "stateRef": "visual-state-visible",
                        "variantAssetVersionRef": "variant-version-1",
                        "variantAssetVersionDigest": "6" * 64,
                        "variantFileDigest": "sha256:" + "7" * 64,
                        "variantPixelDigest": "sha256:" + "8" * 64,
                        "variantStorageKey": "private/variant.png",
                        "variantWidth": 64,
                        "variantHeight": 64,
                    }
                ],
            },
            "executionRequest": {
                "internalPath": "/private/input.mp4",
                "storageKey": "private/input.mp4",
                "ffmpegFilter": "private-filter",
                "argv": ["ffmpeg", "private"],
                "runtimeEnvironment": {"PATH": "/private/bin"},
            },
            "artifactEvidence": {
                "outputStorageKey": "private/output.mp4",
                "commandLine": "ffmpeg private",
            },
            "runtimeEvidence": {
                "runtimeDiagnostics": {"stderr": "private"},
                "environment": {"SECRET": "private"},
            },
            "result": {
                "resultRef": "distance-state-result-1",
                "derivedDistanceFacts": {
                    "metric": "SCREEN_EUCLIDEAN_PIXELS",
                    "startValue": 10,
                    "endValue": 2,
                },
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


class M13E4PublicApiContractTests(unittest.TestCase):
    def test_reuses_the_single_existing_route_and_adds_one_closed_kind(self):
        self.assertEqual(len(EPISODE_PRODUCTION_SUBRESOURCES), 30)
        self.assertIn("deterministic-effects", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertIn(EFFECT_KIND, _DETERMINISTIC_EFFECT_KINDS)
        self.assertNotIn("distance", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("state", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("transform", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("composition", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("ffmpeg", EPISODE_PRODUCTION_SUBRESOURCES)

    def test_closed_screen_space_integer_request_is_not_preemptively_rejected(self):
        request = {
            "effectKind": EFFECT_KIND,
            "requirement": {
                "effectMode": EFFECT_KIND,
                "coordinateSpace": "CANVAS_PIXELS",
                "distanceContract": {
                    "metric": "SCREEN_EUCLIDEAN_PIXELS",
                    "startValue": 100,
                    "endValue": 20,
                    "tolerance": 0,
                    "direction": "APPROACH",
                },
                "motionKeyframes": [
                    {
                        "frame": 0,
                        "x": 10,
                        "y": 20,
                        "scaleXNumerator": 1,
                        "scaleXDenominator": 1,
                        "scaleYNumerator": 1,
                        "scaleYDenominator": 1,
                    }
                ],
                "visualStateSchedule": [
                    {
                        "stateRef": "visual-state-visible",
                        "startFrameInclusive": 0,
                        "endFrameExclusive": 1,
                        "transitionInterpolation": "STEP",
                    }
                ],
            },
        }
        self.assertFalse(
            _contains_forbidden_deterministic_effect_claim(request)
        )

    def test_world_natural_language_float_and_execution_claims_are_rejected(self):
        forbidden = {
            "world-meters": {"distanceContract": {"metric": "WORLD_METERS"}},
            "world-centimeters": {
                "distanceContract": {"metric": "WORLD_CENTIMETERS"}
            },
            "world-meters-field": {"worldMeters": 45},
            "world-centimeters-field": {"worldCentimeters": 12},
            "unspecified-3d": {"coordinateSpace": "UNSPECIFIED_3D"},
            "natural-language-mode": {"coordinateSpace": "NATURAL_LANGUAGE"},
            "natural-language-field": {"distancePrompt": "靠近一点"},
            "expression": {"motionExpression": "sin(t)"},
            "random": {"randomOffset": 7},
            "finite-float": {"motionKeyframes": [{"x": 0.25}]},
            "nan": {"motionKeyframes": [{"x": math.nan}]},
            "positive-infinity": {"motionKeyframes": [{"x": math.inf}]},
            "negative-infinity": {"motionKeyframes": [{"x": -math.inf}]},
            "absolute-path": {"absolutePath": "/private/base.mp4"},
            "storage": {"storageKey": "private/base.mp4"},
            "raw-authority": {"rawShotVersion": {"shotVersionRef": "raw"}},
            "filter": {"ffmpegFilter": "movie=/private/in.png"},
            "argv": {"argv": ["ffmpeg", "-i", "private"]},
            "shell": {"shellCommand": "ffmpeg private"},
            "publication": {"publicationAllowed": False},
            "canonical": {"canonicalMutations": []},
            "base-file": {"basePlateFileDigest": "sha256:" + "0" * 64},
            "base-pixels": {"basePlatePixelDigest": "sha256:" + "1" * 64},
            "subject-file": {
                "subjectLayerFileDigest": "sha256:" + "2" * 64
            },
            "subject-pixels": {
                "subjectLayerPixelDigest": "sha256:" + "3" * 64
            },
            "mask-file": {"maskFileDigest": "sha256:" + "4" * 64},
            "mask-pixels": {"maskPixelDigest": "sha256:" + "5" * 64},
            "variant-private": {
                "visualStateDefinitions": [
                    {"variantStorageKey": "private/variant.png"}
                ]
            },
        }
        for label, claim in forbidden.items():
            with self.subTest(label=label):
                self.assertTrue(
                    _contains_forbidden_deterministic_effect_claim(
                        {
                            "effectKind": EFFECT_KIND,
                            "requirement": claim,
                        }
                    )
                )

    def test_post_and_get_are_deeply_redacted_without_hiding_safe_facts(self):
        stub = _DeliveryStub()
        boundary = _public(stub)
        command = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "expectedRunVersion": 1,
            "idempotencyKey": "m13-e4-public-1",
            "effectKind": EFFECT_KIND,
            "requirement": {"effectMode": EFFECT_KIND},
        }
        created = boundary.execute_deterministic_effect(command)
        listed = boundary.get_deterministic_effects("workspace-1", "run-1")
        self.assertEqual(stub.command, command)
        forbidden = {
            "baseplatefiledigest",
            "baseplatepixeldigest",
            "subjectlayerfiledigest",
            "subjectlayerpixeldigest",
            "maskfiledigest",
            "maskpixeldigest",
            "variantfiledigest",
            "variantpixeldigest",
            "variantstoragekey",
            "variantwidth",
            "variantheight",
            "internalpath",
            "storagekey",
            "ffmpegfilter",
            "argv",
            "runtimeenvironment",
            "runtimediagnostics",
            "stderr",
            "environment",
            "commandline",
        }
        self.assertFalse(_normalized_keys(created) & forbidden)
        self.assertFalse(_normalized_keys(listed) & forbidden)
        requirement = created["deterministicEffect"]["requirement"]
        self.assertEqual(requirement["targetKind"], "OVERLAY_LAYER")
        self.assertEqual(
            requirement["subjectLayerAssetVersionRef"], "subject-version-1"
        )
        self.assertEqual(
            created["deterministicEffect"]["result"]["derivedDistanceFacts"],
            {
                "metric": "SCREEN_EUCLIDEAN_PIXELS",
                "startValue": 10,
                "endValue": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
