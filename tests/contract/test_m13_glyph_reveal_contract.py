from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from services.v3_render_core.digests import (
    IMAGE_PIXEL_DIGEST_SPEC,
    DigestError,
    file_digest,
    image_digest_metadata,
)
from services.v4_platform.composition import (
    GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
    CompositionRequestValidationError,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production.foundation import (
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal import (
    BASE_PLATE_GLYPH_INSPECTION_METHOD,
    BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION,
    BASE_PLATE_GLYPH_INSPECTOR_IDENTITY,
    GLYPH_MASK_ASSET_ROLE,
    GLYPH_REVEAL_BLEND_MODE,
    GLYPH_REVEAL_COMPOSER_CAPABILITY,
    GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION,
    GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION,
    GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION,
    LOCAL_EVIDENCE_PROVENANCE,
    VIDEO_PIXEL_DIGEST_SPEC,
    V4_COMPOSITION_ADAPTER_IDENTITY,
    BasePlateGlyphInspectionRequiredError,
    GlyphRevealArtifactError,
    GlyphRevealError,
    GlyphRevealFrameRangeError,
    GlyphRevealMaskCountError,
    NondeterministicCompositeParamsError,
    ReadableGlyphInBasePlateError,
    build_glyph_reveal_composition_result,
    build_glyph_reveal_execution_request,
    build_glyph_reveal_requirement,
)


WORKSPACE = "workspace-m13-glyph-reveal"
RUN = "production-run-ep01-m13"
SHOT = "EP01_SH15"
REQUIREMENT = "m13-glyph-reveal-ep01-sh15-zhen"
BASE_ASSET_REF = "asset-version-ep01-sh15-base-plate"
MASK_ASSET_REFS = tuple(
    f"asset-version-zhen-cumulative-mask-{ordinal:02d}"
    for ordinal in range(1, 7)
)
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "m13" / "zhen"


def sealed(payload: dict) -> dict:
    result = deepcopy(payload)
    result["payloadDigest"] = _digest(result)
    return result


def resealed(value: dict) -> dict:
    payload = deepcopy(value)
    payload.pop("payloadDigest", None)
    return sealed(payload)


def source_manifest() -> dict:
    return json.loads(
        (FIXTURE_ROOT / "source_manifest.json").read_text(encoding="utf-8")
    )


def composite_params() -> dict:
    return {
        "position": {"xPixels": 16, "yPixels": 16},
        "scale": {"widthPixels": 32, "heightPixels": 32},
        "perspective": {
            "topLeft": [0, 0],
            "topRight": [31, 0],
            "bottomLeft": [0, 31],
            "bottomRight": [31, 31],
        },
        "blendMode": GLYPH_REVEAL_BLEND_MODE,
    }


def requirement_command(**overrides) -> dict:
    command = {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "requirementRef": REQUIREMENT,
        "glyphSlug": "zhen",
        "targetShotRef": SHOT,
        "frameRangeStart": 12,
        "frameRangeEnd": 30,
        "revealFrameCount": 6,
        "maskAssetRefs": list(MASK_ASSET_REFS),
        "basePlateAssetRef": BASE_ASSET_REF,
        "compositeParams": composite_params(),
    }
    command.update(overrides)
    return command


def base_plate_asset(
    *,
    sha256: str = "a" * 64,
    byte_size: int = 4096,
    storage_key: str = "asset-versions/video/ep01/sh15-base-plate.mp4",
) -> dict:
    """Return a representative immutable, REGISTERED M11 AssetVersion."""

    return sealed(
        {
            "schemaVersion": "v5.k2-real-video-asset-version.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRef": "real-video-asset-ep01-sh15",
            "assetVersionRef": BASE_ASSET_REF,
            "version": 2,
            "ordinal": 15,
            "creativeShotRef": SHOT,
            "creativeShotVersionRef": "creative-shot-version-ep01-sh15-v1",
            "creativeShotDigest": "1" * 64,
            "generationRequestRef": "real-video-request-ep01-sh15",
            "generationRequestVersionRef": "real-video-request-version-ep01-sh15-v1",
            "generationRequestDigest": "2" * 64,
            "sourceImageAssetVersionRef": "real-image-asset-version-ep01-sh15-v1",
            "sourceImageAssetVersionDigest": "3" * 64,
            "sourceCandidateRef": "real-video-candidate-ep01-sh15-v2",
            "sourceCandidateDigest": "4" * 64,
            "revisionRef": "real-video-revision-ep01-v2",
            "sourceRuntimeCandidateRef": "wan-candidate-ep01-sh15-v2",
            "semanticVisualQcRef": "semantic-visual-qc-ep01-sh15-v2",
            "semanticVisualQcDigest": "5" * 64,
            "humanSelectionRef": "human-selection-ep01-sh15-v2",
            "humanSelectionVersion": 1,
            "humanSelectionDigest": "6" * 64,
            "supersedesAssetVersionRef": "real-video-asset-version-ep01-sh15-v1",
            "supersedesAssetVersionDigest": "7" * 64,
            "mediaKind": "video",
            "mediaType": "video/mp4",
            "artifactRef": "real-video-artifact-ep01-sh15-v2",
            "storageKey": storage_key,
            "byteSize": byte_size,
            "sha256": sha256,
            "provenance": "LOCAL_EVIDENCE",
            "state": "REGISTERED",
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": "v5.k2.real-video-admission.v1",
            "createdAt": "2026-08-29T00:00:00Z",
        }
    )


def mask_assets(
    *, storage_prefix: str = "asset-versions/image/zhen"
) -> list[dict]:
    manifest = source_manifest()
    glyph_manifest_digest = manifest["glyphAssetSpec"]["fileDigest"]
    return [
        sealed(
            {
                "schemaVersion": "v5.asset-version.v1",
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "assetVersionRef": MASK_ASSET_REFS[index - 1],
                "mediaKind": "image",
                "mediaType": "image/png",
                "storageKey": f"{storage_prefix}/mask-{index:02d}.png",
                "byteSize": record["bytes"],
                "sha256": record["fileDigest"].removeprefix("sha256:"),
                "pixelDigest": record["pixelDigest"],
                "pixelDigestSpec": IMAGE_PIXEL_DIGEST_SPEC,
                "pixelMode": "RGBA",
                "width": 1024,
                "height": 1024,
                "assetRole": GLYPH_MASK_ASSET_ROLE,
                "glyphSlug": "zhen",
                "revealOrdinal": index,
                "glyphManifestDigest": glyph_manifest_digest,
                "state": "REGISTERED",
                "publicationAllowed": False,
            }
        )
        for index, record in enumerate(manifest["files"], start=1)
    ]


def inspection_evidence(
    base_asset: dict,
    *,
    verdict: str = "VERIFIED_NO_READABLE_GLYPH",
    base_asset_ref: str | None = None,
    base_asset_digest: str | None = None,
    base_file_digest: str | None = None,
    media_probe: dict | None = None,
) -> dict:
    return sealed(
        {
            "schemaVersion": BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "inspectionRef": "inspection-ep01-sh15-no-readable-glyph",
            "inspectorIdentity": BASE_PLATE_GLYPH_INSPECTOR_IDENTITY,
            "method": BASE_PLATE_GLYPH_INSPECTION_METHOD,
            "provenance": LOCAL_EVIDENCE_PROVENANCE,
            "basePlateAssetRef": base_asset_ref or base_asset["assetVersionRef"],
            "basePlateAssetDigest": (
                base_asset_digest or base_asset["payloadDigest"]
            ),
            "basePlateFileDigest": base_file_digest or base_asset["sha256"],
            "mediaProbe": media_probe
            or {
                "width": 64,
                "height": 64,
                "frameCount": 49,
                "frameRate": 24,
            },
            "verdict": verdict,
            "publicationAllowed": False,
        }
    )


class StaticBasePlateGlyphInspectionPort:
    def __init__(self, evidence: dict) -> None:
        self.evidence = deepcopy(evidence)
        self.calls: list[dict] = []

    def inspect_base_plate(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        target_shot_ref: str,
        base_plate_asset: dict,
    ) -> dict:
        self.calls.append(
            {
                "workspaceRef": workspace_ref,
                "productionRunRef": production_run_ref,
                "targetShotRef": target_shot_ref,
                "basePlateAsset": deepcopy(base_plate_asset),
            }
        )
        return deepcopy(self.evidence)


class FakeGlyphComposer:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root
        self.calls: list[dict] = []

    def compose_glyph_reveal(self, **command) -> dict:
        self.calls.append(deepcopy(command))
        file_hex = "1" * 64
        runtime_versions = {
            "ffmpegVersion": "ffmpeg version m13-contract-fixture",
            "ffprobeVersion": "ffprobe version m13-contract-fixture",
        }
        output = command["output"]
        return {
            "internalPath": "/discarded/v3/private-path.mp4",
            "storageKey": (
                "renders/m13/"
                f"glyph-reveal-{command['execution_request_digest']}.mp4"
            ),
            "byteSize": 8192,
            "sha256": file_hex,
            "probe": {
                "width": output["width"],
                "height": output["height"],
                "frameCount": output["totalFrames"],
                "frameRate": output["frameRate"],
            },
            "outputDigest": {
                "fileDigest": f"sha256:{file_hex}",
                "fileDigestAlgorithm": "sha256",
                "pixelDigest": "sha256:" + "2" * 64,
                "pixelDigestSpec": VIDEO_PIXEL_DIGEST_SPEC,
                "pixelMode": "RGBA",
                "width": output["width"],
                "height": output["height"],
                "frameCount": output["totalFrames"],
            },
            "composerIdentity": GLYPH_REVEAL_COMPOSER_CAPABILITY,
            "requirementDigest": command["requirement_digest"],
            "executionRequestDigest": command["execution_request_digest"],
            "runtimeIdentity": "sha256:" + _digest(runtime_versions),
            **runtime_versions,
            "publicationAllowed": False,
            "fakeComposerReached": True,
        }


def inspection_port(base: dict, **overrides) -> StaticBasePlateGlyphInspectionPort:
    return StaticBasePlateGlyphInspectionPort(
        inspection_evidence(base, **overrides)
    )


def valid_contract_bundle() -> tuple[
    dict, list[dict], StaticBasePlateGlyphInspectionPort
]:
    base = base_plate_asset()
    masks = mask_assets()
    return base, masks, inspection_port(base)


def build_valid_requirement():
    base, masks, port = valid_contract_bundle()
    requirement = build_glyph_reveal_requirement(
        requirement_command(),
        base_plate_asset=base,
        mask_assets=masks,
        inspection_port=port,
    )
    return requirement, base, masks, port


def build_valid_execution():
    requirement, base, masks, _ = build_valid_requirement()
    port = inspection_port(base)
    execution = build_glyph_reveal_execution_request(
        requirement,
        base,
        masks,
        port,
    )
    return requirement, execution, base, masks, port


def composition_artifact(requirement, execution) -> dict:
    file_hex = "1" * 64
    runtime_versions = {
        "ffmpegVersion": "ffmpeg version m13-contract-fixture",
        "ffprobeVersion": "ffprobe version m13-contract-fixture",
    }
    return sealed(
        {
            "schemaVersion": GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            "storageKey": (
                "renders/m13/"
                f"glyph-reveal-{execution['payloadDigest']}.mp4"
            ),
            "byteSize": 8192,
            "sha256": file_hex,
            "probe": {
                "width": 64,
                "height": 64,
                "frameCount": 49,
                "frameRate": 24,
            },
            "outputDigest": {
                "fileDigest": f"sha256:{file_hex}",
                "fileDigestAlgorithm": "sha256",
                "pixelDigest": "sha256:" + "2" * 64,
                "pixelDigestSpec": VIDEO_PIXEL_DIGEST_SPEC,
                "pixelMode": "RGBA",
                "width": 64,
                "height": 64,
                "frameCount": 49,
            },
            "composerIdentity": GLYPH_REVEAL_COMPOSER_CAPABILITY,
            "adapterIdentity": V4_COMPOSITION_ADAPTER_IDENTITY,
            "requirementDigest": requirement.payload_digest,
            "executionRequestDigest": execution["payloadDigest"],
            "provenance": LOCAL_EVIDENCE_PROVENANCE,
            "gpuUsed": False,
            "publicationAllowed": False,
            "runtimeIdentity": "sha256:" + _digest(runtime_versions),
            **runtime_versions,
        }
    )


class M13GlyphRevealContractTests(unittest.TestCase):
    def test_exact_zhen_fixture_matches_frozen_source_manifest(self):
        manifest = source_manifest()

        self.assertEqual(
            manifest["schemaVersion"],
            "m13.glyph-reveal-technical-fixture.v1",
        )
        self.assertEqual(manifest["glyphSlug"], "zhen")
        self.assertEqual(manifest["revealFrameCount"], 6)
        self.assertEqual(manifest["pixelDigestSpec"], IMAGE_PIXEL_DIGEST_SPEC)
        self.assertEqual(
            manifest["visualSemantics"],
            "no-ink pressure indentation; grazing-light relief only; zero pigment",
        )
        self.assertEqual(
            manifest["status"],
            "TECHNICAL_FIXTURE_ONLY_NOT_ASSET_VERSION_NOT_ADMITTED",
        )
        self.assertEqual(
            manifest["sourceArchive"],
            {
                "fileName": "final-assets-v1.2.zip",
                "bytes": 159_608_548,
                "sha256": (
                    "532765d91b56692e611cabb9fcbd3d8e"
                    "cc916f169f5c4e2b3b9e82a56bbe99c6"
                ),
            },
        )
        self.assertEqual(
            manifest["glyphAssetSpec"]["fileDigest"],
            "sha256:cb77c6c88d39c2593fc360b22fd30e5de1b59c6f2d623905208ce475939584f7",
        )
        asset_spec_path = FIXTURE_ROOT / "asset.json"
        self.assertEqual(
            asset_spec_path.stat().st_size,
            manifest["glyphAssetSpec"]["bytes"],
        )
        self.assertEqual(
            file_digest(asset_spec_path),
            manifest["glyphAssetSpec"]["fileDigest"],
        )
        asset_spec = json.loads(asset_spec_path.read_text(encoding="utf-8"))
        self.assertEqual(asset_spec["character"], "贞")
        self.assertEqual(asset_spec["slug"], "zhen")
        self.assertEqual(asset_spec["font_family"], "Noto Serif SC")
        self.assertEqual(asset_spec["canvas"], [1024, 1024])
        self.assertEqual(asset_spec["reveal_frame_count"], 6)
        self.assertIs(asset_spec["pigment_present"], False)
        self.assertEqual(len(manifest["files"]), 6)

        for record in manifest["files"]:
            path = FIXTURE_ROOT / record["path"]
            with self.subTest(path=record["path"]):
                measured = image_digest_metadata(path)
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(file_digest(path), record["fileDigest"])
                self.assertEqual(measured["pixel_digest"], record["pixelDigest"])
                self.assertEqual(
                    measured["pixel_digest_spec"], IMAGE_PIXEL_DIGEST_SPEC
                )
                self.assertEqual((measured["width"], measured["height"]), (1024, 1024))
                self.assertEqual(measured["pixel_mode"], "RGBA")

    def test_png_pixel_digest_rejects_jpeg_and_survives_lossless_reencode(self):
        source = FIXTURE_ROOT / "cumulative_masks" / "mask_06.png"
        with tempfile.TemporaryDirectory() as directory:
            reencoded = Path(directory) / "mask-06-reencoded.png"
            jpeg = Path(directory) / "mask-06.jpg"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-c:v",
                    "png",
                    "-compression_level",
                    "9",
                    "-pred",
                    "mixed",
                    "-y",
                    str(reencoded),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    str(jpeg),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            source_digest = image_digest_metadata(source)
            reencoded_digest = image_digest_metadata(reencoded)
            source_file_digest = file_digest(source)
            reencoded_file_digest = file_digest(reencoded)
            with self.assertRaises(DigestError):
                image_digest_metadata(jpeg)

        self.assertNotEqual(source_file_digest, reencoded_file_digest)
        self.assertEqual(
            source_digest["pixel_digest"], reencoded_digest["pixel_digest"]
        )
        self.assertEqual(
            source_digest["pixel_digest_spec"],
            reencoded_digest["pixel_digest_spec"],
        )

    def test_base_plate_uses_registered_immutable_m11_schema_without_probe(self):
        base = base_plate_asset()

        self.assertEqual(
            base["schemaVersion"], "v5.k2-real-video-asset-version.v1"
        )
        self.assertEqual(base["state"], "REGISTERED")
        self.assertIs(base["immutable"], True)
        self.assertNotIn("probe", base)
        self.assertEqual(base["creativeShotRef"], SHOT)
        self.assertIn("creativeShotVersionRef", base)
        self.assertIn("assetRef", base)
        self.assertIn("version", base)

    def test_inspection_port_returns_fixed_sealed_local_evidence(self):
        requirement, base, _, port = build_valid_requirement()
        evidence = port.evidence

        self.assertEqual(len(port.calls), 1)
        self.assertEqual(port.calls[0]["basePlateAsset"], base)
        self.assertEqual(
            evidence["inspectorIdentity"], BASE_PLATE_GLYPH_INSPECTOR_IDENTITY
        )
        self.assertEqual(evidence["method"], BASE_PLATE_GLYPH_INSPECTION_METHOD)
        self.assertEqual(evidence["provenance"], LOCAL_EVIDENCE_PROVENANCE)
        self.assertEqual(
            evidence["mediaProbe"],
            {"width": 64, "height": 64, "frameCount": 49, "frameRate": 24},
        )
        self.assertEqual(requirement.inspection_digest, evidence["payloadDigest"])
        self.assertEqual(requirement.target_shot_ref, SHOT)

    def test_missing_unknown_detected_and_stale_inspections_are_rejected(self):
        base = base_plate_asset()
        masks = mask_assets()
        cases = (
            ("missing", None, BasePlateGlyphInspectionRequiredError),
            (
                "unknown",
                inspection_port(base, verdict="UNKNOWN"),
                BasePlateGlyphInspectionRequiredError,
            ),
            (
                "detected",
                inspection_port(base, verdict="READABLE_GLYPH_DETECTED"),
                ReadableGlyphInBasePlateError,
            ),
            (
                "stale",
                inspection_port(base, base_asset_digest="f" * 64),
                StaleInputError,
            ),
        )

        for case, port, error_type in cases:
            with self.subTest(case=case):
                with self.assertRaises(error_type):
                    build_glyph_reveal_requirement(
                        requirement_command(),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_port=port,
                    )

    def test_mask_asset_ref_count_must_equal_reveal_frame_count(self):
        base, masks, port = valid_contract_bundle()
        command = requirement_command(maskAssetRefs=list(MASK_ASSET_REFS[:-1]))

        with self.assertRaises(GlyphRevealMaskCountError):
            build_glyph_reveal_requirement(
                command,
                base_plate_asset=base,
                mask_assets=masks,
                inspection_port=port,
            )

    def test_frame_range_cannot_exceed_inspected_base_plate_frame_count(self):
        base, masks, port = valid_contract_bundle()

        with self.assertRaises(GlyphRevealFrameRangeError):
            build_glyph_reveal_requirement(
                requirement_command(frameRangeEnd=50),
                base_plate_asset=base,
                mask_assets=masks,
                inspection_port=port,
            )

    def test_random_seed_and_expression_params_are_rejected(self):
        base, masks, port = valid_contract_bundle()
        variants = {}
        with_seed = composite_params()
        with_seed["seed"] = 17
        variants["seed"] = with_seed
        with_random = composite_params()
        with_random["random"] = True
        variants["random"] = with_random
        with_expression = composite_params()
        with_expression["position"]["xPixels"] = "rand(0, 16)"
        variants["expression"] = with_expression

        for case, params in variants.items():
            with self.subTest(case=case):
                with self.assertRaises(NondeterministicCompositeParamsError):
                    build_glyph_reveal_requirement(
                        requirement_command(compositeParams=params),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_port=port,
                    )

    def test_masks_require_role_slug_ordinal_and_manifest_digest(self):
        base = base_plate_asset()
        required_fields = (
            "assetRole",
            "glyphSlug",
            "revealOrdinal",
            "glyphManifestDigest",
        )
        for field in required_fields:
            masks = mask_assets()
            masks[0].pop(field)
            masks[0] = resealed(masks[0])
            with self.subTest(case=f"missing-{field}"):
                with self.assertRaises(GlyphRevealError):
                    build_glyph_reveal_requirement(
                        requirement_command(),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_port=inspection_port(base),
                    )

        wrong_values = {
            "assetRole": "GENERIC_IMAGE",
            "glyphSlug": "jia",
            "revealOrdinal": 2,
            "glyphManifestDigest": "sha256:" + "f" * 64,
        }
        for field, value in wrong_values.items():
            masks = mask_assets()
            masks[0][field] = value
            masks[0] = resealed(masks[0])
            with self.subTest(case=f"wrong-{field}"):
                with self.assertRaises(StaleInputError):
                    build_glyph_reveal_requirement(
                        requirement_command(),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_port=inspection_port(base),
                    )

    def test_duplicate_mask_pixel_digests_are_rejected_by_v5_and_v4(self):
        base = base_plate_asset()
        masks = mask_assets()
        masks[1]["pixelDigest"] = masks[0]["pixelDigest"]
        masks[1] = resealed(masks[1])

        with self.subTest(boundary="v5-asset-resolution"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_requirement(
                    requirement_command(),
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_port=inspection_port(base),
                )

        _, execution, _, _, _ = build_valid_execution()
        execution["masks"][1]["pixelDigest"] = execution["masks"][0][
            "pixelDigest"
        ]
        execution["inputBindingsDigest"] = _digest(
            {
                "basePlate": {
                    field: execution["basePlate"][field]
                    for field in (
                        "assetVersionRef",
                        "assetVersionDigest",
                        "fileDigest",
                    )
                },
                "masks": [
                    {
                        field: mask[field]
                        for field in (
                            "assetVersionRef",
                            "assetVersionDigest",
                            "fileDigest",
                            "pixelDigest",
                        )
                    }
                    for mask in execution["masks"]
                ],
            }
        )
        execution = resealed(execution)
        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposer(Path(directory))
            executor = V4CompositionExecutor(composer)
            with self.subTest(boundary="v4-sealed-execution"):
                with self.assertRaises(CompositionRequestValidationError):
                    executor.compose_glyph_reveal(execution)
            self.assertEqual(composer.calls, [])

    def test_masks_require_registered_state_and_real_image_immutability(self):
        base = base_plate_asset()

        for state in (None, "DRAFT"):
            masks = mask_assets()
            if state is None:
                masks[0].pop("state")
            else:
                masks[0]["state"] = state
            masks[0] = resealed(masks[0])
            with self.subTest(schema="v5.asset-version.v1", state=state):
                with self.assertRaises(StaleInputError):
                    build_glyph_reveal_requirement(
                        requirement_command(),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_port=inspection_port(base),
                    )

        real_image_masks = mask_assets()
        real_image_masks[0]["schemaVersion"] = (
            "v5.k2-real-image-asset-version.v1"
        )
        real_image_masks[0] = resealed(real_image_masks[0])
        with self.subTest(schema="v5.k2-real-image-asset-version.v1"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_requirement(
                    requirement_command(),
                    base_plate_asset=base,
                    mask_assets=real_image_masks,
                    inspection_port=inspection_port(base),
                )

        real_image_masks[0]["immutable"] = True
        real_image_masks[0] = resealed(real_image_masks[0])
        requirement = build_glyph_reveal_requirement(
            requirement_command(),
            base_plate_asset=base,
            mask_assets=real_image_masks,
            inspection_port=inspection_port(base),
        )
        self.assertEqual(requirement.mask_asset_refs, MASK_ASSET_REFS)

    def test_requirement_pins_payload_file_and_pixel_input_bindings(self):
        requirement, base, masks, _ = build_valid_requirement()
        bindings = requirement.as_dict()["inputBindings"]

        self.assertEqual(
            bindings["basePlate"],
            {
                "assetVersionRef": base["assetVersionRef"],
                "assetVersionDigest": base["payloadDigest"],
                "fileDigest": f"sha256:{base['sha256']}",
            },
        )
        self.assertEqual(
            bindings["masks"],
            [
                {
                    "assetVersionRef": mask["assetVersionRef"],
                    "assetVersionDigest": mask["payloadDigest"],
                    "fileDigest": f"sha256:{mask['sha256']}",
                    "pixelDigest": mask["pixelDigest"],
                }
                for mask in masks
            ],
        )
        self.assertEqual(requirement.input_bindings_digest, _digest(bindings))

    def test_execution_rejects_same_ref_replaced_base_or_mask_bytes(self):
        requirement, base, masks, _ = build_valid_requirement()

        replaced_base = deepcopy(base)
        replaced_base["sha256"] = "8" * 64
        replaced_base["byteSize"] += 1
        replaced_base = resealed(replaced_base)
        with self.subTest(case="same-base-ref-new-bytes"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_execution_request(
                    requirement,
                    replaced_base,
                    masks,
                    inspection_port(replaced_base),
                )

        replaced_masks = deepcopy(masks)
        replaced_masks[0]["sha256"] = "9" * 64
        replaced_masks[0]["byteSize"] += 1
        replaced_masks[0] = resealed(replaced_masks[0])
        with self.subTest(case="same-mask-ref-new-bytes"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_execution_request(
                    requirement,
                    base,
                    replaced_masks,
                    inspection_port(base),
                )

    def test_execution_request_preserves_exact_inspection_and_asset_bindings(self):
        requirement, execution, base, masks, port = build_valid_execution()

        self.assertEqual(
            execution["schemaVersion"],
            GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION,
        )
        self.assertEqual(execution["requirementDigest"], requirement.payload_digest)
        self.assertEqual(
            execution["inspectionDigest"], port.evidence["payloadDigest"]
        )
        self.assertEqual(
            execution["basePlate"]["fileDigest"], f"sha256:{base['sha256']}"
        )
        self.assertEqual(
            [record["fileDigest"] for record in execution["masks"]],
            [f"sha256:{mask['sha256']}" for mask in masks],
        )
        self.assertEqual(
            [record["pixelDigest"] for record in execution["masks"]],
            [mask["pixelDigest"] for mask in masks],
        )
        self.assertEqual(
            [record["glyphManifestDigest"] for record in execution["masks"]],
            [source_manifest()["glyphAssetSpec"]["fileDigest"]] * 6,
        )
        self.assertFalse(execution["publicationAllowed"])

    def test_requirement_pins_initial_inspection_across_execution_and_result(self):
        requirement, base, masks, initial_port = build_valid_requirement()
        changed_evidence = deepcopy(initial_port.evidence)
        changed_evidence["inspectionRef"] = "inspection-ep01-sh15-replacement"
        changed_port = StaticBasePlateGlyphInspectionPort(
            resealed(changed_evidence)
        )

        with self.subTest(case="execution-reinspection-changed"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_execution_request(
                    requirement,
                    base,
                    masks,
                    changed_port,
                )

        execution = build_glyph_reveal_execution_request(
            requirement,
            base,
            masks,
            StaticBasePlateGlyphInspectionPort(initial_port.evidence),
        )
        forged_execution = deepcopy(execution)
        forged_execution["inspectionDigest"] = "f" * 64
        forged_execution = resealed(forged_execution)
        with self.subTest(case="result-forged-inspection-digest"):
            with self.assertRaises(GlyphRevealArtifactError):
                build_glyph_reveal_composition_result(
                    requirement,
                    forged_execution,
                    composition_artifact(requirement, execution),
                )

    def test_v4_rejects_tampered_sealed_execution_before_composer(self):
        _, execution, _, _, _ = build_valid_execution()
        mutations = {
            "schema": lambda value: value.__setitem__("schemaVersion", "tampered"),
            "params": lambda value: value["compositeParams"]["position"].__setitem__(
                "xPixels", 17
            ),
            "inspection": lambda value: value.__setitem__(
                "inspectionDigest", "f" * 64
            ),
            "glyph": lambda value: value.__setitem__("glyphSlug", "jia"),
            "shot": lambda value: value.__setitem__("targetShotRef", "EP01_SH16"),
            "publication": lambda value: value.__setitem__(
                "publicationAllowed", True
            ),
            "digest": lambda value: value.__setitem__("payloadDigest", "f" * 64),
        }

        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposer(Path(directory))
            executor = V4CompositionExecutor(composer)
            for case, mutate in mutations.items():
                tampered = deepcopy(execution)
                mutate(tampered)
                with self.subTest(case=case):
                    with self.assertRaises(CompositionRequestValidationError):
                        executor.compose_glyph_reveal(tampered)
            self.assertEqual(composer.calls, [])

    def test_v4_valid_execution_reaches_composer_once(self):
        _, execution, _, _, _ = build_valid_execution()

        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposer(Path(directory))
            result = V4CompositionExecutor(composer).compose_glyph_reveal(execution)

        self.assertEqual(len(composer.calls), 1)
        self.assertEqual(
            result["schemaVersion"],
            GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(
            result["payloadDigest"],
            _digest(
                {
                    key: value
                    for key, value in result.items()
                    if key != "payloadDigest"
                }
            ),
        )
        self.assertNotIn("fakeComposerReached", result)
        self.assertNotIn("internalPath", result)
        self.assertEqual(result["adapterIdentity"], V4_COMPOSITION_ADAPTER_IDENTITY)
        self.assertEqual(result["provenance"], LOCAL_EVIDENCE_PROVENANCE)
        self.assertIs(result["publicationAllowed"], False)

    def test_v4_preserves_mask_dimensions_and_rejects_dimension_or_edge_tampering(self):
        _, execution, _, _, _ = build_valid_execution()

        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposer(Path(directory))
            executor = V4CompositionExecutor(composer)
            executor.compose_glyph_reveal(execution)

            self.assertEqual(
                [
                    (mask["width"], mask["height"])
                    for mask in composer.calls[0]["masks"]
                ],
                [
                    (mask["width"], mask["height"])
                    for mask in execution["masks"]
                ],
            )

            dimension_tamper = deepcopy(execution)
            dimension_tamper["masks"][0]["width"] += 1
            dimension_tamper = resealed(dimension_tamper)
            with self.subTest(case="mask-dimensions-disagree"):
                with self.assertRaises(CompositionRequestValidationError):
                    executor.compose_glyph_reveal(dimension_tamper)

            edge_tamper = deepcopy(execution)
            edge_tamper["compositeParams"]["perspective"]["topRight"] = [32, 0]
            edge_tamper = resealed(edge_tamper)
            with self.subTest(case="perspective-equals-width"):
                with self.assertRaises(CompositionRequestValidationError):
                    executor.compose_glyph_reveal(edge_tamper)

            self.assertEqual(len(composer.calls), 1)

    def test_composition_result_binds_requirement_execution_and_artifact(self):
        requirement, execution, _, _, _ = build_valid_execution()
        artifact = composition_artifact(requirement, execution)

        result = build_glyph_reveal_composition_result(
            requirement, execution, artifact
        )

        self.assertEqual(
            result["schemaVersion"],
            GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION,
        )
        self.assertEqual(result["requirementDigest"], requirement.payload_digest)
        self.assertEqual(
            result["executionRequestDigest"], execution["payloadDigest"]
        )
        self.assertEqual(result["inspectionDigest"], requirement.inspection_digest)
        self.assertEqual(
            result["artifactEvidenceDigest"], artifact["payloadDigest"]
        )
        self.assertEqual(result["outputDigest"], artifact["outputDigest"])
        self.assertEqual(result["state"], "COMPOSED_CANDIDATE")
        self.assertFalse(result["publicationAllowed"])
        self.assertNotIn("assetAdmissionRef", result)

    def test_composition_result_rejects_1x1_wrong_fps_and_digest_bindings(self):
        requirement, execution, _, _, _ = build_valid_execution()
        variants = {}

        one_pixel = composition_artifact(requirement, execution)
        one_pixel["probe"].update({"width": 1, "height": 1})
        one_pixel["outputDigest"].update({"width": 1, "height": 1})
        variants["1x1"] = resealed(one_pixel)

        wrong_fps = composition_artifact(requirement, execution)
        wrong_fps["probe"]["frameRate"] = 25
        variants["wrong-fps"] = resealed(wrong_fps)

        wrong_requirement = composition_artifact(requirement, execution)
        wrong_requirement["requirementDigest"] = "f" * 64
        variants["requirement-digest"] = resealed(wrong_requirement)

        wrong_execution = composition_artifact(requirement, execution)
        wrong_execution["executionRequestDigest"] = "e" * 64
        variants["execution-digest"] = resealed(wrong_execution)

        wrong_file = composition_artifact(requirement, execution)
        wrong_file["sha256"] = "d" * 64
        variants["file-digest"] = resealed(wrong_file)

        for case, artifact in variants.items():
            with self.subTest(case=case):
                with self.assertRaises(GlyphRevealArtifactError):
                    build_glyph_reveal_composition_result(
                        requirement, execution, artifact
                    )

    def test_composition_result_rejects_unsealed_or_open_artifact_evidence(self):
        requirement, execution, _, _, _ = build_valid_execution()

        unsealed_mutation = composition_artifact(requirement, execution)
        unsealed_mutation["byteSize"] += 1
        open_evidence = composition_artifact(requirement, execution)
        open_evidence["unexpectedV3Field"] = "must-not-cross-v4"
        open_evidence = resealed(open_evidence)

        for case, artifact in (
            ("unsealed-mutation", unsealed_mutation),
            ("extra-field", open_evidence),
        ):
            with self.subTest(case=case):
                with self.assertRaises(GlyphRevealArtifactError):
                    build_glyph_reveal_composition_result(
                        requirement,
                        execution,
                        artifact,
                    )


if __name__ == "__main__":
    unittest.main()
