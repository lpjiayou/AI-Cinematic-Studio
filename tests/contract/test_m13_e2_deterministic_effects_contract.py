from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production.deterministic_effects import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC,
    DETERMINISTIC_SMOKE_ALGORITHM_IDENTITY,
    DETERMINISTIC_SMOKE_ALGORITHM_VERSION,
    FLAME_EXTINGUISH,
    MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
    MASKED_SURFACE_RENDERER_VERSION_CURRENT,
    MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
    SMOKE,
    DeterministicEffectContractError,
    DeterministicEffectStaleInputError,
    FlameExtinguishRequirement,
    FlameExtinguishResult,
    FlameSmokeExecutionRequest,
    LocalExposureResult,
    SmokeRequirement,
    SmokeResult,
    append_deterministic_effect_result_chain,
    build_deterministic_effect_result,
    build_flame_extinguish_requirement,
    build_flame_smoke_execution_request,
    build_local_exposure_requirement,
    build_masked_surface_execution_request,
    build_smoke_requirement,
    parse_deterministic_effect_requirement,
    parse_deterministic_effect_result,
    resolve_deterministic_effect_result_chain,
    validate_deterministic_effect_execution_request_binding,
    validate_flame_local_exposure_compatibility,
)
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
)


def _digest(value: dict) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _seal(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _base_command(*, requirement_ref: str, effect_mode: str) -> dict:
    return {
        "workspaceRef": "workspace-e2",
        "productionRunRef": "run-e2",
        "requirementRef": requirement_ref,
        "effectMode": effect_mode,
        "targetShotRef": "shot-e2",
        "targetShotVersionRef": "shot-e2-version-1",
        "targetShotVersionDigest": "1" * 64,
        "basePlateAssetVersionRef": "base-version-e2",
        "basePlateAssetVersionDigest": "2" * 64,
        "basePlateFileDigest": "sha256:" + "3" * 64,
        "basePlatePixelDigest": "sha256:" + "4" * 64,
        "frameRangeStartInclusive": 0,
        "frameRangeEndExclusive": 8,
        "blendMode": "SCREEN",
        "layer": 4,
    }


def _local_exposure_command() -> dict:
    command = _base_command(
        requirement_ref="local-exposure-e2", effect_mode="LOCAL_EXPOSURE"
    )
    command.update(
        {
            "maskAssetVersionRef": "flame-mask-version-e2",
            "maskAssetVersionDigest": "5" * 64,
            "maskFileDigest": "sha256:" + "6" * 64,
            "maskPixelDigest": "sha256:" + "7" * 64,
            "explicitSchedule": [
                {
                    "startFrameInclusive": 0,
                    "endFrameExclusive": 8,
                    "enabled": True,
                    "interpolation": "STEP",
                }
            ],
            "trajectoryKeyframes": [
                {
                    "frame": 0,
                    "xPermille": 0,
                    "yPermille": 0,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 7,
                    "xPermille": 0,
                    "yPermille": 0,
                    "interpolation": "LINEAR",
                },
            ],
            "intensityCurve": [
                {"frame": 0, "valuePermille": 0, "interpolation": "LINEAR"},
                {"frame": 7, "valuePermille": 700, "interpolation": "LINEAR"},
            ],
            "exposureCurve": [
                {"frame": 0, "valueMilliStops": 0, "interpolation": "LINEAR"},
                {
                    "frame": 7,
                    "valueMilliStops": -750,
                    "interpolation": "EASE_OUT",
                },
            ],
            "position": {"xPermille": 0, "yPermille": 0},
            "scale": {"xPermille": 1000, "yPermille": 1000},
            "perspective": {"mode": "NONE", "quadPermille": []},
            "blendMode": "NORMAL",
            "layer": 3,
        }
    )
    return command


def _flame_command(local_requirement) -> dict:
    command = _base_command(
        requirement_ref="flame-extinguish-e2", effect_mode=FLAME_EXTINGUISH
    )
    command.update(
        {
            "flameMaskAssetVersionRef": "flame-mask-version-e2",
            "flameMaskAssetVersionDigest": "5" * 64,
            "flameMaskFileDigest": "sha256:" + "6" * 64,
            "flameMaskPixelDigest": "sha256:" + "7" * 64,
            "stateSchedule": [
                {"state": "LIT", "startFrameInclusive": 0, "endFrameExclusive": 2},
                {
                    "state": "DIMMING",
                    "startFrameInclusive": 2,
                    "endFrameExclusive": 4,
                },
                {
                    "state": "EXTINGUISHED",
                    "startFrameInclusive": 4,
                    "endFrameExclusive": 6,
                },
                {"state": "DARK", "startFrameInclusive": 6, "endFrameExclusive": 8},
            ],
            "brightnessCurve": [
                {"frame": 0, "valuePermille": 1000, "interpolation": "LINEAR"},
                {"frame": 4, "valuePermille": 200, "interpolation": "LINEAR"},
                {"frame": 6, "valuePermille": 0, "interpolation": "STEP"},
                {"frame": 7, "valuePermille": 0, "interpolation": "STEP"},
            ],
            "alphaCurve": [
                {"frame": 0, "valuePermille": 1000, "interpolation": "LINEAR"},
                {"frame": 4, "valuePermille": 100, "interpolation": "LINEAR"},
                {"frame": 6, "valuePermille": 0, "interpolation": "STEP"},
                {"frame": 7, "valuePermille": 0, "interpolation": "STEP"},
            ],
            "localExposureRequirementRef": local_requirement.requirement_ref,
            "localExposureRequirementDigest": local_requirement.payload_digest,
        }
    )
    return command


def _smoke_command(*, procedural: bool) -> dict:
    command = _base_command(
        requirement_ref=(
            "smoke-procedural-e2" if procedural else "smoke-pinned-e2"
        ),
        effect_mode=SMOKE,
    )
    command.update(
        {
            "smokeSourceKind": (
                "DETERMINISTIC_CPU_PROCEDURAL"
                if procedural
                else "PINNED_SMOKE_LAYER"
            ),
            "smokeLayerAssetVersionRef": None if procedural else "smoke-layer-version-e2",
            "smokeLayerAssetVersionDigest": None if procedural else "8" * 64,
            "smokeLayerFileDigest": None if procedural else "sha256:" + "9" * 64,
            "smokeLayerPixelDigest": None if procedural else "sha256:" + "a" * 64,
            "emissionMaskAssetVersionRef": "emission-mask-version-e2",
            "emissionMaskAssetVersionDigest": "b" * 64,
            "emissionMaskFileDigest": "sha256:" + "c" * 64,
            "emissionMaskPixelDigest": "sha256:" + "d" * 64,
            "opacitySchedule": [
                {"frame": 0, "valuePermille": 0, "interpolation": "LINEAR"},
                {"frame": 7, "valuePermille": 700, "interpolation": "EASE_IN"},
            ],
            "positionKeyframes": [
                {
                    "frame": 0,
                    "xPermille": 300,
                    "yPermille": 600,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 7,
                    "xPermille": 350,
                    "yPermille": 400,
                    "interpolation": "EASE_OUT",
                },
            ],
            "scaleKeyframes": [
                {
                    "frame": 0,
                    "xPermille": 200,
                    "yPermille": 200,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 7,
                    "xPermille": 500,
                    "yPermille": 500,
                    "interpolation": "EASE_OUT",
                },
            ],
            "driftKeyframes": [
                {
                    "frame": 0,
                    "xDeltaPermille": 0,
                    "yDeltaPermille": 0,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 7,
                    "xDeltaPermille": -25,
                    "yDeltaPermille": -200,
                    "interpolation": "EASE_OUT",
                },
            ],
            "dissipationCurve": [
                {"frame": 0, "valuePermille": 0, "interpolation": "LINEAR"},
                {"frame": 7, "valuePermille": 300, "interpolation": "EASE_IN"},
            ],
            "algorithmIdentity": (
                DETERMINISTIC_SMOKE_ALGORITHM_IDENTITY if procedural else None
            ),
            "algorithmVersion": (
                DETERMINISTIC_SMOKE_ALGORITHM_VERSION if procedural else None
            ),
            "deterministicSeed": 912_345 if procedural else None,
            "blendMode": "SCREEN",
            "layer": 5,
        }
    )
    return command


def _execution_evidence(
    requirement,
    request,
    *,
    local_requirement=None,
    local_result=None,
    ffmpeg_identity: str = "ffmpeg-7.1",
    renderer_version: str = MASKED_SURFACE_RENDERER_VERSION_CURRENT,
) -> dict:
    requirement_value = requirement.as_dict()
    request_value = request.as_dict()
    v3_digest = sha256(request.payload_digest.encode("ascii")).hexdigest()
    runtime_identity = {
        "v3ExecutionRequestDigest": v3_digest,
        "rendererIdentity": "v3.deterministic-masked-surface-ffmpeg",
        "rendererVersion": renderer_version,
        "ffmpegIdentity": ffmpeg_identity,
    }
    runtime = _seal(
        {
            "schemaVersion": MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
            "runtimeEvidenceRef": (
                "m13-masked-surface-runtime-evidence-"
                + _digest(runtime_identity)[:32]
            ),
            "workspaceRef": requirement.workspace_ref,
            "productionRunRef": requirement.production_run_ref,
            "requirementRef": requirement.requirement_ref,
            "requirementDigest": requirement.payload_digest,
            "executionRequestRef": request.execution_request_ref,
            "executionRequestDigest": request.payload_digest,
            "v3ExecutionRequestDigest": v3_digest,
            "effectMode": requirement.effect_mode,
            "rendererIdentity": runtime_identity["rendererIdentity"],
            "rendererVersion": runtime_identity["rendererVersion"],
            "ffmpegIdentity": ffmpeg_identity,
            "gpuUsed": False,
            "publicationAllowed": False,
        }
    )
    output_digest = {
        "fileDigest": "sha256:" + sha256(
            (request.payload_digest + ffmpeg_identity).encode("ascii")
        ).hexdigest(),
        "fileDigestAlgorithm": "sha256",
        "decodedFramePixelDigest": "sha256:" + sha256(
            ("pixels" + request.payload_digest + ffmpeg_identity).encode("ascii")
        ).hexdigest(),
        "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC,
        "pixelMode": "RGBA",
        "width": 64,
        "height": 64,
        "frameCount": 8,
        "frameRate": 24,
    }
    artifact_identity = {
        "v3ExecutionRequestDigest": v3_digest,
        "fileDigest": output_digest["fileDigest"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    artifact = _seal(
        {
            "schemaVersion": MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            "artifactEvidenceRef": (
                "m13-masked-surface-artifact-evidence-"
                + _digest(artifact_identity)[:32]
            ),
            "workspaceRef": requirement.workspace_ref,
            "productionRunRef": requirement.production_run_ref,
            "requirementRef": requirement.requirement_ref,
            "requirementDigest": requirement.payload_digest,
            "executionRequestRef": request.execution_request_ref,
            "executionRequestDigest": request.payload_digest,
            "v3ExecutionRequestDigest": v3_digest,
            "effectMode": requirement.effect_mode,
            "outputByteSize": 4096,
            "outputMediaProbe": {
                "width": 64,
                "height": 64,
                "frameCount": 8,
                "frameRate": 24,
                "pixelFormat": "yuv420p",
                "container": "mp4",
                "videoCodec": "h264",
            },
            "outputDigest": output_digest,
            "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
            "runtimeEvidenceDigest": runtime["payloadDigest"],
            "provenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )
    bindings = {
        "workspaceRef": requirement.workspace_ref,
        "productionRunRef": requirement.production_run_ref,
        "requirementRef": requirement.requirement_ref,
        "requirementDigest": requirement.payload_digest,
        "executionRequestRef": request.execution_request_ref,
        "executionRequestDigest": request.payload_digest,
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=request,
        evidence_bindings=bindings,
        artifact_evidence=(
            artifact if requirement.effect_mode in {FLAME_EXTINGUISH, SMOKE} else None
        ),
        local_exposure_requirement=local_requirement,
        local_exposure_result=local_result,
    )
    return {"runtime": runtime, "artifact": artifact, "result": result}


def _local_chain():
    requirement = build_local_exposure_requirement(_local_exposure_command())
    request = build_masked_surface_execution_request(requirement)
    evidence = _execution_evidence(requirement, request)
    return requirement, request, evidence


class M13E2DeterministicEffectsContractTests(unittest.TestCase):
    def test_flame_state_machine_accepts_only_exact_forward_sequences(self):
        local, _, _ = _local_chain()
        flame = build_flame_extinguish_requirement(_flame_command(local))
        self.assertIs(type(flame), FlameExtinguishRequirement)
        with_ember = _flame_command(local)
        with_ember["stateSchedule"] = [
            {"state": "LIT", "startFrameInclusive": 0, "endFrameExclusive": 1},
            {"state": "DIMMING", "startFrameInclusive": 1, "endFrameExclusive": 3},
            {
                "state": "EXTINGUISHED",
                "startFrameInclusive": 3,
                "endFrameExclusive": 5,
            },
            {"state": "EMBER", "startFrameInclusive": 5, "endFrameExclusive": 6},
            {"state": "DARK", "startFrameInclusive": 6, "endFrameExclusive": 8},
        ]
        self.assertEqual(
            len(build_flame_extinguish_requirement(with_ember).as_dict()["stateSchedule"]),
            5,
        )
        invalids = []
        reverse = _flame_command(local)
        reverse["stateSchedule"][1]["state"] = "EXTINGUISHED"
        invalids.append(reverse)
        gap = _flame_command(local)
        gap["stateSchedule"][1]["startFrameInclusive"] = 3
        invalids.append(gap)
        overlap = _flame_command(local)
        overlap["stateSchedule"][1]["startFrameInclusive"] = 1
        invalids.append(overlap)
        not_dark = _flame_command(local)
        not_dark["stateSchedule"][-1]["state"] = "EMBER"
        invalids.append(not_dark)
        bad_curve = _flame_command(local)
        bad_curve["alphaCurve"][-1]["valuePermille"] = 1
        invalids.append(bad_curve)
        brightness_out_of_bounds = _flame_command(local)
        brightness_out_of_bounds["brightnessCurve"][0]["valuePermille"] = 1001
        invalids.append(brightness_out_of_bounds)
        alpha_out_of_bounds = _flame_command(local)
        alpha_out_of_bounds["alphaCurve"][0]["valuePermille"] = -1
        invalids.append(alpha_out_of_bounds)
        missing_mask = _flame_command(local)
        missing_mask.pop("flameMaskAssetVersionRef")
        invalids.append(missing_mask)
        unsupported_blend = _flame_command(local)
        unsupported_blend["blendMode"] = "SOFT_LIGHT"
        invalids.append(unsupported_blend)
        for command in invalids:
            with self.assertRaises(DeterministicEffectContractError):
                build_flame_extinguish_requirement(command)

    def test_flame_reuses_exact_local_exposure_requirement_and_result(self):
        local, local_request, local_evidence = _local_chain()
        local_result = local_evidence["result"]
        self.assertIs(type(local_result), LocalExposureResult)
        flame = build_flame_extinguish_requirement(_flame_command(local))
        exposure, result = validate_flame_local_exposure_compatibility(
            flame, local, local_result
        )
        self.assertEqual(exposure.as_dict(), local.as_dict())
        self.assertEqual(result.as_dict(), local_result.as_dict())
        request = build_flame_smoke_execution_request(
            flame,
            local_exposure_requirement=local,
            local_exposure_result=local_result,
        )
        self.assertIs(type(request), FlameSmokeExecutionRequest)
        self.assertEqual(
            request.as_dict()["localExposureResultRef"], local_result.result_ref
        )
        with self.assertRaises(DeterministicEffectContractError):
            build_flame_smoke_execution_request(flame)
        stale_exposure_digest = _flame_command(local)
        stale_exposure_digest["localExposureRequirementDigest"] = "f" * 64
        with self.assertRaises(DeterministicEffectStaleInputError):
            validate_flame_local_exposure_compatibility(
                build_flame_extinguish_requirement(stale_exposure_digest),
                local,
                local_result,
            )
        mismatched_local_command = _local_exposure_command()
        mismatched_local_command["maskAssetVersionRef"] = "other-mask-version"
        mismatched_local = build_local_exposure_requirement(
            mismatched_local_command
        )
        mismatched_flame_command = _flame_command(mismatched_local)
        mismatched_flame = build_flame_extinguish_requirement(
            mismatched_flame_command
        )
        with self.assertRaises(DeterministicEffectStaleInputError):
            validate_flame_local_exposure_compatibility(
                mismatched_flame, mismatched_local
            )
        self.assertEqual(local_request.requirement_ref, local.requirement_ref)

    def test_smoke_source_union_allows_only_pinned_or_fixed_procedural(self):
        pinned = build_smoke_requirement(_smoke_command(procedural=False))
        procedural = build_smoke_requirement(_smoke_command(procedural=True))
        self.assertIs(type(pinned), SmokeRequirement)
        self.assertIs(type(procedural), SmokeRequirement)
        self.assertEqual(procedural.as_dict()["deterministicSeed"], 912_345)
        for mutate in (
            lambda value: value.update({"deterministicSeed": None}),
            lambda value: value.update({"algorithmVersion": "system-time"}),
            lambda value: value.update({"smokeLayerAssetVersionRef": "unbound-layer"}),
        ):
            command = _smoke_command(procedural=True)
            mutate(command)
            with self.assertRaises(DeterministicEffectContractError):
                build_smoke_requirement(command)
        forbidden = _smoke_command(procedural=True)
        forbidden["systemTimeSeed"] = 1
        with self.assertRaises(DeterministicEffectContractError):
            build_smoke_requirement(forbidden)
        pinned_with_seed = _smoke_command(procedural=False)
        pinned_with_seed["deterministicSeed"] = 1
        with self.assertRaises(DeterministicEffectContractError):
            build_smoke_requirement(pinned_with_seed)
        for keyframes in (
            "positionKeyframes",
            "scaleKeyframes",
            "driftKeyframes",
        ):
            out_of_range = _smoke_command(procedural=True)
            out_of_range[keyframes][-1]["frame"] = 8
            with self.subTest(keyframes=keyframes):
                with self.assertRaises(DeterministicEffectContractError):
                    build_smoke_requirement(out_of_range)
        unsupported_blend = _smoke_command(procedural=True)
        unsupported_blend["blendMode"] = "SOFT_LIGHT"
        with self.assertRaises(DeterministicEffectContractError):
            build_smoke_requirement(unsupported_blend)

    def test_requests_are_exact_storage_free_projections(self):
        local, _, local_evidence = _local_chain()
        flame = build_flame_extinguish_requirement(_flame_command(local))
        flame_request = build_flame_smoke_execution_request(
            flame,
            local_exposure_requirement=local,
            local_exposure_result=local_evidence["result"],
        )
        smoke = build_smoke_requirement(_smoke_command(procedural=True))
        smoke_request = build_flame_smoke_execution_request(smoke)
        for requirement, request in (
            (flame, flame_request),
            (smoke, smoke_request),
        ):
            serialized = json.dumps(request.as_dict(), sort_keys=True).lower()
            for forbidden in ("storagekey", "path", "argv", "filter"):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(
                validate_deterministic_effect_execution_request_binding(
                    request,
                    requirement,
                    local_exposure_requirement=(
                        local if requirement.effect_mode == FLAME_EXTINGUISH else None
                    ),
                    local_exposure_result=(
                        local_evidence["result"]
                        if requirement.effect_mode == FLAME_EXTINGUISH
                        else None
                    ),
                ).as_dict(),
                request.as_dict(),
            )
        changed = smoke_request.as_dict()
        changed["layer"] += 1
        changed = _seal(changed)
        with self.assertRaises(DeterministicEffectStaleInputError):
            validate_deterministic_effect_execution_request_binding(
                changed, smoke
            )

    def test_e2_results_are_closed_non_publishing_candidates(self):
        local, _, local_evidence = _local_chain()
        flame = build_flame_extinguish_requirement(_flame_command(local))
        flame_request = build_flame_smoke_execution_request(
            flame,
            local_exposure_requirement=local,
            local_exposure_result=local_evidence["result"],
        )
        smoke = build_smoke_requirement(_smoke_command(procedural=False))
        smoke_request = build_flame_smoke_execution_request(smoke)
        flame_evidence = _execution_evidence(
            flame,
            flame_request,
            local_requirement=local,
            local_result=local_evidence["result"],
        )
        smoke_evidence = _execution_evidence(smoke, smoke_request)
        self.assertIs(type(flame_evidence["result"]), FlameExtinguishResult)
        self.assertIs(type(smoke_evidence["result"]), SmokeResult)
        for result in (flame_evidence["result"], smoke_evidence["result"]):
            value = result.as_dict()
            self.assertEqual(value["state"], "COMPOSED_CANDIDATE")
            self.assertEqual(value["assetAdmissionState"], "NOT_ADMITTED")
            self.assertEqual(value["masterState"], "NOT_CREATED")
            self.assertEqual(value["exportState"], "NOT_CREATED")
            self.assertFalse(value["publicationAllowed"])
            self.assertNotIn("Timeline", json.dumps(value, sort_keys=True))
            self.assertEqual(
                parse_deterministic_effect_result(value).as_dict(), value
            )
        self.assertEqual(
            parse_deterministic_effect_requirement(flame.as_dict()).as_dict(),
            flame.as_dict(),
        )

    def test_existing_journal_persists_resolves_replays_and_rejects_drift(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        local, local_request, local_evidence = _local_chain()
        append_deterministic_effect_result_chain(
            repository,
            requirement=local,
            execution_request=local_request,
            artifact_evidence=local_evidence["artifact"],
            runtime_evidence=local_evidence["runtime"],
            result=local_evidence["result"],
            idempotency_key="append-local-e2",
            created_at="2026-08-31T00:00:00Z",
        )
        flame = build_flame_extinguish_requirement(_flame_command(local))
        flame_request = build_flame_smoke_execution_request(
            flame,
            local_exposure_requirement=local,
            local_exposure_result=local_evidence["result"],
        )
        flame_evidence = _execution_evidence(
            flame,
            flame_request,
            local_requirement=local,
            local_result=local_evidence["result"],
        )
        first, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=flame,
            execution_request=flame_request,
            artifact_evidence=flame_evidence["artifact"],
            runtime_evidence=flame_evidence["runtime"],
            result=flame_evidence["result"],
            idempotency_key="append-flame-e2",
            created_at="2026-08-31T00:01:00Z",
        )
        self.assertFalse(replayed)
        resolved = resolve_deterministic_effect_result_chain(
            repository,
            workspace_ref="workspace-e2",
            production_run_ref="run-e2",
            result_ref=flame_evidence["result"].result_ref,
            result_digest=flame_evidence["result"].payload_digest,
        )
        self.assertEqual(first.as_dict(), resolved.as_dict())
        second, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=flame,
            execution_request=flame_request,
            artifact_evidence=flame_evidence["artifact"],
            runtime_evidence=flame_evidence["runtime"],
            result=flame_evidence["result"],
            idempotency_key="append-flame-e2",
            created_at="2026-08-31T00:01:00Z",
        )
        self.assertTrue(replayed)
        self.assertEqual(second.as_dict(), first.as_dict())
        changed = _execution_evidence(
            flame,
            flame_request,
            local_requirement=local,
            local_result=local_evidence["result"],
            ffmpeg_identity="ffmpeg-7.2",
        )
        with self.assertRaises(IdempotencyConflictError):
            append_deterministic_effect_result_chain(
                repository,
                requirement=flame,
                execution_request=flame_request,
                artifact_evidence=changed["artifact"],
                runtime_evidence=changed["runtime"],
                result=changed["result"],
                idempotency_key="append-flame-e2",
                created_at="2026-08-31T00:01:00Z",
            )
        forged = flame_evidence["result"].as_dict()
        forged["outputFileDigest"] = "sha256:" + "f" * 64
        forged = _seal(forged)
        with self.assertRaises(DeterministicEffectStaleInputError):
            append_deterministic_effect_result_chain(
                repository,
                requirement=flame,
                execution_request=flame_request,
                artifact_evidence=flame_evidence["artifact"],
                runtime_evidence=flame_evidence["runtime"],
                result=forged,
                idempotency_key="forged-flame-e2",
                created_at="2026-08-31T00:02:00Z",
            )

    def test_sqlite_restart_reads_exact_smoke_chain_without_new_tables(self):
        smoke = build_smoke_requirement(_smoke_command(procedural=True))
        request = build_flame_smoke_execution_request(smoke)
        evidence = _execution_evidence(smoke, request)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite"
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            tables_before = set(repository._TABLES)
            stored, replayed = append_deterministic_effect_result_chain(
                repository,
                requirement=smoke,
                execution_request=request,
                artifact_evidence=evidence["artifact"],
                runtime_evidence=evidence["runtime"],
                result=evidence["result"],
                idempotency_key="append-smoke-sqlite-e2",
                created_at="2026-08-31T00:03:00Z",
            )
            self.assertFalse(replayed)
            restarted = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )
            resolved = resolve_deterministic_effect_result_chain(
                restarted,
                workspace_ref="workspace-e2",
                production_run_ref="run-e2",
                result_ref=evidence["result"].result_ref,
                result_digest=evidence["result"].payload_digest,
            )
            self.assertEqual(resolved.as_dict(), stored.as_dict())
            self.assertEqual(set(restarted._TABLES), tables_before)


if __name__ == "__main__":
    unittest.main()
