from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.timeline_editing import (
    DETERMINISTIC_EFFECT_KINDS,
    M13_E4_DETERMINISTIC_EFFECT_KINDS,
    TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
    TimelineEditingStaleInputError,
)
from services.v5_core_os.episode_production.timeline_preview import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC,
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION,
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2,
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4,
    PCM_CONTENT_DIGEST_SPEC,
    PreviewArtifactError,
    TimelinePreviewContractError,
    TimelineSourceBindingError,
    V4_EFFECT_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION,
    _EFFECT_PREVIEW_RESULT_BINDING_FIELDS,
    _effect_preview_bindings,
    _v4_effect_preview_result,
)
from tests.contract.test_m13_e2_timeline_preview_contract import GLYPH, _binding
from tests.integration.test_m13_e1_timeline_effect_binding import (
    _apply_insert_and_bind,
    _effect_authorities,
    _sealed,
)


_E4_EFFECT_KIND = "DISTANCE_STATE_TRANSITION"
_E4_MODES = (
    "SCRATCH_REVEAL",
    "LOCAL_EXPOSURE",
    "FLAME_EXTINGUISH",
    "SMOKE",
    "NAMEPLATE_TEXT",
    "FACE_MARK_COMPENSATION",
    _E4_EFFECT_KIND,
)
_LEGACY_GOLDENS = {
    2: "b243db7839d42ad0f785d59002ee9e58a41ded4e66b1a85635a1a0c52b2c1bb0",
    4: "a7ee316dd191d1d1f21d98a4a61c740ee13ca0ba9ecd722468c69c4c65c05cbd",
    6: "b57f5802e6ccce50b7a39f4fa46f6b761bd1fe3c4d642b360ea7d184e039e765",
}
_E4_BINDINGS_GOLDEN = (
    "9066c2ba145248ab4dffefe3b5e3d8bea77e728e6b6c491bccf43512664120da"
)


def _profile(modes: tuple[str, ...]) -> list[dict]:
    return [_binding(index, mode) for index, mode in enumerate(modes)]


def _e4_effect_authorities() -> tuple[dict, dict]:
    requirement, result = _effect_authorities(effect_mode=_E4_EFFECT_KIND)
    requirement["schemaVersion"] = (
        "v5.m13-distance-state-transition-requirement.v1"
    )
    requirement = _sealed(requirement)
    result.update(
        {
            "schemaVersion": "v5.m13-distance-state-transition-result.v1",
            "requirementDigest": requirement["payloadDigest"],
            "state": "COMPOSED_CANDIDATE",
            "assetAdmissionState": "NOT_ADMITTED",
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
        }
    )
    return requirement, _sealed(result)


def _v4_result(bindings: list[dict], renderer_version: str) -> dict:
    unsealed = {
        "schemaVersion": V4_EFFECT_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION,
        "compositionResultRef": "composition-result-e4",
        "artifactRef": "composition-artifact-e4",
        "executionRequestRef": "composition-request-e4",
        "executionRequestDigest": "1" * 64,
        "timelineVersionRef": "timeline-version-e4",
        "timelineVersionDigest": "2" * 64,
        "inputBindingsDigest": "3" * 64,
        "effectResultBindings": bindings,
        "glyphRequirementBinding": deepcopy(GLYPH),
        "effectBindingsDigest": _effect_preview_bindings(bindings, GLYPH)[2],
        "mixRequestRef": "mix-request-e4",
        "mixRequestDigest": "4" * 64,
        "subtitleManifestRef": "subtitle-manifest-e4",
        "subtitleManifestDigest": "5" * 64,
        "outputStorageKey": "workspace/run/composition/preview-e4.mp4",
        "outputByteSize": 1,
        "outputMediaProbe": {
            "container": "mp4",
            "videoCodec": "h264",
            "pixelFormat": "yuv420p",
            "width": 64,
            "height": 64,
            "frameRate": {"numerator": 24, "denominator": 1},
            "frameCount": 24,
            "audioCodec": "aac",
            "sampleRate": 48_000,
            "channelCount": 2,
            "sampleCount": 48_000,
        },
        "outputDigest": {
            "fileDigest": "sha256:" + "6" * 64,
            "fileDigestAlgorithm": "sha256",
            "decodedFramePixelDigest": "sha256:" + "7" * 64,
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC,
            "pixelMode": "RGBA",
            "width": 64,
            "height": 64,
            "frameCount": 24,
            "frameRate": {"numerator": 24, "denominator": 1},
            "pcmContentDigest": "8" * 64,
            "pcmDigestSpec": PCM_CONTENT_DIGEST_SPEC,
            "sampleRate": 48_000,
            "channelCount": 2,
            "sampleCount": 48_000,
        },
        "rendererIdentity": "v3.deterministic-timeline-preview-ffmpeg",
        "rendererVersion": renderer_version,
        "ffmpegIdentity": "ffmpeg-e4-fixture",
        "runtimeEvidenceDigest": "sha256:" + "9" * 64,
        "adapterIdentity": "v4.local-composition-executor.v1",
        "provenance": "LOCAL_EVIDENCE",
        "providerUsed": False,
        "gpuUsed": False,
        "publicationAllowed": False,
    }
    return {**unsealed, "payloadDigest": _digest(unsealed)}


