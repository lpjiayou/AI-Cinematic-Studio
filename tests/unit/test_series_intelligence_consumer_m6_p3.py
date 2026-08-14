import copy
import unittest

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.script_studio import ScriptStudioPublicError
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_intelligence_m6 import (
    ApprovalAuthority,
    Refs,
    ScopeAuthority,
    base_command,
    confirmed_components,
    scoped_outbox,
)
from tests.unit.test_series_planning_m5 import valid_candidate


NOW = "2026-08-14T00:00:00.000Z"


def create_episode(assembly, workspace_ref, series_ref, episode_number=1):
    source = valid_plan()
    confirmed = assembly.series_episode.confirm_creative_plan({
        "workspaceRef": workspace_ref,
        "humanConfirmed": True,
        "sourcePlanRef": f"source-plan-consumer-{episode_number}",
        "sourcePlanSchemaVersion": source["schemaVersion"],
        "sourcePlanVersion": 1,
        "brief": valid_brief(),
        "sourcePlan": source,
    })
    return assembly.series_episode.create_episode({
        "workspaceRef": workspace_ref,
        "seriesRef": series_ref,
        "creativePlanRef": confirmed["creativePlanRef"],
        "episodeNumber": episode_number,
        "title": f"Consumer Episode {episode_number}",
    })


