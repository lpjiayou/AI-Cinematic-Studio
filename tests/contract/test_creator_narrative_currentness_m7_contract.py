import unittest

from services.v5_core_os.episode_production import EpisodeProductionPublicError
from services.v5_core_os.episode_production.evidence import (
    ALLOWED_EVIDENCE_RECORD_KINDS,
)
from services.v5_core_os.episode_production.shot_graph import (
    CONSISTENCY_VALIDATION_SCHEMA_VERSION,
)
from tests.unit.test_narrative_currentness_m7 import (
    seed_m7,
    validation_command,
)


class CreatorNarrativeCurrentnessContractTests(unittest.TestCase):
    def test_public_projection_is_closed_and_binds_exact_m3_m6_profile_inputs(self):
        seed = seed_m7()
        result = seed["boundary"].create_narrative_validation(
            validation_command(seed)
        )
        self.assertEqual(
            set(result),
            {
                "consistencyValidationRef",
                "consistencyValidationVersionRef",
                "validationVersion",
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "scriptVersionRef",
                "scriptVersionDigest",
                "m6ConsumerBindingDigest",
                "m6BaselineSnapshotRef",
                "m6BaselineCanonicalDigest",
                "activationRevision",
                "seriesPlanVersionRef",
                "seriesPlanVersionDigest",
                "seriesBibleVersionRef",
                "seriesBibleVersionDigest",
                "characterContinuityVersionRef",
                "characterContinuityVersionDigest",
                "validationProfileRef",
                "validationProfileVersion",
                "validationProfileDigest",
                "result",
                "m8Readiness",
                "findings",
                "payloadDigest",
                "currentness",
                "idempotentReplay",
            },
        )
        binding = seed["bound"]["scriptVersion"]["m6ConsumerBinding"]
        self.assertEqual(result["scriptVersionRef"], seed["bound"]["scriptVersion"]["scriptVersionRef"])
        self.assertEqual(result["m6ConsumerBindingDigest"], binding["payloadDigest"])
        for field in (
            "m6BaselineSnapshotRef",
            "m6BaselineCanonicalDigest",
            "activationRevision",
            "seriesPlanVersionRef",
            "seriesPlanVersionDigest",
            "seriesBibleVersionRef",
            "seriesBibleVersionDigest",
            "characterContinuityVersionRef",
            "characterContinuityVersionDigest",
        ):
            self.assertEqual(result[field], binding[field])

    def test_caller_cannot_submit_findings_result_or_readiness(self):
        seed = seed_m7()
        for field, value in (
            ("findings", []),
            ("result", "PASS"),
            ("m8Readiness", "READY_FOR_M8"),
        ):
            command = validation_command(seed, key=f"m7-forbidden-{field}")
            command[field] = value
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionPublicError
            ) as rejected:
                seed["boundary"].create_narrative_validation(command)
            self.assertEqual((rejected.exception.status, rejected.exception.code), (400, "invalid_request"))

    def test_m7_adds_only_an_evidence_kind_and_preserves_k2_v1_schema(self):
        self.assertIn(
            "ConsistencyValidationVersion", ALLOWED_EVIDENCE_RECORD_KINDS
        )
        self.assertEqual(
            CONSISTENCY_VALIDATION_SCHEMA_VERSION,
            "v5.consistency-validation.v1",
        )


if __name__ == "__main__":
    unittest.main()
