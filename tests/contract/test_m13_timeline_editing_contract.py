from __future__ import annotations

from copy import deepcopy
import importlib
import unittest

from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.timeline_editing import (
    TimelineEditingAuthorityError,
    TimelineEditingContractError,
    TimelineEditingConflictError,
    TimelineEditingRangeError,
    TimelineEditingStaleInputError,
    apply_timeline_edit,
    assert_timeline_edit_replay,
    build_mask_binding,
    build_output_profile_binding,
    build_speed_spec,
    build_timeline,
    build_timeline_clip,
    build_timeline_edit_command,
    build_timeline_track,
    build_timeline_version,
    build_transform_spec,
    build_transition_spec,
    read_timeline_root,
    validate_mask_binding,
    validate_output_profile_binding,
    validate_speed_spec,
    validate_timeline,
    validate_timeline_clip,
    validate_timeline_edit_chain,
    validate_timeline_edit_command,
    validate_timeline_track,
    validate_timeline_snapshot,
    validate_timeline_version,
    validate_transform_spec,
    validate_transition_spec,
)


WORKSPACE = "workspace-m13-t1"
PROJECT = "project-m13-t1"
SERIES = "series-m13-t1"
EPISODE = "episode-m13-t1"
RUN = "episode-production-run-m13-t1"
TIMELINE_REF = "timeline-m13-t1"
TIMELINE_VERSION_REF = "timeline-version-m13-t1-v1"
CREATED_AT = "2026-08-30T08:55:00Z"
DIGEST_A = "1" * 64
DIGEST_B = "2" * 64


# One auditable selector per numbered acceptance scenario.  Scenarios 34-36
# intentionally point to the accepted regression suites instead of copying
# their real ffmpeg/finalization fixtures into this contract module.
M13_T1_REQUIRED_SCENARIO_MATRIX = {
    1: "M13TimelineEditingAuthorityContractTests.test_full_timeline_version_and_whole_snapshot_are_exact",
    2: "M13TimelineEditingAuthorityContractTests.test_four_closed_track_kinds_are_supported",
    3: "M13TimelineEditingAuthorityContractTests.test_every_closed_clip_kind_has_a_valid_authority_binding",
    4: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:INSERT_CLIP",
    5: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:REMOVE_CLIP",
    6: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:MOVE_CLIP",
    7: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:TRIM_CLIP",
    8: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:SPLIT_CLIP",
    9: "M13TimelineImmutableEditContractTests.test_enable_disable_and_reorder_are_successor_only:ENABLE_DISABLE",
    10: "M13TimelineImmutableEditContractTests.test_enable_disable_and_reorder_are_successor_only:REORDER_TRACK",
    11: "M13TimelineImmutableEditContractTests.test_transition_speed_transform_and_masks_are_closed_edits:SET_TRANSITION",
    12: "M13TimelineEditingPrimitiveContractTests.test_speed_is_positive_bounded_reduced_rational_only",
    13: "M13TimelineEditingPrimitiveContractTests.test_transform_uses_fixed_finite_authority_without_expressions",
    14: "M13TimelineImmutableEditContractTests.test_transition_speed_transform_and_masks_are_closed_edits:SET_MASKS",
    15: "M13TimelineImmutableEditContractTests.test_safe_area_and_output_profiles_are_version_level_edits:SET_SAFE_AREA",
    16: "M13TimelineImmutableEditContractTests.test_safe_area_and_output_profiles_are_version_level_edits:SET_OUTPUT_PROFILES",
    17: "M13TimelineImmutableEditContractTests.test_insert_remove_move_trim_and_split_create_successors:PARENT_IMMUTABLE",
    18: "M13TimelineImmutableEditContractTests.test_exact_replay_matches_and_changed_replay_conflicts:EXACT",
    19: "M13TimelineImmutableEditContractTests.test_exact_replay_matches_and_changed_replay_conflicts:CHANGED",
    20: "M13TimelineEditingAuthorityContractTests.test_predecessor_chain_is_contiguous_and_digest_pinned",
    21: "M13TimelineEditingAuthorityContractTests.test_stale_script_and_storyboard_are_rejected",
    22: "M13TimelineEditingAuthorityContractTests.test_track_clip_kind_mismatch_and_duplicate_clip_refs_fail",
    23: "M13TimelineEditingAuthorityContractTests.test_source_trim_and_timeline_range_fail_closed:SOURCE",
    24: "M13TimelineEditingAuthorityContractTests.test_source_trim_and_timeline_range_fail_closed:TIMELINE",
    25: "M13TimelineEditingAuthorityContractTests.test_transition_cannot_exceed_clip_available_frames",
    26: "M13TimelineEditingPrimitiveContractTests.test_speed_is_positive_bounded_reduced_rational_only:INVALID",
    27: "M13TimelineEditingPrimitiveContractTests.test_transform_uses_fixed_finite_authority_without_expressions:INVALID",
    28: "M13TimelineEditingAuthorityContractTests.test_foreign_source_scope_and_source_digest_drift_fail_closed",
    29: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingSqliteTests.test_create_edit_restart_exact_replay_and_lineage_restore",
    30: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingSqliteTests.test_sqlite_tamper_is_rejected_after_restart",
    31: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingPublicHttpTests.test_browser_scope_claims_are_rejected_before_domain_write",
    32: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingPublicHttpTests.test_path_filter_raw_authority_and_publication_claims_are_rejected",
    33: "M13TimelineEditingAuthorityContractTests.test_legacy_minimal_timeline_remains_readable_without_reseal",
    34: "tests.integration.test_m12_m13_minimal_preview.M12M13MinimalPreviewIntegrationTests.test_real_ffmpeg_vertical_slice_is_deterministic_and_restart_safe",
    35: "tests.integration.test_m13_glyph_reveal_v2_composition.M13GlyphRevealV2CompositionIntegrationTests.test_nonuniform_schedule_repeat_remux_lossless_and_lossy_semantics",
    36: "tests.unit.test_episode_production_k2.EpisodeProductionG6DeliveryTests.test_composes_playable_preview_qc_and_explicitly_approved_master",
    37: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingSqliteTests.test_export_candidate_authority_surface_is_absent",
    38: "tests.integration.test_m13_timeline_editing_sqlite.M13TimelineEditingSqliteTests.test_workspace_isolation_and_no_master_or_export_creation",
}


def timeline_command() -> dict:
    return {
        "timelineRef": TIMELINE_REF,
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "createdAt": CREATED_AT,
    }


def track_command(
    kind: str,
    order: int,
    *,
    timeline_version_ref: str = TIMELINE_VERSION_REF,
) -> dict:
    lane = {
        "VIDEO": "LAYERED_Z_ORDER",
        "AUDIO": "MIX",
        "SUBTITLE": "LAYERED",
        "EFFECT": "LAYERED_Z_ORDER",
    }[kind]
    return {
        "trackRef": f"track-{kind.lower()}",
        "timelineVersionRef": timeline_version_ref,
        "trackKind": kind,
        "order": order,
        "enabled": True,
        "lanePolicy": lane,
    }


