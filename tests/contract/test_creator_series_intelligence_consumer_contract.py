import inspect
from pathlib import Path
import unittest

from services.v5_core_os.script_studio import ScriptStudioPublicBoundary
from services.v5_core_os.series_intelligence import errors
from tests.unit.test_series_intelligence_consumer_m6_p3 import (
    in_memory_consumer,
    read_baseline,
)


ROOT = Path(__file__).resolve().parents[2]


class CreatorSeriesIntelligenceConsumerContractTests(unittest.TestCase):
    def test_exact_m3_read_surface_is_the_only_new_m6_script_surface(self):
        method = ScriptStudioPublicBoundary.get_m6_episode_baseline
        self.assertEqual(
            list(inspect.signature(method).parameters),
            ["self", "workspace_ref", "project_ref", "series_ref", "episode_ref"],
        )
        self.assertEqual(
            {
                name
                for name in ScriptStudioPublicBoundary.__dict__
                if name.startswith("get_m6") and not name.startswith("_get_m6")
            },
            {"get_m6_episode_baseline"},
        )
        import services.v5_core_os.script_studio as script_package
        import services.v5_core_os.series_intelligence as m6_package

        self.assertNotIn("ActiveM6BaselineReader", script_package.__all__)
        self.assertNotIn("ActiveM6BaselineReader", m6_package.__all__)

    def test_exact_v1_output_contract_is_closed_world(self):
        result = read_baseline(in_memory_consumer())
        self.assertEqual(result["schemaVersion"], "v5.m6-episode-baseline-input.v1")
        self.assertEqual(set(result), {
            "schemaVersion", "businessDomain", "tenantId", "workspaceRef",
            "projectRef", "seriesRef", "episodeRef", "episodePlanItemRef",
            "m6BaselineSnapshotRef", "activationRevision",
            "m6BaselineCanonicalDigest", "seriesPlanVersionRef",
            "seriesPlanVersionDigest", "seriesBibleVersionRef",
            "seriesBibleVersionDigest", "characterContinuityVersionRef",
            "characterContinuityVersionDigest", "compatibility", "applicableFacts",
        })
        self.assertEqual(set(result["applicableFacts"]), {
            "episodePlanItem", "worldRules", "glossaryTerms", "locations",
            "factions", "props", "timelineEvents", "visualConstraints",
            "prohibitedNarrativePatterns", "characters", "stateIntervals",
            "relationships",
        })

    def test_stable_errors_are_exact_and_reconciliation_is_reserved(self):
        classes = (
            errors.M6BaselineNotAvailableError,
            errors.M6BaselineStaleError,
            errors.M6LineageMismatchError,
            errors.M6ConsumerAuthorityUnavailableError,
            errors.M6EpisodeMappingUnavailableError,
        )
        self.assertEqual({item.code for item in classes}, {
            "m6_baseline_not_available",
            "m6_baseline_stale",
            "m6_lineage_mismatch",
            "m6_consumer_authority_unavailable",
            "m6_episode_mapping_unavailable",
        })
        production = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "services/v5_core_os/series_intelligence/contracts.py",
                "services/v5_core_os/series_intelligence/errors.py",
                "services/v5_core_os/series_intelligence/foundation.py",
                "services/v5_core_os/series_intelligence/public.py",
                "services/v5_core_os/series_intelligence/composition.py",
                "services/v5_core_os/script_studio/public.py",
                "services/v5_core_os/lifecycle_integrity/composition.py",
            )
        )
        self.assertNotIn("m6_reconciliation_required", production)

    def test_consumer_has_no_http_schema_migration_or_script_write_surface(self):
        server = (ROOT / "apps/creator_workspace_mvp/server.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("get_m6_episode_baseline", server)
        self.assertNotIn("m6-episode-baseline-input", server)
        method_source = inspect.getsource(
            ScriptStudioPublicBoundary.get_m6_episode_baseline
        )
        for prohibited in (
            "create_version", "confirm_version", "rewrite", "append_event",
            "record_operation", "apply_mutation", "lease(",
        ):
            self.assertNotIn(prohibited, method_source)
        migrations = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "services/v5_core_os/lifecycle_integrity").glob("*migration*.py")
        )
        self.assertNotIn("m6_episode_baseline", migrations)


if __name__ == "__main__":
    unittest.main()
