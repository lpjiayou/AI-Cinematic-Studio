from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import shutil
import sqlite3
import tempfile
import unittest

from services.v3_render_core import decoded_frame_pixel_digest_metadata
from services.v4_platform import V4CompositionExecutor
from services.v4_platform.masked_surface_effects import V4MaskedSurfaceEffectExecutor
from services.v5_core_os.episode_production.delivery import (
    COMPOSITION_GATE,
    M13_EFFECT_COMPOSITION_GATE,
    QC_GATE,
    K2DeliveryService,
    RejectingApprovalAuthority,
)
from services.v5_core_os.episode_production.deterministic_effects import (
    LOCAL_EXPOSURE,
    SCRATCH_REVEAL,
    append_deterministic_effect_result_chain,
    build_deterministic_effect_result,
    build_local_exposure_requirement,
    build_masked_surface_execution_request,
    build_scratch_light_requirement,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    GateAppend,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
    EpisodeProductionPublicError,
)
from tests.contract.test_m13_deterministic_effects_contract import (
    _command as effect_command,
)
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
)
from tests.contract.test_m13_timeline_editing_contract import clip_command
from tests.integration.test_m12_m13_minimal_preview import (
    CREATED_AT,
    _CurrentMedia,
    _source_template,
)


def _sealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _fact(kind: str, reference: str, payload: dict) -> EvidenceFact:
    return EvidenceFact(kind, reference, 1, payload, payload["payloadDigest"])


def _authority(inputs) -> tuple[dict, dict, dict]:
    cue = inputs.audio["cue"].as_dict()
    script_ref = cue["scriptVersionRef"]
    script_digest = cue["scriptVersionDigest"]
    run = _sealed(
        {
            **inputs.run,
            "scriptVersionRef": script_ref,
            "upstreamSnapshot": {
                "script": {
                    "scriptVersionRef": script_ref,
                    "versionDigest": script_digest,
                }
            },
        }
    )
    storyboard = _sealed(
        {
            "schemaVersion": "test.m13-e1-storyboard.v1",
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "rootPayloadDigest": run["payloadDigest"],
            "storyboardVersionRef": "m13-e1-preview-storyboard-v1",
            "scriptVersionRef": script_ref,
            "scriptVersionDigest": script_digest,
        }
    )
    shot = {
        "schemaVersion": "test.m13-e1-creative-shot.v1",
        "creativeShotRef": inputs.base["creativeShotRef"],
        "creativeShotVersionRef": inputs.base["creativeShotVersionRef"],
        "payloadDigest": inputs.base["creativeShotDigest"],
    }
    graph = _sealed(
        {
            "schemaVersion": "test.m13-e1-shot-graph.v1",
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "rootPayloadDigest": run["payloadDigest"],
            "executableShotGraphVersionRef": "m13-e1-preview-shot-graph-v1",
            "scriptVersionRef": script_ref,
            "scriptVersionDigest": script_digest,
            "storyboardDigest": storyboard["payloadDigest"],
            "shots": [shot],
            "output": {
                "width": 64,
                "height": 64,
                "frameRate": 24,
                "totalFrames": 49,
            },
        }
    )
    return run, storyboard, graph


