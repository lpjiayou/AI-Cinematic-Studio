import copy
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.script_studio import ScriptStudioPublicError
from services.v5_core_os.series_intelligence import M6Scope
from tests.unit.test_series_intelligence_consumer_m6_p3 import (
    NOW,
    in_memory_consumer,
    read_baseline,
    seed_consumer_on,
)
from tests.unit.test_series_intelligence_m6 import (
    ApprovalAuthority,
    Refs,
    ScopeAuthority,
    base_command,
    bible_content,
    character_content,
    scoped_outbox,
)


def sqlite_assembly(path, *, initialize=False):
    return LifecycleAssembly.sqlite(
        path,
        initialize_or_upgrade=initialize,
        ref_factory=Refs(),
        clock=lambda: NOW,
        m6_scope_authority=ScopeAuthority(),
        m6_approval_authority=ApprovalAuthority(),
    )


class SwitchingScopeAuthority:
    def __init__(self):
        self.business_domain = "series-production-a"
        self.tenant_id = "tenant-consumer-a"

    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope(
            self.business_domain,
            self.tenant_id,
            workspace_ref,
            project_ref,
            series_ref,
        )


class CreatorSeriesIntelligenceConsumerIntegrationTests(unittest.TestCase):
    def test_exact_real_scope_reaches_m3_and_cross_scope_real_refs_fail_without_write(self):
        first = in_memory_consumer()
        assembly = first["assembly"]
        other = seed_consumer_on(
            assembly,
            workspace=first["context"]["workspaceRef"],
            plan_index=2,
        )
        other_workspace = seed_consumer_on(
            assembly,
            workspace="workspace-consumer-other",
            plan_index=2,
        )
        expected = read_baseline(first)
        self.assertEqual(expected["projectRef"], first["context"]["projectRef"])
        before = assembly.series_intelligence.diagnostic_snapshot()
        before_outbox = {
            key: scoped_outbox(assembly.series_intelligence, seed["context"])
            for key, seed in (
                ("first", first), ("other", other),
                ("other_workspace", other_workspace),
            )
        }
        self.assertEqual(
            assembly.project_context.get_project(
                first["context"]["workspaceRef"], first["context"]["projectRef"]
            )["title"],
            assembly.project_context.get_project(
                other["context"]["workspaceRef"], other["context"]["projectRef"]
            )["title"],
        )
        self.assertEqual(
            assembly.series_episode.get_series(
                first["context"]["workspaceRef"], first["context"]["seriesRef"]
            )["title"],
            assembly.series_episode.get_series(
                other["context"]["workspaceRef"], other["context"]["seriesRef"]
            )["title"],
        )
        self.assertEqual(
            assembly.series_episode.get_episode(
                first["context"]["workspaceRef"],
                first["context"]["seriesRef"],
                first["context"]["episodeRef"],
            )["title"],
            assembly.series_episode.get_episode(
                other["context"]["workspaceRef"],
                other["context"]["seriesRef"],
                other["context"]["episodeRef"],
            )["title"],
        )
        invalid_real_scopes = (
            (
                first["context"]["workspaceRef"],
                first["context"]["projectRef"],
                other["context"]["seriesRef"],
                other["context"]["episodeRef"],
            ),
            (
                other_workspace["context"]["workspaceRef"],
                first["context"]["projectRef"],
                first["context"]["seriesRef"],
                first["context"]["episodeRef"],
            ),
            (
                first["context"]["workspaceRef"],
                first["context"]["projectRef"],
                first["context"]["seriesRef"],
                other["context"]["episodeRef"],
            ),
        )
        for refs in invalid_real_scopes:
            with self.assertRaises(ScriptStudioPublicError) as error:
                assembly.script_studio.get_m6_episode_baseline(*refs)
            self.assertEqual(error.exception.code, "m6_consumer_authority_unavailable")
        self.assertEqual(assembly.series_intelligence.diagnostic_snapshot(), before)
        self.assertEqual(
            scoped_outbox(assembly.series_intelligence, first["context"]),
            before_outbox["first"],
        )
        self.assertEqual(
            scoped_outbox(assembly.series_intelligence, other["context"]),
            before_outbox["other"],
        )
        self.assertEqual(
            scoped_outbox(assembly.series_intelligence, other_workspace["context"]),
            before_outbox["other_workspace"],
        )

    def test_business_domain_and_tenant_scope_changes_cannot_read_existing_baseline(self):
        authority = SwitchingScopeAuthority()
        assembly = LifecycleAssembly.in_memory(
            ref_factory=Refs(),
            clock=lambda: NOW,
            m6_scope_authority=authority,
            m6_approval_authority=ApprovalAuthority(),
        )
        seed = seed_consumer_on(assembly)
        accepted = read_baseline(seed)
        before = assembly.series_intelligence.diagnostic_snapshot()

        authority.tenant_id = "tenant-consumer-b"
        with self.assertRaises(ScriptStudioPublicError) as tenant_error:
            read_baseline(seed)
        self.assertEqual(tenant_error.exception.code, "m6_baseline_not_available")

        authority.tenant_id = "tenant-consumer-a"
        authority.business_domain = "series-production-b"
        with self.assertRaises(ScriptStudioPublicError) as domain_error:
            read_baseline(seed)
        self.assertEqual(domain_error.exception.code, "m6_baseline_not_available")

        authority.business_domain = "series-production-a"
        self.assertEqual(read_baseline(seed), accepted)
        self.assertEqual(assembly.series_intelligence.diagnostic_snapshot(), before)

    def test_in_memory_sqlite_and_restart_return_identical_read_only_input(self):
        memory = in_memory_consumer()
        memory_result = read_baseline(memory)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "consumer.sqlite3"
            first = sqlite_assembly(path, initialize=True)
            sqlite_seed = seed_consumer_on(first)
            before = first.series_intelligence.diagnostic_snapshot()
            before_outbox = scoped_outbox(first.series_intelligence, sqlite_seed["context"])
            sqlite_result = read_baseline(sqlite_seed)
            self.assertEqual(sqlite_result, memory_result)
            self.assertEqual(first.series_intelligence.diagnostic_snapshot(), before)
            self.assertEqual(
                scoped_outbox(first.series_intelligence, sqlite_seed["context"]),
                before_outbox,
            )

            restarted = sqlite_assembly(path)
            restarted_seed = {"assembly": restarted, "context": sqlite_seed["context"]}
            self.assertEqual(read_baseline(restarted_seed), sqlite_result)
            self.assertEqual(restarted.series_intelligence.diagnostic_snapshot(), before)
            self.assertEqual(
                scoped_outbox(restarted.series_intelligence, sqlite_seed["context"]),
                before_outbox,
            )

    def test_in_memory_and_sqlite_reads_hold_one_coherent_snapshot_against_m5_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coherent-consumer.sqlite3"
            sqlite = sqlite_assembly(path, initialize=True)
            seeds = (
                ("in-memory", in_memory_consumer()),
                ("sqlite", seed_consumer_on(sqlite)),
            )
            for label, seed in seeds:
                with self.subTest(backend=label):
                    assembly = seed["assembly"]
                    context = seed["context"]
                    before = read_baseline(seed)
                    current = seed["confirmedBound"]
                    replacement = (
                        assembly.series_planning.create_episode_plan_item_binding_version({
                            "workspaceRef": context["workspaceRef"],
                            "projectRef": context["projectRef"],
                            "seriesRef": context["seriesRef"],
                            "seriesPlanRef": current["seriesPlanRef"],
                            "expectedPlanVersion": current["version"],
                            "episodePlanItemBindings": [seed["binding"]],
                        })
                    )
                    captured = Event()
                    release = Event()
                    writer_done = Event()
                    outcome = {}
                    original_context = assembly.project_context.build_context

                    def paused_context(*args):
                        result = original_context(*args)
                        captured.set()
                        if not release.wait(10):
                            raise TimeoutError("coherent consumer read was not released")
                        return result

                    def read_current():
                        try:
                            outcome["read"] = read_baseline(seed)
                        except BaseException as error:
                            outcome["readError"] = error

                    def confirm_replacement():
                        try:
                            assembly.series_planning.confirm_version({
                                "workspaceRef": context["workspaceRef"],
                                "seriesPlanRef": replacement["plan"]["seriesPlanRef"],
                                "seriesPlanVersionRef": replacement["version"][
                                    "seriesPlanVersionRef"
                                ],
                                "expectedPlanVersion": replacement["plan"]["version"],
                                "humanConfirmed": True,
                            })
                        except BaseException as error:
                            outcome["writeError"] = error
                        finally:
                            writer_done.set()

                    assembly.project_context.build_context = paused_context
                    reader = Thread(target=read_current)
                    writer = Thread(target=confirm_replacement)
                    reader.start()
                    try:
                        self.assertTrue(captured.wait(10))
                        writer.start()
                        self.assertFalse(writer_done.wait(0.05))
                    finally:
                        release.set()
                        reader.join(10)
                        writer.join(10)
                        assembly.project_context.build_context = original_context
                    self.assertFalse(reader.is_alive())
                    self.assertFalse(writer.is_alive())
                    self.assertNotIn("readError", outcome, repr(outcome.get("readError")))
                    self.assertNotIn("writeError", outcome, repr(outcome.get("writeError")))
                    self.assertEqual(outcome["read"], before)
                    with self.assertRaises(ScriptStudioPublicError) as stale:
                        read_baseline(seed)
                    self.assertEqual(stale.exception.code, "m6_baseline_stale")

    def test_baseline_replacement_returns_new_current_input_without_mutating_old_dto(self):
        seed = in_memory_consumer()
        assembly = seed["assembly"]
        context = seed["context"]
        original = read_baseline(seed)
        preserved = copy.deepcopy(original)
        replacement_content = bible_content()
        replacement_content["worldRules"][0]["statement"] = "灯只通过光影表达"
        bible = assembly.series_intelligence.create_bible_version({
            **base_command(context, "replace-consumer-bible"),
            "seriesBibleRef": seed["bible"]["root"]["seriesBibleRef"],
            "expectedRevision": seed["bible"]["root"]["revision"],
            "candidate": True,
            "content": replacement_content,
        })
        bible = assembly.series_intelligence.confirm_bible_version({
            **base_command(context, "confirm-replacement-consumer-bible"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": bible["root"]["revision"],
            "approvalRef": "approval-human",
        })
        source = assembly.series_planning.get_confirmed_m6_source_snapshot(
            context["workspaceRef"], context["projectRef"], context["seriesRef"]
        )
        character = assembly.series_intelligence.create_character_version({
            **base_command(context, "replace-consumer-characters"),
            "characterContinuityRef": seed["characters"]["root"][
                "characterContinuityRef"
            ],
            "expectedRevision": seed["characters"]["root"]["revision"],
            "candidate": True,
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "content": character_content(
                [item["episodePlanItemRef"] for item in source["episodePlanItems"]]
            ),
        })
        character = assembly.series_intelligence.confirm_character_version({
            **base_command(context, "confirm-replacement-consumer-characters"),
            "characterContinuityRef": character["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": character["version"][
                "characterContinuityVersionRef"
            ],
            "expectedRevision": character["root"]["revision"],
            "approvalRef": "approval-human",
        })
        replacement = assembly.series_intelligence.activate_baseline({
            **base_command(context, "activate-replacement-consumer-baseline"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": character["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": character["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": seed["snapshot"]["activationRevision"],
            "approvalRef": "approval-human",
        })
        current = read_baseline(seed)
        self.assertEqual(original, preserved)
        self.assertNotEqual(
            current["m6BaselineSnapshotRef"], original["m6BaselineSnapshotRef"]
        )
        self.assertEqual(
            current["m6BaselineSnapshotRef"], replacement["m6BaselineSnapshotRef"]
        )
        self.assertEqual(current["activationRevision"], 2)
        self.assertEqual(current["compatibility"], "CURRENT")
        self.assertEqual(
            current["applicableFacts"]["worldRules"][0]["statement"],
            "灯只通过光影表达",
        )


if __name__ == "__main__":
    unittest.main()
