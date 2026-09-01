from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.rendering import (
    COMPOSITION_PROVENANCE,
    REQUIRED_EFFECT_KINDS,
    RenderDomainContractError,
    RenderDomainStaleInputError,
    build_composition,
    build_composition_version,
    build_render_manifest,
    composition_plan_digests,
    render_manifest_digest_specs,
    seal_composition_track_binding,
    validate_composition,
    validate_composition_version,
    validate_render_manifest,
)


CREATED_AT = "2026-09-01T02:30:00Z"


def digest(label: str) -> str:
    return _digest({"label": label})


def asset(label: str) -> dict:
    return {
        "assetVersionRef": f"asset-version-{label}",
        "version": 1,
        "assetVersionDigest": digest(f"asset-{label}"),
    }


def binding(
    kind: str,
    ordinal: int,
    *,
    effect_kind: str | None = None,
) -> dict:
    source = {
        "sourceRef": f"source-{kind.lower()}-{ordinal}",
        "sourceDigest": digest(f"source-{kind}-{ordinal}"),
    }
    cue = None
    stem = None
    validation = None
    effect = None
    if kind in {"AUDIO", "SUBTITLE"}:
        stem = {
            "stemSetVersionRef": "stem-set-version-1",
            "stemSetVersion": 1,
            "stemSetDigest": digest("stem-set"),
            "stemMemberRef": f"stem-member-{ordinal}",
            "stemMemberDigest": digest(f"stem-member-{ordinal}"),
        }
        validation = {
            "validationRef": "audio-validation",
            "validationVersionRef": "audio-validation-version-1",
            "version": 1,
            "validationDigest": digest("audio-validation"),
            "validationState": "PASSED",
        }
    if kind == "SUBTITLE":
        cue = {
            "cueVersionRef": "audio-cue-version-1",
            "version": 1,
            "cueDigest": digest("audio-cue"),
        }
    if kind == "EFFECT":
        assert effect_kind is not None
        result_ref = (
            None if effect_kind == "GLYPH_REVEAL" else f"result-{effect_kind.lower()}"
        )
        effect = {
            "effectKind": effect_kind,
            "requirementRef": f"requirement-{effect_kind.lower()}",
            "requirementDigest": digest(f"requirement-{effect_kind}"),
            "resultRef": result_ref,
            "resultDigest": (
                None if result_ref is None else digest(f"result-{effect_kind}")
            ),
        }
        source = {
            "effectRequirementRef": effect["requirementRef"],
            "effectRequirementDigest": effect["requirementDigest"],
            "effectKind": effect_kind,
            "effectResultRef": effect["resultRef"],
            "effectResultDigest": effect["resultDigest"],
        }
    return seal_composition_track_binding(
        {
            "trackRef": f"track-{kind.lower()}",
            "trackDigest": digest(f"track-{kind}"),
            "trackKind": kind,
            "trackOrder": {"VIDEO": 0, "AUDIO": 1, "SUBTITLE": 2, "EFFECT": 3}[
                kind
            ],
            "trackEnabled": True,
            "lanePolicy": "MIX" if kind == "AUDIO" else "LAYERED_Z_ORDER",
            "clipRef": f"clip-{kind.lower()}-{ordinal}",
            "clipDigest": digest(f"clip-{kind}-{ordinal}"),
            "clipKind": kind,
            "timelineStartFrameInclusive": ordinal,
            "timelineEndFrameExclusive": ordinal + 10,
            "enabled": True,
            "layer": ordinal,
            "zOrder": ordinal,
            "opacity": 1000,
            "blendMode": "NORMAL",
            "sourceBinding": source,
            "sourceAssetVersions": [asset(f"{kind.lower()}-{ordinal}")],
            "audioCueBinding": cue,
            "stemBinding": stem,
            "technicalValidationBinding": validation,
            "effectBinding": effect,
            "transitionIn": {"kind": "CUT", "durationFrames": 0},
            "transitionOut": {"kind": "CUT", "durationFrames": 0},
            "speed": {"numerator": 1, "denominator": 1},
            "transform": {"x": 0, "y": 0, "scale": 1000},
            "maskBindings": [],
        }
    )


def composition_root() -> dict:
    return build_composition(
        {
            "workspaceRef": "workspace-r1a",
            "productionRunRef": "run-r1a",
            "projectRef": "project-r1a",
            "seriesRef": "series-r1a",
            "episodeRef": "episode-r1a",
            "compositionRef": "composition-r1a",
            "timelineRef": "timeline-r1a",
            "createdAt": CREATED_AT,
            "provenance": COMPOSITION_PROVENANCE,
            "publicationAllowed": False,
        }
    )


