from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest
from unittest import mock

from services.v3_render_core import deterministic_overlays as v3_overlays
from services.v3_render_core import masked_surface as v3_preview
from services.v4_platform.masked_surface_effects import (
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3 as V4_BINDINGS_V3,
    MaskedSurfaceRequestValidationError,
    _effect_preview_bindings as v4_effect_preview_bindings,
)
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.timeline_editing import (
    TimelineEditingConflictError,
    TimelineEditingStaleInputError,
    build_timeline_clip,
    build_timeline_version,
    validate_timeline_snapshot,
)
from services.v5_core_os.episode_production.timeline_preview import (
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
    TimelinePreviewContractError,
    TimelineSourceBindingError,
    _effect_preview_bindings,
)
from tests.contract.test_m13_e2_timeline_preview_contract import GLYPH, _binding
from tests.contract.test_m13_timeline_editing_contract import (
    DIGEST_A,
    DIGEST_B,
    RUN,
    WORKSPACE,
    clip_command,
    source_resolver as base_source_resolver,
    timeline_version_command,
    valid_snapshot,
)


_TWO_STAGE_GOLDEN = (
    "b243db7839d42ad0f785d59002ee9e58a41ded4e66b1a85635a1a0c52b2c1bb0"
)
_FOUR_STAGE_GOLDEN = (
    "a7ee316dd191d1d1f21d98a4a61c740ee13ca0ba9ecd722468c69c4c65c05cbd"
)
_SIX_STAGE_MODES = (
    "SCRATCH_REVEAL",
    "LOCAL_EXPOSURE",
    "FLAME_EXTINGUISH",
    "SMOKE",
    "NAMEPLATE_TEXT",
    "FACE_MARK_COMPENSATION",
)


def _profile(modes: tuple[str, ...]) -> list[dict]:
    return [_binding(index, mode) for index, mode in enumerate(modes)]


def _e3_effect_clip(
    *, clip_ref: str, requirement_ref: str, requirement_digest: str
) -> dict:
    command = clip_command("EFFECT", clip_ref=clip_ref)
    command.update(
        {
            "layer": 6,
            "zOrder": 6,
            "blendMode": "NORMAL",
            "sourceBinding": {
                "effectRequirementRef": requirement_ref,
                "effectRequirementDigest": requirement_digest,
                "effectKind": "NAMEPLATE_TEXT",
                "effectResultRef": None,
                "effectResultDigest": None,
                "layer": 6,
                "blendMode": "NORMAL",
            },
        }
    )
    return command


