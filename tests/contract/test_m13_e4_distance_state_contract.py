from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production.distance_state import (
    DISTANCE_STATE_RENDERER_IDENTITY,
    DistanceStateContractError,
    DistanceStateExecutionRequest,
    DistanceStateJournalError,
    DistanceStateStaleInputError,
    DistanceStateTransitionRequirement,
    append_distance_state_result_chain,
    build_distance_state_artifact_evidence,
    build_distance_state_execution_request,
    build_distance_state_requirement,
    build_distance_state_result,
    build_distance_state_runtime_evidence,
    distance_state_derived_distance_facts,
    distance_state_schedule_digest,
    resolve_distance_state_result_chain,
    validate_distance_state_execution_evidence,
    validate_distance_state_execution_request_binding,
)
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    _digest,
)


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "m13" / "e4"
RAW = "a" * 64
CONTENT = "sha256:" + RAW
REQUIRED_LABELS = {
    "TECHNICAL_FIXTURE_ONLY",
    "NOT_LIVE_K2",
    "NOT_LIVE_ASSET",
    "NOT_SELECTED",
    "NOT_MASTER",
}


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def public_distance() -> dict:
    return deepcopy(fixture("generic_object_distance.json")["publicRequirement"])


def public_state() -> dict:
    return deepcopy(fixture("generic_visual_state.json")["publicRequirement"])


def resolved_base(public: dict) -> dict:
    return {
        "assetVersionRef": public["basePlateAssetVersionRef"],
        "assetVersionDigest": public["basePlateAssetVersionDigest"],
        "storageKey": "server-private-base",
        "fileDigest": CONTENT,
        "pixelDigest": CONTENT,
        "pixelDigestSpec": "RGBA8/test-only/v1",
        "pixelMode": "RGBA",
        "width": 640,
        "height": 360,
        "frameCount": 10,
        "frameRate": 24,
    }


def resolved_image(reference: str, digest: str, *, role: str) -> dict:
    return {
        "assetVersionRef": reference,
        "assetVersionDigest": digest,
        "storageKey": f"server-private-{role}",
        "fileDigest": CONTENT,
        "pixelDigest": CONTENT,
        "pixelDigestSpec": "RGBA8/test-only/v1",
        "pixelMode": "RGBA",
        "width": 64,
        "height": 64,
    }


def authorities(public: dict) -> tuple[dict, dict | None, dict | None, list[dict]]:
    base = resolved_base(public)
    if public["targetKind"] == "FULL_FRAME":
        return base, None, None, []
    subject = resolved_image(
        public["subjectLayerAssetVersionRef"],
        public["subjectLayerAssetVersionDigest"],
        role="subject",
    )
    mask = resolved_image(
        public["maskAssetVersionRef"],
        public["maskAssetVersionDigest"],
        role="mask",
    )
    variants = [
        resolved_image(
            item["variantAssetVersionRef"],
            item["variantAssetVersionDigest"],
            role=f"variant-{index}",
        )
        for index, item in enumerate(public["visualStateDefinitions"])
        if item["variantAssetVersionRef"] is not None
    ]
    return base, subject, mask, variants


def requirement(public: dict | None = None):
    public = deepcopy(public or public_distance())
    base, subject, mask, variants = authorities(public)
    return build_distance_state_requirement(
        public,
        resolved_base=base,
        resolved_subject=subject,
        resolved_mask=mask,
        resolved_variants=variants,
    )


def combined_public() -> dict:
    public = public_distance()
    state = public_state()
    public.update(
        transitionMode="SCREEN_DISTANCE_AND_VISUAL_STATE",
        startStateRef=state["startStateRef"],
        endStateRef=state["endStateRef"],
        visualStateDefinitions=state["visualStateDefinitions"],
        visualStateSchedule=state["visualStateSchedule"],
    )
    return public


