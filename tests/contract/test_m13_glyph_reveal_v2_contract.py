from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from services.v4_platform.composition import (
    CompositionExecutionError,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production.foundation import (
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal import (
    BasePlateGlyphInspectionRequiredError,
    GlyphRevealArtifactError,
    GlyphRevealError,
    GlyphRevealMaskCountError,
    NondeterministicCompositeParamsError,
    ReadableGlyphInBasePlateError,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    BASE_PLATE_GLYPH_INSPECTION_METHOD_V2,
    BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION_V2,
    BASE_PLATE_GLYPH_INSPECTOR_IDENTITY_V2,
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2,
    GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2,
    GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2,
    GLYPH_REVEAL_RENDERER_IDENTITY_V2,
    GLYPH_REVEAL_RENDERER_VERSION_V2,
    GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2,
    DigestPinnedBasePlateGlyphInspectionAdapter,
    DigestPinnedFileBasePlateGlyphInspectionEvidenceStore,
    GlyphRevealCompositionResultV2,
    GlyphRevealRequirementV2,
    GlyphRevealScheduleError,
    build_glyph_reveal_composition_result_v2,
    build_glyph_reveal_execution_request_v2,
    build_glyph_reveal_requirement_v2,
    expected_glyph_reveal_output_storage_key_v2,
    read_glyph_reveal_composition_result,
    read_glyph_reveal_requirement,
)
from tests.contract.test_m13_glyph_reveal_contract import (
    BASE_ASSET_REF,
    MASK_ASSET_REFS,
    REQUIREMENT,
    RUN,
    SHOT,
    WORKSPACE,
    base_plate_asset,
    composite_params,
    mask_assets,
)


HISTORY_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "m13" / "glyph_reveal_v1_history.json"
)
HISTORY_FIXTURE_SHA256 = (
    "9185cbb687d805284324d423811f261641c3307bb70692d7d88edcd445a38ce7"
)
INSPECTION_REF = "inspection-ep01-sh15-no-readable-glyph-v2"
INSPECTION_EVIDENCE_REF = "evidence-ep01-sh15-no-readable-glyph-v2"
INSPECTION_SUPPORT_BYTES = (
    b"K2 M13 digest-pinned full-frame no-readable-glyph evidence v2\n"
)
INSPECTION_RECORD_STORAGE_KEY = "inspection-records/ep01-sh15.json"
INSPECTION_SUPPORT_STORAGE_KEY = "inspection-support/ep01-sh15.bin"


def sealed(payload: dict) -> dict:
    result = deepcopy(payload)
    result["payloadDigest"] = _digest(result)
    return result


def resealed(payload: dict) -> dict:
    result = deepcopy(payload)
    result.pop("payloadDigest", None)
    return sealed(result)


def reveal_schedule() -> list[dict]:
    intervals = (
        (12, 13),
        (13, 15),
        (15, 18),
        (18, 22),
        (22, 26),
        (26, 30),
    )
    return [
        {
            "revealOrdinal": ordinal,
            "maskAssetVersionRef": MASK_ASSET_REFS[ordinal - 1],
            "startFrameInclusive": start,
            "endFrameExclusive": end,
        }
        for ordinal, (start, end) in enumerate(intervals, start=1)
    ]


def requirement_command_v2(**overrides) -> dict:
    result = {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "requirementRef": REQUIREMENT,
        "glyphSlug": "zhen",
        "targetShotRef": SHOT,
        "frameRangeStartInclusive": 12,
        "frameRangeEndExclusive": 30,
        "revealSchedule": reveal_schedule(),
        "basePlateAssetVersionRef": BASE_ASSET_REF,
        "basePlateInspectionRef": INSPECTION_REF,
        "compositeParams": composite_params(),
    }
    result.update(overrides)
    return result


def inspection_evidence_v2(
    base: dict,
    *,
    verdict: str = "NO_READABLE_GLYPH",
    target_shot_ref: str = SHOT,
    evidence_bytes: bytes = INSPECTION_SUPPORT_BYTES,
    media_probe: dict | None = None,
) -> dict:
    return sealed(
        {
            "schemaVersion": BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION_V2,
            "inspectionRef": INSPECTION_REF,
            "inspectorIdentity": BASE_PLATE_GLYPH_INSPECTOR_IDENTITY_V2,
            "inspectionMethod": BASE_PLATE_GLYPH_INSPECTION_METHOD_V2,
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "targetShotRef": target_shot_ref,
            "basePlateAssetVersionRef": base["assetVersionRef"],
            "basePlateAssetVersionDigest": base["payloadDigest"],
            "basePlateFileDigest": f"sha256:{base['sha256']}",
            "verdict": verdict,
            "evidenceRef": INSPECTION_EVIDENCE_REF,
            "evidenceDigest": "sha256:" + sha256(evidence_bytes).hexdigest(),
            "createdAt": "2026-08-30T00:00:00Z",
            "mediaProbe": media_probe
            or {
                "width": 64,
                "height": 64,
                "frameCount": 49,
                "frameRate": 24,
            },
            "provenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )


class InMemoryInspectionEvidenceStore:
    """A test-only server-held store; no evidence is accepted from the command."""

    def __init__(
        self,
        inspection: dict | None,
        evidence_bytes: bytes | None = INSPECTION_SUPPORT_BYTES,
    ) -> None:
        self.inspection = deepcopy(inspection)
        self.evidence_bytes = evidence_bytes
        self.inspection_reads: list[dict] = []
        self.evidence_reads: list[str] = []

    def read_inspection(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        inspection_ref: str,
    ) -> dict | None:
        self.inspection_reads.append(
            {
                "workspaceRef": workspace_ref,
                "productionRunRef": production_run_ref,
                "inspectionRef": inspection_ref,
            }
        )
        if self.inspection is None:
            return None
        return deepcopy(self.inspection)

    def read_evidence_bytes(self, *, evidence_ref: str) -> bytes | None:
        self.evidence_reads.append(evidence_ref)
        if evidence_ref != INSPECTION_EVIDENCE_REF:
            return None
        return self.evidence_bytes


@dataclass(frozen=True, slots=True)
class StagedFileInspectionEvidence:
    record_path: Path
    support_path: Path
    record_bytes: bytes
    support_bytes: bytes
    inspection_index: dict
    evidence_index: dict


def _prefixed_sha256(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def stage_file_inspection_evidence(
    root: Path,
    base: dict,
) -> StagedFileInspectionEvidence:
    root.mkdir(parents=True, exist_ok=True)
    record = inspection_evidence_v2(base)
    record_bytes = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    record_path = root / INSPECTION_RECORD_STORAGE_KEY
    support_path = root / INSPECTION_SUPPORT_STORAGE_KEY
    record_path.parent.mkdir(parents=True, exist_ok=True)
    support_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(record_bytes)
    support_path.write_bytes(INSPECTION_SUPPORT_BYTES)
    return StagedFileInspectionEvidence(
        record_path=record_path,
        support_path=support_path,
        record_bytes=record_bytes,
        support_bytes=INSPECTION_SUPPORT_BYTES,
        inspection_index={
            (WORKSPACE, RUN, INSPECTION_REF): {
                "storageKey": INSPECTION_RECORD_STORAGE_KEY,
                "fileDigest": _prefixed_sha256(record_bytes),
            }
        },
        evidence_index={
            INSPECTION_EVIDENCE_REF: {
                "storageKey": INSPECTION_SUPPORT_STORAGE_KEY,
                "fileDigest": _prefixed_sha256(INSPECTION_SUPPORT_BYTES),
            }
        },
    )


def file_inspection_adapter(
    root: Path,
    staged: StagedFileInspectionEvidence,
    *,
    inspection_index: dict | None = None,
    evidence_index: dict | None = None,
) -> DigestPinnedBasePlateGlyphInspectionAdapter:
    store = DigestPinnedFileBasePlateGlyphInspectionEvidenceStore(
        root,
        inspection_index=(
            staged.inspection_index
            if inspection_index is None
            else inspection_index
        ),
        evidence_index=(
            staged.evidence_index if evidence_index is None else evidence_index
        ),
    )
    return DigestPinnedBasePlateGlyphInspectionAdapter(store)


def valid_contract_bundle(
    *,
    verdict: str = "NO_READABLE_GLYPH",
    target_shot_ref: str = SHOT,
    media_probe: dict | None = None,
) -> tuple[
    dict,
    list[dict],
    InMemoryInspectionEvidenceStore,
    DigestPinnedBasePlateGlyphInspectionAdapter,
]:
    base = base_plate_asset()
    masks = mask_assets()
    store = InMemoryInspectionEvidenceStore(
        inspection_evidence_v2(
            base,
            verdict=verdict,
            target_shot_ref=target_shot_ref,
            media_probe=media_probe,
        )
    )
    return base, masks, store, DigestPinnedBasePlateGlyphInspectionAdapter(store)


def build_valid_requirement_v2() -> tuple:
    base, masks, store, adapter = valid_contract_bundle()
    requirement = build_glyph_reveal_requirement_v2(
        requirement_command_v2(),
        base_plate_asset=base,
        mask_assets=masks,
        inspection_adapter=adapter,
    )
    return requirement, base, masks, store, adapter


def build_valid_execution_v2() -> tuple:
    requirement, base, masks, store, adapter = build_valid_requirement_v2()
    execution = build_glyph_reveal_execution_request_v2(
        requirement,
        base,
        masks,
        adapter,
    )
    return requirement, execution, base, masks, store, adapter


def runtime_evidence_digest(
    *, renderer_identity: str, renderer_version: str, ffmpeg_identity: str
) -> str:
    return "sha256:" + sha256(
        json.dumps(
            {
                "ffmpegIdentity": ffmpeg_identity,
                "rendererIdentity": renderer_identity,
                "rendererVersion": renderer_version,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class FakeGlyphComposerV2:
    def __init__(self, artifact_root: Path, *, wrong_scope: bool = False) -> None:
        self.artifact_root = artifact_root
        self.wrong_scope = wrong_scope
        self.calls: list[dict] = []

    def compose_glyph_reveal_v2(self, **command) -> dict:
        self.calls.append(deepcopy(command))
        file_digest = "sha256:" + "1" * 64
        ffmpeg_identity = "ffmpeg version m13-v2-contract-fixture"
        output = command["output"]
        expected_key = expected_glyph_reveal_output_storage_key_v2(
            command["workspace_ref"],
            command["run_ref"],
            command["execution_request_digest"],
        )
        storage_key = (
            f"wrong-scope/{Path(expected_key).name}"
            if self.wrong_scope
            else expected_key
        )
        return {
            "internalPath": "/discarded/v3/private-path.mp4",
            "outputStorageKey": storage_key,
            "outputByteSize": 8192,
            "outputMediaProbe": {
                "width": output["width"],
                "height": output["height"],
                "frameCount": output["totalFrames"],
                "frameRate": output["frameRate"],
            },
            "outputDigest": {
                "fileDigest": file_digest,
                "fileDigestAlgorithm": "sha256",
                "decodedFramePixelDigest": "sha256:" + "2" * 64,
                "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "pixelMode": "RGBA",
                "width": output["width"],
                "height": output["height"],
                "frameCount": output["totalFrames"],
                "frameRate": output["frameRate"],
            },
            "rendererIdentity": GLYPH_REVEAL_RENDERER_IDENTITY_V2,
            "rendererVersion": GLYPH_REVEAL_RENDERER_VERSION_V2,
            "ffmpegIdentity": ffmpeg_identity,
            "runtimeEvidenceDigest": runtime_evidence_digest(
                renderer_identity=GLYPH_REVEAL_RENDERER_IDENTITY_V2,
                renderer_version=GLYPH_REVEAL_RENDERER_VERSION_V2,
                ffmpeg_identity=ffmpeg_identity,
            ),
            "requirementRef": command["requirement_ref"],
            "requirementDigest": command["requirement_digest"],
            "executionRequestRef": command["execution_request_ref"],
            "executionRequestDigest": command["execution_request_digest"],
            "publicationAllowed": False,
        }


class M13GlyphRevealV2ContractTests(unittest.TestCase):
    def test_v1_history_is_readable_but_cannot_execute_as_v2(self):
        self.assertEqual(
            sha256(HISTORY_FIXTURE.read_bytes()).hexdigest(),
            HISTORY_FIXTURE_SHA256,
        )
        history = json.loads(HISTORY_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            history["sourceCommit"],
            "e9e79fc303f61193cf57c7c363565ed87ebd8210",
        )

        requirement_v1 = read_glyph_reveal_requirement(history["requirement"])
        result_v1 = read_glyph_reveal_composition_result(
            history["compositionResult"]
        )
        self.assertEqual(requirement_v1.as_dict(), history["requirement"])
        self.assertEqual(result_v1, history["compositionResult"])
        self.assertIs(history["requirement"]["outputDigest"], None)

        base, masks, _, adapter = valid_contract_bundle()
        with self.assertRaises(GlyphRevealError):
            build_glyph_reveal_execution_request_v2(
                requirement_v1,
                base,
                masks,
                adapter,
            )

    def test_new_requirement_and_execution_writes_are_exact_v2(self):
        requirement, execution, _, _, store, _ = build_valid_execution_v2()
        requirement_mapping = requirement.as_dict()

        self.assertIsInstance(requirement, GlyphRevealRequirementV2)
        self.assertIsInstance(
            read_glyph_reveal_requirement(requirement_mapping),
            GlyphRevealRequirementV2,
        )
        self.assertEqual(
            requirement_mapping["schemaVersion"],
            GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2,
        )
        self.assertEqual(
            execution["schemaVersion"],
            GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2,
        )
        self.assertEqual(
            set(requirement_mapping),
            {
                "schemaVersion",
                "workspaceRef",
                "productionRunRef",
                "requirementRef",
                "glyphSlug",
                "targetShotRef",
                "frameRangeStartInclusive",
                "frameRangeEndExclusive",
                "revealSchedule",
                "basePlateAssetVersionRef",
                "basePlateAssetVersionDigest",
                "basePlateFileDigest",
                "maskAssetVersionBindings",
                "basePlateInspectionRef",
                "basePlateInspectionDigest",
                "compositeParams",
                "inputBindingsDigest",
                "publicationAllowed",
                "payloadDigest",
            },
        )
        self.assertEqual(
            set(execution),
            {
                "schemaVersion",
                "executionRequestRef",
                "workspaceRef",
                "productionRunRef",
                "requirementRef",
                "requirementDigest",
                "glyphSlug",
                "targetShotRef",
                "frameRangeStartInclusive",
                "frameRangeEndExclusive",
                "revealSchedule",
                "inputBindingsDigest",
                "basePlate",
                "masks",
                "basePlateInspectionRef",
                "basePlateInspectionDigest",
                "compositeParams",
                "output",
                "publicationAllowed",
                "payloadDigest",
            },
        )
        self.assertNotIn("outputDigest", requirement_mapping)
        self.assertNotIn("resultRef", requirement_mapping)
        self.assertNotIn("outputAssetVersionRef", requirement_mapping)
        self.assertEqual(requirement.reveal_frame_count, len(reveal_schedule()))
        self.assertEqual(requirement.reveal_schedule, reveal_schedule())
        self.assertEqual(execution["revealSchedule"], reveal_schedule())
        self.assertEqual(len(store.inspection_reads), 2)
        self.assertEqual(len(store.evidence_reads), 2)

    def test_requirement_rejects_every_output_fact_even_when_null(self):
        requirement, *_ = build_valid_requirement_v2()
        forbidden = {
            "outputDigest": None,
            "outputAssetVersionRef": "asset-version-output",
            "resultRef": "glyph-result",
            "renderedArtifactRef": "glyph-artifact",
            "fileDigest": "sha256:" + "1" * 64,
            "pixelDigest": "sha256:" + "2" * 64,
            "previewCandidateRef": "preview-candidate",
            "timelineVersionRef": "timeline-version",
        }
        for field, value in forbidden.items():
            mapping = requirement.as_dict()
            mapping[field] = value
            mapping = resealed(mapping)
            with self.subTest(field=field):
                with self.assertRaises(GlyphRevealError):
                    GlyphRevealRequirementV2.from_mapping(mapping)

    def test_reveal_schedule_is_required_and_count_must_match_masks(self):
        base, masks, _, adapter = valid_contract_bundle()

        missing = requirement_command_v2()
        missing.pop("revealSchedule")
        with self.subTest(case="missing"):
            with self.assertRaises(GlyphRevealError):
                build_glyph_reveal_requirement_v2(
                    missing,
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_adapter=adapter,
                )

        fewer = reveal_schedule()[:-1]
        fewer[-1]["endFrameExclusive"] = 30
        for case, schedule in (
            ("fewer-schedule-entries", fewer),
            (
                "more-schedule-entries",
                reveal_schedule()
                + [
                    {
                        "revealOrdinal": 7,
                        "maskAssetVersionRef": "asset-version-mask-07",
                        "startFrameInclusive": 30,
                        "endFrameExclusive": 31,
                    }
                ],
            ),
        ):
            command = requirement_command_v2(revealSchedule=schedule)
            if case == "more-schedule-entries":
                command["frameRangeEndExclusive"] = 31
            with self.subTest(case=case):
                with self.assertRaises(GlyphRevealMaskCountError):
                    build_glyph_reveal_requirement_v2(
                        command,
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )

    def test_schedule_rejects_overlap_gap_and_out_of_bounds(self):
        base, masks, _, adapter = valid_contract_bundle()
        variants: dict[str, list[dict]] = {}

        overlap = reveal_schedule()
        overlap[1]["startFrameInclusive"] = 12
        variants["overlap"] = overlap
        gap = reveal_schedule()
        gap[1]["startFrameInclusive"] = 14
        variants["gap"] = gap
        before = reveal_schedule()
        before[0]["startFrameInclusive"] = 11
        variants["before-range"] = before
        after = reveal_schedule()
        after[-1]["endFrameExclusive"] = 31
        variants["after-range"] = after
        empty = reveal_schedule()
        empty[2]["endFrameExclusive"] = empty[2]["startFrameInclusive"]
        variants["empty"] = empty

        for case, schedule in variants.items():
            with self.subTest(case=case):
                with self.assertRaises(GlyphRevealScheduleError):
                    build_glyph_reveal_requirement_v2(
                        requirement_command_v2(revealSchedule=schedule),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )

    def test_schedule_rejects_noncontinuous_ordinal_wrong_mask_and_float_time(self):
        base, masks, _, adapter = valid_contract_bundle()
        variants: dict[str, list[dict]] = {}

        ordinal = reveal_schedule()
        ordinal[2]["revealOrdinal"] = 4
        variants["ordinal"] = ordinal
        wrong_mask = reveal_schedule()
        wrong_mask[1]["maskAssetVersionRef"] = MASK_ASSET_REFS[2]
        variants["wrong-mask-ref"] = wrong_mask
        floating = reveal_schedule()
        floating[1]["startFrameInclusive"] = 13.0
        variants["floating-time"] = floating
        expression = reveal_schedule()
        expression[1]["endFrameExclusive"] = "15+rand(0,1)"
        variants["expression-time"] = expression

        for case, schedule in variants.items():
            with self.subTest(case=case):
                with self.assertRaises(GlyphRevealError):
                    build_glyph_reveal_requirement_v2(
                        requirement_command_v2(revealSchedule=schedule),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )

    def test_server_held_inspection_is_required_and_client_claims_are_rejected(self):
        base = base_plate_asset()
        masks = mask_assets()
        missing_store = InMemoryInspectionEvidenceStore(None)
        missing_adapter = DigestPinnedBasePlateGlyphInspectionAdapter(missing_store)
        with self.subTest(case="missing-server-evidence"):
            with self.assertRaises(BasePlateGlyphInspectionRequiredError):
                build_glyph_reveal_requirement_v2(
                    requirement_command_v2(),
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_adapter=missing_adapter,
                )

        _, _, store, adapter = valid_contract_bundle()
        client_claims = {
            "glyphVisible": False,
            "verdict": "NO_READABLE_GLYPH",
            "inspectionEvidence": store.inspection,
        }
        for field, value in client_claims.items():
            command = requirement_command_v2()
            command[field] = value
            with self.subTest(case=f"client-{field}"):
                with self.assertRaises(GlyphRevealError):
                    build_glyph_reveal_requirement_v2(
                        command,
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )
        self.assertEqual(store.inspection_reads, [])
        self.assertEqual(store.evidence_reads, [])

    def test_concrete_file_store_builds_requirement_and_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            base = base_plate_asset()
            masks = mask_assets()
            staged = stage_file_inspection_evidence(root, base)
            adapter = file_inspection_adapter(root, staged)

            requirement = build_glyph_reveal_requirement_v2(
                requirement_command_v2(),
                base_plate_asset=base,
                mask_assets=masks,
                inspection_adapter=adapter,
            )
            execution = build_glyph_reveal_execution_request_v2(
                requirement,
                base,
                masks,
                adapter,
            )

        self.assertEqual(
            requirement.base_plate_inspection_ref,
            INSPECTION_REF,
        )
        self.assertEqual(
            execution["basePlateInspectionRef"],
            INSPECTION_REF,
        )
        self.assertEqual(
            execution["basePlateInspectionDigest"],
            requirement.base_plate_inspection_digest,
        )

    def test_concrete_file_store_rejects_deleted_or_modified_files(self):
        cases = (
            (
                "record-deleted",
                "record",
                "delete",
                BasePlateGlyphInspectionRequiredError,
            ),
            (
                "support-deleted",
                "support",
                "delete",
                BasePlateGlyphInspectionRequiredError,
            ),
            ("record-one-byte-modified", "record", "modify", StaleInputError),
            ("support-one-byte-modified", "support", "modify", StaleInputError),
        )
        for case, target, operation, error_type in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                base = base_plate_asset()
                masks = mask_assets()
                staged = stage_file_inspection_evidence(root, base)
                adapter = file_inspection_adapter(root, staged)
                requirement = build_glyph_reveal_requirement_v2(
                    requirement_command_v2(),
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_adapter=adapter,
                )
                path = (
                    staged.record_path
                    if target == "record"
                    else staged.support_path
                )
                if operation == "delete":
                    path.unlink()
                elif target == "record":
                    modified = staged.record_bytes.replace(
                        b"2026-08-30T00:00:00Z",
                        b"2026-08-31T00:00:00Z",
                        1,
                    )
                    self.assertEqual(len(modified), len(staged.record_bytes))
                    self.assertNotEqual(modified, staged.record_bytes)
                    path.write_bytes(modified)
                else:
                    modified = bytes((staged.support_bytes[0] ^ 1,)) + (
                        staged.support_bytes[1:]
                    )
                    self.assertEqual(len(modified), len(staged.support_bytes))
                    self.assertNotEqual(modified, staged.support_bytes)
                    path.write_bytes(modified)

                with self.assertRaises(error_type):
                    build_glyph_reveal_execution_request_v2(
                        requirement,
                        base,
                        masks,
                        adapter,
                    )

    def test_concrete_file_store_rejects_server_index_digest_mismatch(self):
        for target in ("record", "support"):
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                base = base_plate_asset()
                masks = mask_assets()
                staged = stage_file_inspection_evidence(root, base)
                requirement = build_glyph_reveal_requirement_v2(
                    requirement_command_v2(),
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_adapter=file_inspection_adapter(root, staged),
                )
                inspection_index = deepcopy(staged.inspection_index)
                evidence_index = deepcopy(staged.evidence_index)
                if target == "record":
                    inspection_index[(WORKSPACE, RUN, INSPECTION_REF)][
                        "fileDigest"
                    ] = "sha256:" + "0" * 64
                else:
                    evidence_index[INSPECTION_EVIDENCE_REF][
                        "fileDigest"
                    ] = "sha256:" + "0" * 64
                adapter = file_inspection_adapter(
                    root,
                    staged,
                    inspection_index=inspection_index,
                    evidence_index=evidence_index,
                )

                with self.assertRaises(StaleInputError):
                    build_glyph_reveal_execution_request_v2(
                        requirement,
                        base,
                        masks,
                        adapter,
                    )

    def test_concrete_file_store_rejects_parent_and_leaf_symlinks(self):
        for case in ("record-parent", "support-leaf"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                temporary_root = Path(directory).resolve()
                root = temporary_root / "evidence-root"
                base = base_plate_asset()
                masks = mask_assets()
                staged = stage_file_inspection_evidence(root, base)
                adapter = file_inspection_adapter(root, staged)
                requirement = build_glyph_reveal_requirement_v2(
                    requirement_command_v2(),
                    base_plate_asset=base,
                    mask_assets=masks,
                    inspection_adapter=adapter,
                )
                outside = temporary_root / "outside"
                outside.mkdir()
                if case == "record-parent":
                    outside_record = outside / staged.record_path.name
                    staged.record_path.replace(outside_record)
                    staged.record_path.parent.rmdir()
                    staged.record_path.parent.symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                else:
                    outside_support = outside / staged.support_path.name
                    staged.support_path.replace(outside_support)
                    staged.support_path.symlink_to(outside_support)

                with self.assertRaises(BasePlateGlyphInspectionRequiredError):
                    build_glyph_reveal_execution_request_v2(
                        requirement,
                        base,
                        masks,
                        adapter,
                    )

    def test_inspection_replacement_and_support_digest_drift_fail_closed(self):
        requirement, base, masks, store, adapter = build_valid_requirement_v2()
        original = deepcopy(store.inspection)

        replacement = deepcopy(original)
        replacement["createdAt"] = "2026-08-30T00:00:01Z"
        store.inspection = resealed(replacement)
        with self.subTest(case="same-ref-resealed-replacement"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_execution_request_v2(
                    requirement,
                    base,
                    masks,
                    adapter,
                )

        store.inspection = original
        store.evidence_bytes = INSPECTION_SUPPORT_BYTES + b"tamper"
        with self.subTest(case="support-bytes-drift"):
            with self.assertRaises(StaleInputError):
                build_glyph_reveal_execution_request_v2(
                    requirement,
                    base,
                    masks,
                    adapter,
                )

    def test_inspection_target_readable_and_indeterminate_fail_closed(self):
        variants = (
            ("target-shot", "NO_READABLE_GLYPH", "EP01_SH16", StaleInputError),
            (
                "readable",
                "READABLE_GLYPH_PRESENT",
                SHOT,
                ReadableGlyphInBasePlateError,
            ),
            (
                "indeterminate",
                "INDETERMINATE",
                SHOT,
                BasePlateGlyphInspectionRequiredError,
            ),
        )
        for case, verdict, target, error_type in variants:
            base, masks, _, adapter = valid_contract_bundle(
                verdict=verdict,
                target_shot_ref=target,
            )
            with self.subTest(case=case):
                with self.assertRaises(error_type):
                    build_glyph_reveal_requirement_v2(
                        requirement_command_v2(),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )

    def test_composite_params_reject_random_items_and_expressions(self):
        base, masks, _, adapter = valid_contract_bundle()
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
                    build_glyph_reveal_requirement_v2(
                        requirement_command_v2(compositeParams=params),
                        base_plate_asset=base,
                        mask_assets=masks,
                        inspection_adapter=adapter,
                    )

    def test_v4_and_v5_emit_closed_scoped_v2_artifact_and_result(self):
        requirement, execution, *_ = build_valid_execution_v2()
        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposerV2(Path(directory))
            artifact = V4CompositionExecutor(composer).compose_glyph_reveal_v2(
                execution
            )

        result = build_glyph_reveal_composition_result_v2(
            requirement,
            execution,
            artifact,
        )
        result_mapping = result.as_dict()
        expected_key = expected_glyph_reveal_output_storage_key_v2(
            WORKSPACE,
            RUN,
            execution["payloadDigest"],
        )
        expected_workspace_scope = sha256(WORKSPACE.encode("utf-8")).hexdigest()[
            :20
        ]
        expected_run_scope = sha256(RUN.encode("utf-8")).hexdigest()[:20]
        self.assertEqual(
            expected_key,
            (
                f"{expected_workspace_scope}/{expected_run_scope}/"
                "glyph-reveal/"
                f"glyph-reveal-{execution['payloadDigest']}.mp4"
            ),
        )

        self.assertEqual(len(composer.calls), 1)
        self.assertEqual(
            artifact["schemaVersion"],
            GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2,
        )
        self.assertEqual(
            result_mapping["schemaVersion"],
            GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION_V2,
        )
        self.assertEqual(
            set(artifact),
            {
                "schemaVersion",
                "artifactEvidenceRef",
                "outputStorageKey",
                "outputByteSize",
                "outputMediaProbe",
                "outputDigest",
                "rendererIdentity",
                "rendererVersion",
                "ffmpegIdentity",
                "runtimeEvidenceDigest",
                "provenance",
                "gpuUsed",
                "publicationAllowed",
                "requirementRef",
                "requirementDigest",
                "executionRequestRef",
                "executionRequestDigest",
                "payloadDigest",
            },
        )
        self.assertEqual(
            set(result_mapping),
            {
                "schemaVersion",
                "workspaceRef",
                "productionRunRef",
                "resultRef",
                "requirementRef",
                "requirementDigest",
                "executionRequestRef",
                "executionRequestDigest",
                "artifactEvidenceRef",
                "artifactEvidenceDigest",
                "outputStorageKey",
                "outputByteSize",
                "outputMediaProbe",
                "outputDigest",
                "rendererIdentity",
                "rendererVersion",
                "ffmpegIdentity",
                "runtimeEvidenceDigest",
                "state",
                "publicationAllowed",
                "payloadDigest",
            },
        )
        self.assertEqual(
            set(artifact["outputDigest"]),
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
        self.assertIsInstance(result, GlyphRevealCompositionResultV2)
        self.assertIsInstance(
            read_glyph_reveal_composition_result(result_mapping),
            GlyphRevealCompositionResultV2,
        )
        self.assertEqual(artifact["outputStorageKey"], expected_key)
        self.assertEqual(result_mapping["outputStorageKey"], expected_key)
        self.assertEqual(result_mapping["outputDigest"], artifact["outputDigest"])
        self.assertEqual(
            result_mapping["artifactEvidenceDigest"], artifact["payloadDigest"]
        )
        self.assertEqual(result_mapping["state"], "COMPOSED_CANDIDATE")
        self.assertFalse(result_mapping["publicationAllowed"])
        self.assertNotIn("internalPath", artifact)
        self.assertNotIn("assetAdmissionRef", result_mapping)
        self.assertNotIn("timelineVersionRef", result_mapping)

    def test_v4_rejects_resealed_execution_identity_and_ordinal_types(self):
        _, execution, *_ = build_valid_execution_v2()
        variants = {}
        wrong_ref = deepcopy(execution)
        wrong_ref["executionRequestRef"] = "m13-glyph-reveal-execution-wrong"
        variants["derived-execution-ref"] = wrong_ref
        boolean_ordinal = deepcopy(execution)
        boolean_ordinal["revealSchedule"][0]["revealOrdinal"] = True
        variants["boolean-ordinal"] = boolean_ordinal
        floating_ordinal = deepcopy(execution)
        floating_ordinal["revealSchedule"][0]["revealOrdinal"] = 1.0
        variants["floating-ordinal"] = floating_ordinal

        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposerV2(Path(directory))
            executor = V4CompositionExecutor(composer)
            for case, variant in variants.items():
                with self.subTest(case=case):
                    with self.assertRaises(CompositionExecutionError):
                        executor.compose_glyph_reveal_v2(resealed(variant))
        self.assertEqual(composer.calls, [])

    def test_result_without_output_digest_is_rejected(self):
        requirement, execution, *_ = build_valid_execution_v2()
        with tempfile.TemporaryDirectory() as directory:
            artifact = V4CompositionExecutor(
                FakeGlyphComposerV2(Path(directory))
            ).compose_glyph_reveal_v2(execution)
        result = build_glyph_reveal_composition_result_v2(
            requirement,
            execution,
            artifact,
        ).as_dict()
        result.pop("outputDigest")
        result = resealed(result)

        with self.assertRaises(GlyphRevealArtifactError):
            GlyphRevealCompositionResultV2.from_mapping(result)

    def test_correct_basename_in_wrong_scope_is_rejected_by_v4_and_v5(self):
        requirement, execution, *_ = build_valid_execution_v2()
        with tempfile.TemporaryDirectory() as directory:
            composer = FakeGlyphComposerV2(Path(directory), wrong_scope=True)
            with self.subTest(boundary="v4"):
                with self.assertRaises(CompositionExecutionError):
                    V4CompositionExecutor(composer).compose_glyph_reveal_v2(
                        execution
                    )

            valid_artifact = V4CompositionExecutor(
                FakeGlyphComposerV2(Path(directory))
            ).compose_glyph_reveal_v2(execution)
        wrong = deepcopy(valid_artifact)
        wrong["outputStorageKey"] = (
            "wrong-scope/" + Path(wrong["outputStorageKey"]).name
        )
        wrong = resealed(wrong)
        with self.subTest(boundary="v5"):
            with self.assertRaises(GlyphRevealArtifactError):
                build_glyph_reveal_composition_result_v2(
                    requirement,
                    execution,
                    wrong,
                )


if __name__ == "__main__":
    unittest.main()
