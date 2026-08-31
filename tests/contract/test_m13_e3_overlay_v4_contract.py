from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    IMAGE_PIXEL_DIGEST_SPEC,
    decoded_frame_pixel_digest_metadata,
    file_digest,
)
from services.v3_render_core.composition import RenderArtifactError
from services.v3_render_core.deterministic_overlays import (
    DeterministicOverlayExecutor,
)
from services.v4_platform import V4CompositionExecutor
from services.v4_platform.composition import CompositionExecutionError
from services.v4_platform.deterministic_overlays import (
    OverlayAssetResolutionError,
    OverlayExecutionError,
    OverlayRequestValidationError,
    OVERLAY_RENDERER_IDENTITY,
    OVERLAY_RENDERER_VERSION,
    _validate_v3_result,
    inspect_deterministic_overlay_image,
    inspect_deterministic_overlay_video,
    validate_overlay_execution_request,
)


class DeterministicOverlayV4InspectionTest(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("FFmpeg test runtime is unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.video = self.root / "base.mp4"
        self.mark = self.root / "mark.png"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f",
                "lavfi", "-i", "color=c=blue:s=64x64:r=2:d=1", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads:v",
                "1", "-video_track_timescale", "1024", "-y",
                str(self.video),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f",
                "lavfi", "-i", "color=c=red@0.8:s=8x8:r=1:d=1",
                "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgba",
                "-threads:v", "1", "-y", str(self.mark),
            ],
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _asset(path: Path, *, storage_key: str, media_type: str) -> dict:
        return {
            "assetVersionRef": "asset-version-1",
            "assetVersionDigest": "1" * 64,
            "storageKey": storage_key,
            "fileDigest": file_digest(path),
            "mediaType": media_type,
            "byteSize": path.stat().st_size,
        }

    @staticmethod
    def _seal(value: dict) -> dict:
        result = deepcopy(value)
        result["payloadDigest"] = sha256(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return result

    def test_pinned_media_descriptors_are_inherited_and_remeasured(self) -> None:
        """Both probes must see the held media fd, not reopen its path."""

        video = inspect_deterministic_overlay_video(
            self.root,
            self._asset(
                self.video,
                storage_key="base.mp4",
                media_type="video/mp4",
            ),
        )
        mark = inspect_deterministic_overlay_image(
            self.root,
            self._asset(
                self.mark,
                storage_key="mark.png",
                media_type="image/png",
            ),
        )
        self.assertEqual(video["pixelDigestSpec"], DECODED_FRAME_PIXEL_DIGEST_SPEC_V2)
        self.assertEqual(video["frameRate"], 2)
        self.assertEqual(video["frameCount"], 2)
        self.assertEqual(video["pixelFormat"], "yuv420p")
        self.assertEqual(mark["pixelDigestSpec"], IMAGE_PIXEL_DIGEST_SPEC)
        self.assertEqual(mark["pixelMode"], "RGBA")
        self.assertEqual((mark["width"], mark["height"]), (8, 8))

    def test_file_digest_drift_fails_closed(self) -> None:
        stale = self._asset(
            self.mark,
            storage_key="mark.png",
            media_type="image/png",
        )
        stale["fileDigest"] = "sha256:" + "0" * 64
        with self.assertRaises(OverlayAssetResolutionError):
            inspect_deterministic_overlay_image(self.root, stale)

    def test_font_authority_late_binding_cannot_be_replaced(self) -> None:
        first = object()
        composition = V4CompositionExecutor.from_artifact_root(
            self.root,
            font_asset_authority=first,
        )
        composition.bind_font_asset_authority(first)
        with self.assertRaises(CompositionExecutionError):
            composition.bind_font_asset_authority(object())

    def test_direct_v4_request_rejects_extra_execution_fields(self) -> None:
        digest = "1" * 64
        spec = {
            "targetShotRef": "shot-1",
            "targetShotVersionRef": "shot-version-1",
            "targetShotVersionDigest": digest,
            "basePlateAssetVersionRef": "base-version-1",
            "basePlateAssetVersionDigest": digest,
            "basePlateFileDigest": "sha256:" + digest,
            "basePlatePixelDigest": "sha256:" + digest,
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": 2,
            "blendMode": "NORMAL",
            "layer": 6,
            "characterRef": "character-1",
            "identityReferenceRef": "identity-reference-1",
            "identityReferenceVersionRef": "identity-reference-version-1",
            "identityReferenceContentDigest": digest,
            "identityReferenceProjectionDigest": digest,
            "identityLockRef": "identity-lock-1",
            "identityLockVersionRef": "identity-lock-version-1",
            "identityLockDigest": digest,
            "markType": "MOLE",
            "markAssetVersionRef": "mark-version-1",
            "markAssetVersionDigest": digest,
            "markFileDigest": "sha256:" + digest,
            "markPixelDigest": "sha256:" + digest,
            "faceRegion": "LEFT_CHEEK",
            "trackingSourceKind": "EXPLICIT_KEYFRAMES",
            "trackingKeyframes": [],
            "scaleKeyframes": [],
            "rotationKeyframes": [],
            "opacityCurve": [],
            "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
        }
        identity = {
            "requirementRef": "requirement-1",
            "requirementDigest": digest,
        }
        request = {
            "schemaVersion": "v5.m13-overlay-execution-request.v1",
            "executionRequestRef": "overlay-execution-"
            + sha256(
                json.dumps(
                    identity,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:32],
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            **identity,
            "effectMode": "FACE_MARK_COMPENSATION",
            "overlaySpec": spec,
            "publicationAllowed": False,
        }
        request["payloadDigest"] = sha256(
            json.dumps(
                request,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        validate_overlay_execution_request(request)
        stale_seal = deepcopy(request)
        stale_seal["payloadDigest"] = "0" * 64
        with self.assertRaises(OverlayRequestValidationError):
            validate_overlay_execution_request(stale_seal)
        injected = deepcopy(request)
        injected["overlaySpec"]["ffmpegFilter"] = "movie=attacker"
        unsealed = deepcopy(injected)
        unsealed.pop("payloadDigest")
        injected["payloadDigest"] = sha256(
            json.dumps(
                unsealed,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.assertRaises(OverlayRequestValidationError):
            validate_overlay_execution_request(injected)

    def test_output_inode_replacement_during_measurement_fails_closed(self) -> None:
        request_digest = "2" * 64
        workspace = "workspace-1"
        run = "run-1"
        storage_key = (
            sha256(workspace.encode()).hexdigest()[:20]
            + "/"
            + sha256(run.encode()).hexdigest()[:20]
            + "/deterministic-overlays/overlay-"
            + request_digest
            + ".mp4"
        )
        output_path = self.root / storage_key
        output_path.parent.mkdir(parents=True)
        shutil.copy2(self.video, output_path)
        replacement = self.root / "replacement.mp4"
        shutil.copy2(self.video, replacement)
        inspected = inspect_deterministic_overlay_video(
            self.root,
            self._asset(
                output_path,
                storage_key=storage_key,
                media_type="video/mp4",
            ),
        )
        output = {
            "width": inspected["width"],
            "height": inspected["height"],
            "frameCount": inspected["frameCount"],
            "frameRate": inspected["frameRate"],
            "pixelFormat": inspected["pixelFormat"],
            "container": "mp4",
            "videoCodec": "h264",
        }
        output_digest = {
            "fileDigest": inspected["fileDigest"],
            "fileDigestAlgorithm": "sha256",
            "decodedFramePixelDigest": inspected["pixelDigest"],
            "decodedFramePixelDigestSpec": inspected["pixelDigestSpec"],
            "pixelMode": "RGBA",
            "width": inspected["width"],
            "height": inspected["height"],
            "frameCount": inspected["frameCount"],
            "frameRate": inspected["frameRate"],
        }
        manifest = "sha256:" + "3" * 64
        runtime = {
            "ffmpegIdentity": "ffmpeg held test identity",
            "rendererIdentity": OVERLAY_RENDERER_IDENTITY,
            "rendererVersion": OVERLAY_RENDERER_VERSION,
            "executionManifestDigest": manifest,
        }
        request = {
            "v5ExecutionRequestRef": "overlay-execution-1",
            "v5ExecutionRequestDigest": "4" * 64,
            "workspaceRef": workspace,
            "productionRunRef": run,
            "requirementRef": "requirement-1",
            "requirementDigest": "5" * 64,
            "effectMode": "FACE_MARK_COMPENSATION",
            "output": output,
            "payloadDigest": request_digest,
        }
        result = {
            "internalPath": str(output_path.resolve()),
            "outputStorageKey": storage_key,
            "outputByteSize": output_path.stat().st_size,
            "outputMediaProbe": output,
            "outputDigest": output_digest,
            **runtime,
            "runtimeEvidenceDigest": "sha256:"
            + sha256(
                json.dumps(
                    runtime,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
            "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
            "v3ExecutionRequestDigest": request_digest,
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "publicationAllowed": False,
        }

        _validate_v3_result(
            deepcopy(result), request=request, artifact_root=self.root
        )
        mutations = {
            "frame-count": lambda value: value["outputMediaProbe"].update(
                {"frameCount": value["outputMediaProbe"]["frameCount"] + 1}
            ),
            "runtime": lambda value: value.update({"rendererVersion": "999"}),
            "lineage": lambda value: value.update(
                {"requirementRef": "foreign-requirement"}
            ),
            "v3-digest": lambda value: value.update(
                {"v3ExecutionRequestDigest": "0" * 64}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(v3_result_drift=label):
                changed = deepcopy(result)
                mutate(changed)
                with self.assertRaises(OverlayExecutionError):
                    _validate_v3_result(
                        changed, request=request, artifact_root=self.root
                    )

        def replace_then_measure(path, **kwargs):
            os.replace(replacement, output_path)
            return decoded_frame_pixel_digest_metadata(path, **kwargs)

        with patch(
            "services.v4_platform.deterministic_overlays."
            "decoded_frame_pixel_digest_metadata",
            side_effect=replace_then_measure,
        ), self.assertRaises(OverlayExecutionError):
            _validate_v3_result(
                result,
                request=request,
                artifact_root=self.root,
            )

    def test_v3_staged_base_replacement_during_render_fails_closed(self) -> None:
        base_input = self._asset(
            self.video,
            storage_key="base.mp4",
            media_type="video/mp4",
        )
        base_input["assetVersionRef"] = "base-version-1"
        base = {
            **inspect_deterministic_overlay_video(self.root, base_input),
            "storageKey": "base.mp4",
        }
        mark_input = self._asset(
            self.mark,
            storage_key="mark.png",
            media_type="image/png",
        )
        mark_input["assetVersionRef"] = "mark-version-1"
        mark = {
            **inspect_deterministic_overlay_image(self.root, mark_input),
            "storageKey": "mark.png",
        }
        endpoints = (0, 1)
        request = self._seal(
            {
                "schemaVersion": "v4.m13-overlay-execution-request.v1",
                "v5ExecutionRequestRef": "overlay-execution-1",
                "v5ExecutionRequestDigest": "2" * 64,
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
                "requirementRef": "requirement-1",
                "requirementDigest": "3" * 64,
                "effectMode": "FACE_MARK_COMPENSATION",
                "basePlate": base,
                "overlayAsset": mark,
                "overlaySpec": {
                    "targetShot": {
                        "shotRef": "shot-1",
                        "shotVersionRef": "shot-version-1",
                        "shotVersionDigest": "4" * 64,
                    },
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 2,
                    "blendMode": "NORMAL",
                    "layer": 6,
                    "markType": "MOLE",
                    "faceRegion": "LEFT_CHEEK",
                    "trackingSourceKind": "EXPLICIT_KEYFRAMES",
                    "trackingKeyframes": [
                        {
                            "frame": frame,
                            "xPermille": 250,
                            "yPermille": 250,
                            "interpolation": "LINEAR",
                        }
                        for frame in endpoints
                    ],
                    "scaleKeyframes": [
                        {
                            "frame": frame,
                            "xPermille": 1000,
                            "yPermille": 1000,
                            "interpolation": "LINEAR",
                        }
                        for frame in endpoints
                    ],
                    "rotationKeyframes": [
                        {
                            "frame": frame,
                            "degreesMilli": 0,
                            "interpolation": "LINEAR",
                        }
                        for frame in endpoints
                    ],
                    "opacityCurve": [
                        {
                            "frame": frame,
                            "valuePermille": 1000,
                            "interpolation": "LINEAR",
                        }
                        for frame in endpoints
                    ],
                    "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
                },
                "output": {
                    "width": base["width"],
                    "height": base["height"],
                    "frameCount": base["frameCount"],
                    "frameRate": base["frameRate"],
                    "pixelFormat": base["pixelFormat"],
                    "container": "mp4",
                    "videoCodec": "h264",
                },
                "publicationAllowed": False,
            }
        )
        executor = DeterministicOverlayExecutor(self.root)
        real_run = executor._run

        def replace_then_render(*args, **kwargs):
            staged = next(
                self.root.glob(".overlay-work-*/inputs/base.media")
            )
            replacement = self.root / "replacement-staged-base.mp4"
            shutil.copy2(self.video, replacement)
            os.replace(replacement, staged)
            return real_run(*args, **kwargs)

        with patch.object(
            executor,
            "_run",
            side_effect=replace_then_render,
        ), self.assertRaises(RenderArtifactError):
            executor.execute(request)


if __name__ == "__main__":
    unittest.main()
