from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest

from services.v3_render_core.digests import (
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)
from services.v3_render_core.masked_surface import (
    DeterministicMaskedSurfaceExecutor,
    FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION,
    MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
    MASKED_SURFACE_MAX_ACTIVE_FLAME_SMOKE_PIXEL_FRAMES,
    MASKED_SURFACE_RENDERER_VERSION_CURRENT,
    RenderArtifactError,
    _flame_smoke_v3_workload,
    _flame_stage_filters,
    _procedural_smoke_sample,
    _smoke_stage_filters,
    _write_procedural_smoke,
)
from tests.contract.test_m13_e2_deterministic_effects_contract import (
    _flame_command,
    _local_exposure_command,
    _smoke_command,
)
from tests.integration.test_m13_masked_surface_v2_full_resolution import (
    FRAME_COUNT,
    FRAME_RATE,
    HEIGHT,
    PERFORMANCE_LIMIT_SECONDS,
    WIDTH,
    _frame_hashes,
    _frame_timestamps,
    _stage_fixture,
)
from tests.integration.test_m13_masked_surface_v3 import _stage_inputs


ACTIVE_END = 8


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = sha256(_canonical(result)).hexdigest()
    return result


def _output(base: dict[str, Any]) -> dict[str, Any]:
    return {
        "width": base["width"],
        "height": base["height"],
        "frameCount": base["frameCount"],
        "frameRate": base["frameRate"],
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }


def _base_binding(root: Path, path: Path) -> dict[str, Any]:
    measured = decoded_frame_pixel_digest_metadata(path)
    return {
        "assetVersionRef": "asset-version:flame-smoke-v3-base",
        "assetVersionDigest": "1" * 64,
        "storageKey": str(path.relative_to(root)),
        "fileDigest": file_digest(path),
        "pixelDigest": measured["decodedFramePixelDigest"],
        "pixelDigestSpec": measured["decodedFramePixelDigestSpec"],
        "width": measured["width"],
        "height": measured["height"],
        "frameCount": measured["frameCount"],
        "frameRate": FRAME_RATE,
        "pixelFormat": "yuv420p",
    }


def _image_binding(
    root: Path, path: Path, *, reference: str, digest_character: str
) -> dict[str, Any]:
    measured = image_digest_metadata(path)
    return {
        "assetVersionRef": reference,
        "assetVersionDigest": digest_character * 64,
        "storageKey": str(path.relative_to(root)),
        "fileDigest": file_digest(path),
        "pixelDigest": measured["pixel_digest"],
        "pixelDigestSpec": measured["pixel_digest_spec"],
        "pixelMode": measured["pixel_mode"],
        "width": measured["width"],
        "height": measured["height"],
    }


def _local_exposure_stage(
    base: dict[str, Any], mask: dict[str, Any], *, workspace: str, run: str
) -> dict[str, Any]:
    profile = _local_exposure_command()
    requirement_ref = "requirement:flame-v3-local-exposure"
    requirement_digest = "a" * 64
    return _seal(
        {
            "schemaVersion": MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": "execution:flame-v3-local-exposure",
            "v5ExecutionRequestDigest": "9" * 64,
            "workspaceRef": workspace,
            "productionRunRef": run,
            "requirementSchemaVersion": (
                "v5.m13-local-exposure-requirement.v1"
            ),
            "requirementRef": requirement_ref,
            "requirementDigest": requirement_digest,
            "effectMode": "LOCAL_EXPOSURE",
            "targetShot": {
                "shotRef": "shot:flame-smoke-v3",
                "shotVersionRef": "shot-version:flame-smoke-v3:v1",
                "shotVersionDigest": "8" * 64,
            },
            "basePlate": deepcopy(base),
            "mask": deepcopy(mask),
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": ACTIVE_END,
            "explicitSchedule": deepcopy(profile["explicitSchedule"]),
            "trajectoryKeyframes": deepcopy(profile["trajectoryKeyframes"]),
            "intensityCurve": deepcopy(profile["intensityCurve"]),
            "exposureCurve": deepcopy(profile["exposureCurve"]),
            "position": deepcopy(profile["position"]),
            "scale": deepcopy(profile["scale"]),
            "perspective": deepcopy(profile["perspective"]),
            "blendMode": profile["blendMode"],
            "layer": profile["layer"],
            "output": _output(base),
            "publicationAllowed": False,
        }
    )


