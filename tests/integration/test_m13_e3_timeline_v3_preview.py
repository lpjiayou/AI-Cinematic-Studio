from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from services.v3_render_core import decoded_frame_pixel_digest_metadata
from services.v3_render_core.masked_surface import (
    DeterministicMaskedSurfaceExecutor,
)
from services.v4_platform import V4CompositionExecutor
from services.v4_platform.masked_surface_effects import (
    _build_effect_preview_v3_request,
)
from services.v5_core_os.episode_production.delivery import (
    K2DeliveryService,
    RejectingApprovalAuthority,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
)
from services.v5_core_os.episode_production.public import EpisodeProductionPublicError
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
)
from tests.contract.test_m13_timeline_editing_contract import clip_command
import tests.contract.test_m12_audio_timing_contract as audio_timing_fixture
import tests.integration.test_m12_m13_minimal_preview as minimal_preview_fixture
from tests.integration.m13_e3_support import (
    CHARACTER_REF,
    CREATED_AT,
    CurrentIdentityProjectionReader,
    CurrentRealMediaAuthority,
    CurrentScriptTextReader,
    SCRIPT_REF,
    SCRIPT_VERSION_DIGEST,
    SCRIPT_VERSION_REF,
    TEXT,
    admit_canonical_font,
    canonical_mark_asset,
    opacity_keyframes,
    perspective_keyframes,
    point_keyframes,
    restart_font_authority,
    rotation_keyframes,
    scale_keyframes,
)
from tests.integration.test_m12_m13_minimal_preview import _source_template
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _contains_private_key,
    _media,
    _public,
    _register_inputs,
    _seed_real_video_ready,
    _sealed,
    _insert_and_bind_timeline,
)
from tests.integration.test_m13_e2_timeline_v3_preview import (
    _append_e2_profile,
)


NAMEPLATE_TEXT = "NAMEPLATE_TEXT"
FACE_MARK_COMPENSATION = "FACE_MARK_COMPENSATION"
EFFECT_ORDER = [
    "SCRATCH_REVEAL",
    "LOCAL_EXPOSURE",
    "FLAME_EXTINGUISH",
    "SMOKE",
    NAMEPLATE_TEXT,
    FACE_MARK_COMPENSATION,
]


class _CountingComposition:
    def __init__(self, root: Path, *, font_asset_authority) -> None:
        self.delegate = V4CompositionExecutor.from_artifact_root(
            root, font_asset_authority=font_asset_authority
        )
        self.artifact_root = self.delegate.artifact_root
        self.font_asset_authority = font_asset_authority
        self.overlay_calls: list[str] = []
        self.preview_v3_requests: list[dict[str, Any]] = []

    def execute_deterministic_overlay(self, request, **kwargs):
        self.overlay_calls.append(str(request.get("effectMode")))
        return self.delegate.execute_deterministic_overlay(request, **kwargs)

    def compose_timeline_preview_v2(self, request, **kwargs):
        # Retain the exact closed request that reaches the real renderer so the
        # vertical test can run non-persistent opacity-zero controls.  Those
        # controls prove both E3 phases affect the final pixels without
        # manufacturing extra V5 executions or journal records.
        self.preview_v3_requests.append(
            _build_effect_preview_v3_request(
                request,
                kwargs["resolved_artifacts"],
                artifact_root=self.artifact_root,
                font_asset_authority=self.font_asset_authority,
            )
        )
        return self.delegate.compose_timeline_preview_v2(request, **kwargs)

    def __getattr__(self, name):
        return getattr(self.delegate, name)


def _source(artifact_root: Path) -> Any:
    """Build the existing real fixture against one digest-real ScriptVersion."""

    stack = (
        patch.object(
            audio_timing_fixture, "SCRIPT_VERSION_REF", SCRIPT_VERSION_REF
        ),
        patch.object(
            audio_timing_fixture, "SCRIPT_VERSION_DIGEST", SCRIPT_VERSION_DIGEST
        ),
        patch.object(
            minimal_preview_fixture, "SCRIPT_VERSION_REF", SCRIPT_VERSION_REF
        ),
        patch.object(
            minimal_preview_fixture,
            "SCRIPT_VERSION_DIGEST",
            SCRIPT_VERSION_DIGEST,
        ),
    )
    with stack[0], stack[1], stack[2], stack[3]:
        return _source_template(artifact_root)


