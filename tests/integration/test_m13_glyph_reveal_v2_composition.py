from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unittest

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    RenderArtifactError,
    decoded_frame_pixel_digest_metadata,
    file_sha256,
    image_digest_metadata,
)
from services.v4_platform.composition import (
    CompositionExecutionError,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
    build_glyph_reveal_composition_result_v2,
    build_glyph_reveal_execution_request_v2,
    build_glyph_reveal_requirement_v2,
    expected_glyph_reveal_output_storage_key_v2,
)
from tests.contract.test_m13_glyph_reveal_contract import (
    FIXTURE_ROOT,
    base_plate_asset,
    mask_assets,
    source_manifest,
)
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
    inspection_evidence_v2,
    requirement_command_v2,
    resealed,
    reveal_schedule,
)
from tests.integration.test_m13_glyph_reveal_composition import (
    BASE_STORAGE_KEY,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    FRAME_COUNT,
    FRAME_RANGE_END,
    FRAME_RANGE_START,
    FRAME_RATE,
    MASK_STORAGE_PREFIX,
    _decoded_frame_evidence,
    _generate_base_plate,
    _generate_small_base_plate,
    _native_composite_params,
    _probe_video_contract,
    _run_media_command,
    _write_small_gray_png,
)


@dataclass
class PreparedV2Run:
    root: Path
    requirement: Any
    execution: dict
    base: dict
    masks: list[dict]
    adapter: DigestPinnedBasePlateGlyphInspectionAdapter
    base_bytes: bytes
    mask_paths: list[Path]


@dataclass
class CompletedV2Run:
    prepared: PreparedV2Run
    artifact: dict
    result: Any


def _stage_full_v2_inputs(
    root: Path,
    *,
    base_bytes: bytes | None = None,
) -> PreparedV2Run:
    base_path = root / BASE_STORAGE_KEY
    if base_bytes is None:
        base_bytes = _generate_base_plate(base_path)
    else:
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_bytes(base_bytes)
    media_probe, pixel_format = _probe_video_contract(base_path)
    if media_probe != {
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "frameCount": FRAME_COUNT,
        "frameRate": FRAME_RATE,
    } or pixel_format != "yuv420p":
        raise AssertionError("generated base does not match the M11 media contract")

    manifest = source_manifest()
    templates = mask_assets(storage_prefix=MASK_STORAGE_PREFIX)
    staged_masks: list[dict] = []
    mask_paths: list[Path] = []
    for index, (record, template) in enumerate(
        zip(manifest["files"], templates, strict=True), start=1
    ):
        source = FIXTURE_ROOT / record["path"]
        destination = root / MASK_STORAGE_PREFIX / f"mask-{index:02d}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        measured = image_digest_metadata(destination)
        asset = deepcopy(template)
        asset.update(
            {
                "storageKey": str(destination.relative_to(root)),
                "byteSize": destination.stat().st_size,
                "sha256": file_sha256(destination),
                "pixelDigest": measured["pixel_digest"],
                "pixelDigestSpec": measured["pixel_digest_spec"],
                "pixelMode": measured["pixel_mode"],
                "width": measured["width"],
                "height": measured["height"],
            }
        )
        staged_masks.append(resealed(asset))
        mask_paths.append(destination)

    base = base_plate_asset(
        sha256=file_sha256(base_path),
        byte_size=base_path.stat().st_size,
        storage_key=BASE_STORAGE_KEY,
    )
    store = InMemoryInspectionEvidenceStore(
        inspection_evidence_v2(base, media_probe=media_probe)
    )
    adapter = DigestPinnedBasePlateGlyphInspectionAdapter(store)
    requirement = build_glyph_reveal_requirement_v2(
        requirement_command_v2(compositeParams=_native_composite_params()),
        base_plate_asset=base,
        mask_assets=staged_masks,
        inspection_adapter=adapter,
    )
    execution = build_glyph_reveal_execution_request_v2(
        requirement,
        base,
        staged_masks,
        adapter,
    )
    return PreparedV2Run(
        root=root,
        requirement=requirement,
        execution=execution,
        base=base,
        masks=staged_masks,
        adapter=adapter,
        base_bytes=base_bytes,
        mask_paths=mask_paths,
    )