def clip_command(kind: str, *, clip_ref: str | None = None) -> dict:
    source_by_kind = {
        "VIDEO": {
            "assetVersionRef": "asset-version-video-v1",
            "assetVersionDigest": DIGEST_A,
            "sourceInFrameInclusive": 0,
            "sourceOutFrameExclusive": 24,
        },
        "AUDIO": {
            "audioAssetVersionRef": "audio-asset-version-dialogue-v1",
            "audioAssetVersionDigest": DIGEST_A,
            "sourceStartSampleInclusive": 0,
            "sourceEndSampleExclusive": 48_000,
            "sampleRate": 48_000,
            "stemMemberRef": "stem-member-dialogue-v1",
            "gainDb": 0,
            "pan": 0,
            "fadeInSamples": 0,
            "fadeOutSamples": 0,
        },
        "SUBTITLE": {
            "audioCueRef": "audio-cue-dialogue-v1",
            "audioCueDigest": DIGEST_A,
            "scriptVersionRef": "script-version-v1",
            "scriptVersionDigest": DIGEST_A,
            "textStart": 0,
            "textEndExclusive": 2,
            "textDigest": DIGEST_A,
            "language": "zh-CN",
            "wordTiming": [
                {
                    "wordRef": "subtitle-word-zhen-v1",
                    "textStart": 0,
                    "textEndExclusive": 1,
                    "timelineStartFrameInclusive": 0,
                    "timelineEndFrameExclusive": 12,
                    "textDigest": DIGEST_A,
                },
                {
                    "wordRef": "subtitle-word-tan-v1",
                    "textStart": 1,
                    "textEndExclusive": 2,
                    "timelineStartFrameInclusive": 12,
                    "timelineEndFrameExclusive": 24,
                    "textDigest": DIGEST_B,
                },
            ],
        },
        "EFFECT": {
            "effectRequirementRef": "glyph-reveal-requirement-zhen-v2",
            "effectRequirementDigest": DIGEST_A,
            "effectKind": "GLYPH_REVEAL",
            "effectResultRef": None,
            "layer": 1,
            "blendMode": "GRAZING_LIGHT_RELIEF",
        },
    }
    track_by_kind = {
        "VIDEO": "track-video",
        "AUDIO": "track-audio",
        "SUBTITLE": "track-subtitle",
        "EFFECT": "track-effect",
    }
    return {
        "clipRef": clip_ref or f"clip-{kind.lower().replace('_', '-')}",
        "timelineVersionRef": TIMELINE_VERSION_REF,
        "trackRef": track_by_kind[kind],
        "clipKind": kind,
        "timelineStartFrameInclusive": 0,
        "timelineEndFrameExclusive": 24,
        "enabled": True,
        "layer": 1 if kind == "EFFECT" else 0,
        "zOrder": 1 if kind == "EFFECT" else 0,
        "opacity": 1000,
        "blendMode": "GRAZING_LIGHT_RELIEF" if kind == "EFFECT" else "NORMAL",
        "sourceBinding": source_by_kind[kind],
        "transitionIn": None,
        "transitionOut": None,
        "speed": build_speed_spec({"numerator": 1, "denominator": 1}),
        "transform": build_transform_spec(transform_command()),
        "maskBindings": [],
    }


def source_resolver(source_type: str, source_ref: str) -> dict:
    authority = {
        "payloadDigest": DIGEST_A,
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
    }
    if source_type == "ASSET_VERSION":
        authority.update(
            {
                "assetVersionRef": source_ref,
                "frameCount": 48,
                "frameRate": {"numerator": 24, "denominator": 1},
            }
        )
    elif source_type == "AUDIO_ASSET_VERSION":
        authority.update(
            {
                "assetVersionRef": source_ref,
                "sampleCount": 96_000,
                "sampleRate": 48_000,
            }
        )
    elif source_type == "AUDIO_STEM_MEMBER":
        authority.update(
            {
                "stemMemberRef": source_ref,
                "sourceAssetVersionRef": (
                    "audio-asset-version-dialogue-v1"
                ),
                "sourceAssetVersionDigest": DIGEST_A,
                "sourceStartSample": 0,
                "sourceEndSample": 48_000,
                "sampleRate": 48_000,
            }
        )
    elif source_type == "AUDIO_CUE":
        authority.update(
            {
                "cueVersionRef": source_ref,
                "scriptVersionRef": "script-version-v1",
                "scriptVersionDigest": DIGEST_A,
                "subtitleTimingReference": {
                    "textRangeStart": 0,
                    "textRangeEndExclusive": 2,
                    "textDigest": DIGEST_A,
                    "language": "zh-CN",
                },
                "timelineStartFrameInclusive": 0,
                "timelineEndFrameExclusive": 24,
                "timelineWordTiming": [
                    {
                        "wordRef": "subtitle-word-zhen-v1",
                        "textStart": 0,
                        "textEndExclusive": 1,
                        "timelineStartFrameInclusive": 0,
                        "timelineEndFrameExclusive": 12,
                        "textDigest": DIGEST_A,
                    },
                    {
                        "wordRef": "subtitle-word-tan-v1",
                        "textStart": 1,
                        "textEndExclusive": 2,
                        "timelineStartFrameInclusive": 12,
                        "timelineEndFrameExclusive": 24,
                        "textDigest": DIGEST_B,
                    },
                ],
                "wordTimings": [
                    {
                        "wordRef": "subtitle-word-zhen-v1",
                        "textRangeStart": 0,
                        "textRangeEndExclusive": 1,
                        "textDigest": DIGEST_A,
                    },
                    {
                        "wordRef": "subtitle-word-tan-v1",
                        "textRangeStart": 1,
                        "textRangeEndExclusive": 2,
                        "textDigest": DIGEST_B,
                    },
                ],
            }
        )
    elif source_type == "MASK_ASSET_VERSION":
        authority.update(
            {
                "assetVersionRef": source_ref,
                "payloadDigest": DIGEST_B,
            }
        )
    elif source_type == "EFFECT_REQUIREMENT":
        authority.update(
            {
                "requirementRef": source_ref,
                "targetShotRef": "creative-shot-zhen-v1",
                "frameRangeStartInclusive": 0,
                "frameRangeEndExclusive": 24,
                "basePlateAssetVersionRef": "asset-version-effect-base-v1",
                "basePlateAssetVersionDigest": DIGEST_A,
                "compositeParams": {"blendMode": "GRAZING_LIGHT_RELIEF"},
            }
        )
    else:
        raise AssertionError(f"unexpected source type: {source_type}")
    return authority


def output_profile_command() -> dict:
    return {
        "outputProfileRef": "output-profile-vertical-704x1280",
        "outputProfileDigest": DIGEST_B,
        "canvasWidth": 704,
        "canvasHeight": 1280,
        "frameRate": {"numerator": 24, "denominator": 1},
        "pixelAspectRatio": {"numerator": 1, "denominator": 1},
        "displayAspectRatio": {"numerator": 11, "denominator": 20},
    }


def timeline_version_command(
    *,
    version_ref: str = TIMELINE_VERSION_REF,
    version_number: int = 1,
    parent_ref: str | None = None,
    parent_digest: str | None = None,
) -> dict:
    return {
        "timelineRef": TIMELINE_REF,
        "timelineVersionRef": version_ref,
        "versionNumber": version_number,
        "parentTimelineVersionRef": parent_ref,
        "parentTimelineVersionDigest": parent_digest,
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "scriptVersionRef": "script-version-v1",
        "scriptVersionDigest": DIGEST_A,
        "storyboardVersionRef": "storyboard-version-v1",
        "storyboardVersionDigest": DIGEST_B,
        "frameRate": {"numerator": 24, "denominator": 1},
        "canvasWidth": 704,
        "canvasHeight": 1280,
        "pixelAspectRatio": {"numerator": 1, "denominator": 1},
        "displayAspectRatio": {"numerator": 11, "denominator": 20},
        "durationFrames": 48,
        "safeArea": {
            "leftPixels": 24,
            "topPixels": 24,
            "rightPixels": 24,
            "bottomPixels": 24,
        },
        "trackRefs": [
            "track-video",
            "track-audio",
            "track-subtitle",
            "track-effect",
        ],
        "createdAt": CREATED_AT,
    }