def seed_consumer_on(
    assembly,
    *,
    workspace="workspace-consumer",
    plan_index=1,
    activate=True,
    bind=True,
):
    series = assembly.series_episode.create_series({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "title": "Consumer Series",
        "plannedEpisodeCount": 4,
    })
    project = assembly.project_context.create_project({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "projectType": "series",
        "seriesRef": series["seriesRef"],
        "title": "Consumer Project",
        "plannedEpisodeCount": 4,
    })
    initial = assembly.series_planning.confirm_candidate({
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "humanConfirmed": True,
        "candidate": valid_candidate(4),
    })
    episode = create_episode(assembly, workspace, series["seriesRef"])
    binding = {
        "episodeRef": episode["episodeRef"],
        "episodePlanItemRef": initial["version"]["episodePlanItems"][plan_index][
            "episodePlanItemRef"
        ],
    }
    context = {
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "episodeRef": episode["episodeRef"],
    }
    if not bind:
        return {"assembly": assembly, "context": context, "initial": initial}
    bound = assembly.series_planning.create_episode_plan_item_binding_version({
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "seriesPlanRef": initial["plan"]["seriesPlanRef"],
        "expectedPlanVersion": initial["plan"]["version"],
        "episodePlanItemBindings": [binding],
    })
    confirmed_bound = assembly.series_planning.confirm_version({
        "workspaceRef": workspace,
        "seriesPlanRef": bound["plan"]["seriesPlanRef"],
        "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
        "expectedPlanVersion": bound["plan"]["version"],
        "humanConfirmed": True,
    })
    result = {
        "assembly": assembly,
        "context": context,
        "initial": initial,
        "bound": bound,
        "confirmedBound": confirmed_bound,
        "binding": binding,
    }
    if activate:
        bible, characters = confirmed_components(assembly, context)
        snapshot = assembly.series_intelligence.activate_baseline({
            **base_command(context, "activate-consumer-baseline"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        })
        result.update({"bible": bible, "characters": characters, "snapshot": snapshot})
    return result


def in_memory_consumer(*, plan_index=1, activate=True):
    assembly = LifecycleAssembly.in_memory(
        ref_factory=Refs(),
        clock=lambda: NOW,
        m6_scope_authority=ScopeAuthority(),
        m6_approval_authority=ApprovalAuthority(),
    )
    return seed_consumer_on(assembly, plan_index=plan_index, activate=activate)


def read_baseline(seed):
    context = seed["context"]
    return seed["assembly"].script_studio.get_m6_episode_baseline(
        context["workspaceRef"],
        context["projectRef"],
        context["seriesRef"],
        context["episodeRef"],
    )


class ActiveM6BaselineReaderTests(unittest.TestCase):
    def test_exact_closed_world_input_and_applicable_facts_are_returned(self):
        seed = in_memory_consumer(plan_index=1)
        result = read_baseline(seed)
        self.assertEqual(set(result), {
            "schemaVersion", "businessDomain", "tenantId", "workspaceRef",
            "projectRef", "seriesRef", "episodeRef", "episodePlanItemRef",
            "m6BaselineSnapshotRef", "activationRevision",
            "m6BaselineCanonicalDigest", "seriesPlanVersionRef",
            "seriesPlanVersionDigest", "seriesBibleVersionRef",
            "seriesBibleVersionDigest", "characterContinuityVersionRef",
            "characterContinuityVersionDigest", "compatibility", "applicableFacts",
        })
        self.assertEqual(result["schemaVersion"], "v5.m6-episode-baseline-input.v1")
        self.assertEqual(result["compatibility"], "CURRENT")
        self.assertEqual(result["episodeRef"], seed["context"]["episodeRef"])
        self.assertEqual(result["episodePlanItemRef"], seed["binding"]["episodePlanItemRef"])
        self.assertEqual(set(result["applicableFacts"]), {
            "episodePlanItem", "worldRules", "glossaryTerms", "locations",
            "factions", "props", "timelineEvents", "visualConstraints",
            "prohibitedNarrativePatterns", "characters", "stateIntervals",
            "relationships",
        })
        self.assertNotIn("identityBindings", result["applicableFacts"])
        self.assertEqual(
            [item["characterRef"] for item in result["applicableFacts"]["characters"]],
            ["character-lamp", "character-traveler"],
        )
        self.assertEqual(
            [item["intervalRef"] for item in result["applicableFacts"]["stateIntervals"]],
            ["interval-location-1"],
        )

    def test_end_exclusive_applicability_empty_array_and_relationship_rules(self):
        seed = in_memory_consumer(plan_index=3)
        facts = read_baseline(seed)["applicableFacts"]
        self.assertEqual(facts["stateIntervals"], [])
        self.assertEqual(
            [item["relationshipRef"] for item in facts["relationships"]],
            ["relationship-watch"],
        )

    def test_duplicate_reads_are_deterministic_immutable_and_write_neutral(self):
        seed = in_memory_consumer()
        assembly = seed["assembly"]
        before_diagnostic = assembly.series_intelligence.diagnostic_snapshot()
        before_outbox = scoped_outbox(assembly.series_intelligence, seed["context"])
        first = read_baseline(seed)
        second = read_baseline(seed)
        self.assertEqual(first, second)
        first["applicableFacts"]["worldRules"].clear()
        self.assertEqual(read_baseline(seed), second)
        self.assertEqual(assembly.series_intelligence.diagnostic_snapshot(), before_diagnostic)
        self.assertEqual(
            scoped_outbox(assembly.series_intelligence, seed["context"]), before_outbox
        )

    def test_absent_unbound_stale_lineage_and_authority_fail_closed(self):
        no_baseline = in_memory_consumer(activate=False)
        with self.assertRaises(ScriptStudioPublicError) as absent:
            read_baseline(no_baseline)
        self.assertEqual(absent.exception.code, "m6_baseline_not_available")

        unbound_assembly = LifecycleAssembly.in_memory(
            ref_factory=Refs(),
            clock=lambda: NOW,
            m6_scope_authority=ScopeAuthority(),
            m6_approval_authority=ApprovalAuthority(),
        )
        unbound = seed_consumer_on(unbound_assembly, activate=False, bind=False)
        with self.assertRaises(ScriptStudioPublicError) as mapping:
            read_baseline(unbound)
        self.assertEqual(mapping.exception.code, "m6_episode_mapping_unavailable")

        stale = in_memory_consumer()
        current = stale["confirmedBound"]
        replacement = stale["assembly"].series_planning.create_episode_plan_item_binding_version({
            "workspaceRef": stale["context"]["workspaceRef"],
            "projectRef": stale["context"]["projectRef"],
            "seriesRef": stale["context"]["seriesRef"],
            "seriesPlanRef": current["seriesPlanRef"],
            "expectedPlanVersion": current["version"],
            "episodePlanItemBindings": [stale["binding"]],
        })
        stale["assembly"].series_planning.confirm_version({
            "workspaceRef": stale["context"]["workspaceRef"],
            "seriesPlanRef": replacement["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": replacement["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": replacement["plan"]["version"],
            "humanConfirmed": True,
        })
        with self.assertRaises(ScriptStudioPublicError) as stale_error:
            read_baseline(stale)
        self.assertEqual(stale_error.exception.code, "m6_baseline_stale")

        corrupt = in_memory_consumer()
        m6_service = (
            corrupt["assembly"].series_intelligence
            ._SeriesIntelligencePublicBoundary__service
        )
        scope = m6_service.resolve_scope(corrupt["context"])
        active_ref = m6_service.repository.active_snapshots[scope.key]
        snapshot_key = (*scope.key, active_ref)
        m6_service.repository.snapshots[snapshot_key] = {
            **m6_service.repository.snapshots[snapshot_key], "status": "SUPERSEDED"
        }
        with self.assertRaises(ScriptStudioPublicError) as lineage:
            read_baseline(corrupt)
        self.assertEqual(lineage.exception.code, "m6_lineage_mismatch")

        unavailable = LifecycleAssembly.in_memory(ref_factory=Refs(), clock=lambda: NOW)
        real = seed_consumer_on(unavailable, activate=False)
        with self.assertRaises(ScriptStudioPublicError) as authority:
            read_baseline(real)
        self.assertEqual(authority.exception.code, "m6_consumer_authority_unavailable")

    def test_existing_script_workspace_is_unchanged_by_m6_read(self):
        seed = in_memory_consumer()
        context = seed["context"]
        assembly = seed["assembly"]
        before = copy.deepcopy(assembly.script_studio.get_workspace(
            context["workspaceRef"], context["seriesRef"], context["episodeRef"]
        ))
        read_baseline(seed)
        self.assertEqual(
            assembly.script_studio.get_workspace(
                context["workspaceRef"], context["seriesRef"], context["episodeRef"]
            ),
            before,
        )


if __name__ == "__main__":
    unittest.main()
