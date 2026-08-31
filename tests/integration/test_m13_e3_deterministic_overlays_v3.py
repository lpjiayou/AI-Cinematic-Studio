from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import unittest

from services.v3_render_core.composition import RenderArtifactError
from services.v3_render_core.deterministic_overlays import (
    DeterministicOverlayExecutor,
    OVERLAY_V3_REQUEST_SCHEMA_VERSION,
    build_overlay_stage_filters,
    overlay_text_bytes,
    validate_overlay_preview_stage,
)
from services.v3_render_core.digests import (
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)


WIDTH = 160
HEIGHT = 120
FRAME_RATE = 6
FRAME_COUNT = 12
START = 1
END = 11
RAW = "a" * 64


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["payloadDigest"] = sha256(_canonical(result)).hexdigest()
    return result


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def _constant_xy(x: int, y: int) -> list[dict[str, Any]]:
    return [
        {"frame": START, "xPermille": x, "yPermille": y, "interpolation": "STEP"},
        {"frame": END - 1, "xPermille": x, "yPermille": y, "interpolation": "STEP"},
    ]


def _constant_rotation(value: int = 0) -> list[dict[str, Any]]:
    return [
        {"frame": START, "degreesMilli": value, "interpolation": "STEP"},
        {"frame": END - 1, "degreesMilli": value, "interpolation": "STEP"},
    ]


def _constant_opacity(value: int = 1000) -> list[dict[str, Any]]:
    return [
        {"frame": START, "valuePermille": value, "interpolation": "STEP"},
        {"frame": END - 1, "valuePermille": value, "interpolation": "STEP"},
    ]


