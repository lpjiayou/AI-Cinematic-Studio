from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import secrets
import sqlite3
from types import SimpleNamespace
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    token_sha256,
)
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server

from services.v5_core_os.episode_production.delivery import (
    K2DeliveryService,
    RejectingApprovalAuthority,
)
from services.v5_core_os.episode_production.evidence import (
    ALLOWED_EVIDENCE_RECORD_KINDS,
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.shot_graph import (
    ValidationFailedError,
)
from services.v5_core_os.episode_production.timeline_editing import (
    TIMELINE_TRACK_SCHEMA_VERSION,
    build_output_profile_binding,
    build_speed_spec,
    build_timeline_clip,
    build_timeline_edit_command,
    build_transform_spec,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.unit.test_episode_production_k2 import seed_k2_roots


WORKSPACE = "workspace-m13-t1-sqlite"
PROJECT = "project-m13-t1-sqlite"
SERIES = "series-m13-t1-sqlite"
EPISODE = "episode-m13-t1-sqlite"
RUN = "episode-production-run-m13-t1-sqlite"
SCRIPT_REF = "script-version-m13-t1-sqlite"
SCRIPT_DIGEST = "3" * 64
CREATED_AT = "2026-08-30T09:10:00Z"


def sealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def run_authority(
    *, workspace_ref: str = WORKSPACE, run_ref: str = RUN
) -> dict:
    return sealed(
        {
            "schemaVersion": "v5.episode-production-run.v1",
            "workspaceRef": workspace_ref,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": run_ref,
            "version": 1,
            "scriptVersionRef": SCRIPT_REF,
            "upstreamSnapshot": {
                "script": {
                    "scriptVersionRef": SCRIPT_REF,
                    "versionDigest": SCRIPT_DIGEST,
                }
            },
        }
    )


class RootAuthority:
    def __init__(self, runs: list[dict]) -> None:
        self.runs = {
            (item["workspaceRef"], item["productionRunRef"]): deepcopy(item)
            for item in runs
        }

    def verify_run_current(self, workspace_ref: str, run_ref: str) -> dict:
        result = self.runs.get((workspace_ref, run_ref))
        if result is None:
            raise StaleInputError("Episode Production run scope is stale")
        return deepcopy(result)

    def get_run(self, workspace_ref: str, run_ref: str) -> dict:
        return self.verify_run_current(workspace_ref, run_ref)


def _fact(kind: str, reference: str, payload: dict) -> EvidenceFact:
    return EvidenceFact(
        factKind=kind,
        factRef=reference,
        factVersion=1,
        payload=payload,
        payloadDigest=payload["payloadDigest"],
    )


def seed_authority(
    repository: SqliteEpisodeProductionEvidenceAdapter,
    run: dict,
) -> None:
    workspace_ref = run["workspaceRef"]
    run_ref = run["productionRunRef"]
    root_digest = run["payloadDigest"]
    authority = sealed(
        {
            "schemaVersion": "v5.authority-fixture.v1",
            "authorityRef": "authority-m13-t1-fixture",
        }
    )
    script = sealed(
        {
            "schemaVersion": "v5.script-fixture.v1",
            "scriptVersionRef": SCRIPT_REF,
            "scriptVersionDigest": SCRIPT_DIGEST,
        }
    )
    storyboard = sealed(
        {
            "schemaVersion": "v5.storyboard-version.fixture.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "rootPayloadDigest": root_digest,
            "storyboardVersionRef": "storyboard-version-m13-t1-sqlite",
            "scriptVersionRef": SCRIPT_REF,
            "scriptVersionDigest": SCRIPT_DIGEST,
        }
    )
    graph = sealed(
        {
            "schemaVersion": "v5.executable-shot-graph.fixture.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "rootPayloadDigest": root_digest,
            "executableShotGraphVersionRef": (
                "executable-shot-graph-version-m13-t1-sqlite"
            ),
            "scriptVersionRef": SCRIPT_REF,
            "scriptVersionDigest": SCRIPT_DIGEST,
            "storyboardDigest": storyboard["payloadDigest"],
            "shots": [],
            "output": {
                "frameRate": {"numerator": 24, "denominator": 1},
                "width": 704,
                "height": 1280,
                "totalFrames": 48,
            },
        }
    )
    gates = (
        GateAppend(
            workspaceRef=workspace_ref,
            productionRunRef=run_ref,
            gateName="G1_AUTHORITY_FIXTURE",
            idempotencyKey="m13-t1-authority-fixture",
            rootPayloadDigest=root_digest,
            requestDigest=_digest({"gate": "G1", "run": run_ref}),
            fromState="ROOTS_READY",
            toState="AUTHORITY_READY",
            createdAt=CREATED_AT,
            facts=(
                _fact(
                    "AuthorityIdentity",
                    authority["authorityRef"],
                    authority,
                ),
            ),
        ),
        GateAppend(
            workspaceRef=workspace_ref,
            productionRunRef=run_ref,
            gateName="G2_SCRIPT_FIXTURE",
            idempotencyKey="m13-t1-script-fixture",
            rootPayloadDigest=root_digest,
            requestDigest=_digest({"gate": "G2", "run": run_ref}),
            fromState="AUTHORITY_READY",
            toState="SCRIPT_VALIDATED",
            createdAt=CREATED_AT,
            facts=(_fact("ScriptVersion", SCRIPT_REF, script),),
        ),
        GateAppend(
            workspaceRef=workspace_ref,
            productionRunRef=run_ref,
            gateName="G3_SHOT_GRAPH",
            idempotencyKey="m13-t1-shot-graph-fixture",
            rootPayloadDigest=root_digest,
            requestDigest=_digest({"gate": "G3", "run": run_ref}),
            fromState="SCRIPT_VALIDATED",
            toState="SHOTS_COMPILED",
            createdAt=CREATED_AT,
            facts=(
                _fact(
                    "StoryboardVersion",
                    storyboard["storyboardVersionRef"],
                    storyboard,
                ),
                _fact(
                    "ExecutableShotGraph",
                    graph["executableShotGraphVersionRef"],
                    graph,
                ),
            ),
        ),
    )
    for gate in gates:
        repository.append_gate(gate)


def delivery_service(
    repository: SqliteEpisodeProductionEvidenceAdapter,
    root_authority: RootAuthority,
) -> K2DeliveryService:
    media = SimpleNamespace(
        assets=SimpleNamespace(
            shot_graph=SimpleNamespace(root_service=root_authority)
        )
    )
    return K2DeliveryService(
        media,
        repository,
        None,
        RejectingApprovalAuthority(),
        ref_factory=lambda prefix: f"{prefix}-m13-t1-sqlite",
        clock=lambda: CREATED_AT,
    )


def create_command(
    *, workspace_ref: str = WORKSPACE, run_ref: str = RUN
) -> dict:
    return {
        "workspaceRef": workspace_ref,
        "productionRunRef": run_ref,
        "operationRef": "m13-t1-create-timeline",
        "idempotencyKey": "m13-t1-create-timeline-key",
        "expectedRunVersion": 1,
    }


def edit_command(created: dict, *, key: str = "m13-t1-safe-area-key") -> dict:
    parent = created["timelineVersion"]
    return {
        "workspaceRef": parent["workspaceRef"],
        "productionRunRef": parent["productionRunRef"],
        "operationRef": "m13-t1-set-safe-area",
        "idempotencyKey": key,
        "expectedRunVersion": 1,
        "parentTimelineVersionRef": parent["timelineVersionRef"],
        "parentTimelineVersionDigest": parent["payloadDigest"],
        "editCommand": {
            "operation": "SET_SAFE_AREA",
            "arguments": {
                "safeArea": {
                    "leftPixels": 24,
                    "topPixels": 24,
                    "rightPixels": 24,
                    "bottomPixels": 24,
                }
            },
        },
    }


def identity_transform() -> dict:
    return build_transform_spec(
        {
            "positionXPixels": 0,
            "positionYPixels": 0,
            "scaleX": {"numerator": 1, "denominator": 1},
            "scaleY": {"numerator": 1, "denominator": 1},
            "rotationMilliDegrees": 0,
            "anchorXPixels": 0,
            "anchorYPixels": 0,
            "opacity": 1000,
            "perspectiveMode": "NONE",
            "perspectiveMatrix": None,
            "perspectiveCorners": None,
        }
    )


class M13TimelineEditingSqliteTests(unittest.TestCase):
    def test_expected_run_version_is_mandatory_positive_cas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            for invalid in (None, 0, True, "1"):
                with self.subTest(operation="create", value=invalid):
                    command = create_command()
                    command["expectedRunVersion"] = invalid
                    with self.assertRaises(ValidationFailedError):
                        service.create_timeline(command)
            self.assertEqual(repository.list_records(WORKSPACE, RUN), [])

            created = service.create_timeline(create_command())
            for index, invalid in enumerate((None, 0, True, "1")):
                with self.subTest(operation="edit", value=invalid):
                    command = edit_command(
                        created,
                        key=f"m13-invalid-cas-{index}",
                    )
                    command["expectedRunVersion"] = invalid
                    with self.assertRaises(ValidationFailedError):
                        service.edit_timeline(command)

    def test_output_profiles_must_resolve_to_current_shot_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            created = service.create_timeline(create_command())
            current = created["timelineVersion"]["outputProfileBindings"][0]
            for index, mutation in enumerate(("ref", "digest")):
                profile_command = {
                    key: deepcopy(value)
                    for key, value in current.items()
                    if key not in {"schemaVersion", "payloadDigest"}
                }
                if mutation == "ref":
                    profile_command["outputProfileRef"] = (
                        "nonexistent-output-profile"
                    )
                else:
                    profile_command["outputProfileDigest"] = "f" * 64
                command = edit_command(
                    created, key=f"m13-output-profile-drift-{index}"
                )
                command["operationRef"] = (
                    f"m13-output-profile-drift-operation-{index}"
                )
                command["editCommand"] = {
                    "operation": "SET_OUTPUT_PROFILES",
                    "arguments": {
                        "outputProfileBindings": [
                            build_output_profile_binding(profile_command)
                        ]
                    },
                }
                with self.subTest(mutation=mutation):
                    with self.assertRaises(StaleInputError):
                        service.edit_timeline(command)
            self.assertEqual(len(repository.list_records(WORKSPACE, RUN)), 6)

    def test_snapshot_membership_and_edit_chain_are_restore_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first_database = Path(directory) / "snapshot.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                first_database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            created = service.create_timeline(create_command())
            version = created["timelineVersion"]
            video_track = next(
                item for item in created["tracks"] if item["trackKind"] == "VIDEO"
            )
            asset = sealed(
                {
                    "schemaVersion": "v5.asset-version.fixture.v1",
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                    "assetVersionRef": "asset-version-injected-video-v1",
                    "mediaKind": "video",
                    "frameCount": 48,
                }
            )
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="AssetVersion",
                    recordRef=asset["assetVersionRef"],
                    recordVersion=1,
                    idempotencyKey="m13-injected-video-authority",
                    requestDigest=_digest({"asset": asset["payloadDigest"]}),
                    createdAt=CREATED_AT,
                    payload=asset,
                    payloadDigest=asset["payloadDigest"],
                )
            )
            injected_clip = build_timeline_clip(
                {
                    "clipRef": "clip-injected-into-version-one",
                    "timelineVersionRef": version["timelineVersionRef"],
                    "trackRef": video_track["trackRef"],
                    "clipKind": "VIDEO",
                    "timelineStartFrameInclusive": 24,
                    "timelineEndFrameExclusive": 36,
                    "enabled": True,
                    "layer": 0,
                    "zOrder": 1,
                    "opacity": 1000,
                    "blendMode": "NORMAL",
                    "sourceBinding": {
                        "assetVersionRef": asset["assetVersionRef"],
                        "assetVersionDigest": asset["payloadDigest"],
                        "sourceInFrameInclusive": 0,
                        "sourceOutFrameExclusive": 12,
                    },
                    "transitionIn": None,
                    "transitionOut": None,
                    "speed": build_speed_spec(
                        {"numerator": 1, "denominator": 1}
                    ),
                    "transform": identity_transform(),
                    "maskBindings": [],
                }
            )
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="TimelineClip",
                    recordRef=injected_clip["clipRef"],
                    recordVersion=1,
                    idempotencyKey="m13-injected-version-one-clip",
                    requestDigest=_digest(
                        {"clip": injected_clip["payloadDigest"]}
                    ),
                    createdAt=CREATED_AT,
                    payload=injected_clip,
                    payloadDigest=injected_clip["payloadDigest"],
                )
            )
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(repository, root).get_timeline(WORKSPACE, RUN)

            null_database = Path(directory) / "null-version-ref.sqlite3"
            null_repository = SqliteEpisodeProductionEvidenceAdapter(
                null_database, initialize_if_missing=True
            )
            seed_authority(null_repository, run)
            null_service = delivery_service(null_repository, root)
            null_service.create_timeline(create_command())
            null_track = sealed(
                {
                    "schemaVersion": TIMELINE_TRACK_SCHEMA_VERSION,
                    "trackRef": "track-null-version-bypass",
                    "timelineVersionRef": None,
                    "trackKind": "VIDEO",
                    "order": 99,
                    "enabled": True,
                    "lanePolicy": "LAYERED_Z_ORDER",
                }
            )
            null_repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="TimelineTrack",
                    recordRef=null_track["trackRef"],
                    recordVersion=1,
                    idempotencyKey="m13-null-version-track",
                    requestDigest=_digest(
                        {"track": null_track["payloadDigest"]}
                    ),
                    createdAt=CREATED_AT,
                    payload=null_track,
                    payloadDigest=null_track["payloadDigest"],
                )
            )
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(null_repository, root).get_timeline(
                    WORKSPACE, RUN
                )

            semantic_database = Path(directory) / "semantic-chain.sqlite3"
            semantic_repository = SqliteEpisodeProductionEvidenceAdapter(
                semantic_database, initialize_if_missing=True
            )
            seed_authority(semantic_repository, run)
            semantic_service = delivery_service(semantic_repository, root)
            semantic_initial = semantic_service.create_timeline(create_command())
            semantic_service.edit_timeline(edit_command(semantic_initial))
            connection = sqlite3.connect(semantic_database)
            try:
                row = connection.execute(
                    "SELECT rowid,payload_json FROM "
                    "v5_episode_production_records "
                    "WHERE record_kind='TimelineEditOperation'"
                ).fetchone()
                self.assertIsNotNone(row)
                tampered_command = json.loads(row[1])
                tampered_command["arguments"]["safeArea"][
                    "leftPixels"
                ] = 25
                tampered_command = sealed(tampered_command)
                connection.execute(
                    "UPDATE v5_episode_production_records "
                    "SET payload_json=?,payload_digest=? WHERE rowid=?",
                    (
                        json.dumps(
                            tampered_command,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        tampered_command["payloadDigest"],
                        row[0],
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(semantic_repository, root).get_timeline(
                    WORKSPACE, RUN
                )

            second_database = Path(directory) / "chain.sqlite3"
            chain_repository = SqliteEpisodeProductionEvidenceAdapter(
                second_database, initialize_if_missing=True
            )
            seed_authority(chain_repository, run)
            chain_service = delivery_service(chain_repository, root)
            initial = chain_service.create_timeline(create_command())
            successor = chain_service.edit_timeline(edit_command(initial))
            orphan = build_timeline_edit_command(
                {
                    "operationRef": "m13-orphan-edit-operation",
                    "idempotencyKey": "m13-orphan-edit-key",
                    "parentTimelineVersionRef": successor["timelineVersion"][
                        "timelineVersionRef"
                    ],
                    "parentTimelineVersionDigest": successor["timelineVersion"][
                        "payloadDigest"
                    ],
                    "newTimelineVersionRef": "m13-orphan-version-3",
                    "operation": "SET_SAFE_AREA",
                    "arguments": {
                        "safeArea": {
                            "leftPixels": 1,
                            "topPixels": 1,
                            "rightPixels": 1,
                            "bottomPixels": 1,
                        }
                    },
                    "createdAt": CREATED_AT,
                }
            )
            chain_repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="TimelineEditOperation",
                    recordRef=orphan["operationRef"],
                    recordVersion=1,
                    idempotencyKey="m13-orphan-edit-record",
                    requestDigest=_digest({"edit": orphan["payloadDigest"]}),
                    createdAt=CREATED_AT,
                    payload=orphan,
                    payloadDigest=orphan["payloadDigest"],
                )
            )
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(chain_repository, root).get_timeline(
                    WORKSPACE, RUN
                )

    def test_v3_authority_closes_both_legacy_timeline_writers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            service.create_timeline(create_command())
            with self.assertRaises(IdempotencyConflictError):
                service.compose_and_qc(
                    {
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": RUN,
                        "idempotencyKey": "legacy-g6-after-v3",
                    }
                )
            revision = repository.read_snapshot(WORKSPACE, RUN).revisionToken
            with self.assertRaises(IdempotencyConflictError):
                service.compose_timeline_preview(
                    {
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": RUN,
                        "operationRef": "legacy-v2-after-v3",
                        "idempotencyKey": "legacy-v2-after-v3-key",
                        "expectedRunVersion": 1,
                        "expectedEvidenceRevision": revision,
                        "timelineInputRefs": {
                            "videoAssetVersionRef": "video-dummy",
                            "audioInputBindingRefs": ["audio-input-dummy"],
                            "audioCueVersionRefs": ["audio-cue-dummy"],
                            "audioStemSetVersionRef": "stem-set-dummy",
                            "glyphRevealRequirementRef": "glyph-dummy",
                        },
                    }
                )
    def test_legacy_minimal_timeline_blocks_implicit_v3_root_creation(self) -> None:
        from services.v5_core_os.episode_production.timeline_preview import (
            build_timeline as build_legacy_timeline,
        )

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            legacy = build_legacy_timeline(
                {
                    "workspaceRef": WORKSPACE,
                    "projectRef": PROJECT,
                    "seriesRef": SERIES,
                    "episodeRef": EPISODE,
                    "productionRunRef": RUN,
                    "timelineRef": "timeline-minimal-history-sqlite",
                    "createdBy": "v5.m12-m13.timeline-preview.v1",
                    "createdAt": CREATED_AT,
                }
            )
            repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="Timeline",
                    recordRef=legacy["timelineRef"],
                    recordVersion=1,
                    idempotencyKey="m13-t1-legacy-minimal-timeline",
                    requestDigest=_digest(
                        {"legacyTimelineDigest": legacy["payloadDigest"]}
                    ),
                    createdAt=CREATED_AT,
                    payload=legacy,
                    payloadDigest=legacy["payloadDigest"],
                )
            )
            service = delivery_service(repository, root)
            with self.assertRaises(IdempotencyConflictError):
                service.create_timeline(create_command())
            stored = repository.get_record(
                WORKSPACE, RUN, legacy["timelineRef"], 1
            )
            self.assertEqual(stored["payload"], legacy)
            timeline_records = repository.list_records(
                WORKSPACE, RUN, record_kind="Timeline"
            )
            self.assertEqual(len(timeline_records), 1)
            self.assertEqual(
                timeline_records[0]["payload"]["schemaVersion"],
                "v5.timeline.v2",
            )

    def test_unknown_or_fact_journal_timeline_authority_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_authority()
            root = RootAuthority([run])

            def repository_for(name: str):
                repository = SqliteEpisodeProductionEvidenceAdapter(
                    Path(directory) / f"{name}.sqlite3",
                    initialize_if_missing=True,
                )
                seed_authority(repository, run)
                return repository

            for index, schema in enumerate(
                ("v5.timeline.v999", "v5.timeline-version.v3")
            ):
                repository = repository_for(f"unknown-root-{index}")
                payload = sealed(
                    {
                        "schemaVersion": schema,
                        "timelineRef": f"unknown-timeline-{index}",
                    }
                )
                repository.append_record(
                    EvidenceRecord(
                        workspaceRef=WORKSPACE,
                        productionRunRef=RUN,
                        recordKind="Timeline",
                        recordRef=payload["timelineRef"],
                        recordVersion=1,
                        idempotencyKey=f"unknown-root-{index}",
                        requestDigest=_digest({"unknown": index}),
                        createdAt=CREATED_AT,
                        payload=payload,
                        payloadDigest=payload["payloadDigest"],
                    )
                )
                with self.subTest(location="create", schema=schema):
                    with self.assertRaises(RepositoryUnavailableError):
                        delivery_service(repository, root).create_timeline(
                            create_command()
                        )

            unknown_kinds = (
                ("TimelineVersion", "timelineVersionRef"),
                ("TimelineTrack", "trackRef"),
                ("TimelineClip", "clipRef"),
                ("TimelineEditOperation", "operationRef"),
            )
            for index, (kind, identity_field) in enumerate(unknown_kinds):
                repository = repository_for(f"unknown-{kind.lower()}")
                service = delivery_service(repository, root)
                service.create_timeline(create_command())
                payload = sealed(
                    {
                        "schemaVersion": f"v5.{kind.lower()}.v999",
                        identity_field: f"unknown-{kind.lower()}-ref",
                    }
                )
                repository.append_record(
                    EvidenceRecord(
                        workspaceRef=WORKSPACE,
                        productionRunRef=RUN,
                        recordKind=kind,
                        recordRef=payload[identity_field],
                        recordVersion=1,
                        idempotencyKey=f"unknown-kind-{index}",
                        requestDigest=_digest({"unknownKind": kind}),
                        createdAt=CREATED_AT,
                        payload=payload,
                        payloadDigest=payload["payloadDigest"],
                    )
                )
                with self.subTest(location="restore", kind=kind):
                    with self.assertRaises(RepositoryUnavailableError):
                        delivery_service(repository, root).get_timeline(
                            WORKSPACE, RUN
                        )

            fact_repository = repository_for("v3-fact")
            fact_service = delivery_service(fact_repository, root)
            created = fact_service.create_timeline(create_command())
            fact_repository.append_gate(
                GateAppend(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    gateName="G4_ASSET_RESOLUTION",
                    idempotencyKey="m13-v3-fact-injection",
                    rootPayloadDigest=run["payloadDigest"],
                    requestDigest=_digest({"v3Fact": True}),
                    fromState="SHOTS_COMPILED",
                    toState="ASSETS_READY",
                    createdAt=CREATED_AT,
                    facts=(
                        _fact(
                            "Timeline",
                            created["timeline"]["timelineRef"],
                            created["timeline"],
                        ),
                    ),
                )
            )
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(fact_repository, root).get_timeline(
                    WORKSPACE, RUN
                )

            orphan_repository = repository_for("orphan-v3-version")
            orphan_service = delivery_service(orphan_repository, root)
            orphan_created = orphan_service.create_timeline(create_command())
            orphan_version = deepcopy(orphan_created["timelineVersion"])
            orphan_version.pop("payloadDigest")
            orphan_version["timelineRef"] = "other-m13-timeline-root"
            orphan_version["timelineVersionRef"] = "other-m13-version-1"
            orphan_version = sealed(orphan_version)
            orphan_repository.append_record(
                EvidenceRecord(
                    workspaceRef=WORKSPACE,
                    productionRunRef=RUN,
                    recordKind="TimelineVersion",
                    recordRef=orphan_version["timelineVersionRef"],
                    recordVersion=1,
                    idempotencyKey="b" * 64,
                    requestDigest="c" * 64,
                    createdAt=CREATED_AT,
                    payload=orphan_version,
                    payloadDigest=orphan_version["payloadDigest"],
                )
            )
            with self.assertRaises(RepositoryUnavailableError):
                delivery_service(orphan_repository, root).get_timeline(
                    WORKSPACE, RUN
                )

    def test_create_edit_restart_exact_replay_and_lineage_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)

            created = service.create_timeline(create_command())
            self.assertFalse(created["idempotentReplay"])
            self.assertEqual(created["timelineVersion"]["versionNumber"], 1)
            self.assertEqual(
                [item["trackKind"] for item in created["tracks"]],
                ["VIDEO", "AUDIO", "SUBTITLE", "EFFECT"],
            )
            self.assertEqual(created["clips"], [])
            parent_copy = deepcopy(created)

            command = edit_command(created)
            edited = service.edit_timeline(command)
            self.assertFalse(edited["idempotentReplay"])
            self.assertEqual(edited["timelineVersion"]["versionNumber"], 2)
            self.assertEqual(
                edited["timelineVersion"]["parentTimelineVersionDigest"],
                created["timelineVersion"]["payloadDigest"],
            )
            self.assertEqual(created, parent_copy)

            create_replay = service.create_timeline(create_command())
            self.assertTrue(create_replay["idempotentReplay"])
            self.assertEqual(
                create_replay["timelineVersion"]["payloadDigest"],
                created["timelineVersion"]["payloadDigest"],
            )
            self.assertEqual(
                [item["versionNumber"] for item in create_replay["lineage"]],
                [1],
            )

            replay = service.edit_timeline(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(
                replay["timelineVersion"]["payloadDigest"],
                edited["timelineVersion"]["payloadDigest"],
            )
            self.assertEqual(
                [item["versionNumber"] for item in replay["lineage"]],
                [1, 2],
            )

            third_command = edit_command(
                edited, key="m13-t1-safe-area-key-v3"
            )
            third_command["operationRef"] = "m13-t1-set-safe-area-v3"
            third_command["editCommand"]["arguments"]["safeArea"] = {
                "leftPixels": 20,
                "topPixels": 20,
                "rightPixels": 20,
                "bottomPixels": 20,
            }
            third = service.edit_timeline(third_command)
            self.assertEqual(third["timelineVersion"]["versionNumber"], 3)
            replay_after_third = service.edit_timeline(command)
            self.assertEqual(
                replay_after_third["timelineVersion"]["payloadDigest"],
                edited["timelineVersion"]["payloadDigest"],
            )
            self.assertEqual(
                [
                    item["versionNumber"]
                    for item in replay_after_third["lineage"]
                ],
                [1, 2],
            )

            restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=False
            )
            restarted = delivery_service(restarted_repository, root)
            restored = restarted.get_timeline(WORKSPACE, RUN)
            self.assertEqual(
                restored["timelineVersion"]["payloadDigest"],
                third["timelineVersion"]["payloadDigest"],
            )
            self.assertEqual(
                [item["versionNumber"] for item in restored["lineage"]],
                [1, 2, 3],
            )
            versions = restarted.get_timeline_versions(WORKSPACE, RUN)
            self.assertEqual(
                [item["versionNumber"] for item in versions["versions"]],
                [1, 2, 3],
            )

    def test_changed_replay_and_concurrent_stale_parent_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            created = service.create_timeline(create_command())
            first = edit_command(created)
            service.edit_timeline(first)

            changed = deepcopy(first)
            changed["editCommand"]["arguments"]["safeArea"][
                "leftPixels"
            ] = 25
            with self.assertRaises(IdempotencyConflictError):
                service.edit_timeline(changed)

            stale = edit_command(created, key="m13-t1-stale-parent-key")
            stale["operationRef"] = "m13-t1-stale-parent-operation"
            with self.assertRaises(StaleInputError):
                service.edit_timeline(stale)

    def test_sqlite_tamper_is_rejected_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            run = run_authority()
            root = RootAuthority([run])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, run)
            service = delivery_service(repository, root)
            service.create_timeline(create_command())

            connection = sqlite3.connect(database)
            try:
                row = connection.execute(
                    "SELECT rowid,payload_json FROM "
                    "v5_episode_production_records "
                    "WHERE record_kind='TimelineVersion'"
                ).fetchone()
                self.assertIsNotNone(row)
                payload = json.loads(row[1])
                payload["durationFrames"] = 47
                connection.execute(
                    "UPDATE v5_episode_production_records SET payload_json=? "
                    "WHERE rowid=?",
                    (
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        row[0],
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(RepositoryUnavailableError):
                restarted_repository = SqliteEpisodeProductionEvidenceAdapter(
                    database, initialize_if_missing=False
                )
                restarted = delivery_service(restarted_repository, root)
                restarted.get_timeline(WORKSPACE, RUN)

    def test_sqlite_timeline_batch_envelope_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = run_authority()
            root = RootAuthority([run])
            for mutation in ("created_at", "idempotency_key"):
                database = Path(directory) / f"{mutation}.sqlite3"
                repository = SqliteEpisodeProductionEvidenceAdapter(
                    database, initialize_if_missing=True
                )
                seed_authority(repository, run)
                service = delivery_service(repository, root)
                created = service.create_timeline(create_command())
                service.edit_timeline(edit_command(created))
                connection = sqlite3.connect(database)
                try:
                    if mutation == "created_at":
                        connection.execute(
                            "UPDATE v5_episode_production_records "
                            "SET created_at=? WHERE record_kind='TimelineTrack' "
                            "AND record_version=2",
                            ("2026-08-30T09:11:00Z",),
                        )
                    else:
                        connection.execute(
                            "UPDATE v5_episode_production_records "
                            "SET idempotency_key=? "
                            "WHERE record_kind='TimelineVersion' "
                            "AND record_version=2",
                            ("a" * 64,),
                        )
                    connection.commit()
                finally:
                    connection.close()
                with self.subTest(mutation=mutation):
                    with self.assertRaises(RepositoryUnavailableError):
                        restarted = delivery_service(
                            SqliteEpisodeProductionEvidenceAdapter(
                                database, initialize_if_missing=False
                            ),
                            root,
                        )
                        restarted.get_timeline(WORKSPACE, RUN)

    def test_workspace_isolation_and_no_master_or_export_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            second_workspace = "workspace-m13-t1-other"
            second_run_ref = "episode-production-run-m13-t1-other"
            first = run_authority()
            second = run_authority(
                workspace_ref=second_workspace,
                run_ref=second_run_ref,
            )
            root = RootAuthority([first, second])
            repository = SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            seed_authority(repository, first)
            seed_authority(repository, second)
            service = delivery_service(repository, root)
            primary = service.create_timeline(create_command())
            foreign = service.create_timeline(
                create_command(
                    workspace_ref=second_workspace,
                    run_ref=second_run_ref,
                )
            )
            self.assertNotEqual(
                primary["timeline"]["timelineRef"],
                foreign["timeline"]["timelineRef"],
            )
            self.assertEqual(
                service.get_timeline(WORKSPACE, RUN)["timeline"][
                    "workspaceRef"
                ],
                WORKSPACE,
            )
            primary_records = repository.list_records(WORKSPACE, RUN)
            self.assertFalse(
                {
                    "EpisodeMaster",
                    "ExportArtifact",
                    "ExportCandidate",
                    "RenderCandidate",
                    "RenderManifest",
                }
                & {item["recordKind"] for item in primary_records}
            )
            self.assertFalse(
                {
                    "EpisodeMaster",
                    "ExportArtifact",
                }
                & {
                    fact["factKind"]
                    for gate in repository.list_gates(WORKSPACE, RUN)
                    for fact in gate["facts"]
                }
            )

    def test_export_candidate_authority_surface_is_absent(self) -> None:
        from apps.creator_workspace_mvp.server import (
            EPISODE_PRODUCTION_SUBRESOURCES,
        )
        from services.v5_core_os.episode_production import (
            delivery as delivery_module,
            timeline_editing,
        )

        self.assertNotIn("ExportCandidate", ALLOWED_EVIDENCE_RECORD_KINDS)
        self.assertFalse(hasattr(timeline_editing, "ExportCandidate"))
        self.assertFalse(
            hasattr(delivery_module, "EXPORT_CANDIDATE_SCHEMA_VERSION")
        )
        self.assertNotIn("export-candidate", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("export-candidates", EPISODE_PRODUCTION_SUBRESOURCES)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-evidence.sqlite3"
            SqliteEpisodeProductionEvidenceAdapter(
                database, initialize_if_missing=True
            )
            connection = sqlite3.connect(database)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()
        self.assertFalse(
            any("export_candidate" in table.lower() for table in tables)
        )


class M13TimelineEditingPublicHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = (
            Path(self.temporary_directory.name) / "episode-evidence.sqlite3"
        )
        self.run = run_authority()
        self.root = RootAuthority([self.run])
        self.repository = SqliteEpisodeProductionEvidenceAdapter(
            self.database, initialize_if_missing=True
        )
        seed_authority(self.repository, self.run)
        self.delivery = delivery_service(self.repository, self.root)

        boundary = object.__new__(EpisodeProductionPublicBoundary)
        setattr(
            boundary,
            "_EpisodeProductionPublicBoundary__delivery",
            self.delivery,
        )
        self.token = secrets.token_urlsafe(48)
        authenticator = PublicApiAuthenticator.from_mapping(
            {
                "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                "credentials": [
                    {
                        "credentialRef": "creator-m13-t1-http",
                        "workspaceRef": WORKSPACE,
                        "tokenSha256": token_sha256(self.token),
                        "enabled": True,
                    }
                ],
            }
        )
        assembly, _, _, _, _, _ = seed_k2_roots()
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=assembly.series_episode,
            project_boundary=assembly.project_context,
            series_planning_boundary=assembly.series_planning,
            series_intelligence_boundary=assembly.series_intelligence,
            script_studio_boundary=assembly.script_studio,
            episode_production_boundary=boundary,
            public_authenticator=authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        encoded_run = parse.quote(RUN, safe="")
        self.timeline_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run}/timeline"
        )
        self.edit_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run}/timeline-edits"
        )
        self.versions_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run}/timeline-versions"
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary_directory.cleanup()

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(http_request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _get(self, path: str) -> tuple[int, dict]:
        http_request = request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(http_request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _assert_http_error(
        self, operation, *, status: int, codes: set[str]
    ) -> None:
        with self.assertRaises(error.HTTPError) as caught:
            operation()
        self.assertEqual(caught.exception.code, status)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn(payload["error"]["code"], codes)

    def _assert_sanitized(self, value: object) -> None:
        forbidden = {
            "absolutepath",
            "actorref",
            "approvalref",
            "argv",
            "credential",
            "ffmpegargv",
            "ffmpegfilter",
            "filter",
            "internalpath",
            "path",
            "privateruntimediagnostics",
            "shellcommand",
            "sql",
            "storagekey",
            "token",
        }

        def visit(item: object) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    normalized = key.replace("_", "").replace("-", "").lower()
                    self.assertNotIn(normalized, forbidden)
                    self.assertFalse(normalized.endswith("storagekey"))
                    self.assertFalse(normalized.endswith("argv"))
                    visit(nested)
            elif isinstance(item, list):
                for nested in item:
                    visit(nested)

        visit(value)

    def test_browser_scope_claims_are_rejected_before_domain_write(self) -> None:
        command = {
            "operationRef": "m13-t1-http-create",
            "idempotencyKey": "m13-t1-http-create-key",
            "expectedRunVersion": 1,
        }
        for field, value, codes in (
            (
                "workspaceRef",
                WORKSPACE,
                {"client_workspace_scope_forbidden"},
            ),
            ("productionRunRef", RUN, {"invalid_request"}),
            ("actorRef", "browser-forged-actor", {"invalid_request"}),
            ("approvalRef", "browser-forged-approval", {"invalid_request"}),
        ):
            with self.subTest(field=field):
                self._assert_http_error(
                    lambda field=field, value=value: self._post(
                        self.timeline_path,
                        {**command, field: value},
                    ),
                    status=400,
                    codes=codes,
                )
        self.assertEqual(self.repository.list_records(WORKSPACE, RUN), [])

        self._assert_http_error(
            lambda: self._post(
                f"{self.timeline_path}?workspaceRef={parse.quote(WORKSPACE)}",
                command,
            ),
            status=400,
            codes={"client_workspace_scope_forbidden", "invalid_request"},
        )
        self.assertEqual(self.repository.list_records(WORKSPACE, RUN), [])

    def test_public_writes_reject_missing_or_nonpositive_run_cas(self) -> None:
        base_create = {
            "operationRef": "m13-t1-http-cas-create",
            "idempotencyKey": "m13-t1-http-cas-create-key",
        }
        for invalid in (None, 0, True, "1"):
            with self.subTest(operation="create", value=invalid):
                self._assert_http_error(
                    lambda invalid=invalid: self._post(
                        self.timeline_path,
                        {**base_create, "expectedRunVersion": invalid},
                    ),
                    status=400,
                    codes={"invalid_request"},
                )
        self._assert_http_error(
            lambda: self._post(self.timeline_path, base_create),
            status=400,
            codes={"invalid_request"},
        )
        self.assertEqual(self.repository.list_records(WORKSPACE, RUN), [])

        status, created = self._post(
            self.timeline_path,
            {**base_create, "expectedRunVersion": 1},
        )
        self.assertEqual(status, 201)
        parent = created["timelineVersion"]
        base_edit = {
            "operationRef": "m13-t1-http-cas-edit",
            "idempotencyKey": "m13-t1-http-cas-edit-key",
            "parentTimelineVersionRef": parent["timelineVersionRef"],
            "parentTimelineVersionDigest": parent["payloadDigest"],
            "editCommand": {
                "operation": "SET_SAFE_AREA",
                "arguments": {
                    "safeArea": {
                        "leftPixels": 24,
                        "topPixels": 24,
                        "rightPixels": 24,
                        "bottomPixels": 24,
                    }
                },
            },
        }
        for invalid in (None, 0, True, "1"):
            with self.subTest(operation="edit", value=invalid):
                self._assert_http_error(
                    lambda invalid=invalid: self._post(
                        self.edit_path,
                        {**base_edit, "expectedRunVersion": invalid},
                    ),
                    status=400,
                    codes={"invalid_request"},
                )
        self._assert_http_error(
            lambda: self._post(self.edit_path, base_edit),
            status=400,
            codes={"invalid_request"},
        )

    def test_path_filter_raw_authority_and_publication_claims_are_rejected(self) -> None:
        create_payload = {
            "operationRef": "m13-t1-http-create",
            "idempotencyKey": "m13-t1-http-create-key",
            "expectedRunVersion": 1,
        }
        status, created = self._post(self.timeline_path, create_payload)
        self.assertEqual(status, 201)
        parent = created["timelineVersion"]
        base = {
            "operationRef": "m13-t1-http-edit",
            "idempotencyKey": "m13-t1-http-edit-key",
            "expectedRunVersion": 1,
            "parentTimelineVersionRef": parent["timelineVersionRef"],
            "parentTimelineVersionDigest": parent["payloadDigest"],
            "editCommand": {
                "operation": "SET_SAFE_AREA",
                "arguments": {
                    "safeArea": {
                        "leftPixels": 24,
                        "topPixels": 24,
                        "rightPixels": 24,
                        "bottomPixels": 24,
                    }
                },
            },
        }
        for field, value in (
            ("absolutePath", "/tmp/browser-selected.mp4"),
            ("ffmpegFilter", "movie=/tmp/input.mp4;overlay"),
            ("shellCommand", "ffmpeg -i input output"),
            ("storageKey", "browser/selected/object"),
            ("rawAssetVersion", {"assetVersionRef": "forged"}),
            ("rawAudioCue", {"audioCueRef": "forged"}),
            ("rawRequirement", {"requirementRef": "forged"}),
            ("publicationAllowed", True),
            ("canonicalMutations", ["publish"]),
        ):
            with self.subTest(field=field):
                forged = deepcopy(base)
                forged["editCommand"]["arguments"][field] = value
                self._assert_http_error(
                    lambda forged=forged: self._post(self.edit_path, forged),
                    status=400,
                    codes={"invalid_request"},
                )
        self.assertEqual(
            len(self.repository.list_records(WORKSPACE, RUN)),
            6,
        )

    def test_http_rejects_unresolvable_output_profile_bindings(self) -> None:
        status, created = self._post(
            self.timeline_path,
            {
                "operationRef": "m13-t1-http-profile-create",
                "idempotencyKey": "m13-t1-http-profile-create-key",
                "expectedRunVersion": 1,
            },
        )
        self.assertEqual(status, 201)
        parent = created["timelineVersion"]
        current = parent["outputProfileBindings"][0]
        for index, mutation in enumerate(("ref", "digest")):
            profile_command = {
                key: deepcopy(value)
                for key, value in current.items()
                if key not in {"schemaVersion", "payloadDigest"}
            }
            if mutation == "ref":
                profile_command["outputProfileRef"] = "missing-profile"
            else:
                profile_command["outputProfileDigest"] = "f" * 64
            payload = {
                "operationRef": f"m13-t1-http-profile-edit-{index}",
                "idempotencyKey": f"m13-t1-http-profile-edit-key-{index}",
                "expectedRunVersion": 1,
                "parentTimelineVersionRef": parent["timelineVersionRef"],
                "parentTimelineVersionDigest": parent["payloadDigest"],
                "editCommand": {
                    "operation": "SET_OUTPUT_PROFILES",
                    "arguments": {
                        "outputProfileBindings": [
                            build_output_profile_binding(profile_command)
                        ]
                    },
                },
            }
            with self.subTest(mutation=mutation):
                self._assert_http_error(
                    lambda payload=payload: self._post(
                        self.edit_path, payload
                    ),
                    status=409,
                    codes={"stale_input"},
                )

    def test_public_create_edit_and_get_projections_are_sanitized(self) -> None:
        status, created = self._post(
            self.timeline_path,
            {
                "operationRef": "m13-t1-http-create",
                "idempotencyKey": "m13-t1-http-create-key",
                "expectedRunVersion": 1,
            },
        )
        self.assertEqual(status, 201)
        self._assert_sanitized(created)
        parent = created["timelineVersion"]
        status, edited = self._post(
            self.edit_path,
            {
                "operationRef": "m13-t1-http-edit",
                "idempotencyKey": "m13-t1-http-edit-key",
                "expectedRunVersion": 1,
                "parentTimelineVersionRef": parent["timelineVersionRef"],
                "parentTimelineVersionDigest": parent["payloadDigest"],
                "editCommand": {
                    "operation": "SET_SAFE_AREA",
                    "arguments": {
                        "safeArea": {
                            "leftPixels": 24,
                            "topPixels": 24,
                            "rightPixels": 24,
                            "bottomPixels": 24,
                        }
                    },
                },
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(edited["timelineVersion"]["versionNumber"], 2)
        self._assert_sanitized(edited)

        status, current = self._get(self.timeline_path)
        self.assertEqual(status, 200)
        self.assertEqual(current["timelineVersion"]["versionNumber"], 2)
        self._assert_sanitized(current)
        status, versions = self._get(self.versions_path)
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["versionNumber"] for item in versions["versions"]],
            [1, 2],
        )
        self._assert_sanitized(versions)


if __name__ == "__main__":
    unittest.main()
