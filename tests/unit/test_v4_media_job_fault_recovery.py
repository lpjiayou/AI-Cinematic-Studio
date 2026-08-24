from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from services.v4_platform import (
    ArtifactVerificationError,
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    MediaJobError,
    MediaJobStateError,
    SqliteMediaJobAdapter,
)


WORKSPACE = "workspace-v4-recovery"
RUN = "production-run-v4-recovery"


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def request():
    value = {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "generationRequestRef": "generation-request-v4-recovery",
        "generationRequestVersionRef": "generation-request-version-v4-recovery-v1",
        "assetRequirementRef": "asset-requirement-v4-recovery",
        "creativeShotRef": "creative-shot-v4-recovery",
        "creativeShotVersionRef": "creative-shot-version-v4-recovery-v1",
        "mediaKind": "video",
        "mediaType": "video/mp4",
        "adapterCapability": "deterministic-local-ffmpeg-v1",
        "parameters": {
            "durationFrames": 24,
            "frameRate": 24,
            "width": 64,
            "height": 64,
            "visualSeedDigest": "123456" + "0" * 58,
        },
        "state": "READY_FOR_DISPATCH",
        "requestedProvenance": "LOCAL_EVIDENCE",
        "publicationAllowed": False,
    }
    value["payloadDigest"] = sha256(_canonical(value)).hexdigest()
    return value


class MutableClock:
    def __init__(self):
        self.value = "2026-08-24T00:00:00Z"

    def __call__(self):
        return self.value


class Refs:
    def __init__(self):
        self.counter = 0

    def __call__(self, prefix):
        self.counter += 1
        return f"{prefix}-recovery-{self.counter:04d}"


class InjectedProcessCrash(BaseException):
    pass


