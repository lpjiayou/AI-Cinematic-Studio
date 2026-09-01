from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from services.v3_render_core.digests import file_sha256
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
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
    _register_inputs,
    _seed_real_video_ready,
    _insert_and_bind_timeline,
)
from tests.integration.test_m13_e2_timeline_v3_preview import (
    _append_e2_profile,
)
from tests.integration.test_m13_e3_timeline_v3_preview import (
    _authority,
    _face_command,
    _insert_and_bind_e3,
    _nameplate_command,
    _service,
    _source,
)
from tests.integration.test_m13_e4_timeline_v3_preview import (
    _distance_state_command,
    _insert_and_bind_e4,
)


def _toolchain() -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        raise AssertionError("FFmpeg toolchain is unavailable")
    return {
        "rendererIdentity": "v3-deterministic-render-core",
        "rendererVersion": "1",
        "ffmpegBinaryDigest": file_sha256(ffmpeg),
        "ffprobeBinaryDigest": file_sha256(ffprobe),
    }


def _profile(
    width: int,
    height: int,
    *,
    subtitle_mode: str = "SIDECAR",
    font: dict | None = None,
) -> dict:
    return {
        "outputProfile": {
            "profileRef": f"m13-r1a-{width}x{height}",
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
        "subtitleFontAssetVersionRef": (
            None if font is None else font["assetVersionRef"]
        ),
        "subtitleFontAssetVersionDigest": (
            None if font is None else font["payloadDigest"]
        ),
    }


def _command(
    run: dict,
    timeline: dict,
    *,
    slug: str,
    profile: dict,
) -> dict:
    return {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "operationRef": f"m13-r1a-{slug}",
        "idempotencyKey": f"m13-r1a-{slug}-key",
        "expectedRunVersion": 1,
        "timelineVersionRef": timeline["timelineVersionRef"],
        "timelineVersionDigest": timeline["payloadDigest"],
        "renderProfile": profile,
    }


def _contains_forbidden_fact(value) -> bool:
    fragments = (
        "storagekey",
        "path",
        "filter",
        "argv",
        "outputfile",
        "outputdigest",
        "rendercandidate",
        "episodemaster",
        "exportartifact",
    )
    if isinstance(value, dict):
        for key, item in value.items():
            folded = key.replace("_", "").replace("-", "").lower()
            if any(fragment in folded for fragment in fragments):
                return True
            if _contains_forbidden_fact(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_fact(item) for item in value)
    return False


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13R1ACompositionRenderManifestIntegrationTests(unittest.TestCase):
    def test_full_timeline_persists_replays_restarts_and_stales_safely(self) -> None:
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
            identity_reader = CurrentIdentityProjectionReader(run)
            script_reader = CurrentScriptTextReader(run)
            toolchain = _toolchain()
            service, _ = _service(
                artifact_root=artifact_root,
                repository=repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=identity_reader,
                script_reader=script_reader,
                font_authority=font_fixture.service,
                render_toolchain_identity=toolchain,
            )
            _register_inputs(service, inputs)

            smoke_layer = deepcopy(inputs.masks[3])
            smoke_layer.pop("payloadDigest")
            smoke_layer["assetVersionRef"] = "asset-version-m13-r1a-smoke-layer"
            smoke_layer["payloadDigest"] = _digest(smoke_layer)
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=run["workspaceRef"],
                    productionRunRef=run["productionRunRef"],
                    recordKind="MaskAssetVersion",
                    recordRef=smoke_layer["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-r1a-smoke-layer",
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
            timeline = current["timelineVersion"]

            micro_command = _command(
                run,
                timeline,
                slug="micro",
                profile=_profile(64, 64),
            )
            created = service.create_composition_render_manifest(micro_command)
            self.assertFalse(created["idempotentReplay"])
            self.assertEqual(
                {
                    len(created["compositionVersion"]["videoTrackBindings"]),
                    len(created["compositionVersion"]["audioTrackBindings"]),
                    len(created["compositionVersion"]["subtitleTrackBindings"]),
                },
                {1},
            )
            self.assertEqual(
                len(created["compositionVersion"]["effectTrackBindings"]), 8
            )
            all_bindings = [
                item
                for field in (
                    "videoTrackBindings",
                    "audioTrackBindings",
                    "subtitleTrackBindings",
                    "effectTrackBindings",
                )
                for item in created["compositionVersion"][field]
            ]
            self.assertTrue(
                all(item["sourceAssetVersions"] for item in all_bindings)
            )
            self.assertTrue(
                all(
                    isinstance(source["version"], int)
                    and source["version"] > 0
                    for item in all_bindings
                    for source in item["sourceAssetVersions"]
                )
            )
            self.assertIsNotNone(
                created["compositionVersion"]["audioTrackBindings"][0][
                    "technicalValidationBinding"
                ]
            )
            subtitle_binding = created["compositionVersion"][
                "subtitleTrackBindings"
            ][0]
            self.assertIsNotNone(subtitle_binding["audioCueBinding"])
            self.assertIsNotNone(subtitle_binding["stemBinding"])
            self.assertEqual(
                {
                    item["effectBinding"]["effectKind"]
                    for item in created["compositionVersion"][
                        "effectTrackBindings"
                    ]
                },
                {
                    "GLYPH_REVEAL",
                    "SCRATCH_REVEAL",
                    "LOCAL_EXPOSURE",
                    "FLAME_EXTINGUISH",
                    "SMOKE",
                    "NAMEPLATE_TEXT",
                    "FACE_MARK_COMPENSATION",
                    "DISTANCE_STATE_TRANSITION",
                },
            )
            self.assertFalse(_contains_forbidden_fact(created["composition"]))
            self.assertFalse(
                _contains_forbidden_fact(created["compositionVersion"])
            )
            self.assertFalse(_contains_forbidden_fact(created["renderManifest"]))

            exact_replay = service.create_composition_render_manifest(
                micro_command
            )
            self.assertTrue(exact_replay["idempotentReplay"])
            self.assertEqual(
                exact_replay["renderManifest"], created["renderManifest"]
            )
            changed_replay = deepcopy(micro_command)
            changed_replay["renderProfile"] = _profile(704, 1280)
            with self.assertRaises(IdempotencyConflictError):
                service.create_composition_render_manifest(changed_replay)
            raw_client_authority = deepcopy(micro_command)
            raw_client_authority["tracks"] = current["tracks"]
            with self.assertRaises(EpisodeProductionError):
                service.create_composition_render_manifest(raw_client_authority)

            required_profiles = []
            for width, height in ((704, 1280), (720, 1280), (1080, 1920)):
                mode = "BURN_IN" if width == 1080 else "SIDECAR"
                response = service.create_composition_render_manifest(
                    _command(
                        run,
                        timeline,
                        slug=f"profile-{width}x{height}",
                        profile=_profile(
                            width,
                            height,
                            subtitle_mode=mode,
                            font=(font_fixture.asset if mode == "BURN_IN" else None),
                        ),
                    )
                )
                required_profiles.append(response["renderManifest"])
                self.assertEqual(
                    response["compositionVersion"]["payloadDigest"],
                    created["compositionVersion"]["payloadDigest"],
                )
            self.assertEqual(
                {
                    (
                        item["outputProfile"]["width"],
                        item["outputProfile"]["height"],
                    )
                    for item in required_profiles
                },
                {(704, 1280), (720, 1280), (1080, 1920)},
            )

            record_kinds = [
                item["recordKind"]
                for item in repository.list_records(
                    run["workspaceRef"], run["productionRunRef"]
                )
            ]
            self.assertEqual(record_kinds.count("Composition"), 1)
            self.assertEqual(record_kinds.count("CompositionVersion"), 1)
            self.assertEqual(record_kinds.count("RenderManifest"), 4)
            self.assertFalse(
                {
                    "RenderCandidate",
                    "ExportCandidate",
                    "EpisodeMaster",
                    "ExportArtifact",
                }.intersection(record_kinds)
            )
            self.assertEqual(
                service.get_timeline(
                    run["workspaceRef"], run["productionRunRef"]
                )["timelineVersion"],
                timeline,
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
            restart_replay = restarted.create_composition_render_manifest(
                micro_command
            )
            self.assertTrue(restart_replay["idempotentReplay"])
            self.assertEqual(
                restart_replay["compositionVersion"],
                created["compositionVersion"],
            )
            with self.assertRaises(EpisodeProductionError):
                restarted.get_composition_render_manifest(
                    "foreign-workspace", run["productionRunRef"]
                )

            current_media = restarted._test_e3_media_authority
            original_base = deepcopy(current_media.base)
            current_media.base["payloadDigest"] = "0" * 64
            with self.assertRaises(EpisodeProductionError):
                restarted.get_composition_render_manifest(
                    run["workspaceRef"],
                    run["productionRunRef"],
                    render_manifest_ref=created["renderManifest"][
                        "renderManifestRef"
                    ],
                )
            current_media.base = original_base

            stale_effect_path = root / "stale-effect.sqlite3"
            shutil.copy2(evidence_path, stale_effect_path)
            with sqlite3.connect(stale_effect_path) as connection:
                rowid, payload_json = connection.execute(
                    "SELECT rowid,payload_json FROM v5_episode_production_records "
                    "WHERE record_kind='ScratchLightResult'"
                ).fetchone()
                payload = json.loads(payload_json)
                payload["state"] = "TAMPERED"
                connection.execute(
                    "UPDATE v5_episode_production_records SET payload_json=? "
                    "WHERE rowid=?",
                    (
                        json.dumps(
                            payload,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        rowid,
                    ),
                )
                connection.commit()
            with self.assertRaises(RepositoryUnavailableError):
                SqliteEpisodeProductionEvidenceAdapter(
                    stale_effect_path, initialize_if_missing=False
                )

            video_clip = next(
                item
                for item in current["clips"]
                if item["clipKind"] == "VIDEO"
            )
            restarted.edit_timeline(
                {
                    "workspaceRef": run["workspaceRef"],
                    "productionRunRef": run["productionRunRef"],
                    "operationRef": "m13-r1a-stale-timeline",
                    "idempotencyKey": "m13-r1a-stale-timeline-key",
                    "expectedRunVersion": 1,
                    "parentTimelineVersionRef": timeline[
                        "timelineVersionRef"
                    ],
                    "parentTimelineVersionDigest": timeline["payloadDigest"],
                    "editCommand": {
                        "operation": "DISABLE_CLIP",
                        "arguments": {"clipRef": video_clip["clipRef"]},
                    },
                }
            )
            with self.assertRaises(StaleInputError):
                restarted.get_composition_render_manifest(
                    run["workspaceRef"],
                    run["productionRunRef"],
                    render_manifest_ref=created["renderManifest"][
                        "renderManifestRef"
                    ],
                )


if __name__ == "__main__":
    unittest.main()