def _flame_request(
    base: dict[str, Any], mask: dict[str, Any], *, workspace: str, run: str
) -> dict[str, Any]:
    local = _local_exposure_stage(base, mask, workspace=workspace, run=run)
    profile = _flame_command(
        SimpleNamespace(
            requirement_ref=local["requirementRef"],
            payload_digest=local["requirementDigest"],
        )
    )
    profile["stateSchedule"] = [
        {"state": "LIT", "startFrameInclusive": 0, "endFrameExclusive": 2},
        {
            "state": "DIMMING",
            "startFrameInclusive": 2,
            "endFrameExclusive": 4,
        },
        {
            "state": "EXTINGUISHED",
            "startFrameInclusive": 4,
            "endFrameExclusive": 5,
        },
        {
            "state": "EMBER",
            "startFrameInclusive": 5,
            "endFrameExclusive": 6,
        },
        {"state": "DARK", "startFrameInclusive": 6, "endFrameExclusive": 8},
    ]
    return _seal(
        {
            "schemaVersion": FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": "execution:flame-v3",
            "v5ExecutionRequestDigest": "b" * 64,
            "workspaceRef": workspace,
            "productionRunRef": run,
            "requirementSchemaVersion": (
                "v5.m13-flame-extinguish-requirement.v1"
            ),
            "requirementRef": "requirement:flame-v3",
            "requirementDigest": "c" * 64,
            "effectMode": "FLAME_EXTINGUISH",
            "targetShot": deepcopy(local["targetShot"]),
            "basePlate": deepcopy(base),
            "flameMask": deepcopy(mask),
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": ACTIVE_END,
            "stateSchedule": deepcopy(profile["stateSchedule"]),
            "brightnessCurve": deepcopy(profile["brightnessCurve"]),
            "alphaCurve": deepcopy(profile["alphaCurve"]),
            "localExposureRequirementRef": local["requirementRef"],
            "localExposureRequirementDigest": local["requirementDigest"],
            "localExposureResultRef": "result:flame-v3-local-exposure",
            "localExposureResultDigest": "d" * 64,
            "localExposureStage": local,
            "blendMode": profile["blendMode"],
            "layer": profile["layer"],
            "output": _output(base),
            "publicationAllowed": False,
        }
    )


def _smoke_request(
    base: dict[str, Any],
    emission: dict[str, Any],
    *,
    workspace: str,
    run: str,
    smoke_layer: dict[str, Any] | None,
    seed: int = 912_345,
) -> dict[str, Any]:
    procedural = smoke_layer is None
    profile = _smoke_command(procedural=procedural)
    return _seal(
        {
            "schemaVersion": FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": (
                "execution:smoke-v3-procedural"
                if procedural
                else "execution:smoke-v3-pinned"
            ),
            "v5ExecutionRequestDigest": ("e" if procedural else "f") * 64,
            "workspaceRef": workspace,
            "productionRunRef": run,
            "requirementSchemaVersion": "v5.m13-smoke-requirement.v1",
            "requirementRef": (
                "requirement:smoke-v3-procedural"
                if procedural
                else "requirement:smoke-v3-pinned"
            ),
            "requirementDigest": ("1" if procedural else "2") * 64,
            "effectMode": "SMOKE",
            "targetShot": {
                "shotRef": "shot:flame-smoke-v3",
                "shotVersionRef": "shot-version:flame-smoke-v3:v1",
                "shotVersionDigest": "8" * 64,
            },
            "basePlate": deepcopy(base),
            "smokeSourceKind": profile["smokeSourceKind"],
            "smokeLayer": deepcopy(smoke_layer),
            "emissionMask": deepcopy(emission),
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": ACTIVE_END,
            "opacitySchedule": deepcopy(profile["opacitySchedule"]),
            "positionKeyframes": deepcopy(profile["positionKeyframes"]),
            "scaleKeyframes": deepcopy(profile["scaleKeyframes"]),
            "driftKeyframes": deepcopy(profile["driftKeyframes"]),
            "dissipationCurve": deepcopy(profile["dissipationCurve"]),
            "algorithmIdentity": profile["algorithmIdentity"],
            "algorithmVersion": profile["algorithmVersion"],
            "deterministicSeed": seed if procedural else None,
            "blendMode": profile["blendMode"],
            "layer": profile["layer"],
            "output": _output(base),
            "publicationAllowed": False,
        }
    )


