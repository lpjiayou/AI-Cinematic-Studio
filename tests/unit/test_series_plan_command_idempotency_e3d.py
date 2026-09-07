"""M5 deterministic identities, terminal state rules and domain compatibility."""

import copy
from dataclasses import replace
from hashlib import sha256
import json
import unittest

from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService, SeriesDirectorGenerationError
from apps.creator_workspace_mvp.series_plan_candidate_commands import (
    SeriesPlanCandidateCommandError, create_command_service, new_pending_command,
)
from apps.creator_workspace_mvp.series_plan_candidate_receipts import build_series_plan_candidate_context, create_in_memory_receipt_service
from services.v5_core_os.series_planning import SeriesPlanningPublicError
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_planning.candidate_command_sqlite import (
    SeriesPlanCandidateCommandStorageError, seal_record, validate_command, validate_transition,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import canonical_json, canonical_json_digest
from services.v5_core_os.series_planning.foundation import confirmation_identity
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v5_core_os.text_generation import TextGenerationTimeoutError, TextGenerationUnavailableError
from tests.unit.test_series_planning_m5 import WORKSPACE, create_context, valid_candidate


NOW = "2026-09-07T08:00:00.000Z"


def source_context():
    return {
        "schemaVersion": "creator.series-plan-candidate-source-context.v1",
        "workspaceRef": "e3d-golden-workspace", "contentProfileRef": "e3d-profile",
        "projectRef": "e3d-project", "seriesRef": "e3d-series", "projectTitle": "晚灯",
        "projectDescription": "test source", "targetPlatform": "streaming", "aspectRatio": "16:9",
        "plannedEpisodeCount": 4, "createdEpisodeCount": 0, "seriesTitle": "晚灯系列",
        "seriesDescription": "test series", "projectVersion": 1, "seriesVersion": 1,
        "projectStatus": "active", "seriesStatus": "active",
    }


def candidate_context(source=None):
    source = source if source is not None else source_context()
    return {"sourceContext": source, "generationContext": {
        **{k: v for k, v in source.items() if k not in {"projectVersion", "seriesVersion", "projectStatus", "seriesStatus", "schemaVersion"}},
        "schemaVersion": "creator.series-director.context.v1",
    }}


def completed_command(pending):
    candidate = valid_candidate()
    return seal_record(replace(pending, state="COMPLETED", candidateJson=canonical_json(candidate),
                              candidateDigest=canonical_json_digest(candidate), completedAt=NOW))


class CandidateIdentityAndStateTests(unittest.TestCase):
    def pending(self, **changes):
        return new_pending_command({**source_context(), **changes}, "input never persisted", "key:晚灯 01", clock=lambda: NOW)

    def test_independent_golden_identity_vectors_and_full_domain_separation(self):
        row = self.pending()
        self.assertEqual(row.identityDigest, "af90ce0e1a10d742e4f1e201a49d583c498bb78bd35627358fe57bdc90537c71")
        self.assertEqual(row.candidateRef, "series-plan-candidate-9389e2ebb49aea4adb8f0adbec29903c8e822842c5a1ca256500082c11d069ab")
        self.assertEqual(confirmation_identity(row.workspaceRef, "key:晚灯 01"), "a79d1706035a927af80dc797382f19352aa0a6fb27384157ea8a958569b9252e")
        self.assertEqual(row.commandRef, "series-plan-candidate-command-" + row.identityDigest)
        for ref in (row.commandRef, row.candidateRef):
            self.assertRegex(ref, r"-[0-9a-f]{64}$")
            self.assertNotIn("key:晚灯 01", ref)
        self.assertEqual(row, self.pending())
        self.assertNotEqual(row.identityDigest, self.pending(workspaceRef="other-workspace").identityDigest)
        other = new_pending_command(source_context(), "input never persisted", "another-key", clock=lambda: NOW)
        self.assertNotEqual(row.candidateRef, other.candidateRef)
        self.assertNotEqual(row.identityDigest, row.candidateRef.rsplit("-", 1)[1])

    def test_normalization_and_request_digest_include_current_context_but_not_identity(self):
        a = self.pending()
        b = new_pending_command(source_context(), "  input never persisted \n", "key:晚灯 01", clock=lambda: NOW)
        self.assertEqual(a, b)
        self.assertEqual(a.creativeInputDigest, sha256(b"input never persisted").hexdigest())
        for changes in ({"projectVersion": 2}, {"seriesVersion": 2}, {"projectTitle": "new title"},
                        {"createdEpisodeCount": 1}, {"projectRef": "other-project"}, {"seriesRef": "other-series"}):
            changed = self.pending(**changes)
            self.assertEqual(changed.identityDigest, a.identityDigest)
            self.assertNotEqual(changed.requestDigest, a.requestDigest)

    def test_bad_keys_and_empty_inputs_cannot_reserve(self):
        for key in (None, False, 1, [], {}, "", " key", "key ", ".", "..", "a/b", "a\\b", "a\x00b", "a" * 201):
            with self.subTest(key=repr(key)), self.assertRaises(SeriesPlanCandidateCommandError):
                new_pending_command(source_context(), "input", key)
        for value in (None, "", "  ", "a" * 4001):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(SeriesPlanCandidateCommandError):
                new_pending_command(source_context(), value, "valid")

    def test_terminal_states_are_closed_and_all_immutable_fields_are_bound(self):
        pending = self.pending()
        completed = completed_command(pending)
        validate_transition(pending, completed)
        failed = seal_record(replace(pending, state="FAILED", failureCode="provider_timeout", completedAt=NOW))
        validate_transition(pending, failed)
        for bad in (replace(pending, state="UNKNOWN"), replace(completed, candidateDigest="0" * 64),
                    replace(completed, candidateJson='{"schemaVersion":"creator.series-plan.candidate.v1"}'),
                    replace(failed, failureCode="raw sensitive failure"), replace(pending, completedAt=NOW),
                    replace(completed, completedAt="2026-09-06T00:00:00.000Z"),
                    replace(completed, requestDigest="0" * 64), replace(completed, projectRef="another")):
            with self.subTest(changed=bad.state), self.assertRaises(SeriesPlanCandidateCommandStorageError):
                validate_command(seal_record(bad))
        with self.assertRaises(SeriesPlanCandidateCommandStorageError):
            validate_transition(completed, completed)
        with self.assertRaises(SeriesPlanCandidateCommandStorageError):
            validate_command(replace(pending, rowDigest="f" * 64))

    def test_failed_calls_replay_the_same_stable_error_without_provider_details(self):
        cases = [([TextGenerationTimeoutError()], "provider_timeout", 1),
                 ([TextGenerationUnavailableError(category="test")], "provider_unavailable", 1),
                 (["{}", "{}"], "invalid_provider_output", 2),
                 ([RuntimeError("raw private error")], "application_error", 1)]
        for outcomes, code, calls in cases:
            with self.subTest(code=code):
                service = create_command_service()
                capability = FakeTextGenerationCapability(outcomes)
                director = SeriesDirectorApplicationService(capability)
                for _ in range(2):
                    with self.assertRaises(SeriesDirectorGenerationError) as failure:
                        service.generate(candidate_context(), "input", "key", director)
                    self.assertEqual(failure.exception.code, code)
                    self.assertEqual(failure.exception.validation_issues, ())
                self.assertEqual(len(capability.commands), calls)
                self.assertEqual(service.store.count(), 1)


class KeyedDomainCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.series, self.projects, self.planning, self.series_record, self.project = create_context()
        context = build_series_plan_candidate_context(self.projects.build_context(
            WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"]))
        receipts = create_in_memory_receipt_service()
        receipt, _ = receipts.issue(context, "input", valid_candidate())
        self.command = {name: getattr(receipt, name) for name in (
            "workspaceRef", "contentProfileRef", "projectRef", "seriesRef", "sourceProjectVersion",
            "sourceSeriesVersion", "sourceContextDigest", "candidateRef", "candidateDigest")}
        self.command.update(candidate=valid_candidate(), humanConfirmed=True, idempotencyKey="confirmation")

    def test_root_and_episode_identity_match_the_frozen_formulas_and_bootstrap(self):
        first = self.planning.confirm_candidate_idempotently(self.command)
        request = {"schemaVersion": "v5.series-plan-confirmation-request.v1",
                   **{k: v for k, v in self.command.items() if k not in {"workspaceRef", "humanConfirmed", "idempotencyKey"}}}
        digest = canonical_json_digest(request)
        identity = confirmation_identity(WORKSPACE, "confirmation")
        self.assertEqual(first["plan"]["seriesPlanRef"], "series-plan-" + identity)
        self.assertEqual(first["version"]["seriesPlanVersionRef"], "series-plan-version-" + canonical_json_digest({
            "schemaVersion": "v5.series-plan-confirmation-version-identity.v1",
            "confirmationIdentityDigest": identity, "requestDigest": digest}))
        for item in first["version"]["episodePlanItems"]:
            self.assertEqual(item["episodePlanItemRef"], "episode-plan-item-" + canonical_json_digest({
                "schemaVersion": "v5.episode-plan-item-confirmation-identity.v1",
                "requestDigest": digest, "episodeNumber": item["episodeNumber"]}))
        replay = self.planning.confirm_candidate_idempotently(self.command)
        self.assertEqual(first["plan"], replay["plan"])
        self.assertEqual(first["version"], replay["version"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(first["version"]["schemaVersion"], "v5.series-plan-version.v1")
        bootstrap = self.planning.build_m6_bootstrap(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"])
        self.assertIn(first["plan"]["seriesPlanRef"], json.dumps(bootstrap))

    def test_manual_append_remains_immutable_and_blocks_old_root_replay(self):
        first = self.planning.confirm_candidate_idempotently(self.command)
        content = {k: copy.deepcopy(self.command["candidate"][k]) for k in self.command["candidate"] if k != "schemaVersion"}
        content["episodePlanItems"] = first["version"]["episodePlanItems"]
        content["premise"] = "A manual revision"
        result = self.planning.create_manual_version({"workspaceRef": WORKSPACE, "projectRef": self.project["projectRef"],
            "seriesRef": self.series_record["seriesRef"], "seriesPlanRef": first["plan"]["seriesPlanRef"],
            "expectedPlanVersion": 1, "content": content})
        self.assertEqual(result["version"]["versionNumber"], 2)
        before = self.planning.get_workspace(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"])
        with self.assertRaises(SeriesPlanningPublicError) as failure:
            self.planning.confirm_candidate_idempotently(self.command)
        self.assertEqual((failure.exception.status, failure.exception.code), (409, "series_plan_confirmation_idempotency_conflict"))
        self.assertEqual(before, self.planning.get_workspace(WORKSPACE, self.project["projectRef"], self.series_record["seriesRef"]))
        self.assertEqual(before["versions"][0], first["version"])

    def test_keyed_root_remains_readable_after_existing_v2_binding_operation(self):
        assembly = LifecycleAssembly.in_memory()
        series = assembly.series_episode.create_series({"workspaceRef": WORKSPACE,
            "contentProfileRef": "e3d-profile", "title": "E3D series", "plannedEpisodeCount": 4})
        project = assembly.project_context.create_project({"workspaceRef": WORKSPACE,
            "contentProfileRef": "e3d-profile", "projectType": "series", "seriesRef": series["seriesRef"],
            "title": "E3D project", "plannedEpisodeCount": 4})
        context = build_series_plan_candidate_context(assembly.project_context.build_context(
            WORKSPACE, project["projectRef"], series["seriesRef"]))
        receipt, _ = create_in_memory_receipt_service().issue(context, "input", valid_candidate())
        command = {name: getattr(receipt, name) for name in self.command if hasattr(receipt, name)}
        command.update(humanConfirmed=True, candidate=valid_candidate(), idempotencyKey="v2-compatibility")
        first = assembly.series_planning.confirm_candidate_idempotently(command)
        second = assembly.series_planning.create_episode_plan_item_binding_version({
            "workspaceRef": WORKSPACE, "projectRef": project["projectRef"], "seriesRef": series["seriesRef"],
            "seriesPlanRef": first["plan"]["seriesPlanRef"], "expectedPlanVersion": 1, "episodePlanItemBindings": [],
        })
        self.assertEqual(second["version"]["schemaVersion"], "v5.series-plan-version.v2")
        self.assertEqual(second["version"]["episodePlanItems"], first["version"]["episodePlanItems"])
        self.assertEqual(second["version"]["parentSeriesPlanVersionRef"], first["version"]["seriesPlanVersionRef"])
        workspace = assembly.series_planning.get_workspace(WORKSPACE, project["projectRef"], series["seriesRef"])
        self.assertEqual(workspace["versions"][0], first["version"])
        with self.assertRaises(SeriesPlanningPublicError) as failure:
            assembly.series_planning.confirm_candidate_idempotently(command)
        self.assertEqual(failure.exception.code, "series_plan_confirmation_idempotency_conflict")


if __name__ == "__main__":
    unittest.main()