def _seed_real_video_ready(
    repository, run: dict, storyboard: dict, graph: dict
) -> None:
    authority = _sealed(
        {"schemaVersion": "test.m13-e1-authority.v1", "authorityRef": "e1-authority"}
    )
    script = _sealed(
        {
            "schemaVersion": "test.m13-e1-script.v1",
            "scriptVersionRef": run["scriptVersionRef"],
            "scriptVersionDigest": run["upstreamSnapshot"]["script"]["versionDigest"],
        }
    )
    assets = _sealed(
        {"schemaVersion": "test.m13-e1-assets.v1", "assetPlanRef": "e1-assets"}
    )
    media = _sealed(
        {"schemaVersion": "test.m13-e1-media.v1", "mediaRef": "e1-media"}
    )
    handoffs = {
        slug: _sealed(
            {
                "schemaVersion": f"test.m13-e1-{slug}.v1",
                "technicalHandoffRef": f"e1-{slug}",
            }
        )
        for slug in (
            "preview-handoff",
            "quality-handoff",
            "real-image-plan-handoff",
            "real-image-handoff",
            "real-video-plan-handoff",
            "real-video-admission",
        )
    }
    steps = (
        (
            "E1_AUTHORITY",
            "ROOTS_READY",
            "AUTHORITY_READY",
            (_fact("AuthorityIdentity", authority["authorityRef"], authority),),
        ),
        (
            "E1_SCRIPT",
            "AUTHORITY_READY",
            "SCRIPT_VALIDATED",
            (_fact("ScriptVersion", script["scriptVersionRef"], script),),
        ),
        (
            "G3_SHOT_GRAPH",
            "SCRIPT_VALIDATED",
            "SHOTS_COMPILED",
            (
                _fact("StoryboardVersion", storyboard["storyboardVersionRef"], storyboard),
                _fact(
                    "ExecutableShotGraph",
                    graph["executableShotGraphVersionRef"],
                    graph,
                ),
            ),
        ),
        (
            "E1_ASSETS",
            "SHOTS_COMPILED",
            "ASSETS_READY",
            (_fact("TechnicalAssetPlan", assets["assetPlanRef"], assets),),
        ),
        (
            "E1_MEDIA",
            "ASSETS_READY",
            "MEDIA_READY",
            (_fact("TechnicalMedia", media["mediaRef"], media),),
        ),
        (
            COMPOSITION_GATE,
            "MEDIA_READY",
            "PREVIEW_READY",
            (
                _fact(
                    "TechnicalPreviewHandoff",
                    handoffs["preview-handoff"]["technicalHandoffRef"],
                    handoffs["preview-handoff"],
                ),
            ),
        ),
        (
            QC_GATE,
            "PREVIEW_READY",
            "QC_READY",
            (
                _fact(
                    "TechnicalQualityHandoff",
                    handoffs["quality-handoff"]["technicalHandoffRef"],
                    handoffs["quality-handoff"],
                ),
            ),
        ),
        (
            "E1_TECHNICAL_REAL_IMAGE_PLAN_HANDOFF",
            "QC_READY",
            "REAL_IMAGE_PLAN_READY",
            (
                _fact(
                    "TechnicalRealImagePlanHandoff",
                    handoffs["real-image-plan-handoff"]["technicalHandoffRef"],
                    handoffs["real-image-plan-handoff"],
                ),
            ),
        ),
        (
            "E1_TECHNICAL_REAL_IMAGE_HANDOFF",
            "REAL_IMAGE_PLAN_READY",
            "REAL_IMAGE_READY",
            (
                _fact(
                    "TechnicalRealImageHandoff",
                    handoffs["real-image-handoff"]["technicalHandoffRef"],
                    handoffs["real-image-handoff"],
                ),
            ),
        ),
        (
            "E1_TECHNICAL_REAL_VIDEO_PLAN_HANDOFF",
            "REAL_IMAGE_READY",
            "REAL_VIDEO_PLAN_READY",
            (
                _fact(
                    "TechnicalRealVideoPlanHandoff",
                    handoffs["real-video-plan-handoff"]["technicalHandoffRef"],
                    handoffs["real-video-plan-handoff"],
                ),
            ),
        ),
        (
            "E1_TECHNICAL_REAL_VIDEO_ADMISSION",
            "REAL_VIDEO_PLAN_READY",
            "REAL_VIDEO_READY",
            (
                _fact(
                    "TechnicalRealVideoAdmission",
                    handoffs["real-video-admission"]["technicalHandoffRef"],
                    handoffs["real-video-admission"],
                ),
            ),
        ),
    )
    for ordinal, (name, from_state, to_state, facts) in enumerate(steps, 1):
        repository.append_gate(
            GateAppend(
                run["workspaceRef"],
                run["productionRunRef"],
                name,
                f"m13-e1-preview-seed-{ordinal}",
                run["payloadDigest"],
                _digest({"seed": ordinal}),
                from_state,
                to_state,
                CREATED_AT,
                facts,
            )
        )