class M13E3TimelinePreviewContractTests(unittest.TestCase):
    def test_two_and_four_stage_wire_digests_are_preserved(self) -> None:
        two = _profile(("SCRATCH_REVEAL", "LOCAL_EXPOSURE"))
        four = _profile(
            (
                "LIGHT_SWEEP",
                "LOCAL_EXPOSURE",
                "FLAME_EXTINGUISH",
                "SMOKE",
            )
        )

        self.assertEqual(_effect_preview_bindings(two, GLYPH)[2], _TWO_STAGE_GOLDEN)
        self.assertEqual(
            _effect_preview_bindings(four, GLYPH)[2], _FOUR_STAGE_GOLDEN
        )
        self.assertEqual(
            v4_effect_preview_bindings(two, GLYPH)[2], _TWO_STAGE_GOLDEN
        )
        self.assertEqual(
            v4_effect_preview_bindings(four, GLYPH)[2], _FOUR_STAGE_GOLDEN
        )

    def test_six_stage_profile_uses_additive_v3_binding_digest(self) -> None:
        bindings = _profile(_SIX_STAGE_MODES)
        expected = _digest(
            {
                "schemaVersion": EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
                "effectResultBindings": bindings,
                "glyphRequirementBinding": GLYPH,
            }
        )

        normalized, glyph, digest = _effect_preview_bindings(bindings, GLYPH)
        self.assertEqual(normalized, bindings)
        self.assertEqual(glyph, GLYPH)
        self.assertEqual(digest, expected)
        self.assertEqual(V4_BINDINGS_V3, EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3)
        self.assertEqual(v4_effect_preview_bindings(bindings, GLYPH)[2], expected)

    def test_only_closed_stage_lengths_and_ranks_are_accepted(self) -> None:
        bindings = _profile(_SIX_STAGE_MODES)
        for count in (1, 3, 5):
            with self.subTest(count=count):
                with self.assertRaises(TimelinePreviewContractError):
                    _effect_preview_bindings(bindings[:count], GLYPH)
                with self.assertRaises(MaskedSurfaceRequestValidationError):
                    v4_effect_preview_bindings(bindings[:count], GLYPH)

        seventh = [*bindings, _binding(6, "FACE_MARK_COMPENSATION")]
        with self.assertRaises(TimelinePreviewContractError):
            _effect_preview_bindings(seventh, GLYPH)
        with self.assertRaises(MaskedSurfaceRequestValidationError):
            v4_effect_preview_bindings(seventh, GLYPH)

    def test_e3_stage_order_is_fail_closed(self) -> None:
        bindings = _profile(_SIX_STAGE_MODES)
        reordered = deepcopy(bindings)
        reordered[4], reordered[5] = reordered[5], reordered[4]

        with self.assertRaises(TimelineSourceBindingError):
            _effect_preview_bindings(reordered, GLYPH)
        with self.assertRaises(MaskedSurfaceRequestValidationError):
            v4_effect_preview_bindings(reordered, GLYPH)

    def test_e3_clip_layer_must_match_its_requirement_binding(self) -> None:
        command = _e3_effect_clip(
            clip_ref="effect-clip-e3-layer-mismatch",
            requirement_ref="effect-requirement-e3-layer-mismatch",
            requirement_digest="3" * 64,
        )
        command["sourceBinding"]["layer"] = 7
        with self.assertRaisesRegex(
            TimelineEditingStaleInputError,
            "EFFECT layer/blend/transform binding is stale",
        ):
            build_timeline_clip(command)

    def test_overlapping_e3_clips_cannot_share_layer_and_z_order(self) -> None:
        fixture = valid_snapshot()
        requirement_digests = {
            "effect-requirement-e3-a": "3" * 64,
            "effect-requirement-e3-b": "4" * 64,
        }
        additions = [
            build_timeline_clip(
                _e3_effect_clip(
                    clip_ref=f"effect-clip-e3-{suffix}",
                    requirement_ref=requirement_ref,
                    requirement_digest=requirement_digest,
                )
            )
            for suffix, (requirement_ref, requirement_digest) in zip(
                ("a", "b"), requirement_digests.items(), strict=True
            )
        ]
        clips = [*fixture["clips"], *additions]
        version = build_timeline_version(
            timeline_version_command(),
            output_profile_bindings=[fixture["profile"]],
            tracks=fixture["tracks"],
            clips=clips,
        )

        def source_resolver(source_type: str, source_ref: str) -> dict:
            if source_type == "EFFECT_REQUIREMENT" and source_ref in requirement_digests:
                return {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                    "requirementRef": source_ref,
                    "payloadDigest": requirement_digests[source_ref],
                    "effectMode": "NAMEPLATE_TEXT",
                    "targetShotRef": "creative-shot-zhen-v1",
                    "targetShotVersionRef": "creative-shot-version-zhen-v1",
                    "targetShotVersionDigest": DIGEST_B,
                    "basePlateAssetVersionRef": "asset-version-effect-base-v1",
                    "basePlateAssetVersionDigest": DIGEST_A,
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "blendMode": "NORMAL",
                    "layer": 6,
                }
            authority = base_source_resolver(source_type, source_ref)
            if (
                source_type == "ASSET_VERSION"
                and source_ref == "asset-version-effect-base-v1"
            ):
                authority.update(
                    {
                        "creativeShotRef": "creative-shot-zhen-v1",
                        "creativeShotVersionRef": "creative-shot-version-zhen-v1",
                        "creativeShotDigest": DIGEST_B,
                    }
                )
            return authority

        with self.assertRaisesRegex(
            TimelineEditingConflictError,
            "z-order conflicts in lane",
        ):
            validate_timeline_snapshot(
                version,
                fixture["tracks"],
                clips,
                timeline=fixture["timeline"],
                source_resolver=source_resolver,
                expected_script={
                    "scriptVersionRef": "script-version-v1",
                    "scriptVersionDigest": DIGEST_A,
                },
                expected_storyboard={
                    "storyboardVersionRef": "storyboard-version-v1",
                    "storyboardVersionDigest": DIGEST_B,
                },
            )

    def test_v3_request_v4_accepts_only_the_exact_six_stage_projection(self) -> None:
        bindings = _profile(_SIX_STAGE_MODES)
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
        stages = []
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
        for stage in stages[4:]:
            stage["overlaySpec"] = {
                "frameRangeStartInclusive": stage.pop(
                    "frameRangeStartInclusive"
                ),
                "frameRangeEndExclusive": stage.pop(
                    "frameRangeEndExclusive"
                ),
            }
        glyph = {"payloadDigest": "c" * 64}
        audio_mix = {"mixRequestRef": "mix-1", "mixRequestDigest": "d" * 64}
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
                "schemaVersion": EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
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
            "schemaVersion": v3_preview.EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4,
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
                side_effect=stages[4:],
                create=True,
            ),
            mock.patch.object(
                v3_preview, "_validate_glyph_request", return_value=glyph
            ),
        ):
            validated = v3_preview._validate_effect_preview_request(request)

        self.assertEqual(stages, validated["effectStages"])
        self.assertEqual(
            v3_preview.EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4,
            validated["schemaVersion"],
        )


if __name__ == "__main__":
    unittest.main()