def composition_version(
    *,
    version_number: int = 1,
    predecessor: dict | None = None,
) -> dict:
    plan = {
        "timelineRef": "timeline-r1a",
        "timelineVersionRef": f"timeline-r1a-version-{version_number}",
        "timelineVersionNumber": version_number,
        "timelineVersionDigest": digest(f"timeline-version-{version_number}"),
        "videoTrackBindings": [binding("VIDEO", 0)],
        "audioTrackBindings": [binding("AUDIO", 0)],
        "subtitleTrackBindings": [binding("SUBTITLE", 0)],
        "effectTrackBindings": [
            binding("EFFECT", ordinal, effect_kind=kind)
            for ordinal, kind in enumerate(sorted(REQUIRED_EFFECT_KINDS))
        ],
    }
    return build_composition_version(
        {
            "workspaceRef": "workspace-r1a",
            "productionRunRef": "run-r1a",
            "projectRef": "project-r1a",
            "seriesRef": "series-r1a",
            "episodeRef": "episode-r1a",
            "compositionRef": "composition-r1a",
            "compositionVersionRef": f"composition-r1a-version-{version_number}",
            "versionNumber": version_number,
            "parentCompositionVersionRef": (
                None if predecessor is None else predecessor["compositionVersionRef"]
            ),
            "parentCompositionVersionDigest": (
                None if predecessor is None else predecessor["payloadDigest"]
            ),
            **plan,
            **composition_plan_digests(plan),
            "createdAt": CREATED_AT,
            "provenance": COMPOSITION_PROVENANCE,
            "publicationAllowed": False,
        },
        predecessor=predecessor,
    )


def manifest_command(
    *,
    width: int = 704,
    height: int = 1280,
    subtitle_mode: str = "SIDECAR",
) -> dict:
    font_ref = "font-version-1" if subtitle_mode == "BURN_IN" else None
    font_digest = digest("font") if subtitle_mode == "BURN_IN" else None
    timing = None if subtitle_mode == "NONE" else digest("subtitle-timing")
    return {
        "workspaceRef": "workspace-r1a",
        "productionRunRef": "run-r1a",
        "renderManifestRef": f"manifest-{width}-{height}-{subtitle_mode.lower()}",
        "timelineVersionRef": "timeline-r1a-version-1",
        "timelineVersionDigest": digest("timeline-version-1"),
        "compositionVersionRef": "composition-r1a-version-1",
        "compositionVersionDigest": digest("composition-version-1"),
        "outputProfile": {
            "profileRef": f"vertical-{width}x{height}",
            "width": width,
            "height": height,
            "frameRateNumerator": 24,
            "frameRateDenominator": 1,
            "pixelAspectRatioNumerator": 1,
            "pixelAspectRatioDenominator": 1,
            "resizeMode": "FIT_PAD",
            "backgroundPolicy": "BLACK",
            "safeArea": {
                "leftPixels": 0,
                "topPixels": 0,
                "rightPixels": 0,
                "bottomPixels": 0,
            },
        },
        "videoEncoding": {
            "codec": "H264",
            "pixelFormat": "YUV420P",
            "qualityMode": "CRF",
            "qualityValue": 18,
            "profile": "HIGH",
            "level": "4.1",
            "gopFrames": 48,
            "deterministicThreadPolicy": "SINGLE_THREAD",
        },
        "colorMetadata": {
            "colorPrimaries": "BT709",
            "colorTransfer": "BT709",
            "colorSpace": "BT709",
            "colorRange": "TV",
        },
        "audioEncoding": {
            "enabled": True,
            "codec": "AAC",
            "sampleRate": 48_000,
            "channelCount": 2,
            "bitrate": 128_000,
        },
        "subtitleMode": subtitle_mode,
        "subtitleTimingDigest": timing,
        "subtitleFontAssetVersionRef": font_ref,
        "subtitleFontAssetVersionDigest": font_digest,
        "rendererIdentity": "v3-deterministic-render-core",
        "rendererVersion": "1",
        "ffmpegBinaryDigest": digest("ffmpeg"),
        "ffprobeBinaryDigest": digest("ffprobe"),
        **render_manifest_digest_specs(),
        "publicationAllowed": False,
        "masterState": "NOT_CREATED",
        "exportState": "NOT_CREATED",
        "createdAt": CREATED_AT,
    }


