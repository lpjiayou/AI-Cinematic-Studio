from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production.deterministic_overlays import (
    FACE_MARK_COMPENSATION,
    NAMEPLATE_TEXT,
    DeterministicOverlayContractError,
    DeterministicOverlayJournalError,
    DeterministicOverlayStaleInputError,
    append_overlay_result_chain,
    build_face_mark_compensation_requirement,
    build_nameplate_text_requirement,
    build_overlay_artifact_evidence,
    build_overlay_execution_request,
    build_overlay_result,
    build_overlay_runtime_evidence,
    resolve_overlay_result_chain,
    validate_overlay_execution_evidence,
)
from services.v5_core_os.episode_production.delivery import K2DeliveryService
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    StaleInputError,
    _digest,
)

RAW = "1" * 64
CONTENT = "sha256:" + RAW


def keyframes(kind: str = "point") -> list[dict]:
    values = {
        "point": {"xPermille": 500, "yPermille": 500},
        "scale": {"xPermille": 200, "yPermille": 200},
        "rotation": {"degreesMilli": 0},
        "opacity": {"valuePermille": 1000},
        "perspective": {"quadPermille": [0, 0, 1000, 0, 0, 1000, 1000, 1000]},
    }[kind]
    return [{"frame": frame, **values, "interpolation": "LINEAR"} for frame in (0, 9)]


def common(mode: str) -> dict:
    return {
        "workspaceRef": "workspace-e3", "productionRunRef": "run-e3",
        "requirementRef": f"requirement-{mode.lower()}", "effectMode": mode,
        "targetShotRef": "shot-17", "targetShotVersionRef": "shot-version-17",
        "targetShotVersionDigest": RAW, "basePlateAssetVersionRef": "base-v1",
        "basePlateAssetVersionDigest": RAW, "frameRangeStartInclusive": 0,
        "frameRangeEndExclusive": 10, "blendMode": "NORMAL", "layer": 6,
    }


def resolved_base() -> dict:
    return {"assetVersionRef": "base-v1", "assetVersionDigest": RAW, "fileDigest": CONTENT, "pixelDigest": CONTENT, "width": 640, "height": 360, "storageKey": "server-only"}


def nameplate_public() -> dict:
    return {
        **common(NAMEPLATE_TEXT), "textSourceKind": "SCRIPT_TEXT",
        "textSourceRef": "script-1", "textSourceVersionRef": "script-v4",
        "textSourceDigest": RAW, "fontAssetVersionRef": "font-v2",
        "fontAssetVersionDigest": RAW,
        "layout": {"writingMode": "HORIZONTAL_LTR", "alignment": "CENTER", "fontSizeMilliPixels": 32000, "letterSpacingMilliPixels": 0, "lineSpacingMilliPixels": 32000, "maxWidthPixels": 640, "maxHeightPixels": 120},
        "positionKeyframes": keyframes(), "scaleKeyframes": keyframes("scale"),
        "rotationKeyframes": keyframes("rotation"), "perspectiveKeyframes": keyframes("perspective"),
        "opacityCurve": keyframes("opacity"), "trackingKeyframes": keyframes(),
    }


def resolved_text(text: str = "长安") -> dict:
    return {"textSourceKind": "SCRIPT_TEXT", "textSourceRef": "script-1", "textSourceVersionRef": "script-v4", "textSourceDigest": RAW, "resolvedText": text, "resolvedTextDigest": _digest({"utf8": text}), "language": "und"}


def resolved_font() -> dict:
    return {"fontAssetVersionRef": "font-v2", "fontAssetVersionDigest": RAW, "fontFileDigest": RAW, "fontTechnicalValidationRef": "font-validation-1", "fontTechnicalValidationDigest": RAW, "fontLicenseBindingVersionRef": "font-license-v1", "fontLicenseBindingVersionDigest": RAW}