def _stage_small_v2_inputs(
    root: Path,
    *,
    stage_pixels: list[set[int]] | None = None,
) -> PreparedV2Run:
    base_path = root / BASE_STORAGE_KEY
    base_bytes = _generate_small_base_plate(base_path)
    media_probe = {
        "width": 64,
        "height": 64,
        "frameCount": FRAME_COUNT,
        "frameRate": FRAME_RATE,
    }
    templates = mask_assets(storage_prefix=MASK_STORAGE_PREFIX)
    stage_pixels = stage_pixels or [set(range(index)) for index in range(6)]
    if len(stage_pixels) != len(templates):
        raise AssertionError("small v2 stage fixture count is invalid")
    staged_masks: list[dict] = []
    mask_paths: list[Path] = []
    for index, (template, covered) in enumerate(
        zip(templates, stage_pixels, strict=True), start=1
    ):
        path = root / MASK_STORAGE_PREFIX / f"mask-{index:02d}.png"
        _write_small_gray_png(path, covered)
        measured = image_digest_metadata(path)
        asset = deepcopy(template)
        asset.update(
            {
                "storageKey": str(path.relative_to(root)),
                "byteSize": path.stat().st_size,
                "sha256": file_sha256(path),
                "pixelDigest": measured["pixel_digest"],
                "pixelDigestSpec": measured["pixel_digest_spec"],
                "pixelMode": measured["pixel_mode"],
                "width": measured["width"],
                "height": measured["height"],
            }
        )
        staged_masks.append(resealed(asset))
        mask_paths.append(path)

    base = base_plate_asset(
        sha256=file_sha256(base_path),
        byte_size=base_path.stat().st_size,
        storage_key=BASE_STORAGE_KEY,
    )
    store = InMemoryInspectionEvidenceStore(
        inspection_evidence_v2(base, media_probe=media_probe)
    )
    adapter = DigestPinnedBasePlateGlyphInspectionAdapter(store)
    requirement = build_glyph_reveal_requirement_v2(
        requirement_command_v2(),
        base_plate_asset=base,
        mask_assets=staged_masks,
        inspection_adapter=adapter,
    )
    execution = build_glyph_reveal_execution_request_v2(
        requirement,
        base,
        staged_masks,
        adapter,
    )
    return PreparedV2Run(
        root=root,
        requirement=requirement,
        execution=execution,
        base=base,
        masks=staged_masks,
        adapter=adapter,
        base_bytes=base_bytes,
        mask_paths=mask_paths,
    )


def _execute_v2(
    root: Path,
    *,
    base_bytes: bytes | None = None,
) -> CompletedV2Run:
    prepared = _stage_full_v2_inputs(root, base_bytes=base_bytes)
    artifact = V4CompositionExecutor.from_artifact_root(
        root
    ).compose_glyph_reveal_v2(prepared.execution)
    result = build_glyph_reveal_composition_result_v2(
        prepared.requirement,
        prepared.execution,
        artifact,
    )
    return CompletedV2Run(prepared=prepared, artifact=artifact, result=result)


def _remux_video(source: Path, destination: Path) -> None:
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-c:v",
            "copy",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-fflags",
            "+bitexact",
            "-y",
            str(destination),
        ]
    )


def _lossless_video_reencode(source: Path, destination: Path) -> None:
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-fps_mode",
            "passthrough",
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-g",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-y",
            str(destination),
        ]
    )


def _lossy_video_reencode(source: Path, destination: Path) -> None:
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-fps_mode",
            "passthrough",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "40",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-x264-params",
            (
                "threads=1:lookahead_threads=1:sliced_threads=0:"
                "sync-lookahead=0:rc-lookahead=0:scenecut=0"
            ),
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-y",
            str(destination),
        ]
    )