class CrashOnSucceededSave:
    """Let PREPARED intent persist, then simulate process death at final CAS."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.crashed = False

    def create(self, job):
        return self.delegate.create(job)

    def get(self, workspace_ref, run_ref, job_ref):
        return self.delegate.get(workspace_ref, run_ref, job_ref)

    def list(self, workspace_ref, run_ref):
        return self.delegate.list(workspace_ref, run_ref)

    def save(self, job, expected_revision):
        if job["state"] == "SUCCEEDED" and not self.crashed:
            self.crashed = True
            raise InjectedProcessCrash("final published; success CAS not persisted")
        return self.delegate.save(job, expected_revision)


class CountingAdapter:
    adapter_identity = DeterministicLocalFfmpegAdapter.adapter_identity
    provenance = DeterministicLocalFfmpegAdapter.provenance

    def __init__(self):
        self.calls = 0
        self.delegate = DeterministicLocalFfmpegAdapter()

    def generate(self, generation_request, candidate_path):
        self.calls += 1
        return self.delegate.generate(generation_request, candidate_path)


class V4MediaJobFaultRecoveryTests(unittest.TestCase):
    def test_deleted_artifact_root_fails_closed_with_domain_error(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "artifacts"
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                artifacts,
                ref_factory=Refs(),
                clock=MutableClock(),
            )
            created, _ = coordinator.dispatch(
                request(), idempotency_key="deleted-artifact-root"
            )
            leased = coordinator.lease_next(WORKSPACE, RUN, "worker-root-gone")
            self.assertEqual(leased["jobRef"], created["jobRef"])
            artifacts.rmdir()

            with self.assertRaises(MediaJobError) as raised:
                coordinator.run_leased(leased, "worker-root-gone")

            self.assertIn("artifact root became unavailable", str(raised.exception))

    def _crash_after_publish(self, directory, *, max_attempts=1):
        database = Path(directory) / "jobs.sqlite3"
        artifacts = Path(directory) / "artifacts"
        clock = MutableClock()
        refs = Refs()
        durable = SqliteMediaJobAdapter(database)
        crashing = CrashOnSucceededSave(durable)
        adapter = CountingAdapter()
        coordinator = MediaJobCoordinator(
            crashing,
            adapter,
            artifacts,
            ref_factory=refs,
            clock=clock,
            lease_seconds=10,
            max_attempts=max_attempts,
        )
        created, _ = coordinator.dispatch(request(), idempotency_key="recover-final")
        leased = coordinator.lease_next(WORKSPACE, RUN, "worker-before-crash")
        with self.assertRaises(InjectedProcessCrash):
            coordinator.run_leased(leased, "worker-before-crash")
        stored = durable.get(WORKSPACE, RUN, created["jobRef"])
        self.assertEqual(stored["state"], "RUNNING")
        self.assertEqual(stored["attempts"][-1]["state"], "RUNNING")
        self.assertIsNotNone(stored["artifactCommitIntent"])
        final_path = artifacts / stored["artifactCommitIntent"]["finalStorageKey"]
        self.assertTrue(final_path.is_file())
        self.assertEqual(adapter.calls, 1)
        return database, artifacts, clock, refs, adapter, stored, final_path

    def test_exact_final_is_adopted_after_publish_to_success_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, stored, final_path = (
                self._crash_after_publish(directory)
            )
            expected_digest = sha256(final_path.read_bytes()).hexdigest()
            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            recovered = restored.recover_expired(WORKSPACE, RUN)
            self.assertEqual(len(recovered), 1)
            adopted = recovered[0]
            self.assertEqual(adopted["state"], "SUCCEEDED")
            self.assertIsNone(adopted["artifactCommitIntent"])
            self.assertEqual(adopted["artifact"]["sha256"], expected_digest)
            self.assertTrue(
                adopted["attempts"][-1]["recoveredFromCommitIntent"]
            )
            self.assertEqual(len(adopted["attempts"]), 1)
            self.assertEqual(adapter.calls, 1)
            revision = adopted["revision"]
            self.assertEqual(restored.recover_expired(WORKSPACE, RUN), [])
            replay = restored.list_jobs(WORKSPACE, RUN)[0]
            self.assertEqual(replay["revision"], revision)
            self.assertEqual(len(replay["attempts"]), 1)

            late_candidate = artifacts / stored["artifactCommitIntent"][
                "candidateStorageKey"
            ]
            late_candidate.write_bytes(b"late-unreferenced-candidate")
            by_key = {
                item["storageKey"]: item
                for item in restored.inventory_orphan_artifacts(WORKSPACE, RUN)
            }
            late_key = late_candidate.relative_to(artifacts).as_posix()
            self.assertEqual(by_key[late_key]["inventoryState"], "ORPHAN")

    def test_mismatched_final_is_quarantined_and_budget_is_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, stored, final_path = (
                self._crash_after_publish(directory)
            )
            final_path.write_bytes(b"tampered-final")
            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            recovered = restored.recover_expired(WORKSPACE, RUN)
            self.assertEqual(len(recovered), 1)
            failed = recovered[0]
            self.assertEqual(failed["state"], "FAILED")
            self.assertEqual(
                failed["attempts"][-1]["errorCode"],
                "artifact_recovery_mismatch",
            )
            self.assertEqual(len(failed["attempts"]), 1)
            self.assertFalse(final_path.exists())
            quarantined = failed["attempts"][-1]["quarantineStorageKeys"]
            self.assertEqual(len(quarantined), 1)
            self.assertTrue((artifacts / quarantined[0]).is_file())
            self.assertIsNone(restored.lease_next(WORKSPACE, RUN, "worker-too-late"))
            self.assertEqual(restored.recover_expired(WORKSPACE, RUN), [])

    def test_cleanup_claim_survives_a_second_recovery_crash(self):
        class CrashAfterCleanupClaim:
            def __init__(self, delegate):
                self.delegate = delegate
                self.crashed = False

            def create(self, job):
                return self.delegate.create(job)

            def get(self, workspace_ref, run_ref, job_ref):
                return self.delegate.get(workspace_ref, run_ref, job_ref)

            def list(self, workspace_ref, run_ref):
                return self.delegate.list(workspace_ref, run_ref)

            def save(self, job, expected_revision):
                if (
                    not self.crashed
                    and job["state"] == "FAILED"
                    and job.get("artifactCommitIntent") is not None
                    and job["attempts"][-1].get("errorCode")
                    == "artifact_recovery_mismatch"
                ):
                    self.crashed = True
                    self.delegate.save(job, expected_revision)
                    raise InjectedProcessCrash("cleanup claim persisted")
                return self.delegate.save(job, expected_revision)

        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, _, final_path = (
                self._crash_after_publish(directory)
            )
            final_path.write_bytes(b"mismatch-before-cleanup-claim")
            clock.value = "2026-08-24T00:00:11Z"
            interrupted = MediaJobCoordinator(
                CrashAfterCleanupClaim(SqliteMediaJobAdapter(database)),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            with self.assertRaises(InjectedProcessCrash):
                interrupted.recover_expired(WORKSPACE, RUN)
            claimed = SqliteMediaJobAdapter(database).list(WORKSPACE, RUN)[0]
            self.assertEqual(claimed["state"], "FAILED")
            self.assertIsNotNone(claimed["artifactCommitIntent"])
            self.assertTrue(final_path.is_file())

            resumed = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            completed = resumed.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(completed["state"], "FAILED")
            self.assertIsNone(completed["artifactCommitIntent"])
            self.assertFalse(final_path.exists())
            self.assertEqual(
                len(completed["attempts"][-1]["quarantineStorageKeys"]), 1
            )
            revision = completed["revision"]
            self.assertEqual(resumed.recover_expired(WORKSPACE, RUN), [])
            self.assertEqual(
                resumed.list_jobs(WORKSPACE, RUN)[0]["revision"], revision
            )

    def test_unsafe_cleanup_target_never_clears_the_durable_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, stored, final_path = (
                self._crash_after_publish(directory)
            )
            outside = Path(directory) / "outside-unsafe.mp4"
            outside.write_bytes(b"must not be quarantined")
            final_path.unlink()
            final_path.symlink_to(outside)
            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )

            blocked = restored.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(blocked["state"], "FAILED")
            self.assertEqual(
                blocked["artifactCommitIntent"],
                stored["artifactCommitIntent"],
            )
            self.assertTrue(final_path.is_symlink())
            self.assertEqual(outside.read_bytes(), b"must not be quarantined")
            revision = blocked["revision"]

            replay = restored.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(replay["revision"], revision)
            self.assertIsNotNone(replay["artifactCommitIntent"])
            self.assertTrue(final_path.is_symlink())

    def test_expired_running_attempt_never_exceeds_max_attempts(self):
        class CrashBeforeArtifact:
            adapter_identity = "test.crash-before-artifact"
            provenance = "LOCAL_EVIDENCE"

            def generate(self, generation_request, candidate_path):
                del generation_request, candidate_path
                raise InjectedProcessCrash("worker died")

        with tempfile.TemporaryDirectory() as directory:
            clock = MutableClock()
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                CrashBeforeArtifact(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            coordinator.dispatch(request(), idempotency_key="budget")
            leased = coordinator.lease_next(WORKSPACE, RUN, "worker-one")
            with self.assertRaises(InjectedProcessCrash):
                coordinator.run_leased(leased, "worker-one")
            clock.value = "2026-08-24T00:00:11Z"
            recovered = coordinator.recover_expired(WORKSPACE, RUN)
            self.assertEqual(recovered[0]["state"], "FAILED")
            self.assertEqual(len(recovered[0]["attempts"]), 1)
            self.assertIsNone(coordinator.lease_next(WORKSPACE, RUN, "worker-two"))
            with self.assertRaises(MediaJobStateError):
                coordinator.retry(WORKSPACE, RUN, recovered[0]["jobRef"])

    def test_two_jobs_for_one_request_have_non_clobbering_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
                max_attempts=1,
            )
            first, _ = coordinator.dispatch(request(), idempotency_key="job-one")
            second, _ = coordinator.dispatch(request(), idempotency_key="job-two")
            first_result = coordinator.run_leased(
                coordinator.lease_next(WORKSPACE, RUN, "worker-one"), "worker-one"
            )
            second_result = coordinator.run_leased(
                coordinator.lease_next(WORKSPACE, RUN, "worker-two"), "worker-two"
            )
            self.assertNotEqual(first["jobRef"], second["jobRef"])
            self.assertNotEqual(
                first_result["artifact"]["storageKey"],
                second_result["artifact"]["storageKey"],
            )
            self.assertTrue(
                (coordinator.artifact_root / first_result["artifact"]["storageKey"]).is_file()
            )
            self.assertTrue(
                (coordinator.artifact_root / second_result["artifact"]["storageKey"]).is_file()
            )

    def test_orphan_inventory_quarantine_and_symlink_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory) / "artifacts"
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                artifact_root,
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            run_root = coordinator._run_root(WORKSPACE, RUN)
            orphan = run_root / "jobs" / "detached.mp4"
            orphan.parent.mkdir(parents=True, exist_ok=True)
            orphan.write_bytes(b"detached-but-preserved")
            orphan_key = orphan.relative_to(artifact_root).as_posix()

            outside = Path(directory) / "outside.bin"
            outside.write_bytes(b"outside-must-not-change")
            unsafe_link = run_root / "jobs" / "unsafe-link.mp4"
            unsafe_link.symlink_to(outside)
            unsafe_key = unsafe_link.relative_to(artifact_root).as_posix()

            inventory = coordinator.inventory_orphan_artifacts(WORKSPACE, RUN)
            by_key = {item["storageKey"]: item for item in inventory}
            self.assertEqual(by_key[orphan_key]["inventoryState"], "ORPHAN")
            self.assertEqual(by_key[unsafe_key]["entryType"], "SYMLINK")

            quarantined = coordinator.quarantine_orphan_artifact(
                WORKSPACE, RUN, orphan_key, reason="unit_test_orphan"
            )
            self.assertEqual(quarantined["inventoryState"], "QUARANTINED")
            self.assertFalse(orphan.exists())
            self.assertTrue((artifact_root / quarantined["storageKey"]).is_file())
            replay = coordinator.quarantine_orphan_artifact(
                WORKSPACE, RUN, orphan_key, reason="unit_test_orphan"
            )
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["storageKey"], quarantined["storageKey"])
            with self.assertRaises(ArtifactVerificationError):
                coordinator.quarantine_orphan_artifact(
                    WORKSPACE, RUN, orphan_key, reason="different_command"
                )

            with self.assertRaises(ArtifactVerificationError):
                coordinator.quarantine_orphan_artifact(
                    WORKSPACE, RUN, unsafe_key, reason="unsafe_symlink"
                )
            with self.assertRaises(ArtifactVerificationError):
                coordinator.quarantine_orphan_artifact(
                    WORKSPACE, RUN, "../../outside.bin", reason="path_escape"
                )
            linked_directory = run_root / "linked-directory"
            linked_directory.symlink_to(outside.parent, target_is_directory=True)
            with self.assertRaises(ArtifactVerificationError):
                coordinator.quarantine_orphan_artifact(
                    WORKSPACE,
                    RUN,
                    (linked_directory / outside.name)
                    .relative_to(artifact_root)
                    .as_posix(),
                    reason="intermediate_symlink",
                )
            self.assertEqual(outside.read_bytes(), b"outside-must-not-change")
            self.assertTrue(unsafe_link.is_symlink())

    def test_artifact_root_symlink_is_rejected_before_use(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.mkdir()
            linked = Path(directory) / "linked-artifacts"
            linked.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ArtifactVerificationError):
                MediaJobCoordinator(
                    InMemoryMediaJobAdapter(),
                    DeterministicLocalFfmpegAdapter(),
                    linked,
                    ref_factory=Refs(),
                    clock=lambda: "2026-08-24T00:00:00Z",
                )
            self.assertEqual(list(target.iterdir()), [])

    def test_inventory_of_unknown_scope_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory) / "artifacts"
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                artifact_root,
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            self.assertEqual(
                coordinator.inventory_artifacts("unknown-workspace", "unknown-run"),
                [],
            )
            self.assertEqual(list(artifact_root.iterdir()), [])

    def test_quarantine_replay_finishes_interrupted_no_clobber_move(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory) / "artifacts"
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                artifact_root,
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            orphan = coordinator._run_root(WORKSPACE, RUN) / "jobs" / "replay.mp4"
            orphan.parent.mkdir(parents=True, exist_ok=True)
            orphan.write_bytes(b"quarantine-replay-bytes")
            storage_key = orphan.relative_to(artifact_root).as_posix()
            with mock.patch(
                "services.v4_platform.artifact_recovery.os.unlink",
                side_effect=OSError("crash before source unlink"),
            ):
                with self.assertRaises(ArtifactVerificationError):
                    coordinator.quarantine_orphan_artifact(
                        WORKSPACE,
                        RUN,
                        storage_key,
                        reason="interrupted_move",
                    )
            self.assertTrue(orphan.is_file())
            resumed = coordinator.quarantine_orphan_artifact(
                WORKSPACE,
                RUN,
                storage_key,
                reason="interrupted_move",
            )
            self.assertTrue(resumed["idempotentReplay"])
            self.assertFalse(orphan.exists())
            self.assertEqual(
                (artifact_root / resumed["storageKey"]).read_bytes(),
                b"quarantine-replay-bytes",
            )

    def test_expired_and_replaced_leases_are_exactly_fenced(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = MutableClock()
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            coordinator.dispatch(request(), idempotency_key="lease-fence")
            stale = coordinator.lease_next(WORKSPACE, RUN, "same-worker")
            self.assertIn("leaseToken", stale["lease"])
            clock.value = "2026-08-24T00:00:11Z"
            with self.assertRaises(MediaJobStateError):
                coordinator.run_leased(stale, "same-worker")
            fresh = coordinator.lease_next(WORKSPACE, RUN, "same-worker")
            self.assertNotEqual(stale["revision"], fresh["revision"])
            self.assertNotEqual(
                stale["lease"]["leaseToken"], fresh["lease"]["leaseToken"]
            )
            with self.assertRaises(MediaJobStateError):
                coordinator.run_leased(stale, "same-worker")
            self.assertEqual(
                coordinator.run_leased(fresh, "same-worker")["state"],
                "SUCCEEDED",
            )

    def test_lease_expiry_during_generation_cannot_commit_success(self):
        clock = MutableClock()

        class SlowAdapter:
            adapter_identity = DeterministicLocalFfmpegAdapter.adapter_identity
            provenance = DeterministicLocalFfmpegAdapter.provenance

            def generate(self, generation_request, candidate_path):
                result = DeterministicLocalFfmpegAdapter().generate(
                    generation_request, candidate_path
                )
                clock.value = "2026-08-24T00:00:11Z"
                return result

        with tempfile.TemporaryDirectory() as directory:
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                SlowAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            coordinator.dispatch(request(), idempotency_key="lease-expired-mid-run")
            leased = coordinator.lease_next(WORKSPACE, RUN, "slow-worker")
            result = coordinator.run_leased(leased, "slow-worker")
            self.assertEqual(result["state"], "FAILED")
            self.assertEqual(result["attempts"][-1]["state"], "FAILED")
            self.assertIsNone(result["artifact"])
            self.assertIsNone(result["artifactCommitIntent"])
            self.assertEqual(
                len(result["attempts"][-1]["quarantineStorageKeys"]), 1
            )

    def test_partial_prepared_artifact_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, stored, final_path = (
                self._crash_after_publish(directory)
            )
            candidate_path = artifacts / stored["artifactCommitIntent"][
                "candidateStorageKey"
            ]
            final_path.rename(candidate_path)
            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            recovered = restored.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(recovered["state"], "FAILED")
            self.assertIsNone(recovered["artifact"])
            self.assertFalse(candidate_path.exists())
            self.assertEqual(
                len(recovered["attempts"][-1]["quarantineStorageKeys"]), 1
            )

    def test_interrupted_hard_link_publication_is_repaired_then_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobs.sqlite3"
            artifacts = Path(directory) / "artifacts"
            clock = MutableClock()
            refs = Refs()
            adapter = CountingAdapter()
            repository = SqliteMediaJobAdapter(database)
            coordinator = MediaJobCoordinator(
                repository,
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            created, _ = coordinator.dispatch(
                request(), idempotency_key="hard-link-interruption"
            )
            leased = coordinator.lease_next(WORKSPACE, RUN, "worker")
            with mock.patch(
                "services.v4_platform.artifact_recovery.os.unlink",
                side_effect=OSError("crash after final link"),
            ):
                with self.assertRaises(ArtifactVerificationError):
                    coordinator.run_leased(leased, "worker")
            prepared = repository.get(WORKSPACE, RUN, created["jobRef"])
            intent = prepared["artifactCommitIntent"]
            candidate = artifacts / intent["candidateStorageKey"]
            final = artifacts / intent["finalStorageKey"]
            self.assertEqual(candidate.stat().st_ino, final.stat().st_ino)
            self.assertEqual(candidate.stat().st_nlink, 2)

            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            adopted = restored.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(adopted["state"], "SUCCEEDED")
            self.assertTrue(adopted["attempts"][-1]["recoveredFromCommitIntent"])
            self.assertFalse(candidate.exists())
            self.assertTrue(final.is_file())
            self.assertEqual(final.stat().st_nlink, 1)
            self.assertEqual(adapter.calls, 1)

    def test_recovery_loser_never_quarantines_winner_final(self):
        class ConcurrentSuccess:
            def __init__(self, delegate):
                self.delegate = delegate
                self.injected = False

            def create(self, job):
                return self.delegate.create(job)

            def get(self, workspace_ref, run_ref, job_ref):
                return self.delegate.get(workspace_ref, run_ref, job_ref)

            def list(self, workspace_ref, run_ref):
                return self.delegate.list(workspace_ref, run_ref)

            def save(self, job, expected_revision):
                if not self.injected and job["state"] in {"FAILED", "QUEUED"}:
                    self.injected = True
                    current = self.delegate.get(
                        job["workspaceRef"],
                        job["productionRunRef"],
                        job["jobRef"],
                    )
                    intent = current["artifactCommitIntent"]
                    won = deepcopy(current)
                    won["attempts"][-1].update(
                        {
                            "state": "SUCCEEDED",
                            "finishedAt": "2026-08-24T00:00:11Z",
                            "artifactSha256": intent["artifact"]["sha256"],
                            "artifactCommitIntentDigest": intent["intentDigest"],
                        }
                    )
                    won.update(
                        {
                            "state": "SUCCEEDED",
                            "lease": None,
                            "artifact": deepcopy(intent["artifact"]),
                            "artifactCommitIntent": None,
                            "updatedAt": "2026-08-24T00:00:11Z",
                        }
                    )
                    self.delegate.save(won, expected_revision)
                    raise MediaJobStateError("concurrent success won")
                return self.delegate.save(job, expected_revision)

        with tempfile.TemporaryDirectory() as directory:
            database, artifacts, clock, refs, adapter, stored, final_path = (
                self._crash_after_publish(directory)
            )
            candidate_path = artifacts / stored["artifactCommitIntent"][
                "candidateStorageKey"
            ]
            candidate_path.write_bytes(b"late-candidate-for-race")
            clock.value = "2026-08-24T00:00:11Z"
            restored = MediaJobCoordinator(
                ConcurrentSuccess(SqliteMediaJobAdapter(database)),
                adapter,
                artifacts,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
                max_attempts=1,
            )
            recovered = restored.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(recovered["state"], "SUCCEEDED")
            self.assertTrue(final_path.is_file())
            self.assertTrue(candidate_path.is_file())
            by_key = {
                item["storageKey"]: item
                for item in restored.inventory_orphan_artifacts(WORKSPACE, RUN)
            }
            self.assertEqual(
                by_key[candidate_path.relative_to(artifacts).as_posix()][
                    "inventoryState"
                ],
                "ORPHAN",
            )

    def test_legacy_retrying_state_recovers_without_new_attempt(self):
        repository = InMemoryMediaJobAdapter()
        with tempfile.TemporaryDirectory() as directory:
            coordinator = MediaJobCoordinator(
                repository,
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            created, _ = coordinator.dispatch(request(), idempotency_key="retrying")
            stranded = repository.get(WORKSPACE, RUN, created["jobRef"])
            expected = stranded["revision"]
            stranded["state"] = "RETRYING"
            stranded = repository.save(stranded, expected)
            recovered = coordinator.recover_expired(WORKSPACE, RUN)
            self.assertEqual(recovered[0]["state"], "QUEUED")
            self.assertEqual(recovered[0]["attempts"], [])

    def test_attempt_budget_is_immutable_after_dispatch(self):
        repository = InMemoryMediaJobAdapter()
        with tempfile.TemporaryDirectory() as directory:
            coordinator = MediaJobCoordinator(
                repository,
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
                max_attempts=2,
            )
            created, _ = coordinator.dispatch(request(), idempotency_key="immutable")
            changed = repository.get(WORKSPACE, RUN, created["jobRef"])
            changed["maxAttempts"] = 3
            with self.assertRaises(MediaJobStateError):
                repository.save(changed, changed["revision"])

    def test_attempt_history_cannot_be_deleted_or_terminally_rewritten(self):
        class FailingAdapter:
            adapter_identity = "test.failing-adapter"
            provenance = "LOCAL_EVIDENCE"

            def generate(self, generation_request, candidate_path):
                del generation_request, candidate_path
                raise RuntimeError("expected failure")

        repository = InMemoryMediaJobAdapter()
        with tempfile.TemporaryDirectory() as directory:
            coordinator = MediaJobCoordinator(
                repository,
                FailingAdapter(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
                max_attempts=2,
            )
            coordinator.dispatch(request(), idempotency_key="append-only-attempt")
            failed = coordinator.run_leased(
                coordinator.lease_next(WORKSPACE, RUN, "worker"), "worker"
            )
            removed = deepcopy(failed)
            removed["attempts"] = []
            with self.assertRaises(MediaJobError):
                repository.save(removed, removed["revision"])
            rewritten = deepcopy(failed)
            rewritten["attempts"][-1]["errorCode"] = "forged-error"
            with self.assertRaises(MediaJobStateError):
                repository.save(rewritten, rewritten["revision"])

    def test_attempt_budget_two_is_an_exact_upper_bound(self):
        class WorkerCrash:
            adapter_identity = "test.worker-crash"
            provenance = "LOCAL_EVIDENCE"

            def generate(self, generation_request, candidate_path):
                del generation_request, candidate_path
                raise InjectedProcessCrash("worker disappeared")

        with tempfile.TemporaryDirectory() as directory:
            clock = MutableClock()
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                WorkerCrash(),
                Path(directory) / "artifacts",
                ref_factory=Refs(),
                clock=clock,
                lease_seconds=10,
                max_attempts=2,
            )
            coordinator.dispatch(request(), idempotency_key="two-attempt-budget")
            first = coordinator.lease_next(WORKSPACE, RUN, "worker-one")
            with self.assertRaises(InjectedProcessCrash):
                coordinator.run_leased(first, "worker-one")
            clock.value = "2026-08-24T00:00:11Z"
            self.assertEqual(
                coordinator.recover_expired(WORKSPACE, RUN)[0]["state"],
                "QUEUED",
            )
            second = coordinator.lease_next(WORKSPACE, RUN, "worker-two")
            with self.assertRaises(InjectedProcessCrash):
                coordinator.run_leased(second, "worker-two")
            clock.value = "2026-08-24T00:00:22Z"
            terminal = coordinator.recover_expired(WORKSPACE, RUN)[0]
            self.assertEqual(terminal["state"], "FAILED")
            self.assertEqual(len(terminal["attempts"]), 2)
            self.assertIsNone(
                coordinator.lease_next(WORKSPACE, RUN, "worker-three")
            )

    def test_v2_jobs_read_and_one_way_upgrade_legacy_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            source = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "source-artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            created, _ = source.dispatch(request(), idempotency_key="schema-source")
            self.assertEqual(created["schemaVersion"], "v4.media-job.v2")

            legacy_repository = SqliteMediaJobAdapter(
                Path(directory) / "legacy.sqlite3"
            )
            legacy = deepcopy(created)
            legacy["schemaVersion"] = "v4.media-job.v1"
            legacy.pop("artifactCommitIntent")
            legacy, _ = legacy_repository.create(legacy)
            restored = MediaJobCoordinator(
                legacy_repository,
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "legacy-artifacts",
                ref_factory=Refs(),
                clock=lambda: "2026-08-24T00:00:00Z",
            )
            leased = restored.lease_next(WORKSPACE, RUN, "legacy-worker")
            self.assertEqual(leased["schemaVersion"], "v4.media-job.v2")
            self.assertIn("leaseToken", leased["lease"])

            invalid_legacy = deepcopy(created)
            invalid_legacy["schemaVersion"] = "v4.media-job.v1"
            invalid_legacy["artifactCommitIntent"] = {"unexpected": "intent"}
            with self.assertRaises(MediaJobError):
                InMemoryMediaJobAdapter().create(invalid_legacy)


if __name__ == "__main__":
    unittest.main()
