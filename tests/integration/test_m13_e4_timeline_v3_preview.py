from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from services.v3_render_core.masked_surface import (
    DeterministicMaskedSurfaceExecutor,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.contract.test_m13_timeline_editing_contract import clip_command
from tests.integration.m13_e3_support import (
    CREATED_AT,
    CurrentIdentityProjectionReader,
    CurrentScriptTextReader,
    admit_canonical_font,
    canonical_mark_asset,
    restart_font_authority,
)
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _contains_private_key,
    _public,
    _register_inputs,
    _seed_real_video_ready,
    _insert_and_bind_timeline,
)
from tests.integration.test_m13_e2_timeline_v3_preview import (
    _append_e2_profile,
)
from tests.integration.test_m13_e3_timeline_v3_preview import (
    EFFECT_ORDER,
    _authority,
    _edit,
    _face_command,
    _insert_and_bind_e3,
    _nameplate_command,
    _service,
    _source,
)


DISTANCE_STATE_TRANSITION = "DISTANCE_STATE_TRANSITION"
E4_EFFECT_ORDER = [*EFFECT_ORDER, DISTANCE_STATE_TRANSITION]
WIDTH = 64
HEIGHT = 64


def _distance_state_command(
    run: dict, base: dict, subject: dict, mask: dict
) -> dict:
    start, end = 0, 8
    identity_quad = [0, 0, 64, 0, 64, 64, 0, 64]
    requirement = {
        "requirementRef": "m13-e4-preview-distance-state-requirement",
        "effectMode": DISTANCE_STATE_TRANSITION,
        "targetShotRef": base["creativeShotRef"],
        "targetShotVersionRef": base["creativeShotVersionRef"],
        "targetShotVersionDigest": base["creativeShotDigest"],
        "basePlateAssetVersionRef": base["assetVersionRef"],
        "basePlateAssetVersionDigest": base["payloadDigest"],
        "targetKind": "OVERLAY_LAYER",
        "subjectLayerAssetVersionRef": subject["assetVersionRef"],
        "subjectLayerAssetVersionDigest": subject["payloadDigest"],
        "maskAssetVersionRef": mask["assetVersionRef"],
        "maskAssetVersionDigest": mask["payloadDigest"],
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "transitionMode": "SCREEN_DISTANCE_AND_VISUAL_STATE",
        "coordinateSpace": "CANVAS_PIXELS",
        "motionKeyframes": [
            {
                "frame": start,
                "x": 16,
                "y": 32,
                "scaleXNumerator": 1,
                "scaleXDenominator": 2,
                "scaleYNumerator": 1,
                "scaleYDenominator": 2,
                "rotationMilliDegrees": 0,
                "perspectiveQuad": identity_quad,
                "interpolation": "LINEAR",
            },
            {
                "frame": end - 1,
                "x": 48,
                "y": 32,
                "scaleXNumerator": 1,
                "scaleXDenominator": 2,
                "scaleYNumerator": 1,
                "scaleYDenominator": 2,
                "rotationMilliDegrees": 0,
                "perspectiveQuad": identity_quad,
                "interpolation": "LINEAR",
            },
        ],
        "distanceContract": {
            "metric": "SCREEN_EUCLIDEAN_PIXELS",
            "startValue": 48,
            "endValue": 16,
            "tolerance": 0,
            "direction": "APPROACH",
            "referenceX": 64,
            "referenceY": 32,
        },
        "startStateRef": "technical-visible",
        "endStateRef": "technical-hidden",
        "visualStateDefinitions": [
            {
                "stateRef": "technical-visible",
                "visibility": "VISIBLE",
                "opacityPermille": 1000,
                "variantAssetVersionRef": None,
                "variantAssetVersionDigest": None,
                "layer": 8,
                "blendMode": "NORMAL",
            },
            {
                "stateRef": "technical-hidden",
                "visibility": "HIDDEN",
                "opacityPermille": 0,
                "variantAssetVersionRef": None,
                "variantAssetVersionDigest": None,
                "layer": 8,
                "blendMode": "NORMAL",
            },
        ],
        "visualStateSchedule": [
            {
                "stateRef": "technical-visible",
                "startFrameInclusive": start,
                "endFrameExclusive": end - 1,
                "transitionInterpolation": "STEP",
            },
            {
                "stateRef": "technical-hidden",
                "startFrameInclusive": end - 1,
                "endFrameExclusive": end,
                "transitionInterpolation": "STEP",
            },
        ],
        "blendMode": "NORMAL",
        "layer": 8,
    }
    return {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "expectedRunVersion": 1,
        "idempotencyKey": "m13-e4-preview-distance-state-execution",
        "effectKind": DISTANCE_STATE_TRANSITION,
        "requirement": requirement,
    }