class M13GlyphRevealV2CompositionIntegrationTests(unittest.TestCase):
    def test_nonuniform_schedule_repeat_remux_lossless_and_lossy_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _execute_v2(root / "independent-run-a")
            second = _execute_v2(
                root / "independent-run-b",
                base_bytes=first.prepared.base_bytes,
            )
            first_result = first.result.as_dict()

            self.assertEqual(
                first.prepared.requirement.payload_digest,
                second.prepared.requirement.payload_digest,
            )
            self.assertEqual(
                first.prepared.execution["payloadDigest"],
                second.prepared.execution["payloadDigest"],
            )
            self.assertEqual(
                first.artifact["outputDigest"]["decodedFramePixelDigest"],
                second.artifact["outputDigest"]["decodedFramePixelDigest"],
            )
            self.assertEqual(
                first.artifact["outputDigest"]["fileDigest"],
                second.artifact["outputDigest"]["fileDigest"],
            )
            self.assertEqual(
                first_result["outputDigest"], first.artifact["outputDigest"]
            )
            self.assertEqual(
                first.prepared.execution["revealSchedule"], reveal_schedule()
            )

            expected_key = expected_glyph_reveal_output_storage_key_v2(
                first.prepared.execution["workspaceRef"],
                first.prepared.execution["productionRunRef"],
                first.prepared.execution["payloadDigest"],
            )
            self.assertEqual(first.artifact["outputStorageKey"], expected_key)
            first_output = first.prepared.root / expected_key
            second_output = second.prepared.root / expected_key
            self.assertTrue(first_output.is_file())
            self.assertTrue(second_output.is_file())
            self.assertTrue(first_output.is_relative_to(first.prepared.root))
            self.assertTrue(second_output.is_relative_to(second.prepared.root))

            evidence = _decoded_frame_evidence(
                first.prepared.root / BASE_STORAGE_KEY,
                first_output,
            )
            self.assertEqual(
                evidence.output_digests[:FRAME_RANGE_START],
                evidence.base_digests[:FRAME_RANGE_START],
            )
            stage_digests: list[str] = []
            for entry in reveal_schedule():
                start = entry["startFrameInclusive"]
                end = entry["endFrameExclusive"]
                group = evidence.output_digests[start:end]
                with self.subTest(stage=entry["revealOrdinal"]):
                    self.assertEqual(len(group), end - start)
                    self.assertEqual(len(set(group)), 1)
                stage_digests.append(group[0])
            self.assertEqual(len(set(stage_digests)), len(reveal_schedule()))
            self.assertEqual(
                evidence.output_digests[FRAME_RANGE_END:],
                [stage_digests[-1]] * (FRAME_COUNT - FRAME_RANGE_END),
            )
            self.assertEqual(evidence.outside_roi_equal, [True] * FRAME_COUNT)

            remuxed = root / "representation-remux.mkv"
            lossless = root / "representation-lossless.mkv"
            lossy = root / "representation-lossy.mp4"
            _remux_video(first_output, remuxed)
            _lossless_video_reencode(first_output, lossless)
            _lossy_video_reencode(first_output, lossy)

            original_digest = decoded_frame_pixel_digest_metadata(first_output)
            remux_digest = decoded_frame_pixel_digest_metadata(remuxed)
            lossless_digest = decoded_frame_pixel_digest_metadata(lossless)
            lossy_digest = decoded_frame_pixel_digest_metadata(lossy)
            for case, measured in (
                ("remux", remux_digest),
                ("lossless", lossless_digest),
            ):
                with self.subTest(representation=case):
                    self.assertNotEqual(
                        original_digest["fileDigest"], measured["fileDigest"]
                    )
                    self.assertEqual(
                        original_digest["decodedFramePixelDigest"],
                        measured["decodedFramePixelDigest"],
                    )
                    self.assertEqual(
                        measured["decodedFramePixelDigestSpec"],
                        DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                    )
            self.assertNotEqual(
                original_digest["fileDigest"], lossy_digest["fileDigest"]
            )
            self.assertNotEqual(
                original_digest["decodedFramePixelDigest"],
                lossy_digest["decodedFramePixelDigest"],
            )
            for field in ("width", "height", "frameCount"):
                self.assertEqual(original_digest[field], lossy_digest[field])

    def test_output_symlink_escape_is_rejected_without_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "artifact-root"
            outside = Path(directory) / "outside"
            outside.mkdir()
            prepared = _stage_small_v2_inputs(root)
            expected_key = expected_glyph_reveal_output_storage_key_v2(
                prepared.execution["workspaceRef"],
                prepared.execution["productionRunRef"],
                prepared.execution["payloadDigest"],
            )
            output_directory = root / Path(expected_key).parent
            output_directory.parent.mkdir(parents=True, exist_ok=True)
            output_directory.symlink_to(outside, target_is_directory=True)

            executor = V4CompositionExecutor.from_artifact_root(root)
            with self.assertRaises(CompositionExecutionError) as caught:
                executor.compose_glyph_reveal_v2(prepared.execution)
            self.assertIsInstance(caught.exception.__cause__, RenderArtifactError)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual(list(root.rglob("candidate.mp4")), [])
            self.assertEqual(list(root.rglob(".glyph-reveal-work-*")), [])

    def test_v3_rejects_non_cumulative_v2_mask_stages_without_output(self):
        stage_pixels = [
            set(),
            {0},
            {1, 2},
            {0, 1, 2, 3},
            {0, 1, 2, 3, 4},
            {0, 1, 2, 3, 4, 5},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = _stage_small_v2_inputs(root, stage_pixels=stage_pixels)
            executor = V4CompositionExecutor.from_artifact_root(root)
            with self.assertRaises(CompositionExecutionError) as caught:
                executor.compose_glyph_reveal_v2(prepared.execution)
            self.assertIsInstance(caught.exception.__cause__, RenderArtifactError)
            self.assertEqual(
                str(caught.exception.__cause__),
                "glyph cumulative mask coverage regressed",
            )
            self.assertEqual(list(root.rglob("glyph-reveal-*.mp4")), [])
            self.assertEqual(list(root.rglob("candidate.mp4")), [])


if __name__ == "__main__":
    unittest.main()