def face_public() -> dict:
    return {
        **common(FACE_MARK_COMPENSATION), "characterRef": "character-1",
        "markType": "MOLE", "markAssetVersionRef": "mark-v1",
        "markAssetVersionDigest": RAW, "faceRegion": "LEFT_CHEEK",
        "trackingSourceKind": "EXPLICIT_KEYFRAMES", "trackingKeyframes": keyframes(),
        "scaleKeyframes": keyframes("scale"), "rotationKeyframes": keyframes("rotation"),
        "opacityCurve": keyframes("opacity"), "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
    }


def identity() -> dict:
    return {"schemaVersion": "v5.identity-reference-version-projection.v1", "workspaceRef": "workspace-e3", "productionRunRef": "run-e3", "characterRef": "character-1", "referenceRef": "identity-ref", "referenceVersionRef": "identity-ref-v1", "contentDigest": RAW, "projectionDigest": RAW, "identityLockRef": "identity-lock", "identityLockVersionRef": "identity-lock-v1", "identityLockDigest": RAW, "projectionCheckedAt": "2026-08-31T00:00:00Z"}


def resolved_mark() -> dict:
    return {"assetVersionRef": "mark-v1", "assetVersionDigest": RAW, "fileDigest": CONTENT, "pixelDigest": CONTENT, "storageKey": "private-mark"}


def nameplate_requirement():
    return build_nameplate_text_requirement(nameplate_public(), resolved_base=resolved_base(), resolved_text_source=resolved_text(), resolved_font=resolved_font())


def face_requirement():
    return build_face_mark_compensation_requirement(
        face_public(),
        resolved_base=resolved_base(),
        identity_projection=identity(),
        resolved_mark=resolved_mark(),
    )


def execution_chain(ffmpeg_identity: str = "ffmpeg-pinned", *, requirement=None):
    requirement = requirement or nameplate_requirement()
    request = build_overlay_execution_request(requirement)
    runtime = build_overlay_runtime_evidence(requirement=requirement, execution_request=request, execution_facts={"v3ExecutionRequestDigest": RAW, "rendererIdentity": "v3.deterministic-overlay-ffmpeg", "rendererVersion": "1", "ffmpegIdentity": ffmpeg_identity, "executionManifestDigest": CONTENT})
    probe = {"width": 640, "height": 360, "frameCount": 10, "frameRate": 24, "pixelFormat": "yuv420p", "container": "mp4", "videoCodec": "h264"}
    digest = {"fileDigest": CONTENT, "fileDigestAlgorithm": "sha256", "decodedFramePixelDigest": CONTENT, "decodedFramePixelDigestSpec": "RGBA8/display-identity/frame-major/row-major/width-height-frame-count-bound/v2", "pixelMode": "RGBA", "width": 640, "height": 360, "frameCount": 10, "frameRate": 24}
    artifact = build_overlay_artifact_evidence(requirement=requirement, execution_request=request, runtime_evidence=runtime, execution_facts={"v3ExecutionRequestDigest": RAW, "outputByteSize": 1234, "outputMediaProbe": probe, "outputDigest": digest})
    bindings = {"workspaceRef": requirement.workspace_ref, "productionRunRef": requirement.production_run_ref, "requirementRef": requirement.requirement_ref, "requirementDigest": requirement.payload_digest, "executionRequestRef": request.execution_request_ref, "executionRequestDigest": request.payload_digest, "artifactEvidenceRef": artifact.artifact_evidence_ref, "artifactEvidenceDigest": artifact.payload_digest, "runtimeEvidenceRef": runtime.runtime_evidence_ref, "runtimeEvidenceDigest": runtime.payload_digest}
    result = build_overlay_result(requirement=requirement, execution_request=request, evidence_bindings=bindings, artifact_evidence=artifact)
    return requirement, request, artifact, runtime, result