def _insert_and_bind_e4(
    service, run: dict, parent: dict, chain: dict
) -> tuple[dict, dict]:
    requirement = chain["requirement"]
    result = chain["result"]
    effect_track = next(
        item["trackRef"]
        for item in parent["tracks"]
        if item["trackKind"] == "EFFECT"
    )
    clip = clip_command(
        "EFFECT", clip_ref="m13-e4-preview-clip-11-distance-state"
    )
    clip.pop("timelineVersionRef")
    clip.update(
        {
            "trackRef": effect_track,
            "timelineStartFrameInclusive": requirement[
                "frameRangeStartInclusive"
            ],
            "timelineEndFrameExclusive": requirement[
                "frameRangeEndExclusive"
            ],
            "layer": requirement["layer"],
            "zOrder": requirement["layer"],
            "blendMode": requirement["blendMode"],
            "sourceBinding": {
                "effectRequirementRef": requirement["requirementRef"],
                "effectRequirementDigest": requirement["payloadDigest"],
                "effectKind": requirement["effectMode"],
                "effectResultRef": None,
                "effectResultDigest": None,
                "layer": requirement["layer"],
                "blendMode": requirement["blendMode"],
            },
        }
    )
    inserted, _ = _edit(
        service,
        run,
        parent,
        "insert-e4-distance-state",
        "INSERT_CLIP",
        {"clip": clip},
    )
    return _edit(
        service,
        run,
        inserted,
        "bind-e4-distance-state",
        "BIND_EFFECT_RESULT",
        {
            "clipRef": clip["clipRef"],
            "effectResultRef": result["resultRef"],
            "effectResultDigest": result["payloadDigest"],
        },
    )


def _transparent_distance_state_control(request: dict) -> dict:
    value = deepcopy(request)
    selected = [
        stage
        for stage in value["effectStages"]
        if stage["effectMode"] == DISTANCE_STATE_TRANSITION
    ]
    if len(selected) != 1:
        raise AssertionError("missing unique Distance/State Preview stage")
    stage = selected[0]
    for definition in stage["visualStateDefinitions"]:
        definition["opacityPermille"] = 0
    stage.pop("payloadDigest")
    stage["payloadDigest"] = _digest(stage)

    value["inputBindingsDigest"] = _digest(
        {
            "baseVideo": value["baseVideo"],
            "deterministicEffectRequestDigests": [
                item["payloadDigest"] for item in value["effectStages"]
            ],
            "glyphRevealRequestDigest": value["glyphStage"]["payloadDigest"],
            "effectResultBindings": value["effectResultBindings"],
            "glyphRequirementBinding": value["glyphRequirementBinding"],
            "audioMix": value["audioMix"],
            "subtitleManifest": value["subtitleManifest"],
        }
    )
    value["executionRequestRef"] = "m13-effect-preview-execution-" + _digest(
        {
            "timelineVersionRef": value["timelineVersionRef"],
            "timelineVersionDigest": value["timelineVersionDigest"],
            "inputBindingsDigest": value["inputBindingsDigest"],
            "effectBindingsDigest": value["effectBindingsDigest"],
            "outputContractDigest": _digest(value["output"]),
        }
    )[:32]
    value.pop("payloadDigest")
    value["payloadDigest"] = _digest(value)
    return value


def _frame_rgba(path: Path, frame: int) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{frame})",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    if len(result.stdout) != WIDTH * HEIGHT * 4:
        raise AssertionError("decoded Preview frame has unexpected dimensions")
    return result.stdout