class _RealVideoAuthority:
    def __init__(self, inputs) -> None:
        self.inputs = inputs
        self.calls = []

    def get_revision_bundle(
        self, workspace_ref: str, run_ref: str, *, evidence_snapshot=None
    ) -> dict:
        if (workspace_ref, run_ref) != (
            self.inputs.run["workspaceRef"],
            self.inputs.run["productionRunRef"],
        ):
            raise AssertionError("real-video fixture scope drifted")
        self.calls.append(evidence_snapshot)
        return {
            "videoAssetVersions": [deepcopy(self.inputs.base)],
            "videoLineageState": {"state": "CURRENT"},
            "publicationAllowed": False,
        }


def _media(inputs, run: dict, graph: dict, *, allow_legacy_current: bool):
    current = _CurrentMedia(inputs)
    current._inputs = type(inputs)(
        audio=inputs.audio,
        base=inputs.base,
        masks=inputs.masks,
        inspection=inputs.inspection,
        requirement=inputs.requirement,
        run=run,
    )
    current.verify_run_current = current.get_run
    current.allow_legacy_current = allow_legacy_current

    def verify_media_current(workspace_ref: str, run_ref: str) -> dict:
        if not current.allow_legacy_current:
            raise AssertionError(
                "legacy current-media reader was used for the Glyph base"
            )
        current._check_scope(workspace_ref, run_ref)
        return {
            "root": deepcopy(run),
            "executableShotGraph": deepcopy(graph),
            "mediaManifest": _sealed(
                {
                    "schemaVersion": "test.m13-e1-media-manifest.v1",
                    "mediaManifestRef": "m13-e1-preview-media-manifest",
                }
            ),
            "creativeShotVersions": [],
            "assetVersions": [deepcopy(inputs.base)],
        }

    current.verify_media_current = verify_media_current
    return current


def _service(
    root: Path,
    repository,
    inputs,
    run: dict,
    graph: dict,
    *,
    allow_legacy_current: bool = False,
) -> K2DeliveryService:
    authority = _RealVideoAuthority(inputs)
    service = K2DeliveryService(
        _media(
            inputs,
            run,
            graph,
            allow_legacy_current=allow_legacy_current,
        ),
        repository,
        V4CompositionExecutor.from_artifact_root(root),
        RejectingApprovalAuthority(),
        ref_factory=lambda prefix: f"{prefix}-m13-e1-preview",
        clock=lambda: CREATED_AT,
        real_video_authority=authority,
        glyph_inspection_adapter=DigestPinnedBasePlateGlyphInspectionAdapter(
            InMemoryInspectionEvidenceStore(inputs.inspection)
        ),
    )
    service._test_real_video_authority = authority
    return service


def _public(service: K2DeliveryService) -> EpisodeProductionPublicBoundary:
    boundary = object.__new__(EpisodeProductionPublicBoundary)
    setattr(boundary, "_EpisodeProductionPublicBoundary__delivery", service)
    return boundary


def _register_inputs(service: K2DeliveryService, inputs) -> dict:
    return service.record_m12_m13_inputs(
        workspace_ref=inputs.run["workspaceRef"],
        production_run_ref=inputs.run["productionRunRef"],
        idempotency_key="m13-e1-preview-inputs",
        audio_input_bindings=(inputs.audio["binding"],),
        audio_cues=(inputs.audio["cue"],),
        audio_stem_set=inputs.audio["stemSet"],
        glyph_reveal_requirement=inputs.requirement,
        mask_assets=inputs.masks,
    )


