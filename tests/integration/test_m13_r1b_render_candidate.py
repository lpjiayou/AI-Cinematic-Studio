from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from services.v4_platform.render_candidate import V4RenderCandidateExecutor
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    _digest,
)
from services.v5_core_os.episode_production.media import ArtifactRejectedError
from services.v5_core_os.episode_production.timeline_editing import (
    build_speed_spec,
    build_transform_spec,
    build_transition_spec,
)
from tests.integration.m13_e3_support import (
    CREATED_AT,
    CurrentIdentityProjectionReader,
    CurrentScriptTextReader,
    admit_canonical_font,
    canonical_mark_asset,
    restart_font_authority,
)
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _insert_and_bind_timeline,
    _register_inputs,
    _seed_real_video_ready,
)
from tests.integration.test_m13_e2_timeline_v3_preview import _append_e2_profile
from tests.integration.test_m13_e3_timeline_v3_preview import (
    _authority,
    _face_command,
    _insert_and_bind_e3,
    _nameplate_command,
    _service,
    _source,
)
from tests.integration.test_m13_e4_timeline_v3_preview import (
    E4_EFFECT_ORDER,
    _distance_state_command,
    _insert_and_bind_e4,
)
from tests.integration.test_m13_r1a_composition_render_manifest import (
    _command as manifest_command,
    _profile,
    _toolchain,
)


def _candidate_command(run: dict, manifest_result: dict, slug: str) -> dict:
    timeline = manifest_result["timelineVersion"]
    composition = manifest_result["compositionVersion"]
    manifest = manifest_result["renderManifest"]
    return {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "operationRef": f"m13-r1b-{slug}",
        "idempotencyKey": f"m13-r1b-{slug}-key",
        "expectedRunVersion": 1,
        "timelineVersionRef": timeline["timelineVersionRef"],
        "timelineVersionDigest": timeline["payloadDigest"],
        "compositionVersionRef": composition["compositionVersionRef"],
        "compositionVersionDigest": composition["payloadDigest"],
        "renderManifestRef": manifest["renderManifestRef"],
        "renderManifestDigest": manifest["payloadDigest"],
    }


