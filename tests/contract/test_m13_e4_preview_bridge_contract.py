from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest
from unittest import mock

from services.v3_render_core import deterministic_overlays as v3_overlays
from services.v3_render_core import distance_state as v3_distance
from services.v3_render_core import masked_surface as v3_preview
from services.v4_platform import distance_state as v4_distance
from services.v4_platform import masked_surface_effects as v4_preview
from services.v5_core_os.episode_production.foundation import _digest
from tests.contract.test_m13_e2_timeline_preview_contract import GLYPH, _binding


_MODES = (
    "SCRATCH_REVEAL",
    "LOCAL_EXPOSURE",
    "FLAME_EXTINGUISH",
    "SMOKE",
    "NAMEPLATE_TEXT",
    "FACE_MARK_COMPENSATION",
    "DISTANCE_STATE_TRANSITION",
)
_LEGACY_GOLDENS = {
    2: "b243db7839d42ad0f785d59002ee9e58a41ded4e66b1a85635a1a0c52b2c1bb0",
    4: "a7ee316dd191d1d1f21d98a4a61c740ee13ca0ba9ecd722468c69c4c65c05cbd",
    6: "b57f5802e6ccce50b7a39f4fa46f6b761bd1fe3c4d642b360ea7d184e039e765",
}
_SEVEN_STAGE_GOLDEN = (
    "9066c2ba145248ab4dffefe3b5e3d8bea77e728e6b6c491bccf43512664120da"
)


def _profile(count: int) -> list[dict]:
    return [_binding(index, mode) for index, mode in enumerate(_MODES[:count])]