def execution_chain(*, public: dict | None = None, ffmpeg_identity: str = "ffmpeg-pinned"):
    req = requirement(public)
    request = build_distance_state_execution_request(req)
    runtime = build_distance_state_runtime_evidence(
        requirement=req,
        execution_request=request,
        execution_facts={
            "v3ExecutionRequestDigest": "b" * 64,
            "rendererIdentity": DISTANCE_STATE_RENDERER_IDENTITY,
            "rendererVersion": "1",
            "ffmpegIdentity": ffmpeg_identity,
            "executionManifestDigest": "sha256:" + "c" * 64,
        },
    )
    probe = {
        "width": 640,
        "height": 360,
        "frameCount": 10,
        "frameRate": 24,
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }
    output_digest = {
        "fileDigest": "sha256:" + "d" * 64,
        "fileDigestAlgorithm": "sha256",
        "decodedFramePixelDigest": "sha256:" + "e" * 64,
        "decodedFramePixelDigestSpec": (
            "RGBA8/display-identity/frame-major/row-major/"
            "width-height-frame-count-bound/v2"
        ),
        "pixelMode": "RGBA",
        "width": 640,
        "height": 360,
        "frameCount": 10,
        "frameRate": 24,
    }
    artifact = build_distance_state_artifact_evidence(
        requirement=req,
        execution_request=request,
        runtime_evidence=runtime,
        execution_facts={
            "v3ExecutionRequestDigest": "b" * 64,
            "outputByteSize": 1234,
            "outputMediaProbe": probe,
            "outputDigest": output_digest,
            "derivedDistanceFacts": distance_state_derived_distance_facts(req),
            "appliedStateScheduleDigest": distance_state_schedule_digest(req),
        },
    )
    bindings = {
        "workspaceRef": req.workspace_ref,
        "productionRunRef": req.production_run_ref,
        "requirementRef": req.requirement_ref,
        "requirementDigest": req.payload_digest,
        "executionRequestRef": request.execution_request_ref,
        "executionRequestDigest": request.payload_digest,
        "artifactEvidenceRef": artifact.artifact_evidence_ref,
        "artifactEvidenceDigest": artifact.payload_digest,
        "runtimeEvidenceRef": runtime.runtime_evidence_ref,
        "runtimeEvidenceDigest": runtime.payload_digest,
    }
    result = build_distance_state_result(
        requirement=req,
        execution_request=request,
        evidence_bindings=bindings,
        artifact_evidence=artifact,
    )
    return req, request, artifact, runtime, result


