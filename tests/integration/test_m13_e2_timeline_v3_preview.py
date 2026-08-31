from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from services.v3_render_core import decoded_frame_pixel_digest_metadata
from services.v4_platform.masked_surface_effects import (
    V4MaskedSurfaceEffectExecutor,
)
from services.v5_core_os.episode_production.deterministic_effects import (
    FLAME_EXTINGUISH,
    LOCAL_EXPOSURE,
    SCRATCH_REVEAL,
    SMOKE,
    append_deterministic_effect_result_chain,
    build_deterministic_effect_result,
    build_local_exposure_requirement,
    build_masked_surface_execution_request,
    build_scratch_light_requirement,
    resolve_deterministic_effect_result_chain,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicError,
)
from tests.contract.test_m13_deterministic_effects_contract import (
    _command as e1_effect_command,
)
from tests.contract.test_m13_e2_deterministic_effects_contract import (
    _flame_command,
    _local_exposure_command,
    _smoke_command,
)
from tests.integration.test_m12_m13_minimal_preview import _source_template
from tests.integration.test_m13_e1_timeline_v3_preview import (
    CREATED_AT,
    _authority,
    _contains_private_key,
    _insert_and_bind_timeline,
    _public,
    _register_inputs,
    _seed_real_video_ready,
    _service,
)