class M13E4PreviewBridgeContractTests(unittest.TestCase):
    def test_v4_adds_only_the_closed_seven_stage_wire_profile(self) -> None:
        legacy_profiles = {
            2: _profile(2),
            4: [
                _binding(0, "LIGHT_SWEEP"),
                _binding(1, "LOCAL_EXPOSURE"),
                _binding(2, "FLAME_EXTINGUISH"),
                _binding(3, "SMOKE"),
            ],
            6: _profile(6),
        }
        for count, golden in _LEGACY_GOLDENS.items():
            with self.subTest(count=count):
                self.assertEqual(
                    v4_preview._effect_preview_bindings(
                        legacy_profiles[count], GLYPH
                    )[2],
                    golden,
                )

        bindings = _profile(7)
        self.assertEqual(
            v4_preview.EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4,
            "v5.m13-effect-preview-bindings.v4",
        )
        self.assertEqual(
            v4_preview._effect_preview_bindings(bindings, GLYPH)[2],
            _SEVEN_STAGE_GOLDEN,
        )

        reordered = deepcopy(bindings)
        reordered[5], reordered[6] = reordered[6], reordered[5]
        with self.assertRaises(v4_preview.MaskedSurfaceRequestValidationError):
            v4_preview._effect_preview_bindings(reordered, GLYPH)

    def test_v4_builder_dispatches_rank_six_through_full_chain_resolver(
        self,
    ) -> None:
        bindings = _profile(7)
        base = {
            "assetVersionRef": "base-version-1",
            "assetVersionDigest": "1" * 64,
            "storageKey": "inputs/base.mp4",
            "fileDigest": "sha256:" + "2" * 64,
            "pixelDigest": "sha256:" + "3" * 64,
            "pixelDigestSpec": "pixel-spec-v1",
            "width": 64,
            "height": 64,
            "frameCount": 24,
            "frameRate": 24,
            "pixelFormat": "yuv420p",
        }
        stages: list[dict] = []
        for binding in bindings:
            stages.append(
                {
                    "effectMode": binding["effectMode"],
                    "workspaceRef": "workspace-1",
                    "productionRunRef": "run-1",
                    "basePlate": deepcopy(base),
                    "requirementRef": binding["requirementRef"],
                    "requirementDigest": binding["requirementDigest"],
                    "v5ExecutionRequestRef": binding["executionRequestRef"],
                    "v5ExecutionRequestDigest": binding[
                        "executionRequestDigest"
                    ],
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "payloadDigest": sha256(
                        binding["resultRef"].encode("utf-8")
                    ).hexdigest(),
                }
            )
        stages[2]["localExposureStage"] = stages[1]
        for stage in stages[4:6]:
            stage["overlaySpec"] = {
                "frameRangeStartInclusive": stage.pop(
                    "frameRangeStartInclusive"
                ),
                "frameRangeEndExclusive": stage.pop(
                    "frameRangeEndExclusive"
                ),
            }
        glyph_stage = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "executionRequestRef": "glyph-request-1",
            "payloadDigest": "c" * 64,
        }
        command = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "timelineVersionRef": "timeline-version-1",
            "timelineVersionDigest": "f" * 64,
            "baseVideo": {
                "assetVersionRef": "base-version-1",
                "assetVersionDigest": "1" * 64,
                "fileDigest": "sha256:" + "2" * 64,
                "pixelDigest": "sha256:" + "3" * 64,
                "width": 64,
                "height": 64,
                "frameCount": 24,
                "frameRate": {"numerator": 24, "denominator": 1},
            },
            "effectResultBindings": bindings,
            "glyphRequirementBinding": deepcopy(GLYPH),
            "audioMix": {"fixture": "audio"},
            "subtitleManifest": {"fixture": "subtitle"},
            "output": {"fixture": "output"},
        }
        resolutions = {
            "baseVideo": {"fixture": "base"},
            "effectExecutions": {
                binding["resultRef"]: {"fixture": binding["resultRef"]}
                for binding in bindings
            },
            "glyphExecution": {"fixture": "glyph"},
        }
        legacy = {
            "audioMix": {
                "mixRequestRef": "mix-1",
                "mixRequestDigest": "d" * 64,
            },
            "subtitleManifest": {
                "subtitleManifestRef": "subtitle-1",
                "subtitleManifestDigest": "e" * 64,
            },
            "output": {
                "width": 64,
                "height": 64,
                "frameRate": {"numerator": 24, "denominator": 1},
                "totalFrames": 24,
            },
        }

        with (
            mock.patch.object(
                v4_preview, "_resolve_preview_base", return_value=base
            ),
            mock.patch.object(
                v4_preview, "_resolve_effect_stage", side_effect=stages[:4]
            ),
            mock.patch.object(
                v4_preview,
                "_resolve_overlay_preview_stage",
                side_effect=stages[4:6],
            ),
            mock.patch.object(
                v4_distance,
                "resolve_distance_state_preview_stage",
                return_value=stages[6],
                create=True,
            ) as distance_resolver,
            mock.patch.object(
                v4_preview, "_resolve_glyph_stage", return_value=glyph_stage
            ),
            mock.patch(
                "services.v4_platform.composition."
                "_build_timeline_preview_execution_request_v1",
                return_value=legacy,
            ),
        ):
            request = v4_preview._build_effect_preview_v3_request(
                command,
                resolutions,
                artifact_root=mock.sentinel.artifact_root,
            )

        distance_resolver.assert_called_once_with(
            bindings[6],
            resolutions["effectExecutions"][bindings[6]["resultRef"]],
            artifact_root=mock.sentinel.artifact_root,
            base=base,
        )
        self.assertEqual(
            request["schemaVersion"],
            v4_preview.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V5,
        )
        self.assertEqual(request["effectStages"], stages)
        self.assertEqual(
            request["effectBindingsDigest"], _SEVEN_STAGE_GOLDEN
        )

    def test_v3_v5_request_accepts_exact_rank_six_distance_stage(self) -> None:
        bindings = _profile(7)
        base = {
            "assetVersionRef": "base-version-1",
            "assetVersionDigest": "1" * 64,
            "storageKey": "inputs/base.mp4",
            "fileDigest": "sha256:" + "2" * 64,
            "pixelDigest": "sha256:" + "3" * 64,
            "pixelDigestSpec": "pixel-spec-v1",
            "width": 64,
            "height": 64,
            "frameCount": 24,
            "frameRate": 24,
            "pixelFormat": "yuv420p",
        }
        stages: list[dict] = []
        for binding in bindings:
            stages.append(
                {
                    "effectMode": binding["effectMode"],
                    "workspaceRef": "workspace-1",
                    "productionRunRef": "run-1",
                    "basePlate": deepcopy(base),
                    "requirementRef": binding["requirementRef"],
                    "requirementDigest": binding["requirementDigest"],
                    "v5ExecutionRequestRef": binding["executionRequestRef"],
                    "v5ExecutionRequestDigest": binding[
                        "executionRequestDigest"
                    ],
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "payloadDigest": sha256(
                        binding["resultRef"].encode("utf-8")
                    ).hexdigest(),
                }
            )
        stages[2]["localExposureStage"] = stages[1]
        for stage in stages[4:6]:
            stage["overlaySpec"] = {
                "frameRangeStartInclusive": stage.pop(
                    "frameRangeStartInclusive"
                ),
                "frameRangeEndExclusive": stage.pop(
                    "frameRangeEndExclusive"
                ),
            }

        glyph = {"payloadDigest": "c" * 64}
        audio_mix = {
            "mixRequestRef": "mix-1",
            "mixRequestDigest": "d" * 64,
        }
        subtitle = {
            "subtitleManifestRef": "subtitle-1",
            "subtitleManifestDigest": "e" * 64,
        }
        output = {
            "width": 64,
            "height": 64,
            "frameRate": {"numerator": 24, "denominator": 1},
            "totalFrames": 24,
        }
        effect_digest = _digest(
            {
                "schemaVersion": "v5.m13-effect-preview-bindings.v4",
                "effectResultBindings": bindings,
                "glyphRequirementBinding": GLYPH,
            }
        )
        input_digest = _digest(
            {
                "baseVideo": base,
                "deterministicEffectRequestDigests": [
                    stage["payloadDigest"] for stage in stages
                ],
                "glyphRevealRequestDigest": glyph["payloadDigest"],
                "effectResultBindings": bindings,
                "glyphRequirementBinding": GLYPH,
                "audioMix": audio_mix,
                "subtitleManifest": subtitle,
            }
        )
        timeline_ref = "timeline-version-1"
        timeline_digest = "f" * 64
        execution_ref = "m13-effect-preview-execution-" + sha256(
            v3_preview._canonical_json(
                {
                    "timelineVersionRef": timeline_ref,
                    "timelineVersionDigest": timeline_digest,
                    "inputBindingsDigest": input_digest,
                    "effectBindingsDigest": effect_digest,
                    "outputContractDigest": _digest(output),
                }
            )
        ).hexdigest()[:32]
        unsealed = {
            "schemaVersion": "v4.m13-effect-preview-execution-request.v5",
            "executionRequestRef": execution_ref,
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "timelineVersionRef": timeline_ref,
            "timelineVersionDigest": timeline_digest,
            "inputBindingsDigest": input_digest,
            "baseVideo": base,
            "effectStages": [{} for _ in stages],
            "glyphStage": {},
            "effectResultBindings": bindings,
            "glyphRequirementBinding": GLYPH,
            "effectBindingsDigest": effect_digest,
            "audioMix": audio_mix,
            "subtitleManifest": subtitle,
            "output": output,
            "publicationAllowed": False,
        }
        request = {**unsealed, "payloadDigest": _digest(unsealed)}

        with (
            mock.patch.object(
                v3_preview, "_validate_effect_request", side_effect=stages[:4]
            ),
            mock.patch.object(
                v3_overlays,
                "validate_overlay_preview_stage",
                side_effect=stages[4:6],
            ),
            mock.patch.object(
                v3_distance,
                "validate_distance_state_preview_stage",
                return_value=stages[6],
            ),
            mock.patch.object(
                v3_preview, "_validate_glyph_request", return_value=glyph
            ),
        ):
            validated = v3_preview._validate_effect_preview_request(request)

        self.assertEqual(validated["effectStages"], stages)
        self.assertEqual(
            validated["schemaVersion"],
            v3_preview.EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V5,
        )
        self.assertEqual(v3_preview.EFFECT_PREVIEW_RENDERER_VERSION_V5, "5")


if __name__ == "__main__":
    unittest.main()
