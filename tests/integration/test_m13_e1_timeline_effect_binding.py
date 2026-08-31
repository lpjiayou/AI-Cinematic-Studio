from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    MediaJobCoordinator,
    SqliteMediaJobAdapter,
)
from services.v5_core_os.episode_production.deterministic_effects import (
    append_deterministic_effect_result_chain,
    build_masked_surface_execution_request,
    build_scratch_light_requirement,
)
from services.v5_core_os.episode_production.evidence import (
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicError,
    create_local_development_boundary,
)
from services.v5_core_os.episode_production.timeline_editing import (
    DETERMINISTIC_EFFECT_KINDS,
    TIMELINE_CLIP_SCHEMA_VERSION_V3,
    TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
    TimelineEditingAuthorityError,
    TimelineEditingContractError,
    TimelineEditingConflictError,
    TimelineEditingStaleInputError,
    apply_timeline_edit,
    assert_timeline_edit_replay,
    build_timeline_edit_command,
    validate_timeline,
    validate_timeline_clip,
    validate_timeline_edit_chain,
    validate_timeline_edit_command,
    validate_timeline_track,
    validate_timeline_version,
)
from tests.contract.test_m13_timeline_editing_contract import (
    DIGEST_A,
    DIGEST_B,
    WORKSPACE,
    clip_command,
    source_resolver as t1_source_resolver,
    timeline_edit_command,
    valid_snapshot,
)
from tests.contract.test_m13_deterministic_effects_contract import (
    _command as deterministic_effect_command,
    _evidence as deterministic_effect_evidence,
)
from tests.unit.test_episode_production_k2 import (
    Refs,
    activate_k2_m6_baseline,
    g2_command,
    g3_command,
    g4_command,
    g5_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


_V1_GOLDEN_DIGESTS = {
    "INSERT_CLIP": (
        "f893289e41f1a50a2c1b2c7f8f16ffb90d9f60c1b559620297cbd5e5b5d8752a",
        "0a7ee2aed66fdfc5d47cddd28ab84997e7cd9f21c81a8c3290de503e4d1e6cb3",
    ),
    "REMOVE_CLIP": (
        "4ea71c3a7448dd35825afa00081817781fb889eff86fdff3fb818c68d7cf3049",
        "f4a7e5fba830b292096f8cc3c438c77082a8c839a30bf8451bb61c78de3539ce",
    ),
    "MOVE_CLIP": (
        "e07bbcf02bfcb2b0ca78fcca8c139efa5977fe4bf3049db4cdf504a2731aa4b0",
        "06df52b063d827e7bec61fa26518a35b54ec0eeaabfe81ed1db798a7b86fe453",
    ),
    "TRIM_CLIP": (
        "474e8126a9058477d0d1563baa07534e5ab0624b767eeb6afeba71fa64f68e6f",
        "c9102da5f72a687698c257ec817c078c2be71eede7eb8b09a9529bba34c7cd86",
    ),
    "SPLIT_CLIP": (
        "00bfe46d8e8148aacadd045cae661c93724beaee02243a20d96e655042032241",
        "878aa024c7c1b58d6981981585a39ce384c17902620e0e6a9e18ad432a2bd198",
    ),
    "ENABLE_CLIP": (
        "0460d061ac265c0642c7bf9fe48e6718ed0a8d9adfb140054f5805a1bf2b6c92",
        "2a0d35c3520d7fb4da2e3d39c7e27437ac1f17ac4b7a7ed45179809a400799a7",
    ),
    "DISABLE_CLIP": (
        "2569ee396ac2d7e2164a518e3a8127b949f9b289153b808c6420bafcffdd9658",
        "e33ba6bb60880cf8e8097e69b134c98125492c2c8f1eb56166bea2684970bc8e",
    ),
    "REORDER_TRACK": (
        "0396ef247ace7cd76f07d692e00679e0f041b4b300a0cb12680a797c02f09705",
        "3a7d3609ae12619942b29e1374fe1df4bed7a125031795f82b09c422d40b6ea1",
    ),
    "SET_TRANSITION": (
        "9ee9ec3b1b82fd80e8dfc03db27bc5ec7e6c08de47097b40656cb670ecc1f0e9",
        "ce50e4bf7b5508f04d5dac80daffe07b10ffd0cd6c0526ce60608ec3ad9d0eef",
    ),
    "SET_SPEED": (
        "962d7aef1a4d6d1714ce4ca0a476554ae21f743abca48386b9576378cfd8b9b5",
        "7dd7167ce9c2913134610d09b32f9d758ea5ebea0d6b3d477067f8080b4a1f0c",
    ),
    "SET_TRANSFORM": (
        "c1e84e395e7bfa956ccfade91693965f8630697229e46c446a7ad5b240449d67",
        "5fe97efccbcd02b992895ea8bf682d4b69f0c028eebeea1d69a5ab134fab15a6",
    ),
    "SET_MASKS": (
        "402cc61fb0689f60aa884c6e01f8573867c18670d7f2562c81d7004bc4cd55b8",
        "88dfcefdd541ba914a49af4c9a19b44ce229456248c126ba5237343c22314643",
    ),
    "SET_SAFE_AREA": (
        "0d166755fec6c876ce3311f7b5f2a9ab8277492c722d44d11a3708a4fda139ba",
        "6cc920f6a573e660868b4041ce10113445f94218b0a403865412d60796518c49",
    ),
    "SET_OUTPUT_PROFILES": (
        "d70ed0dca31e781911b869d29447f73e3cb1e3405abf78f41ebe270e5e874fa7",
        "fa30569e661506da7c9b39920734ed1892cd8700cb1b3b87fa9ab318d8e4137e",
    ),
}


def _sealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _effect_authorities(
    *,
    effect_mode: str = "SCRATCH_REVEAL",
    workspace_ref: str = WORKSPACE,
) -> tuple[dict, dict]:
    requirement = _sealed(
        {
            "schemaVersion": "v5.m13-scratch-light-requirement.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": "episode-production-run-m13-t1",
            "requirementRef": "masked-surface-requirement-e1",
            "effectMode": effect_mode,
            "targetShotRef": "creative-shot-e1",
            "targetShotVersionRef": "creative-shot-e1-v1",
            "targetShotVersionDigest": DIGEST_B,
            "basePlateAssetVersionRef": "asset-version-effect-base-v1",
            "basePlateAssetVersionDigest": DIGEST_A,
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": 24,
            "blendMode": "SCREEN",
            "layer": 2,
            "publicationAllowed": False,
        }
    )
    result = _sealed(
        {
            "schemaVersion": "v5.m13-scratch-light-result.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": requirement["productionRunRef"],
            "resultRef": "masked-surface-result-e1",
            "effectMode": effect_mode,
            "requirementRef": requirement["requirementRef"],
            "requirementDigest": requirement["payloadDigest"],
            "state": "SUCCEEDED",
            "publicationAllowed": False,
        }
    )
    return requirement, result


def _e2_effect_authorities(effect_mode: str) -> tuple[dict, dict]:
    requirement, result = _effect_authorities(effect_mode=effect_mode)
    requirement["schemaVersion"] = (
        "v5.m13-flame-extinguish-requirement.v1"
        if effect_mode == "FLAME_EXTINGUISH"
        else "v5.m13-smoke-requirement.v1"
    )
    requirement = _sealed(requirement)
    result.update(
        {
            "schemaVersion": (
                "v5.m13-flame-extinguish-result.v1"
                if effect_mode == "FLAME_EXTINGUISH"
                else "v5.m13-smoke-result.v1"
            ),
            "requirementDigest": requirement["payloadDigest"],
            "state": "COMPOSED_CANDIDATE",
            "assetAdmissionState": "NOT_ADMITTED",
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
        }
    )
    return requirement, _sealed(result)


def _source_resolver(requirement: dict, result: dict):
    def resolve(source_type: str, source_ref: str) -> dict:
        if (
            source_type == "EFFECT_REQUIREMENT"
            and source_ref == requirement["requirementRef"]
        ):
            return deepcopy(requirement)
        if source_type == "EFFECT_RESULT" and source_ref == result["resultRef"]:
            return {
                **deepcopy(result),
                "targetShotRef": requirement["targetShotRef"],
                "frameRangeStartInclusive": requirement[
                    "frameRangeStartInclusive"
                ],
                "frameRangeEndExclusive": requirement[
                    "frameRangeEndExclusive"
                ],
            }
        authority = t1_source_resolver(source_type, source_ref)
        if (
            source_type == "ASSET_VERSION"
            and source_ref == requirement["basePlateAssetVersionRef"]
        ):
            authority.update(
                {
                    "creativeShotRef": "creative-shot-e1",
                    "creativeShotVersionRef": "creative-shot-e1-v1",
                    "creativeShotDigest": DIGEST_B,
                }
            )
        return authority

    return resolve


def _unbound_effect_clip(requirement: dict) -> dict:
    clip = clip_command("EFFECT", clip_ref="clip-masked-surface-e1")
    clip.pop("timelineVersionRef")
    clip.update(
        {
            "layer": requirement["layer"],
            "zOrder": 2,
            "blendMode": requirement["blendMode"],
            "sourceBinding": {
                "effectRequirementRef": requirement["requirementRef"],
                "effectRequirementDigest": requirement["payloadDigest"],
                "effectKind": requirement["effectMode"],
                "effectResultRef": None,
                "effectResultDigest": None,
                "layer": requirement["layer"],
                "blendMode": requirement["blendMode"],
            },
        }
    )
    return clip


def _apply_insert_and_bind(
    *, requirement: dict | None = None, result: dict | None = None
):
    requirement, result = (
        _effect_authorities()
        if requirement is None or result is None
        else (requirement, result)
    )
    resolver = _source_resolver(requirement, result)
    fixture = valid_snapshot()
    root = validate_timeline(fixture["timeline"])
    initial = validate_timeline_version(fixture["timelineVersion"])
    tracks = [validate_timeline_track(item) for item in fixture["tracks"]]
    clips = [validate_timeline_clip(item) for item in fixture["clips"]]
    insert_command = validate_timeline_edit_command(
        build_timeline_edit_command(
            {
                "operationRef": "insert-masked-surface-effect",
                "idempotencyKey": "insert-masked-surface-effect-key",
                "parentTimelineVersionRef": initial.as_dict()[
                    "timelineVersionRef"
                ],
                "parentTimelineVersionDigest": initial.as_dict()[
                    "payloadDigest"
                ],
                "newTimelineVersionRef": "timeline-version-e1-unbound-v2",
                "operation": "INSERT_CLIP",
                "arguments": {"clip": _unbound_effect_clip(requirement)},
                "createdAt": "2026-08-30T09:00:00Z",
            }
        )
    )
    inserted = apply_timeline_edit(
        initial,
        tracks,
        clips,
        insert_command,
        existing_timeline_versions=[initial],
        timeline=root,
        source_resolver=resolver,
    )
    bind_command = validate_timeline_edit_command(
        build_timeline_edit_command(
            {
                "operationRef": "bind-masked-surface-result",
                "idempotencyKey": "bind-masked-surface-result-key",
                "parentTimelineVersionRef": inserted.timeline_version.as_dict()[
                    "timelineVersionRef"
                ],
                "parentTimelineVersionDigest": inserted.timeline_version.as_dict()[
                    "payloadDigest"
                ],
                "newTimelineVersionRef": "timeline-version-e1-bound-v3",
                "operation": "BIND_EFFECT_RESULT",
                "arguments": {
                    "clipRef": "clip-masked-surface-e1",
                    "effectResultRef": result["resultRef"],
                    "effectResultDigest": result["payloadDigest"],
                },
                "createdAt": "2026-08-30T09:01:00Z",
            }
        )
    )
    bound = apply_timeline_edit(
        inserted.timeline_version,
        inserted.tracks,
        inserted.clips,
        bind_command,
        existing_timeline_versions=[initial, inserted.timeline_version],
        timeline=root,
        source_resolver=resolver,
    )
    return initial, inserted, bound, insert_command, bind_command, resolver


class M13E1TimelineEffectBindingTests(unittest.TestCase):
    def test_all_t1_v1_command_and_successor_digests_are_unchanged(self):
        from tests.contract.test_m13_timeline_editing_contract import apply_edit

        for operation, (command_digest, successor_digest) in (
            _V1_GOLDEN_DIGESTS.items()
        ):
            with self.subTest(operation=operation):
                command = timeline_edit_command(valid_snapshot(), operation)
                successor = apply_edit(valid_snapshot(), operation)
                self.assertEqual(
                    command["schemaVersion"], "v5.timeline-edit-command.v1"
                )
                self.assertEqual(command["payloadDigest"], command_digest)
                self.assertEqual(
                    successor.timeline_version.as_dict()["payloadDigest"],
                    successor_digest,
                )

    def test_bind_is_the_only_v2_operation_and_upgrades_only_target_clip(self):
        initial, inserted, bound, _, bind_command, _ = _apply_insert_and_bind()
        self.assertEqual(set(DETERMINISTIC_EFFECT_KINDS), {
            "SCRATCH_REVEAL",
            "LIGHT_SWEEP",
            "LOCAL_EXPOSURE",
            "FLAME_EXTINGUISH",
            "SMOKE",
            "NAMEPLATE_TEXT",
            "FACE_MARK_COMPENSATION",
            "DISTANCE_STATE_TRANSITION",
        })
        self.assertEqual(
            bind_command.as_dict()["schemaVersion"],
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        )
        before = {
            item.as_dict()["clipRef"]: item.as_dict() for item in inserted.clips
        }
        after = {
            item.as_dict()["clipRef"]: item.as_dict() for item in bound.clips
        }
        target = after["clip-masked-surface-e1"]
        self.assertEqual(target["schemaVersion"], TIMELINE_CLIP_SCHEMA_VERSION_V3)
        self.assertEqual(
            target["sourceBinding"]["effectResultRef"],
            "masked-surface-result-e1",
        )
        self.assertIsNone(
            before["clip-masked-surface-e1"]["sourceBinding"][
                "effectResultRef"
            ]
        )
        for clip_ref in set(before) - {"clip-masked-surface-e1"}:
            self.assertEqual(
                {
                    key: value
                    for key, value in before[clip_ref].items()
                    if key not in {"timelineVersionRef", "payloadDigest"}
                },
                {
                    key: value
                    for key, value in after[clip_ref].items()
                    if key not in {"timelineVersionRef", "payloadDigest"}
                },
            )
        self.assertNotEqual(
            initial.as_dict()["payloadDigest"],
            bound.timeline_version.as_dict()["payloadDigest"],
        )

        raw = bind_command.as_dict()
        raw.pop("payloadDigest")
        raw["operation"] = "REMOVE_CLIP"
        raw["arguments"] = {"clipRef": "clip-masked-surface-e1"}
        raw["payloadDigest"] = _digest(raw)
        with self.assertRaises(TimelineEditingContractError):
            validate_timeline_edit_command(raw)

    def test_binding_rejects_result_requirement_scope_shot_and_frame_drift(self):
        mutations = {
            "result-requirement": lambda requirement, result: result.update(
                {"requirementDigest": "f" * 64}
            ),
            "foreign-workspace": lambda requirement, result: result.update(
                {"workspaceRef": "workspace-foreign"}
            ),
            "shot": lambda requirement, result: requirement.update(
                {"targetShotRef": "creative-shot-foreign"}
            ),
            "frame": lambda requirement, result: requirement.update(
                {"frameRangeEndExclusive": 23}
            ),
        }
        for name, mutate in mutations.items():
            requirement, result = _effect_authorities()
            mutate(requirement, result)
            requirement = _sealed(requirement)
            if name != "result-requirement":
                result["requirementDigest"] = requirement["payloadDigest"]
            result = _sealed(result)
            with self.subTest(mutation=name), self.assertRaises(
                (TimelineEditingStaleInputError, TimelineEditingAuthorityError)
            ):
                _apply_insert_and_bind(requirement=requirement, result=result)

    def test_e2_kinds_reuse_bind_with_composed_candidate_state(self):
        for effect_mode in ("FLAME_EXTINGUISH", "SMOKE"):
            requirement, result = _e2_effect_authorities(effect_mode)
            with self.subTest(effectMode=effect_mode):
                initial, inserted, bound, _, _, _ = _apply_insert_and_bind(
                    requirement=requirement,
                    result=result,
                )
                bound_source = next(
                    item.as_dict()["sourceBinding"]
                    for item in bound.clips
                    if item.as_dict()["clipRef"]
                    == "clip-masked-surface-e1"
                )
                self.assertEqual(
                    bound_source["effectResultDigest"],
                    result["payloadDigest"],
                )
                self.assertIsNone(
                    next(
                        item.as_dict()["sourceBinding"]
                        for item in inserted.clips
                        if item.as_dict()["clipRef"]
                        == "clip-masked-surface-e1"
                    )["effectResultRef"]
                )
                self.assertNotEqual(
                    initial.as_dict()["payloadDigest"],
                    bound.timeline_version.as_dict()["payloadDigest"],
                )

                invalid = deepcopy(result)
                invalid["state"] = "SUCCEEDED"
                invalid = _sealed(invalid)
                with self.assertRaises(TimelineEditingStaleInputError):
                    _apply_insert_and_bind(
                        requirement=requirement,
                        result=invalid,
                    )

    def test_parent_is_immutable_and_mixed_v1_v2_chain_replays(self):
        initial, inserted, bound, insert, bind, _ = _apply_insert_and_bind()
        initial_before = initial.as_dict()
        inserted_before = inserted.as_dict()
        validate_timeline_edit_chain(
            [initial, inserted.timeline_version, bound.timeline_version],
            [insert, bind],
        )
        assert_timeline_edit_replay(bind.as_dict()["payloadDigest"], bind)
        changed = bind.as_dict()
        changed.pop("payloadDigest")
        changed["arguments"]["effectResultDigest"] = "f" * 64
        changed["payloadDigest"] = _digest(changed)
        with self.assertRaises(TimelineEditingConflictError):
            assert_timeline_edit_replay(
                bind.as_dict()["payloadDigest"], changed
            )
        self.assertEqual(initial.as_dict(), initial_before)
        self.assertEqual(inserted.as_dict(), inserted_before)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E1TimelineEffectBindingSqliteTests(unittest.TestCase):
    def test_public_insert_bind_restart_replay_and_parent_immutability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode.sqlite3"
            evidence_database = root / "evidence.sqlite3"
            jobs_database = root / "jobs.sqlite3"
            artifact_root = root / "artifacts"
            refs = Refs()
            (
                assembly,
                _,
                project,
                series,
                episode,
                _,
            ) = seed_k2_roots(with_m6_authority=True)
            activate_k2_m6_baseline(assembly, project, series)

            def media_execution(*, initialize: bool):
                return MediaJobCoordinator(
                    SqliteMediaJobAdapter(
                        jobs_database,
                        initialize_if_missing=initialize,
                    ),
                    DeterministicLocalFfmpegAdapter(),
                    artifact_root,
                    ref_factory=refs,
                    clock=lambda: "2026-08-30T10:00:00Z",
                )

            boundary_arguments = {
                "project_boundary": assembly.project_context,
                "series_episode_boundary": assembly.series_episode,
                "series_planning_boundary": assembly.series_planning,
                "script_studio_boundary": assembly.script_studio,
                "evidence_database_path": evidence_database,
                "identity_reference_authority": k2_identity_authority(),
                "media_execution": media_execution(initialize=True),
                "ref_factory": refs,
                "clock": lambda: "2026-08-30T10:00:00Z",
            }
            boundary = create_local_development_boundary(
                database, **boundary_arguments
            )
            run = boundary.create_run(
                run_command(
                    project,
                    series,
                    episode,
                    idempotencyKey="m13-e1-timeline-run",
                )
            )
            boundary.authorize_and_lock(
                g2_command(run, idempotencyKey="m13-e1-timeline-g2")
            )
            boundary.compile_shot_graph(
                g3_command(run, idempotencyKey="m13-e1-timeline-g3")
            )
            boundary.resolve_assets(
                g4_command(run, idempotencyKey="m13-e1-timeline-g4")
            )
            media = boundary.execute_media(
                g5_command(run, idempotencyKey="m13-e1-timeline-g5")
            )
            base = next(
                item
                for item in media["assetVersions"]
                if item["mediaKind"] == "video"
            )
            workspace = run["workspaceRef"]
            run_ref = run["productionRunRef"]

            with sqlite3.connect(evidence_database) as connection:
                tables_before = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }

            requirement_command = deterministic_effect_command()
            requirement_command.update(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "requirementRef": "m13-e1-timeline-requirement",
                    "targetShotRef": base["creativeShotRef"],
                    "targetShotVersionRef": base[
                        "creativeShotVersionRef"
                    ],
                    "targetShotVersionDigest": base[
                        "creativeShotDigest"
                    ],
                    "basePlateAssetVersionRef": base["assetVersionRef"],
                    "basePlateAssetVersionDigest": base["payloadDigest"],
                    "basePlateFileDigest": f"sha256:{base['sha256']}",
                    "frameRangeStartInclusive": 0,
                    "frameRangeEndExclusive": 24,
                    "explicitSchedule": [
                        {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 24,
                            "enabled": True,
                            "interpolation": "STEP",
                        }
                    ],
                    "trajectoryKeyframes": [
                        {
                            "frame": 0,
                            "xPermille": 250,
                            "yPermille": 300,
                            "interpolation": "LINEAR",
                        },
                        {
                            "frame": 23,
                            "xPermille": 750,
                            "yPermille": 300,
                            "interpolation": "EASE_IN_OUT",
                        },
                    ],
                    "intensityCurve": [
                        {
                            "frame": 0,
                            "valuePermille": 0,
                            "interpolation": "LINEAR",
                        },
                        {
                            "frame": 23,
                            "valuePermille": 900,
                            "interpolation": "EASE_OUT",
                        },
                    ],
                    "exposureCurve": [
                        {
                            "frame": 0,
                            "valueMilliStops": 0,
                            "interpolation": "LINEAR",
                        },
                        {
                            "frame": 23,
                            "valueMilliStops": 500,
                            "interpolation": "EASE_OUT",
                        },
                    ],
                }
            )
            requirement = build_scratch_light_requirement(
                requirement_command
            )
            execution_request = build_masked_surface_execution_request(
                requirement
            )
            execution_evidence = deterministic_effect_evidence(
                requirement, execution_request
            )
            repository = SqliteEpisodeProductionEvidenceAdapter(
                evidence_database,
                initialize_if_missing=False,
            )
            chain, replayed = append_deterministic_effect_result_chain(
                repository,
                requirement=requirement,
                execution_request=execution_request,
                artifact_evidence=execution_evidence["artifact"],
                runtime_evidence=execution_evidence["runtime"],
                result=execution_evidence["result"],
                idempotency_key="m13-e1-timeline-result-chain",
                created_at="2026-08-30T10:00:00Z",
                expected_record_journal_head=repository.record_journal_head(
                    workspace, run_ref
                ),
            )
            self.assertFalse(replayed)

            created = boundary.create_timeline(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "operationRef": "m13-e1-create-timeline",
                    "idempotencyKey": "m13-e1-create-timeline-key",
                    "expectedRunVersion": run["version"],
                }
            )
            tracks = {
                item["trackKind"]: item["trackRef"]
                for item in created["tracks"]
            }

            def edit_command(
                parent: dict,
                *,
                operation_ref: str,
                idempotency_key: str,
                operation: str,
                arguments: dict,
            ) -> dict:
                return {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "operationRef": operation_ref,
                    "idempotencyKey": idempotency_key,
                    "expectedRunVersion": run["version"],
                    "parentTimelineVersionRef": parent[
                        "timelineVersionRef"
                    ],
                    "parentTimelineVersionDigest": parent[
                        "payloadDigest"
                    ],
                    "editCommand": {
                        "operation": operation,
                        "arguments": arguments,
                    },
                }

            video_clip = clip_command(
                "VIDEO", clip_ref="clip-m13-e1-base-video"
            )
            video_clip.pop("timelineVersionRef")
            video_clip["trackRef"] = tracks["VIDEO"]
            video_clip["sourceBinding"] = {
                "assetVersionRef": base["assetVersionRef"],
                "assetVersionDigest": base["payloadDigest"],
                "sourceInFrameInclusive": 0,
                "sourceOutFrameExclusive": 24,
            }
            video_insert = boundary.edit_timeline(
                edit_command(
                    created["timelineVersion"],
                    operation_ref="m13-e1-insert-base-video",
                    idempotency_key="m13-e1-insert-base-video-key",
                    operation="INSERT_CLIP",
                    arguments={"clip": video_clip},
                )
            )

            effect_clip = _unbound_effect_clip(requirement.as_dict())
            effect_clip["trackRef"] = tracks["EFFECT"]
            effect_insert_command = edit_command(
                video_insert["timelineVersion"],
                operation_ref="m13-e1-insert-effect",
                idempotency_key="m13-e1-insert-effect-key",
                operation="INSERT_CLIP",
                arguments={"clip": effect_clip},
            )
            effect_insert = boundary.edit_timeline(effect_insert_command)
            unbound_parent = deepcopy(effect_insert)

            result = chain.result.as_dict()
            bind_command = edit_command(
                effect_insert["timelineVersion"],
                operation_ref="m13-e1-bind-effect-result",
                idempotency_key="m13-e1-bind-effect-result-key",
                operation="BIND_EFFECT_RESULT",
                arguments={
                    "clipRef": effect_clip["clipRef"],
                    "effectResultRef": result["resultRef"],
                    "effectResultDigest": result["payloadDigest"],
                },
            )
            bound = boundary.edit_timeline(bind_command)
            bound_clip = next(
                item
                for item in bound["clips"]
                if item["clipRef"] == effect_clip["clipRef"]
            )
            self.assertEqual(
                bound["editOperation"]["schemaVersion"],
                TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
            )
            self.assertEqual(
                bound_clip["sourceBinding"]["effectResultDigest"],
                result["payloadDigest"],
            )
            self.assertEqual(effect_insert, unbound_parent)
            self.assertIsNone(
                next(
                    item
                    for item in effect_insert["clips"]
                    if item["clipRef"] == effect_clip["clipRef"]
                )["sourceBinding"]["effectResultRef"]
            )

            restarted_arguments = {
                **boundary_arguments,
                "media_execution": media_execution(initialize=False),
                "initialize_if_missing": False,
            }
            restarted = create_local_development_boundary(
                database, **restarted_arguments
            )
            restored = restarted.get_timeline(workspace, run_ref)
            self.assertEqual(
                restored["timelineVersion"]["payloadDigest"],
                bound["timelineVersion"]["payloadDigest"],
            )
            restored_clip = next(
                item
                for item in restored["clips"]
                if item["clipRef"] == effect_clip["clipRef"]
            )
            self.assertEqual(restored_clip, bound_clip)

            exact_replay = restarted.edit_timeline(bind_command)
            self.assertTrue(exact_replay["idempotentReplay"])
            self.assertEqual(
                exact_replay["timelineVersion"]["payloadDigest"],
                bound["timelineVersion"]["payloadDigest"],
            )
            changed_replay = deepcopy(bind_command)
            changed_replay["editCommand"]["arguments"][
                "effectResultDigest"
            ] = "f" * 64
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                restarted.edit_timeline(changed_replay)
            self.assertEqual(
                (caught.exception.code, caught.exception.status),
                ("idempotency_conflict", 409),
            )

            records = repository.list_records(workspace, run_ref)
            unbound_record = next(
                item
                for item in records
                if item["recordKind"] == "TimelineClip"
                and item["recordVersion"] == 3
                and item["recordRef"] == effect_clip["clipRef"]
            )
            bound_record = next(
                item
                for item in records
                if item["recordKind"] == "TimelineClip"
                and item["recordVersion"] == 4
                and item["recordRef"] == effect_clip["clipRef"]
            )
            self.assertIsNone(
                unbound_record["payload"]["sourceBinding"][
                    "effectResultRef"
                ]
            )
            self.assertEqual(
                bound_record["payload"]["sourceBinding"][
                    "effectResultRef"
                ],
                result["resultRef"],
            )
            with sqlite3.connect(evidence_database) as connection:
                tables_after = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(tables_after, tables_before)


if __name__ == "__main__":
    unittest.main()