class M13E4TimelinePreviewContractTests(unittest.TestCase):
    def test_e4_kind_reuses_the_existing_effect_clip_and_bind_operation(self) -> None:
        self.assertEqual(
            M13_E4_DETERMINISTIC_EFFECT_KINDS, frozenset({_E4_EFFECT_KIND})
        )
        self.assertIn(_E4_EFFECT_KIND, DETERMINISTIC_EFFECT_KINDS)
        requirement, result = _e4_effect_authorities()

        _, inserted, bound, _, bind_command, _ = _apply_insert_and_bind(
            requirement=requirement,
            result=result,
        )

        self.assertEqual(
            bind_command.as_dict()["schemaVersion"],
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        )
        before = next(
            item.as_dict()["sourceBinding"]
            for item in inserted.clips
            if item.as_dict()["clipRef"] == "clip-masked-surface-e1"
        )
        after = next(
            item.as_dict()["sourceBinding"]
            for item in bound.clips
            if item.as_dict()["clipRef"] == "clip-masked-surface-e1"
        )
        self.assertIsNone(before["effectResultRef"])
        self.assertEqual(after["effectKind"], _E4_EFFECT_KIND)
        self.assertEqual(after["effectResultRef"], result["resultRef"])
        self.assertEqual(after["effectResultDigest"], result["payloadDigest"])

    def test_e4_bind_rejects_each_non_candidate_lifecycle_drift(self) -> None:
        requirement, result = _e4_effect_authorities()
        changes = {
            "state": "SUCCEEDED",
            "assetAdmissionState": "ADMITTED",
            "masterState": "CREATED",
            "exportState": "CREATED",
        }
        for field, value in changes.items():
            changed = deepcopy(result)
            changed[field] = value
            changed = _sealed(changed)
            with self.subTest(field=field), self.assertRaises(
                TimelineEditingStaleInputError
            ):
                _apply_insert_and_bind(
                    requirement=requirement,
                    result=changed,
                )

    def test_legacy_profile_schema_and_digest_literals_are_unchanged(self) -> None:
        profiles = {
            2: ("SCRATCH_REVEAL", "LOCAL_EXPOSURE"),
            4: (
                "LIGHT_SWEEP",
                "LOCAL_EXPOSURE",
                "FLAME_EXTINGUISH",
                "SMOKE",
            ),
            6: _E4_MODES[:6],
        }
        schemas = {
            2: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION,
            4: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2,
            6: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
        }
        self.assertEqual(
            schemas,
            {
                2: "v5.m13-effect-preview-bindings.v1",
                4: "v5.m13-effect-preview-bindings.v2",
                6: "v5.m13-effect-preview-bindings.v3",
            },
        )
        for count, modes in profiles.items():
            with self.subTest(count=count):
                bindings = _profile(modes)
                self.assertEqual(
                    _effect_preview_bindings(bindings, GLYPH)[2],
                    _LEGACY_GOLDENS[count],
                )

    def test_e4_seven_stage_profile_has_additive_v4_binding_digest(self) -> None:
        bindings = _profile(_E4_MODES)
        normalized, glyph, digest = _effect_preview_bindings(bindings, GLYPH)

        self.assertEqual(normalized, bindings)
        self.assertEqual(glyph, GLYPH)
        self.assertEqual(
            set(bindings[-1]), _EFFECT_PREVIEW_RESULT_BINDING_FIELDS
        )
        self.assertEqual(
            EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4,
            "v5.m13-effect-preview-bindings.v4",
        )
        self.assertEqual(digest, _E4_BINDINGS_GOLDEN)
        self.assertEqual(
            digest,
            _digest(
                {
                    "schemaVersion": EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4,
                    "effectResultBindings": bindings,
                    "glyphRequirementBinding": GLYPH,
                }
            ),
        )

    def test_e4_profile_is_closed_and_rank_six_is_last(self) -> None:
        bindings = _profile(_E4_MODES)
        reordered = deepcopy(bindings)
        reordered[5], reordered[6] = reordered[6], reordered[5]
        with self.assertRaises(TimelinePreviewContractError):
            _effect_preview_bindings(reordered, GLYPH)

        with self.assertRaises(TimelinePreviewContractError):
            _effect_preview_bindings(
                [*bindings, _binding(7, _E4_EFFECT_KIND)], GLYPH
            )

    def test_renderer_version_five_is_closed_to_the_e4_profile(self) -> None:
        e4_bindings = _profile(_E4_MODES)
        self.assertEqual(
            _v4_effect_preview_result(
                _v4_result(e4_bindings, "5")
            )["rendererVersion"],
            "5",
        )
        with self.assertRaisesRegex(
            PreviewArtifactError, "V4 effect preview authority is invalid"
        ):
            _v4_effect_preview_result(_v4_result(e4_bindings, "4"))

        legacy_bindings = _profile(_E4_MODES[:6])
        self.assertEqual(
            _v4_effect_preview_result(
                _v4_result(legacy_bindings, "4")
            )["rendererVersion"],
            "4",
        )


if __name__ == "__main__":
    unittest.main()