class DistanceStateTransitionContractTest(unittest.TestCase):
    def test_technical_fixture_boundaries_are_explicit(self):
        for name in ("generic_object_distance.json", "generic_visual_state.json"):
            value = fixture(name)
            with self.subTest(name=name):
                self.assertTrue(REQUIRED_LABELS.issubset(value["classificationLabels"]))
                self.assertIs(value["publicationAllowed"], False)
                self.assertEqual(
                    value["semanticBoundary"]["distanceSemantics"],
                    "EXACT_SCREEN_SPACE_ONLY",
                )
                self.assertIs(value["semanticBoundary"]["worldDistanceClaim"], False)
                self.assertIs(value["semanticBoundary"]["visualStateIsCanonical"], False)
                serialized = json.dumps(value, ensure_ascii=False).lower()
                self.assertNotIn("/data/k2-technical-evidence", serialized)
                self.assertNotIn("a100", serialized)

    def test_three_closed_modes_and_two_targets_build(self):
        distance = requirement(public_distance()).as_dict()
        state = requirement(public_state()).as_dict()
        combined = requirement(combined_public()).as_dict()
        full = public_distance()
        full.update(
            targetKind="FULL_FRAME",
            subjectLayerAssetVersionRef=None,
            subjectLayerAssetVersionDigest=None,
            maskAssetVersionRef=None,
            maskAssetVersionDigest=None,
        )
        full_value = requirement(full).as_dict()
        self.assertEqual(
            {distance["transitionMode"], state["transitionMode"], combined["transitionMode"]},
            {"SCREEN_DISTANCE", "VISUAL_STATE", "SCREEN_DISTANCE_AND_VISUAL_STATE"},
        )
        self.assertEqual(
            {distance["targetKind"], full_value["targetKind"]},
            {"OVERLAY_LAYER", "FULL_FRAME"},
        )
        self.assertEqual(combined["distanceContract"]["direction"], "APPROACH")
        self.assertEqual(combined["startStateRef"], "technical-state-a")

    def test_unknown_modes_targets_interpolation_and_blend_are_rejected(self):
        cases = {}
        target = public_distance()
        target["targetKind"] = "OBJECT_3D"
        cases["target"] = target
        mode = public_distance()
        mode["transitionMode"] = "FREEFORM"
        cases["transition"] = mode
        interpolation = public_distance()
        interpolation["motionKeyframes"][0]["interpolation"] = "BEZIER"
        cases["interpolation"] = interpolation
        blend = public_distance()
        blend["blendMode"] = "CUSTOM_SHADER"
        cases["blend"] = blend
        for label, public in cases.items():
            with self.subTest(label=label), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_normalized_permille_is_exact_and_world_coordinates_are_closed(self):
        normalized = public_distance()
        normalized["coordinateSpace"] = "NORMALIZED_PERMILLE"
        for keyframe, x in zip(normalized["motionKeyframes"], (0, 500)):
            keyframe.update(
                x=x,
                y=500,
                perspectiveQuad=[0, 0, 1000, 0, 1000, 1000, 0, 1000],
            )
        normalized["distanceContract"].update(
            startValue=640,
            endValue=320,
            referenceX=1000,
            referenceY=500,
        )
        self.assertEqual(
            requirement(normalized).as_dict()["coordinateSpace"],
            "NORMALIZED_PERMILLE",
        )
        for coordinate in (
            "WORLD_METERS",
            "WORLD_CENTIMETERS",
            "UNSPECIFIED_3D",
            "NATURAL_LANGUAGE",
        ):
            public = public_distance()
            public["coordinateSpace"] = coordinate
            with self.subTest(coordinate=coordinate), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_approach_recede_lateral_and_custom_exact_are_derived(self):
        cases = []
        approach = public_distance()
        cases.append(("APPROACH", approach))

        recede = public_distance()
        recede["motionKeyframes"][0]["x"] = 500
        recede["motionKeyframes"][-1]["x"] = 100
        recede["distanceContract"].update(
            startValue=100, endValue=500, direction="RECEDE"
        )
        cases.append(("RECEDE", recede))

        lateral = public_distance()
        lateral["motionKeyframes"][0].update(x=100, y=300)
        lateral["motionKeyframes"][-1].update(
            x=500,
            y=300,
            scaleXNumerator=1,
            scaleYNumerator=1,
        )
        lateral["distanceContract"].update(
            startValue=200,
            endValue=200,
            direction="LATERAL",
            referenceX=300,
            referenceY=300,
        )
        cases.append(("LATERAL", lateral))

        custom = public_distance()
        custom["distanceContract"]["direction"] = "CUSTOM_EXACT"
        cases.append(("CUSTOM_EXACT", custom))

        for direction, public in cases:
            with self.subTest(direction=direction):
                value = requirement(public).as_dict()
                self.assertEqual(value["distanceContract"]["direction"], direction)

    def test_relative_scale_approach_and_recede_are_exact(self):
        approach = public_distance()
        approach["distanceContract"] = {
            "metric": "RELATIVE_SCALE_PERMILLE",
            "startValue": 1000,
            "endValue": 2000,
            "tolerance": 0,
            "direction": "APPROACH",
            "referenceX": None,
            "referenceY": None,
        }
        self.assertEqual(
            requirement(approach).as_dict()["distanceContract"]["endValue"], 2000
        )
        recede = deepcopy(approach)
        recede["motionKeyframes"][0].update(
            scaleXNumerator=2, scaleYNumerator=2
        )
        recede["motionKeyframes"][-1].update(
            scaleXNumerator=1, scaleYNumerator=1
        )
        recede["distanceContract"].update(
            startValue=2000, endValue=1000, direction="RECEDE"
        )
        self.assertEqual(
            requirement(recede).as_dict()["distanceContract"]["direction"],
            "RECEDE",
        )

    def test_distance_declaration_mismatch_and_natural_language_are_rejected(self):
        mismatch = public_distance()
        mismatch["distanceContract"]["endValue"] = 101
        with self.assertRaises(DistanceStateContractError):
            requirement(mismatch)

        for field, value in (
            ("direction", "靠近一点"),
            ("metric", "向前约45厘米"),
        ):
            public = public_distance()
            public["distanceContract"][field] = value
            with self.subTest(field=field), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

        public = public_distance()
        public["naturalLanguageDistance"] = "走远一些"
        with self.assertRaises(DistanceStateContractError):
            requirement(public)

    def test_motion_keyframes_require_exact_first_last_and_strict_order(self):
        cases = {}
        missing_start = public_distance()
        missing_start["motionKeyframes"][0]["frame"] = 1
        cases["missing-start"] = missing_start
        missing_end = public_distance()
        missing_end["motionKeyframes"][-1]["frame"] = 8
        cases["missing-end"] = missing_end
        duplicate = public_distance()
        duplicate["motionKeyframes"][-1]["frame"] = 0
        cases["duplicate"] = duplicate
        reverse = public_distance()
        reverse["motionKeyframes"] = list(reversed(reverse["motionKeyframes"]))
        cases["reverse"] = reverse
        for label, public in cases.items():
            with self.subTest(label=label), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_rationals_floats_nan_and_expressions_are_rejected(self):
        cases = {}
        zero_denominator = public_distance()
        zero_denominator["motionKeyframes"][0]["scaleXDenominator"] = 0
        cases["zero-denominator"] = zero_denominator
        not_normalized = public_distance()
        not_normalized["motionKeyframes"][0].update(
            scaleXNumerator=2, scaleXDenominator=2
        )
        cases["not-normalized"] = not_normalized
        floating = public_distance()
        floating["motionKeyframes"][0]["x"] = 100.0
        cases["float"] = floating
        nan = public_distance()
        nan["motionKeyframes"][0]["x"] = float("nan")
        cases["nan"] = nan
        expression = public_distance()
        expression["motionKeyframes"][0]["xExpression"] = "frame * 4"
        cases["expression"] = expression
        for label, public in cases.items():
            with self.subTest(label=label), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_perspective_is_integer_bounded_and_convex(self):
        out_of_bounds = public_distance()
        out_of_bounds["motionKeyframes"][0]["perspectiveQuad"][0] = 3201
        degenerate = public_distance()
        degenerate["motionKeyframes"][0]["perspectiveQuad"] = [
            0,
            0,
            64,
            0,
            0,
            64,
            64,
            64,
        ]
        string_matrix = public_distance()
        string_matrix["motionKeyframes"][0]["perspectiveQuad"] = (
            "0,0:64,0:64,64:0,64"
        )
        for label, public in (
            ("out-of-bounds", out_of_bounds),
            ("non-convex", degenerate),
            ("matrix-string", string_matrix),
        ):
            with self.subTest(label=label), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_state_identity_schedule_and_variant_authority_are_closed(self):
        duplicate = public_state()
        duplicate["visualStateDefinitions"][1]["stateRef"] = (
            duplicate["visualStateDefinitions"][0]["stateRef"]
        )
        gap = public_state()
        gap["visualStateSchedule"][1]["startFrameInclusive"] = 6
        overlap = public_state()
        overlap["visualStateSchedule"][1]["startFrameInclusive"] = 4
        incomplete = public_state()
        incomplete["visualStateSchedule"][-1]["endFrameExclusive"] = 9
        variant_curve = public_state()
        variant_curve["visualStateSchedule"][0]["transitionInterpolation"] = (
            "LINEAR"
        )
        for label, public in (
            ("duplicate-state", duplicate),
            ("schedule-gap", gap),
            ("schedule-overlap", overlap),
            ("schedule-incomplete", incomplete),
            ("variant-non-step", variant_curve),
        ):
            with self.subTest(label=label), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

        public = public_state()
        base, subject, mask, variants = authorities(public)
        variants[0]["assetVersionDigest"] = "f" * 64
        with self.assertRaises(DistanceStateStaleInputError):
            build_distance_state_requirement(
                public,
                resolved_base=base,
                resolved_subject=subject,
                resolved_mask=mask,
                resolved_variants=variants,
            )

    def test_target_kind_and_exact_asset_authority_are_fail_closed(self):
        overlay = public_distance()
        base, _, mask, variants = authorities(overlay)
        with self.assertRaises(DistanceStateContractError):
            build_distance_state_requirement(
                overlay,
                resolved_base=base,
                resolved_subject=None,
                resolved_mask=mask,
                resolved_variants=variants,
            )

        full = public_distance()
        full["targetKind"] = "FULL_FRAME"
        with self.assertRaises(DistanceStateContractError):
            requirement(full)

        for label, index, field in (
            ("base", 0, "assetVersionDigest"),
            ("subject", 1, "assetVersionDigest"),
            ("mask", 2, "assetVersionDigest"),
        ):
            public = public_distance()
            values = list(authorities(public))
            resolved = values[index]
            assert isinstance(resolved, dict)
            resolved[field] = "f" * 64
            with self.subTest(label=label), self.assertRaises(
                (DistanceStateContractError, DistanceStateStaleInputError)
            ):
                build_distance_state_requirement(
                    public,
                    resolved_base=values[0],
                    resolved_subject=values[1],
                    resolved_mask=values[2],
                    resolved_variants=values[3],
                )

    def test_client_paths_filters_argv_and_free_properties_are_rejected(self):
        for field, value in (
            ("absolutePath", "/private/source.png"),
            ("storageKey", "caller/storage"),
            ("ffmpegFilter", "overlay=0:0"),
            ("ffmpegArgv", ["-i", "source"]),
            ("shellCommand", "true"),
            ("canonicalMutations", 0),
            ("publicationAllowed", False),
        ):
            public = public_distance()
            public[field] = value
            with self.subTest(field=field), self.assertRaises(
                DistanceStateContractError
            ):
                requirement(public)

    def test_requirement_and_v4_request_are_sealed_against_drift(self):
        req = requirement()
        drifted_requirement = req.as_dict()
        drifted_requirement["motionKeyframes"][-1]["x"] = 499
        with self.assertRaises(DistanceStateStaleInputError):
            DistanceStateTransitionRequirement.from_mapping(drifted_requirement)

        request = build_distance_state_execution_request(req)
        drifted_request = request.as_dict()
        drifted_request["transitionSpec"]["motionKeyframes"][-1]["x"] = 499
        unsigned = deepcopy(drifted_request)
        unsigned.pop("payloadDigest")
        drifted_request["payloadDigest"] = _digest(unsigned)
        with self.assertRaises(DistanceStateStaleInputError):
            DistanceStateExecutionRequest.from_mapping(drifted_request)
        self.assertEqual(
            validate_distance_state_execution_request_binding(request, req).as_dict(),
            request.as_dict(),
        )

    def test_execution_evidence_is_exactly_bound_and_fixed_non_publication(self):
        chain = execution_chain(public=combined_public())
        validated = validate_distance_state_execution_evidence(
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
        )
        self.assertEqual(validated[0].as_dict(), chain[2].as_dict())
        result = chain[4].as_dict()
        self.assertEqual(result["state"], "COMPOSED_CANDIDATE")
        self.assertEqual(result["assetAdmissionState"], "NOT_ADMITTED")
        self.assertEqual(result["masterState"], "NOT_CREATED")
        self.assertEqual(result["exportState"], "NOT_CREATED")
        self.assertIs(result["publicationAllowed"], False)
        self.assertNotIn("successorTimelineVersionRef", result)
        self.assertNotIn("previewCandidateRef", result)

    def test_output_media_facts_must_match_the_requirement_on_build_and_replay(self):
        chain = execution_chain(public=combined_public())
        artifact = chain[2].as_dict()
        drifted_probe = deepcopy(artifact["outputMediaProbe"])
        drifted_output = deepcopy(artifact["outputDigest"])
        for media in (drifted_probe, drifted_output):
            media.update(width=320, height=180, frameCount=5, frameRate=30)

        with self.assertRaises(DistanceStateStaleInputError):
            build_distance_state_artifact_evidence(
                requirement=chain[0],
                execution_request=chain[1],
                runtime_evidence=chain[3],
                execution_facts={
                    "v3ExecutionRequestDigest": artifact[
                        "v3ExecutionRequestDigest"
                    ],
                    "outputByteSize": artifact["outputByteSize"],
                    "outputMediaProbe": drifted_probe,
                    "outputDigest": drifted_output,
                    "derivedDistanceFacts": artifact[
                        "derivedDistanceFacts"
                    ],
                    "appliedStateScheduleDigest": artifact[
                        "appliedStateScheduleDigest"
                    ],
                },
            )

        drifted = deepcopy(artifact)
        drifted["outputMediaProbe"] = drifted_probe
        drifted["outputDigest"] = drifted_output
        drifted.pop("payloadDigest")
        drifted["payloadDigest"] = _digest(drifted)
        with self.assertRaises(DistanceStateStaleInputError):
            validate_distance_state_execution_evidence(
                requirement=chain[0],
                execution_request=chain[1],
                artifact_evidence=drifted,
                runtime_evidence=chain[3],
            )

    def test_atomic_five_record_journal_replay_and_sqlite_restart(self):
        chain = execution_chain(public=combined_public())
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        stored, replayed = append_distance_state_result_chain(
            repository,
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
            result=chain[4],
            idempotency_key="distance-state-chain",
            created_at="2026-08-31T00:00:00Z",
        )
        self.assertFalse(replayed)
        self.assertEqual(
            len(repository.list_records("workspace-e4-fixture", "run-e4-fixture")),
            5,
        )
        exact, replayed = append_distance_state_result_chain(
            repository,
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
            result=chain[4],
            idempotency_key="distance-state-chain",
            created_at="2026-08-31T00:00:00Z",
        )
        self.assertTrue(replayed)
        self.assertEqual(exact.as_dict(), stored.as_dict())

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evidence.sqlite"
            sqlite = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            append_distance_state_result_chain(
                sqlite,
                requirement=chain[0],
                execution_request=chain[1],
                artifact_evidence=chain[2],
                runtime_evidence=chain[3],
                result=chain[4],
                idempotency_key="distance-state-sqlite",
                created_at="2026-08-31T00:00:00Z",
            )
            restarted = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )
            resolved = resolve_distance_state_result_chain(
                restarted,
                workspace_ref="workspace-e4-fixture",
                production_run_ref="run-e4-fixture",
                result_ref=chain[4].result_ref,
                result_digest=chain[4].payload_digest,
            )
            self.assertEqual(resolved.result.as_dict(), chain[4].as_dict())

    def test_changed_journal_replay_cross_chain_and_digest_tamper_are_rejected(self):
        chain = execution_chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        append_distance_state_result_chain(
            repository,
            requirement=chain[0],
            execution_request=chain[1],
            artifact_evidence=chain[2],
            runtime_evidence=chain[3],
            result=chain[4],
            idempotency_key="distance-state-conflict",
            created_at="2026-08-31T00:00:00Z",
        )
        changed = execution_chain(ffmpeg_identity="ffmpeg-other")
        with self.assertRaises(IdempotencyConflictError):
            append_distance_state_result_chain(
                repository,
                requirement=changed[0],
                execution_request=changed[1],
                artifact_evidence=changed[2],
                runtime_evidence=changed[3],
                result=changed[4],
                idempotency_key="distance-state-conflict",
                created_at="2026-08-31T00:00:00Z",
            )
        with self.assertRaises(DistanceStateJournalError):
            resolve_distance_state_result_chain(
                repository,
                workspace_ref="workspace-e4-fixture",
                production_run_ref="run-e4-fixture",
                result_ref=chain[4].result_ref,
                result_digest="f" * 64,
            )

        state_chain = execution_chain(public=public_state())
        with self.assertRaises(DistanceStateStaleInputError):
            validate_distance_state_execution_evidence(
                requirement=chain[0],
                execution_request=chain[1],
                artifact_evidence=state_chain[2],
                runtime_evidence=state_chain[3],
            )


if __name__ == "__main__":
    unittest.main()
