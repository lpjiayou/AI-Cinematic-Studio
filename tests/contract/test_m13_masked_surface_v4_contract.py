from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    IMAGE_PIXEL_DIGEST_SPEC,
    PCM_CONTENT_DIGEST_SPEC,
    file_digest,
)
from services.v4_platform import masked_surface_effects as subject


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def seal(value: dict) -> dict:
    result = deepcopy(value)
    result["payloadDigest"] = sha256(canonical(result)).hexdigest()
    return result


def request_ref(requirement_ref: str, requirement_digest: str) -> str:
    identity = {
        "schemaVersion": "v5.m13-masked-surface-execution-request-identity.v1",
        "requirementRef": requirement_ref,
        "requirementDigest": requirement_digest,
    }
    return "m13-masked-surface-execution-" + sha256(canonical(identity)).hexdigest()[:32]


class FakeV3Executor:
    def __init__(self, root: Path, *, drift: str | None = None) -> None:
        self.root = root
        self.drift = drift
        self.request: dict | None = None

    def execute(self, execution_request: dict) -> dict:
        request = deepcopy(execution_request)
        self.request = request
        workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
        run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
        key = (
            f"{workspace}/{run}/masked-surface/"
            f"masked-surface-v{subject.MASKED_SURFACE_RENDERER_VERSION}-"
            f"{request['payloadDigest']}.mp4"
        )
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"deterministic-masked-surface-output")
        identity = {
            "ffmpegIdentity": "ffmpeg test identity",
            "rendererIdentity": subject.MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": subject.MASKED_SURFACE_RENDERER_VERSION,
        }
        result = {
            "internalPath": str(path.resolve()),
            "outputStorageKey": key,
            "outputByteSize": path.stat().st_size,
            "outputMediaProbe": deepcopy(request["output"]),
            "outputDigest": {
                "fileDigest": file_digest(path),
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "c" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": request["output"]["width"],
                "height": request["output"]["height"],
                "frameCount": request["output"]["frameCount"],
                "frameRate": request["output"]["frameRate"],
            },
            "rendererIdentity": subject.MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": subject.MASKED_SURFACE_RENDERER_VERSION,
            "ffmpegIdentity": identity["ffmpegIdentity"],
            "runtimeEvidenceDigest": "sha256:" + sha256(canonical(identity)).hexdigest(),
            "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
            "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
            "v3ExecutionRequestDigest": request["payloadDigest"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "publicationAllowed": False,
        }
        if self.drift == "frame-count":
            result["outputMediaProbe"]["frameCount"] += 1
        elif self.drift == "pixel-digest":
            result["outputDigest"]["decodedFramePixelDigest"] = "sha256:" + "d" * 64
        elif self.drift == "runtime":
            result["runtimeEvidenceDigest"] = "sha256:" + "0" * 64
        elif self.drift == "lineage":
            result["requirementDigest"] = "f" * 64
        elif self.drift == "renderer-v1":
            result["rendererVersion"] = subject.MASKED_SURFACE_RENDERER_VERSION_V1
        elif self.drift == "renderer-v2":
            result["rendererVersion"] = subject.MASKED_SURFACE_RENDERER_VERSION_V2
        return result

    def compose_timeline_preview_v2(self, request: dict) -> dict:
        self.request = deepcopy(request)
        workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
        run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
        key = f"{workspace}/{run}/composition/preview-{request['payloadDigest']}.mp4"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"combined-effect-preview-output")
        renderer_version = {
            subject.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION:
                subject.EFFECT_PREVIEW_RENDERER_VERSION,
            subject.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V3:
                subject.EFFECT_PREVIEW_RENDERER_VERSION_V3,
            subject.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4:
                subject.EFFECT_PREVIEW_RENDERER_VERSION_V4,
        }[request["schemaVersion"]]
        identity = {
            "ffmpegIdentity": "ffmpeg combined test identity",
            "rendererIdentity": subject.EFFECT_PREVIEW_RENDERER_IDENTITY,
            "rendererVersion": renderer_version,
        }
        output = request["output"]
        probe = {
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
        }
        return {
            "internalPath": str(path.resolve()),
            "outputStorageKey": key,
            "outputByteSize": path.stat().st_size,
            "outputMediaProbe": probe,
            "outputDigest": {
                "fileDigest": file_digest(path),
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "e" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": probe["width"],
                "height": probe["height"],
                "frameCount": probe["frameCount"],
                "frameRate": probe["frameRate"],
                "pcmContentDigest": "f" * 64,
                "pcmDigestSpec": PCM_CONTENT_DIGEST_SPEC,
                "sampleRate": probe["sampleRate"],
                "channelCount": probe["channelCount"],
                "sampleCount": probe["sampleCount"],
            },
            "rendererIdentity": identity["rendererIdentity"],
            "rendererVersion": identity["rendererVersion"],
            "ffmpegIdentity": identity["ffmpegIdentity"],
            "runtimeEvidenceDigest": "sha256:" + sha256(canonical(identity)).hexdigest(),
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["payloadDigest"],
            "timelineVersionRef": request["timelineVersionRef"],
            "timelineVersionDigest": request["timelineVersionDigest"],
            "inputBindingsDigest": request["inputBindingsDigest"],
            "effectResultBindings": deepcopy(request["effectResultBindings"]),
            "glyphRequirementBinding": deepcopy(request["glyphRequirementBinding"]),
            "effectBindingsDigest": request["effectBindingsDigest"],
            "mixRequestRef": request["audioMix"]["mixRequestRef"],
            "mixRequestDigest": request["audioMix"]["mixRequestDigest"],
            "subtitleManifestRef": request["subtitleManifest"]["subtitleManifestRef"],
            "subtitleManifestDigest": request["subtitleManifest"]["subtitleManifestDigest"],
            "publicationAllowed": False,
        }