class M13R1ARenderDomainContractTests(unittest.TestCase):
    def test_composition_root_is_closed_immutable_and_non_publishing(self) -> None:
        root = composition_root()
        self.assertEqual(validate_composition(root).as_dict(), root)
        self.assertFalse(root["publicationAllowed"])
        changed = deepcopy(root)
        changed["timelineRef"] = "/tmp/client-timeline"
        with self.assertRaises(RenderDomainStaleInputError):
            validate_composition(changed)
        command = {key: value for key, value in root.items() if key not in {"schemaVersion", "payloadDigest"}}
        command["outputDigest"] = digest("forbidden")
        with self.assertRaises(RenderDomainContractError):
            build_composition(command)

    def test_full_composition_version_has_stable_graph_and_eight_effects(self) -> None:
        first = composition_version()
        second = composition_version()
        self.assertEqual(first, second)
        self.assertEqual(
            len(first["effectTrackBindings"]), len(REQUIRED_EFFECT_KINDS)
        )
        self.assertEqual(
            {
                item["effectBinding"]["effectKind"]
                for item in first["effectTrackBindings"]
            },
            REQUIRED_EFFECT_KINDS,
        )
        self.assertEqual(validate_composition_version(first).as_dict(), first)
        changed = deepcopy(first)
        changed["clipOrderDigest"] = digest("changed-order")
        changed.pop("payloadDigest")
        changed["payloadDigest"] = _digest(changed)
        with self.assertRaises(RenderDomainStaleInputError):
            validate_composition_version(changed)

    def test_composition_predecessor_is_exact(self) -> None:
        first = composition_version()
        second = composition_version(version_number=2, predecessor=first)
        self.assertEqual(
            validate_composition_version(second, predecessor=first).as_dict(),
            second,
        )
        wrong = deepcopy(first)
        wrong["compositionVersionRef"] = "composition-r1a-wrong"
        wrong.pop("payloadDigest")
        wrong["payloadDigest"] = _digest(wrong)
        with self.assertRaises(RenderDomainStaleInputError):
            validate_composition_version(second, predecessor=wrong)

    def test_composition_binding_rejects_path_filter_and_argv(self) -> None:
        for forbidden in (
            {"absolutePath": "/tmp/input.mp4"},
            {"ffmpegFilter": "scale=704:1280"},
            {"argv": ["ffmpeg", "-i", "input"]},
        ):
            value = binding("VIDEO", 0)
            value["sourceBinding"] = forbidden
            value.pop("bindingDigest")
            value["bindingDigest"] = _digest(value)
            with self.subTest(forbidden=next(iter(forbidden))):
                with self.assertRaises(RenderDomainContractError):
                    plan = composition_version()
                    plan["videoTrackBindings"] = [value]
                    plan.pop("payloadDigest")
                    plan["payloadDigest"] = _digest(plan)
                    validate_composition_version(plan)

    def test_audio_and_subtitle_bindings_require_passed_technical_validation(self) -> None:
        for kind in ("AUDIO", "SUBTITLE"):
            value = binding(kind, 0)
            value["technicalValidationBinding"] = None
            value.pop("bindingDigest")
            value["bindingDigest"] = _digest(value)
            plan = composition_version()
            plan[f"{kind.lower()}TrackBindings"] = [value]
            plan.pop("payloadDigest")
            plan["payloadDigest"] = _digest(plan)
            with self.subTest(kind=kind):
                with self.assertRaises(RenderDomainContractError):
                    validate_composition_version(plan)

    def test_render_manifest_supports_three_vertical_profiles(self) -> None:
        for width, height in ((704, 1280), (720, 1280), (1080, 1920)):
            with self.subTest(size=(width, height)):
                manifest = build_render_manifest(
                    manifest_command(width=width, height=height)
                )
                self.assertEqual(validate_render_manifest(manifest).as_dict(), manifest)
                self.assertFalse(manifest["publicationAllowed"])
                self.assertEqual(manifest["masterState"], "NOT_CREATED")
                self.assertEqual(manifest["exportState"], "NOT_CREATED")

    def test_render_manifest_rejects_open_or_invalid_encoding_fields(self) -> None:
        cases = (
            ("frameRateDenominator", 0),
            ("resizeMode", "FREEFORM"),
            ("codec", "HEVC"),
            ("profile", "CUSTOM"),
        )
        for field, replacement in cases:
            command = manifest_command()
            if field in command["outputProfile"]:
                command["outputProfile"][field] = replacement
            else:
                command["videoEncoding"][field] = replacement
            with self.subTest(field=field):
                with self.assertRaises(RenderDomainContractError):
                    build_render_manifest(command)

    def test_subtitle_modes_are_closed_and_burn_in_requires_font(self) -> None:
        for mode in ("NONE", "SIDECAR", "BURN_IN"):
            with self.subTest(mode=mode):
                build_render_manifest(manifest_command(subtitle_mode=mode))
        invalid = manifest_command()
        invalid["subtitleMode"] = "CLIENT_FILTER"
        with self.assertRaises(RenderDomainContractError):
            build_render_manifest(invalid)
        missing_font = manifest_command(subtitle_mode="BURN_IN")
        missing_font["subtitleFontAssetVersionRef"] = None
        missing_font["subtitleFontAssetVersionDigest"] = None
        with self.assertRaises(RenderDomainContractError):
            build_render_manifest(missing_font)

    def test_render_manifest_cannot_contain_execution_results(self) -> None:
        for forbidden in (
            "fileDigest",
            "decodedFramePixelDigest",
            "pcmContentDigest",
            "artifactPath",
            "renderCandidateRef",
            "episodeMasterRef",
            "exportArtifactRef",
        ):
            command = manifest_command()
            command[forbidden] = digest(forbidden)
            with self.subTest(field=forbidden):
                with self.assertRaises(RenderDomainContractError):
                    build_render_manifest(command)


if __name__ == "__main__":
    unittest.main()