def _edit_video_timeline(
    service,
    run: dict,
    parent: dict,
    *,
    slug: str,
    operation: str,
    arguments: dict,
) -> dict:
    version = parent["timelineVersion"]
    return service.edit_timeline(
        {
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "operationRef": f"m13-r1b-video-{slug}",
            "idempotencyKey": f"m13-r1b-video-{slug}-key",
            "expectedRunVersion": 1,
            "parentTimelineVersionRef": version["timelineVersionRef"],
            "parentTimelineVersionDigest": version["payloadDigest"],
            "editCommand": {
                "operation": operation,
                "arguments": deepcopy(arguments),
            },
        }
    )


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13R1BRenderCandidateIntegrationTests(unittest.TestCase):
    def test_full_cpu_render_repeats_restarts_and_rejects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_root = root / "artifacts"
            evidence_path = root / "evidence.sqlite3"
            raw_inputs = _source(artifact_root)
            run, storyboard, graph = _authority(raw_inputs)
            inputs = type(raw_inputs)(
                audio=raw_inputs.audio,
                base=raw_inputs.base,
                masks=raw_inputs.masks,
                inspection=raw_inputs.inspection,
                requirement=raw_inputs.requirement,
                run=run,
            )
            mark = canonical_mark_asset(
                run=run, base=inputs.base, source=inputs.masks[4]
            )
            repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=True
            )
            _seed_real_video_ready(repository, run, storyboard, graph)
            font_fixture = admit_canonical_font(run=run, evidence=repository)
            toolchain = _toolchain()
            service, composition = _service(
                artifact_root=artifact_root,
                repository=repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=CurrentIdentityProjectionReader(run),
                script_reader=CurrentScriptTextReader(run),
                font_authority=font_fixture.service,
                render_toolchain_identity=toolchain,
            )
            composition.render_candidate = V4RenderCandidateExecutor(
                artifact_root,
                composition,
                font_asset_authority=font_fixture.service,
            ).execute
            _register_inputs(service, inputs)
            smoke_layer = deepcopy(inputs.masks[3])
            smoke_layer.pop("payloadDigest")
            smoke_layer["assetVersionRef"] = "asset-version-m13-r1b-smoke-layer"
            smoke_layer["payloadDigest"] = _digest(smoke_layer)
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=run["workspaceRef"],
                    productionRunRef=run["productionRunRef"],
                    recordKind="MaskAssetVersion",
                    recordRef=smoke_layer["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-r1b-smoke-layer",
                    requestDigest=_digest(
                        {"smokeLayer": smoke_layer["payloadDigest"]}
                    ),
                    createdAt=CREATED_AT,
                    payload=smoke_layer,
                    payloadDigest=smoke_layer["payloadDigest"],
                )
            )
            e2_chains, _ = _append_e2_profile(
                artifact_root, repository, service, inputs, smoke_layer
            )
            e2_timeline = _insert_and_bind_timeline(
                service, inputs, run, e2_chains
            )
            nameplate = service.execute_deterministic_effect(
                _nameplate_command(run, inputs.base, font_fixture.asset)
            )
            face = service.execute_deterministic_effect(
                _face_command(run, inputs.base, mark)
            )
            e3_timeline, _ = _insert_and_bind_e3(
                service,
                run,
                e2_timeline,
                [nameplate["deterministicEffect"], face["deterministicEffect"]],
            )
            distance = service.execute_deterministic_effect(
                _distance_state_command(run, inputs.base, mark, inputs.masks[4])
            )
            current, _ = _insert_and_bind_e4(
                service, run, e3_timeline, distance["deterministicEffect"]
            )
            video = next(
                item for item in current["clips"] if item["clipKind"] == "VIDEO"
            )
            right_clip_ref = "m13-r1b-video-clip-right"
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="split",
                operation="SPLIT_CLIP",
                arguments={
                    "clipRef": video["clipRef"],
                    "splitTimelineFrame": 32,
                    "rightClipRef": right_clip_ref,
                },
            )
            right = next(
                item for item in current["clips"] if item["clipRef"] == right_clip_ref
            )
            trimmed_source = deepcopy(right["sourceBinding"])
            trimmed_source["sourceOutFrameExclusive"] = 48
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="trim",
                operation="TRIM_CLIP",
                arguments={
                    "clipRef": right_clip_ref,
                    "timelineStartFrameInclusive": 32,
                    "timelineEndFrameExclusive": 48,
                    "sourceBinding": trimmed_source,
                },
            )
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="speed",
                operation="SET_SPEED",
                arguments={
                    "clipRef": right_clip_ref,
                    "speed": build_speed_spec(
                        {"numerator": 2, "denominator": 1}
                    ),
                },
            )
            crossfade = build_transition_spec(
                {
                    "transitionKind": "CROSSFADE",
                    "durationFrames": 4,
                    "curve": "LINEAR",
                    "alignment": "CENTER",
                }
            )
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="transition-out",
                operation="SET_TRANSITION",
                arguments={
                    "clipRef": video["clipRef"],
                    "edge": "OUT",
                    "transition": crossfade,
                },
            )
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="transition-in",
                operation="SET_TRANSITION",
                arguments={
                    "clipRef": right_clip_ref,
                    "edge": "IN",
                    "transition": crossfade,
                },
            )
            current = _edit_video_timeline(
                service,
                run,
                current,
                slug="transform",
                operation="SET_TRANSFORM",
                arguments={
                    "clipRef": right_clip_ref,
                    "transform": build_transform_spec(
                        {
                            "positionXPixels": 2,
                            "positionYPixels": -2,
                            "scaleX": {"numerator": 3, "denominator": 4},
                            "scaleY": {"numerator": 3, "denominator": 4},
                            "rotationMilliDegrees": 0,
                            "anchorXPixels": 0,
                            "anchorYPixels": 0,
                            "opacity": 875,
                            "perspectiveMode": "NONE",
                            "perspectiveMatrix": None,
                            "perspectiveCorners": None,
                        }
                    ),
                },
            )
            timeline = current["timelineVersion"]

            sidecar_manifest = service.create_composition_render_manifest(
                manifest_command(
                    run,
                    timeline,
                    slug="r1b-sidecar",
                    profile=_profile(64, 64, subtitle_mode="SIDECAR"),
                )
            )
            burn_manifest = service.create_composition_render_manifest(
                manifest_command(
                    run,
                    timeline,
                    slug="r1b-burn",
                    profile=_profile(
                        64,
                        64,
                        subtitle_mode="BURN_IN",
                        font=font_fixture.asset,
                    ),
                )
            )
            video_bindings = sidecar_manifest["compositionVersion"][
                "videoTrackBindings"
            ]
            self.assertEqual(len(video_bindings), 2)
            edited_binding = next(
                item for item in video_bindings if item["clipRef"] == right_clip_ref
            )
            self.assertEqual(
                edited_binding["speed"],
                build_speed_spec({"numerator": 2, "denominator": 1}),
            )
            self.assertEqual(
                edited_binding["transitionIn"]["transitionKind"],
                "CROSSFADE",
            )
            self.assertEqual(
                edited_binding["transform"]["scaleX"],
                {"numerator": 3, "denominator": 4},
            )

            first_command = _candidate_command(
                run, sidecar_manifest, "sidecar-first"
            )
            for stale_field in (
                "timelineVersionDigest",
                "compositionVersionDigest",
                "renderManifestDigest",
            ):
                stale_command = deepcopy(first_command)
                stale_command[stale_field] = "0" * 64
                with self.subTest(staleAuthority=stale_field):
                    with self.assertRaises(EpisodeProductionError):
                        service.create_render_candidate(stale_command)
            first = service.create_render_candidate(first_command)
            first_candidate = first["renderCandidate"]
            self.assertFalse(first["idempotentReplay"])
            self.assertEqual(first_candidate["state"], "RENDERED_CANDIDATE")
            self.assertEqual(first_candidate["technicalValidationState"], "PASS")
            self.assertEqual(first_candidate["qcState"], "NOT_RUN")
            self.assertEqual(first_candidate["approvalState"], "NOT_REQUESTED")
            self.assertEqual(first_candidate["assetAdmissionState"], "NOT_ADMITTED")
            self.assertEqual(first_candidate["masterState"], "NOT_CREATED")
            self.assertEqual(first_candidate["exportState"], "NOT_CREATED")
            self.assertFalse(first_candidate["publicationAllowed"])
            self.assertFalse(first["runtimeEvidence"]["gpuUsed"])
            self.assertFalse(first["runtimeEvidence"]["providerUsed"])
            self.assertIsNotNone(first["artifactEvidence"]["subtitleSidecar"])
            self.assertEqual(
                (first_candidate["mediaProbe"]["width"], first_candidate["mediaProbe"]["height"]),
                (64, 64),
            )
            self.assertEqual(len(composition.preview_v3_requests), 1)
            full_render_request = composition.preview_v3_requests[0]
            self.assertEqual(
                [
                    item["effectMode"]
                    for item in full_render_request["effectStages"]
                ],
                E4_EFFECT_ORDER,
            )
            self.assertEqual(
                full_render_request["glyphStage"]["schemaVersion"],
                "v5.m13-glyph-reveal-execution-request.v2",
            )
            self.assertTrue(full_render_request["audioMix"]["clips"])

            current_media = service._test_e3_media_authority
            original_base = deepcopy(current_media.base)
            current_media.base["payloadDigest"] = "0" * 64
            with self.assertRaises(EpisodeProductionError):
                service.get_render_candidate(
                    run["workspaceRef"],
                    run["productionRunRef"],
                    first_candidate["renderCandidateRef"],
                )
            current_media.base = original_base

            original_toolchain = deepcopy(service.render_toolchain_identity)
            service.render_toolchain_identity = {
                **original_toolchain,
                "ffmpegBinaryDigest": "0" * 64,
            }
            with self.assertRaises(EpisodeProductionError):
                service.get_render_candidate(
                    run["workspaceRef"],
                    run["productionRunRef"],
                    first_candidate["renderCandidateRef"],
                )
            service.render_toolchain_identity = original_toolchain

            exact_replay = service.create_render_candidate(first_command)
            self.assertTrue(exact_replay["idempotentReplay"])
            self.assertEqual(exact_replay["renderCandidate"], first_candidate)

            second = service.create_render_candidate(
                _candidate_command(run, sidecar_manifest, "sidecar-second")
            )
            second_candidate = second["renderCandidate"]
            self.assertNotEqual(
                second_candidate["renderCandidateRef"],
                first_candidate["renderCandidateRef"],
            )
            for field in (
                "fileDigest",
                "decodedFramePixelDigest",
                "pcmContentDigest",
                "subtitleTimingDigest",
                "timelineVersionDigest",
                "compositionVersionDigest",
                "renderManifestDigest",
            ):
                self.assertEqual(first_candidate[field], second_candidate[field])

            changed_replay = deepcopy(first_command)
            changed_replay.update(
                {
                    "renderManifestRef": burn_manifest["renderManifest"][
                        "renderManifestRef"
                    ],
                    "renderManifestDigest": burn_manifest["renderManifest"][
                        "payloadDigest"
                    ],
                }
            )
            with self.assertRaises(IdempotencyConflictError):
                service.create_render_candidate(changed_replay)

            burn = service.create_render_candidate(
                _candidate_command(run, burn_manifest, "burn-in")
            )
            self.assertIsNone(burn["artifactEvidence"]["subtitleSidecar"])
            self.assertEqual(
                burn["renderCandidate"]["subtitleTimingDigest"],
                first_candidate["subtitleTimingDigest"],
            )
            self.assertNotEqual(
                burn["renderCandidate"]["decodedFramePixelDigest"],
                first_candidate["decodedFramePixelDigest"],
            )

            listed = service.list_render_candidates(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertEqual(len(listed["renderCandidates"]), 3)
            detail = service.get_render_candidate(
                run["workspaceRef"],
                run["productionRunRef"],
                first_candidate["renderCandidateRef"],
            )
            self.assertEqual(detail["renderCandidate"], first_candidate)
            content = service.get_render_candidate_content(
                run["workspaceRef"],
                run["productionRunRef"],
                first_candidate["renderCandidateRef"],
            )
            self.assertEqual(content["contentDisposition"], "inline")
            self.assertEqual(content["sha256"], first_candidate["fileDigest"].removeprefix("sha256:"))
            self.assertTrue(content["path"].is_file())

            kinds = [
                item["recordKind"]
                for item in repository.list_records(
                    run["workspaceRef"], run["productionRunRef"]
                )
            ]
            for kind in (
                "RenderExecutionRequest",
                "RenderRuntimeEvidence",
                "RenderArtifactEvidence",
                "RenderResult",
                "RenderCandidate",
            ):
                self.assertEqual(kinds.count(kind), 3)
            self.assertFalse(
                {
                    "EpisodeMaster",
                    "ExportArtifact",
                    "ExportCandidate",
                    "AssetAdmission",
                }.intersection(kinds)
            )

            restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=False
            )
            restarted_font = restart_font_authority(
                run=run,
                evidence=restarted_repository,
                fixture=font_fixture,
            )
            restarted, _ = _service(
                artifact_root=artifact_root,
                repository=restarted_repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=CurrentIdentityProjectionReader(run),
                script_reader=CurrentScriptTextReader(run),
                font_authority=restarted_font,
                render_toolchain_identity=toolchain,
            )
            replay_after_restart = restarted.create_render_candidate(first_command)
            self.assertTrue(replay_after_restart["idempotentReplay"])
            self.assertEqual(
                replay_after_restart["renderCandidate"], first_candidate
            )
            with self.assertRaises(EpisodeProductionError):
                restarted.get_render_candidate(
                    "foreign-workspace",
                    run["productionRunRef"],
                    first_candidate["renderCandidateRef"],
                )

            with content["path"].open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaises(ArtifactRejectedError):
                restarted.get_render_candidate(
                    run["workspaceRef"],
                    run["productionRunRef"],
                    first_candidate["renderCandidateRef"],
                )


if __name__ == "__main__":
    unittest.main()
