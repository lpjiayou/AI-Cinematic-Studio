from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os.episode_production.audio_authority import (
    validate_dialogue_asset_version,
)
from services.v5_core_os.episode_production.audio_timing import (
    build_source_audio_timing_evidence,
    validate_audio_cue,
)
from services.v5_core_os.episode_production.audio_validation import (
    build_audio_technical_validation,
    validate_audio_technical_validation,
)
from services.v5_core_os.episode_production.foundation import (
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
    GlyphRevealScheduleError,
    build_glyph_reveal_requirement_v2,
)
from services.v5_core_os.episode_production.timeline_preview import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC,
    PCM_CONTENT_DIGEST_SPEC,
    TECHNICAL_FIXTURE_LABELS,
    TIMELINE_MIX_PARAMETERS,
    PreviewArtifactError,
    TimelineAuthorityError,
    TimelinePreviewContractError,
    TimelineRangeError,
    TimelineSourceBindingError,
    TimelineTrackError,
    build_audio_input_binding,
    build_composition_result,
    build_mask_asset_version_binding,
    build_preview_candidate,
    build_subtitle_manifest,
    build_timeline,
    build_timeline_clip,
    build_timeline_input_bundle,
    build_timeline_track,
    build_timeline_mix_request,
    build_timeline_version,
    validate_audio_input_binding,
    validate_composition_result,
    validate_mask_asset_version_binding,
    validate_preview_candidate,
    validate_subtitle_manifest,
    validate_timeline,
    validate_timeline_clip,
    validate_timeline_input_bundle,
    validate_timeline_track,
    validate_timeline_mix_request,
    validate_timeline_version,
)
from tests.contract.test_m12_audio_technical_validation_contract import (
    analysis_evidence,
    technical_source,
    validation_command,
)
from tests.contract.test_m12_audio_timing_contract import (
    SCRIPT_VERSION_DIGEST,
    SCRIPT_VERSION_REF,
    build_cue,
    build_stem_member_fixture,
    build_stem_set_fixture,
    explicit_source_assets,
)
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
    inspection_evidence_v2,
    requirement_command_v2,
    valid_contract_bundle,
)
from tests.contract.test_m13_glyph_reveal_contract import (
    build_valid_requirement as build_valid_glyph_v1_requirement,
)


def resealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def technical_dialogue_fixture() -> dict:
    bundle = explicit_source_assets()
    original = bundle["sources"]["dialogue"]
    evidence = deepcopy(original["v4Evidence"])
    evidence.pop("payloadDigest")
    evidence["artifactRef"] = "audio-artifact-" + evidence["sha256"][:32]
    evidence["artifactEvidenceRef"] = (
        "audio-artifact-evidence-"
        + _digest(
            {
                "generationRequestDigest": evidence[
                    "generationRequestDigest"
                ],
                "executionRequestDigest": evidence[
                    "executionRequestDigest"
                ],
                "storageKey": evidence["storageKey"],
                "sha256": evidence["sha256"],
            }
        )[:32]
    )
    evidence = resealed(evidence)

    asset = deepcopy(original["asset"])
    asset.pop("payloadDigest")
    asset["artifact"].update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
        }
    )
    provenance = deepcopy(asset["provenance"])
    provenance.pop("payloadDigest")
    provenance.update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
        }
    )
    asset["provenance"] = resealed(provenance)
    asset = resealed(asset)
    asset_contract = validate_dialogue_asset_version(
        asset,
        confirmed_voice_lock=bundle["confirmedVoiceLock"],
        voice_asset_version=bundle["voiceAsset"],
    )
    timing = build_source_audio_timing_evidence(
        evidence,
        source_asset_version=asset_contract,
    )
    source = {
        "asset": asset,
        "assetContract": asset_contract,
        "v4Evidence": evidence,
        "timingEvidence": timing,
    }
    bundle["sources"]["dialogue"] = source
    cue = build_cue(source, "dialogue", sourceEndSample=4_000)
    cue_contract = validate_audio_cue(
        cue,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        source_timing_evidence=timing,
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )
    analysis = analysis_evidence(source)
    command = validation_command("timeline-dialogue")
    command.update(
        {
            "validationRef": "audio-technical-validation-dialogue",
            "validationVersionRef": (
                "audio-technical-validation-dialogue-v1"
            ),
        }
    )
    validation_mapping = build_audio_technical_validation(
        command,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue_contract],
    )
    validation = validate_audio_technical_validation(
        validation_mapping,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue_contract],
    )
    binding_mapping = build_audio_input_binding(
        {
            "workspaceRef": asset["workspaceRef"],
            "productionRunRef": asset["productionRunRef"],
            "audioInputBindingRef": "audio-input-binding-dialogue-m12-m13",
            "sourceLabels": sorted(TECHNICAL_FIXTURE_LABELS),
        },
        asset_version=asset_contract,
        technical_validation=validation,
    )
    binding = validate_audio_input_binding(binding_mapping)
    member = build_stem_member_fixture(
        source,
        "dialogue",
        suffix="timeline",
        cue=cue,
        source_end=cue["sourceEndSample"],
    )
    stem_set = build_stem_set_fixture(
        bundle,
        [member],
        suffix="timeline",
        cues=[cue],
    )
    return {
        "bundle": bundle,
        "source": source,
        "cue": cue,
        "cueContract": cue_contract,
        "analysis": analysis,
        "validation": validation,
        "binding": binding,
        "member": member,
        "stemSet": stem_set,
    }