class MaskedSurfaceV4ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "inputs").mkdir()
        self.base_path = self.root / "inputs/base.mp4"
        self.mask_path = self.root / "inputs/mask.png"
        self.base_path.write_bytes(b"base-video")
        self.mask_path.write_bytes(b"mask-png")
        self.request = self._request()
        self.assets = self._assets()

    def _request(self) -> dict:
        requirement_ref = "masked-effect-requirement-1"
        requirement_digest = "1" * 64
        return seal(
            {
                "schemaVersion": subject.MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
                "executionRequestRef": request_ref(requirement_ref, requirement_digest),
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
                "requirementSchemaVersion": subject.SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION,
                "requirementRef": requirement_ref,
                "requirementDigest": requirement_digest,
                "effectMode": "LIGHT_SWEEP",
                "targetShot": {
                    "shotRef": "shot-2",
                    "shotVersionRef": "shot-version-3",
                    "shotVersionDigest": "2" * 64,
                },
                "basePlate": {
                    "assetVersionRef": "base-version-1",
                    "assetVersionDigest": "3" * 64,
                    "fileDigest": file_digest(self.base_path),
                    "pixelDigest": "sha256:" + "a" * 64,
                },
                "mask": {
                    "assetVersionRef": "mask-version-1",
                    "assetVersionDigest": "4" * 64,
                    "fileDigest": file_digest(self.mask_path),
                    "pixelDigest": "sha256:" + "b" * 64,
                },
                "frameRangeStartInclusive": 1,
                "frameRangeEndExclusive": 5,
                "explicitSchedule": [
                    {
                        "startFrameInclusive": 1,
                        "endFrameExclusive": 5,
                        "enabled": True,
                        "interpolation": "STEP",
                    }
                ],
                "trajectoryKeyframes": [
                    {
                        "frame": 1,
                        "xPermille": 100,
                        "yPermille": 100,
                        "interpolation": "LINEAR",
                    },
                    {
                        "frame": 4,
                        "xPermille": 500,
                        "yPermille": 500,
                        "interpolation": "STEP",
                    },
                ],
                "intensityCurve": [
                    {"frame": 1, "valuePermille": 200, "interpolation": "LINEAR"},
                    {"frame": 4, "valuePermille": 900, "interpolation": "STEP"},
                ],
                "exposureCurve": [
                    {"frame": 1, "valueMilliStops": 0, "interpolation": "LINEAR"},
                    {"frame": 4, "valueMilliStops": 750, "interpolation": "STEP"},
                ],
                "position": {"xPermille": 100, "yPermille": 100},
                "scale": {"xPermille": 200, "yPermille": 200},
                "perspective": {"mode": "NONE", "quadPermille": []},
                "blendMode": "SCREEN",
                "layer": 1,
                "publicationAllowed": False,
            }
        )

    def _assets(self) -> dict:
        return {
            "base-version-1": {
                **self.request["basePlate"],
                "storageKey": "inputs/base.mp4",
                "pixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "width": 640,
                "height": 360,
                "frameCount": 6,
                "frameRate": 24,
                "pixelFormat": "yuv420p",
            },
            "mask-version-1": {
                **self.request["mask"],
                "storageKey": "inputs/mask.png",
                "pixelDigestSpec": IMAGE_PIXEL_DIGEST_SPEC,
                "pixelMode": "RGBA",
                "width": 640,
                "height": 360,
            },
        }

    def _decoded(self, path: Path) -> dict:
        candidate = Path(path)
        if candidate == self.base_path:
            return {
                "fileDigest": file_digest(candidate),
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "a" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": 640,
                "height": 360,
                "frameCount": 6,
            }
        return {
            "fileDigest": file_digest(candidate),
            "fileDigestAlgorithm": "sha256",
            "decodedFramePixelDigest": "sha256:" + "c" * 64,
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
            "pixelMode": "RGBA",
            "width": 640,
            "height": 360,
            "frameCount": 6,
        }

    def _image(self, path: Path) -> dict:
        self.assertEqual(Path(path), self.mask_path)
        return {
            "width": 640,
            "height": 360,
            "source_mode": None,
            "pixel_mode": "RGBA",
            "pixel_digest": "sha256:" + "b" * 64,
            "pixel_digest_spec": IMAGE_PIXEL_DIGEST_SPEC,
        }

    def _execute(self, fake: FakeV3Executor, *, request: dict | None = None, assets: dict | None = None) -> dict:
        executor = subject.V4MaskedSurfaceEffectExecutor(self.root, fake)
        with (
            mock.patch.object(
                subject,
                "decoded_frame_pixel_digest_metadata",
                side_effect=self._decoded,
            ),
            mock.patch.object(subject, "image_digest_metadata", side_effect=self._image),
        ):
            return executor.execute(
                request or self.request,
                resolved_asset_versions=assets or self.assets,
            )

    def _effect_binding(self, index: int, mode: str) -> dict:
        return {
            "clipRef": f"effect-clip-{index}",
            "clipDigest": f"{index + 1:x}" * 64,
            "effectMode": mode,
            "requirementRef": f"effect-requirement-{index}",
            "requirementDigest": f"{index + 3:x}" * 64,
            "resultRef": f"effect-result-{index}",
            "resultDigest": f"{index + 5:x}" * 64,
            "executionRequestRef": f"effect-execution-{index}",
            "executionRequestDigest": f"{index + 7:x}" * 64,
            "artifactEvidenceRef": f"effect-artifact-{index}",
            "artifactEvidenceDigest": f"{index + 9:x}" * 64,
            "runtimeEvidenceRef": f"effect-runtime-{index}",
            "runtimeEvidenceDigest": f"{index + 11:x}" * 64,
            "frameRangeStartInclusive": 1,
            "frameRangeEndExclusive": 5,
        }

    def _preview_command(self) -> dict:
        return {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "timelineVersionRef": "timeline-version-3",
            "timelineVersionDigest": "d" * 64,
            "baseVideo": {
                "assetVersionRef": "base-version-1",
                "assetVersionDigest": "3" * 64,
                "fileDigest": file_digest(self.base_path),
                "pixelDigest": "sha256:" + "a" * 64,
                "width": 640,
                "height": 360,
                "frameCount": 6,
                "frameRate": {"numerator": 24, "denominator": 1},
            },
            "effectResultBindings": [
                self._effect_binding(0, "LIGHT_SWEEP"),
                self._effect_binding(1, "LOCAL_EXPOSURE"),
            ],
            "glyphRequirementBinding": {
                "clipRef": "effect-clip-glyph",
                "clipDigest": "c" * 64,
                "requirementRef": "glyph-requirement-1",
                "requirementDigest": "b" * 64,
            },
            "audioMix": {
                "mixRequestRef": "mix-request-1",
                "mixRequestDigest": "a" * 64,
            },
            "subtitleManifest": {
                "subtitleManifestRef": "subtitle-manifest-1",
                "subtitleManifestDigest": "9" * 64,
            },
            "output": {
                "width": 640,
                "height": 360,
                "frameRate": {"numerator": 24, "denominator": 1},
                "totalFrames": 6,
                "sampleRate": 48_000,
                "channelCount": 2,
                "durationSamples": 12_000,
                "container": "mp4",
                "videoCodec": "h264",
                "pixelFormat": "yuv420p",
                "audioCodec": "aac",
                "audioBitRate": 128_000,
            },
        }

    def _preview_resolved(self, command: dict) -> dict:
        return {
            "baseVideo": deepcopy(self.assets["base-version-1"]),
            "effectExecutions": {
                item["resultRef"]: {} for item in command["effectResultBindings"]
            },
            "glyphExecution": {},
        }

    def test_executes_closed_v3_projection_and_returns_path_free_typed_evidence(self) -> None:
        fake = FakeV3Executor(self.root)
        evidence = self._execute(fake)
        self.assertEqual(
            set(evidence), {"artifactEvidence", "runtimeEvidence", "evidenceBindings"}
        )
        artifact = evidence["artifactEvidence"]
        runtime = evidence["runtimeEvidence"]
        bindings = evidence["evidenceBindings"]
        self.assertEqual(
            artifact["schemaVersion"],
            subject.MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(
            runtime["schemaVersion"],
            subject.MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(bindings["artifactEvidenceDigest"], artifact["payloadDigest"])
        self.assertEqual(bindings["runtimeEvidenceDigest"], runtime["payloadDigest"])
        self.assertFalse(runtime["gpuUsed"])
        projection = json.dumps(evidence, sort_keys=True)
        for forbidden in ("internalPath", "storageKey", "argv", "filter"):
            self.assertNotIn(forbidden, projection)
        self.assertIsNotNone(fake.request)
        assert fake.request is not None
        self.assertEqual(fake.request["basePlate"]["storageKey"], "inputs/base.mp4")
        self.assertEqual(fake.request["mask"]["storageKey"], "inputs/mask.png")
        self.assertEqual(fake.request["output"]["frameCount"], 6)

    def test_rejects_request_seal_drift_and_any_client_extension(self) -> None:
        drift = deepcopy(self.request)
        drift["layer"] = 2
        with self.assertRaises(subject.MaskedSurfaceRequestValidationError):
            self._execute(FakeV3Executor(self.root), request=drift)
        extended = deepcopy(self.request)
        extended["filter"] = "arbitrary"
        extended = seal({key: value for key, value in extended.items() if key != "payloadDigest"})
        with self.assertRaises(subject.MaskedSurfaceRequestValidationError):
            self._execute(FakeV3Executor(self.root), request=extended)

    def test_rejects_server_asset_binding_drift_and_actual_file_tamper(self) -> None:
        for asset_ref in ("base-version-1", "mask-version-1"):
            with self.subTest(asset_ref=asset_ref):
                drift = deepcopy(self.assets)
                drift[asset_ref]["assetVersionDigest"] = "9" * 64
                with self.assertRaises(subject.MaskedSurfaceAssetResolutionError):
                    self._execute(FakeV3Executor(self.root), assets=drift)
        self.base_path.write_bytes(b"tampered-base")
        with self.assertRaises(subject.MaskedSurfaceAssetResolutionError):
            self._execute(FakeV3Executor(self.root))

    def test_rejects_missing_base_plate_and_mask_assets(self) -> None:
        for missing_ref in ("base-version-1", "mask-version-1"):
            with self.subTest(missing_ref=missing_ref):
                assets = {
                    ref: deepcopy(asset)
                    for ref, asset in self.assets.items()
                    if ref != missing_ref
                }
                with self.assertRaises(subject.MaskedSurfaceAssetResolutionError):
                    self._execute(FakeV3Executor(self.root), assets=assets)

    def test_rejects_effect_frame_range_beyond_base_plate(self) -> None:
        request = deepcopy(self.request)
        request["frameRangeEndExclusive"] = 7
        request["explicitSchedule"][-1]["endFrameExclusive"] = 7
        request["trajectoryKeyframes"][-1]["frame"] = 6
        request["intensityCurve"][-1]["frame"] = 6
        request["exposureCurve"][-1]["frame"] = 6
        request = seal(
            {key: value for key, value in request.items() if key != "payloadDigest"}
        )
        with self.assertRaises(subject.MaskedSurfaceAssetResolutionError):
            self._execute(FakeV3Executor(self.root), request=request)

    def test_rejects_v3_media_digest_runtime_and_lineage_drift(self) -> None:
        for drift in (
            "frame-count",
            "pixel-digest",
            "runtime",
            "lineage",
            "renderer-v1",
            "renderer-v2",
        ):
            with self.subTest(drift=drift):
                with self.assertRaises(subject.MaskedSurfaceExecutionError):
                    self._execute(FakeV3Executor(self.root, drift=drift))

    def test_runtime_reader_accepts_v1_v2_v3_and_refs_do_not_collide(self) -> None:
        evidence = self._execute(FakeV3Executor(self.root))
        runtime_v3 = evidence["runtimeEvidence"]
        self.assertEqual(
            runtime_v3,
            subject.validate_masked_surface_runtime_evidence(runtime_v3),
        )
        def with_version(version: str) -> dict:
            runtime = deepcopy(runtime_v3)
            runtime["rendererVersion"] = version
            runtime["runtimeEvidenceRef"] = (
                "m13-masked-surface-runtime-evidence-"
                + sha256(
                    canonical(
                        {
                            "v3ExecutionRequestDigest": runtime[
                                "v3ExecutionRequestDigest"
                            ],
                            "rendererIdentity": runtime["rendererIdentity"],
                            "rendererVersion": runtime["rendererVersion"],
                            "ffmpegIdentity": runtime["ffmpegIdentity"],
                        }
                    )
                ).hexdigest()[:32]
            )
            return seal(
                {
                    key: value
                    for key, value in runtime.items()
                    if key != "payloadDigest"
                }
            )

        runtime_v1 = with_version(subject.MASKED_SURFACE_RENDERER_VERSION_V1)
        runtime_v2 = with_version(subject.MASKED_SURFACE_RENDERER_VERSION_V2)
        for runtime in (runtime_v1, runtime_v2):
            self.assertEqual(
                runtime,
                subject.validate_masked_surface_runtime_evidence(runtime),
            )
        self.assertEqual(
            3,
            len(
                {
                    runtime_v1["runtimeEvidenceRef"],
                    runtime_v2["runtimeEvidenceRef"],
                    runtime_v3["runtimeEvidenceRef"],
                }
            ),
        )
        unknown = with_version("4")
        with self.assertRaises(subject.MaskedSurfaceExecutionError):
            subject.validate_masked_surface_runtime_evidence(unknown)

    def test_v2_v3_dependency_aliases_measure_only_version_bound_artifacts(
        self,
    ) -> None:
        fake = FakeV3Executor(self.root)
        evidence = self._execute(fake)
        assert fake.request is not None
        artifact = evidence["artifactEvidence"]
        runtime_v3 = evidence["runtimeEvidence"]
        workspace = sha256(artifact["workspaceRef"].encode()).hexdigest()[:20]
        run = sha256(artifact["productionRunRef"].encode()).hexdigest()[:20]
        legacy_key = (
            f"{workspace}/{run}/masked-surface/"
            f"masked-surface-{artifact['v3ExecutionRequestDigest']}.mp4"
        )
        legacy_path = self.root / legacy_key
        legacy_path.write_bytes(b"historical-v1-artifact-must-not-be-opened")
        output = artifact["outputDigest"]
        probe = artifact["outputMediaProbe"]
        storage = {
            "artifactEvidenceRef": artifact["artifactEvidenceRef"],
            "artifactEvidenceDigest": artifact["payloadDigest"],
            "storageKey": legacy_key,
            "fileDigest": output["fileDigest"],
            "pixelDigest": output["decodedFramePixelDigest"],
            "pixelDigestSpec": output["decodedFramePixelDigestSpec"],
            "width": output["width"],
            "height": output["height"],
            "frameCount": output["frameCount"],
            "frameRate": output["frameRate"],
            "pixelFormat": probe["pixelFormat"],
        }
        identity = {
            "workspaceRef": artifact["workspaceRef"],
            "productionRunRef": artifact["productionRunRef"],
            "payloadDigest": artifact["v3ExecutionRequestDigest"],
        }
        for version in (
            subject.MASKED_SURFACE_RENDERER_VERSION_V2,
            subject.MASKED_SURFACE_RENDERER_VERSION_V3,
        ):
            with self.subTest(renderer_version=version):
                runtime = deepcopy(runtime_v3)
                runtime["rendererVersion"] = version
                expected_key = subject._expected_output_storage_key(
                    identity, renderer_version=version
                )
                expected_path = self.root / expected_key
                expected_path.parent.mkdir(parents=True, exist_ok=True)
                expected_path.write_bytes(b"deterministic-masked-surface-output")
                with mock.patch.object(
                    subject,
                    "decoded_frame_pixel_digest_metadata",
                    return_value={
                        "fileDigest": output["fileDigest"],
                        "decodedFramePixelDigest": output[
                            "decodedFramePixelDigest"
                        ],
                        "decodedFramePixelDigestSpec": output[
                            "decodedFramePixelDigestSpec"
                        ],
                        "width": output["width"],
                        "height": output["height"],
                        "frameCount": output["frameCount"],
                    },
                ) as measured:
                    self.assertEqual(
                        storage,
                        subject._validate_effect_artifact_storage(
                            storage,
                            artifact=artifact,
                            runtime_evidence=runtime,
                            artifact_root=self.root,
                        ),
                    )
                measured_path = Path(measured.call_args.args[0])
                self.assertEqual(expected_path, measured_path)
                self.assertIn(
                    f"masked-surface-v{version}-", measured_path.name
                )
                self.assertNotEqual(legacy_path, measured_path)
        self.assertEqual(
            b"historical-v1-artifact-must-not-be-opened",
            legacy_path.read_bytes(),
        )

    def test_combined_preview_v2_preserves_fixed_bindings_and_exact_cross_layer_constants(self) -> None:
        command = self._preview_command()
        resolved = self._preview_resolved(command)
        base = deepcopy(self.assets["base-version-1"])
        stages = [
            seal({
                "schemaVersion": subject.MASKED_SURFACE_V3_REQUEST_SCHEMA_VERSION,
                "payload": "stage-0",
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
                "frameRangeEndExclusive": 5,
            }),
            seal({
                "schemaVersion": subject.MASKED_SURFACE_V3_REQUEST_SCHEMA_VERSION,
                "payload": "stage-1",
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
                "frameRangeEndExclusive": 5,
            }),
        ]
        glyph = seal(
            {
                "schemaVersion": "v5.m13-glyph-reveal-execution-request.v2",
                "executionRequestRef": "glyph-execution-1",
                "payload": "glyph",
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
            }
        )
        legacy = {
            "audioMix": deepcopy(command["audioMix"]),
            "subtitleManifest": deepcopy(command["subtitleManifest"]),
            "output": deepcopy(command["output"]),
        }
        fake = FakeV3Executor(self.root)
        executor = subject.V4MaskedSurfaceEffectExecutor(self.root, fake)

        def decoded(path: Path, **_: object) -> dict:
            candidate = Path(path)
            if candidate == self.base_path:
                return self._decoded(candidate)
            return {
                "fileDigest": file_digest(candidate),
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "e" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": 640,
                "height": 360,
                "frameCount": 6,
            }

        with (
            mock.patch.object(subject, "_resolve_preview_base", return_value=base),
            mock.patch.object(subject, "_resolve_effect_stage", side_effect=stages),
            mock.patch.object(subject, "_resolve_glyph_stage", return_value=glyph),
            mock.patch(
                "services.v4_platform.composition._build_timeline_preview_execution_request_v1",
                return_value=legacy,
            ),
            mock.patch.object(
                subject, "decoded_frame_pixel_digest_metadata", side_effect=decoded
            ),
            mock.patch.object(
                subject,
                "canonical_pcm_digest_metadata",
                return_value={
                    "pcmContentDigest": "f" * 64,
                    "pcmDigestSpec": PCM_CONTENT_DIGEST_SPEC,
                    "sampleRate": 48_000,
                    "channelCount": 2,
                    "sampleCount": 12_000,
                },
            ),
        ):
            result = executor.compose_timeline_preview_v2(
                command, resolved_artifacts=resolved
            )
        self.assertEqual(
            subject.EFFECT_PREVIEW_V4_RESULT_SCHEMA_VERSION,
            result["schemaVersion"],
        )
        self.assertEqual(command["effectResultBindings"], result["effectResultBindings"])
        self.assertEqual(
            command["glyphRequirementBinding"], result["glyphRequirementBinding"]
        )
        self.assertEqual(subject.EFFECT_PREVIEW_RENDERER_IDENTITY, result["rendererIdentity"])
        self.assertEqual(subject.EFFECT_PREVIEW_RENDERER_VERSION, result["rendererVersion"])
        self.assertFalse(result["providerUsed"])
        self.assertFalse(result["gpuUsed"])
        assert fake.request is not None
        self.assertEqual(
            subject.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION,
            fake.request["schemaVersion"],
        )
        self.assertEqual(["stage-0", "stage-1"], [item["payload"] for item in fake.request["effectStages"]])

    def test_combined_preview_rejects_ambiguous_effect_order_before_v3(self) -> None:
        command = self._preview_command()
        command["effectResultBindings"].reverse()
        executor = subject.V4MaskedSurfaceEffectExecutor(
            self.root, FakeV3Executor(self.root)
        )
        with self.assertRaises(subject.MaskedSurfaceRequestValidationError):
            executor.compose_timeline_preview_v2(
                command,
                resolved_artifacts=self._preview_resolved(command),
            )

    def test_combined_preview_v4_adds_exact_six_stage_profile(self) -> None:
        command = self._preview_command()
        face_binding = self._effect_binding(5, "FACE_MARK_COMPENSATION")
        face_binding["runtimeEvidenceDigest"] = "f" * 64
        command["effectResultBindings"].extend(
            [
                self._effect_binding(2, "FLAME_EXTINGUISH"),
                self._effect_binding(3, "SMOKE"),
                self._effect_binding(4, "NAMEPLATE_TEXT"),
                face_binding,
            ]
        )
        resolved = self._preview_resolved(command)
        base = deepcopy(self.assets["base-version-1"])

        def stage(index: int) -> dict:
            value = {
                "schemaVersion": "test-stage.v1",
                "payload": f"stage-{index}",
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
            }
            if index < 4:
                value["frameRangeEndExclusive"] = 5
            else:
                value["overlaySpec"] = {
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 5,
                }
            return seal(value)

        stages = [stage(index) for index in range(6)]
        glyph = seal(
            {
                "schemaVersion": "v5.m13-glyph-reveal-execution-request.v2",
                "executionRequestRef": "glyph-execution-1",
                "payload": "glyph",
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
            }
        )
        legacy = {
            "audioMix": deepcopy(command["audioMix"]),
            "subtitleManifest": deepcopy(command["subtitleManifest"]),
            "output": deepcopy(command["output"]),
        }
        fake = FakeV3Executor(self.root)
        executor = subject.V4MaskedSurfaceEffectExecutor(self.root, fake)

        def decoded(path: Path, **_: object) -> dict:
            candidate = Path(path)
            if candidate == self.base_path:
                return self._decoded(candidate)
            return {
                "fileDigest": file_digest(candidate),
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "e" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": 640,
                "height": 360,
                "frameCount": 6,
            }

        with (
            mock.patch.object(subject, "_resolve_preview_base", return_value=base),
            mock.patch.object(
                subject, "_resolve_effect_stage", side_effect=stages[:4]
            ),
            mock.patch.object(
                subject, "_resolve_overlay_preview_stage", side_effect=stages[4:]
            ),
            mock.patch.object(subject, "_resolve_glyph_stage", return_value=glyph),
            mock.patch(
                "services.v4_platform.composition._build_timeline_preview_execution_request_v1",
                return_value=legacy,
            ),
            mock.patch.object(
                subject, "decoded_frame_pixel_digest_metadata", side_effect=decoded
            ),
            mock.patch.object(
                subject,
                "canonical_pcm_digest_metadata",
                return_value={
                    "pcmContentDigest": "f" * 64,
                    "pcmDigestSpec": PCM_CONTENT_DIGEST_SPEC,
                    "sampleRate": 48_000,
                    "channelCount": 2,
                    "sampleCount": 12_000,
                },
            ),
        ):
            result = executor.compose_timeline_preview_v2(
                command, resolved_artifacts=resolved
            )

        assert fake.request is not None
        self.assertEqual(
            subject.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4,
            fake.request["schemaVersion"],
        )
        self.assertEqual(
            [f"stage-{index}" for index in range(6)],
            [item["payload"] for item in fake.request["effectStages"]],
        )
        self.assertEqual(
            subject.EFFECT_PREVIEW_RENDERER_VERSION_V4,
            result["rendererVersion"],
        )


if __name__ == "__main__":
    unittest.main()