def _authority(inputs) -> tuple[dict, dict, dict]:
    run = _sealed(
        {
            **inputs.run,
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "upstreamSnapshot": {
                "script": {
                    "scriptRef": SCRIPT_REF,
                    "scriptVersionRef": SCRIPT_VERSION_REF,
                    "versionDigest": SCRIPT_VERSION_DIGEST,
                }
            },
        }
    )
    storyboard = _sealed(
        {
            "schemaVersion": "test.m13-e3-storyboard.v1",
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "rootPayloadDigest": run["payloadDigest"],
            "storyboardVersionRef": "m13-e3-preview-storyboard-v1",
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
        }
    )
    shot = {
        "schemaVersion": "test.m13-e3-creative-shot.v1",
        "creativeShotRef": inputs.base["creativeShotRef"],
        "creativeShotVersionRef": inputs.base["creativeShotVersionRef"],
        "payloadDigest": inputs.base["creativeShotDigest"],
        "requiredCharacterIdentityLocks": [
            {
                "characterRef": CHARACTER_REF,
                "identityLockRef": "identity-lock-m13-e3",
                "identityLockVersionRef": "identity-lock-version-m13-e3-1",
                "identityLockDigest": "1" * 64,
            }
        ],
    }
    graph = _sealed(
        {
            "schemaVersion": "test.m13-e3-shot-graph.v1",
            "workspaceRef": run["workspaceRef"],
            "productionRunRef": run["productionRunRef"],
            "rootPayloadDigest": run["payloadDigest"],
            "executableShotGraphVersionRef": "m13-e3-preview-shot-graph-v1",
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
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


def _service(
    *,
    artifact_root: Path,
    repository,
    inputs,
    run: dict,
    graph: dict,
    mark: dict,
    identity_reader,
    script_reader,
    font_authority,
    render_toolchain_identity=None,
) -> tuple[K2DeliveryService, _CountingComposition]:
    composition = _CountingComposition(
        artifact_root, font_asset_authority=font_authority
    )
    media_authority = CurrentRealMediaAuthority(run, inputs.base, mark)
    service = K2DeliveryService(
        _media(inputs, run, graph, allow_legacy_current=False),
        repository,
        composition,
        RejectingApprovalAuthority(),
        ref_factory=lambda prefix: f"{prefix}-m13-e3-preview",
        clock=lambda: CREATED_AT,
        real_video_authority=media_authority,
        glyph_inspection_adapter=DigestPinnedBasePlateGlyphInspectionAdapter(
            InMemoryInspectionEvidenceStore(inputs.inspection)
        ),
        identity_reference_projection_reader=identity_reader,
        script_text_reader=script_reader,
        font_asset_authority=font_authority,
        render_toolchain_identity=render_toolchain_identity,
    )
    service._test_e3_media_authority = media_authority
    return service, composition


def _nameplate_command(run: dict, base: dict, font: dict) -> dict:
    start, end = 0, 8
    requirement = {
        "requirementRef": "m13-e3-nameplate-requirement",
        "effectMode": NAMEPLATE_TEXT,
        "targetShotRef": base["creativeShotRef"],
        "targetShotVersionRef": base["creativeShotVersionRef"],
        "targetShotVersionDigest": base["creativeShotDigest"],
        "basePlateAssetVersionRef": base["assetVersionRef"],
        "basePlateAssetVersionDigest": base["payloadDigest"],
        "textSourceKind": "SCRIPT_TEXT",
        "textSourceRef": SCRIPT_REF,
        "textSourceVersionRef": SCRIPT_VERSION_REF,
        "textSourceDigest": SCRIPT_VERSION_DIGEST,
        "fontAssetVersionRef": font["assetVersionRef"],
        "fontAssetVersionDigest": font["payloadDigest"],
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "layout": {
            "writingMode": "HORIZONTAL_LTR",
            "alignment": "CENTER",
            "fontSizeMilliPixels": 16_000,
            "letterSpacingMilliPixels": 0,
            "lineSpacingMilliPixels": 18_000,
            "maxWidthPixels": 60,
            "maxHeightPixels": 24,
        },
        "positionKeyframes": point_keyframes(start, end, 500, 150),
        "scaleKeyframes": scale_keyframes(start, end),
        "rotationKeyframes": rotation_keyframes(start, end),
        "perspectiveKeyframes": perspective_keyframes(start, end),
        "opacityCurve": opacity_keyframes(start, end),
        "trackingKeyframes": point_keyframes(start, end, 0, 0),
        "blendMode": "NORMAL",
        "layer": 6,
    }
    return {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "expectedRunVersion": 1,
        "idempotencyKey": "m13-e3-nameplate-execution",
        "effectKind": NAMEPLATE_TEXT,
        "requirement": requirement,
    }


def _face_command(run: dict, base: dict, mark: dict) -> dict:
    start, end = 0, 8
    requirement = {
        "requirementRef": "m13-e3-face-mark-requirement",
        "effectMode": FACE_MARK_COMPENSATION,
        "targetShotRef": base["creativeShotRef"],
        "targetShotVersionRef": base["creativeShotVersionRef"],
        "targetShotVersionDigest": base["creativeShotDigest"],
        "basePlateAssetVersionRef": base["assetVersionRef"],
        "basePlateAssetVersionDigest": base["payloadDigest"],
        "characterRef": CHARACTER_REF,
        "markType": "MOLE",
        "markAssetVersionRef": mark["assetVersionRef"],
        "markAssetVersionDigest": mark["payloadDigest"],
        "faceRegion": "LEFT_CHEEK",
        "trackingSourceKind": "EXPLICIT_KEYFRAMES",
        "trackingKeyframes": point_keyframes(start, end, 650, 600),
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "scaleKeyframes": scale_keyframes(start, end, 200),
        "rotationKeyframes": rotation_keyframes(start, end),
        "opacityCurve": opacity_keyframes(start, end),
        "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
        "blendMode": "NORMAL",
        "layer": 7,
    }
    return {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "expectedRunVersion": 1,
        "idempotencyKey": "m13-e3-face-mark-execution",
        "effectKind": FACE_MARK_COMPENSATION,
        "requirement": requirement,
    }


def _edit(service, run: dict, parent: dict, slug: str, operation: str, arguments: dict):
    command = {
        "workspaceRef": run["workspaceRef"],
        "productionRunRef": run["productionRunRef"],
        "operationRef": f"m13-e3-preview-{slug}",
        "idempotencyKey": f"m13-e3-preview-{slug}-key",
        "expectedRunVersion": 1,
        "parentTimelineVersionRef": parent["timelineVersion"]["timelineVersionRef"],
        "parentTimelineVersionDigest": parent["timelineVersion"]["payloadDigest"],
        "editCommand": {"operation": operation, "arguments": arguments},
    }
    return service.edit_timeline(command), command


def _insert_and_bind_e3(service, run: dict, parent: dict, chains: list[dict]):
    current = parent
    bind_commands = []
    effect_track = next(
        item["trackRef"] for item in current["tracks"] if item["trackKind"] == "EFFECT"
    )
    for ordinal, chain in enumerate(chains, 1):
        requirement = chain["requirement"]
        result = chain["result"]
        clip = clip_command(
            "EFFECT", clip_ref=f"m13-e3-preview-clip-{ordinal + 8:02d}-effect"
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
        current, _ = _edit(
            service,
            run,
            current,
            f"insert-e3-{ordinal}",
            "INSERT_CLIP",
            {"clip": clip},
        )
        current, bind_command = _edit(
            service,
            run,
            current,
            f"bind-e3-{ordinal}",
            "BIND_EFFECT_RESULT",
            {
                "clipRef": clip["clipRef"],
                "effectResultRef": result["resultRef"],
                "effectResultDigest": result["payloadDigest"],
            },
        )
        bind_commands.append(bind_command)
    return current, bind_commands


def _chain_record_refs(chain: dict) -> set[str]:
    return {
        chain["requirement"]["requirementRef"],
        chain["executionRequest"]["executionRequestRef"],
        chain["artifactEvidence"]["artifactEvidenceRef"],
        chain["runtimeEvidence"]["runtimeEvidenceRef"],
        chain["result"]["resultRef"],
    }


def _all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _zero_overlay_control(request: dict, effect_mode: str) -> dict:
    """Reseal one six-stage V3 request with exactly one overlay transparent."""

    value = deepcopy(request)
    selected = [
        stage for stage in value["effectStages"] if stage["effectMode"] == effect_mode
    ]
    if len(selected) != 1:
        raise AssertionError(f"missing unique {effect_mode} stage")
    stage = selected[0]
    for keyframe in stage["overlaySpec"]["opacityCurve"]:
        keyframe["valuePermille"] = 0
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


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E3TimelineV3PreviewIntegrationTests(unittest.TestCase):
    def test_six_stage_preview_is_current_repeatable_restart_safe_and_redacted(self):
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
            service, composition = _service(
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
            smoke_layer["assetVersionRef"] = "asset-version-m13-e3-smoke-layer"
            smoke_layer["payloadDigest"] = _digest(smoke_layer)
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=run["workspaceRef"],
                    productionRunRef=run["productionRunRef"],
                    recordKind="MaskAssetVersion",
                    recordRef=smoke_layer["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-e3-smoke-layer",
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
            immutable_e2_parent = deepcopy(e2_timeline)

            nameplate_command = _nameplate_command(
                run, inputs.base, font_fixture.asset
            )
            face_command = _face_command(run, inputs.base, mark)
            self.assertNotIn("resolvedText", nameplate_command["requirement"])
            self.assertFalse(
                {
                    "identityReferenceRef",
                    "identityReferenceVersionRef",
                    "identityReferenceContentDigest",
                    "identityReferenceProjectionDigest",
                    "identityLockRef",
                    "identityLockVersionRef",
                    "identityLockDigest",
                }.intersection(face_command["requirement"])
            )

            nameplate = service.execute_deterministic_effect(nameplate_command)
            face = service.execute_deterministic_effect(face_command)
            self.assertFalse(nameplate["idempotentReplay"])
            self.assertFalse(face["idempotentReplay"])
            e3_chains = [
                nameplate["deterministicEffect"],
                face["deterministicEffect"],
            ]
            self.assertEqual(
                [item["requirement"]["effectMode"] for item in e3_chains],
                [NAMEPLATE_TEXT, FACE_MARK_COMPENSATION],
            )
            for chain in e3_chains:
                self.assertEqual(chain["result"]["state"], "COMPOSED_CANDIDATE")
                self.assertEqual(
                    chain["result"]["assetAdmissionState"], "NOT_ADMITTED"
                )
                self.assertEqual(chain["result"]["masterState"], "NOT_CREATED")
                self.assertEqual(chain["result"]["exportState"], "NOT_CREATED")
                self.assertFalse(chain["result"]["publicationAllowed"])
            nameplate_requirement = e3_chains[0]["requirement"]
            face_requirement = e3_chains[1]["requirement"]
            self.assertEqual(nameplate_requirement["resolvedText"], TEXT)
            self.assertEqual(nameplate_requirement["language"], "und")
            self.assertEqual(
                nameplate_requirement["resolvedTextDigest"],
                _digest({"utf8": TEXT}),
            )
            self.assertEqual(
                nameplate_requirement["fontAssetVersionRef"],
                font_fixture.asset["assetVersionRef"],
            )
            projection = identity_reader.require_current_identity_reference_projection(
                run["workspaceRef"], run["productionRunRef"], CHARACTER_REF
            )
            self.assertEqual(
                {
                    field: face_requirement[field]
                    for field in (
                        "identityReferenceRef",
                        "identityReferenceVersionRef",
                        "identityReferenceContentDigest",
                    )
                },
                {
                    "identityReferenceRef": projection["referenceRef"],
                    "identityReferenceVersionRef": projection[
                        "referenceVersionRef"
                    ],
                    "identityReferenceContentDigest": projection[
                        "contentDigest"
                    ],
                },
            )
            self.assertEqual(
                face_requirement["identityReferenceProjectionDigest"],
                projection["projectionDigest"],
            )
            self.assertEqual(
                face_requirement["identityLockDigest"],
                projection["identityLockDigest"],
            )
            self.assertNotIn("bundleSha256", face_requirement)
            self.assertTrue(script_reader.calls)
            self.assertGreaterEqual(len(identity_reader.calls), 2)
            self.assertEqual(
                composition.overlay_calls,
                [NAMEPLATE_TEXT, FACE_MARK_COMPENSATION],
            )

            first_pixels = [
                item["result"]["outputDecodedFramePixelDigest"]
                for item in e3_chains
            ]
            nameplate_replay = service.execute_deterministic_effect(
                nameplate_command
            )
            face_replay = service.execute_deterministic_effect(face_command)
            self.assertTrue(nameplate_replay["idempotentReplay"])
            self.assertTrue(face_replay["idempotentReplay"])
            self.assertEqual(
                [
                    nameplate_replay["deterministicEffect"]["result"][
                        "outputDecodedFramePixelDigest"
                    ],
                    face_replay["deterministicEffect"]["result"][
                        "outputDecodedFramePixelDigest"
                    ],
                ],
                first_pixels,
            )
            self.assertEqual(
                composition.overlay_calls,
                [
                    NAMEPLATE_TEXT,
                    FACE_MARK_COMPENSATION,
                    NAMEPLATE_TEXT,
                    FACE_MARK_COMPENSATION,
                ],
            )

            records = repository.list_records(
                run["workspaceRef"], run["productionRunRef"]
            )
            for chain in e3_chains:
                selected = [
                    item
                    for item in records
                    if item["recordRef"] in _chain_record_refs(chain)
                ]
                self.assertEqual(len(selected), 5)
                self.assertEqual(
                    {item["recordRef"] for item in selected},
                    _chain_record_refs(chain),
                )

            current, bind_commands = _insert_and_bind_e3(
                service, run, e2_timeline, e3_chains
            )
            self.assertEqual(e2_timeline, immutable_e2_parent)
            bound_modes = [
                clip["sourceBinding"]["effectKind"]
                for clip in current["clips"]
                if clip["sourceBinding"].get("effectResultRef")
            ]
            self.assertEqual(bound_modes, EFFECT_ORDER)
            for chain in e3_chains:
                result_wire = json.dumps(
                    chain["result"], sort_keys=True, separators=(",", ":")
                )
                self.assertNotIn("timelineVersion", result_wire)
                self.assertNotIn(
                    current["timelineVersion"]["timelineVersionRef"], result_wire
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
            self.assertTrue(restarted_identity.calls)
            self.assertTrue(restarted_script.calls)
            replayed_bind = _public(restarted).edit_timeline(bind_commands[-1])
            self.assertTrue(replayed_bind["idempotentReplay"])
            changed_bind = deepcopy(bind_commands[-1])
            changed_bind["editCommand"]["arguments"][
                "effectResultDigest"
            ] = "f" * 64
            with self.assertRaises(EpisodeProductionPublicError) as conflict:
                _public(restarted).edit_timeline(changed_bind)
            self.assertEqual(
                (conflict.exception.code, conflict.exception.status),
                ("idempotency_conflict", 409),
            )

            stable_decision = deepcopy(restarted_identity.decision)
            restarted_identity.decision["approvalRef"] += "-drifted"
            with self.assertRaises(EpisodeProductionPublicError) as identity_stale:
                _public(restarted).get_timeline(
                    run["workspaceRef"], run["productionRunRef"]
                )
            self.assertEqual(identity_stale.exception.code, "stale_input")
            restarted_identity.decision = stable_decision

            stable_script = deepcopy(restarted_script.version)
            restarted_script.version["title"] = "洛阳"
            with self.assertRaises(EpisodeProductionPublicError) as script_stale:
                _public(restarted).get_timeline(
                    run["workspaceRef"], run["productionRunRef"]
                )
            self.assertEqual(script_stale.exception.code, "stale_input")
            restarted_script.version = stable_script

            mark_path = artifact_root / mark["storageKey"]
            stable_mark_bytes = mark_path.read_bytes()
            mark_path.write_bytes(stable_mark_bytes + b"tamper")
            with self.assertRaises(EpisodeProductionPublicError):
                _public(restarted).get_timeline(
                    run["workspaceRef"], run["productionRunRef"]
                )
            mark_path.write_bytes(stable_mark_bytes)

            compose_command = {
                "workspaceRef": run["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "operationRef": "m13-e3-preview-compose",
                "idempotencyKey": "m13-e3-preview-compose-key",
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
                preview["compositionResult"]["rendererVersion"], "4"
            )
            self.assertFalse(preview["compositionResult"]["gpuUsed"])
            self.assertFalse(preview["compositionResult"]["providerUsed"])
            bindings = preview["previewCandidate"]["effectResultBindings"]
            self.assertEqual(
                [item["effectMode"] for item in bindings], EFFECT_ORDER
            )
            self.assertEqual(
                [item["resultDigest"] for item in bindings[-2:]],
                [item["result"]["payloadDigest"] for item in e3_chains],
            )
            self.assertEqual(
                preview["previewCandidate"]["schemaVersion"],
                "v5.preview-candidate.v3",
            )
            output = (
                artifact_root
                / preview["compositionResult"]["outputStorageKey"]
            )
            measured = decoded_frame_pixel_digest_metadata(output)
            self.assertEqual(
                measured["decodedFramePixelDigest"],
                preview["compositionResult"]["outputDigest"][
                    "decodedFramePixelDigest"
                ],
            )
            self.assertNotIn(
                measured["decodedFramePixelDigest"],
                {
                    decoded_frame_pixel_digest_metadata(
                        artifact_root / inputs.base["storageKey"]
                    )["decodedFramePixelDigest"],
                    *first_pixels,
                },
            )
            self.assertEqual(len(restarted_composition.preview_v3_requests), 1)
            full_v3_request = restarted_composition.preview_v3_requests[0]
            self.assertEqual(
                [item["effectMode"] for item in full_v3_request["effectStages"]],
                EFFECT_ORDER,
            )
            control_executor = DeterministicMaskedSurfaceExecutor(artifact_root)
            without_nameplate = control_executor.compose_timeline_preview_v2(
                _zero_overlay_control(full_v3_request, NAMEPLATE_TEXT)
            )
            without_face = control_executor.compose_timeline_preview_v2(
                _zero_overlay_control(full_v3_request, FACE_MARK_COMPENSATION)
            )
            self.assertNotEqual(
                without_nameplate["outputDigest"]["decodedFramePixelDigest"],
                measured["decodedFramePixelDigest"],
            )
            self.assertNotEqual(
                without_face["outputDigest"]["decodedFramePixelDigest"],
                measured["decodedFramePixelDigest"],
            )

            public = _public(restarted)
            public_preview = public.compose_and_qc(compose_command)
            self.assertTrue(public_preview["idempotentReplay"])
            self.assertFalse(_contains_private_key(public_preview))
            public_effects = public.get_deterministic_effects(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertFalse(_contains_private_key(public_effects))
            private_identity = {
                "identityReferenceRef",
                "identityReferenceVersionRef",
                "identityReferenceContentDigest",
                "identityReferenceProjectionDigest",
                "identityLockRef",
                "identityLockVersionRef",
                "identityLockDigest",
            }
            self.assertFalse(private_identity.intersection(_all_keys(public_effects)))
            bundle = public.get_preview_bundle(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertEqual(
                bundle["effect"]["executionOrder"],
                [*EFFECT_ORDER, "GLYPH_REVEAL"],
            )
            self.assertFalse(_contains_private_key(bundle))

            final_records = restarted_repository.list_records(
                run["workspaceRef"], run["productionRunRef"]
            )
            forbidden = {
                "QCReport",
                "RenderCandidate",
                "EpisodeMaster",
                "ExportCandidate",
                "ExportArtifact",
            }
            self.assertFalse(
                forbidden.intersection(item["recordKind"] for item in final_records)
            )
            self.assertEqual(
                [
                    item["recordKind"]
                    for item in final_records
                    if item["recordKind"] in {"CompositionResult", "PreviewCandidate"}
                ],
                ["CompositionResult", "PreviewCandidate"],
            )

            original = output.read_bytes()
            output.write_bytes(original + b"tamper")
            with self.assertRaises(EpisodeProductionPublicError) as tampered:
                public.compose_and_qc(compose_command)
            self.assertEqual(
                (tampered.exception.code, tampered.exception.status),
                ("artifact_verification_failed", 422),
            )
            output.write_bytes(original)

            second_restart_repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=False
            )
            second_identity = CurrentIdentityProjectionReader(run)
            second_script = CurrentScriptTextReader(run)
            second_restart, _ = _service(
                artifact_root=artifact_root,
                repository=second_restart_repository,
                inputs=inputs,
                run=run,
                graph=graph,
                mark=mark,
                identity_reader=second_identity,
                script_reader=second_script,
                font_authority=restart_font_authority(
                    run=run,
                    evidence=second_restart_repository,
                    fixture=font_fixture,
                ),
            )
            final_replay = second_restart.compose_and_qc(compose_command)
            self.assertTrue(final_replay["idempotentReplay"])
            self.assertEqual(
                final_replay["previewCandidate"], preview["previewCandidate"]
            )
            self.assertEqual(
                final_replay["compositionResult"], preview["compositionResult"]
            )
            self.assertTrue(second_identity.calls)
            self.assertTrue(second_script.calls)


if __name__ == "__main__":
    unittest.main()