def scoped_glyph_fixture(workspace_ref: str, run_ref: str) -> dict:
    base, masks, _, _ = valid_contract_bundle()
    base.update(
        {"workspaceRef": workspace_ref, "productionRunRef": run_ref}
    )
    base = resealed(base)
    masks = [
        resealed(
            {
                **mask,
                "workspaceRef": workspace_ref,
                "productionRunRef": run_ref,
            }
        )
        for mask in masks
    ]
    inspection = inspection_evidence_v2(base)
    inspection.update(
        {"workspaceRef": workspace_ref, "productionRunRef": run_ref}
    )
    inspection = resealed(inspection)
    store = InMemoryInspectionEvidenceStore(inspection)
    adapter = DigestPinnedBasePlateGlyphInspectionAdapter(store)
    requirement = build_glyph_reveal_requirement_v2(
        requirement_command_v2(
            workspaceRef=workspace_ref,
            productionRunRef=run_ref,
        ),
        base_plate_asset=base,
        mask_assets=masks,
        inspection_adapter=adapter,
    )
    bindings = []
    for index, mask in enumerate(masks, start=1):
        binding_mapping = build_mask_asset_version_binding(
            {
                "workspaceRef": workspace_ref,
                "productionRunRef": run_ref,
                "maskAssetVersionBindingRef": (
                    f"mask-asset-binding-zhen-{index}"
                ),
                "glyphSlug": "zhen",
                "maskOrdinal": index,
            },
            asset_version=mask,
        )
        bindings.append(validate_mask_asset_version_binding(binding_mapping))
    return {
        "base": base,
        "masks": masks,
        "inspection": inspection,
        "adapter": adapter,
        "requirement": requirement,
        "maskBindings": bindings,
    }


def valid_timeline_input_fixture() -> dict:
    audio = technical_dialogue_fixture()
    binding_mapping = audio["binding"].as_dict()
    workspace = binding_mapping["workspaceRef"]
    run_ref = binding_mapping["productionRunRef"]
    glyph = scoped_glyph_fixture(workspace, run_ref)
    command = {
        "workspaceRef": workspace,
        "productionRunRef": run_ref,
        "timelineInputBundleRef": "timeline-input-bundle-m12-m13-v1",
        "scriptVersionRef": SCRIPT_VERSION_REF,
        "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
    }
    bundle_mapping = build_timeline_input_bundle(
        command,
        audio_input_bindings=[audio["binding"]],
        audio_cues=[audio["cueContract"]],
        audio_stem_set=audio["stemSet"],
        audio_stem_members=[audio["member"]],
        glyph_reveal_requirements=[glyph["requirement"]],
        mask_asset_bindings=glyph["maskBindings"],
    )
    return {
        "audio": audio,
        "glyph": glyph,
        "command": command,
        "inputBundle": validate_timeline_input_bundle(bundle_mapping),
    }


def rebuild_timeline_input_bundle(
    fixture: dict,
    *,
    command: dict | None = None,
    audio_cues: list[dict] | None = None,
    stem_members: list[dict] | None = None,
    stem_set: dict | None = None,
    glyph_requirements: list | None = None,
) -> dict:
    audio = fixture["audio"]
    glyph = fixture["glyph"]
    return build_timeline_input_bundle(
        command or fixture["command"],
        audio_input_bindings=[audio["binding"]],
        audio_cues=audio_cues or [audio["cue"]],
        audio_stem_set=stem_set or audio["stemSet"],
        audio_stem_members=stem_members or [audio["member"]],
        glyph_reveal_requirements=(
            glyph_requirements or [glyph["requirement"]]
        ),
        mask_asset_bindings=glyph["maskBindings"],
    )


FRAME_RATE = {"numerator": 24, "denominator": 1}
DURATION_FRAMES = 49
CREATED_AT = "2026-08-30T04:00:00Z"