def valid_snapshot() -> dict:
    timeline = build_timeline(timeline_command())
    profile = build_output_profile_binding(output_profile_command())
    tracks = [
        build_timeline_track(track_command(kind, order))
        for order, kind in enumerate(
            ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
        )
    ]
    clips = [
        build_timeline_clip(clip_command(kind))
        for kind in (
            "VIDEO",
            "AUDIO",
            "SUBTITLE",
            "EFFECT",
        )
    ]
    effect_base = clip_command("VIDEO", clip_ref="clip-effect-base-video")
    effect_base["zOrder"] = 1
    effect_base["sourceBinding"][
        "assetVersionRef"
    ] = "asset-version-effect-base-v1"
    clips.append(build_timeline_clip(effect_base))
    version = build_timeline_version(
        timeline_version_command(),
        output_profile_bindings=[profile],
        tracks=tracks,
        clips=clips,
    )
    snapshot = validate_timeline_snapshot(
        version,
        tracks,
        clips,
        timeline=timeline,
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
    return {
        "timeline": timeline,
        "profile": profile,
        **snapshot.as_dict(),
    }


def edit_arguments(operation: str) -> dict:
    if operation == "INSERT_CLIP":
        inserted = clip_command("VIDEO", clip_ref="clip-video-inserted")
        inserted.pop("timelineVersionRef")
        inserted.update(
            {
                "timelineStartFrameInclusive": 24,
                "timelineEndFrameExclusive": 48,
            }
        )
        inserted["sourceBinding"].update(
            {
                "sourceInFrameInclusive": 24,
                "sourceOutFrameExclusive": 48,
            }
        )
        return {"clip": inserted}
    if operation == "REMOVE_CLIP":
        return {"clipRef": "clip-effect"}
    if operation == "MOVE_CLIP":
        return {
            "clipRef": "clip-video",
            "trackRef": "track-video",
            "timelineStartFrameInclusive": 24,
            "timelineEndFrameExclusive": 48,
        }
    if operation == "TRIM_CLIP":
        source = deepcopy(clip_command("VIDEO")["sourceBinding"])
        source["sourceOutFrameExclusive"] = 12
        return {
            "clipRef": "clip-video",
            "timelineStartFrameInclusive": 0,
            "timelineEndFrameExclusive": 12,
            "sourceBinding": source,
        }
    if operation == "SPLIT_CLIP":
        return {
            "clipRef": "clip-video",
            "splitTimelineFrame": 12,
            "rightClipRef": "clip-video-right",
        }
    if operation in {"ENABLE_CLIP", "DISABLE_CLIP"}:
        return {"clipRef": "clip-video"}
    if operation == "REORDER_TRACK":
        return {"trackRef": "track-video", "order": 1}
    if operation == "SET_TRANSITION":
        return {
            "clipRef": "clip-video",
            "edge": "IN",
            "transition": build_transition_spec(
                {
                    "transitionKind": "FADE_IN",
                    "durationFrames": 4,
                    "curve": "LINEAR",
                    "alignment": "START",
                }
            ),
        }
    if operation == "SET_SPEED":
        return {
            "clipRef": "clip-video",
            "speed": build_speed_spec({"numerator": 1, "denominator": 1}),
        }
    if operation == "SET_TRANSFORM":
        transformed = transform_command()
        transformed["positionXPixels"] = 32
        return {
            "clipRef": "clip-video",
            "transform": build_transform_spec(transformed),
        }
    if operation == "SET_MASKS":
        return {
            "clipRef": "clip-video",
            "maskBindings": [
                build_mask_binding(
                    {
                        "maskAssetVersionRef": "asset-version-mask-edit-v1",
                        "maskAssetVersionDigest": DIGEST_B,
                        "mode": "ALPHA",
                        "frameRangeStartInclusive": 0,
                        "frameRangeEndExclusive": 24,
                        "transform": build_transform_spec(transform_command()),
                    }
                )
            ],
        }
    if operation == "SET_SAFE_AREA":
        return {
            "safeArea": {
                "leftPixels": 32,
                "topPixels": 32,
                "rightPixels": 32,
                "bottomPixels": 32,
            }
        }
    if operation == "SET_OUTPUT_PROFILES":
        return {
            "outputProfileBindings": [
                build_output_profile_binding(output_profile_command())
            ]
        }
    raise AssertionError(f"unhandled operation: {operation}")


def timeline_edit_command(
    fixture: dict,
    operation: str,
    *,
    operation_ref: str | None = None,
    idempotency_key: str | None = None,
    arguments: dict | None = None,
) -> dict:
    parent = fixture["timelineVersion"]
    return build_timeline_edit_command(
        {
            "operationRef": operation_ref or f"timeline-edit-{operation.lower()}",
            "idempotencyKey": idempotency_key or f"timeline-edit-key-{operation.lower()}",
            "parentTimelineVersionRef": parent["timelineVersionRef"],
            "parentTimelineVersionDigest": parent["payloadDigest"],
            "newTimelineVersionRef": f"timeline-version-{operation.lower()}-v2",
            "operation": operation,
            "arguments": arguments if arguments is not None else edit_arguments(operation),
            "createdAt": "2026-08-30T08:56:00Z",
        }
    )


def apply_edit(fixture: dict, operation: str):
    parent_version = validate_timeline_version(fixture["timelineVersion"])
    return apply_timeline_edit(
        parent_version,
        [validate_timeline_track(item) for item in fixture["tracks"]],
        [validate_timeline_clip(item) for item in fixture["clips"]],
        validate_timeline_edit_command(timeline_edit_command(fixture, operation)),
        existing_timeline_versions=[parent_version],
        timeline=validate_timeline(fixture["timeline"]),
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


def transform_command() -> dict:
    return {
        "positionXPixels": 0,
        "positionYPixels": 0,
        "scaleX": {"numerator": 1, "denominator": 1},
        "scaleY": {"numerator": 1, "denominator": 1},
        "rotationMilliDegrees": 0,
        "anchorXPixels": 0,
        "anchorYPixels": 0,
        "opacity": 1000,
        "perspectiveMode": "NONE",
        "perspectiveMatrix": None,
        "perspectiveCorners": None,
    }


class M13TimelineEditingPrimitiveContractTests(unittest.TestCase):
    def test_required_38_scenario_matrix_is_complete(self) -> None:
        self.assertEqual(
            set(M13_T1_REQUIRED_SCENARIO_MATRIX), set(range(1, 39))
        )
        self.assertEqual(
            len(set(M13_T1_REQUIRED_SCENARIO_MATRIX.values())), 38
        )
        for scenario in (34, 35, 36):
            selector = M13_T1_REQUIRED_SCENARIO_MATRIX[scenario]
            module_name, class_name, method_name = selector.rsplit(".", 2)
            module = importlib.import_module(module_name)
            case = getattr(module, class_name)
            self.assertTrue(callable(getattr(case, method_name)))

    def test_transition_is_closed_and_duration_is_frame_bounded(self) -> None:
        transition = build_transition_spec(
            {
                "transitionKind": "CROSSFADE",
                "durationFrames": 12,
                "curve": "EASE_IN_OUT",
                "alignment": "CENTER",
            }
        )
        self.assertEqual(
            validate_transition_spec(transition).as_dict(), transition
        )
        for field, value in (
            ("transitionKind", "CLIENT_FILTER"),
            ("durationFrames", -1),
            ("curve", "python-expression"),
            ("alignment", "ARBITRARY"),
        ):
            with self.subTest(field=field):
                invalid = {
                    "transitionKind": "CROSSFADE",
                    "durationFrames": 12,
                    "curve": "LINEAR",
                    "alignment": "CENTER",
                    field: value,
                }
                with self.assertRaises(
                    (
                        TimelineEditingContractError,
                        TimelineEditingRangeError,
                        TimelineEditingStaleInputError,
                    )
                ):
                    build_transition_spec(invalid)

    def test_speed_is_positive_bounded_reduced_rational_only(self) -> None:
        speed = build_speed_spec({"numerator": 3, "denominator": 2})
        self.assertEqual(validate_speed_spec(speed).as_dict(), speed)
        for command in (
            {"numerator": 0, "denominator": 1},
            {"numerator": -1, "denominator": 1},
            {"numerator": 4, "denominator": 2},
            {"numerator": 65, "denominator": 1},
            {"numerator": 1.5, "denominator": 1},
        ):
            with self.subTest(command=command):
                with self.assertRaises(
                    (TimelineEditingContractError, TimelineEditingRangeError)
                ):
                    build_speed_spec(command)

    def test_transform_uses_fixed_finite_authority_without_expressions(self) -> None:
        transform = build_transform_spec(transform_command())
        self.assertEqual(validate_transform_spec(transform).as_dict(), transform)
        invalid_commands = []
        invalid = transform_command()
        invalid["positionXPixels"] = 1.25
        invalid_commands.append(invalid)
        invalid = transform_command()
        invalid["opacity"] = 1001
        invalid_commands.append(invalid)
        invalid = transform_command()
        invalid["scaleX"] = {"numerator": 2, "denominator": 2}
        invalid_commands.append(invalid)
        invalid = transform_command()
        invalid["perspectiveMode"] = "EXPRESSION"
        invalid_commands.append(invalid)
        invalid = transform_command()
        invalid["perspectiveMatrix"] = ["x"] * 9
        invalid_commands.append(invalid)
        for command in invalid_commands:
            with self.subTest(command=command):
                with self.assertRaises(
                    (TimelineEditingContractError, TimelineEditingRangeError)
                ):
                    build_transform_spec(command)

    def test_validated_primitives_are_immutable_detached_values(self) -> None:
        mapping = build_transform_spec(transform_command())
        contract = validate_transform_spec(mapping)
        changed = deepcopy(mapping)
        changed["positionXPixels"] = 50
        self.assertEqual(contract.as_dict()["positionXPixels"], 0)


class M13TimelineEditingAuthorityContractTests(unittest.TestCase):
    def test_new_timeline_root_is_exact_scoped_and_digest_sealed(self) -> None:
        timeline = build_timeline(timeline_command())
        self.assertEqual(validate_timeline(timeline).as_dict(), timeline)
        self.assertEqual(timeline["workspaceRef"], WORKSPACE)
        self.assertEqual(timeline["productionRunRef"], RUN)
        for forbidden in ("storageKey", "absolutePath", "publicationAllowed"):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(TimelineEditingContractError):
                    build_timeline({**timeline_command(), forbidden: "forged"})

    def test_four_closed_track_kinds_are_supported(self) -> None:
        tracks = [
            build_timeline_track(track_command(kind, order))
            for order, kind in enumerate(
                ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
            )
        ]
        self.assertEqual(
            [validate_timeline_track(item).as_dict()["trackKind"] for item in tracks],
            ["VIDEO", "AUDIO", "SUBTITLE", "EFFECT"],
        )
        for invalid_kind in ("MUSIC", "FREEFORM", "video"):
            with self.subTest(invalid_kind=invalid_kind):
                with self.assertRaises(TimelineEditingContractError):
                    build_timeline_track(
                        {
                            **track_command("VIDEO", 0),
                            "trackKind": invalid_kind,
                        }
                    )

    def test_mask_binding_pins_asset_digest_range_mode_and_transform(self) -> None:
        mask = build_mask_binding(
            {
                "maskAssetVersionRef": "asset-version-mask-v1",
                "maskAssetVersionDigest": DIGEST_A,
                "mode": "ALPHA",
                "frameRangeStartInclusive": 10,
                "frameRangeEndExclusive": 20,
                "transform": build_transform_spec(transform_command()),
            }
        )
        self.assertEqual(validate_mask_binding(mask).as_dict(), mask)
        for changed in (
            {"mode": "CLIENT_MASK"},
            {"frameRangeStartInclusive": 20},
            {"maskAssetVersionDigest": "not-a-digest"},
        ):
            command = {
                "maskAssetVersionRef": "asset-version-mask-v1",
                "maskAssetVersionDigest": DIGEST_A,
                "mode": "ALPHA",
                "frameRangeStartInclusive": 10,
                "frameRangeEndExclusive": 20,
                "transform": build_transform_spec(transform_command()),
                **changed,
            }
            with self.subTest(changed=changed):
                with self.assertRaises(
                    (TimelineEditingContractError, TimelineEditingRangeError)
                ):
                    build_mask_binding(command)

    def test_output_profile_is_exact_digest_pinned_rational_geometry(self) -> None:
        profile = build_output_profile_binding(
            {
                "outputProfileRef": "output-profile-vertical-704x1280",
                "outputProfileDigest": DIGEST_B,
                "canvasWidth": 704,
                "canvasHeight": 1280,
                "frameRate": {"numerator": 24, "denominator": 1},
                "pixelAspectRatio": {"numerator": 1, "denominator": 1},
                "displayAspectRatio": {"numerator": 11, "denominator": 20},
            }
        )
        self.assertEqual(validate_output_profile_binding(profile).as_dict(), profile)
        with self.assertRaises(TimelineEditingRangeError):
            build_output_profile_binding(
                {
                    "outputProfileRef": "output-profile-vertical-704x1280",
                    "outputProfileDigest": DIGEST_B,
                    "canvasWidth": 704,
                    "canvasHeight": 1280,
                    "frameRate": {"numerator": 24, "denominator": 1},
                    "pixelAspectRatio": {"numerator": 1, "denominator": 1},
                    "displayAspectRatio": {"numerator": 9, "denominator": 16},
                }
            )

    def test_every_closed_clip_kind_has_a_valid_authority_binding(self) -> None:
        for kind in (
            "VIDEO",
            "AUDIO",
            "SUBTITLE",
            "EFFECT",
        ):
            with self.subTest(kind=kind):
                clip = build_timeline_clip(clip_command(kind))
                validated = validate_timeline_clip(
                    clip,
                    duration_frames=48,
                    frame_rate={"numerator": 24, "denominator": 1},
                    source_resolver=source_resolver,
                    scope={
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": RUN,
                    },
                ).as_dict()
                self.assertEqual(validated, clip)

    def test_effect_result_stem_and_full_audio_cue_fail_closed(self) -> None:
        effect = clip_command("EFFECT")
        effect["sourceBinding"]["effectResultRef"] = "effect-result-forbidden"
        with self.assertRaises(TimelineEditingAuthorityError):
            build_timeline_clip(effect)

        audio = build_timeline_clip(clip_command("AUDIO"))

        def missing_stem(source_type: str, source_ref: str):
            if source_type == "AUDIO_STEM_MEMBER":
                return None
            return source_resolver(source_type, source_ref)

        with self.assertRaises(TimelineEditingAuthorityError):
            validate_timeline_clip(
                audio,
                source_resolver=missing_stem,
                scope={
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                },
            )

        def stale_stem(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "AUDIO_STEM_MEMBER":
                authority["sourceEndSample"] = 47_999
            return authority

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_clip(
                audio,
                source_resolver=stale_stem,
                scope={
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                },
            )

        subtitle = build_timeline_clip(clip_command("SUBTITLE"))
        for mutation in ("language", "word"):
            def stale_cue(
                source_type: str,
                source_ref: str,
                *,
                mutation: str = mutation,
            ) -> dict:
                authority = source_resolver(source_type, source_ref)
                if source_type == "AUDIO_CUE" and mutation == "language":
                    authority["subtitleTimingReference"]["language"] = "en-US"
                elif source_type == "AUDIO_CUE":
                    authority["wordTimings"][0]["textDigest"] = DIGEST_B
                return authority

            with self.subTest(mutation=mutation):
                with self.assertRaises(TimelineEditingStaleInputError):
                    validate_timeline_clip(
                        subtitle,
                        source_resolver=stale_cue,
                        scope={
                            "workspaceRef": WORKSPACE,
                            "productionRunRef": RUN,
                        },
                    )

    def test_source_trim_and_timeline_range_fail_closed(self) -> None:
        invalid_source = clip_command("VIDEO")
        invalid_source["sourceBinding"]["sourceOutFrameExclusive"] = 49
        invalid_source["timelineEndFrameExclusive"] = 49
        clip = build_timeline_clip(invalid_source)
        with self.assertRaises(TimelineEditingRangeError):
            validate_timeline_clip(
                clip,
                duration_frames=60,
                source_resolver=source_resolver,
                scope={
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                },
            )

        out_of_timeline = build_timeline_clip(clip_command("VIDEO"))
        with self.assertRaises(TimelineEditingRangeError):
            validate_timeline_clip(out_of_timeline, duration_frames=23)

    def test_transition_cannot_exceed_clip_available_frames(self) -> None:
        command = clip_command("VIDEO")
        command["transitionIn"] = build_transition_spec(
            {
                "transitionKind": "FADE_IN",
                "durationFrames": 25,
                "curve": "LINEAR",
                "alignment": "START",
            }
        )
        with self.assertRaises(TimelineEditingRangeError):
            build_timeline_clip(command)

    def test_mask_layer_and_effect_binding_are_exact(self) -> None:
        command = clip_command("VIDEO")
        command["maskBindings"] = [
            build_mask_binding(
                {
                    "maskAssetVersionRef": "asset-version-mask-v1",
                    "maskAssetVersionDigest": DIGEST_B,
                    "mode": "LUMA",
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "transform": build_transform_spec(transform_command()),
                }
            )
        ]
        video = validate_timeline_clip(build_timeline_clip(command)).as_dict()
        self.assertEqual(video["maskBindings"][0]["mode"], "LUMA")

        effect = clip_command("EFFECT")
        effect["layer"] = 2
        with self.assertRaises(TimelineEditingStaleInputError):
            build_timeline_clip(effect)
        transformed_effect = clip_command("EFFECT")
        transform = transform_command()
        transform["positionXPixels"] = 1
        transformed_effect["transform"] = build_transform_spec(transform)
        with self.assertRaises(TimelineEditingStaleInputError):
            build_timeline_clip(transformed_effect)

    def test_mask_authority_ref_and_digest_must_join_exactly(self) -> None:
        command = clip_command("VIDEO")
        command["maskBindings"] = [
            build_mask_binding(
                {
                    "maskAssetVersionRef": "asset-version-mask-v1",
                    "maskAssetVersionDigest": DIGEST_B,
                    "mode": "ALPHA",
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "transform": build_transform_spec(transform_command()),
                }
            )
        ]
        clip = build_timeline_clip(command)

        def wrong_ref_resolver(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "MASK_ASSET_VERSION":
                authority["assetVersionRef"] = "asset-version-mask-foreign"
            return authority

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_clip(
                clip,
                duration_frames=48,
                frame_rate={"numerator": 24, "denominator": 1},
                source_resolver=wrong_ref_resolver,
                scope={
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                },
            )

    def test_foreign_source_scope_and_source_digest_drift_fail_closed(self) -> None:
        video = build_timeline_clip(clip_command("VIDEO"))

        def foreign_resolver(source_type: str, source_ref: str) -> dict:
            return {**source_resolver(source_type, source_ref), "workspaceRef": "foreign"}

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_clip(
                video,
                source_resolver=foreign_resolver,
                scope={
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                },
            )

        effect = build_timeline_clip(clip_command("EFFECT"))

        def drifted_resolver(source_type: str, source_ref: str) -> dict:
            return {**source_resolver(source_type, source_ref), "payloadDigest": DIGEST_B}

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_clip(effect, source_resolver=drifted_resolver)

    def test_video_frame_rate_and_effect_base_plate_closure_fail_closed(self) -> None:
        fixture = valid_snapshot()

        def thirty_fps(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "ASSET_VERSION":
                authority["frameRate"] = {"numerator": 30, "denominator": 1}
            return authority

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_snapshot(
                fixture["timelineVersion"],
                fixture["tracks"],
                fixture["clips"],
                timeline=fixture["timeline"],
                source_resolver=thirty_fps,
            )

        def drifted_base(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "EFFECT_REQUIREMENT":
                authority["basePlateAssetVersionRef"] = "other-base-plate"
            return authority

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_snapshot(
                fixture["timelineVersion"],
                fixture["tracks"],
                fixture["clips"],
                timeline=fixture["timeline"],
                source_resolver=drifted_base,
            )

    def test_full_timeline_version_and_whole_snapshot_are_exact(self) -> None:
        fixture = valid_snapshot()
        version = fixture["timelineVersion"]
        validated = validate_timeline_version(version).as_dict()
        self.assertEqual(validated, version)
        self.assertEqual(version["versionNumber"], 1)
        self.assertIsNone(version["parentTimelineVersionRef"])
        self.assertIsNone(version["parentTimelineVersionDigest"])
        self.assertEqual(version["durationFrames"], 48)
        self.assertFalse(version["publicationAllowed"])
        self.assertEqual(
            [track["trackKind"] for track in fixture["tracks"]],
            ["VIDEO", "AUDIO", "SUBTITLE", "EFFECT"],
        )

    def test_invalid_duration_frame_rate_and_duplicate_track_refs_fail(self) -> None:
        profile = build_output_profile_binding(output_profile_command())
        tracks = [
            build_timeline_track(track_command(kind, order))
            for order, kind in enumerate(
                ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
            )
        ]
        for changed in (
            {"durationFrames": 0},
            {"durationFrames": -1},
            {"frameRate": {"numerator": 0, "denominator": 1}},
            {"frameRate": {"numerator": 23.976, "denominator": 1}},
            {
                "trackRefs": [
                    "track-video",
                    "track-video",
                    "track-subtitle",
                    "track-effect",
                ]
            },
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(
                    (
                        TimelineEditingContractError,
                        TimelineEditingRangeError,
                        TimelineEditingStaleInputError,
                    )
                ):
                    build_timeline_version(
                        {**timeline_version_command(), **changed},
                        output_profile_bindings=[profile],
                        tracks=tracks,
                        clips=(),
                    )

    def test_predecessor_chain_is_contiguous_and_digest_pinned(self) -> None:
        fixture = valid_snapshot()
        parent = validate_timeline_version(fixture["timelineVersion"])
        successor_command = timeline_version_command(
            version_ref="timeline-version-m13-t1-v2",
            version_number=2,
            parent_ref=parent.as_dict()["timelineVersionRef"],
            parent_digest=parent.as_dict()["payloadDigest"],
        )
        successor_tracks = [
            build_timeline_track(
                track_command(
                    kind,
                    order,
                    timeline_version_ref="timeline-version-m13-t1-v2",
                )
            )
            for order, kind in enumerate(
                ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
            )
        ]
        successor = build_timeline_version(
            successor_command,
            output_profile_bindings=[fixture["profile"]],
            tracks=successor_tracks,
            clips=(),
            predecessor=parent,
        )
        self.assertEqual(
            validate_timeline_version(
                successor, predecessor=parent
            ).as_dict(),
            successor,
        )
        for changed in (
            {"parentTimelineVersionDigest": DIGEST_B},
            {"versionNumber": 3},
            {"parentTimelineVersionRef": "timeline-version-wrong"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(TimelineEditingStaleInputError):
                    build_timeline_version(
                        {**successor_command, **changed},
                        output_profile_bindings=[fixture["profile"]],
                        tracks=successor_tracks,
                        clips=(),
                        predecessor=parent,
                    )

    def test_stale_script_and_storyboard_are_rejected(self) -> None:
        fixture = valid_snapshot()
        for expected_script, expected_storyboard in (
            (
                {
                    "scriptVersionRef": "script-version-v1",
                    "scriptVersionDigest": DIGEST_B,
                },
                None,
            ),
            (
                None,
                {
                    "storyboardVersionRef": "storyboard-version-v1",
                    "storyboardVersionDigest": DIGEST_A,
                },
            ),
        ):
            with self.subTest(
                expected_script=expected_script,
                expected_storyboard=expected_storyboard,
            ):
                with self.assertRaises(TimelineEditingStaleInputError):
                    validate_timeline_snapshot(
                        fixture["timelineVersion"],
                        fixture["tracks"],
                        fixture["clips"],
                        timeline=fixture["timeline"],
                        source_resolver=source_resolver,
                        expected_script=expected_script,
                        expected_storyboard=expected_storyboard,
                    )

    def test_track_clip_kind_mismatch_and_duplicate_clip_refs_fail(self) -> None:
        fixture = valid_snapshot()
        mismatched = deepcopy(fixture["clips"])
        mismatched[0] = build_timeline_clip(
            {
                **clip_command("VIDEO"),
                "trackRef": "track-audio",
            }
        )
        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_snapshot(
                fixture["timelineVersion"],
                fixture["tracks"],
                mismatched,
            )
        with self.assertRaises(TimelineEditingContractError):
            validate_timeline_snapshot(
                fixture["timelineVersion"],
                fixture["tracks"],
                [*fixture["clips"], fixture["clips"][0]],
            )

    def test_layered_z_order_conflict_is_rejected(self) -> None:
        fixture = valid_snapshot()
        duplicate_lane = clip_command(
            "VIDEO", clip_ref="clip-video-second"
        )
        second = build_timeline_clip(duplicate_lane)
        conflict_clips = [*fixture["clips"], second]
        conflict_version = build_timeline_version(
            timeline_version_command(),
            output_profile_bindings=[fixture["profile"]],
            tracks=fixture["tracks"],
            clips=conflict_clips,
        )
        with self.assertRaises(Exception) as caught:
            validate_timeline_snapshot(
                conflict_version,
                fixture["tracks"],
                conflict_clips,
            )
        self.assertEqual(
            getattr(caught.exception, "code", None),
            "timeline_editing_idempotency_conflict",
        )

    def test_legacy_minimal_timeline_remains_readable_without_reseal(self) -> None:
        from services.v5_core_os.episode_production.timeline_preview import (
            build_timeline as build_legacy_timeline,
        )

        legacy = build_legacy_timeline(
            {
                "workspaceRef": WORKSPACE,
                "projectRef": PROJECT,
                "seriesRef": SERIES,
                "episodeRef": EPISODE,
                "productionRunRef": RUN,
                "timelineRef": "timeline-minimal-history",
                "createdBy": "v5.m12-m13.timeline-preview.v1",
                "createdAt": CREATED_AT,
            }
        )
        projection = read_timeline_root(legacy)
        self.assertIsInstance(projection, dict)
        self.assertEqual(projection, legacy)
        with self.assertRaises(TimelineEditingContractError):
            validate_timeline(legacy)


class M13TimelineImmutableEditContractTests(unittest.TestCase):
    def test_ancestor_timeline_version_ref_reuse_and_incomplete_history_fail_closed(
        self,
    ) -> None:
        fixture = valid_snapshot()
        first = apply_edit(fixture, "REMOVE_CLIP")
        first_mapping = first.as_dict()
        parent = first_mapping["timelineVersion"]
        reuse_command = build_timeline_edit_command(
            {
                "operationRef": "timeline-edit-reuse-root-version-ref",
                "idempotencyKey": "timeline-edit-key-reuse-root-version-ref",
                "parentTimelineVersionRef": parent["timelineVersionRef"],
                "parentTimelineVersionDigest": parent["payloadDigest"],
                "newTimelineVersionRef": TIMELINE_VERSION_REF,
                "operation": "SET_SAFE_AREA",
                "arguments": edit_arguments("SET_SAFE_AREA"),
                "createdAt": "2026-08-30T08:57:00Z",
            }
        )
        with self.assertRaises(TimelineEditingStaleInputError):
            apply_timeline_edit(
                first.timeline_version,
                first.tracks,
                first.clips,
                validate_timeline_edit_command(reuse_command),
                existing_timeline_versions=[
                    validate_timeline_version(fixture["timelineVersion"]),
                    first.timeline_version,
                ],
                timeline=validate_timeline(fixture["timeline"]),
                source_resolver=source_resolver,
            )
        with self.assertRaises(TimelineEditingAuthorityError):
            apply_timeline_edit(
                first.timeline_version,
                first.tracks,
                first.clips,
                validate_timeline_edit_command(reuse_command),
                existing_timeline_versions=[first.timeline_version],
                timeline=validate_timeline(fixture["timeline"]),
                source_resolver=source_resolver,
            )
        with self.assertRaises(TimelineEditingConflictError):
            validate_timeline_edit_chain(
                [
                    fixture["timelineVersion"],
                    first.timeline_version,
                    fixture["timelineVersion"],
                ],
                [first.edit_command, reuse_command],
            )

    def test_insert_and_trim_nested_payloads_are_closed_before_apply(self) -> None:
        fixture = valid_snapshot()
        invalid_commands: list[dict] = []

        insert = timeline_edit_command(fixture, "INSERT_CLIP")
        insert.pop("schemaVersion")
        insert.pop("payloadDigest")
        insert["arguments"]["clip"]["sourceBinding"]["codecHint"] = "h264"
        invalid_commands.append(insert)

        trim = timeline_edit_command(fixture, "TRIM_CLIP")
        trim.pop("schemaVersion")
        trim.pop("payloadDigest")
        trim["arguments"]["sourceBinding"]["codecHint"] = "h264"
        invalid_commands.append(trim)

        path_ref = timeline_edit_command(fixture, "TRIM_CLIP")
        path_ref.pop("schemaVersion")
        path_ref.pop("payloadDigest")
        path_ref["arguments"]["sourceBinding"][
            "assetVersionRef"
        ] = "/tmp/source.wav"
        invalid_commands.append(path_ref)

        for command in invalid_commands:
            with self.subTest(operation=command["operation"]):
                with self.assertRaises(TimelineEditingContractError):
                    build_timeline_edit_command(command)

        sealed_trim = timeline_edit_command(fixture, "TRIM_CLIP")
        sealed_trim["arguments"]["sourceBinding"]["codecHint"] = "h264"
        sealed_trim["payloadDigest"] = _digest(
            {
                key: value
                for key, value in sealed_trim.items()
                if key != "payloadDigest"
            }
        )
        with self.assertRaises(TimelineEditingContractError):
            validate_timeline_edit_command(sealed_trim)

    def test_audio_trim_and_split_remain_within_exact_stem_member(self) -> None:
        fixture = valid_snapshot()
        parent_version = validate_timeline_version(fixture["timelineVersion"])
        parent_tracks = [
            validate_timeline_track(item) for item in fixture["tracks"]
        ]
        parent_clips = [
            validate_timeline_clip(item) for item in fixture["clips"]
        ]
        split_command = timeline_edit_command(
            fixture,
            "SPLIT_CLIP",
            operation_ref="timeline-edit-split-audio",
            idempotency_key="timeline-edit-key-split-audio",
            arguments={
                "clipRef": "clip-audio",
                "splitTimelineFrame": 12,
                "rightClipRef": "clip-audio-right",
            },
        )
        split = apply_timeline_edit(
            parent_version,
            parent_tracks,
            parent_clips,
            validate_timeline_edit_command(split_command),
            existing_timeline_versions=[parent_version],
            timeline=validate_timeline(fixture["timeline"]),
            source_resolver=source_resolver,
        ).as_dict()
        split_clips = {item["clipRef"]: item for item in split["clips"]}
        self.assertEqual(
            split_clips["clip-audio"]["sourceBinding"][
                "sourceEndSampleExclusive"
            ],
            24_000,
        )
        self.assertEqual(
            split_clips["clip-audio-right"]["sourceBinding"][
                "sourceStartSampleInclusive"
            ],
            24_000,
        )

        trimmed_source = deepcopy(clip_command("AUDIO")["sourceBinding"])
        trimmed_source["sourceEndSampleExclusive"] = 24_000
        trim_command = timeline_edit_command(
            fixture,
            "TRIM_CLIP",
            operation_ref="timeline-edit-trim-audio",
            idempotency_key="timeline-edit-key-trim-audio",
            arguments={
                "clipRef": "clip-audio",
                "timelineStartFrameInclusive": 0,
                "timelineEndFrameExclusive": 12,
                "sourceBinding": trimmed_source,
            },
        )
        trimmed = apply_timeline_edit(
            parent_version,
            parent_tracks,
            parent_clips,
            validate_timeline_edit_command(trim_command),
            existing_timeline_versions=[parent_version],
            timeline=validate_timeline(fixture["timeline"]),
            source_resolver=source_resolver,
        ).as_dict()
        trimmed_audio = next(
            item for item in trimmed["clips"] if item["clipRef"] == "clip-audio"
        )
        self.assertEqual(
            trimmed_audio["sourceBinding"]["sourceEndSampleExclusive"],
            24_000,
        )

        def narrowed_stem(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "AUDIO_STEM_MEMBER":
                authority["sourceStartSample"] = 1
            return authority

        with self.assertRaises(TimelineEditingStaleInputError):
            validate_timeline_snapshot(
                fixture["timelineVersion"],
                fixture["tracks"],
                fixture["clips"],
                timeline=fixture["timeline"],
                source_resolver=narrowed_stem,
            )

    def test_audio_split_rejects_fractional_sample_boundary(self) -> None:
        fixture = valid_snapshot()
        audio_44k = clip_command("AUDIO")
        audio_44k["sourceBinding"].update(
            {
                "sourceEndSampleExclusive": 44_100,
                "sampleRate": 44_100,
            }
        )
        clips_44k = [
            build_timeline_clip(audio_44k)
            if item["clipRef"] == "clip-audio"
            else item
            for item in fixture["clips"]
        ]
        tracks_44k = [
            validate_timeline_track(item) for item in fixture["tracks"]
        ]

        def resolver_44k(source_type: str, source_ref: str) -> dict:
            authority = source_resolver(source_type, source_ref)
            if source_type == "AUDIO_ASSET_VERSION":
                authority.update({"sampleRate": 44_100, "sampleCount": 88_200})
            elif source_type == "AUDIO_STEM_MEMBER":
                authority.update(
                    {
                        "sampleRate": 44_100,
                        "sourceStartSample": 0,
                        "sourceEndSample": 44_100,
                    }
                )
            return authority

        version_44k = build_timeline_version(
            timeline_version_command(),
            output_profile_bindings=[fixture["profile"]],
            tracks=tracks_44k,
            clips=clips_44k,
        )
        snapshot_44k = validate_timeline_snapshot(
            version_44k,
            tracks_44k,
            clips_44k,
            timeline=fixture["timeline"],
            source_resolver=resolver_44k,
        )
        parent = snapshot_44k.timeline_version.as_dict()
        command = build_timeline_edit_command(
            {
                "operationRef": "timeline-edit-split-audio-inexact",
                "idempotencyKey": "timeline-edit-key-split-audio-inexact",
                "parentTimelineVersionRef": parent["timelineVersionRef"],
                "parentTimelineVersionDigest": parent["payloadDigest"],
                "newTimelineVersionRef": "timeline-version-split-audio-inexact-v2",
                "operation": "SPLIT_CLIP",
                "arguments": {
                    "clipRef": "clip-audio",
                    "splitTimelineFrame": 1,
                    "rightClipRef": "clip-audio-inexact-right",
                },
                "createdAt": "2026-08-30T08:57:00Z",
            }
        )
        with self.assertRaises(TimelineEditingRangeError):
            apply_timeline_edit(
                snapshot_44k.timeline_version,
                snapshot_44k.tracks,
                snapshot_44k.clips,
                validate_timeline_edit_command(command),
                existing_timeline_versions=[snapshot_44k.timeline_version],
                timeline=validate_timeline(fixture["timeline"]),
                source_resolver=resolver_44k,
            )

    def test_trim_cannot_rebind_source_authority(self) -> None:
        fixture = valid_snapshot()
        parent_version = validate_timeline_version(fixture["timelineVersion"])
        replacement = deepcopy(clip_command("VIDEO")["sourceBinding"])
        replacement.update(
            {
                "assetVersionRef": "different-video-asset-version",
                "sourceOutFrameExclusive": 12,
            }
        )
        command = timeline_edit_command(
            fixture,
            "TRIM_CLIP",
            arguments={
                "clipRef": "clip-video",
                "timelineStartFrameInclusive": 0,
                "timelineEndFrameExclusive": 12,
                "sourceBinding": replacement,
            },
        )
        with self.assertRaises(TimelineEditingAuthorityError):
            apply_timeline_edit(
                parent_version,
                [validate_timeline_track(item) for item in fixture["tracks"]],
                [validate_timeline_clip(item) for item in fixture["clips"]],
                validate_timeline_edit_command(command),
                existing_timeline_versions=[parent_version],
                timeline=validate_timeline(fixture["timeline"]),
                source_resolver=source_resolver,
            )

    def test_move_translates_absolute_mask_ranges(self) -> None:
        fixture = valid_snapshot()
        masked_video_command = clip_command("VIDEO")
        masked_video_command["maskBindings"] = [
            build_mask_binding(
                {
                    "maskAssetVersionRef": "asset-version-mask-move-v1",
                    "maskAssetVersionDigest": DIGEST_B,
                    "mode": "ALPHA",
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "transform": build_transform_spec(transform_command()),
                }
            )
        ]
        masked_video = build_timeline_clip(masked_video_command)
        clips = [
            masked_video if item["clipRef"] == "clip-video" else item
            for item in fixture["clips"]
        ]
        version = build_timeline_version(
            timeline_version_command(),
            output_profile_bindings=[fixture["profile"]],
            tracks=fixture["tracks"],
            clips=clips,
        )
        masked_fixture = {
            **fixture,
            "timelineVersion": version,
            "clips": clips,
        }
        moved = apply_edit(masked_fixture, "MOVE_CLIP").as_dict()
        moved_video = next(
            item for item in moved["clips"] if item["clipRef"] == "clip-video"
        )
        self.assertEqual(
            (
                moved_video["maskBindings"][0]["frameRangeStartInclusive"],
                moved_video["maskBindings"][0]["frameRangeEndExclusive"],
            ),
            (24, 48),
        )

    def test_insert_remove_move_trim_and_split_create_successors(self) -> None:
        fixture = valid_snapshot()
        parent = deepcopy(fixture)
        for operation in (
            "INSERT_CLIP",
            "REMOVE_CLIP",
            "MOVE_CLIP",
            "TRIM_CLIP",
            "SPLIT_CLIP",
        ):
            with self.subTest(operation=operation):
                result = apply_edit(fixture, operation).as_dict()
                version = result["timelineVersion"]
                self.assertEqual(version["versionNumber"], 2)
                self.assertEqual(
                    version["parentTimelineVersionRef"], TIMELINE_VERSION_REF
                )
                self.assertEqual(
                    version["parentTimelineVersionDigest"],
                    fixture["timelineVersion"]["payloadDigest"],
                )
                clips = {item["clipRef"]: item for item in result["clips"]}
                if operation == "INSERT_CLIP":
                    self.assertIn("clip-video-inserted", clips)
                elif operation == "REMOVE_CLIP":
                    self.assertNotIn("clip-effect", clips)
                elif operation == "MOVE_CLIP":
                    self.assertEqual(
                        clips["clip-video"]["timelineStartFrameInclusive"],
                        24,
                    )
                elif operation == "TRIM_CLIP":
                    self.assertEqual(
                        clips["clip-video"]["sourceBinding"][
                            "sourceOutFrameExclusive"
                        ],
                        12,
                    )
                else:
                    self.assertEqual(
                        {
                            clips["clip-video"]["timelineEndFrameExclusive"],
                            clips["clip-video-right"][
                                "timelineStartFrameInclusive"
                            ],
                        },
                        {12},
                    )
        self.assertEqual(fixture, parent)

    def test_enable_disable_and_reorder_are_successor_only(self) -> None:
        fixture = valid_snapshot()
        disabled = apply_edit(fixture, "DISABLE_CLIP").as_dict()
        disabled_clip = next(
            item for item in disabled["clips"] if item["clipRef"] == "clip-video"
        )
        self.assertFalse(disabled_clip["enabled"])

        enabled = apply_edit(fixture, "ENABLE_CLIP").as_dict()
        enabled_clip = next(
            item for item in enabled["clips"] if item["clipRef"] == "clip-video"
        )
        self.assertTrue(enabled_clip["enabled"])

        reordered = apply_edit(fixture, "REORDER_TRACK").as_dict()
        order_by_ref = {
            item["trackRef"]: item["order"] for item in reordered["tracks"]
        }
        self.assertEqual(order_by_ref["track-video"], 1)
        self.assertEqual(order_by_ref["track-audio"], 0)
        self.assertEqual(fixture["tracks"][0]["order"], 0)

    def test_transition_speed_transform_and_masks_are_closed_edits(self) -> None:
        fixture = valid_snapshot()
        expected = {
            "SET_TRANSITION": lambda clip: self.assertEqual(
                clip["transitionIn"]["transitionKind"], "FADE_IN"
            ),
            "SET_SPEED": lambda clip: self.assertEqual(
                (clip["speed"]["numerator"], clip["speed"]["denominator"]),
                (1, 1),
            ),
            "SET_TRANSFORM": lambda clip: self.assertEqual(
                clip["transform"]["positionXPixels"], 32
            ),
            "SET_MASKS": lambda clip: self.assertEqual(
                clip["maskBindings"][0]["maskAssetVersionRef"],
                "asset-version-mask-edit-v1",
            ),
        }
        for operation, assertion in expected.items():
            with self.subTest(operation=operation):
                result = apply_edit(fixture, operation).as_dict()
                clip = next(
                    item
                    for item in result["clips"]
                    if item["clipRef"] == "clip-video"
                )
                assertion(clip)

    def test_safe_area_and_output_profiles_are_version_level_edits(self) -> None:
        fixture = valid_snapshot()
        safe_area = apply_edit(fixture, "SET_SAFE_AREA").as_dict()[
            "timelineVersion"
        ]["safeArea"]
        self.assertEqual(safe_area["leftPixels"], 32)
        profiles = apply_edit(fixture, "SET_OUTPUT_PROFILES").as_dict()[
            "timelineVersion"
        ]["outputProfileBindings"]
        self.assertEqual(
            profiles[0]["outputProfileRef"],
            "output-profile-vertical-704x1280",
        )

    def test_exact_replay_matches_and_changed_replay_conflicts(self) -> None:
        fixture = valid_snapshot()
        exact = validate_timeline_edit_command(
            timeline_edit_command(fixture, "REMOVE_CLIP")
        )
        assert_timeline_edit_replay(exact.as_dict()["payloadDigest"], exact)

        changed = timeline_edit_command(
            fixture,
            "DISABLE_CLIP",
            operation_ref=exact.as_dict()["operationRef"],
            idempotency_key=exact.as_dict()["idempotencyKey"],
        )
        with self.assertRaises(TimelineEditingConflictError):
            assert_timeline_edit_replay(
                exact.as_dict()["payloadDigest"], changed
            )

    def test_predecessor_mismatch_and_arbitrary_patch_fail_closed(self) -> None:
        fixture = valid_snapshot()
        parent_version = validate_timeline_version(fixture["timelineVersion"])
        exact = timeline_edit_command(fixture, "REMOVE_CLIP")
        raw = deepcopy(exact)
        raw.pop("schemaVersion")
        raw.pop("payloadDigest")
        raw["parentTimelineVersionDigest"] = DIGEST_B
        mismatched = build_timeline_edit_command(raw)
        with self.assertRaises(TimelineEditingStaleInputError):
            apply_timeline_edit(
                parent_version,
                [validate_timeline_track(item) for item in fixture["tracks"]],
                [validate_timeline_clip(item) for item in fixture["clips"]],
                validate_timeline_edit_command(mismatched),
                existing_timeline_versions=[parent_version],
            )

        raw = deepcopy(exact)
        raw.pop("schemaVersion")
        raw.pop("payloadDigest")
        raw["arguments"] = {
            "clipRef": "clip-effect",
            "patch": "/clips/0/sourceBinding",
        }
        with self.assertRaises(TimelineEditingContractError):
            build_timeline_edit_command(raw)


if __name__ == "__main__":
    unittest.main()
