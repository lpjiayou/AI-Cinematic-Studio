import copy
import unittest

from services.v5_core_os.series_intelligence.public import SeriesIntelligencePublicError
from tests.unit.test_series_intelligence_m6 import (
    base_command,
    bible_content,
    confirmed_components,
    scoped_outbox,
    seed_assembly,
)


class SeriesIntelligenceProductionSpineTests(unittest.TestCase):
    def setUp(self):
        self.assembly, self.context = seed_assembly()

    def test_m5_confirmed_plan_to_m6_active_baseline_preserves_ref_and_digest_lineage(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        source = self.assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        snapshot = self.assembly.series_intelligence.activate_baseline({
            **base_command(self.context, "spine-activate"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        })
        self.assertEqual(snapshot["seriesPlanRef"], source["seriesPlanRef"])
        self.assertEqual(snapshot["seriesPlanVersionRef"], source["seriesPlanVersionRef"])
        self.assertEqual(snapshot["seriesPlanVersionDigest"], source["seriesPlanVersionDigest"])
        self.assertEqual(snapshot["seriesBibleVersionDigest"], bible["version"]["contentDigest"])
        self.assertEqual(snapshot["characterContinuityVersionDigest"], characters["version"]["contentDigest"])

    def test_m6_does_not_create_episode_script_or_provider_calls(self):
        before_series = self.assembly.series_episode.list_series(self.context["workspaceRef"])
        before_script_diagnostics = self.assembly.series_intelligence.diagnostic_snapshot()
        confirmed_components(self.assembly, self.context)
        after_series = self.assembly.series_episode.list_series(self.context["workspaceRef"])
        self.assertEqual(before_series, after_series)
        self.assertEqual(before_script_diagnostics["snapshotCount"], 0)
        self.assertEqual(after_series[0]["episodes"], [])

    def test_invalid_bible_reference_rolls_back_root_version_and_operation_registry(self):
        command = {
            **base_command(self.context, "invalid-bible"),
            "content": bible_content(),
        }
        command["content"]["timelineEvents"][0]["locationRef"] = "missing-location"
        with self.assertRaises(SeriesIntelligencePublicError):
            self.assembly.series_intelligence.create_bible_version(command)
        diagnostic = self.assembly.series_intelligence.diagnostic_snapshot()
        self.assertEqual(diagnostic["bibleCount"], 0)
        self.assertEqual(diagnostic["bibleVersionCount"], 0)
        self.assertEqual(diagnostic["operationCount"], 0)

    def test_existing_m1_to_m5_boundaries_remain_usable_after_m6_registration(self):
        project = self.assembly.project_context.build_context(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        plan = self.assembly.series_planning.get_workspace(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        self.assertEqual(project["projectRef"], self.context["projectRef"])
        self.assertEqual(plan["plan"]["status"], "confirmed")
        self.assertEqual(plan["plan"]["seriesRef"], self.context["seriesRef"])

    def test_real_m5_source_switch_before_activation_is_reread_and_rolls_back_atomically(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        original = self.context["plan"]
        fields = {
            "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
            "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
            "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
        }
        content = {field: copy.deepcopy(original["version"][field]) for field in fields}
        content["premise"] = "M5 source switched at the activation gate"
        replacement = self.assembly.series_planning.create_manual_version({
            "workspaceRef": self.context["workspaceRef"],
            "projectRef": self.context["projectRef"],
            "seriesRef": self.context["seriesRef"],
            "seriesPlanRef": original["plan"]["seriesPlanRef"],
            "expectedPlanVersion": original["plan"]["version"],
            "content": content,
        })
        self.assembly.series_planning.confirm_version({
            "workspaceRef": self.context["workspaceRef"],
            "seriesPlanRef": replacement["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": replacement["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": replacement["plan"]["version"],
            "humanConfirmed": True,
        })
        before = self.assembly.series_intelligence.diagnostic_snapshot()
        with self.assertRaises(SeriesIntelligencePublicError) as stale:
            self.assembly.series_intelligence.activate_baseline({
                **base_command(self.context, "real-m5-activation-race"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "characterContinuityRef": characters["root"]["characterContinuityRef"],
                "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
                "expectedActivationRevision": 0,
                "approvalRef": "approval-human",
            })
        self.assertEqual(stale.exception.code, "stale_source")
        self.assertEqual(self.assembly.series_intelligence.diagnostic_snapshot(), before)
        self.assertEqual(
            scoped_outbox(self.assembly.series_intelligence, self.context), []
        )


if __name__ == "__main__":
    unittest.main()