def valid_timeline_graph_fixture() -> dict:
    fixture = valid_timeline_input_fixture()
    input_bundle = fixture["inputBundle"]
    audio = fixture["audio"]
    glyph = fixture["glyph"]
    asset = audio["source"]["asset"]
    scope = {
        "workspaceRef": asset["workspaceRef"],
        "projectRef": asset["projectRef"],
        "seriesRef": asset["seriesRef"],
        "episodeRef": asset["episodeRef"],
        "productionRunRef": asset["productionRunRef"],
    }
    timeline_mapping = build_timeline(
        {
            **scope,
            "timelineRef": "timeline-m12-m13-preview",
            "createdBy": "v5.m12-m13.timeline.contract-test",
            "createdAt": CREATED_AT,
        }
    )
    timeline = validate_timeline(timeline_mapping)

    base = glyph["base"]
    requirement = glyph["requirement"].as_dict()
    cue = audio["cue"]
    member = audio["member"]
    binding = audio["binding"].as_dict()
    clip_commands = {
        "VIDEO": {
            "workspaceRef": scope["workspaceRef"],
            "productionRunRef": scope["productionRunRef"],
            "timelineClipRef": "timeline-clip-video-m12-m13",
            "timelineTrackRef": "timeline-track-video-m12-m13",
            "trackKind": "VIDEO",
            "timelineStartFrame": 0,
            "timelineEndFrameExclusive": DURATION_FRAMES,
            "sourceBinding": {
                "creativeShotRef": base["creativeShotRef"],
                "assetVersionRef": base["assetVersionRef"],
                "assetVersionDigest": base["payloadDigest"],
                "storageKey": base["storageKey"],
                "fileDigest": f"sha256:{base['sha256']}",
                "sourceStartFrame": 0,
                "sourceEndFrameExclusive": DURATION_FRAMES,
            },
        },
        "AUDIO": {
            "workspaceRef": scope["workspaceRef"],
            "productionRunRef": scope["productionRunRef"],
            "timelineClipRef": "timeline-clip-audio-m12-m13",
            "timelineTrackRef": "timeline-track-audio-m12-m13",
            "trackKind": "AUDIO",
            "timelineStartFrame": 0,
            "timelineEndFrameExclusive": 2,
            "sourceBinding": {
                "audioInputBindingRef": binding["audioInputBindingRef"],
                "stemMemberRef": member["stemMemberRef"],
                "gainDb": 0,
                "fadeInSamples": 0,
                "fadeOutSamples": 0,
            },
        },
        "SUBTITLE": {
            "workspaceRef": scope["workspaceRef"],
            "productionRunRef": scope["productionRunRef"],
            "timelineClipRef": "timeline-clip-subtitle-m12-m13",
            "timelineTrackRef": "timeline-track-subtitle-m12-m13",
            "trackKind": "SUBTITLE",
            "timelineStartFrame": 0,
            "timelineEndFrameExclusive": 2,
            "sourceBinding": {
                "audioCueVersionRef": cue["cueVersionRef"],
                "stemMemberRef": member["stemMemberRef"],
                "language": "zh-CN",
            },
        },
        "EFFECT": {
            "workspaceRef": scope["workspaceRef"],
            "productionRunRef": scope["productionRunRef"],
            "timelineClipRef": "timeline-clip-effect-m12-m13",
            "timelineTrackRef": "timeline-track-effect-m12-m13",
            "trackKind": "EFFECT",
            "timelineStartFrame": requirement["frameRangeStartInclusive"],
            "timelineEndFrameExclusive": requirement[
                "frameRangeEndExclusive"
            ],
            "sourceBinding": {
                "glyphRevealRequirementRef": requirement["requirementRef"]
            },
        },
    }
    clips = {}
    for kind, command in clip_commands.items():
        mapping = build_timeline_clip(
            command,
            timeline_input_bundle=input_bundle,
            frame_rate=FRAME_RATE,
            duration_frames=DURATION_FRAMES,
        )
        clips[kind] = validate_timeline_clip(
            mapping,
            timeline_input_bundle=input_bundle,
            frame_rate=FRAME_RATE,
            duration_frames=DURATION_FRAMES,
        )
    tracks = []
    for ordinal, kind in enumerate(("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")):
        mapping = build_timeline_track(
            {
                "workspaceRef": scope["workspaceRef"],
                "productionRunRef": scope["productionRunRef"],
                "timelineTrackRef": clip_commands[kind]["timelineTrackRef"],
                "trackKind": kind,
                "ordinal": ordinal,
            },
            clips=[clips[kind]],
            timeline_input_bundle=input_bundle,
            frame_rate=FRAME_RATE,
            duration_frames=DURATION_FRAMES,
        )
        tracks.append(
            validate_timeline_track(
                mapping,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )
        )
    version_command = {
        **scope,
        "timelineVersionRef": "timeline-version-m12-m13-preview-v1",
        "version": 1,
        "supersedesTimelineVersionRef": None,
        "supersedesTimelineVersionDigest": None,
        "scriptVersionRef": SCRIPT_VERSION_REF,
        "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
        "frameRate": FRAME_RATE,
        "width": 64,
        "height": 64,
        "pixelFormat": "yuv420p",
        "durationFrames": DURATION_FRAMES,
        "createdBy": "v5.m12-m13.timeline.contract-test",
        "createdAt": CREATED_AT,
    }
    version_mapping = build_timeline_version(
        version_command,
        timeline=timeline,
        tracks=tracks,
        timeline_input_bundle=input_bundle,
    )
    version = validate_timeline_version(
        version_mapping,
        timeline=timeline,
        timeline_input_bundle=input_bundle,
    )
    subtitle_mapping = build_subtitle_manifest(
        {
            "subtitleManifestRef": "subtitle-manifest-m12-m13-v1",
            "createdBy": "v5.m12-m13.timeline.contract-test",
            "createdAt": CREATED_AT,
        },
        timeline_version=version,
    )
    subtitle_manifest = validate_subtitle_manifest(
        subtitle_mapping,
        timeline_version=version,
    )
    mix_mapping = build_timeline_mix_request(
        {
            "mixRequestRef": "timeline-mix-request-m12-m13-v1",
            "createdBy": "v5.m12-m13.timeline.contract-test",
            "createdAt": CREATED_AT,
        },
        timeline_version=version,
        timeline_input_bundle=input_bundle,
    )
    mix_request = validate_timeline_mix_request(
        mix_mapping,
        timeline_version=version,
        timeline_input_bundle=input_bundle,
    )
    return {
        **fixture,
        "scope": scope,
        "timeline": timeline,
        "clipCommands": clip_commands,
        "clips": clips,
        "tracks": tracks,
        "versionCommand": version_command,
        "timelineVersion": version,
        "subtitleManifest": subtitle_manifest,
        "mixRequest": mix_request,
    }


def valid_audio_binding_fixture() -> dict:
    source = technical_source()
    analysis = analysis_evidence(source)
    validation_mapping = build_audio_technical_validation(
        validation_command("timeline"),
        source_asset_version=source["assetContract"],
        source_artifact_evidence=source["v4Evidence"],
        v4_analysis_evidence=analysis,
    )
    validation = validate_audio_technical_validation(
        validation_mapping,
        source_asset_version=source["assetContract"],
        source_artifact_evidence=source["v4Evidence"],
        v4_analysis_evidence=analysis,
    )
    asset = source["assetContract"].as_dict()
    command = {
        "workspaceRef": asset["workspaceRef"],
        "productionRunRef": asset["productionRunRef"],
        "audioInputBindingRef": "audio-input-binding-sfx-m12-m13",
        "sourceLabels": sorted(TECHNICAL_FIXTURE_LABELS),
    }
    binding = build_audio_input_binding(
        command,
        asset_version=source["assetContract"],
        technical_validation=validation,
    )
    return {
        "source": source,
        "analysis": analysis,
        "validation": validation,
        "command": command,
        "binding": binding,
    }