def _append_effects(root: Path, repository, inputs) -> list:
    base = inputs.base
    decoded = decoded_frame_pixel_digest_metadata(root / base["storageKey"])
    resolved_base = {
        "assetVersionRef": base["assetVersionRef"],
        "assetVersionDigest": base["payloadDigest"],
        "storageKey": base["storageKey"],
        "fileDigest": f"sha256:{base['sha256']}",
        "pixelDigest": decoded["decodedFramePixelDigest"],
        "pixelDigestSpec": decoded["decodedFramePixelDigestSpec"],
        "width": 64,
        "height": 64,
        "frameCount": 49,
        "frameRate": 24,
        "pixelFormat": "yuv420p",
    }
    executor = V4MaskedSurfaceEffectExecutor.from_artifact_root(root)
    chains = []
    specs = (
        (SCRATCH_REVEAL, build_scratch_light_requirement, 2, inputs.masks[0]),
        (LOCAL_EXPOSURE, build_local_exposure_requirement, 3, inputs.masks[1]),
    )
    for ordinal, (mode, builder, layer, mask) in enumerate(specs, 1):
        command = effect_command(mode)
        command.update(
            {
                "workspaceRef": inputs.run["workspaceRef"],
                "productionRunRef": inputs.run["productionRunRef"],
                "requirementRef": f"m13-e1-preview-{mode.lower()}-requirement",
                "targetShotRef": base["creativeShotRef"],
                "targetShotVersionRef": base["creativeShotVersionRef"],
                "targetShotVersionDigest": base["creativeShotDigest"],
                "basePlateAssetVersionRef": base["assetVersionRef"],
                "basePlateAssetVersionDigest": base["payloadDigest"],
                "basePlateFileDigest": f"sha256:{base['sha256']}",
                "basePlatePixelDigest": decoded["decodedFramePixelDigest"],
                "maskAssetVersionRef": mask["assetVersionRef"],
                "maskAssetVersionDigest": mask["payloadDigest"],
                "maskFileDigest": f"sha256:{mask['sha256']}",
                "maskPixelDigest": mask["pixelDigest"],
                "frameRangeStartInclusive": 12,
                "frameRangeEndExclusive": 30,
                "explicitSchedule": [
                    {
                        "startFrameInclusive": 12,
                        "endFrameExclusive": 30,
                        "enabled": True,
                        "interpolation": "STEP",
                    }
                ],
                "trajectoryKeyframes": [
                    {
                        "frame": 12,
                        "xPermille": 250,
                        "yPermille": 300,
                        "interpolation": "LINEAR",
                    },
                    {
                        "frame": 29,
                        "xPermille": 750,
                        "yPermille": 300,
                        "interpolation": "EASE_IN_OUT",
                    },
                ],
                "intensityCurve": [
                    {"frame": 12, "valuePermille": 0, "interpolation": "LINEAR"},
                    {"frame": 29, "valuePermille": 900, "interpolation": "EASE_OUT"},
                ],
                "exposureCurve": [
                    {"frame": 12, "valueMilliStops": 0, "interpolation": "LINEAR"},
                    {"frame": 29, "valueMilliStops": 500, "interpolation": "EASE_OUT"},
                ],
                "layer": layer,
            }
        )
        requirement = builder(command)
        request = build_masked_surface_execution_request(requirement)
        resolved_mask = {
            "assetVersionRef": mask["assetVersionRef"],
            "assetVersionDigest": mask["payloadDigest"],
            "storageKey": mask["storageKey"],
            "fileDigest": f"sha256:{mask['sha256']}",
            "pixelDigest": mask["pixelDigest"],
            "pixelDigestSpec": mask["pixelDigestSpec"],
            "pixelMode": mask["pixelMode"],
            "width": mask["width"],
            "height": mask["height"],
        }
        evidence = executor.execute(
            request.as_dict(),
            resolved_asset_versions={
                base["assetVersionRef"]: resolved_base,
                mask["assetVersionRef"]: resolved_mask,
            },
        )
        result = build_deterministic_effect_result(
            requirement=requirement,
            execution_request=request,
            evidence_bindings=evidence["evidenceBindings"],
        )
        chain, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifactEvidence"],
            runtime_evidence=evidence["runtimeEvidence"],
            result=result,
            idempotency_key=f"m13-e1-preview-effect-chain-{ordinal}",
            created_at=CREATED_AT,
            expected_record_journal_head=repository.record_journal_head(
                inputs.run["workspaceRef"], inputs.run["productionRunRef"]
            ),
        )
        if replayed:
            raise AssertionError("new effect chain unexpectedly replayed")
        chains.append(chain)
    return chains