def _resolved_mask(mask: dict) -> dict:
    return {
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


def _append_e2_profile(
    root: Path, repository, service, inputs, smoke_layer: dict
) -> list:
    base = inputs.base
    workspace = inputs.run["workspaceRef"]
    run_ref = inputs.run["productionRunRef"]
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

    def exact_scope(command: dict) -> dict:
        value = deepcopy(command)
        value.update(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "targetShotRef": base["creativeShotRef"],
                "targetShotVersionRef": base["creativeShotVersionRef"],
                "targetShotVersionDigest": base["creativeShotDigest"],
                "basePlateAssetVersionRef": base["assetVersionRef"],
                "basePlateAssetVersionDigest": base["payloadDigest"],
                "basePlateFileDigest": f"sha256:{base['sha256']}",
                "basePlatePixelDigest": decoded[
                    "decodedFramePixelDigest"
                ],
            }
        )
        return value

    def exact_mask(command: dict, prefix: str, mask: dict) -> None:
        command.update(
            {
                f"{prefix}AssetVersionRef": mask["assetVersionRef"],
                f"{prefix}AssetVersionDigest": mask["payloadDigest"],
                f"{prefix}FileDigest": f"sha256:{mask['sha256']}",
                f"{prefix}PixelDigest": mask["pixelDigest"],
            }
        )

    chains = []

    scratch_command = exact_scope(e1_effect_command(SCRATCH_REVEAL))
    scratch_command.update(
        {
            "requirementRef": "m13-e2-preview-scratch-requirement",
            "layer": 2,
        }
    )
    exact_mask(scratch_command, "mask", inputs.masks[0])
    scratch = build_scratch_light_requirement(scratch_command)
    scratch_request = build_masked_surface_execution_request(scratch)
    scratch_execution = executor.execute(
        scratch_request.as_dict(),
        resolved_asset_versions={
            base["assetVersionRef"]: resolved_base,
            inputs.masks[0]["assetVersionRef"]: _resolved_mask(
                inputs.masks[0]
            ),
        },
    )
    scratch_result = build_deterministic_effect_result(
        requirement=scratch,
        execution_request=scratch_request,
        evidence_bindings=scratch_execution["evidenceBindings"],
    )
    scratch_chain, _ = append_deterministic_effect_result_chain(
        repository,
        requirement=scratch,
        execution_request=scratch_request,
        artifact_evidence=scratch_execution["artifactEvidence"],
        runtime_evidence=scratch_execution["runtimeEvidence"],
        result=scratch_result,
        idempotency_key="m13-e2-preview-scratch-chain",
        created_at=CREATED_AT,
        expected_record_journal_head=repository.record_journal_head(
            workspace, run_ref
        ),
    )
    chains.append(scratch_chain)

    local_command = exact_scope(_local_exposure_command())
    local_command["requirementRef"] = "m13-e2-preview-local-requirement"
    exact_mask(local_command, "mask", inputs.masks[1])
    local = build_local_exposure_requirement(local_command)
    local_request = build_masked_surface_execution_request(local)
    local_execution = executor.execute(
        local_request.as_dict(),
        resolved_asset_versions={
            base["assetVersionRef"]: resolved_base,
            inputs.masks[1]["assetVersionRef"]: _resolved_mask(
                inputs.masks[1]
            ),
        },
    )
    local_result = build_deterministic_effect_result(
        requirement=local,
        execution_request=local_request,
        evidence_bindings=local_execution["evidenceBindings"],
    )
    local_chain, _ = append_deterministic_effect_result_chain(
        repository,
        requirement=local,
        execution_request=local_request,
        artifact_evidence=local_execution["artifactEvidence"],
        runtime_evidence=local_execution["runtimeEvidence"],
        result=local_result,
        idempotency_key="m13-e2-preview-local-chain",
        created_at=CREATED_AT,
        expected_record_journal_head=repository.record_journal_head(
            workspace, run_ref
        ),
    )
    chains.append(local_chain)

    flame_command = exact_scope(_flame_command(local))
    flame_command["requirementRef"] = "m13-e2-preview-flame-requirement"
    flame_command["localExposureRequirementRef"] = local.requirement_ref
    flame_command["localExposureRequirementDigest"] = local.payload_digest
    exact_mask(flame_command, "flameMask", inputs.masks[1])
    flame_delivery_command = {
        "workspaceRef": workspace,
        "productionRunRef": run_ref,
        "expectedRunVersion": 1,
        "idempotencyKey": "m13-e2-preview-flame-chain",
        "effectKind": FLAME_EXTINGUISH,
        "requirement": {
            key: value
            for key, value in flame_command.items()
            if key not in {"workspaceRef", "productionRunRef"}
        },
    }
    flame_response = service.execute_deterministic_effect(
        flame_delivery_command
    )
    if flame_response["idempotentReplay"]:
        raise AssertionError("new Flame execution unexpectedly replayed")
    flame_result = flame_response["deterministicEffect"]["result"]
    flame_chain = resolve_deterministic_effect_result_chain(
        repository,
        workspace_ref=workspace,
        production_run_ref=run_ref,
        result_ref=flame_result["resultRef"],
        result_digest=flame_result["payloadDigest"],
    )
    chains.append(flame_chain)

    smoke_command = exact_scope(_smoke_command(procedural=False))
    smoke_command["requirementRef"] = "m13-e2-preview-smoke-requirement"
    exact_mask(smoke_command, "emissionMask", inputs.masks[2])
    exact_mask(smoke_command, "smokeLayer", smoke_layer)
    smoke_delivery_command = {
        "workspaceRef": workspace,
        "productionRunRef": run_ref,
        "expectedRunVersion": 1,
        "idempotencyKey": "m13-e2-preview-smoke-chain",
        "effectKind": SMOKE,
        "requirement": {
            key: value
            for key, value in smoke_command.items()
            if key not in {"workspaceRef", "productionRunRef"}
        },
    }
    smoke_response = service.execute_deterministic_effect(
        smoke_delivery_command
    )
    if smoke_response["idempotentReplay"]:
        raise AssertionError("new Smoke execution unexpectedly replayed")
    smoke_result = smoke_response["deterministicEffect"]["result"]
    smoke_chain = resolve_deterministic_effect_result_chain(
        repository,
        workspace_ref=workspace,
        production_run_ref=run_ref,
        result_ref=smoke_result["resultRef"],
        result_digest=smoke_result["payloadDigest"],
    )
    chains.append(smoke_chain)
    return chains, (flame_delivery_command, smoke_delivery_command)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E2TimelineV3PreviewIntegrationTests(unittest.TestCase):
    def test_four_stage_preview_replays_after_restart_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_root = root / "artifacts"
            evidence_path = root / "evidence.sqlite3"
            inputs = _source_template(artifact_root)
            smoke_layer = deepcopy(inputs.masks[3])
            smoke_layer.pop("payloadDigest")
            smoke_layer["assetVersionRef"] = (
                "asset-version-m13-e2-pinned-smoke-layer"
            )
            smoke_layer["payloadDigest"] = _digest(smoke_layer)
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
            _seed_real_video_ready(repository, run, storyboard, graph)
            service = _service(
                artifact_root, repository, inputs, run, graph
            )
            _register_inputs(service, inputs)
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=run["workspaceRef"],
                    productionRunRef=run["productionRunRef"],
                    recordKind="MaskAssetVersion",
                    recordRef=smoke_layer["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-e2-preview-smoke-layer",
                    requestDigest=_digest(
                        {"smokeLayer": smoke_layer["payloadDigest"]}
                    ),
                    createdAt=CREATED_AT,
                    payload=smoke_layer,
                    payloadDigest=smoke_layer["payloadDigest"],
                )
            )
            chains, effect_commands = _append_e2_profile(
                artifact_root,
                repository,
                service,
                inputs,
                smoke_layer,
            )
            current = _insert_and_bind_timeline(
                service, inputs, run, chains
            )
            parent_before = deepcopy(current)
            smoke_result = chains[-1].result.as_dict()
            smoke_clip = next(
                item
                for item in current["clips"]
                if item["sourceBinding"].get("effectResultRef")
                == smoke_result["resultRef"]
            )
            bind_replay_command = {
                "workspaceRef": run["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "operationRef": "m13-e1-preview-bind-effect-4",
                "idempotencyKey": "m13-e1-preview-bind-effect-4-key",
                "expectedRunVersion": 1,
                "parentTimelineVersionRef": current["timelineVersion"][
                    "parentTimelineVersionRef"
                ],
                "parentTimelineVersionDigest": current["timelineVersion"][
                    "parentTimelineVersionDigest"
                ],
                "editCommand": {
                    "operation": "BIND_EFFECT_RESULT",
                    "arguments": {
                        "clipRef": smoke_clip["clipRef"],
                        "effectResultRef": smoke_result["resultRef"],
                        "effectResultDigest": smoke_result[
                            "payloadDigest"
                        ],
                    },
                },
            }
            binding_restart_repository = (
                SqliteEpisodeProductionEvidenceAdapter(
                    evidence_path, initialize_if_missing=False
                )
            )
            binding_restarted = _service(
                artifact_root,
                binding_restart_repository,
                inputs,
                run,
                graph,
            )
            bind_replay = _public(binding_restarted).edit_timeline(
                bind_replay_command
            )
            self.assertTrue(bind_replay["idempotentReplay"])
            self.assertEqual(
                bind_replay["timelineVersion"], current["timelineVersion"]
            )
            changed_bind_replay = deepcopy(bind_replay_command)
            changed_bind_replay["editCommand"]["arguments"][
                "effectResultDigest"
            ] = "f" * 64
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                _public(binding_restarted).edit_timeline(
                    changed_bind_replay
                )
            self.assertEqual(
                (caught.exception.code, caught.exception.status),
                ("idempotency_conflict", 409),
            )
            self.assertEqual(current, parent_before)
            original_composition = service.composition

            class CountingComposition:
                def __init__(self, delegate):
                    self.delegate = delegate
                    self.artifact_root = delegate.artifact_root
                    self.flame_smoke_calls = 0

                def execute_flame_smoke(self, *args, **kwargs):
                    self.flame_smoke_calls += 1
                    return self.delegate.execute_flame_smoke(*args, **kwargs)

                def __getattr__(self, name):
                    return getattr(self.delegate, name)

            counting_composition = CountingComposition(original_composition)
            service.composition = counting_composition
            effect_replay = _public(service).execute_deterministic_effect(
                effect_commands[0]
            )
            self.assertTrue(effect_replay["idempotentReplay"])
            self.assertFalse(_contains_private_key(effect_replay))
            smoke_replay = _public(service).execute_deterministic_effect(
                effect_commands[1]
            )
            self.assertTrue(smoke_replay["idempotentReplay"])
            self.assertFalse(_contains_private_key(smoke_replay))
            self.assertEqual(counting_composition.flame_smoke_calls, 2)
            base_pixels = decoded_frame_pixel_digest_metadata(
                artifact_root / inputs.base["storageKey"]
            )["decodedFramePixelDigest"]
            local_pixels = chains[1].artifact_evidence.as_dict()[
                "outputDigest"
            ]["decodedFramePixelDigest"]
            flame_pixels = chains[2].result.as_dict()[
                "outputDecodedFramePixelDigest"
            ]
            smoke_pixels = chains[3].result.as_dict()[
                "outputDecodedFramePixelDigest"
            ]
            self.assertNotEqual(flame_pixels, base_pixels)
            self.assertNotEqual(flame_pixels, local_pixels)
            self.assertNotEqual(smoke_pixels, base_pixels)
            self.assertNotEqual(smoke_pixels, flame_pixels)
            self.assertEqual(
                effect_replay["deterministicEffect"]["result"][
                    "outputDecodedFramePixelDigest"
                ],
                flame_pixels,
            )
            self.assertEqual(
                smoke_replay["deterministicEffect"]["result"][
                    "outputDecodedFramePixelDigest"
                ],
                smoke_pixels,
            )
            self.assertTrue(
                all(
                    chain.runtime_evidence.as_dict()["gpuUsed"] is False
                    for chain in chains[2:]
                )
            )
            effect_listing = _public(service).get_deterministic_effects(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertEqual(len(effect_listing["deterministicEffects"]), 2)
            self.assertFalse(_contains_private_key(effect_listing))
            with self.assertRaises(EpisodeProductionPublicError):
                _public(service).get_deterministic_effects(
                    "workspace-foreign", run["productionRunRef"]
                )
            nested_scope = deepcopy(effect_commands[0])
            nested_scope["requirement"]["workspaceRef"] = (
                "workspace-foreign"
            )
            with self.assertRaises(EpisodeProductionPublicError):
                _public(service).execute_deterministic_effect(nested_scope)
            command = {
                "workspaceRef": run["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "operationRef": "m13-e2-preview-compose",
                "idempotencyKey": "m13-e2-preview-compose-key",
                "expectedRunVersion": 1,
                "expectedEvidenceRevision": current["evidenceRevision"],
                "timelineVersionRef": current["timelineVersion"][
                    "timelineVersionRef"
                ],
                "timelineVersionDigest": current["timelineVersion"][
                    "payloadDigest"
                ],
            }
            result = service.compose_and_qc(command)
            self.assertEqual(current, parent_before)
            bindings = result["previewCandidate"]["effectResultBindings"]
            self.assertEqual(
                [item["effectMode"] for item in bindings],
                [
                    SCRATCH_REVEAL,
                    LOCAL_EXPOSURE,
                    FLAME_EXTINGUISH,
                    SMOKE,
                ],
            )
            self.assertEqual(
                result["compositionResult"]["rendererVersion"], "3"
            )
            self.assertIs(result["compositionResult"]["gpuUsed"], False)
            self.assertIs(
                result["compositionResult"]["providerUsed"], False
            )
            self.assertEqual(
                [chain.result.payload_digest for chain in chains],
                [item["resultDigest"] for item in bindings],
            )
            self.assertTrue(
                all(
                    chain.result.as_dict()["state"]
                    == (
                        "COMPOSED_CANDIDATE"
                        if chain.requirement.effect_mode
                        in {FLAME_EXTINGUISH, SMOKE}
                        else "SUCCEEDED"
                    )
                    for chain in chains
                )
            )
            public_result = _public(service).compose_and_qc(command)
            self.assertTrue(public_result["idempotentReplay"])
            self.assertFalse(_contains_private_key(public_result))
            preview_bundle = _public(service).get_preview_bundle(
                run["workspaceRef"], run["productionRunRef"]
            )
            self.assertEqual(
                preview_bundle["effect"]["executionOrder"],
                [
                    SCRATCH_REVEAL,
                    LOCAL_EXPOSURE,
                    FLAME_EXTINGUISH,
                    SMOKE,
                    "GLYPH_REVEAL",
                ],
            )
            self.assertFalse(_contains_private_key(preview_bundle))

            restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_path, initialize_if_missing=False
            )
            restarted = _service(
                artifact_root,
                restarted_repository,
                inputs,
                run,
                graph,
            )
            replay = restarted.compose_and_qc(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(
                replay["previewCandidate"], result["previewCandidate"]
            )
            records = restarted_repository.list_records(
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
                forbidden.intersection(
                    item["recordKind"] for item in records
                )
            )
            composition = next(
                item["payload"]
                for item in records
                if item["recordKind"] == "CompositionResult"
            )
            artifact = artifact_root / composition["outputStorageKey"]
            original = artifact.read_bytes()
            artifact.write_bytes(original + b"tamper")
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                _public(restarted).compose_and_qc(command)
            self.assertEqual(
                (caught.exception.code, caught.exception.status),
                ("artifact_verification_failed", 422),
            )


if __name__ == "__main__":
    unittest.main()
