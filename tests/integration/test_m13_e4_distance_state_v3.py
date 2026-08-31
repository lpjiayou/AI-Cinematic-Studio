from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping
import unittest

from services.v3_render_core.digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)
from services.v3_render_core.composition import RenderArtifactError
from services.v3_render_core.distance_state import (
    DeterministicDistanceStateExecutor,
)
from services.v4_platform import (
    CompositionExecutionError,
    V4CompositionExecutor,
)
from services.v4_platform.distance_state import (
    rebuild_distance_state_v3_request,
    resolve_distance_state_preview_stage,
)
from services.v5_core_os.episode_production.distance_state import (
    build_distance_state_execution_request,
    build_distance_state_requirement,
    build_distance_state_result,
    parse_distance_state_requirement,
)


WIDTH = 160
HEIGHT = 120
FRAME_RATE = 6
FRAME_COUNT = 12
SUBJECT_WIDTH = 20
SUBJECT_HEIGHT = 20
RAW = "a" * 64


def _run(command: list[str]) -> bytes:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout


def _frame_rgba(path: Path, frame: int) -> bytes:
    raw = _run(
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
        ]
    )
    if len(raw) != WIDTH * HEIGHT * 4:
        raise AssertionError("decoded test frame has unexpected dimensions")
    return raw


def _frame_digest(path: Path, frame: int) -> str:
    return sha256(_frame_rgba(path, frame)).hexdigest()