def _perspective() -> list[dict[str, Any]]:
    quad = [0, 0, 1000, 0, 0, 1000, 1000, 1000]
    return [
        {"frame": START, "quadPermille": quad, "interpolation": "STEP"},
        {"frame": END - 1, "quadPermille": quad, "interpolation": "STEP"},
    ]


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg is required for real V3 overlay integration",
)
class M13E3DeterministicOverlaysV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="m13-e3-v3-")
        self.root = Path(self.temporary.name)
        inputs = self.root / "inputs"
        inputs.mkdir()
        self.base_path = inputs / "base.mp4"
        _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-f", "lavfi", "-i",
                f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FRAME_RATE}",
                "-frames:v", str(FRAME_COUNT), "-c:v", "libx264", "-crf", "0",
                "-pix_fmt", "yuv420p", "-threads:v", "1", "-x264-params",
                "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0:rc-lookahead=0:scenecut=0",
                "-y", str(self.base_path),
            ]
        )
        fixture = Path(__file__).parents[1] / "fixtures" / "v5_fonts" / "ACS-Technical-CJK.ttf"
        self.font_path = inputs / fixture.name
        shutil.copyfile(fixture, self.font_path)
        self.mole_path = inputs / "mole.png"
        self.scar_path = inputs / "scar.png"
        _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=black@0.0:size=16x12,format=rgba",
                "-vf", "drawbox=x=5:y=4:w=5:h=5:color=black@1:t=fill:replace=1",
                "-frames:v", "1", "-c:v", "png", "-threads:v", "1", "-y",
                str(self.mole_path),
            ]
        )
        _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=black@0.0:size=22x10,format=rgba",
                "-vf", "drawbox=x=1:y=4:w=20:h=2:color=red@1:t=fill:replace=1",
                "-frames:v", "1", "-c:v", "png", "-threads:v", "1", "-y",
                str(self.scar_path),
            ]
        )
        decoded = decoded_frame_pixel_digest_metadata(self.base_path)
        self.base = {
            "assetVersionRef": "asset-version:base:v1",
            "assetVersionDigest": "1" * 64,
            "storageKey": "inputs/base.mp4",
            "fileDigest": file_digest(self.base_path),
            "pixelDigest": decoded["decodedFramePixelDigest"],
            "pixelDigestSpec": decoded["decodedFramePixelDigestSpec"],
            "width": WIDTH, "height": HEIGHT, "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE, "pixelFormat": "yuv420p",
        }
        self.output = {
            "width": WIDTH, "height": HEIGHT, "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE, "pixelFormat": "yuv420p",
            "container": "mp4", "videoCodec": "h264",
        }
        self.executor = DeterministicOverlayExecutor(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _common(self, mode: str) -> dict[str, Any]:
        return {
            "schemaVersion": OVERLAY_V3_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": f"overlay-execution:{mode.lower()}",
            "v5ExecutionRequestDigest": "2" * 64,
            "workspaceRef": "workspace:m13-e3-v3",
            "productionRunRef": "run:m13-e3-v3",
            "requirementRef": f"requirement:{mode.lower()}",
            "requirementDigest": "3" * 64,
            "effectMode": mode,
            "basePlate": deepcopy(self.base),
            "output": deepcopy(self.output),
            "publicationAllowed": False,
        }

    def _nameplate(self, text: str, writing_mode: str) -> dict[str, Any]:
        value = self._common("NAMEPLATE_TEXT")
        value["overlayAsset"] = {
            "assetVersionRef": "asset-version:font:v2",
            "assetVersionDigest": "4" * 64,
            "storageKey": "inputs/ACS-Technical-CJK.ttf",
            "fileDigest": file_digest(self.font_path),
            "validationRef": "font-validation:v1",
            "validationDigest": "5" * 64,
            "licenseBindingRef": "font-license-binding:v1",
            "licenseBindingDigest": "6" * 64,
        }
        value["overlaySpec"] = {
            "targetShot": {"shotRef": "shot:sh17", "shotVersionRef": "shot-version:sh17:v1", "shotVersionDigest": "7" * 64},
            "frameRangeStartInclusive": START,
            "frameRangeEndExclusive": END,
            "blendMode": "NORMAL", "layer": 20,
            "resolvedText": text,
            "resolvedTextDigest": sha256(_canonical({"utf8": text})).hexdigest(),
            "language": "zh-CN",
            "layout": {
                "writingMode": writing_mode, "alignment": "CENTER",
                "fontSizeMilliPixels": 28000, "letterSpacingMilliPixels": 0,
                "lineSpacingMilliPixels": 0, "maxWidthPixels": 100,
                "maxHeightPixels": 90,
            },
            "positionKeyframes": _constant_xy(300, 150),
            "scaleKeyframes": _constant_xy(1000, 1000),
            "rotationKeyframes": _constant_rotation(),
            "perspectiveKeyframes": _perspective(),
            "opacityCurve": _constant_opacity(),
            "trackingKeyframes": _constant_xy(0, 0),
        }
        return _seal(value)

    def _face(self, mark_type: str) -> dict[str, Any]:
        path = self.mole_path if mark_type == "MOLE" else self.scar_path
        measured = image_digest_metadata(path)
        value = self._common("FACE_MARK_COMPENSATION")
        value["overlayAsset"] = {
            "assetVersionRef": f"asset-version:{mark_type.lower()}:v1",
            "assetVersionDigest": "8" * 64,
            "storageKey": f"inputs/{path.name}",
            "fileDigest": file_digest(path),
            "pixelDigest": measured["pixel_digest"],
            "pixelDigestSpec": measured["pixel_digest_spec"],
            "pixelMode": measured["pixel_mode"],
            "width": measured["width"], "height": measured["height"],
        }
        value["overlaySpec"] = {
            "targetShot": {"shotRef": "shot:sh18", "shotVersionRef": "shot-version:sh18:v1", "shotVersionDigest": "9" * 64},
            "frameRangeStartInclusive": START,
            "frameRangeEndExclusive": END,
            "blendMode": "NORMAL", "layer": 21,
            "markType": mark_type,
            "faceRegion": "LEFT_CHEEK" if mark_type == "MOLE" else "RIGHT_BROW",
            "trackingSourceKind": "EXPLICIT_KEYFRAMES",
            "trackingKeyframes": _constant_xy(650, 400),
            "scaleKeyframes": _constant_xy(1000, 1000),
            "rotationKeyframes": _constant_rotation(0 if mark_type == "MOLE" else -12000),
            "opacityCurve": _constant_opacity(900),
            "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
        }
        return _seal(value)

    def test_horizontal_and_vertical_chinese_are_real_and_repeatable(self) -> None:
        horizontal = self._nameplate("长安", "HORIZONTAL_LTR")
        vertical = self._nameplate("名牌", "VERTICAL_RTL")
        first = self.executor.execute(horizontal)
        replay = self.executor.execute(horizontal)
        vertical_result = self.executor.execute(vertical)
        self.assertEqual(first["outputDigest"]["decodedFramePixelDigest"], replay["outputDigest"]["decodedFramePixelDigest"])
        self.assertNotEqual(first["outputDigest"]["decodedFramePixelDigest"], vertical_result["outputDigest"]["decodedFramePixelDigest"])
        self.assertEqual(overlay_text_bytes(horizontal), "长安".encode())
        self.assertEqual(overlay_text_bytes(vertical), "名\n牌".encode())
        self.assertTrue(first["executionManifestDigest"].startswith("sha256:"))

    def test_mole_and_scar_are_real_and_repeatable(self) -> None:
        mole, scar = self._face("MOLE"), self._face("SCAR")
        first = self.executor.execute(mole)
        replay = self.executor.execute(mole)
        scar_result = self.executor.execute(scar)
        self.assertEqual(first["outputDigest"]["decodedFramePixelDigest"], replay["outputDigest"]["decodedFramePixelDigest"])
        self.assertNotEqual(first["outputDigest"]["decodedFramePixelDigest"], scar_result["outputDigest"]["decodedFramePixelDigest"])

    def test_preview_helpers_share_strict_standalone_semantics(self) -> None:
        request = self._face("MOLE")
        validated = validate_overlay_preview_stage(request)
        filters, label = build_overlay_stage_filters(validated, input_label="phase4out", overlay_input_label="5:v", prefix="facemark")
        self.assertEqual(label, "facemarkout")
        self.assertTrue(any("ALWAYS" not in item and "overlay=" in item for item in filters))
        rejected = deepcopy(request)
        rejected["overlaySpec"]["occlusionPolicy"] = "CLIP_TO_FACE_REGION"
        rejected = _seal({key: value for key, value in rejected.items() if key != "payloadDigest"})
        with self.assertRaises(RenderArtifactError):
            validate_overlay_preview_stage(rejected)

    def test_missing_glyph_and_tampered_inputs_fail_closed(self) -> None:
        missing = self._nameplate("长安", "HORIZONTAL_LTR")
        geist = Path(__file__).parents[1] / "fixtures" / "v5_fonts" / "Geist-Regular.ttf"
        target = self.root / "inputs" / "Geist-Regular.ttf"
        shutil.copyfile(geist, target)
        missing["overlayAsset"]["storageKey"] = "inputs/Geist-Regular.ttf"
        missing["overlayAsset"]["fileDigest"] = file_digest(target)
        missing = _seal({key: value for key, value in missing.items() if key != "payloadDigest"})
        with self.assertRaisesRegex(RenderArtifactError, "missing U\\+"):
            self.executor.execute(missing)

        tampered = self._face("SCAR")
        self.scar_path.write_bytes(self.scar_path.read_bytes() + b"tamper")
        with self.assertRaises(RenderArtifactError):
            self.executor.execute(tampered)


if __name__ == "__main__":
    unittest.main()
