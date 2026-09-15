"""Public supervision is not an authority or a second generation engine."""
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
import unittest

from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceBoundary, GenerationWorkspaceError
from services.v5_core_os.episode_production.generation_dispatch_operator import GenerationDispatchOperator
from services.v5_core_os.episode_production import generation_dispatch_contracts as c

SCOPE = dict(workspaceRef="workspace-test", projectRef="project-test", seriesRef="series-test", episodeRef="episode-test", productionRunRef="run-test")


class TestOnlyOperator(GenerationDispatchOperator):
    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.calls = []
        self.job = {**SCOPE, "jobRef": "job-test", "revision": 1, "state": "QUEUED", "attempts": [],
            "request": {**SCOPE, "creativeShotVersionRef": "shot-v1", "beatRef": "beat-1"},
            "dispatchGrantBinding": {"approvedPlanDigest": "a" * 64},
            "executionEnvelope": {"outputConstraints": {"width": 704, "height": 1280, "durationFrames": 48, "frameRate": 24}}}

    def read_job(self, media_job_ref):
        assert media_job_ref == "job-test"
        return deepcopy(self.job)

    def prepare(self):
        self.calls.append("prepare")
        return {"planPackage": {}}

    def execute_one(self, media_job_ref):
        self.calls.append("execute")
        self.entered.set()
        assert self.release.wait(5)
        self.job.update(state="FAILED", revision=2, attempts=[{"attemptRef": "attempt-test"}],
            dispatchResult={"outcome": "UNKNOWN"})
        return deepcopy(self.job)


class GenerationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.operator = TestOnlyOperator()
        self.boundary = self.make_boundary()
        self.command = dict(operation="EXECUTE_APPROVED", mediaJobRef="job-test", expectedJobRevision=1, approvedPlanDigest="a" * 64)
        self.addCleanup(self.boundary.close)
        self.addCleanup(self.operator.release.set)

    def make_boundary(self, writers=frozenset({"credential-test"})):
        return GenerationWorkspaceBoundary(operator=self.operator, media_job_ref="job-test",
            run_reader=SimpleNamespace(get_run=lambda workspace, run: deepcopy(SCOPE)), allowed_credential_refs=writers)

    def test_read_is_side_effect_free_and_contains_no_private_material(self):
        view = self.boundary.project(SCOPE, "credential-test")
        self.assertEqual(view["state"], "QUEUED")
        self.assertTrue(view["canExecute"])
        self.assertFalse(view["publicationAllowed"])
        self.assertFalse(view["automaticRetryAllowed"])
        self.assertEqual(self.operator.calls, [])
        self.assertTrue(set(view).isdisjoint({"grant", "endpoint", "internalPath", "approval", "selection"}))

    def test_every_scope_dimension_is_checked_before_operator(self):
        for field in SCOPE:
            with self.subTest(field=field), self.assertRaises(GenerationWorkspaceError):
                self.boundary.project({**SCOPE, field: "another"}, "credential-test")
        self.assertEqual(self.operator.calls, [])

    def test_missing_writer_authority_fails_closed(self):
        boundary = self.make_boundary(frozenset())
        self.assertFalse(boundary.project(SCOPE, "credential-test")["canExecute"])
        with self.assertRaises(GenerationWorkspaceError) as error:
            boundary.start(SCOPE, "credential-test", self.command)
        self.assertEqual(error.exception.status, 403)

    def test_forged_closed_command_and_stale_binding_are_rejected(self):
        for command in ({**self.command, "actorRef": "owner"}, {**self.command, "expectedJobRevision": True},
                        {**self.command, "expectedJobRevision": 0}, {**self.command, "approvedPlanDigest": "b" * 64},
                        {**self.command, "mediaJobRef": "other"}, {**self.command, "operation": "ISSUE"}):
            with self.subTest(command=command), self.assertRaises(GenerationWorkspaceError):
                self.boundary.start(SCOPE, "credential-test", command)
        self.assertEqual(self.operator.calls, [])

    def test_duplicate_click_inflight_and_unknown_restart_never_resubmit(self):
        self.boundary.start(SCOPE, "credential-test", self.command)
        self.assertTrue(self.operator.entered.wait(5))
        self.boundary.start(SCOPE, "credential-test", self.command)
        self.assertEqual(self.operator.calls, ["execute"])
        self.assertEqual(self.boundary.project(SCOPE, "credential-test")["activity"], "EXECUTING")
        self.operator.release.set(); self.boundary.close()
        restarted = self.make_boundary()
        self.assertEqual(restarted.project(SCOPE, "credential-test")["state"], "UNKNOWN")
        with self.assertRaises(GenerationWorkspaceError):
            restarted.start(SCOPE, "credential-test", {**self.command, "expectedJobRevision": 2})
        self.assertEqual(self.operator.calls, ["execute"])

    def test_prepare_does_not_execute_and_sanitizes_failure(self):
        self.boundary.start(SCOPE, "credential-test", {**self.command, "operation": "PREPARE"})
        self.boundary.close()
        self.assertEqual(self.operator.calls, ["prepare"])
        def fail():
            raise c.DispatchError("OUTSIDE_VALIDITY_WINDOW")
        self.operator.prepare = fail
        self.boundary.start(SCOPE, "credential-test", {**self.command, "operation": "PREPARE"})
        self.boundary.close()
        self.assertEqual(self.boundary.project(SCOPE, "credential-test")["errorCode"], "OUTSIDE_VALIDITY_WINDOW")

    def test_terminal_states_never_offer_restart(self):
        for state in ("LEASED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"):
            self.operator.job["state"] = state
            with self.subTest(state=state):
                self.assertFalse(self.boundary.project(SCOPE, "credential-test")["canExecute"])
                with self.assertRaises(GenerationWorkspaceError):
                    self.boundary.start(SCOPE, "credential-test", self.command)

    def test_content_request_cannot_choose_arbitrary_file_or_job(self):
        with self.assertRaises(GenerationWorkspaceError) as error:
            self.boundary.content(SCOPE, "../../private", "a" * 64)
        self.assertEqual(error.exception.status, 404)
