from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production import deterministic_effects as subject

from services.v5_core_os.episode_production.deterministic_effects import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC,
    DeterministicEffectContractError,
    DeterministicEffectJournalError,
    DeterministicEffectStaleInputError,
    LIGHT_SWEEP,
    LOCAL_EXPOSURE,
    MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
    MASKED_SURFACE_RENDERER_VERSION_CURRENT,
    MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
    SCRATCH_REVEAL,
    LocalExposureRequirement,
    LocalExposureResult,
    MaskedSurfaceArtifactEvidence,
    MaskedSurfaceRuntimeEvidence,
    ScratchLightRequirement,
    ScratchLightResult,
    append_deterministic_effect_result_chain,
    build_deterministic_effect_result,
    build_local_exposure_requirement,
    build_masked_surface_execution_request,
    build_scratch_light_requirement,
    parse_deterministic_effect_requirement,
    parse_deterministic_effect_result,
    resolve_deterministic_effect_result_chain,
    validate_masked_surface_execution_evidence,
    validate_masked_surface_execution_request_binding,
)
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    StaleInputError,
)


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: dict) -> str:
    return sha256(_canonical(value)).hexdigest()


def _seal(value: dict) -> dict:
    result = deepcopy(value)
    result["payloadDigest"] = _digest(result)
    return result


def _command(effect_mode: str = SCRATCH_REVEAL) -> dict:
    return {
        "workspaceRef": "workspace-e1",
        "productionRunRef": "run-e1",
        "requirementRef": f"requirement-{effect_mode.lower()}",
        "effectMode": effect_mode,
        "targetShotRef": "shot-e1",
        "targetShotVersionRef": "shot-e1-version-3",
        "targetShotVersionDigest": "1" * 64,
        "basePlateAssetVersionRef": "base-version-1",
        "basePlateAssetVersionDigest": "2" * 64,
        "basePlateFileDigest": "sha256:" + "3" * 64,
        "basePlatePixelDigest": "sha256:" + "4" * 64,
        "maskAssetVersionRef": "mask-version-1",
        "maskAssetVersionDigest": "5" * 64,
        "maskFileDigest": "sha256:" + "6" * 64,
        "maskPixelDigest": "sha256:" + "7" * 64,
        "frameRangeStartInclusive": 10,
        "frameRangeEndExclusive": 14,
        "explicitSchedule": [
            {
                "startFrameInclusive": 10,
                "endFrameExclusive": 12,
                "enabled": True,
                "interpolation": "STEP",
            },
            {
                "startFrameInclusive": 12,
                "endFrameExclusive": 14,
                "enabled": True,
                "interpolation": "STEP",
            },
        ],
        "trajectoryKeyframes": [
            {
                "frame": 10,
                "xPermille": 250,
                "yPermille": 300,
                "interpolation": "LINEAR",
            },
            {
                "frame": 13,
                "xPermille": 750,
                "yPermille": 300,
                "interpolation": "EASE_IN_OUT",
            },
        ],
        "intensityCurve": [
            {"frame": 10, "valuePermille": 0, "interpolation": "LINEAR"},
            {"frame": 13, "valuePermille": 900, "interpolation": "EASE_OUT"},
        ],
        "exposureCurve": [
            {"frame": 10, "valueMilliStops": 0, "interpolation": "LINEAR"},
            {"frame": 13, "valueMilliStops": 500, "interpolation": "EASE_OUT"},
        ],
        "position": {"xPermille": 250, "yPermille": 300},
        "scale": {"xPermille": 200, "yPermille": 400},
        "perspective": {"mode": "NONE", "quadPermille": []},
        "blendMode": "SCREEN",
        "layer": 4,
    }