def _legacy_paths(root: Path, request: dict[str, Any]) -> tuple[Path, Path]:
    workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
    run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
    directory = root / workspace / run / "masked-surface"
    directory.mkdir(parents=True, exist_ok=True)
    v1 = directory / f"masked-surface-{request['payloadDigest']}.mp4"
    v2 = directory / f"masked-surface-v2-{request['payloadDigest']}.mp4"
    v1.write_bytes(b"historical-v1-artifact")
    v2.write_bytes(b"historical-v2-artifact")
    return v1, v2


def _execute_twice(
    executor: DeterministicMaskedSurfaceExecutor, request: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[float]]:
    results: list[dict[str, Any]] = []
    elapsed: list[float] = []
    for _ in range(2):
        started = time.monotonic()
        results.append(executor.execute(request))
        elapsed.append(time.monotonic() - started)
    return results, elapsed


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13FlameSmokeRendererV3FullResolutionTests(unittest.TestCase):
    def test_full_profile_flame_and_both_smoke_sources_are_sparse_and_repeatable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_path, mask_path = _stage_fixture(root)
            smoke_path = root / "inputs" / "smoke-layer.png"
            emission_path = root / "inputs" / "emission-mask.png"
            shutil.copyfile(mask_path, smoke_path)
            shutil.copyfile(mask_path, emission_path)
            base = _base_binding(root, base_path)
            flame_mask = _image_binding(
                root,
                mask_path,
                reference="asset-version:flame-v3-mask",
                digest_character="3",
            )
            smoke_layer = _image_binding(
                root,
                smoke_path,
                reference="asset-version:smoke-v3-layer",
                digest_character="4",
            )
            emission = _image_binding(
                root,
                emission_path,
                reference="asset-version:smoke-v3-emission",
                digest_character="5",
            )
            requests = {
                "flame": _flame_request(
                    base,
                    flame_mask,
                    workspace="workspace:flame-v3-full",
                    run="run:flame-v3-full",
                ),
                "smoke-pinned": _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-pinned-full",
                    run="run:smoke-v3-pinned-full",
                    smoke_layer=smoke_layer,
                ),
                "smoke-procedural": _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-procedural-full",
                    run="run:smoke-v3-procedural-full",
                    smoke_layer=None,
                ),
            }
            self.assertEqual((WIDTH, HEIGHT, FRAME_COUNT, FRAME_RATE), (
                base["width"],
                base["height"],
                base["frameCount"],
                base["frameRate"],
            ))
            for request in requests.values():
                profile = _flame_smoke_v3_workload(request)
                self.assertEqual("v3", profile["executionProfile"])
                self.assertEqual(((0, ACTIVE_END),), profile["activeIntervals"])
                self.assertEqual(ACTIVE_END, profile["activeFrameCount"])
                self.assertEqual(
                    WIDTH * HEIGHT * ACTIVE_END,
                    profile["activePixelFrames"],
                )
                self.assertLessEqual(
                    profile["activePixelFrames"],
                    MASKED_SURFACE_MAX_ACTIVE_FLAME_SMOKE_PIXEL_FRAMES,
                )
            self.assertEqual(
                {"LIT", "DIMMING", "EXTINGUISHED", "EMBER", "DARK"},
                {item["state"] for item in requests["flame"]["stateSchedule"]},
            )

            flame_graph = ";".join(
                _flame_stage_filters(
                    requests["flame"],
                    input_label="0:v",
                    mask_input_index=1,
                    prefix="flamecheck",
                )[0]
            )
            smoke_graph = ";".join(
                _smoke_stage_filters(
                    requests["smoke-pinned"],
                    input_label="0:v",
                    smoke_input_index=1,
                    emission_input_index=2,
                    prefix="smokecheck",
                )[0]
            )
            for graph in (flame_graph, smoke_graph):
                self.assertIn(
                    f"trim=start_frame={ACTIVE_END}:end_frame={FRAME_COUNT}",
                    graph,
                )
                self.assertIn("concat=n=2:v=1:a=0", graph)
                self.assertIn("N+0", graph)
            self.assertNotIn("localexposure", flame_graph)

            executor = DeterministicMaskedSurfaceExecutor(root)
            base_hashes = _frame_hashes(base_path)
            all_results: dict[str, dict[str, Any]] = {}
            all_elapsed: dict[str, list[float]] = {}
            for label, request in requests.items():
                legacy_v1, legacy_v2 = _legacy_paths(root, request)
                results, elapsed = _execute_twice(executor, request)
                first, second = results
                all_results[label] = first
                all_elapsed[label] = elapsed
                self.assertTrue(
                    all(duration <= PERFORMANCE_LIMIT_SECONDS for duration in elapsed),
                    msg=f"{label} elapsed={elapsed}",
                )
                self.assertEqual("3", MASKED_SURFACE_RENDERER_VERSION_CURRENT)
                self.assertEqual("3", first["rendererVersion"])
                self.assertIn(
                    f"masked-surface-v3-{request['payloadDigest']}.mp4",
                    first["outputStorageKey"],
                )
                self.assertEqual(first["outputStorageKey"], second["outputStorageKey"])
                self.assertEqual(first["outputDigest"], second["outputDigest"])
                self.assertEqual(b"historical-v1-artifact", legacy_v1.read_bytes())
                self.assertEqual(b"historical-v2-artifact", legacy_v2.read_bytes())
                output_path = root / first["outputStorageKey"]
                output_hashes = _frame_hashes(output_path)
                self.assertEqual(FRAME_COUNT, len(output_hashes))
                self.assertTrue(
                    all(
                        base_hashes[frame] == output_hashes[frame]
                        for frame in range(ACTIVE_END, FRAME_COUNT)
                    )
                )
                self.assertTrue(
                    any(
                        base_hashes[frame] != output_hashes[frame]
                        for frame in range(ACTIVE_END)
                    )
                )
                self.assertEqual(
                    [frame * 512 for frame in range(FRAME_COUNT)],
                    _frame_timestamps(output_path),
                )
                self.assertGreater(first["outputByteSize"], 0)
                print(
                    "M13_RENDERER_V3_PERF "
                    f"stage={label} run1_seconds={elapsed[0]:.3f} "
                    f"run2_seconds={elapsed[1]:.3f} "
                    f"output_bytes={first['outputByteSize']}"
                )
            self.assertNotEqual(
                all_results["smoke-pinned"]["outputDigest"],
                all_results["smoke-procedural"]["outputDigest"],
            )
            self.assertEqual(
                {"flame", "smoke-pinned", "smoke-procedural"},
                set(all_elapsed),
            )

    def test_smoke_seed_and_pinned_source_change_authoritative_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, original = _stage_inputs(root)
            original_path = root / original["storageKey"]
            emission = deepcopy(original)
            emission["assetVersionRef"] = "asset-version:smoke-emission-micro"
            emission["assetVersionDigest"] = "6" * 64
            smoke_a = deepcopy(original)
            smoke_a["assetVersionRef"] = "asset-version:smoke-pinned-a"
            smoke_a["assetVersionDigest"] = "7" * 64
            alternate_path = root / "inputs" / "smoke-pinned-b.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=white:size=16x12",
                    "-frames:v",
                    "1",
                    "-c:v",
                    "png",
                    "-threads:v",
                    "1",
                    "-y",
                    str(alternate_path),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            smoke_b = _image_binding(
                root,
                alternate_path,
                reference="asset-version:smoke-pinned-b",
                digest_character="8",
            )
            self.assertNotEqual(file_digest(original_path), file_digest(alternate_path))
            requests = [
                _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-seed-a",
                    run="run:smoke-v3-seed-a",
                    smoke_layer=None,
                    seed=912_345,
                ),
                _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-seed-b",
                    run="run:smoke-v3-seed-b",
                    smoke_layer=None,
                    seed=912_346,
                ),
                _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-pinned-a",
                    run="run:smoke-v3-pinned-a",
                    smoke_layer=smoke_a,
                ),
                _smoke_request(
                    base,
                    emission,
                    workspace="workspace:smoke-v3-pinned-b",
                    run="run:smoke-v3-pinned-b",
                    smoke_layer=smoke_b,
                ),
            ]
            executor = DeterministicMaskedSurfaceExecutor(root)
            digests = [executor.execute(request)["outputDigest"] for request in requests]
            self.assertNotEqual(digests[0], digests[1])
            self.assertNotEqual(digests[2], digests[3])

    def test_smoke_zero_tail_and_fixed_workload_budget_are_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, emission = _stage_inputs(root)
            emission["assetVersionRef"] = "asset-version:smoke-zero-emission"
            emission["assetVersionDigest"] = "9" * 64
            request = _smoke_request(
                base,
                emission,
                workspace="workspace:smoke-v3-zero-tail",
                run="run:smoke-v3-zero-tail",
                smoke_layer=None,
            )
            request["opacitySchedule"] = [
                {"frame": 0, "valuePermille": 700, "interpolation": "STEP"},
                {"frame": 3, "valuePermille": 0, "interpolation": "STEP"},
                {"frame": 7, "valuePermille": 0, "interpolation": "STEP"},
            ]
            request = _seal(request)
            profile = _flame_smoke_v3_workload(request)
            self.assertEqual(((0, 3),), profile["activeIntervals"])
            self.assertEqual(3, profile["activeFrameCount"])

            offset = _smoke_request(
                base,
                emission,
                workspace="workspace:smoke-v3-global-frame",
                run="run:smoke-v3-global-frame",
                smoke_layer=None,
            )
            offset["frameRangeStartInclusive"] = 3
            for field in (
                "opacitySchedule",
                "positionKeyframes",
                "scaleKeyframes",
                "driftKeyframes",
                "dissipationCurve",
            ):
                offset[field][0]["frame"] = 3
                offset[field][-1]["frame"] = 7
            offset = _seal(offset)
            offset_graph = ";".join(
                _smoke_stage_filters(
                    offset,
                    input_label="0:v",
                    smoke_input_index=1,
                    emission_input_index=2,
                    prefix="globalframe",
                )[0]
            )
            self.assertIn("trim=start_frame=3:end_frame=8", offset_graph)
            self.assertIn("N+3", offset_graph)
            self.assertIn("n+3", offset_graph)
            procedural = root / "procedural-global.gray"
            _write_procedural_smoke(procedural, seed=912_345, frame_count=12)
            payload = procedural.read_bytes()
            tile_bytes = 32 * 32
            self.assertEqual(
                _procedural_smoke_sample(912_345, 3, 0, 0),
                payload[3 * tile_bytes],
            )

            oversized = deepcopy(request)
            oversized["basePlate"]["frameCount"] = 10_000_000
            oversized["output"]["frameCount"] = 10_000_000
            oversized = _seal(oversized)
            with self.assertRaisesRegex(
                RenderArtifactError, "output pixel-frame budget exceeded"
            ):
                _flame_smoke_v3_workload(oversized)


if __name__ == "__main__":
    unittest.main()