def _difference_center(
    rendered: bytes, control: bytes
) -> tuple[int, tuple[int, int] | None]:
    if len(rendered) != len(control):
        raise AssertionError("Preview frames have different byte sizes")
    points: list[tuple[int, int]] = []
    for offset in range(0, len(rendered), 4):
        if rendered[offset : offset + 3] != control[offset : offset + 3]:
            pixel = offset // 4
            points.append((pixel % WIDTH, pixel // WIDTH))
    if not points:
        return 0, None
    return len(points), (
        sum(point[0] for point in points) // len(points),
        sum(point[1] for point in points) // len(points),
    )


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E4TimelineV3PreviewIntegrationTests(unittest.TestCase):
    def test_seven_stage_preview_has_real_distance_and_visual_state_pixels(
        self,
    ) -> None:
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
            service, _composition = _service(
                artifact_root=artifact_root,
                repository=repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=identity_reader,
                script_reader=script_reader,
                font_authority=font_fixture.service,
            )
            _register_inputs(service, inputs)

            smoke_layer = deepcopy(inputs.masks[3])
            smoke_layer.pop("payloadDigest")
            smoke_layer["assetVersionRef"] = (
                "asset-version-m13-e4-smoke-layer"
            )
            smoke_layer["payloadDigest"] = _digest(smoke_layer)
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=run["workspaceRef"],
                    productionRunRef=run["productionRunRef"],
                    recordKind="MaskAssetVersion",
                    recordRef=smoke_layer["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-e4-smoke-layer",
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
            e3_chains = [
                nameplate["deterministicEffect"],
                face["deterministicEffect"],
            ]
            e3_timeline, _ = _insert_and_bind_e3(
                service, run, e2_timeline, e3_chains
            )

            e4_response = service.execute_deterministic_effect(
                _distance_state_command(
                    run, inputs.base, mark, inputs.masks[4]
                )
            )
            self.assertFalse(e4_response["idempotentReplay"])
            e4_chain = e4_response["deterministicEffect"]
            self.assertEqual(
                e4_chain["result"]["state"], "COMPOSED_CANDIDATE"
            )
            current, _bind_command = _insert_and_bind_e4(
                service, run, e3_timeline, e4_chain
            )

            restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=False
            )
            restarted_identity = CurrentIdentityProjectionReader(run)
            restarted_script = CurrentScriptTextReader(run)
            restarted_font = restart_font_authority(
                run=run,
                evidence=restarted_repository,
                fixture=font_fixture,
            )
            restarted, restarted_composition = _service(
                artifact_root=artifact_root,
                repository=restarted_repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=restarted_identity,
                script_reader=restarted_script,
                font_authority=restarted_font,
            )
            restored = restarted.get_timeline(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertEqual(
                restored["timelineVersion"], current["timelineVersion"]
            )

            compose_command = {
                "workspaceRef": run["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "operationRef": "m13-e4-preview-compose",
                "idempotencyKey": "m13-e4-preview-compose-key",
                "expectedRunVersion": 1,
                "expectedEvidenceRevision": current["evidenceRevision"],
                "timelineVersionRef": current["timelineVersion"][
                    "timelineVersionRef"
                ],
                "timelineVersionDigest": current["timelineVersion"][
                    "payloadDigest"
                ],
            }
            preview = restarted.compose_and_qc(compose_command)
            self.assertFalse(preview["idempotentReplay"])
            self.assertEqual(preview["state"], "REAL_PREVIEW_READY")
            self.assertEqual(
                preview["compositionResult"]["rendererVersion"], "5"
            )
            self.assertFalse(preview["compositionResult"]["gpuUsed"])
            self.assertFalse(preview["compositionResult"]["providerUsed"])
            probe = preview["compositionResult"]["outputMediaProbe"]
            self.assertEqual(
                (probe["width"], probe["height"], probe["frameCount"]),
                (WIDTH, HEIGHT, 49),
            )
            self.assertEqual(
                probe["frameRate"], {"numerator": 24, "denominator": 1}
            )
            bindings = preview["previewCandidate"]["effectResultBindings"]
            self.assertEqual(
                [item["effectMode"] for item in bindings], E4_EFFECT_ORDER
            )
            self.assertEqual(
                bindings[-1]["resultDigest"],
                e4_chain["result"]["payloadDigest"],
            )

            self.assertEqual(len(restarted_composition.preview_v3_requests), 1)
            full_request = restarted_composition.preview_v3_requests[0]
            self.assertEqual(
                full_request["schemaVersion"],
                "v4.m13-effect-preview-execution-request.v5",
            )
            self.assertEqual(
                [item["effectMode"] for item in full_request["effectStages"]],
                E4_EFFECT_ORDER,
            )
            control = DeterministicMaskedSurfaceExecutor(
                artifact_root
            ).compose_timeline_preview_v2(
                _transparent_distance_state_control(full_request)
            )
            output_path = (
                artifact_root
                / preview["compositionResult"]["outputStorageKey"]
            )
            control_path = Path(control["internalPath"])

            frame_zero = _frame_rgba(output_path, 0)
            frame_six = _frame_rgba(output_path, 6)
            frame_seven = _frame_rgba(output_path, 7)
            control_zero = _frame_rgba(control_path, 0)
            control_six = _frame_rgba(control_path, 6)
            control_seven = _frame_rgba(control_path, 7)
            zero_count, zero_center = _difference_center(
                frame_zero, control_zero
            )
            six_count, six_center = _difference_center(
                frame_six, control_six
            )
            self.assertGreater(zero_count, 0)
            self.assertGreater(six_count, 0)
            self.assertIsNotNone(zero_center)
            self.assertIsNotNone(six_center)
            assert zero_center is not None and six_center is not None
            self.assertGreater(six_center[0] - zero_center[0], 15)
            self.assertEqual(frame_seven, control_seven)

            public_preview = _public(restarted).compose_and_qc(
                compose_command
            )
            self.assertTrue(public_preview["idempotentReplay"])
            self.assertFalse(_contains_private_key(public_preview))
            public_effects = _public(restarted).get_deterministic_effects(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertFalse(_contains_private_key(public_effects))

            records = restarted_repository.list_records(
                run["workspaceRef"], run["productionRunRef"]
            )
            forbidden = {
                "QCReport",
                "RenderCandidate",
                "ExportCandidate",
                "EpisodeMaster",
                "ExportArtifact",
            }
            self.assertFalse(
                forbidden.intersection(
                    item["recordKind"] for item in records
                )
            )


if __name__ == "__main__":
    unittest.main()
