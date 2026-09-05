import copy
import math
import unittest

from apps.creator_workspace_mvp.project_foundation import (
    ProjectFoundationApplicationError,
    ProjectFoundationApplicationService,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.project_engine.project_foundation import (
    PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
    ProjectFoundationValidationError,
    canonical_json,
    canonical_json_digest,
    normalize_project_foundation_command,
    validate_project_foundation_record,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


WORKSPACE = "workspace-project-foundation-unit"
PROFILE = "profile-project-foundation-unit"


def valid_command(*, key="foundation-key", project_type="series", episode=None):
    series = (
        {
            "title": "Wanlight",
            "description": "A recoverable Series foundation",
        }
        if project_type == "series"
        else None
    )
    return {
        "schemaVersion": PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
        "idempotencyKey": key,
        "contentProfileRef": PROFILE,
        "series": series,
        "project": {
            "projectType": project_type,
            "title": "Wanlight Project",
            "description": "A recoverable Project foundation",
            "targetPlatform": "streaming",
            "aspectRatio": "16:9",
            "defaultDurationSec": 60,
            "plannedEpisodeCount": 4,
        },
        "episode": episode,
    }


class ProjectFoundationCommandNormalizationTests(unittest.TestCase):
    def assert_invalid(self, value):
        with self.assertRaises(ProjectFoundationValidationError):
            normalize_project_foundation_command(value)

    def test_supported_project_shapes_normalize_without_workspace_metadata(self):
        series_key, series = normalize_project_foundation_command(valid_command())
        self.assertEqual("foundation-key", series_key)
        self.assertNotIn("idempotencyKey", series)
        self.assertNotIn("workspaceRef", series)
        self.assertEqual(
            series["series"]["title"],
            "Wanlight",
        )
        for project_type in ("standalone", "brand-film"):
            with self.subTest(project_type=project_type):
                _key, normalized = normalize_project_foundation_command(
                    valid_command(project_type=project_type)
                )
                self.assertIsNone(normalized["series"])
                self.assertIsNone(normalized["episode"])

    def test_standalone_may_include_optional_series(self):
        value = valid_command(project_type="standalone")
        value["series"] = {"title": "Optional Series", "description": ""}
        _key, normalized = normalize_project_foundation_command(value)
        self.assertEqual("Optional Series", normalized["series"]["title"])

    def test_series_and_episode_scope_requirements_fail_closed(self):
        missing_series = valid_command()
        missing_series["series"] = None
        self.assert_invalid(missing_series)

        episode_without_series = valid_command(project_type="standalone")
        episode_without_series["episode"] = {
            "creativePlanRef": "creative-plan-1",
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Episode 001",
        }
        self.assert_invalid(episode_without_series)

    def test_unknown_or_client_owned_fields_fail_closed(self):
        for field in ("unknown", "workspaceRef", "foundationRef"):
            value = valid_command()
            value[field] = "forbidden"
            with self.subTest(field=field):
                self.assert_invalid(value)

        for container in ("series", "project"):
            value = valid_command()
            value[container]["authorityRef"] = "forbidden"
            with self.subTest(container=container):
                self.assert_invalid(value)

    def test_all_integer_fields_are_exact_integers(self):
        fields = (
            ("project", "defaultDurationSec"),
            ("project", "plannedEpisodeCount"),
        )
        invalid_values = (True, 1.0, 1.9, "1", None, math.nan, math.inf, -math.inf)
        for container, field in fields:
            for invalid in invalid_values:
                value = valid_command()
                value[container][field] = invalid
                with self.subTest(container=container, field=field, invalid=invalid):
                    self.assert_invalid(value)

        episode = {
            "creativePlanRef": "creative-plan-1",
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Episode 001",
        }
        for field in ("episodeNumber", "seasonNumber", "volumeNumber"):
            for invalid in invalid_values:
                value = valid_command(episode=copy.deepcopy(episode))
                value["episode"][field] = invalid
                with self.subTest(field=field, invalid=invalid):
                    self.assert_invalid(value)

    def test_idempotency_key_is_bounded_non_path_text(self):
        for invalid in ("", " key", "key ", "a" * 201, "a/b", "a\\b", ".", "..", "a\x00b"):
            with self.subTest(invalid=repr(invalid)):
                self.assert_invalid(valid_command(key=invalid))

    def test_canonical_digest_is_stable_and_excludes_idempotency_scope(self):
        first_key, first = normalize_project_foundation_command(valid_command())
        reordered = {
            "episode": None,
            "project": dict(reversed(list(valid_command()["project"].items()))),
            "series": dict(reversed(list(valid_command()["series"].items()))),
            "contentProfileRef": PROFILE,
            "idempotencyKey": "different-key",
            "schemaVersion": PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
        }
        second_key, second = normalize_project_foundation_command(reordered)
        self.assertNotEqual(first_key, second_key)
        self.assertEqual(first, second)
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(canonical_json_digest(first), canonical_json_digest(second))


class _OneShotFault:
    def __init__(self, point):
        self.point = point
        self.fired = False

    def __call__(self, point):
        if point == self.point and not self.fired:
            self.fired = True
            raise RuntimeError(f"fault:{point}")


class ProjectFoundationServiceTests(unittest.TestCase):
    def setUp(self):
        self.assembly = LifecycleAssembly.in_memory()

    def service(self, fault_hook=None):
        return ProjectFoundationApplicationService(
            self.assembly.project_foundation_store,
            self.assembly.coordinator,
            self.assembly.series_episode,
            self.assembly.project_context,
            fault_hook=fault_hook,
        )

    def confirmed_plan(self):
        return self.assembly.series_episode.confirm_creative_plan(
            {
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "sourcePlanRef": "source-plan-project-foundation-unit",
                "sourcePlanSchemaVersion": "creator.ai-director.plan.v1",
                "sourcePlanVersion": 1,
                "brief": valid_brief(),
                "sourcePlan": valid_plan(),
            }
        )

    def counts(self):
        series = self.assembly.series_episode.list_series(WORKSPACE)
        projects = self.assembly.project_context.list_projects(WORKSPACE)
        return len(series), len(projects), sum(len(item["episodes"]) for item in series)

    def test_success_reuses_domain_authorities_without_script_or_canonical_fact(self):
        plan = self.confirmed_plan()
        command = valid_command(
            episode={
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Episode 001",
            }
        )
        response = self.service().execute(WORKSPACE, command)
        result = response["foundation"]
        self.assertEqual((1, 1, 1), self.counts())
        self.assertEqual("COMPLETED", result["state"])
        self.assertEqual(
            result["series"]["seriesRef"],
            result["project"]["seriesRefs"][0],
        )
        detail = self.assembly.series_episode.get_episode(
            WORKSPACE,
            result["series"]["seriesRef"],
            result["episode"]["episodeRef"],
        )
        self.assertEqual(
            plan["creativePlanRef"],
            detail["confirmedPlanBinding"]["creativePlanRef"],
        )
        self.assertIsNone(
            self.assembly.script_studio.get_workspace(
                WORKSPACE,
                result["series"]["seriesRef"],
                result["episode"]["episodeRef"],
            )["script"]
        )
        # The assembly has no canonical target; success proves this command did
        # not invoke or require Canonical Registration.

    def test_project_only_and_optional_series_shapes_use_existing_project_contract(self):
        for index, project_type in enumerate(("standalone", "brand-film"), start=1):
            command = valid_command(
                key=f"project-only-{index}",
                project_type=project_type,
            )
            result = self.service().execute(WORKSPACE, command)["foundation"]
            self.assertIsNone(result["series"])
            self.assertIsNone(result["episode"])
            self.assertEqual([], result["project"]["seriesRefs"])

        optional = valid_command(key="optional-series", project_type="standalone")
        optional["series"] = {"title": "Optional Series", "description": ""}
        result = self.service().execute(WORKSPACE, optional)["foundation"]
        self.assertEqual(
            [result["series"]["seriesRef"]],
            result["project"]["seriesRefs"],
        )

    def test_exact_replay_is_stable_and_changed_replay_conflicts(self):
        service = self.service()
        first = service.execute(WORKSPACE, valid_command())
        replay = service.execute(WORKSPACE, valid_command())
        self.assertFalse(first["idempotentReplay"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(first["foundation"], replay["foundation"])
        self.assertEqual((1, 1, 0), self.counts())

        changed = valid_command()
        changed["project"]["title"] = "Changed"
        with self.assertRaises(ProjectFoundationApplicationError) as caught:
            service.execute(WORKSPACE, changed)
        self.assertEqual(
            ("project_foundation_idempotency_conflict", 409),
            (caught.exception.code, caught.exception.status),
        )
        self.assertEqual((1, 1, 0), self.counts())

    def test_every_precommit_fault_rolls_back_domain_facts_and_retains_pending(self):
        plan = self.confirmed_plan()
        episode = {
            "creativePlanRef": plan["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Episode 001",
        }
        for index, point in enumerate(
            (
                "after-intent-commit",
                "after-series-create",
                "after-project-create",
                "after-episode-create",
                "before-result-receipt-update",
            ),
            start=1,
        ):
            with self.subTest(point=point):
                command = valid_command(key=f"fault-{index}", episode=copy.deepcopy(episode))
                fault = _OneShotFault(point)
                with self.assertRaises(RuntimeError):
                    self.service(fault).execute(WORKSPACE, command)
                self.assertEqual((index - 1, index - 1, index - 1), self.counts())
                record = self.assembly.project_foundation_store.get_by_key(
                    WORKSPACE, command["idempotencyKey"]
                )
                self.assertEqual("PENDING", record.state)
                recovered = self.service().execute(WORKSPACE, command)
                self.assertTrue(recovered["recoveredFromPending"])
                self.assertEqual((index, index, index), self.counts())

    def test_postcommit_response_loss_replays_without_new_domain_facts(self):
        service = self.service(
            _OneShotFault("after-transaction-commit-before-http-response")
        )
        command = valid_command()
        with self.assertRaises(RuntimeError):
            service.execute(WORKSPACE, command)
        self.assertEqual((1, 1, 0), self.counts())
        replay = service.execute(WORKSPACE, command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual((1, 1, 0), self.counts())
        record = self.assembly.project_foundation_store.get_by_key(
            WORKSPACE, command["idempotencyKey"]
        )
        request_value, result = validate_project_foundation_record(record)
        self.assertEqual(PROFILE, request_value["contentProfileRef"])
        self.assertEqual(replay["foundation"], result)


if __name__ == "__main__":
    unittest.main()
