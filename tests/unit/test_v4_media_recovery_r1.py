from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock
import tempfile
import time
import unittest
from unittest import mock

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    MediaJobError,
    MediaJobStateError,
    SqliteMediaJobAdapter,
)
from services.v4_platform.artifact_recovery import (
    ArtifactRecoveryStore,
    ArtifactRecoveryStoreError,
)
from services.v4_platform.media_jobs import (
    MediaJobConflictError,
    _validate_request,
)
from tests.unit.test_v4_comfyui_adapter import m11_request
from tests.unit.test_v4_media_job_fault_recovery import (
    RUN,
    WORKSPACE as RECOVERY_WORKSPACE,
    MutableClock,
    Refs,
    request as recovery_request,
)
from tests.unit.test_v4_media_jobs import WORKSPACE, one_request


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _changed_request(source, *, suffix, ordinal=None):
    value = deepcopy(source)
    value["generationRequestRef"] = f"{source['generationRequestRef']}-{suffix}"
    value["generationRequestVersionRef"] = (
        f"{source['generationRequestVersionRef']}-{suffix}"
    )
    if ordinal is not None and "ordinal" in value:
        value["ordinal"] = ordinal
    value.pop("payloadDigest", None)
    value["payloadDigest"] = sha256(_canonical(value)).hexdigest()
    return value


class CountingLocalAdapter:
    adapter_identity = DeterministicLocalFfmpegAdapter.adapter_identity
    provenance = DeterministicLocalFfmpegAdapter.provenance

    def __init__(self):
        self.calls = 0
        self.delegate = DeterministicLocalFfmpegAdapter()

    def generate(self, generation_request, candidate_path):
        self.calls += 1
        return self.delegate.generate(generation_request, candidate_path)