def v4_composition_execution_fixture(graph: dict) -> dict:
    version = graph["timelineVersion"].as_dict()
    subtitle = graph["subtitleManifest"].as_dict()
    output = version["output"]
    renderer_identity = "v3.deterministic-timeline-preview-ffmpeg"
    renderer_version = "1"
    ffmpeg_identity = "ffmpeg version contract-fixture"
    execution_request_digest = _digest(
        {
            "timelineVersionDigest": version["payloadDigest"],
            "mixRequestDigest": graph["mixRequest"].as_dict()[
                "payloadDigest"
            ],
            "subtitleManifestDigest": subtitle["payloadDigest"],
        }
    )
    result = {
        "schemaVersion": "v4.m13-composition-result.v1",
        "compositionResultRef": "v4-composition-result-m12-m13-v1",
        "artifactRef": "v4-preview-artifact-m12-m13-v1",
        "executionRequestRef": "v4-composition-execution-m12-m13-v1",
        "executionRequestDigest": execution_request_digest,
        "timelineVersionRef": version["timelineVersionRef"],
        "timelineVersionDigest": version["payloadDigest"],
        "inputBindingsDigest": _digest(
            {
                "timelineInputBundleDigest": version[
                    "timelineInputBundleDigest"
                ],
                "executionRequestDigest": execution_request_digest,
            }
        ),
        "outputStorageKey": "preview/timeline-m12-m13-v1.mp4",
        "outputByteSize": 4096,
        "outputMediaProbe": {
            "container": output["container"],
            "videoCodec": output["videoCodec"],
            "pixelFormat": output["pixelFormat"],
            "width": output["width"],
            "height": output["height"],
            "frameRate": output["frameRate"],
            "frameCount": output["totalFrames"],
            "audioCodec": output["audioCodec"],
            "sampleRate": output["sampleRate"],
            "channelCount": output["channelCount"],
            "sampleCount": output["durationSamples"],
        },
        "outputDigest": {
            "fileDigest": "sha256:" + "7" * 64,
            "fileDigestAlgorithm": "sha256",
            "decodedFramePixelDigest": "sha256:" + "8" * 64,
            "decodedFramePixelDigestSpec": (
                DECODED_FRAME_PIXEL_DIGEST_SPEC
            ),
            "pixelMode": "RGBA",
            "width": output["width"],
            "height": output["height"],
            "frameCount": output["totalFrames"],
            "frameRate": output["frameRate"],
            "pcmContentDigest": "9" * 64,
            "pcmDigestSpec": PCM_CONTENT_DIGEST_SPEC,
            "sampleRate": output["sampleRate"],
            "channelCount": output["channelCount"],
            "sampleCount": output["durationSamples"],
        },
        "subtitleManifestRef": subtitle["subtitleManifestRef"],
        "subtitleManifestDigest": subtitle["payloadDigest"],
        "rendererIdentity": renderer_identity,
        "rendererVersion": renderer_version,
        "ffmpegIdentity": ffmpeg_identity,
        "runtimeEvidenceDigest": "sha256:" + _digest(
            {
                "ffmpegIdentity": ffmpeg_identity,
                "rendererIdentity": renderer_identity,
                "rendererVersion": renderer_version,
            }
        ),
        "adapterIdentity": "v4.local-composition-executor.v1",
        "provenance": "LOCAL_EVIDENCE",
        "providerUsed": False,
        "gpuUsed": False,
        "publicationAllowed": False,
    }
    return resealed(result)


def valid_preview_graph_fixture() -> dict:
    graph = valid_timeline_graph_fixture()
    execution = v4_composition_execution_fixture(graph)
    composition_mapping = build_composition_result(
        {
            "createdBy": "v5.m12-m13.timeline.contract-test",
            "createdAt": CREATED_AT,
        },
        timeline_version=graph["timelineVersion"],
        timeline_mix_request=graph["mixRequest"],
        subtitle_manifest=graph["subtitleManifest"],
        execution_result=execution,
    )
    composition = validate_composition_result(
        composition_mapping,
        timeline_version=graph["timelineVersion"],
        timeline_mix_request=graph["mixRequest"],
        subtitle_manifest=graph["subtitleManifest"],
    )
    preview_mapping = build_preview_candidate(
        {
            "previewCandidateRef": "preview-candidate-m12-m13",
            "previewCandidateVersionRef": "preview-candidate-m12-m13-v1",
            "version": 1,
            "supersedesPreviewCandidateVersionRef": None,
            "supersedesPreviewCandidateVersionDigest": None,
            "createdBy": "v5.m12-m13.timeline.contract-test",
            "createdAt": CREATED_AT,
        },
        timeline_version=graph["timelineVersion"],
        timeline_mix_request=graph["mixRequest"],
        subtitle_manifest=graph["subtitleManifest"],
        composition_result=composition,
    )
    preview = validate_preview_candidate(
        preview_mapping,
        timeline_version=graph["timelineVersion"],
        timeline_mix_request=graph["mixRequest"],
        subtitle_manifest=graph["subtitleManifest"],
        composition_result=composition,
    )
    return {
        **graph,
        "executionResult": execution,
        "compositionResult": composition,
        "previewCandidate": preview,
    }