class OverlayContractTest(unittest.TestCase):
    def test_server_injects_text_font_and_base_facts(self):
        requirement = nameplate_requirement()
        value = requirement.as_dict()
        self.assertEqual(requirement.production_run_ref, "run-e3")
        self.assertEqual(value["resolvedText"], "长安")
        self.assertEqual(value["language"], "und")
        self.assertEqual(value["basePlateFileDigest"], CONTENT)
        self.assertNotIn("width", value)
        self.assertNotIn("height", value)

    def test_public_self_claims_are_rejected(self):
        for field, value in (("resolvedText", "forged"), ("language", "zh"), ("fontFileDigest", RAW)):
            command = nameplate_public(); command[field] = value
            with self.subTest(field=field), self.assertRaises(DeterministicOverlayContractError):
                build_nameplate_text_requirement(command, resolved_base=resolved_base(), resolved_text_source=resolved_text(), resolved_font=resolved_font())
        for field in ("identityVersionRef", "identityVersionDigest", "identityReferenceVersionRef", "identityLockRef", "markFileDigest"):
            command = face_public(); command[field] = "forged"
            with self.subTest(field=field), self.assertRaises(DeterministicOverlayContractError):
                build_face_mark_compensation_requirement(command, resolved_base=resolved_base(), identity_projection=identity(), resolved_mark=resolved_mark())

    def test_face_requirement_uses_current_projection_names_only(self):
        requirement = build_face_mark_compensation_requirement(face_public(), resolved_base=resolved_base(), identity_projection=identity(), resolved_mark=resolved_mark())
        value = requirement.as_dict()
        self.assertEqual(value["identityReferenceVersionRef"], "identity-ref-v1")
        self.assertEqual(value["identityLockDigest"], RAW)
        self.assertNotIn("identityVersionRef", value)

    def test_digest_forms_and_source_kind_fail_closed(self):
        bad_base = resolved_base(); bad_base["fileDigest"] = RAW
        with self.assertRaises(DeterministicOverlayContractError):
            build_nameplate_text_requirement(nameplate_public(), resolved_base=bad_base, resolved_text_source=resolved_text(), resolved_font=resolved_font())
        command = nameplate_public(); command["textSourceKind"] = "PROP_STATE"
        with self.assertRaises(DeterministicOverlayStaleInputError):
            build_nameplate_text_requirement(command, resolved_base=resolved_base(), resolved_text_source=resolved_text(), resolved_font=resolved_font())

    def test_renderer_v1_domain_is_rejected_at_requirement_creation(self):
        mutations = {
            "blend": lambda value: value.update(blendMode="SCREEN"),
            "position": lambda value: value["positionKeyframes"][0].update(xPermille=-1),
            "tracking": lambda value: value["trackingKeyframes"][0].update(xPermille=-1001),
            "font-size": lambda value: value["layout"].update(fontSizeMilliPixels=32500),
            "font-size-upper": lambda value: value["layout"].update(fontSizeMilliPixels=513000),
            "line-size": lambda value: value["layout"].update(lineSpacingMilliPixels=32500),
            "line-size-upper": lambda value: value["layout"].update(lineSpacingMilliPixels=513000),
            "letter-spacing": lambda value: value["layout"].update(letterSpacingMilliPixels=1),
            "perspective": lambda value: value["perspectiveKeyframes"][1]["quadPermille"].__setitem__(0, 1),
            "scale-animation": lambda value: value["scaleKeyframes"][1].update(xPermille=201),
            "rotation-animation": lambda value: value["rotationKeyframes"][1].update(degreesMilli=1),
            "opacity-animation": lambda value: value["opacityCurve"][1].update(valuePermille=999),
        }
        for label, mutate in mutations.items():
            command = nameplate_public(); mutate(command)
            with self.subTest(label=label), self.assertRaises(DeterministicOverlayContractError):
                build_nameplate_text_requirement(command, resolved_base=resolved_base(), resolved_text_source=resolved_text(), resolved_font=resolved_font())
        command = face_public(); command["trackingKeyframes"][0]["xPermille"] = -1
        with self.assertRaises(DeterministicOverlayContractError):
            build_face_mark_compensation_requirement(command, resolved_base=resolved_base(), identity_projection=identity(), resolved_mark=resolved_mark())

    def test_face_semantics_and_tracking_source_are_closed(self):
        mutations = {
            "mark-type": ("markType", "TATTOO"),
            "face-region": ("faceRegion", "LEFT_EAR"),
            "tracking-source": ("trackingSourceKind", "AI_TRACKING"),
        }
        for label, (field, value) in mutations.items():
            command = face_public()
            command[field] = value
            with self.subTest(label=label), self.assertRaises(
                DeterministicOverlayContractError
            ):
                build_face_mark_compensation_requirement(
                    command,
                    resolved_base=resolved_base(),
                    identity_projection=identity(),
                    resolved_mark=resolved_mark(),
                )

    def test_face_tracking_keyframes_are_required_unique_closed_and_in_range(self):
        cases = {}

        missing = face_public()
        missing.pop("trackingKeyframes")
        cases["field-missing"] = missing

        empty = face_public()
        empty["trackingKeyframes"] = []
        cases["empty"] = empty

        missing_start = face_public()
        missing_start["trackingKeyframes"][0]["frame"] = 1
        cases["start-frame-missing"] = missing_start

        missing_end = face_public()
        missing_end["trackingKeyframes"][-1]["frame"] = 8
        cases["end-frame-missing"] = missing_end

        duplicate = face_public()
        duplicate["trackingKeyframes"][-1]["frame"] = 0
        cases["duplicate-frame"] = duplicate

        out_of_range = face_public()
        out_of_range["trackingKeyframes"][-1]["frame"] = 10
        cases["out-of-range"] = out_of_range

        for label, command in cases.items():
            with self.subTest(label=label), self.assertRaises(
                DeterministicOverlayContractError
            ):
                build_face_mark_compensation_requirement(
                    command,
                    resolved_base=resolved_base(),
                    identity_projection=identity(),
                    resolved_mark=resolved_mark(),
                )

    def test_character_must_be_bound_to_the_exact_target_shot(self):
        context = {
            "executableShotGraph": {
                "shots": [
                    {
                        "creativeShotRef": "shot-17",
                        "creativeShotVersionRef": "shot-version-17",
                        "payloadDigest": RAW,
                        "requiredCharacterIdentityLocks": [
                            {"characterRef": "character-other"}
                        ],
                    }
                ]
            }
        }
        with self.assertRaisesRegex(
            StaleInputError,
            "character is not bound to the target ShotVersion",
        ):
            K2DeliveryService._require_character_in_target_shot(
                context=context,
                target_shot_ref="shot-17",
                target_shot_version_ref="shot-version-17",
                target_shot_version_digest=RAW,
                character_ref="character-1",
            )

    def test_missing_or_foreign_workspace_mark_authority_is_rejected(self):
        with self.assertRaises(DeterministicOverlayContractError):
            build_face_mark_compensation_requirement(
                face_public(),
                resolved_base=resolved_base(),
                identity_projection=identity(),
                resolved_mark={},
            )

        class MarkAuthority:
            def __init__(self, asset_versions):
                self.asset_versions = asset_versions

            def get_revision_bundle(
                self, workspace, run_ref, *, evidence_snapshot=None
            ):
                return {"assetVersions": deepcopy(self.asset_versions)}

        foreign = {
            "schemaVersion": "v5.k2-real-image-asset-version.v1",
            "workspaceRef": "workspace-foreign",
            "productionRunRef": "run-e3",
            "assetVersionRef": "mark-v1",
            "payloadDigest": RAW,
        }
        context = {
            "run": {
                "workspaceRef": "workspace-e3",
                "productionRunRef": "run-e3",
            },
            "snapshot": object(),
        }
        for label, assets in (("missing", []), ("foreign-workspace", [foreign])):
            service = K2DeliveryService(
                object(),
                object(),
                None,
                object(),
                ref_factory=lambda prefix: prefix,
                clock=lambda: "2026-08-31T00:00:00Z",
                real_video_authority=MarkAuthority(assets),
            )
            with self.subTest(label=label), self.assertRaises(StaleInputError):
                service._current_mark_asset(
                    context=context,
                    asset_version_ref="mark-v1",
                    asset_version_digest=RAW,
                    target_shot_ref="shot-17",
                    target_shot_version_ref="shot-version-17",
                    target_shot_version_digest=RAW,
                )

    def test_text_byte_limit_and_current_base_dimensions_are_closed(self):
        with self.assertRaises(DeterministicOverlayContractError):
            build_nameplate_text_requirement(nameplate_public(), resolved_base=resolved_base(), resolved_text_source=resolved_text("长" * 5462), resolved_font=resolved_font())
        for field, value in (("maxWidthPixels", 641), ("maxHeightPixels", 361)):
            command = nameplate_public(); command["layout"][field] = value
            with self.subTest(field=field), self.assertRaises(DeterministicOverlayContractError):
                build_nameplate_text_requirement(command, resolved_base=resolved_base(), resolved_text_source=resolved_text(), resolved_font=resolved_font())

    def test_atomic_five_record_append_replay_and_sqlite_restart(self):
        chain = execution_chain()
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        stored, replayed = append_overlay_result_chain(repository, requirement=chain[0], execution_request=chain[1], artifact_evidence=chain[2], runtime_evidence=chain[3], result=chain[4], idempotency_key="overlay-chain", created_at="2026-08-31T00:00:00Z")
        self.assertFalse(replayed); self.assertEqual(len(repository.list_records("workspace-e3", "run-e3")), 5)
        replay, replayed = append_overlay_result_chain(repository, requirement=chain[0], execution_request=chain[1], artifact_evidence=chain[2], runtime_evidence=chain[3], result=chain[4], idempotency_key="overlay-chain", created_at="2026-08-31T00:00:00Z")
        self.assertTrue(replayed); self.assertEqual(replay.as_dict(), stored.as_dict())
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evidence.sqlite"
            sqlite = SqliteEpisodeProductionEvidenceAdapter(database, initialize_if_missing=True)
            saved, _ = append_overlay_result_chain(sqlite, requirement=chain[0], execution_request=chain[1], artifact_evidence=chain[2], runtime_evidence=chain[3], result=chain[4], idempotency_key="overlay-sqlite", created_at="2026-08-31T00:00:00Z")
            restarted = SqliteEpisodeProductionEvidenceAdapter(database, initialize_if_missing=False)
            resolved = resolve_overlay_result_chain(restarted, workspace_ref="workspace-e3", production_run_ref="run-e3", result_ref=chain[4].result_ref, result_digest=chain[4].payload_digest)
            self.assertEqual(resolved.as_dict(), saved.as_dict())

    def test_changed_replay_and_tamper_are_rejected(self):
        chain = execution_chain(); repository = InMemoryEpisodeProductionEvidenceAdapter()
        append_overlay_result_chain(repository, requirement=chain[0], execution_request=chain[1], artifact_evidence=chain[2], runtime_evidence=chain[3], result=chain[4], idempotency_key="overlay-conflict", created_at="2026-08-31T00:00:00Z")
        changed = execution_chain("ffmpeg-other")
        with self.assertRaises(IdempotencyConflictError):
            append_overlay_result_chain(repository, requirement=changed[0], execution_request=changed[1], artifact_evidence=changed[2], runtime_evidence=changed[3], result=changed[4], idempotency_key="overlay-conflict", created_at="2026-08-31T00:00:00Z")
        with self.assertRaises(DeterministicOverlayJournalError):
            resolve_overlay_result_chain(repository, workspace_ref="workspace-e3", production_run_ref="run-e3", result_ref=chain[4].result_ref, result_digest="f" * 64)

    def test_cross_chain_runtime_and_artifact_evidence_swaps_are_rejected(self):
        nameplate = execution_chain()
        face = execution_chain(requirement=face_requirement())
        swaps = (
            (face[2], nameplate[3]),
            (nameplate[2], face[3]),
            (face[2], face[3]),
        )
        for artifact, runtime in swaps:
            with self.subTest(
                artifact=artifact.artifact_evidence_ref,
                runtime=runtime.runtime_evidence_ref,
            ), self.assertRaises(DeterministicOverlayStaleInputError):
                validate_overlay_execution_evidence(
                    requirement=nameplate[0],
                    execution_request=nameplate[1],
                    artifact_evidence=artifact,
                    runtime_evidence=runtime,
                )


if __name__ == "__main__": unittest.main()