def _insert_and_bind_timeline(service, inputs, run: dict, chains: list) -> dict:
    workspace = run["workspaceRef"]
    run_ref = run["productionRunRef"]
    created = service.create_timeline(
        {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "operationRef": "m13-e1-preview-create-timeline",
            "idempotencyKey": "m13-e1-preview-create-timeline-key",
            "expectedRunVersion": 1,
        }
    )
    tracks = {item["trackKind"]: item["trackRef"] for item in created["tracks"]}

    def edit(parent: dict, slug: str, operation: str, arguments: dict) -> dict:
        return service.edit_timeline(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "operationRef": f"m13-e1-preview-{slug}",
                "idempotencyKey": f"m13-e1-preview-{slug}-key",
                "expectedRunVersion": 1,
                "parentTimelineVersionRef": parent["timelineVersionRef"],
                "parentTimelineVersionDigest": parent["payloadDigest"],
                "editCommand": {"operation": operation, "arguments": arguments},
            }
        )

    base = inputs.base
    video = clip_command("VIDEO", clip_ref="m13-e1-preview-clip-01-video")
    video.pop("timelineVersionRef")
    video.update(
        {
            "trackRef": tracks["VIDEO"],
            "timelineEndFrameExclusive": 49,
            "sourceBinding": {
                "assetVersionRef": base["assetVersionRef"],
                "assetVersionDigest": base["payloadDigest"],
                "sourceInFrameInclusive": 0,
                "sourceOutFrameExclusive": 49,
            },
        }
    )
    current = edit(created["timelineVersion"], "insert-video", "INSERT_CLIP", {"clip": video})

    binding = inputs.audio["binding"].as_dict()
    audio = clip_command("AUDIO", clip_ref="m13-e1-preview-clip-02-audio")
    audio.pop("timelineVersionRef")
    audio["trackRef"] = tracks["AUDIO"]
    audio["sourceBinding"].update(
        {
            "audioAssetVersionRef": binding["assetVersionRef"],
            "audioAssetVersionDigest": binding["assetVersionDigest"],
            "stemMemberRef": inputs.audio["member"]["stemMemberRef"],
        }
    )
    current = edit(current["timelineVersion"], "insert-audio", "INSERT_CLIP", {"clip": audio})

    cue = inputs.audio["cue"].as_dict()
    subtitle = clip_command(
        "SUBTITLE", clip_ref="m13-e1-preview-clip-03-subtitle"
    )
    subtitle.pop("timelineVersionRef")
    subtitle["trackRef"] = tracks["SUBTITLE"]
    subtitle["sourceBinding"] = {
        "audioCueRef": cue["cueVersionRef"],
        "audioCueDigest": cue["payloadDigest"],
        "scriptVersionRef": cue["scriptVersionRef"],
        "scriptVersionDigest": cue["scriptVersionDigest"],
        "textStart": cue["subtitleTimingReference"]["textRangeStart"],
        "textEndExclusive": cue["subtitleTimingReference"]["textRangeEndExclusive"],
        "textDigest": cue["subtitleTimingReference"]["textDigest"],
        "language": cue["subtitleTimingReference"]["language"],
        "wordTiming": [
            {
                "wordRef": word["wordRef"],
                "textStart": word["textRangeStart"],
                "textEndExclusive": word["textRangeEndExclusive"],
                "timelineStartFrameInclusive": word["sourceStartSample"] * 24 // 48_000,
                "timelineEndFrameExclusive": word["sourceEndSample"] * 24 // 48_000,
                "textDigest": word["textDigest"],
            }
            for word in cue["wordTimings"]
        ],
    }
    current = edit(current["timelineVersion"], "insert-subtitle", "INSERT_CLIP", {"clip": subtitle})

    glyph = clip_command("EFFECT", clip_ref="m13-e1-preview-clip-04-glyph")
    glyph.pop("timelineVersionRef")
    glyph.update(
        {
            "trackRef": tracks["EFFECT"],
            "timelineStartFrameInclusive": 12,
            "timelineEndFrameExclusive": 30,
            "sourceBinding": {
                "effectRequirementRef": inputs.requirement.requirement_ref,
                "effectRequirementDigest": inputs.requirement.payload_digest,
                "effectKind": "GLYPH_REVEAL",
                "effectResultRef": None,
                "layer": 1,
                "blendMode": "GRAZING_LIGHT_RELIEF",
            },
        }
    )
    current = edit(current["timelineVersion"], "insert-glyph", "INSERT_CLIP", {"clip": glyph})

    for ordinal, chain in enumerate(chains, 1):
        requirement = chain.requirement.as_dict()
        result = chain.result.as_dict()
        effect = clip_command(
            "EFFECT", clip_ref=f"m13-e1-preview-clip-0{ordinal + 4}-effect"
        )
        effect.pop("timelineVersionRef")
        effect.update(
            {
                "trackRef": tracks["EFFECT"],
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
        current = edit(
            current["timelineVersion"],
            f"insert-effect-{ordinal}",
            "INSERT_CLIP",
            {"clip": effect},
        )
        current = edit(
            current["timelineVersion"],
            f"bind-effect-{ordinal}",
            "BIND_EFFECT_RESULT",
            {
                "clipRef": effect["clipRef"],
                "effectResultRef": result["resultRef"],
                "effectResultDigest": result["payloadDigest"],
            },
        )
    return current


def _contains_private_key(value) -> bool:
    private_fragments = ("storage", "path", "filter", "argv")
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.replace("_", "").replace("-", "").lower()
            if normalized == "executionresult" or any(
                fragment in normalized for fragment in private_fragments
            ):
                return True
            if _contains_private_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_private_key(item) for item in value)
    return False


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E1TimelineV3PreviewIntegrationTests(unittest.TestCase):
    def test_preview_is_exact_restart_safe_redacted_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path = root / "evidence.sqlite3"
            artifact_root = root / "artifacts"
            inputs = _source_template(artifact_root)
            run, storyboard, graph = _authority(inputs)
            inputs = type(inputs)(
                audio=inputs.audio,
                base=inputs.base,
                masks=inputs.masks,
                inspection=inputs.inspection,
                requirement=inputs.requirement,
                run=run,
            )
            repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=True
            )
            with sqlite3.connect(evidence_path) as connection:
                tables_before = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            _seed_real_video_ready(repository, run, storyboard, graph)
            service = _service(artifact_root, repository, inputs, run, graph)
            _register_inputs(service, inputs)
            chains = _append_effects(artifact_root, repository, inputs)
            current = _insert_and_bind_timeline(service, inputs, run, chains)
            records_before = repository.list_records(run["workspaceRef"], run["productionRunRef"])
            timeline_records_before = sum(
                item["recordKind"].startswith("Timeline") for item in records_before
            )
            snapshot_before = repository.read_snapshot(
                run["workspaceRef"], run["productionRunRef"]
            )
            historical_composition_gate = repository.get_gate(
                run["workspaceRef"], run["productionRunRef"], COMPOSITION_GATE
            )
            historical_qc_gate = repository.get_gate(
                run["workspaceRef"], run["productionRunRef"], QC_GATE
            )
            self.assertIsNotNone(historical_composition_gate)
            self.assertIsNotNone(historical_qc_gate)
            timeline_facts_before = sum(
                fact["factKind"].startswith("Timeline")
                for gate in snapshot_before.gates
                for fact in gate["facts"]
            )
            command = {
                "workspaceRef": run["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "operationRef": "m13-e1-preview-compose",
                "idempotencyKey": "m13-e1-preview-compose-key",
                "expectedRunVersion": 1,
                "expectedEvidenceRevision": current["evidenceRevision"],
                "timelineVersionRef": current["timelineVersion"]["timelineVersionRef"],
                "timelineVersionDigest": current["timelineVersion"]["payloadDigest"],
            }

            internal = service.compose_and_qc(command)
            self.assertTrue(service._test_real_video_authority.calls)
            self.assertTrue(
                all(
                    snapshot is not None
                    for snapshot in service._test_real_video_authority.calls
                )
            )
            self.assertEqual(internal["state"], "REAL_PREVIEW_READY")
            self.assertEqual(
                set(internal),
                {
                    "state",
                    "timelineVersion",
                    "compositionResult",
                    "previewCandidate",
                    "evidenceRevision",
                    "idempotentReplay",
                },
            )
            self.assertEqual(
                internal["timelineVersion"]["payloadDigest"],
                current["timelineVersion"]["payloadDigest"],
            )
            bindings = internal["previewCandidate"]["effectResultBindings"]
            self.assertEqual(
                [item["effectMode"] for item in bindings],
                [SCRATCH_REVEAL, LOCAL_EXPOSURE],
            )
            self.assertEqual(
                [item["resultDigest"] for item in bindings],
                [chain.result.payload_digest for chain in chains],
            )
            self.assertEqual(
                [item["resultRef"] for item in bindings],
                [chain.result.result_ref for chain in chains],
            )
            self.assertEqual(
                internal["compositionResult"]["effectResultBindings"],
                bindings,
            )
            self.assertEqual(
                internal["previewCandidate"]["glyphRequirementBinding"]["requirementDigest"],
                inputs.requirement.payload_digest,
            )
            self.assertEqual(
                internal["compositionResult"]["glyphRequirementBinding"],
                internal["previewCandidate"]["glyphRequirementBinding"],
            )
            self.assertEqual(
                internal["compositionResult"]["effectBindingsDigest"],
                internal["previewCandidate"]["effectBindingsDigest"],
            )

            public = _public(service)
            public_result = public.compose_and_qc(command)
            self.assertTrue(public_result["idempotentReplay"])
            self.assertFalse(_contains_private_key(public_result))
            self.assertNotIn("outputStorageKey", public_result["compositionResult"])
            bundle = public.get_preview_bundle(run["workspaceRef"], run["productionRunRef"])
            self.assertEqual(
                set(bundle),
                {"state", "productionRunRef", "timeline", "preview", "audio", "cues", "effect"},
            )
            self.assertEqual(bundle["state"], "REAL_PREVIEW_READY")
            self.assertEqual(
                bundle["effect"]["executionOrder"],
                [SCRATCH_REVEAL, LOCAL_EXPOSURE, "GLYPH_REVEAL"],
            )
            self.assertEqual(bundle["effect"]["effectResultBindings"], bindings)
            self.assertEqual(
                bundle["effect"]["glyphRequirementBinding"],
                internal["previewCandidate"]["glyphRequirementBinding"],
            )
            self.assertEqual(
                bundle["effect"]["effectBindingsDigest"],
                internal["previewCandidate"]["effectBindingsDigest"],
            )
            self.assertFalse(_contains_private_key(bundle))
            delivery_bundle = public.get_delivery_bundle(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertNotIn("qcReport", delivery_bundle)
            self.assertEqual(
                delivery_bundle["previewCandidate"]["schemaVersion"],
                "v5.preview-candidate.v3",
            )

            records_after = repository.list_records(run["workspaceRef"], run["productionRunRef"])
            self.assertEqual(
                sum(item["recordKind"].startswith("Timeline") for item in records_after),
                timeline_records_before,
            )
            self.assertEqual(
                [
                    item["recordKind"]
                    for item in records_after
                    if item["recordKind"] in {"CompositionResult", "PreviewCandidate"}
                ],
                ["CompositionResult", "PreviewCandidate"],
            )
            forbidden = {
                "QCReport",
                "RenderCandidate",
                "EpisodeMaster",
                "ExportCandidate",
                "ExportArtifact",
            }
            self.assertFalse(forbidden.intersection(item["recordKind"] for item in records_after))
            snapshot = repository.read_snapshot(run["workspaceRef"], run["productionRunRef"])
            self.assertEqual(
                sum(
                    fact["factKind"].startswith("Timeline")
                    for gate in snapshot.gates
                    for fact in gate["facts"]
                ),
                timeline_facts_before,
            )
            self.assertEqual(
                repository.get_gate(
                    run["workspaceRef"], run["productionRunRef"], COMPOSITION_GATE
                ),
                historical_composition_gate,
            )
            self.assertEqual(
                repository.get_gate(
                    run["workspaceRef"], run["productionRunRef"], QC_GATE
                ),
                historical_qc_gate,
            )
            effect_composition_gate = repository.get_gate(
                run["workspaceRef"],
                run["productionRunRef"],
                M13_EFFECT_COMPOSITION_GATE,
            )
            self.assertIsNotNone(effect_composition_gate)
            self.assertEqual(
                (
                    effect_composition_gate["fromState"],
                    effect_composition_gate["toState"],
                ),
                ("REAL_VIDEO_READY", "REAL_PREVIEW_READY"),
            )
            self.assertEqual(
                [fact["factKind"] for fact in effect_composition_gate["facts"]],
                ["PreviewCandidate"],
            )
            self.assertFalse(
                forbidden.intersection(
                    fact["factKind"] for gate in snapshot.gates for fact in gate["facts"]
                )
            )

            restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=False
            )
            restarted = _service(artifact_root, restarted_repository, inputs, run, graph)
            replay = restarted.compose_and_qc(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["previewCandidate"], internal["previewCandidate"])

            composition_record = next(
                item
                for item in restarted_repository.list_records(
                    run["workspaceRef"], run["productionRunRef"]
                )
                if item["recordKind"] == "CompositionResult"
            )
            output = artifact_root / composition_record["payload"]["outputStorageKey"]
            original = output.read_bytes()
            output.write_bytes(original + b"tamper")
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                _public(restarted).compose_and_qc(command)
            self.assertEqual(
                (caught.exception.code, caught.exception.status),
                ("artifact_verification_failed", 422),
            )
            output.write_bytes(original)

            with sqlite3.connect(evidence_path) as connection:
                rowid, payload_json = connection.execute(
                    "SELECT rowid,payload_json FROM v5_episode_production_records "
                    "WHERE record_kind='ScratchLightResult'"
                ).fetchone()
                payload = json.loads(payload_json)
                payload["state"] = "TAMPERED"
                connection.execute(
                    "UPDATE v5_episode_production_records SET payload_json=? WHERE rowid=?",
                    (json.dumps(payload, sort_keys=True, separators=(",", ":")), rowid),
                )
                connection.commit()
            with self.assertRaises(RepositoryUnavailableError):
                SqliteEpisodeProductionEvidenceAdapter(
                    evidence_path, initialize_if_missing=False
                )

            with sqlite3.connect(evidence_path) as connection:
                tables_after = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(tables_after, tables_before)


if __name__ == "__main__":
    unittest.main()