class V4BatchReservationR1Tests(unittest.TestCase):
    def test_batch_key_pins_members_and_digests_across_restart(self):
        for kind in ("memory", "sqlite"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                refs, run, first_request = one_request()
                database = Path(directory) / "jobs.sqlite3"
                repository = (
                    InMemoryMediaJobAdapter()
                    if kind == "memory"
                    else SqliteMediaJobAdapter(database)
                )
                adapter = CountingLocalAdapter()
                artifacts = Path(directory) / "artifacts"
                first = MediaJobCoordinator(
                    repository,
                    adapter,
                    artifacts,
                    ref_factory=refs,
                    clock=lambda: "2026-08-24T01:00:00Z",
                )
                result = first.execute_batch(
                    WORKSPACE,
                    run["productionRunRef"],
                    [first_request],
                    batch_idempotency_key="durable-batch-key",
                )
                self.assertEqual(result[0]["state"], "SUCCEEDED")
                self.assertEqual(adapter.calls, 1)

                restored_repository = (
                    repository
                    if kind == "memory"
                    else SqliteMediaJobAdapter(database)
                )
                restored = MediaJobCoordinator(
                    restored_repository,
                    adapter,
                    artifacts,
                    ref_factory=refs,
                    clock=lambda: "2026-08-24T01:00:01Z",
                )
                replay = restored.execute_batch(
                    WORKSPACE,
                    run["productionRunRef"],
                    [first_request],
                    batch_idempotency_key="durable-batch-key",
                )
                self.assertEqual(replay[0]["jobRef"], result[0]["jobRef"])
                self.assertEqual(adapter.calls, 1)

                second_request = _changed_request(
                    first_request, suffix="second", ordinal=2
                )
                with self.assertRaises(MediaJobConflictError):
                    restored.execute_batch(
                        WORKSPACE,
                        run["productionRunRef"],
                        [first_request, second_request],
                        batch_idempotency_key="durable-batch-key",
                    )
                self.assertEqual(
                    len(
                        restored.list_jobs(
                            WORKSPACE, run["productionRunRef"]
                        )
                    ),
                    1,
                )
                self.assertEqual(adapter.calls, 1)

                changed_digest = deepcopy(first_request)
                changed_digest["parameters"]["visualSeedDigest"] = "f" * 64
                changed_digest.pop("payloadDigest")
                changed_digest["payloadDigest"] = sha256(
                    _canonical(changed_digest)
                ).hexdigest()
                with self.assertRaises(MediaJobConflictError):
                    restored.execute_batch(
                        WORKSPACE,
                        run["productionRunRef"],
                        [changed_digest],
                        batch_idempotency_key="durable-batch-key",
                    )

    def test_batch_key_pins_member_order(self):
        for kind in ("memory", "sqlite"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                refs, run, first_request = one_request()
                second_request = _changed_request(
                    first_request, suffix="ordered-second", ordinal=2
                )
                repository = (
                    InMemoryMediaJobAdapter()
                    if kind == "memory"
                    else SqliteMediaJobAdapter(Path(directory) / "jobs.sqlite3")
                )
                adapter = CountingLocalAdapter()
                coordinator = MediaJobCoordinator(
                    repository,
                    adapter,
                    Path(directory) / "artifacts",
                    ref_factory=refs,
                    clock=lambda: "2026-08-24T01:30:00Z",
                )
                coordinator.execute_batch(
                    WORKSPACE,
                    run["productionRunRef"],
                    [first_request, second_request],
                    batch_idempotency_key="ordered-batch",
                )
                with self.assertRaises(MediaJobConflictError):
                    coordinator.execute_batch(
                        WORKSPACE,
                        run["productionRunRef"],
                        [second_request, first_request],
                        batch_idempotency_key="ordered-batch",
                    )
                self.assertEqual(adapter.calls, 2)


class V4M11SuccessorRequestR1Tests(unittest.TestCase):
    @staticmethod
    def _successor_request():
        value = m11_request("a" * 64)
        value.update(
            {
                "schemaVersion": "v5.k2-real-shot-video-request.v2",
                "generationRequestVersionRef": (
                    "real-video-generation-request-1-v2"
                ),
                "version": 2,
                "realVideoRevisionRef": "real-video-revision-shot-01-v2",
                "sourceRealVideoPlanRef": "real-video-plan-v1",
                "sourceRealVideoPlanDigest": "b" * 64,
                "supersedesGenerationRequestVersionRef": (
                    "real-video-generation-request-1-v1"
                ),
                "supersedesGenerationRequestDigest": "c" * 64,
            }
        )
        value.pop("payloadDigest")
        value["payloadDigest"] = sha256(_canonical(value)).hexdigest()
        return value

    def test_accepts_only_the_closed_successor_request_shape(self):
        value = self._successor_request()
        _validate_request(value)

        broadened_v1 = m11_request("a" * 64)
        broadened_v1["realVideoRevisionRef"] = "forbidden-on-v1"
        broadened_v1["payloadDigest"] = sha256(
            _canonical(
                {
                    key: item
                    for key, item in broadened_v1.items()
                    if key != "payloadDigest"
                }
            )
        ).hexdigest()
        with self.assertRaises(MediaJobError):
            _validate_request(broadened_v1)

        extra = deepcopy(value)
        extra["untrustedRuntimePath"] = "/tmp/forbidden"
        extra["payloadDigest"] = sha256(
            _canonical(
                {key: item for key, item in extra.items() if key != "payloadDigest"}
            )
        ).hexdigest()
        with self.assertRaises(MediaJobError):
            _validate_request(extra)

        bad_predecessor = deepcopy(value)
        bad_predecessor["supersedesGenerationRequestDigest"] = "not-a-digest"
        bad_predecessor["payloadDigest"] = sha256(
            _canonical(
                {
                    key: item
                    for key, item in bad_predecessor.items()
                    if key != "payloadDigest"
                }
            )
        ).hexdigest()
        with self.assertRaises(MediaJobError):
            _validate_request(bad_predecessor)

    def test_v1_and_v2_reject_broadened_or_runtime_invalid_nested_shapes(self):
        for schema in ("v1", "v2"):
            with self.subTest(schema=schema):
                source = (
                    m11_request("a" * 64)
                    if schema == "v1"
                    else self._successor_request()
                )
                cases = []

                broadened_probe = deepcopy(source)
                broadened_probe["sourceImageProbe"]["internalPath"] = (
                    "/private/start.png"
                )
                cases.append(broadened_probe)

                broadened_camera = deepcopy(source)
                broadened_camera["promptSpec"]["cameraInstruction"][
                    "providerSecret"
                ] = "forbidden"
                cases.append(broadened_camera)

                empty_continuity = deepcopy(source)
                empty_continuity["promptSpec"]["continuityConstraints"] = []
                cases.append(empty_continuity)

                oversized_action = deepcopy(source)
                oversized_action["promptSpec"]["action"] = "x" * 1001
                cases.append(oversized_action)

                empty_negative = deepcopy(source)
                empty_negative["parameters"]["negativePrompt"] = ""
                cases.append(empty_negative)

                non_finite_lens = deepcopy(source)
                non_finite_lens["promptSpec"]["cameraInstruction"][
                    "lensMm"
                ] = float("nan")
                cases.append(non_finite_lens)

                oversized_integer_lens = deepcopy(source)
                oversized_integer_lens["promptSpec"]["cameraInstruction"][
                    "lensMm"
                ] = 10**400
                cases.append(oversized_integer_lens)

                for value in cases:
                    value.pop("payloadDigest")
                    value["payloadDigest"] = sha256(_canonical(value)).hexdigest()
                    with self.assertRaises(MediaJobError):
                        _validate_request(value)


class V4LeaseHeartbeatR1Tests(unittest.TestCase):
    def test_running_attempt_renews_lease_and_recovery_cannot_duplicate_it(self):
        for kind in ("memory", "sqlite"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / "jobs.sqlite3"
                repository = (
                    InMemoryMediaJobAdapter()
                    if kind == "memory"
                    else SqliteMediaJobAdapter(database)
                )
                clock = MutableClock()
                adapter = CountingLocalAdapter()
                artifacts = Path(directory) / "artifacts"
                coordinator = MediaJobCoordinator(
                    repository,
                    adapter,
                    artifacts,
                    ref_factory=Refs(),
                    clock=clock,
                    lease_seconds=10,
                    heartbeat_interval_seconds=0.01,
                    max_attempts=1,
                )
                observer_repository = (
                    repository
                    if kind == "memory"
                    else SqliteMediaJobAdapter(database)
                )
                observer = MediaJobCoordinator(
                    observer_repository,
                    DeterministicLocalFfmpegAdapter(),
                    artifacts,
                    ref_factory=Refs(),
                    clock=clock,
                    lease_seconds=10,
                    heartbeat_interval_seconds=0.01,
                    max_attempts=1,
                )

                original_generate = adapter.generate
                observed_recovery = []

                def long_generate(generation_request, candidate_path):
                    produced = original_generate(
                        generation_request, candidate_path
                    )
                    clock.value = "2026-08-24T00:00:05Z"
                    time.sleep(0.08)
                    clock.value = "2026-08-24T00:00:11Z"
                    time.sleep(0.08)
                    observed_recovery.extend(
                        observer.recover_expired(RECOVERY_WORKSPACE, RUN)
                    )
                    return produced

                adapter.generate = long_generate
                coordinator.dispatch(
                    recovery_request(), idempotency_key="heartbeat-long-job"
                )
                leased = coordinator.lease_next(
                    RECOVERY_WORKSPACE, RUN, "heartbeat-worker"
                )
                result = coordinator.run_leased(leased, "heartbeat-worker")
                self.assertEqual(result["state"], "SUCCEEDED")
                self.assertEqual(observed_recovery, [])
                self.assertEqual(adapter.calls, 1)
                self.assertEqual(len(result["attempts"]), 1)

    def test_expired_worker_cannot_create_final_artifact_after_commit_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = InMemoryMediaJobAdapter()
            clock = MutableClock()
            artifacts = Path(directory) / "artifacts"
            coordinator = MediaJobCoordinator(
                repository,
                DeterministicLocalFfmpegAdapter(),
                artifacts,
                ref_factory=Refs(),
                clock=clock,
                lease_seconds=10,
                heartbeat_interval_seconds=9.9,
                max_attempts=1,
            )
            created, _ = coordinator.dispatch(
                recovery_request(), idempotency_key="fenced-publication"
            )
            leased = coordinator.lease_next(
                RECOVERY_WORKSPACE, RUN, "fenced-worker"
            )
            original_replace = coordinator._artifact_recovery.durable_replace

            def expire_before_publish(source, destination, **kwargs):
                clock.value = "2026-08-24T00:00:11Z"
                return original_replace(source, destination, **kwargs)

            with mock.patch.object(
                coordinator._artifact_recovery,
                "durable_replace",
                side_effect=expire_before_publish,
            ):
                with self.assertRaisesRegex(
                    MediaJobStateError, "worker lease was fenced"
                ):
                    coordinator.run_leased(leased, "fenced-worker")

            pending = repository.get(
                RECOVERY_WORKSPACE, RUN, created["jobRef"]
            )
            intent = pending["artifactCommitIntent"]
            self.assertEqual(pending["state"], "RUNNING")
            self.assertIsNotNone(intent)
            candidate = artifacts / intent["candidateStorageKey"]
            final = artifacts / intent["finalStorageKey"]
            self.assertTrue(candidate.is_file())
            self.assertFalse(final.exists())

            recovered = coordinator.recover_expired(
                RECOVERY_WORKSPACE, RUN
            )[0]
            self.assertEqual(recovered["state"], "FAILED")
            self.assertIsNone(recovered["artifactCommitIntent"])
            self.assertFalse(candidate.exists())
            self.assertFalse(final.exists())


class V4SqliteSchemaR1Tests(unittest.TestCase):
    @staticmethod
    def _create_legacy_v1(path):
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE v4_media_job_schema ("
                "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO v4_media_job_schema VALUES ('media_jobs',1)"
            )
            connection.execute(
                "CREATE TABLE v4_media_jobs ("
                "workspace_ref TEXT NOT NULL,"
                "production_run_ref TEXT NOT NULL,"
                "job_ref TEXT NOT NULL,"
                "idempotency_key TEXT NOT NULL,"
                "request_digest TEXT NOT NULL,"
                "state TEXT NOT NULL,"
                "revision INTEGER NOT NULL,"
                "payload_json TEXT NOT NULL,"
                "PRIMARY KEY(workspace_ref,production_run_ref,job_ref),"
                "UNIQUE(workspace_ref,production_run_ref,idempotency_key))"
            )
            connection.commit()
        finally:
            connection.close()

    def test_exact_v1_schema_migrates_once_to_batch_reservation_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            self._create_legacy_v1(path)
            SqliteMediaJobAdapter(path)
            SqliteMediaJobAdapter(path)
            connection = sqlite3.connect(path)
            try:
                marker = connection.execute(
                    "SELECT component,schema_version FROM v4_media_job_schema"
                ).fetchall()
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(marker, [("media_jobs", 2)])
            self.assertEqual(
                tables,
                {
                    "v4_media_job_schema",
                    "v4_media_jobs",
                    "v4_media_job_batches",
                },
            )

    def test_same_columns_without_exact_constraints_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "relaxed.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE v4_media_job_schema ("
                    "component TEXT, schema_version INTEGER)"
                )
                connection.execute(
                    "INSERT INTO v4_media_job_schema VALUES ('media_jobs',1)"
                )
                connection.execute(
                    "CREATE TABLE v4_media_jobs ("
                    "workspace_ref TEXT NOT NULL,"
                    "production_run_ref TEXT NOT NULL,"
                    "job_ref TEXT NOT NULL,"
                    "idempotency_key TEXT NOT NULL,"
                    "request_digest TEXT NOT NULL,"
                    "state TEXT NOT NULL,"
                    "revision INTEGER NOT NULL,"
                    "payload_json TEXT NOT NULL)"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(MediaJobError):
                SqliteMediaJobAdapter(path)
            connection = sqlite3.connect(path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()
            self.assertNotIn("v4_media_job_batches", tables)

    def test_unexpected_index_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra-index.sqlite3"
            SqliteMediaJobAdapter(path)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE INDEX unexpected_media_state "
                    "ON v4_media_jobs(state)"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(MediaJobError):
                SqliteMediaJobAdapter(path, initialize_if_missing=False)


class V4DurablePublicationR1Tests(unittest.TestCase):
    def test_durable_replace_publishes_one_exact_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            payload = b"durable publication payload"
            source.write_bytes(payload)
            source_inode = source.stat().st_ino

            self.assertEqual(
                store.durable_replace(source, destination),
                destination,
            )

            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(destination.stat().st_ino, source_inode)
            self.assertEqual(destination.stat().st_nlink, 1)

    def test_parent_rename_with_inode_alias_is_rejected_by_link_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            payload = b"one exact durable publication candidate"
            source.write_bytes(payload)

            jobs_parent = run_root / "jobs"
            moved_jobs = Path(directory) / "moved-jobs"
            replacement_jobs = Path(directory) / "replacement-jobs"
            replacement_parent = replacement_jobs / "request" / "job"
            replacement_parent.mkdir(parents=True)
            original_link = os.link
            renamed = False

            def rename_parent_before_link(source_path, destination_path, **kwargs):
                nonlocal renamed
                if not renamed:
                    renamed = True
                    os.rename(jobs_parent, moved_jobs)
                    original_source = moved_jobs / "request" / "job" / source.name
                    original_link(original_source, replacement_parent / source.name)
                    os.symlink(replacement_jobs, jobs_parent)
                return original_link(source_path, destination_path, **kwargs)

            with mock.patch(
                "services.v4_platform.artifact_recovery.os.link",
                side_effect=rename_parent_before_link,
            ):
                with self.assertRaisesRegex(
                    ArtifactRecoveryStoreError,
                    "artifact changed during no-clobber publication",
                ):
                    store.durable_replace(source, destination)

            moved_source = moved_jobs / "request" / "job" / source.name
            aliased_source = replacement_parent / source.name
            self.assertEqual(moved_source.read_bytes(), payload)
            self.assertEqual(
                moved_source.stat().st_ino,
                aliased_source.stat().st_ino,
            )
            self.assertEqual(moved_source.stat().st_nlink, 2)
            self.assertEqual(aliased_source.stat().st_nlink, 2)
            self.assertFalse((replacement_parent / destination.name).exists())

    def test_parent_rename_immediately_after_link_restores_single_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            payload = b"restore candidate after linked parent rename"
            source.write_bytes(payload)

            jobs_parent = run_root / "jobs"
            moved_jobs = Path(directory) / "moved-jobs"
            replacement_jobs = Path(directory) / "replacement-jobs"
            (replacement_jobs / "request" / "job").mkdir(parents=True)
            original_link = os.link
            renamed = False

            def rename_parent_after_link(source_path, destination_path, **kwargs):
                nonlocal renamed
                result = original_link(source_path, destination_path, **kwargs)
                if not renamed:
                    renamed = True
                    os.rename(jobs_parent, moved_jobs)
                    os.symlink(replacement_jobs, jobs_parent)
                return result

            with mock.patch(
                "services.v4_platform.artifact_recovery.os.link",
                side_effect=rename_parent_after_link,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.durable_replace(source, destination)

            moved_parent = moved_jobs / "request" / "job"
            restored_source = moved_parent / source.name
            self.assertEqual(restored_source.read_bytes(), payload)
            self.assertEqual(restored_source.stat().st_nlink, 1)
            self.assertFalse((moved_parent / destination.name).exists())
            self.assertEqual(
                list((replacement_jobs / "request" / "job").iterdir()),
                [],
            )

    def test_parent_rename_after_source_unlink_restores_single_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            payload = b"restore candidate after parent rename"
            source.write_bytes(payload)

            jobs_parent = run_root / "jobs"
            moved_jobs = Path(directory) / "moved-jobs"
            replacement_jobs = Path(directory) / "replacement-jobs"
            (replacement_jobs / "request" / "job").mkdir(parents=True)
            original_binding_check = store._assert_directory_binding
            parent_binding_checks = 0

            def rename_after_unlink(root_fd, parts, expected_fd):
                nonlocal parent_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts)[-3:] == ("jobs", "request", "job"):
                    parent_binding_checks += 1
                    if parent_binding_checks == 7:
                        os.rename(jobs_parent, moved_jobs)
                        os.symlink(replacement_jobs, jobs_parent)
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=rename_after_unlink,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.durable_replace(source, destination)

            moved_parent = moved_jobs / "request" / "job"
            restored_source = moved_parent / source.name
            self.assertEqual(restored_source.read_bytes(), payload)
            self.assertEqual(restored_source.stat().st_nlink, 1)
            self.assertFalse((moved_parent / destination.name).exists())
            self.assertEqual(
                list((replacement_jobs / "request" / "job").iterdir()),
                [],
            )

    def test_complete_linked_publication_converges_to_one_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            candidate = publication_parent / "candidate.part.mp4"
            final = publication_parent / "final.mp4"
            payload = b"interrupted publication payload"
            candidate.write_bytes(payload)
            os.link(candidate, final)
            candidate_inode = candidate.stat().st_ino

            self.assertEqual(
                store.complete_linked_publication(candidate, final),
                final,
            )

            self.assertFalse(candidate.exists())
            self.assertEqual(final.read_bytes(), payload)
            self.assertEqual(final.stat().st_ino, candidate_inode)
            self.assertEqual(final.stat().st_nlink, 1)

    def test_complete_linked_publication_parent_rename_restores_two_links(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            candidate = publication_parent / "candidate.part.mp4"
            final = publication_parent / "final.mp4"
            payload = b"restore interrupted publication after parent rename"
            candidate.write_bytes(payload)
            os.link(candidate, final)

            jobs_parent = run_root / "jobs"
            moved_jobs = Path(directory) / "moved-jobs"
            replacement_jobs = Path(directory) / "replacement-jobs"
            (replacement_jobs / "request" / "job").mkdir(parents=True)
            original_binding_check = store._assert_directory_binding
            parent_binding_checks = 0

            def rename_after_candidate_unlink(root_fd, parts, expected_fd):
                nonlocal parent_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts)[-3:] == ("jobs", "request", "job"):
                    parent_binding_checks += 1
                    if parent_binding_checks == 5:
                        os.rename(jobs_parent, moved_jobs)
                        os.symlink(replacement_jobs, jobs_parent)
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=rename_after_candidate_unlink,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.complete_linked_publication(candidate, final)

            moved_parent = moved_jobs / "request" / "job"
            restored_candidate = moved_parent / candidate.name
            restored_final = moved_parent / final.name
            self.assertEqual(restored_candidate.read_bytes(), payload)
            self.assertEqual(restored_final.read_bytes(), payload)
            self.assertEqual(
                restored_candidate.stat().st_ino,
                restored_final.stat().st_ino,
            )
            self.assertEqual(restored_candidate.stat().st_nlink, 2)
            self.assertEqual(restored_final.stat().st_nlink, 2)
            self.assertEqual(
                list((replacement_jobs / "request" / "job").iterdir()),
                [],
            )

    def test_final_destination_binding_rename_restores_durable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source_parent = run_root / "jobs" / "source"
            destination_parent = run_root / "published"
            source_parent.mkdir(parents=True)
            destination_parent.mkdir()
            source = source_parent / "candidate.part.mp4"
            destination = destination_parent / "final.mp4"
            payload = b"restore source after final destination binding rename"
            source.write_bytes(payload)

            detached_parent = Path(directory) / "detached-published"
            destination_parts = destination_parent.relative_to(store.root).parts
            original_binding_check = store._assert_directory_binding
            destination_binding_checks = 0

            def rename_after_final_destination_check(root_fd, parts, expected_fd):
                nonlocal destination_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts) == destination_parts:
                    destination_binding_checks += 1
                    if destination_binding_checks == 5:
                        os.rename(destination_parent, detached_parent)
                        destination_parent.mkdir()
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=rename_after_final_destination_check,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.durable_replace(source, destination)

            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(destination_parent.iterdir()), [])
            self.assertEqual(list(detached_parent.iterdir()), [])

    def test_final_absolute_file_binding_rejects_same_parent_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            detached_destination = publication_parent / "detached-final.mp4"
            payload = b"original final publication bytes"
            replacement = b"concurrent replacement bytes"
            source.write_bytes(payload)
            original_binding_check = store._assert_absolute_regular_file_binding
            replaced = False

            def replace_before_final_absolute_open(path, **kwargs):
                nonlocal replaced
                if not replaced:
                    replaced = True
                    os.rename(destination, detached_destination)
                    destination.write_bytes(replacement)
                return original_binding_check(path, **kwargs)

            with mock.patch.object(
                store,
                "_assert_absolute_regular_file_binding",
                side_effect=replace_before_final_absolute_open,
            ):
                with self.assertRaisesRegex(
                    ArtifactRecoveryStoreError,
                    "absolute namespace binding",
                ):
                    store.durable_replace(source, destination)

            self.assertEqual(detached_destination.read_bytes(), payload)
            self.assertEqual(detached_destination.stat().st_nlink, 1)
            self.assertEqual(destination.read_bytes(), replacement)
            self.assertEqual(destination.stat().st_nlink, 1)

    def test_full_path_linearization_catches_parent_rename_before_openat2(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source_parent = run_root / "jobs" / "source"
            destination_parent = run_root / "published"
            source_parent.mkdir(parents=True)
            destination_parent.mkdir()
            source = source_parent / "candidate.part.mp4"
            destination = destination_parent / "final.mp4"
            payload = b"full path final binding payload"
            source.write_bytes(payload)

            detached_parent = Path(directory) / "detached-published"
            original_openat2 = store._openat2_no_symlinks
            observed_paths = []

            def rename_before_full_path_open(base_fd, relative_path, flags):
                observed_paths.append(relative_path)
                os.rename(destination_parent, detached_parent)
                destination_parent.mkdir()
                return original_openat2(base_fd, relative_path, flags)

            with mock.patch.object(
                store,
                "_openat2_no_symlinks",
                side_effect=rename_before_full_path_open,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.durable_replace(source, destination)

            self.assertEqual(
                observed_paths,
                [destination.relative_to(Path(os.sep)).as_posix()],
            )
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(destination_parent.iterdir()), [])
            self.assertEqual(list(detached_parent.iterdir()), [])

    def test_openat2_unavailable_fails_closed_and_restores_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            publication_parent = run_root / "jobs" / "request" / "job"
            publication_parent.mkdir(parents=True)
            source = publication_parent / "candidate.part.mp4"
            destination = publication_parent / "final.mp4"
            payload = b"restore source when openat2 is unavailable"
            source.write_bytes(payload)

            with mock.patch.object(
                store,
                "_openat2_no_symlinks",
                side_effect=OSError(errno.ENOSYS, "openat2 unavailable"),
            ):
                with self.assertRaisesRegex(
                    ArtifactRecoveryStoreError,
                    "required openat2 artifact binding is unavailable",
                ):
                    store.durable_replace(source, destination)

            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertFalse(destination.exists())

    def test_openat2_rejects_nul_in_relative_path_before_syscall(self):
        slash_fd = os.open(os.sep, ArtifactRecoveryStore._directory_open_flags())
        try:
            with self.assertRaises(OSError) as raised:
                ArtifactRecoveryStore._openat2_no_symlinks(
                    slash_fd,
                    "tmp/final.mp4\0ignored",
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
            self.assertEqual(raised.exception.errno, errno.EINVAL)
        finally:
            os.close(slash_fd)

    def test_final_destination_binding_rename_restores_interrupted_links(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            candidate_parent = run_root / "jobs" / "source"
            final_parent = run_root / "published"
            candidate_parent.mkdir(parents=True)
            final_parent.mkdir()
            candidate = candidate_parent / "candidate.part.mp4"
            final = final_parent / "final.mp4"
            payload = b"restore linked publication after final binding rename"
            candidate.write_bytes(payload)
            os.link(candidate, final)

            detached_parent = Path(directory) / "detached-published"
            final_parts = final_parent.relative_to(store.root).parts
            original_binding_check = store._assert_directory_binding
            destination_binding_checks = 0

            def rename_after_final_destination_check(root_fd, parts, expected_fd):
                nonlocal destination_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts) == final_parts:
                    destination_binding_checks += 1
                    if destination_binding_checks == 4:
                        os.rename(final_parent, detached_parent)
                        final_parent.mkdir()
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=rename_after_final_destination_check,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.complete_linked_publication(candidate, final)

            detached_final = detached_parent / final.name
            self.assertEqual(candidate.read_bytes(), payload)
            self.assertEqual(detached_final.read_bytes(), payload)
            self.assertEqual(
                candidate.stat().st_ino,
                detached_final.stat().st_ino,
            )
            self.assertEqual(candidate.stat().st_nlink, 2)
            self.assertEqual(detached_final.stat().st_nlink, 2)
            self.assertEqual(list(final_parent.iterdir()), [])


class V4QuarantineR1Tests(unittest.TestCase):
    def test_final_destination_binding_rename_restores_quarantine_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "final-binding.part.mp4"
            source.parent.mkdir(parents=True)
            payload = b"restore quarantine source after final binding rename"
            source.write_bytes(payload)
            storage_key = store.storage_key(source)
            destination_parent = run_root / "quarantine" / "recovery"
            detached_parent = Path(directory) / "detached-quarantine"
            destination_parts = destination_parent.relative_to(store.root).parts
            original_binding_check = store._assert_directory_binding
            destination_binding_checks = 0

            def rename_after_final_destination_check(root_fd, parts, expected_fd):
                nonlocal destination_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts) == destination_parts:
                    destination_binding_checks += 1
                    if destination_binding_checks == 4:
                        os.rename(destination_parent, detached_parent)
                        destination_parent.mkdir()
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=rename_after_final_destination_check,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="final-destination-binding-rename",
                    )

            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(destination_parent.iterdir()), [])
            self.assertEqual(list(detached_parent.iterdir()), [])

    def test_directory_binding_cleanup_preserves_primary_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            expected = root / "expected"
            child.mkdir()
            expected.mkdir()
            root_fd = os.open(
                root,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            expected_fd = os.open(
                expected,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            child_stat = child.stat()
            original_close = os.close
            failed_descriptor = None

            def fail_child_descriptor_close(descriptor):
                nonlocal failed_descriptor
                opened = os.fstat(descriptor)
                if (
                    opened.st_dev == child_stat.st_dev
                    and opened.st_ino == child_stat.st_ino
                ):
                    failed_descriptor = descriptor
                    raise OSError("injected binding descriptor close failure")
                return original_close(descriptor)

            try:
                with mock.patch(
                    "services.v4_platform.artifact_recovery.os.close",
                    side_effect=fail_child_descriptor_close,
                ):
                    with self.assertRaisesRegex(
                        ArtifactRecoveryStoreError,
                        "artifact directory binding changed",
                    ) as raised:
                        ArtifactRecoveryStore._assert_directory_binding(
                            root_fd,
                            ("child",),
                            expected_fd,
                        )
                self.assertTrue(
                    any(
                        "binding descriptor cleanup also failed" in note
                        for note in getattr(raised.exception, "__notes__", [])
                    )
                )
            finally:
                if failed_descriptor is not None:
                    original_close(failed_descriptor)
                original_close(expected_fd)
                original_close(root_fd)

    def test_directory_chain_creation_failure_does_not_leak_descriptor(self):
        if not Path("/proc/self/fd").is_dir():
            self.skipTest("descriptor inventory requires Linux /proc")
        with tempfile.TemporaryDirectory() as directory:
            base_fd = os.open(
                directory,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            before = len(tuple(Path("/proc/self/fd").iterdir()))
            original_fsync = os.fsync
            fsync_calls = 0

            def fail_new_directory_fsync(descriptor):
                nonlocal fsync_calls
                fsync_calls += 1
                if fsync_calls == 2:
                    raise OSError("injected new-directory fsync failure")
                return original_fsync(descriptor)

            try:
                with mock.patch(
                    "services.v4_platform.artifact_recovery.os.fsync",
                    side_effect=fail_new_directory_fsync,
                ):
                    with self.assertRaisesRegex(
                        OSError, "injected new-directory fsync failure"
                    ):
                        ArtifactRecoveryStore._open_directory_chain(
                            base_fd,
                            ("new-child",),
                            create=True,
                        )
                self.assertEqual(
                    len(tuple(Path("/proc/self/fd").iterdir())),
                    before,
                )
            finally:
                os.close(base_fd)

    def test_two_concurrent_claims_converge_to_one_safe_quarantine_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "orphan.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"one exact orphan")
            storage_key = store.storage_key(source)
            original_link = os.link
            original_flock = fcntl.flock
            first_linked = Event()
            release_first = Event()
            second_lock_attempted = Event()
            lock_counter_guard = Lock()
            exclusive_lock_calls = 0

            def racing_link(source_path, destination_path, **kwargs):
                original_link(source_path, destination_path, **kwargs)
                first_linked.set()
                if not release_first.wait(timeout=5):
                    raise TimeoutError("first quarantine claim was not released")

            def observed_flock(fd, operation):
                nonlocal exclusive_lock_calls
                if operation == fcntl.LOCK_EX:
                    with lock_counter_guard:
                        exclusive_lock_calls += 1
                        if exclusive_lock_calls == 2:
                            second_lock_attempted.set()
                return original_flock(fd, operation)

            with mock.patch(
                "services.v4_platform.artifact_recovery.os.link",
                side_effect=racing_link,
            ), mock.patch(
                "services.v4_platform.artifact_recovery.fcntl.flock",
                side_effect=observed_flock,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(
                        store.quarantine,
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="concurrent-claim",
                    )
                    self.assertTrue(first_linked.wait(timeout=5))
                    second = executor.submit(
                        store.quarantine,
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="concurrent-claim",
                    )
                    self.assertTrue(second_lock_attempted.wait(timeout=5))
                    release_first.set()
                    results = [first.result(timeout=10), second.result(timeout=10)]
            self.assertEqual(
                len({result["storageKey"] for result in results}), 1
            )
            destination = store.path_from_storage_key(results[0]["storageKey"])
            self.assertFalse(source.exists())
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.stat().st_nlink, 1)
            self.assertTrue(
                any(result["idempotentReplay"] for result in results)
            )

    def test_two_distinct_concurrent_claims_are_serialized_first_reason_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "two-claims.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"one exact orphan")
            storage_key = store.storage_key(source)
            original_link = os.link
            original_flock = fcntl.flock
            first_linked = Event()
            release_first = Event()
            second_lock_attempted = Event()
            lock_counter_guard = Lock()
            exclusive_lock_calls = 0

            def racing_link(source_path, destination_path, **kwargs):
                original_link(source_path, destination_path, **kwargs)
                first_linked.set()
                if not release_first.wait(timeout=5):
                    raise TimeoutError("first quarantine claim was not released")

            def observed_flock(fd, operation):
                nonlocal exclusive_lock_calls
                if operation == fcntl.LOCK_EX:
                    with lock_counter_guard:
                        exclusive_lock_calls += 1
                        if exclusive_lock_calls == 2:
                            second_lock_attempted.set()
                return original_flock(fd, operation)

            def claim(reason):
                return store.quarantine(
                    RECOVERY_WORKSPACE,
                    RUN,
                    storage_key,
                    category="recovery",
                    reason=reason,
                )

            with mock.patch(
                "services.v4_platform.artifact_recovery.os.link",
                side_effect=racing_link,
            ), mock.patch(
                "services.v4_platform.artifact_recovery.fcntl.flock",
                side_effect=observed_flock,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(claim, "first-claim")
                    self.assertTrue(first_linked.wait(timeout=5))
                    second = executor.submit(claim, "second-claim")
                    self.assertTrue(second_lock_attempted.wait(timeout=5))
                    release_first.set()
                    winner = first.result(timeout=10)
                    with self.assertRaises(ArtifactRecoveryStoreError):
                        second.result(timeout=10)

            self.assertFalse(source.exists())
            self.assertEqual(winner["quarantineReason"], "first-claim")
            destinations = list(run_root.glob("quarantine/**/*.mp4"))
            self.assertEqual(len(destinations), 1)
            self.assertEqual(destinations[0].stat().st_nlink, 1)

    def test_failed_new_claim_rolls_back_the_destination_link(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "rollback.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"rollback exact orphan")
            storage_key = store.storage_key(source)

            with mock.patch.object(
                store,
                "_sync_locked_file",
                side_effect=ArtifactRecoveryStoreError(
                    "injected destination fsync"
                ),
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="rollback-claim",
                    )
            self.assertTrue(source.is_file())
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(run_root.glob("quarantine/**/*.mp4")), [])

    def test_source_replacement_before_claim_is_rejected_without_moving_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "replaced.part.mp4"
            replacement = run_root / "jobs" / "replacement.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"original orphan")
            replacement.write_bytes(b"replacement bytes")
            storage_key = store.storage_key(source)
            original_flock = fcntl.flock
            replaced = False

            def replace_after_lock(descriptor, operation):
                nonlocal replaced
                result = original_flock(descriptor, operation)
                if operation == fcntl.LOCK_EX and not replaced:
                    replaced = True
                    os.replace(replacement, source)
                return result

            with mock.patch(
                "services.v4_platform.artifact_recovery.fcntl.flock",
                side_effect=replace_after_lock,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="replace-before-claim",
                    )
            self.assertEqual(source.read_bytes(), b"replacement bytes")
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(run_root.glob("quarantine/**/*.mp4")), [])

    def test_late_concurrent_claim_observes_the_completed_atomic_move(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "late-claim.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"late concurrent claim")
            storage_key = store.storage_key(source)
            reason = "late-concurrent-claim"
            key_hash = sha256(
                f"{storage_key}\0recovery\0{reason}".encode("utf-8")
            ).hexdigest()[:24]
            destination = (
                run_root
                / "quarantine"
                / "recovery"
                / f"artifact-{key_hash}.mp4"
            )
            original_fsync = store._sync_locked_file
            completed = False

            def finish_other_claim(descriptor):
                nonlocal completed
                if not completed:
                    completed = True
                    os.unlink(source)
                return original_fsync(descriptor)

            with mock.patch.object(
                store,
                "_sync_locked_file",
                side_effect=finish_other_claim,
            ):
                result = store.quarantine(
                    RECOVERY_WORKSPACE,
                    RUN,
                    storage_key,
                    category="recovery",
                    reason=reason,
                )
            self.assertTrue(result["idempotentReplay"])
            self.assertEqual(
                store.path_from_storage_key(result["storageKey"]),
                destination,
            )
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"late concurrent claim")
            self.assertEqual(destination.stat().st_nlink, 1)

    def test_lock_open_race_falls_back_to_same_reason_replay_target(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "open-race.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"open race replay")
            storage_key = store.storage_key(source)
            reason = "open-race-replay"
            key_hash = sha256(
                f"{storage_key}\0recovery\0{reason}".encode("utf-8")
            ).hexdigest()[:24]
            destination = (
                run_root
                / "quarantine"
                / "recovery"
                / f"artifact-{key_hash}.mp4"
            )
            destination.parent.mkdir(parents=True)
            original_open = os.open
            moved = False

            def finish_move_before_source_open(path, flags, *args, **kwargs):
                nonlocal moved
                if path == source.name and not moved:
                    moved = True
                    os.link(source, destination)
                    os.unlink(source)
                    raise FileNotFoundError(source)
                return original_open(path, flags, *args, **kwargs)

            with mock.patch(
                "services.v4_platform.artifact_recovery.os.open",
                side_effect=finish_move_before_source_open,
            ):
                replay = store.quarantine(
                    RECOVERY_WORKSPACE,
                    RUN,
                    storage_key,
                    category="recovery",
                    reason=reason,
                )

            self.assertTrue(replay["idempotentReplay"])
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"open race replay")
            self.assertEqual(destination.stat().st_nlink, 1)

    def test_lock_cleanup_failure_preserves_primary_store_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "cleanup-error.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"cleanup error")
            storage_key = store.storage_key(source)
            original_flock = fcntl.flock
            original_close = os.close
            locked_descriptor = None

            def remember_lock(descriptor, operation):
                nonlocal locked_descriptor
                if operation == fcntl.LOCK_EX:
                    locked_descriptor = descriptor
                return original_flock(descriptor, operation)

            def fail_locked_close(descriptor):
                if descriptor == locked_descriptor:
                    raise OSError("injected descriptor close failure")
                return original_close(descriptor)

            with mock.patch.object(
                store,
                "_sync_locked_file",
                side_effect=ArtifactRecoveryStoreError("primary store error"),
            ), mock.patch(
                "services.v4_platform.artifact_recovery.fcntl.flock",
                side_effect=remember_lock,
            ), mock.patch(
                "services.v4_platform.artifact_recovery.os.close",
                side_effect=fail_locked_close,
            ):
                with self.assertRaisesRegex(
                    ArtifactRecoveryStoreError, "primary store error"
                ) as raised:
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="cleanup-error",
                    )

            self.assertTrue(
                any(
                    "descriptor cleanup also failed" in note
                    for note in getattr(raised.exception, "__notes__", [])
                )
            )
            if locked_descriptor is not None:
                original_close(locked_descriptor)

    def test_parent_namespace_swap_is_rejected_without_following_decoy(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "namespace-swap.part.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"original scoped artifact")
            storage_key = store.storage_key(source)
            moved_parent = store.root / "moved-outside-run"
            decoy_parent = Path(directory) / "untrusted-decoy"
            decoy_parent.mkdir()
            decoy = decoy_parent / source.name
            decoy.write_bytes(b"must remain untouched")
            original_binding_check = store._assert_directory_binding
            source_binding_checks = 0

            def swap_after_first_source_binding(
                root_fd,
                parts,
                expected_fd,
            ):
                nonlocal source_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts)[-1:] == ("jobs",):
                    source_binding_checks += 1
                    if source_binding_checks == 1:
                        os.rename(source.parent, moved_parent)
                        os.symlink(decoy_parent, source.parent)
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=swap_after_first_source_binding,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="namespace-swap",
                    )

            moved_source = moved_parent / source.name
            self.assertEqual(moved_source.read_bytes(), b"original scoped artifact")
            self.assertEqual(decoy.read_bytes(), b"must remain untouched")
            self.assertEqual(list(run_root.glob("quarantine/**/*.mp4")), [])

    def test_destination_swap_at_commit_is_rejected_and_source_is_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "destination-swap.part.mp4"
            source.parent.mkdir(parents=True)
            payload = b"restore exact source after destination namespace swap"
            source.write_bytes(payload)
            storage_key = store.storage_key(source)
            destination_parent = run_root / "quarantine" / "recovery"
            moved_parent = store.root / "moved-quarantine-parent"
            decoy_parent = Path(directory) / "untrusted-quarantine-decoy"
            decoy_parent.mkdir()
            original_binding_check = store._assert_directory_binding
            destination_binding_checks = 0

            def swap_after_pre_unlink_destination_check(
                root_fd,
                parts,
                expected_fd,
            ):
                nonlocal destination_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts)[-2:] == ("quarantine", "recovery"):
                    destination_binding_checks += 1
                    if destination_binding_checks == 2:
                        os.rename(destination_parent, moved_parent)
                        os.symlink(decoy_parent, destination_parent)
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=swap_after_pre_unlink_destination_check,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="destination-namespace-swap",
                    )

            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_nlink, 1)
            self.assertEqual(list(moved_parent.glob("*.mp4")), [])
            self.assertEqual(list(decoy_parent.glob("*.mp4")), [])

    def test_artifact_root_swap_at_commit_is_rejected_and_source_is_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactRecoveryStore(Path(directory) / "artifacts")
            run_root = store.run_root(RECOVERY_WORKSPACE, RUN)
            source = run_root / "jobs" / "root-swap.part.mp4"
            source.parent.mkdir(parents=True)
            payload = b"restore exact source after artifact root swap"
            source.write_bytes(payload)
            storage_key = store.storage_key(source)
            original_root = store.root
            moved_root = Path(directory) / "moved-artifact-root"
            original_binding_check = store._assert_directory_binding
            destination_binding_checks = 0

            def swap_root_after_pre_unlink_destination_check(
                root_fd,
                parts,
                expected_fd,
            ):
                nonlocal destination_binding_checks
                result = original_binding_check(root_fd, parts, expected_fd)
                if tuple(parts)[-2:] == ("quarantine", "recovery"):
                    destination_binding_checks += 1
                    if destination_binding_checks == 2:
                        os.rename(original_root, moved_root)
                        original_root.mkdir()
                return result

            with mock.patch.object(
                store,
                "_assert_directory_binding",
                side_effect=swap_root_after_pre_unlink_destination_check,
            ):
                with self.assertRaises(ArtifactRecoveryStoreError):
                    store.quarantine(
                        RECOVERY_WORKSPACE,
                        RUN,
                        storage_key,
                        category="recovery",
                        reason="artifact-root-swap",
                    )

            moved_source = moved_root.joinpath(*source.relative_to(original_root).parts)
            self.assertEqual(moved_source.read_bytes(), payload)
            self.assertEqual(moved_source.stat().st_nlink, 1)
            self.assertEqual(list(original_root.rglob("*.mp4")), [])
            self.assertEqual(list(moved_root.glob("**/quarantine/**/*.mp4")), [])


if __name__ == "__main__":
    unittest.main()