def _evidence(
    requirement,
    request,
    *,
    ffmpeg_identity: str = "ffmpeg-7.1",
    renderer_version: str = MASKED_SURFACE_RENDERER_VERSION_CURRENT,
) -> dict:
    requirement_value = requirement.as_dict()
    request_value = request.as_dict()
    v3_digest = "8" * 64
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
            "workspaceRef": requirement_value["workspaceRef"],
            "productionRunRef": requirement_value["productionRunRef"],
            "requirementRef": requirement_value["requirementRef"],
            "requirementDigest": requirement_value["payloadDigest"],
            "executionRequestRef": request_value["executionRequestRef"],
            "executionRequestDigest": request_value["payloadDigest"],
            "v3ExecutionRequestDigest": v3_digest,
            "effectMode": requirement_value["effectMode"],
            "rendererIdentity": runtime_identity["rendererIdentity"],
            "rendererVersion": runtime_identity["rendererVersion"],
            "ffmpegIdentity": ffmpeg_identity,
            "gpuUsed": False,
            "publicationAllowed": False,
        }
    )
    output_digest = {
        "fileDigest": "sha256:" + "9" * 64,
        "fileDigestAlgorithm": "sha256",
        "decodedFramePixelDigest": "sha256:" + "a" * 64,
        "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC,
        "pixelMode": "RGBA",
        "width": 720,
        "height": 1280,
        "frameCount": 24,
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
            "workspaceRef": requirement_value["workspaceRef"],
            "productionRunRef": requirement_value["productionRunRef"],
            "requirementRef": requirement_value["requirementRef"],
            "requirementDigest": requirement_value["payloadDigest"],
            "executionRequestRef": request_value["executionRequestRef"],
            "executionRequestDigest": request_value["payloadDigest"],
            "v3ExecutionRequestDigest": v3_digest,
            "effectMode": requirement_value["effectMode"],
            "outputByteSize": 4096,
            "outputMediaProbe": {
                "width": 720,
                "height": 1280,
                "frameCount": 24,
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
        "workspaceRef": requirement_value["workspaceRef"],
        "productionRunRef": requirement_value["productionRunRef"],
        "requirementRef": requirement_value["requirementRef"],
        "requirementDigest": requirement_value["payloadDigest"],
        "executionRequestRef": request_value["executionRequestRef"],
        "executionRequestDigest": request_value["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=request,
        evidence_bindings=bindings,
    )
    return {
        "artifact": artifact,
        "runtime": runtime,
        "bindings": bindings,
        "result": result,
    }


class DeterministicEffectsContractTests(unittest.TestCase):
    def _chain(self, effect_mode: str = SCRATCH_REVEAL, *, ffmpeg_identity: str = "ffmpeg-7.1"):
        requirement = (
            build_local_exposure_requirement(_command(effect_mode))
            if effect_mode == LOCAL_EXPOSURE
            else build_scratch_light_requirement(_command(effect_mode))
        )
        request = build_masked_surface_execution_request(requirement)
        evidence = _evidence(
            requirement, request, ffmpeg_identity=ffmpeg_identity
        )
        return requirement, request, evidence

    def test_closed_requirements_cover_all_three_modes(self) -> None:
        scratch = build_scratch_light_requirement(_command(SCRATCH_REVEAL))
        light = build_scratch_light_requirement(_command(LIGHT_SWEEP))
        exposure = build_local_exposure_requirement(_command(LOCAL_EXPOSURE))
        self.assertIs(type(scratch), ScratchLightRequirement)
        self.assertIs(type(light), ScratchLightRequirement)
        self.assertIs(type(exposure), LocalExposureRequirement)
        self.assertEqual(scratch.effect_mode, SCRATCH_REVEAL)
        self.assertEqual(light.effect_mode, LIGHT_SWEEP)
        self.assertEqual(exposure.effect_mode, LOCAL_EXPOSURE)
        self.assertFalse(exposure.as_dict()["publicationAllowed"])
        self.assertEqual(
            parse_deterministic_effect_requirement(scratch.as_dict()).as_dict(),
            scratch.as_dict(),
        )

    def test_wrong_mode_schema_pair_is_rejected(self) -> None:
        with self.assertRaises(DeterministicEffectContractError):
            build_scratch_light_requirement(_command(LOCAL_EXPOSURE))
        with self.assertRaises(DeterministicEffectContractError):
            build_local_exposure_requirement(_command(LIGHT_SWEEP))

    def test_schedule_gap_overlap_and_disabled_range_are_rejected(self) -> None:
        for schedule in (
            [
                {
                    "startFrameInclusive": 10,
                    "endFrameExclusive": 11,
                    "enabled": True,
                    "interpolation": "STEP",
                },
                {
                    "startFrameInclusive": 12,
                    "endFrameExclusive": 14,
                    "enabled": True,
                    "interpolation": "STEP",
                },
            ],
            [
                {
                    "startFrameInclusive": 10,
                    "endFrameExclusive": 13,
                    "enabled": True,
                    "interpolation": "STEP",
                },
                {
                    "startFrameInclusive": 12,
                    "endFrameExclusive": 14,
                    "enabled": True,
                    "interpolation": "STEP",
                },
            ],
            [
                {
                    "startFrameInclusive": 10,
                    "endFrameExclusive": 14,
                    "enabled": False,
                    "interpolation": "STEP",
                }
            ],
        ):
            command = _command()
            command["explicitSchedule"] = schedule
            with self.assertRaises(DeterministicEffectContractError):
                build_scratch_light_requirement(command)

    def test_integer_curves_and_trajectory_bounds_are_closed(self) -> None:
        cases = []
        floating = _command()
        floating["intensityCurve"][1]["valuePermille"] = 1.5
        cases.append(floating)
        random_curve = _command()
        random_curve["intensityCurve"][0]["random"] = True
        cases.append(random_curve)
        expression_curve = _command()
        expression_curve["exposureCurve"][0]["expression"] = "frame/24"
        cases.append(expression_curve)
        out_of_bounds = _command()
        out_of_bounds["trajectoryKeyframes"][1]["xPermille"] = 1001
        cases.append(out_of_bounds)
        wrong_endpoint = _command()
        wrong_endpoint["trajectoryKeyframes"][1]["frame"] = 12
        cases.append(wrong_endpoint)
        for command in cases:
            with self.assertRaises(DeterministicEffectContractError):
                build_scratch_light_requirement(command)

    def test_paths_filters_argv_and_random_fields_are_rejected(self) -> None:
        for field, value in (
            ("inputPath", "/tmp/base.mp4"),
            ("ffmpegFilter", "overlay"),
            ("argv", ["ffmpeg"]),
            ("randomSeed", 1),
        ):
            command = _command()
            command[field] = value
            with self.assertRaises(DeterministicEffectContractError):
                build_scratch_light_requirement(command)

    def test_geometry_and_blend_contracts_are_closed(self) -> None:
        valid_quad = _command()
        valid_quad["perspective"] = {
            "mode": "FIXED_QUAD",
            "quadPermille": [
                {"xPermille": 0, "yPermille": 0},
                {"xPermille": 1000, "yPermille": 0},
                {"xPermille": 0, "yPermille": 1000},
                {"xPermille": 1000, "yPermille": 1000},
            ],
        }
        self.assertEqual(
            build_scratch_light_requirement(valid_quad)
            .as_dict()["perspective"]["mode"],
            "FIXED_QUAD",
        )
        invalid_scale = _command()
        invalid_scale["scale"]["xPermille"] = 1001
        outside_canvas = _command()
        outside_canvas["trajectoryKeyframes"][1]["xPermille"] = 900
        invalid_quad = _command()
        invalid_quad["perspective"] = {
            "mode": "FIXED_QUAD",
            "quadPermille": [
                {"xPermille": 0, "yPermille": 0},
                {"xPermille": 0, "yPermille": 0},
                {"xPermille": 1000, "yPermille": 1000},
                {"xPermille": 0, "yPermille": 1000},
            ],
        }
        invalid_blend = _command()
        invalid_blend["blendMode"] = "FREE_FILTER"
        misordered_quad = _command()
        misordered_quad["perspective"] = {
            "mode": "FIXED_QUAD",
            "quadPermille": [
                {"xPermille": 800, "yPermille": 0},
                {"xPermille": 0, "yPermille": 0},
                {"xPermille": 800, "yPermille": 900},
                {"xPermille": 0, "yPermille": 900},
            ],
        }
        for command in (
            invalid_scale,
            outside_canvas,
            invalid_quad,
            misordered_quad,
            invalid_blend,
        ):
            with self.assertRaises(DeterministicEffectContractError):
                build_scratch_light_requirement(command)

    def test_execution_request_is_exact_storage_free_projection(self) -> None:
        requirement, request, _ = self._chain()
        value = request.as_dict()
        self.assertNotIn("requirementKind", value)
        self.assertNotIn("output", value)
        serialized = json.dumps(value, sort_keys=True).lower()
        for forbidden in ("storagekey", "path", "argv", "filter"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(
            validate_masked_surface_execution_request_binding(
                value, requirement
            ).as_dict(),
            value,
        )

    def test_execution_request_tamper_is_rejected(self) -> None:
        requirement, request, _ = self._chain()
        changed = request.as_dict()
        changed["layer"] += 1
        changed["payloadDigest"] = _digest(
            {key: value for key, value in changed.items() if key != "payloadDigest"}
        )
        with self.assertRaises(DeterministicEffectStaleInputError):
            validate_masked_surface_execution_request_binding(
                changed, requirement
            )

    def test_artifact_and_runtime_evidence_are_closed_and_linked(self) -> None:
        requirement, request, evidence = self._chain()
        artifact, runtime = validate_masked_surface_execution_evidence(
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
        )
        self.assertIs(type(artifact), MaskedSurfaceArtifactEvidence)
        self.assertIs(type(runtime), MaskedSurfaceRuntimeEvidence)
        self.assertFalse(runtime.as_dict()["gpuUsed"])

    def test_runtime_reader_accepts_v1_v2_rejects_unknown_and_new_context_requires_v2(self) -> None:
        requirement, request, evidence_v2 = self._chain()
        evidence_v1 = _evidence(requirement, request, renderer_version="1")
        parsed_v1 = MaskedSurfaceRuntimeEvidence.from_mapping(
            evidence_v1["runtime"]
        )
        parsed_v2 = MaskedSurfaceRuntimeEvidence.from_mapping(
            evidence_v2["runtime"]
        )
        self.assertEqual("1", parsed_v1.as_dict()["rendererVersion"])
        self.assertEqual("2", parsed_v2.as_dict()["rendererVersion"])
        self.assertNotEqual(
            parsed_v1.as_dict()["runtimeEvidenceRef"],
            parsed_v2.as_dict()["runtimeEvidenceRef"],
        )
        self.assertNotEqual(
            evidence_v1["artifact"]["artifactEvidenceRef"],
            evidence_v2["artifact"]["artifactEvidenceRef"],
        )
        with self.assertRaises(DeterministicEffectContractError):
            validate_masked_surface_execution_evidence(
                requirement=requirement,
                execution_request=request,
                artifact_evidence=evidence_v1["artifact"],
                runtime_evidence=evidence_v1["runtime"],
                require_current_renderer=True,
            )
        unknown = _evidence(requirement, request, renderer_version="3")
        with self.assertRaises(DeterministicEffectContractError):
            MaskedSurfaceRuntimeEvidence.from_mapping(unknown["runtime"])

    def test_new_v1_append_rejects_but_historical_v1_exact_replay_is_unchanged(self) -> None:
        requirement, request, _ = self._chain()
        evidence = _evidence(requirement, request, renderer_version="1")
        empty = InMemoryEpisodeProductionEvidenceAdapter()
        with self.assertRaises(DeterministicEffectContractError):
            append_deterministic_effect_result_chain(
                empty,
                requirement=requirement,
                execution_request=request,
                artifact_evidence=evidence["artifact"],
                runtime_evidence=evidence["runtime"],
                result=evidence["result"],
                idempotency_key="historical-v1-chain",
                created_at="2026-08-30T12:00:00Z",
            )
        self.assertEqual([], empty.list_records("workspace-e1", "run-e1"))

        repository = InMemoryEpisodeProductionEvidenceAdapter()
        chain = subject._validated_chain(
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
        )
        records = subject._chain_records(
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
            result=chain[4],
            idempotency_key="historical-v1-chain",
            created_at="2026-08-30T12:00:00Z",
        )
        repository.append_records(records)
        before = repository.list_records("workspace-e1", "run-e1")
        replay, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
            idempotency_key="historical-v1-chain",
            created_at="2026-08-30T12:00:00Z",
        )
        self.assertTrue(replayed)
        self.assertEqual("1", replay.runtime_evidence.as_dict()["rendererVersion"])
        self.assertEqual(before, repository.list_records("workspace-e1", "run-e1"))
        self.assertEqual(evidence["result"].as_dict(), replay.result.as_dict())
        self.assertEqual(
            evidence["artifact"], replay.artifact_evidence.as_dict()
        )

    def test_sqlite_restart_reads_historical_v1_result_without_rewrite(self) -> None:
        requirement, request, _ = self._chain()
        evidence = _evidence(requirement, request, renderer_version="1")
        chain = subject._validated_chain(
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
        )
        records = subject._chain_records(
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
            result=chain[4],
            idempotency_key="historical-v1-sqlite",
            created_at="2026-08-30T12:00:00Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "evidence.sqlite3"
            first = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            first.append_records(records)
            second = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )
            resolved = resolve_deterministic_effect_result_chain(
                second,
                workspace_ref="workspace-e1",
                production_run_ref="run-e1",
                result_ref=evidence["result"].result_ref,
                result_digest=evidence["result"].payload_digest,
            )
            self.assertEqual("1", resolved.runtime_evidence.as_dict()["rendererVersion"])
            self.assertEqual(evidence["result"].as_dict(), resolved.result.as_dict())
            self.assertEqual(5, len(second.list_records("workspace-e1", "run-e1")))

    def test_artifact_runtime_or_output_tamper_is_rejected(self) -> None:
        requirement, request, evidence = self._chain()
        runtime = deepcopy(evidence["runtime"])
        runtime["executionRequestDigest"] = "f" * 64
        runtime["payloadDigest"] = _digest(
            {key: value for key, value in runtime.items() if key != "payloadDigest"}
        )
        with self.assertRaises(DeterministicEffectStaleInputError):
            validate_masked_surface_execution_evidence(
                requirement=requirement,
                execution_request=request,
                artifact_evidence=evidence["artifact"],
                runtime_evidence=runtime,
            )
        artifact = deepcopy(evidence["artifact"])
        artifact["outputMediaProbe"]["frameCount"] = 23
        artifact["payloadDigest"] = _digest(
            {key: value for key, value in artifact.items() if key != "payloadDigest"}
        )
        with self.assertRaises(DeterministicEffectStaleInputError):
            MaskedSurfaceArtifactEvidence.from_mapping(artifact)
        alternate_runtime = deepcopy(evidence["runtime"])
        alternate_runtime["rendererIdentity"] = "alternate-renderer"
        identity = {
            "v3ExecutionRequestDigest": alternate_runtime[
                "v3ExecutionRequestDigest"
            ],
            "rendererIdentity": alternate_runtime["rendererIdentity"],
            "rendererVersion": alternate_runtime["rendererVersion"],
            "ffmpegIdentity": alternate_runtime["ffmpegIdentity"],
        }
        alternate_runtime["runtimeEvidenceRef"] = (
            "m13-masked-surface-runtime-evidence-"
            + _digest(identity)[:32]
        )
        alternate_runtime["payloadDigest"] = _digest(
            {
                key: value
                for key, value in alternate_runtime.items()
                if key != "payloadDigest"
            }
        )
        with self.assertRaises(DeterministicEffectContractError):
            MaskedSurfaceRuntimeEvidence.from_mapping(alternate_runtime)

    def test_result_only_references_closed_predecessor_evidence(self) -> None:
        _, _, evidence = self._chain()
        result = evidence["result"]
        self.assertIs(type(result), ScratchLightResult)
        value = result.as_dict()
        self.assertEqual(
            set(value),
            {
                "schemaVersion",
                "workspaceRef",
                "productionRunRef",
                "resultRef",
                "effectMode",
                "requirementRef",
                "requirementDigest",
                "executionRequestRef",
                "executionRequestDigest",
                "artifactEvidenceRef",
                "artifactEvidenceDigest",
                "runtimeEvidenceRef",
                "runtimeEvidenceDigest",
                "state",
                "publicationAllowed",
                "payloadDigest",
            },
        )
        self.assertNotIn("Timeline", json.dumps(value, sort_keys=True))
        self.assertEqual(
            parse_deterministic_effect_result(value).as_dict(), value
        )
        forged = deepcopy(value)
        forged["resultRef"] = "forged-result-ref"
        forged["payloadDigest"] = _digest(
            {key: item for key, item in forged.items() if key != "payloadDigest"}
        )
        with self.assertRaises(DeterministicEffectStaleInputError):
            parse_deterministic_effect_result(forged)

    def test_local_exposure_result_type_is_closed(self) -> None:
        _, _, evidence = self._chain(LOCAL_EXPOSURE)
        self.assertIs(type(evidence["result"]), LocalExposureResult)

    def test_atomic_append_resolve_and_exact_replay(self) -> None:
        requirement, request, evidence = self._chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        head = repository.record_journal_head("workspace-e1", "run-e1")
        first, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
            idempotency_key="append-effect-1",
            created_at="2026-08-30T12:00:00Z",
            expected_record_journal_head=head,
        )
        self.assertFalse(replayed)
        self.assertEqual(len(repository.list_records("workspace-e1", "run-e1")), 5)
        resolved = resolve_deterministic_effect_result_chain(
            repository,
            workspace_ref="workspace-e1",
            production_run_ref="run-e1",
            result_ref=evidence["result"].result_ref,
            result_digest=evidence["result"].payload_digest,
        )
        self.assertEqual(first.as_dict(), resolved.as_dict())
        second, replayed = append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
            idempotency_key="append-effect-1",
            created_at="2026-08-30T12:00:00Z",
            expected_record_journal_head=head,
        )
        self.assertTrue(replayed)
        self.assertEqual(second.as_dict(), first.as_dict())

    def test_changed_replay_conflicts(self) -> None:
        requirement, request, evidence = self._chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
            idempotency_key="append-effect-2",
            created_at="2026-08-30T12:00:00Z",
        )
        changed = _evidence(requirement, request, ffmpeg_identity="ffmpeg-7.2")
        with self.assertRaises(IdempotencyConflictError):
            append_deterministic_effect_result_chain(
                repository,
                requirement=requirement,
                execution_request=request,
                artifact_evidence=changed["artifact"],
                runtime_evidence=changed["runtime"],
                result=changed["result"],
                idempotency_key="append-effect-2",
                created_at="2026-08-30T12:00:00Z",
            )

    def test_stale_journal_head_rejects_new_chain(self) -> None:
        requirement, request, evidence = self._chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        with self.assertRaises(StaleInputError):
            append_deterministic_effect_result_chain(
                repository,
                requirement=requirement,
                execution_request=request,
                artifact_evidence=evidence["artifact"],
                runtime_evidence=evidence["runtime"],
                result=evidence["result"],
                idempotency_key="append-effect-stale",
                created_at="2026-08-30T12:00:00Z",
                expected_record_journal_head="f" * 64,
            )

    def test_sqlite_restart_reads_the_exact_chain(self) -> None:
        requirement, request, evidence = self._chain(LOCAL_EXPOSURE)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite"
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            stored, replayed = append_deterministic_effect_result_chain(
                repository,
                requirement=requirement,
                execution_request=request,
                artifact_evidence=evidence["artifact"],
                runtime_evidence=evidence["runtime"],
                result=evidence["result"],
                idempotency_key="append-effect-sqlite",
                created_at="2026-08-30T12:00:00Z",
            )
            self.assertFalse(replayed)
            restarted = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )
            resolved = resolve_deterministic_effect_result_chain(
                restarted,
                workspace_ref="workspace-e1",
                production_run_ref="run-e1",
                result_ref=evidence["result"].result_ref,
                result_digest=evidence["result"].payload_digest,
            )
            self.assertEqual(resolved.as_dict(), stored.as_dict())

    def test_foreign_scope_missing_or_wrong_digest_fails_closed(self) -> None:
        requirement, request, evidence = self._chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        append_deterministic_effect_result_chain(
            repository,
            requirement=requirement,
            execution_request=request,
            artifact_evidence=evidence["artifact"],
            runtime_evidence=evidence["runtime"],
            result=evidence["result"],
            idempotency_key="append-effect-scope",
            created_at="2026-08-30T12:00:00Z",
        )
        for workspace, run_ref, digest in (
            ("workspace-foreign", "run-e1", evidence["result"].payload_digest),
            ("workspace-e1", "run-foreign", evidence["result"].payload_digest),
            ("workspace-e1", "run-e1", "e" * 64),
        ):
            with self.assertRaises(DeterministicEffectJournalError):
                resolve_deterministic_effect_result_chain(
                    repository,
                    workspace_ref=workspace,
                    production_run_ref=run_ref,
                    result_ref=evidence["result"].result_ref,
                    result_digest=digest,
                )


if __name__ == "__main__":
    unittest.main()
