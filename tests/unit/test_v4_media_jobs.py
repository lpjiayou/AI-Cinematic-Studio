import json
from pathlib import Path
import tempfile
import unittest

from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    MediaJobStateError,
    SqliteMediaJobAdapter,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    create_boundary,
    g2_command,
    g3_command,
    g4_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


class MutableClock:
    def __init__(self):
        self.value = "2026-08-17T01:00:00Z"

    def __call__(self):
        return self.value


def one_request():
    assembly, refs, project, series, episode, _ = seed_k2_roots(
        with_m6_authority=True
    )
    activate_k2_m6_baseline(assembly, project, series)
    boundary = create_boundary(
        assembly, refs, identity_reference_authority=k2_identity_authority()
    )
    run = boundary.create_run(run_command(project, series, episode))
    boundary.authorize_and_lock(g2_command(run))
    boundary.compile_shot_graph(g3_command(run))
    plan = boundary.resolve_assets(g4_command(run))
    return refs, run, plan["generationRequests"][0]


class V4SingleEpisodeMediaJobTests(unittest.TestCase):
    def test_lease_expiry_recovery_and_cancellation_are_explicit(self):
        refs, run, generation_request = one_request()
        clock = MutableClock()
        with tempfile.TemporaryDirectory() as directory:
            queue = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                DeterministicLocalFfmpegAdapter(),
                directory,
                ref_factory=refs,
                clock=clock,
                lease_seconds=10,
            )
            job, replay = queue.dispatch(
                generation_request, idempotency_key="dispatch-one"
            )
            self.assertFalse(replay)
            leased = queue.lease_next(WORKSPACE, run["productionRunRef"], "worker-a")
            self.assertEqual(leased["state"], "LEASED")
            clock.value = "2026-08-17T01:00:11Z"
            recovered = queue.recover_expired(WORKSPACE, run["productionRunRef"])
            self.assertEqual([item["state"] for item in recovered], ["QUEUED"])
            cancelled = queue.cancel(WORKSPACE, run["productionRunRef"], job["jobRef"])
            self.assertEqual(cancelled["state"], "CANCELLED")
            with self.assertRaises(MediaJobStateError):
                queue.cancel(WORKSPACE, run["productionRunRef"], job["jobRef"])

    def test_sqlite_queue_is_restart_safe_and_exactly_scoped(self):
        refs, run, generation_request = one_request()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobs.sqlite3"
            first = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=refs,
                clock=lambda: "2026-08-17T01:00:00Z",
            )
            created, _ = first.dispatch(
                generation_request, idempotency_key="durable-dispatch"
            )
            leased = first.lease_next(
                WORKSPACE, run["productionRunRef"], "worker-before-crash"
            )
            self.assertEqual(leased["state"], "LEASED")
            second = MediaJobCoordinator(
                SqliteMediaJobAdapter(database),
                DeterministicLocalFfmpegAdapter(),
                Path(directory) / "artifacts",
                ref_factory=refs,
                clock=lambda: "2026-08-17T01:00:31Z",
            )
            recovered = second.recover_expired(WORKSPACE, run["productionRunRef"])
            self.assertEqual([item["state"] for item in recovered], ["QUEUED"])
            restored = second.list_jobs(WORKSPACE, run["productionRunRef"])
            self.assertEqual(restored[0]["jobRef"], created["jobRef"])
            self.assertEqual(restored[0]["state"], "QUEUED")
            self.assertEqual(second.list_jobs("workspace-other", run["productionRunRef"]), [])
            import sqlite3
            connection = sqlite3.connect(database)
            try:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(
                tables,
                {
                    "v4_media_job_schema",
                    "v4_media_jobs",
                    "v4_media_job_batches",
                },
            )

    def test_adapter_escape_is_failed_not_accepted(self):
        refs, run, generation_request = one_request()

        class EscapingAdapter:
            adapter_identity = "test.escape"
            provenance = "LOCAL_EVIDENCE"

            def generate(self, request, candidate_path):
                del request
                candidate_path.parent.mkdir(parents=True, exist_ok=True)
                candidate_path.write_bytes(b"orphan temporary artifact")
                escaped = Path(directory).parent / "escaped-media.mp4"
                escaped.write_bytes(b"not media")
                return escaped

        with tempfile.TemporaryDirectory() as directory:
            queue = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                EscapingAdapter(),
                directory,
                ref_factory=refs,
                clock=lambda: "2026-08-17T01:00:00Z",
                max_attempts=1,
            )
            queue.dispatch(generation_request, idempotency_key="escape")
            leased = queue.lease_next(WORKSPACE, run["productionRunRef"], "worker-a")
            result = queue.run_leased(leased, "worker-a")
            self.assertEqual(result["state"], "FAILED")
            self.assertEqual(result["attempts"][-1]["errorCode"], "artifact_verification_failed")
            self.assertIsNone(result["artifact"])
            quarantined = list(Path(directory).glob("**/quarantine/*"))
            self.assertEqual(len(quarantined), 1)
            escaped = Path(directory).parent / "escaped-media.mp4"
            if escaped.exists():
                escaped.unlink()

    def test_failed_attempt_retries_without_duplicate_accepted_result(self):
        refs, run, generation_request = one_request()

        class FailOnceAdapter:
            adapter_identity = "test.fail-once-local-ffmpeg"
            provenance = "LOCAL_EVIDENCE"

            def __init__(self):
                self.calls = 0
                self.delegate = DeterministicLocalFfmpegAdapter()

            def generate(self, request, candidate_path):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected retryable failure")
                return self.delegate.generate(request, candidate_path)

        with tempfile.TemporaryDirectory() as directory:
            adapter = FailOnceAdapter()
            queue = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                adapter,
                directory,
                ref_factory=refs,
                clock=lambda: "2026-08-17T01:00:00Z",
                max_attempts=2,
            )
            jobs = queue.execute_batch(
                WORKSPACE,
                run["productionRunRef"],
                [generation_request],
                batch_idempotency_key="retry-batch",
            )
            self.assertEqual(jobs[0]["state"], "SUCCEEDED")
            self.assertEqual(
                [attempt["state"] for attempt in jobs[0]["attempts"]],
                ["FAILED", "SUCCEEDED"],
            )
            artifact_sha = jobs[0]["artifact"]["sha256"]
            replay = queue.execute_batch(
                WORKSPACE,
                run["productionRunRef"],
                [generation_request],
                batch_idempotency_key="retry-batch",
            )
            self.assertEqual(replay[0]["artifact"]["sha256"], artifact_sha)
            self.assertEqual(len(replay[0]["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()
