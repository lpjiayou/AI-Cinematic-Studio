"""Scoped identity and repository parity for confirmed Creative Plan commands."""

from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import threading
import unittest

from services.v5_core_os.series_episode.foundation import (
    CreativePlanIdempotencyConflictError,
    InMemorySeriesEpisodeAdapter,
    SeriesEpisodeError,
    SeriesEpisodeService,
    _confirmed_plan_semantics,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


def confirmation_command():
    return {
        "workspaceRef": "workspace-e3b-unit", "humanConfirmed": True,
        "sourcePlanRef": "source-e3b-1", "sourcePlanVersion": 1,
        "sourcePlanSchemaVersion": "creator.ai-director.plan.v1",
        "brief": valid_brief(), "sourcePlan": valid_plan(), "idempotencyKey": "e3b-command",
    }


class ConfirmedCreativePlanIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemorySeriesEpisodeAdapter()
        self.service = SeriesEpisodeService(self.repository)
        self.command = confirmation_command()

    def confirm(self, command=None):
        return self.service.confirm_creative_plan_idempotently(command or self.command)

    def test_versioned_identity_golden_vectors_and_separate_namespaces(self):
        explicit = self.confirm()["confirmedPlan"]["creativePlanRef"]
        legacy = dict(self.command)
        del legacy["idempotencyKey"]
        source = self.confirm(legacy)["confirmedPlan"]["creativePlanRef"]
        self.assertEqual(explicit, "creative-plan-d0abe06d933efe0621b3cc9939aa273ad0923ac5ae221aabe85879d1f9d4d0d2")
        self.assertEqual(source, "creative-plan-898dba0e5834e9a7ee17861e7b47870dacbbcbe9491b460b9fd2f81717071851")
        self.assertNotEqual(explicit, source)
        for ref in (explicit, source):
            self.assertRegex(ref, r"^creative-plan-[0-9a-f]{64}$")
            self.assertNotIn(self.command["idempotencyKey"], ref)

    def test_ref_does_not_depend_on_clock_ref_factory_or_service_instance(self):
        first = self.confirm()
        def forbidden_factory(_prefix):
            self.fail("idempotent confirmation must not allocate a random ref")
        restarted = SeriesEpisodeService(self.repository, clock=lambda: "2099-01-01", ref_factory=forbidden_factory)
        replay = restarted.confirm_creative_plan_idempotently(copy.deepcopy(self.command))
        self.assertEqual(first["confirmedPlan"], replay["confirmedPlan"])
        self.assertFalse(first["idempotentReplay"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(len(self.repository._plans), 1)

    def test_invalid_keys_fail_before_repository_mutation(self):
        for key in (None, True, 7, 1.5, [], {}, "", " ", " x", "x ", ".", "..",
                    "a/b", "a\\b", "a\n", "a\x00b", "a\x7fb", "a\u200bb", "x" * 201):
            with self.subTest(key_type=type(key).__name__, representation=repr(key)):
                with self.assertRaises(SeriesEpisodeError) as caught:
                    self.confirm({**self.command, "idempotencyKey": key})
                self.assertEqual(caught.exception.code, "invalid_request")
                self.assertEqual(self.repository._plans, {})

    def test_printable_unicode_and_maximum_key_are_not_trimmed_or_coerced(self):
        for key in ("确认 操作", "x" * 200):
            first = self.confirm({**self.command, "idempotencyKey": key})
            replay = self.confirm({**self.command, "idempotencyKey": key})
            self.assertEqual(first["confirmedPlan"], replay["confirmedPlan"])
        self.assertEqual(len(self.repository._plans), 2)

    def test_comparison_excludes_timestamp_and_ref_but_includes_every_semantic_field(self):
        result = self.confirm()["confirmedPlan"]
        record = self.repository.get_confirmed_plan(self.command["workspaceRef"], result["creativePlanRef"])
        semantics = _confirmed_plan_semantics(record)
        self.assertEqual(semantics, _confirmed_plan_semantics(replace(record, confirmedAt="later", creativePlanRef="other")))
        for field, value in {
            "sourcePlanRef": "other", "sourcePlanSchemaVersion": "other", "sourcePlanVersion": 2,
            "briefJson": "{}", "sourcePlanJson": "{}", "confirmationStatus": "other", "version": 2,
        }.items():
            with self.subTest(field=field):
                self.assertNotEqual(semantics, _confirmed_plan_semantics(replace(record, **{field: value})))

    def test_changed_request_conflicts_and_keeps_the_original_record(self):
        first = self.confirm()["confirmedPlan"]
        for field, value in {
            "sourcePlanRef": "other", "sourcePlanVersion": 2,
            "brief": {**valid_brief(), "theme": "different"},
            "sourcePlan": {**valid_plan(), "storyDirection": {**valid_plan()["storyDirection"], "title": "different"}},
        }.items():
            with self.subTest(field=field):
                with self.assertRaises(CreativePlanIdempotencyConflictError):
                    self.confirm({**self.command, field: value})
                self.assertEqual(self.confirm()["confirmedPlan"], first)
                self.assertEqual(len(self.repository._plans), 1)

    def test_canonical_key_order_replays_and_returned_mapping_is_detached(self):
        first = self.confirm()["confirmedPlan"]
        command = copy.deepcopy(self.command)
        command["brief"] = dict(reversed(list(command["brief"].items())))
        command["sourcePlan"] = dict(reversed(list(command["sourcePlan"].items())))
        replay = self.confirm(command)
        self.assertEqual(first, replay["confirmedPlan"])
        replay["confirmedPlan"]["brief"]["theme"] = "caller mutation"
        self.assertEqual(self.confirm()["confirmedPlan"], first)

    def test_source_identity_content_change_conflicts_and_version_change_is_independent(self):
        legacy = dict(self.command)
        del legacy["idempotencyKey"]
        first = self.confirm(legacy)
        with self.assertRaises(CreativePlanIdempotencyConflictError):
            self.confirm({**legacy, "brief": {**legacy["brief"], "theme": "changed"}})
        changed_version = self.confirm({**legacy, "sourcePlanVersion": 2})
        self.assertNotEqual(first["confirmedPlan"]["creativePlanRef"], changed_version["confirmedPlan"]["creativePlanRef"])

    def _concurrent(self, changed):
        barrier = threading.Barrier(2)
        commands = [self.command, copy.deepcopy(self.command)]
        if changed:
            commands[1]["brief"]["theme"] = "competing command"
        services = [SeriesEpisodeService(self.repository), SeriesEpisodeService(self.repository)]
        def execute(index):
            barrier.wait(timeout=5)
            try:
                return services[index].confirm_creative_plan_idempotently(commands[index])
            except CreativePlanIdempotencyConflictError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(execute, range(2)))
        self.assertEqual(len(self.repository._plans), 1)
        return results

    def test_in_memory_concurrent_exact_replay_uses_the_winner(self):
        first, second = self._concurrent(False)
        self.assertEqual(first["confirmedPlan"], second["confirmedPlan"])
        self.assertEqual({first["idempotentReplay"], second["idempotentReplay"]}, {False, True})

    def test_in_memory_concurrent_changed_replay_conflicts(self):
        results = self._concurrent(True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertIn("creative_plan_idempotency_conflict", results)

    def test_internal_non_idempotent_method_preserves_random_ref_behavior(self):
        first = self.service.confirm_creative_plan(self.command)
        second = self.service.confirm_creative_plan(self.command)
        self.assertNotEqual(first["creativePlanRef"], second["creativePlanRef"])
        self.assertNotIn("idempotentReplay", first)
        self.assertEqual(len(self.repository._plans), 2)

    def test_invalid_source_version_and_nonfinite_content_write_nothing(self):
        for version in (0, -1, True, 1.0, "1", None):
            with self.subTest(version=version), self.assertRaises(SeriesEpisodeError):
                self.confirm({**self.command, "sourcePlanVersion": version})
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(SeriesEpisodeError):
                self.confirm({**self.command, "brief": {"invalid": value}})
        self.assertEqual(self.repository._plans, {})
