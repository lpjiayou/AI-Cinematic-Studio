from dataclasses import replace
from threading import Barrier, Event, Lock, Thread
import unittest

from services.v5_core_os.lifecycle_integrity import (
    AssemblyPoisonedError,
    BackendKind,
    InMemoryLifecycleState,
    LeaseRejectedError,
    LeaseState,
    LifecycleAssembly,
    LifecycleAssemblyIdentity,
    LifecycleLeaseView,
    LifecycleOperation,
    LifecycleRollbackError,
)
from services.v5_core_os.project_engine import ProjectPublicError
from services.v5_core_os.project_engine import create_in_memory_boundary as create_project_boundary
from services.v5_core_os.script_studio import create_in_memory_boundary as create_script_boundary
from services.v5_core_os.series_episode import SeriesEpisodePublicError
from services.v5_core_os.series_episode import create_in_memory_boundary as create_series_boundary
from services.v5_core_os.series_planning import create_in_memory_boundary as create_planning_boundary
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_script_studio_m3 import content_from_candidate


NOW = "2026-08-12T00:00:00.000Z"


class Refs:
    def __init__(self, *, fixed: bool = False):
        self.counts = {}
        self.fixed = fixed
        self.lock = Lock()

    def __call__(self, prefix):
        if self.fixed and prefix in {"series", "creative-plan", "episode", "script", "script-version"}:
            return f"{prefix}-fixed"
        with self.lock:
            self.counts[prefix] = self.counts.get(prefix, 0) + 1
            return f"{prefix}-{self.counts[prefix]}"


class BlockingJournal:
    """Deterministically pauses the next mutation while it owns the lifecycle lease."""

    def __init__(self):
        self._lock = Lock()
        self._armed = False
        self.entered = Event()
        self.release = Event()

    def arm(self):
        with self._lock:
            self._armed = True
            self.entered.clear()
            self.release.clear()

    def __call__(self, _undo):
        with self._lock:
            block = self._armed
            self._armed = False
        if block:
            self.entered.set()
            if not self.release.wait(5):
                raise TimeoutError("test did not release lifecycle mutation")


def seed_series(assembly, workspace="workspace-a", profile="profile-a"):
    return assembly.series_episode.create_series(
        {
            "workspaceRef": workspace,
            "contentProfileRef": profile,
            "title": "晚灯",
            "plannedEpisodeCount": 12,
        }
    )


def seed_episode(assembly, series, workspace="workspace-a"):
    plan = valid_plan()
    confirmed = assembly.series_episode.confirm_creative_plan(
        {
            "workspaceRef": workspace,
            "humanConfirmed": True,
            "sourcePlanRef": "director-plan",
            "sourcePlanSchemaVersion": plan["schemaVersion"],
            "sourcePlanVersion": 1,
            "brief": valid_brief(),
            "sourcePlan": plan,
        }
    )
    return assembly.series_episode.create_episode(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": confirmed["creativePlanRef"],
            "episodeNumber": 1,
            "title": "第1集",
        }
    )


def project_command(series, workspace="workspace-a", profile="profile-a"):
    return {
        "workspaceRef": workspace,
        "contentProfileRef": profile,
        "projectType": "series",
        "seriesRef": series["seriesRef"],
        "title": "晚灯制作",
        "aspectRatio": "9:16",
        "defaultDurationSec": 30,
        "plannedEpisodeCount": 12,
    }


def script_command(series, episode, workspace="workspace-a"):
    return {
        "workspaceRef": workspace,
        "seriesRef": series["seriesRef"],
        "episodeRef": episode["episodeRef"],
        "changeKind": "ai-generation",
        "content": content_from_candidate(),
    }