def _color_pixels(
    path: Path, frame: int, color: str
) -> tuple[int, tuple[int, int] | None]:
    raw = _frame_rgba(path, frame)
    points: list[tuple[int, int]] = []
    for offset in range(0, len(raw), 4):
        red, green, blue = raw[offset : offset + 3]
        if color == "red":
            selected = red > green + 40 and red > blue + 40
        elif color == "green":
            selected = green > red + 30 and green > blue + 20
        elif color == "blue":
            selected = blue > red + 40 and blue > green + 20
        else:  # pragma: no cover - test construction is closed above.
            raise AssertionError(f"unsupported test color {color}")
        if selected:
            pixel = offset // 4
            points.append((pixel % WIDTH, pixel // WIDTH))
    if not points:
        return 0, None
    return len(points), (
        sum(item[0] for item in points) // len(points),
        sum(item[1] for item in points) // len(points),
    )


def _motion(
    *,
    start_xy: tuple[int, int],
    end_xy: tuple[int, int],
    start_scale: tuple[int, int] = (1, 1),
    end_scale: tuple[int, int] = (1, 1),
    quad: list[int] | None = None,
    end_quad: list[int] | None = None,
    start_rotation_milli_degrees: int = 0,
    end_rotation_milli_degrees: int = 0,
) -> list[dict[str, Any]]:
    perspective = (
        list(quad)
        if quad is not None
        else [
            0,
            0,
            SUBJECT_WIDTH,
            0,
            SUBJECT_WIDTH,
            SUBJECT_HEIGHT,
            0,
            SUBJECT_HEIGHT,
        ]
    )
    return [
        {
            "frame": 0,
            "x": start_xy[0],
            "y": start_xy[1],
            "scaleXNumerator": start_scale[0],
            "scaleXDenominator": start_scale[1],
            "scaleYNumerator": start_scale[0],
            "scaleYDenominator": start_scale[1],
            "rotationMilliDegrees": start_rotation_milli_degrees,
            "perspectiveQuad": perspective,
            "interpolation": "LINEAR",
        },
        {
            "frame": FRAME_COUNT - 1,
            "x": end_xy[0],
            "y": end_xy[1],
            "scaleXNumerator": end_scale[0],
            "scaleXDenominator": end_scale[1],
            "scaleYNumerator": end_scale[0],
            "scaleYDenominator": end_scale[1],
            "rotationMilliDegrees": end_rotation_milli_degrees,
            "perspectiveQuad": (
                list(end_quad) if end_quad is not None else perspective
            ),
            "interpolation": "LINEAR",
        },
    ]


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required for real M13-E4 execution",
)
class M13E4DistanceStateV3IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="m13-e4-v3-")
        self.root = Path(self.temporary.name)
        inputs = self.root / "inputs"
        inputs.mkdir()
        self.base_path = inputs / "base.mp4"
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                (
                    f"color=c=0x202020:size={WIDTH}x{HEIGHT}:"
                    f"rate={FRAME_RATE}"
                ),
                "-frames:v",
                str(FRAME_COUNT),
                "-c:v",
                "libx264",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-threads:v",
                "1",
                "-x264-params",
                (
                    "threads=1:lookahead_threads=1:sliced_threads=0:"
                    "sync-lookahead=0:rc-lookahead=0:scenecut=0"
                ),
                "-y",
                str(self.base_path),
            ]
        )
        self.subject_path = inputs / "subject.png"
        self.mask_path = inputs / "mask.png"
        self.variant_a_path = inputs / "variant-a.png"
        self.variant_b_path = inputs / "variant-b.png"
        for path, color in (
            (self.subject_path, "red@1.0"),
            (self.mask_path, "white@1.0"),
            (self.variant_a_path, "green@1.0"),
            (self.variant_b_path, "blue@1.0"),
        ):
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    (
                        f"color={color}:size={SUBJECT_WIDTH}x"
                        f"{SUBJECT_HEIGHT},format=rgba"
                    ),
                    "-frames:v",
                    "1",
                    "-c:v",
                    "png",
                    "-threads:v",
                    "1",
                    "-y",
                    str(path),
                ]
            )

        base_pixels = decoded_frame_pixel_digest_metadata(self.base_path)
        self.base = {
            "assetVersionRef": "asset-version:e4-base:v1",
            "assetVersionDigest": "1" * 64,
            "storageKey": "inputs/base.mp4",
            "fileDigest": file_digest(self.base_path),
            "pixelDigest": base_pixels["decodedFramePixelDigest"],
            "pixelDigestSpec": base_pixels["decodedFramePixelDigestSpec"],
            "width": WIDTH,
            "height": HEIGHT,
            "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE,
            "pixelFormat": "yuv420p",
        }
        self.subject = self._image_asset(
            self.subject_path, "asset-version:e4-subject:v1", "2" * 64
        )
        self.mask = self._image_asset(
            self.mask_path, "asset-version:e4-mask:v1", "3" * 64
        )
        self.variant_a = self._image_asset(
            self.variant_a_path, "asset-version:e4-variant-a:v1", "4" * 64
        )
        self.variant_b = self._image_asset(
            self.variant_b_path, "asset-version:e4-variant-b:v1", "5" * 64
        )
        self.composition = V4CompositionExecutor.from_artifact_root(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _public_base() -> dict[str, Any]:
        return {
            "workspaceRef": "workspace:e4-v3",
            "productionRunRef": "run:e4-v3",
            "requirementRef": "requirement:e4-distance-state",
            "effectMode": "DISTANCE_STATE_TRANSITION",
            "targetShotRef": "shot:e4-technical",
            "targetShotVersionRef": "shot-version:e4-technical:v1",
            "targetShotVersionDigest": RAW,
            "basePlateAssetVersionRef": "asset-version:e4-base:v1",
            "basePlateAssetVersionDigest": "1" * 64,
            "targetKind": "OVERLAY_LAYER",
            "subjectLayerAssetVersionRef": "asset-version:e4-subject:v1",
            "subjectLayerAssetVersionDigest": "2" * 64,
            "maskAssetVersionRef": "asset-version:e4-mask:v1",
            "maskAssetVersionDigest": "3" * 64,
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": FRAME_COUNT,
            "transitionMode": "SCREEN_DISTANCE",
            "coordinateSpace": "CANVAS_PIXELS",
            "motionKeyframes": _motion(
                start_xy=(20, 60), end_xy=(80, 60)
            ),
            "distanceContract": {
                "metric": "SCREEN_EUCLIDEAN_PIXELS",
                "startValue": 80,
                "endValue": 20,
                "tolerance": 0,
                "direction": "APPROACH",
                "referenceX": 100,
                "referenceY": 60,
            },
            "startStateRef": None,
            "endStateRef": None,
            "visualStateDefinitions": [],
            "visualStateSchedule": [],
            "blendMode": "NORMAL",
            "layer": 8,
        }

    @staticmethod
    def _image_asset(path: Path, reference: str, digest: str) -> dict[str, Any]:
        measured = image_digest_metadata(path)
        return {
            "assetVersionRef": reference,
            "assetVersionDigest": digest,
            "storageKey": f"inputs/{path.name}",
            "fileDigest": file_digest(path),
            "pixelDigest": measured["pixel_digest"],
            "pixelDigestSpec": measured["pixel_digest_spec"],
            "pixelMode": measured["pixel_mode"],
            "width": measured["width"],
            "height": measured["height"],
        }

    def _request(
        self,
        public: Mapping[str, Any],
        *,
        variants: list[Mapping[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        variant_assets = list(variants or [])
        full_frame = public["targetKind"] == "FULL_FRAME"
        requirement = build_distance_state_requirement(
            public,
            resolved_base=self.base,
            resolved_subject=None if full_frame else self.subject,
            resolved_mask=None if full_frame else self.mask,
            resolved_variants=variant_assets,
        )
        request = build_distance_state_execution_request(requirement).as_dict()
        assets = {self.base["assetVersionRef"]: deepcopy(self.base)}
        if not full_frame:
            assets[self.subject["assetVersionRef"]] = deepcopy(self.subject)
            assets[self.mask["assetVersionRef"]] = deepcopy(self.mask)
        for asset in variant_assets:
            assets[str(asset["assetVersionRef"])] = deepcopy(dict(asset))
        return request, assets

    @staticmethod
    def _reseal_v3(value: Mapping[str, Any]) -> dict[str, Any]:
        result = deepcopy(dict(value))
        result.pop("payloadDigest", None)
        result["payloadDigest"] = sha256(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return result

    def _execute(
        self,
        public: Mapping[str, Any],
        *,
        variants: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request, assets = self._request(public, variants=variants)
        result = self.composition.execute_distance_state(
            request,
            resolved_asset_versions=assets,
        )
        self.assertEqual(
            set(result),
            {"artifactEvidence", "runtimeEvidence", "evidenceBindings"},
        )
        self.assertEqual(
            self.composition.verify_distance_state_artifact(
                result["artifactEvidence"],
                runtime_evidence=result["runtimeEvidence"],
            ),
            result["artifactEvidence"],
        )
        requirement_value = {
            "schemaVersion": "v5.m13-distance-state-transition-requirement.v1",
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "requirementRef": request["requirementRef"],
            "effectMode": request["effectMode"],
            **deepcopy(request["transitionSpec"]),
            "publicationAllowed": False,
            "payloadDigest": request["requirementDigest"],
        }
        requirement = parse_distance_state_requirement(requirement_value)
        v5_result = build_distance_state_result(
            requirement=requirement,
            execution_request=request,
            evidence_bindings=result["evidenceBindings"],
            artifact_evidence=result["artifactEvidence"],
        ).as_dict()
        artifact = result["artifactEvidence"]
        output = artifact["outputDigest"]
        probe = artifact["outputMediaProbe"]
        workspace_hash = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
        run_hash = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
        binding = {
            "clipRef": "clip:e4-real-preview-stage",
            "clipDigest": "9" * 64,
            "effectMode": request["effectMode"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "resultRef": v5_result["resultRef"],
            "resultDigest": v5_result["payloadDigest"],
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["payloadDigest"],
            "artifactEvidenceRef": artifact["artifactEvidenceRef"],
            "artifactEvidenceDigest": artifact["payloadDigest"],
            "runtimeEvidenceRef": result["runtimeEvidence"][
                "runtimeEvidenceRef"
            ],
            "runtimeEvidenceDigest": result["runtimeEvidence"][
                "payloadDigest"
            ],
            "frameRangeStartInclusive": public[
                "frameRangeStartInclusive"
            ],
            "frameRangeEndExclusive": public["frameRangeEndExclusive"],
        }
        resolution = {
            "requirement": requirement.as_dict(),
            "executionRequest": request,
            "artifactEvidence": artifact,
            "runtimeEvidence": result["runtimeEvidence"],
            "result": v5_result,
            "assetVersions": assets,
            "artifactStorage": {
                "artifactEvidenceRef": artifact["artifactEvidenceRef"],
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "storageKey": (
                    f"{workspace_hash}/{run_hash}/distance-state/"
                    f"distance-state-{artifact['v3ExecutionRequestDigest']}.mp4"
                ),
                "fileDigest": output["fileDigest"],
                "pixelDigest": output["decodedFramePixelDigest"],
                "pixelDigestSpec": output["decodedFramePixelDigestSpec"],
                "width": output["width"],
                "height": output["height"],
                "frameCount": output["frameCount"],
                "frameRate": output["frameRate"],
                "pixelFormat": probe["pixelFormat"],
            },
        }
        self.assertEqual(
            resolve_distance_state_preview_stage(
                binding,
                resolution,
                artifact_root=self.root,
                base=self.base,
            ),
            rebuild_distance_state_v3_request(request, assets, self.root),
        )
        return result

    def _artifact_path(self, result: Mapping[str, Any]) -> Path:
        artifact = result["artifactEvidence"]
        self.assertNotIn("outputStorageKey", artifact)
        self.assertNotIn("storageKey", artifact)
        self.assertNotIn("internalPath", artifact)
        workspace_hash = sha256(
            artifact["workspaceRef"].encode("utf-8")
        ).hexdigest()[:20]
        run_hash = sha256(
            artifact["productionRunRef"].encode("utf-8")
        ).hexdigest()[:20]
        storage_key = (
            f"{workspace_hash}/{run_hash}/distance-state/"
            f"distance-state-{artifact['v3ExecutionRequestDigest']}.mp4"
        )
        path = self.root / storage_key
        self.assertTrue(path.is_file())
        return path

    def _assert_exact_media(self, result: Mapping[str, Any]) -> None:
        artifact = result["artifactEvidence"]
        runtime = result["runtimeEvidence"]
        self.assertIs(artifact["publicationAllowed"], False)
        self.assertIs(runtime["publicationAllowed"], False)
        self.assertIs(runtime["gpuUsed"], False)
        self.assertEqual(
            runtime["rendererIdentity"],
            "v3.deterministic-distance-state-ffmpeg",
        )
        self.assertEqual(runtime["rendererVersion"], "1")
        probe = artifact["outputMediaProbe"]
        self.assertEqual(
            probe,
            {
                "width": WIDTH,
                "height": HEIGHT,
                "frameCount": FRAME_COUNT,
                "frameRate": FRAME_RATE,
                "pixelFormat": "yuv420p",
                "container": "mp4",
                "videoCodec": "h264",
            },
        )
        output = artifact["outputDigest"]
        self.assertEqual(
            set(output),
            {
                "fileDigest",
                "fileDigestAlgorithm",
                "decodedFramePixelDigest",
                "decodedFramePixelDigestSpec",
                "pixelMode",
                "width",
                "height",
                "frameCount",
                "frameRate",
            },
        )
        self.assertEqual(output["fileDigestAlgorithm"], "sha256")
        self.assertEqual(
            output["decodedFramePixelDigestSpec"],
            DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
        )
        self.assertEqual(output["pixelMode"], "RGBA")
        self.assertEqual(output["width"], WIDTH)
        self.assertEqual(output["height"], HEIGHT)
        self.assertEqual(output["frameCount"], FRAME_COUNT)
        self.assertEqual(output["frameRate"], FRAME_RATE)

    def test_screen_distance_overlay_is_real_and_repeatable(self) -> None:
        public = self._public_base()
        first = self._execute(public)
        replay = self._execute(public)
        self._assert_exact_media(first)
        self.assertEqual(
            first["artifactEvidence"]["outputDigest"][
                "decodedFramePixelDigest"
            ],
            replay["artifactEvidence"]["outputDigest"][
                "decodedFramePixelDigest"
            ],
        )
        self.assertEqual(
            first["artifactEvidence"]["derivedDistanceFacts"],
            public["distanceContract"],
        )
        output = self._artifact_path(first)
        self.assertNotEqual(
            _frame_digest(output, 0),
            _frame_digest(output, FRAME_COUNT - 1),
        )
        first_count, first_center = _color_pixels(output, 0, "red")
        last_count, last_center = _color_pixels(
            output, FRAME_COUNT - 1, "red"
        )
        self.assertGreater(first_count, 100)
        self.assertGreater(last_count, 100)
        self.assertIsNotNone(first_center)
        self.assertIsNotNone(last_center)
        assert first_center is not None and last_center is not None
        self.assertGreater(last_center[0] - first_center[0], 30)
        output.write_bytes(output.read_bytes() + b"artifact-tamper")
        with self.assertRaises(CompositionExecutionError):
            self.composition.verify_distance_state_artifact(
                first["artifactEvidence"],
                runtime_evidence=first["runtimeEvidence"],
            )

    def test_visual_state_and_combined_change_real_output_frames(self) -> None:
        visual = self._public_base()
        visual.update(
            {
                "requirementRef": "requirement:e4-visual-state",
                "transitionMode": "VISUAL_STATE",
                "motionKeyframes": _motion(
                    start_xy=(60, 50), end_xy=(60, 50)
                ),
                "distanceContract": None,
                "startStateRef": "state:visible",
                "endStateRef": "state:hidden",
                "visualStateDefinitions": [
                    {
                        "stateRef": "state:visible",
                        "visibility": "VISIBLE",
                        "opacityPermille": 1000,
                        "variantAssetVersionRef": None,
                        "variantAssetVersionDigest": None,
                        "layer": 8,
                        "blendMode": "NORMAL",
                    },
                    {
                        "stateRef": "state:hidden",
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
                        "stateRef": "state:visible",
                        "startFrameInclusive": 0,
                        "endFrameExclusive": FRAME_COUNT // 2,
                        "transitionInterpolation": "STEP",
                    },
                    {
                        "stateRef": "state:hidden",
                        "startFrameInclusive": FRAME_COUNT // 2,
                        "endFrameExclusive": FRAME_COUNT,
                        "transitionInterpolation": "STEP",
                    },
                ],
            }
        )
        visual_result = self._execute(visual)
        self._assert_exact_media(visual_result)
        visual_output = self._artifact_path(visual_result)
        self.assertNotEqual(
            _frame_digest(visual_output, 0),
            _frame_digest(visual_output, FRAME_COUNT - 1),
        )
        visible_red, _ = _color_pixels(visual_output, 0, "red")
        hidden_red, _ = _color_pixels(
            visual_output, FRAME_COUNT - 1, "red"
        )
        self.assertGreater(visible_red, 100)
        self.assertLess(hidden_red, visible_red // 4)
        before_hidden_red, _ = _color_pixels(
            visual_output, FRAME_COUNT // 2 - 1, "red"
        )
        after_hidden_red, _ = _color_pixels(
            visual_output, FRAME_COUNT // 2, "red"
        )
        self.assertGreater(before_hidden_red, 100)
        self.assertLess(after_hidden_red, before_hidden_red // 4)
        self.assertRegex(
            visual_result["artifactEvidence"][
                "appliedStateScheduleDigest"
            ],
            r"^[0-9a-f]{64}$",
        )

        combined = self._public_base()
        combined.update(
            {
                "requirementRef": "requirement:e4-combined",
                "transitionMode": "SCREEN_DISTANCE_AND_VISUAL_STATE",
                "motionKeyframes": _motion(
                    start_xy=(20, 60),
                    end_xy=(80, 60),
                    start_scale=(1, 1),
                    end_scale=(3, 2),
                    end_rotation_milli_degrees=30_000,
                    end_quad=[2, 0, 18, 2, 20, 18, 0, 20],
                ),
                "startStateRef": "state:variant-a",
                "endStateRef": "state:variant-b",
                "visualStateDefinitions": [
                    {
                        "stateRef": "state:variant-a",
                        "visibility": "VISIBLE",
                        "opacityPermille": 1000,
                        "variantAssetVersionRef": self.variant_a[
                            "assetVersionRef"
                        ],
                        "variantAssetVersionDigest": self.variant_a[
                            "assetVersionDigest"
                        ],
                        "layer": 8,
                        "blendMode": "NORMAL",
                    },
                    {
                        "stateRef": "state:variant-b",
                        "visibility": "VISIBLE",
                        "opacityPermille": 1000,
                        "variantAssetVersionRef": self.variant_b[
                            "assetVersionRef"
                        ],
                        "variantAssetVersionDigest": self.variant_b[
                            "assetVersionDigest"
                        ],
                        "layer": 8,
                        "blendMode": "NORMAL",
                    },
                ],
                "visualStateSchedule": [
                    {
                        "stateRef": "state:variant-a",
                        "startFrameInclusive": 0,
                        "endFrameExclusive": FRAME_COUNT // 2,
                        "transitionInterpolation": "STEP",
                    },
                    {
                        "stateRef": "state:variant-b",
                        "startFrameInclusive": FRAME_COUNT // 2,
                        "endFrameExclusive": FRAME_COUNT,
                        "transitionInterpolation": "STEP",
                    },
                ],
            }
        )
        combined_result = self._execute(
            combined, variants=[self.variant_a, self.variant_b]
        )
        self._assert_exact_media(combined_result)
        self.assertNotEqual(
            visual_result["artifactEvidence"]["outputDigest"][
                "decodedFramePixelDigest"
            ],
            combined_result["artifactEvidence"]["outputDigest"][
                "decodedFramePixelDigest"
            ],
        )
        combined_output = self._artifact_path(combined_result)
        first_green, _ = _color_pixels(combined_output, 0, "green")
        first_blue, _ = _color_pixels(combined_output, 0, "blue")
        last_green, _ = _color_pixels(
            combined_output, FRAME_COUNT - 1, "green"
        )
        last_blue, _ = _color_pixels(
            combined_output, FRAME_COUNT - 1, "blue"
        )
        self.assertGreater(first_green, 100)
        self.assertLess(first_blue, first_green // 4)
        self.assertGreater(last_blue, 100)
        self.assertLess(last_green, last_blue // 4)
        before_switch_green, _ = _color_pixels(
            combined_output, FRAME_COUNT // 2 - 1, "green"
        )
        before_switch_blue, _ = _color_pixels(
            combined_output, FRAME_COUNT // 2 - 1, "blue"
        )
        after_switch_green, _ = _color_pixels(
            combined_output, FRAME_COUNT // 2, "green"
        )
        after_switch_blue, _ = _color_pixels(
            combined_output, FRAME_COUNT // 2, "blue"
        )
        self.assertGreater(before_switch_green, 100)
        self.assertLess(before_switch_blue, before_switch_green // 4)
        self.assertGreater(after_switch_blue, 100)
        self.assertLess(after_switch_green, after_switch_blue // 4)
        self.assertEqual(
            combined_result["artifactEvidence"]["derivedDistanceFacts"],
            combined["distanceContract"],
        )
        self.assertRegex(
            combined_result["artifactEvidence"][
                "appliedStateScheduleDigest"
            ],
            r"^[0-9a-f]{64}$",
        )

    def test_full_frame_preserves_media_contract_and_input_drift_rejects(
        self,
    ) -> None:
        public = self._public_base()
        public.update(
            {
                "requirementRef": "requirement:e4-full-frame",
                "targetKind": "FULL_FRAME",
                "subjectLayerAssetVersionRef": None,
                "subjectLayerAssetVersionDigest": None,
                "maskAssetVersionRef": None,
                "maskAssetVersionDigest": None,
                "motionKeyframes": _motion(
                    start_xy=(0, 60),
                    end_xy=(60, 60),
                    quad=[0, 0, WIDTH, 0, WIDTH, HEIGHT, 0, HEIGHT],
                ),
                "distanceContract": {
                    "metric": "SCREEN_EUCLIDEAN_PIXELS",
                    "startValue": 80,
                    "endValue": 20,
                    "tolerance": 0,
                    "direction": "APPROACH",
                    "referenceX": 80,
                    "referenceY": 60,
                },
            }
        )
        result = self._execute(public)
        self._assert_exact_media(result)
        output = self._artifact_path(result)
        self.assertNotEqual(
            _frame_digest(output, 0),
            _frame_digest(output, FRAME_COUNT - 1),
        )

        request, assets = self._request(public)
        assets[self.base["assetVersionRef"]]["frameCount"] += 1
        with self.assertRaises(CompositionExecutionError):
            self.composition.execute_distance_state(
                request,
                resolved_asset_versions=assets,
            )

        overlay = self._public_base()
        request, assets = self._request(overlay)
        original_subject = self.subject_path.read_bytes()
        try:
            self.subject_path.write_bytes(original_subject + b"tamper")
            with self.assertRaises(CompositionExecutionError):
                self.composition.execute_distance_state(
                    request,
                    resolved_asset_versions=assets,
                )
        finally:
            self.subject_path.write_bytes(original_subject)

        request, assets = self._request(public)
        assets[self.base["assetVersionRef"]]["frameRate"] += 1
        with self.assertRaises(CompositionExecutionError):
            self.composition.execute_distance_state(
                request,
                resolved_asset_versions=assets,
            )

        request, assets = self._request(public)
        assets[self.base["assetVersionRef"]]["width"] += 2
        with self.assertRaises(CompositionExecutionError):
            self.composition.execute_distance_state(
                request,
                resolved_asset_versions=assets,
            )

    def test_full_frame_safe_area_and_transform_budget_fail_closed(self) -> None:
        off_canvas = self._public_base()
        off_canvas.update(
            {
                "requirementRef": "requirement:e4-full-frame-off-canvas",
                "targetKind": "FULL_FRAME",
                "subjectLayerAssetVersionRef": None,
                "subjectLayerAssetVersionDigest": None,
                "maskAssetVersionRef": None,
                "maskAssetVersionDigest": None,
                "motionKeyframes": _motion(
                    start_xy=(-1, 60),
                    end_xy=(60, 60),
                    quad=[0, 0, WIDTH, 0, WIDTH, HEIGHT, 0, HEIGHT],
                ),
                "distanceContract": {
                    "metric": "SCREEN_EUCLIDEAN_PIXELS",
                    "startValue": 81,
                    "endValue": 20,
                    "tolerance": 0,
                    "direction": "APPROACH",
                    "referenceX": 80,
                    "referenceY": 60,
                },
            }
        )
        with self.assertRaises(CompositionExecutionError):
            self._execute(off_canvas)

        oversized = deepcopy(off_canvas)
        oversized.update(
            requirementRef="requirement:e4-full-frame-resource-budget",
            motionKeyframes=_motion(
                start_xy=(80, 60),
                end_xy=(80, 60),
                start_scale=(1, 1),
                end_scale=(8, 1),
                quad=[0, 0, WIDTH, 0, WIDTH, HEIGHT, 0, HEIGHT],
            ),
            distanceContract={
                "metric": "RELATIVE_SCALE_PERMILLE",
                "startValue": 1000,
                "endValue": 8000,
                "tolerance": 0,
                "direction": "APPROACH",
                "referenceX": None,
                "referenceY": None,
            },
        )
        with self.assertRaises(CompositionExecutionError):
            self._execute(oversized)

    def test_v3_rejects_output_frame_rate_and_size_drift(self) -> None:
        request, assets = self._request(self._public_base())
        v3 = rebuild_distance_state_v3_request(
            request,
            assets,
            self.root,
        )
        executor = DeterministicDistanceStateExecutor(self.root)
        cases = {
            "frameCount": FRAME_COUNT + 1,
            "frameRate": FRAME_RATE + 1,
            "width": WIDTH + 2,
            "height": HEIGHT + 2,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                drifted = deepcopy(v3)
                drifted["output"][field] = value
                drifted = self._reseal_v3(drifted)
                with self.assertRaises(RenderArtifactError):
                    executor.execute(drifted)


if __name__ == "__main__":
    unittest.main()