class M12M13TimelineContractTests(unittest.TestCase):
    def test_audio_input_requires_validated_immutable_wrappers(self):
        fixture = valid_audio_binding_fixture()

        with self.subTest(boundary="asset"), self.assertRaises(
            TimelineAuthorityError
        ):
            build_audio_input_binding(
                fixture["command"],
                asset_version=fixture["source"]["asset"],
                technical_validation=fixture["validation"],
            )

        with self.subTest(boundary="technical-validation"), self.assertRaises(
            TimelineAuthorityError
        ):
            build_audio_input_binding(
                fixture["command"],
                asset_version=fixture["source"]["assetContract"],
                technical_validation=fixture["validation"].as_dict(),
            )

    def test_non_pass_clipping_validation_is_rejected(self):
        source = technical_source()
        analysis = analysis_evidence(source, clipping=True)
        failed_mapping = build_audio_technical_validation(
            validation_command("timeline-clipping"),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        failed = validate_audio_technical_validation(
            failed_mapping,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        command = {
            "workspaceRef": source["asset"]["workspaceRef"],
            "productionRunRef": source["asset"]["productionRunRef"],
            "audioInputBindingRef": "audio-input-binding-clipping-m12-m13",
            "sourceLabels": sorted(TECHNICAL_FIXTURE_LABELS),
        }

        self.assertEqual(failed.as_dict()["validationState"], "FAILED")
        self.assertTrue(failed.as_dict()["clippingDetected"])
        with self.assertRaises(TimelineAuthorityError):
            build_audio_input_binding(
                command,
                asset_version=source["assetContract"],
                technical_validation=failed,
            )

    def test_pcm_digest_drift_is_rejected_on_reread(self):
        fixture = valid_audio_binding_fixture()
        drifted = deepcopy(fixture["binding"])
        technical = deepcopy(drifted["technicalValidation"])
        technical["pcmContentDigest"] = "f" * 64
        technical = resealed(technical)
        drifted.update(
            {
                "technicalValidation": technical,
                "technicalValidationDigest": technical["payloadDigest"],
                "pcmContentDigest": technical["pcmContentDigest"],
            }
        )
        drifted = resealed(drifted)

        with self.assertRaises(TimelineSourceBindingError):
            validate_audio_input_binding(drifted)

    def test_audio_binding_and_fixture_labels_are_deterministic(self):
        first = valid_audio_binding_fixture()
        second = valid_audio_binding_fixture()

        self.assertEqual(first["binding"], second["binding"])
        self.assertEqual(
            first["binding"]["sourceLabels"],
            sorted(
                {
                    "LOCAL_TECHNICAL_FIXTURE",
                    "NOT_TTS",
                    "NOT_VOICE_CLONE",
                    "NOT_ADMITTED",
                }
            ),
        )
        self.assertFalse(first["binding"]["publicationAllowed"])
        self.assertEqual(
            validate_audio_input_binding(first["binding"]).as_dict(),
            first["binding"],
        )

    def test_technical_fixture_speech_requires_exact_honesty_labels(self):
        fixture = technical_dialogue_fixture()
        asset = fixture["source"]["assetContract"]
        validation = fixture["validation"]
        asset_mapping = asset.as_dict()
        required = set(TECHNICAL_FIXTURE_LABELS)

        for case, labels in (
            ("empty", []),
            ("missing", sorted(required - {"NOT_TTS"})),
            ("extra", sorted(required | {"PRODUCTION_TTS"})),
        ):
            command = {
                "workspaceRef": asset_mapping["workspaceRef"],
                "productionRunRef": asset_mapping["productionRunRef"],
                "audioInputBindingRef": f"audio-input-binding-{case}",
                "sourceLabels": labels,
            }
            with self.subTest(boundary="builder", case=case), self.assertRaises(
                TimelineAuthorityError
            ):
                build_audio_input_binding(
                    command,
                    asset_version=asset,
                    technical_validation=validation,
                )

        persisted = fixture["binding"].as_dict()
        persisted["sourceLabels"] = []
        persisted = resealed(persisted)
        with self.subTest(boundary="persisted"), self.assertRaises(
            TimelineAuthorityError
        ):
            validate_audio_input_binding(persisted)

        alternate_asset = deepcopy(fixture["source"]["asset"])
        alternate_provenance = deepcopy(alternate_asset["provenance"])
        alternate_provenance["adapterIdentity"] = "v4.alternate-local-fixture.v1"
        alternate_asset["provenance"] = resealed(alternate_provenance)
        alternate_asset = resealed(alternate_asset)
        alternate_contract = validate_dialogue_asset_version(
            alternate_asset,
            confirmed_voice_lock=fixture["bundle"]["confirmedVoiceLock"],
            voice_asset_version=fixture["bundle"]["voiceAsset"],
        )
        with self.subTest(boundary="alternate-adapter"), self.assertRaises(
            TimelineAuthorityError
        ):
            build_audio_input_binding(
                {
                    "workspaceRef": asset_mapping["workspaceRef"],
                    "productionRunRef": asset_mapping["productionRunRef"],
                    "audioInputBindingRef": "audio-input-binding-alternate-adapter",
                    "sourceLabels": [],
                },
                asset_version=alternate_contract,
                technical_validation=validation,
            )

    def test_timeline_inputs_bind_exact_cue_stem_glyph_and_mask_authority(self):
        first = valid_timeline_input_fixture()
        second = valid_timeline_input_fixture()
        first_value = first["inputBundle"].as_dict()
        second_value = second["inputBundle"].as_dict()

        self.assertEqual(first_value, second_value)
        self.assertEqual(len(first_value["audioInputBindings"]), 1)
        self.assertEqual(len(first_value["audioCues"]), 1)
        self.assertEqual(len(first_value["audioStemMembers"]), 1)
        self.assertEqual(len(first_value["glyphRevealRequirements"]), 1)
        self.assertEqual(len(first_value["maskAssetVersionBindings"]), 6)
        self.assertFalse(first_value["publicationAllowed"])

    def test_cue_range_script_text_and_timeline_claims_fail_closed(self):
        fixture = valid_timeline_input_fixture()
        cue = fixture["audio"]["cue"]

        outside = deepcopy(cue)
        outside["sourceEndSample"] = (
            fixture["audio"]["binding"].as_dict()["sampleCount"] + 1
        )
        outside = resealed(outside)
        with self.subTest(case="source-range"), self.assertRaises(
            TimelineRangeError
        ):
            rebuild_timeline_input_bundle(fixture, audio_cues=[outside])

        wrong_script = deepcopy(cue)
        wrong_script["scriptVersionRef"] = "script-version-wrong"
        wrong_script = resealed(wrong_script)
        with self.subTest(case="script-version"), self.assertRaises(
            TimelineSourceBindingError
        ):
            rebuild_timeline_input_bundle(
                fixture, audio_cues=[wrong_script]
            )

        wrong_text = deepcopy(cue)
        subtitle = deepcopy(wrong_text["subtitleTimingReference"])
        subtitle["textDigest"] = "0" * 64
        wrong_text["subtitleTimingReference"] = resealed(subtitle)
        wrong_text = resealed(wrong_text)
        with self.subTest(case="subtitle-text"), self.assertRaises(
            TimelineSourceBindingError
        ):
            rebuild_timeline_input_bundle(fixture, audio_cues=[wrong_text])

        timeline_claim = deepcopy(cue)
        timeline_claim["timelineStartFrame"] = 0
        timeline_claim = resealed(timeline_claim)
        with self.subTest(case="m12-final-timeline-field"), self.assertRaises(
            TimelinePreviewContractError
        ):
            rebuild_timeline_input_bundle(
                fixture, audio_cues=[timeline_claim]
            )

    def test_stem_role_and_stem_set_digest_drift_fail_closed(self):
        fixture = valid_timeline_input_fixture()
        member = deepcopy(fixture["audio"]["member"])
        member["stemRole"] = "sfx"
        member = resealed(member)
        with self.subTest(case="asset-type-role"), self.assertRaises(
            TimelineSourceBindingError
        ):
            rebuild_timeline_input_bundle(fixture, stem_members=[member])

        stem_set = deepcopy(fixture["audio"]["stemSet"])
        stale_member = deepcopy(stem_set["members"][0])
        stale_member["payloadDigest"] = "1" * 64
        stem_set["members"][0] = stale_member
        stem_set = resealed(stem_set)
        with self.subTest(case="stem-set-member-digest"), self.assertRaises(
            TimelineSourceBindingError
        ):
            rebuild_timeline_input_bundle(fixture, stem_set=stem_set)

    def test_glyph_v1_schedule_and_inspection_drift_fail_closed(self):
        fixture = valid_timeline_input_fixture()
        glyph_v1, *_ = build_valid_glyph_v1_requirement()
        with self.subTest(case="glyph-v1"), self.assertRaises(
            StaleInputError
        ):
            rebuild_timeline_input_bundle(
                fixture, glyph_requirements=[glyph_v1]
            )

        requirement = fixture["glyph"]["requirement"].as_dict()
        schedule_drift = deepcopy(requirement)
        schedule_drift["revealSchedule"][1]["startFrameInclusive"] += 1
        schedule_drift = resealed(schedule_drift)
        with self.subTest(case="schedule"), self.assertRaises(
            GlyphRevealScheduleError
        ):
            rebuild_timeline_input_bundle(
                fixture, glyph_requirements=[schedule_drift]
            )

        inspection_drift = deepcopy(requirement)
        inspection_drift["basePlateInspectionDigest"] = "2" * 64
        inspection_drift = resealed(inspection_drift)
        with self.subTest(case="inspection"), self.assertRaises(
            StaleInputError
        ):
            rebuild_timeline_input_bundle(
                fixture, glyph_requirements=[inspection_drift]
            )

    def test_client_paths_filters_and_publication_claims_are_rejected(self):
        fixture = valid_timeline_input_fixture()
        forbidden = {
            "absolute-path": {"inputPath": "/tmp/forbidden.wav"},
            "ffmpeg-filter": {"ffmpegFilter": "movie=/tmp/x"},
            "publication": {"publicationAllowed": True},
        }
        for case, extra in forbidden.items():
            command = {**fixture["command"], **extra}
            with self.subTest(case=case), self.assertRaises(
                TimelinePreviewContractError
            ):
                rebuild_timeline_input_bundle(fixture, command=command)

    def test_timeline_version_has_exactly_four_deterministic_tracks(self):
        first = valid_timeline_graph_fixture()
        second = valid_timeline_graph_fixture()
        first_value = first["timelineVersion"].as_dict()
        second_value = second["timelineVersion"].as_dict()
        first_subtitle = first["subtitleManifest"].as_dict()
        second_subtitle = second["subtitleManifest"].as_dict()
        first_mix = first["mixRequest"].as_dict()
        second_mix = second["mixRequest"].as_dict()

        self.assertEqual(first_value, second_value)
        self.assertEqual(first_subtitle, second_subtitle)
        self.assertEqual(first_mix, second_mix)
        self.assertEqual(
            [track["trackKind"] for track in first_value["tracks"]],
            ["VIDEO", "AUDIO", "SUBTITLE", "EFFECT"],
        )
        self.assertEqual(first_value["frameRate"], FRAME_RATE)
        self.assertEqual(first_value["roundingRule"], "FLOOR_EACH_BOUNDARY")
        self.assertEqual(first_value["durationFrames"], DURATION_FRAMES)
        self.assertEqual(first_value["output"]["durationSamples"], 98_000)
        self.assertEqual(
            first["clips"]["SUBTITLE"].as_dict()["sourceBinding"]["text"],
            "不要动。",
        )
        subtitle_source = first["clips"]["SUBTITLE"].as_dict()["sourceBinding"]
        self.assertEqual(subtitle_source["textStart"], subtitle_source["textRangeStart"])
        self.assertEqual(
            subtitle_source["textEndExclusive"],
            subtitle_source["textRangeEndExclusive"],
        )
        self.assertEqual(
            first["clips"]["EFFECT"].as_dict()["sourceBinding"][
                "glyphRevealRequirementDigest"
            ],
            first["glyph"]["requirement"].payload_digest,
        )
        effect_source = first["clips"]["EFFECT"].as_dict()["sourceBinding"]
        self.assertEqual(effect_source["layer"], 1)
        self.assertEqual(effect_source["blendMode"], "GRAZING_LIGHT_RELIEF")
        self.assertEqual(
            effect_source["blendMode"],
            effect_source["compositeParams"]["blendMode"],
        )
        self.assertEqual(len(first_subtitle["entries"]), 1)
        self.assertEqual(
            first_subtitle["entries"][0]["timelineClipDigest"],
            first["clips"]["SUBTITLE"].as_dict()["payloadDigest"],
        )
        self.assertEqual(
            first_subtitle["entries"][0]["textDigest"],
            first["audio"]["cue"]["subtitleTimingReference"][
                "textDigest"
            ],
        )
        self.assertEqual(first_mix["mixParameters"], TIMELINE_MIX_PARAMETERS)
        self.assertEqual(
            first_mix["mixParametersDigest"],
            _digest(TIMELINE_MIX_PARAMETERS),
        )
        self.assertEqual(
            first_mix["stemSetDigest"],
            first["audio"]["stemSet"]["payloadDigest"],
        )
        self.assertEqual(
            first_mix["clips"][0]["pcmContentDigest"],
            first["audio"]["binding"].as_dict()["pcmContentDigest"],
        )
        self.assertFalse(first_value["publicationAllowed"])
        self.assertFalse(first_subtitle["publicationAllowed"])
        self.assertFalse(first_mix["publicationAllowed"])

    def test_subtitle_and_mix_cross_digests_fail_closed(self):
        fixture = valid_timeline_graph_fixture()
        version = fixture["timelineVersion"]
        input_bundle = fixture["inputBundle"]

        subtitle = fixture["subtitleManifest"].as_dict()
        subtitle["entries"][0]["textDigest"] = "4" * 64
        subtitle = resealed(subtitle)
        with self.subTest(case="subtitle-text-digest"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_subtitle_manifest(
                subtitle,
                timeline_version=version,
            )

        mix_stem = fixture["mixRequest"].as_dict()
        mix_stem["stemSetDigest"] = "5" * 64
        mix_stem = resealed(mix_stem)
        with self.subTest(case="mix-stem-set-digest"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_timeline_mix_request(
                mix_stem,
                timeline_version=version,
                timeline_input_bundle=input_bundle,
            )

        mix_pcm = fixture["mixRequest"].as_dict()
        mix_pcm["clips"][0]["pcmContentDigest"] = "6" * 64
        mix_pcm = resealed(mix_pcm)
        with self.subTest(case="mix-pcm-digest"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_timeline_mix_request(
                mix_pcm,
                timeline_version=version,
                timeline_input_bundle=input_bundle,
            )

        mix_parameters = fixture["mixRequest"].as_dict()
        mix_parameters["mixParameters"]["roleGainDb"]["dialogue"] = -1
        mix_parameters["mixParametersDigest"] = _digest(
            mix_parameters["mixParameters"]
        )
        mix_parameters = resealed(mix_parameters)
        with self.subTest(case="mix-parameters"), self.assertRaises(
            TimelineAuthorityError
        ):
            validate_timeline_mix_request(
                mix_parameters,
                timeline_version=version,
                timeline_input_bundle=input_bundle,
            )

    def test_composition_and_preview_project_exact_deterministic_digests(self):
        first = valid_preview_graph_fixture()
        second = valid_preview_graph_fixture()
        first_composition = first["compositionResult"].as_dict()
        second_composition = second["compositionResult"].as_dict()
        first_preview = first["previewCandidate"].as_dict()
        second_preview = second["previewCandidate"].as_dict()

        self.assertEqual(first_composition, second_composition)
        self.assertEqual(first_preview, second_preview)
        self.assertEqual(
            first_composition["timelineVersionDigest"],
            first["timelineVersion"].as_dict()["payloadDigest"],
        )
        self.assertEqual(
            first_composition["mixRequestDigest"],
            first["mixRequest"].as_dict()["payloadDigest"],
        )
        self.assertEqual(
            first_composition["subtitleManifestDigest"],
            first["subtitleManifest"].as_dict()["payloadDigest"],
        )
        self.assertEqual(
            first_preview["compositionResultDigest"],
            first_composition["payloadDigest"],
        )
        self.assertEqual(
            first_composition["mixOutputPcmContentDigest"],
            first_composition["outputDigest"]["pcmContentDigest"],
        )
        self.assertEqual(
            first_preview["compositionRequestDigest"],
            first_composition["executionRequestDigest"],
        )
        self.assertEqual(
            first_preview["runtimeIdentity"],
            first_composition["runtimeEvidenceDigest"],
        )
        self.assertEqual(
            first_preview["mediaProbe"],
            first_composition["outputMediaProbe"],
        )
        self.assertEqual(
            first_preview["decodedFramePixelDigest"],
            first_composition["outputDigest"][
                "decodedFramePixelDigest"
            ],
        )
        self.assertEqual(
            first_preview["pcmContentDigest"],
            first_composition["outputDigest"]["pcmContentDigest"],
        )
        self.assertEqual(first_preview["approvalStatus"], "UNAPPROVED")
        self.assertFalse(first_composition["publicationAllowed"])
        self.assertFalse(first_preview["publicationAllowed"])

    def test_composition_output_and_preview_publication_drift_fail_closed(self):
        fixture = valid_preview_graph_fixture()

        execution = deepcopy(fixture["executionResult"])
        execution["outputDigest"]["sampleCount"] += 1
        execution = resealed(execution)
        with self.subTest(case="execution-sample-count"), self.assertRaises(
            PreviewArtifactError
        ):
            build_composition_result(
                {
                    "createdBy": "v5.m12-m13.timeline.contract-test",
                    "createdAt": CREATED_AT,
                },
                timeline_version=fixture["timelineVersion"],
                timeline_mix_request=fixture["mixRequest"],
                subtitle_manifest=fixture["subtitleManifest"],
                execution_result=execution,
            )

        publication = deepcopy(fixture["executionResult"])
        publication["publicationAllowed"] = True
        publication = resealed(publication)
        with self.subTest(case="execution-publication"), self.assertRaises(
            PreviewArtifactError
        ):
            build_composition_result(
                {
                    "createdBy": "v5.m12-m13.timeline.contract-test",
                    "createdAt": CREATED_AT,
                },
                timeline_version=fixture["timelineVersion"],
                timeline_mix_request=fixture["mixRequest"],
                subtitle_manifest=fixture["subtitleManifest"],
                execution_result=publication,
            )

        preview = fixture["previewCandidate"].as_dict()
        preview["publicationAllowed"] = True
        preview = resealed(preview)
        with self.subTest(case="preview-publication"), self.assertRaises(
            TimelineAuthorityError
        ):
            validate_preview_candidate(
                preview,
                timeline_version=fixture["timelineVersion"],
                timeline_mix_request=fixture["mixRequest"],
                subtitle_manifest=fixture["subtitleManifest"],
                composition_result=fixture["compositionResult"],
            )

        composition = fixture["compositionResult"].as_dict()
        composition["mixOutputPcmContentDigest"] = "a" * 64
        composition = resealed(composition)
        with self.subTest(case="mix-output-pcm"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_composition_result(
                composition,
                timeline_version=fixture["timelineVersion"],
                timeline_mix_request=fixture["mixRequest"],
                subtitle_manifest=fixture["subtitleManifest"],
            )

        for case, field, value in (
            ("composition-request", "compositionRequestDigest", "b" * 64),
            ("runtime-identity", "runtimeIdentity", "sha256:" + "c" * 64),
        ):
            preview = fixture["previewCandidate"].as_dict()
            preview[field] = value
            preview = resealed(preview)
            with self.subTest(case=case), self.assertRaises(
                TimelineSourceBindingError
            ):
                validate_preview_candidate(
                    preview,
                    timeline_version=fixture["timelineVersion"],
                    timeline_mix_request=fixture["mixRequest"],
                    subtitle_manifest=fixture["subtitleManifest"],
                    composition_result=fixture["compositionResult"],
                )

        preview = fixture["previewCandidate"].as_dict()
        preview["mediaProbe"]["frameCount"] += 1
        preview = resealed(preview)
        with self.subTest(case="media-probe"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_preview_candidate(
                preview,
                timeline_version=fixture["timelineVersion"],
                timeline_mix_request=fixture["mixRequest"],
                subtitle_manifest=fixture["subtitleManifest"],
                composition_result=fixture["compositionResult"],
            )

    def test_float_inverted_and_out_of_range_clip_time_is_rejected(self):
        fixture = valid_timeline_graph_fixture()
        input_bundle = fixture["inputBundle"]
        valid = fixture["clipCommands"]["VIDEO"]

        float_frame = deepcopy(valid)
        float_frame["timelineStartFrame"] = 0.0
        with self.subTest(case="float-frame"), self.assertRaises(
            TimelinePreviewContractError
        ):
            build_timeline_clip(
                float_frame,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

        float_seconds = {**valid, "timelineStartSeconds": 0.0}
        with self.subTest(case="float-seconds-authority"), self.assertRaises(
            TimelinePreviewContractError
        ):
            build_timeline_clip(
                float_seconds,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

        inverted = deepcopy(valid)
        inverted.update(
            {"timelineStartFrame": 10, "timelineEndFrameExclusive": 10}
        )
        with self.subTest(case="inverted"), self.assertRaises(
            TimelineRangeError
        ):
            build_timeline_clip(
                inverted,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

        outside = deepcopy(valid)
        outside["timelineEndFrameExclusive"] = DURATION_FRAMES + 1
        with self.subTest(case="outside-duration"), self.assertRaises(
            TimelineRangeError
        ):
            build_timeline_clip(
                outside,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

    def test_track_kind_and_clip_source_projection_mismatch_are_rejected(self):
        fixture = valid_timeline_graph_fixture()
        input_bundle = fixture["inputBundle"]

        with self.subTest(case="track-kind"), self.assertRaises(
            TimelineTrackError
        ):
            build_timeline_track(
                {
                    "workspaceRef": fixture["scope"]["workspaceRef"],
                    "productionRunRef": fixture["scope"][
                        "productionRunRef"
                    ],
                    "timelineTrackRef": "timeline-track-video-m12-m13",
                    "trackKind": "VIDEO",
                    "ordinal": 0,
                },
                clips=[fixture["clips"]["AUDIO"]],
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

        stale = fixture["clips"]["EFFECT"].as_dict()
        stale["sourceBinding"]["glyphRevealRequirementDigest"] = "3" * 64
        stale = resealed(stale)
        with self.subTest(case="effect-source-digest"), self.assertRaises(
            TimelineSourceBindingError
        ):
            validate_timeline_clip(
                stale,
                timeline_input_bundle=input_bundle,
                frame_rate=FRAME_RATE,
                duration_frames=DURATION_FRAMES,
            )

        for case, field, value in (
            ("effect-layer", "layer", 2),
            ("effect-blend", "blendMode", "RANDOM_BLEND"),
        ):
            stale = fixture["clips"]["EFFECT"].as_dict()
            stale["sourceBinding"][field] = value
            stale = resealed(stale)
            with self.subTest(case=case), self.assertRaises(
                TimelineSourceBindingError
            ):
                validate_timeline_clip(
                    stale,
                    timeline_input_bundle=input_bundle,
                    frame_rate=FRAME_RATE,
                    duration_frames=DURATION_FRAMES,
                )

        for case, field in (
            ("subtitle-text-start", "textStart"),
            ("subtitle-text-end", "textEndExclusive"),
        ):
            stale = fixture["clips"]["SUBTITLE"].as_dict()
            stale["sourceBinding"][field] += 1
            stale = resealed(stale)
            with self.subTest(case=case), self.assertRaises(
                TimelineSourceBindingError
            ):
                validate_timeline_clip(
                    stale,
                    timeline_input_bundle=input_bundle,
                    frame_rate=FRAME_RATE,
                    duration_frames=DURATION_FRAMES,
                )


if __name__ == "__main__":
    unittest.main()