class LifecycleLeaseContractTests(unittest.TestCase):
    def setUp(self):
        identity = LifecycleAssemblyIdentity("assembly-a", BackendKind.IN_MEMORY, "memory:a")
        self.state = InMemoryLifecycleState(identity)

    def test_missing_and_forged_lease_are_rejected(self):
        for value in (None, object()):
            with self.subTest(value=value), self.assertRaises(LeaseRejectedError):
                self.state.validate_lease(
                    value,
                    workspace_ref="workspace-a",
                    allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
                )
        forged = LifecycleLeaseView(
            "issuer-forged",
            self.state.identity,
            "nonce-forged",
            1,
            "workspace-a",
            LifecycleOperation.CREATE_PROJECT,
            LeaseState.ACTIVE,
        )
        with self.assertRaises(LeaseRejectedError):
            self.state.validate_lease(
                forged,
                workspace_ref="workspace-a",
                allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
            )

    def test_expired_terminal_workspace_operation_and_assembly_leases_are_rejected(self):
        with self.state.lease(
            workspace_ref="workspace-a", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            self.state.validate_lease(
                lease,
                workspace_ref="workspace-a",
                allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
            )
            with self.assertRaises(LeaseRejectedError):
                self.state.validate_lease(
                    lease,
                    workspace_ref="workspace-b",
                    allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
                )
            with self.assertRaises(LeaseRejectedError):
                self.state.validate_lease(
                    lease,
                    workspace_ref="workspace-a",
                    allowed_operations=frozenset({LifecycleOperation.DELETE_SERIES}),
                )
            terminal = replace(lease, state=LeaseState.COMMITTED)
            with self.assertRaises(LeaseRejectedError):
                self.state.validate_lease(
                    terminal,
                    workspace_ref="workspace-a",
                    allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
                )
            other = InMemoryLifecycleState(
                LifecycleAssemblyIdentity("assembly-b", BackendKind.IN_MEMORY, "memory:b")
            )
            with self.assertRaises(LeaseRejectedError):
                other.validate_lease(
                    lease,
                    workspace_ref="workspace-a",
                    allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
                )
        with self.assertRaises(LeaseRejectedError):
            self.state.validate_lease(
                lease,
                workspace_ref="workspace-a",
                allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
            )

    def test_nested_and_cross_thread_lease_are_rejected(self):
        errors = []
        with self.state.lease(
            workspace_ref="workspace-a", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(LeaseRejectedError):
                with self.state.lease(
                    workspace_ref="workspace-a", operation=LifecycleOperation.DELETE_SERIES
                ):
                    pass

            def other_thread():
                try:
                    self.state.validate_lease(
                        lease,
                        workspace_ref="workspace-a",
                        allowed_operations=frozenset({LifecycleOperation.CREATE_PROJECT}),
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = Thread(target=other_thread)
            thread.start()
            thread.join(5)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], LeaseRejectedError)


class InMemoryRollbackTests(unittest.TestCase):
    def _state(self, registrar=None):
        return InMemoryLifecycleState(
            LifecycleAssemblyIdentity("assembly", BackendKind.IN_MEMORY, "memory:test"),
            journal_registrar=registrar,
        )

    def test_journal_registration_failure_performs_no_mutation(self):
        data = {"value": 1}
        state = self._state(lambda _undo: (_ for _ in ()).throw(RuntimeError("journal")))
        state.register_resource("data", lambda: dict(data), lambda value: data.update(value))
        called = []
        with state.lease(
            workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(RuntimeError):
                state.apply_preimaged(lease, lambda: called.append(True))
        self.assertEqual(called, [])
        self.assertEqual(data, {"value": 1})
        self.assertEqual(state.state.value, "ready")

    def test_partial_mutation_is_rolled_back_to_complete_preimage(self):
        data = {"one": 1, "two": 2}
        state = self._state()

        def restore(value):
            data.clear()
            data.update(value)

        state.register_resource("data", lambda: dict(data), restore)

        def mutate():
            data["one"] = 99
            data.pop("two")
            data["three"] = 3
            raise RuntimeError("partial mutation")

        with state.lease(
            workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(RuntimeError):
                state.apply_preimaged(lease, mutate)
        self.assertEqual(data, {"one": 1, "two": 2})
        self.assertEqual(state.state.value, "ready")

    def test_undo_failure_poisoned_assembly_rejects_reads_writes_and_new_leases(self):
        data = {"value": 1}
        state = self._state()

        def restore(_value):
            raise RuntimeError("undo failed")

        state.register_resource("data", lambda: dict(data), restore)
        with state.lease(
            workspace_ref="workspace", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(LifecycleRollbackError):
                state.apply_preimaged(
                    lease,
                    lambda: (data.update(value=2), (_ for _ in ()).throw(RuntimeError("write")))[1],
                )
        self.assertEqual(state.diagnostic_snapshot()["state"], "poisoned")
        with self.assertRaises(AssemblyPoisonedError):
            state.assert_ready()
        with self.assertRaises(AssemblyPoisonedError):
            with state.lease(
                workspace_ref="workspace", operation=LifecycleOperation.DELETE_SERIES
            ):
                pass

    def test_poisoned_assembly_rejects_all_public_boundaries_but_allows_diagnostics(self):
        assembly = LifecycleAssembly.in_memory(ref_factory=Refs(), clock=lambda: NOW)
        assembly.state.register_resource(
            "faulting-resource",
            lambda: {"value": 1},
            lambda _snapshot: (_ for _ in ()).throw(RuntimeError("undo failed")),
        )
        with assembly.state.lease(
            workspace_ref="workspace-a", operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(LifecycleRollbackError):
                assembly.state.apply_preimaged(
                    lease,
                    lambda: (_ for _ in ()).throw(RuntimeError("mutation failed")),
                )

        ordinary_calls = (
            lambda: assembly.series_episode.list_series("workspace-a"),
            lambda: assembly.project_context.list_projects("workspace-a"),
            lambda: assembly.script_studio.get_workspace(
                "workspace-a", "series-a", "episode-a"
            ),
            lambda: assembly.series_planning.get_workspace(
                "workspace-a", "project-a", "series-a"
            ),
        )
        for call in ordinary_calls:
            with self.subTest(call=call), self.assertRaises(AssemblyPoisonedError):
                call()
        self.assertEqual(assembly.diagnostic_snapshot()["state"], "poisoned")


class LifecyclePublicBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.hook = BlockingJournal()
        self.assembly = LifecycleAssembly.in_memory(
            ref_factory=Refs(), clock=lambda: NOW, journal_registrar=self.hook
        )

    def _run_race(self, first_call, second_call):
        started = Barrier(2)
        results = {}

        def run(name, call, wait_for_hook=False):
            started.wait()
            if wait_for_hook:
                self.assertTrue(self.hook.entered.wait(5))
            try:
                results[name] = ("ok", call())
            except BaseException as exc:
                results[name] = ("error", exc)

        self.hook.arm()
        first = Thread(target=run, args=("first", first_call))
        second = Thread(target=run, args=("second", second_call, True))
        first.start()
        second.start()
        self.assertTrue(self.hook.entered.wait(5))
        self.hook.release.set()
        first.join(5)
        second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        return results

    def test_project_write_first_blocks_series_delete_without_orphan(self):
        series = seed_series(self.assembly)
        result = self._run_race(
            lambda: self.assembly.project_context.create_project(project_command(series)),
            lambda: self.assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
        )
        self.assertEqual(result["first"][0], "ok")
        self.assertIsInstance(result["second"][1], SeriesEpisodePublicError)
        self.assertEqual(result["second"][1].code, "dependent_project_exists")
        project = self.assembly.project_context.get_project_for_series(
            "workspace-a", series["seriesRef"]
        )
        self.assertIsNotNone(project)
        self.assertEqual(
            self.assembly.series_episode.get_series("workspace-a", series["seriesRef"])["seriesRef"],
            series["seriesRef"],
        )

    def test_series_delete_first_rejects_project_write_without_orphan(self):
        series = seed_series(self.assembly)
        result = self._run_race(
            lambda: self.assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
            lambda: self.assembly.project_context.create_project(project_command(series)),
        )
        self.assertEqual(result["first"][0], "ok")
        self.assertIsInstance(result["second"][1], ProjectPublicError)
        self.assertEqual(result["second"][1].code, "not_found")
        self.assertIsNone(
            self.assembly.project_context.get_project_for_series("workspace-a", series["seriesRef"])
        )
        with self.assertRaises(SeriesEpisodePublicError):
            self.assembly.series_episode.get_series("workspace-a", series["seriesRef"])

    def test_script_write_first_blocks_episode_delete_without_orphan(self):
        series = seed_series(self.assembly)
        episode = seed_episode(self.assembly, series)
        result = self._run_race(
            lambda: self.assembly.script_studio.create_version(script_command(series, episode)),
            lambda: self.assembly.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            ),
        )
        self.assertEqual(result["first"][0], "ok")
        self.assertIsInstance(result["second"][1], SeriesEpisodePublicError)
        self.assertEqual(result["second"][1].code, "dependent_script_exists")
        workspace = self.assembly.script_studio.get_workspace(
            "workspace-a", series["seriesRef"], episode["episodeRef"]
        )
        self.assertIsNotNone(workspace["script"])
        self.assertEqual(
            self.assembly.series_episode.get_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )["episodeRef"],
            episode["episodeRef"],
        )

    def test_episode_delete_first_rejects_script_write_without_orphan(self):
        series = seed_series(self.assembly)
        episode = seed_episode(self.assembly, series)
        result = self._run_race(
            lambda: self.assembly.series_episode.delete_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            ),
            lambda: self.assembly.script_studio.create_version(script_command(series, episode)),
        )
        self.assertEqual(result["first"][0], "ok")
        self.assertEqual(result["second"][0], "error")
        with self.assertRaises(SeriesEpisodePublicError):
            self.assembly.series_episode.get_episode(
                "workspace-a", series["seriesRef"], episode["episodeRef"]
            )

    def test_script_version_append_and_series_delete_never_orphan(self):
        series = seed_series(self.assembly)
        episode = seed_episode(self.assembly, series)
        first = self.assembly.script_studio.create_version(script_command(series, episode))
        append = script_command(series, episode)
        append["content"] = {
            key: first["scriptVersion"][key]
            for key in ("title", "logline", "synopsis", "targetDurationSec", "scenes")
        }
        append.update(
            {
                "changeKind": "manual-edit",
                "scriptRef": first["script"]["scriptRef"],
                "baseScriptVersionRef": first["scriptVersion"]["scriptVersionRef"],
            }
        )
        result = self._run_race(
            lambda: self.assembly.script_studio.create_version(append),
            lambda: self.assembly.series_episode.delete_series("workspace-a", series["seriesRef"]),
        )
        self.assertEqual(result["first"][0], "ok")
        self.assertEqual(result["second"][1].code, "dependent_script_exists")
        workspace = self.assembly.script_studio.get_workspace(
            "workspace-a", series["seriesRef"], episode["episodeRef"]
        )
        self.assertEqual(len(workspace["versions"]), 2)

    def test_project_dependency_has_priority_over_script_dependency(self):
        series = seed_series(self.assembly)
        episode = seed_episode(self.assembly, series)
        self.assembly.project_context.create_project(project_command(series))
        self.assembly.script_studio.create_version(script_command(series, episode))
        with self.assertRaises(SeriesEpisodePublicError) as error:
            self.assembly.series_episode.delete_series("workspace-a", series["seriesRef"])
        self.assertEqual(error.exception.code, "dependent_project_exists")
        self.assertEqual(error.exception.status, 409)

    def test_equal_refs_in_two_workspaces_do_not_cross_block(self):
        assembly = LifecycleAssembly.in_memory(ref_factory=Refs(fixed=True), clock=lambda: NOW)
        series_a = seed_series(assembly, "workspace-a", "profile-a")
        episode_a = seed_episode(assembly, series_a, "workspace-a")
        series_b = seed_series(assembly, "workspace-b", "profile-b")
        episode_b = seed_episode(assembly, series_b, "workspace-b")
        assembly.script_studio.create_version(script_command(series_b, episode_b, "workspace-b"))
        deletion = assembly.series_episode.delete_episode(
            "workspace-a", series_a["seriesRef"], episode_a["episodeRef"]
        )
        self.assertEqual(deletion["deletedEpisodeCount"], 1)
        self.assertEqual(
            assembly.series_episode.get_episode(
                "workspace-b", series_b["seriesRef"], episode_b["episodeRef"]
            )["workspaceRef"],
            "workspace-b",
        )

    def test_default_in_memory_factories_reuse_one_authoritative_assembly(self):
        series_boundary = create_series_boundary()
        project_boundary = create_project_boundary(series_boundary)
        script_boundary = create_script_boundary(series_boundary)
        planning_boundary = create_planning_boundary(project_boundary)
        assembly = series_boundary._lifecycle_assembly_or_none()
        self.assertIs(project_boundary, assembly.project_context)
        self.assertIs(script_boundary, assembly.script_studio)
        self.assertIs(planning_boundary, assembly.series_planning)

        series = series_boundary.create_series(
            {
                "workspaceRef": "workspace-a",
                "contentProfileRef": "profile-a",
                "title": "Shared assembly",
                "plannedEpisodeCount": 1,
            }
        )
        project_boundary.create_project(project_command(series))
        with self.assertRaises(SeriesEpisodePublicError) as error:
            series_boundary.delete_series("workspace-a", series["seriesRef"])
        self.assertEqual(error.exception.code, "dependent_project_exists")


if __name__ == "__main__":
    unittest.main()
