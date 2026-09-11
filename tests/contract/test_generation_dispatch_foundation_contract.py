"""Three explicit V5 entrypoints; no application/CLI/consumer composition."""
import ast
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production import generation_dispatch_foundation as f
from services.v5_core_os.episode_production.generation_dispatch_public import GenerationDispatchPublicBoundary
from tests.support.generation_dispatch_fixtures import Fixture, TransactionObservation


class GenerationDispatchPublicContractTests(unittest.TestCase):
    def test_three_success_dtos_have_exact_keys_and_no_send_capability(self):
        x = Fixture(self)
        issued = x.public.issue(x.command())
        self.assertEqual(set(issued), {"schemaVersion", "operation", "grant", "recordReplay", "eligibility", "sendPermission"}, issued)
        self.assertEqual(issued["eligibility"], "ELIGIBLE_FOR_CONSUMPTION")
        inspected = x.public.inspect(x.inspect_command())
        self.assertEqual(set(inspected), {"schemaVersion", "operation", "grant", "terminal", "eligibility", "sendPermission"})
        self.assertIsNone(inspected["terminal"])
        revoked = x.public.revoke(x.revoke_command(issued["grant"]))
        self.assertEqual(set(revoked), {"schemaVersion", "operation", "terminal", "recordReplay", "eligibility", "sendPermission"}, revoked)
        for result in (issued, inspected, revoked):
            self.assertEqual(result["sendPermission"], "NONE")
            self.assertNotIn(str(x.root), c.canonical(result).decode())
            self.assertNotIn("continuation", result)
        self.assertFalse(hasattr(x.public, "consume"))
        # Package 2 exposes prepare only with explicit dependencies; the old
        # Package 1 assembly still cannot prepare or grant another operation.
        command = x.command()
        prepared = x.public.prepare({**{key: command[key] for key in (
            "workspaceRef", "productionRunRef", "methodAwareInputPlanVersionRef",
            "creativeShotVersionRef", "beatRef", "inputAssetVersionRef", "backendRef")},
            "executionConfigRef": x.package["materials"]["executionConfig"]["configRef"],
            "costBasisRef": x.package["materials"]["costBasis"]["costBasisRef"],
            "limits": x.package["plan"]["limits"]})
        self.assertEqual(prepared["code"], "CURRENTNESS_FENCE_UNAVAILABLE")
        self.assertEqual(prepared["sendPermission"], "NONE")
        self.assertEqual(prepared["writesCommitted"], 0)
        self.assertFalse(hasattr(x.service, "consume"))

    def test_default_and_every_missing_trusted_dependency_rejects(self):
        x = Fixture(self)
        self.assertEqual(GenerationDispatchPublicBoundary().issue(x.command())["code"], "PERSISTENCE_UNAVAILABLE")
        for name in ("source_reader", "backend_reader", "runtime_reader", "cost_reader", "coordination", "clock", "issuer_service_ref"):
            service = x.make_service()
            setattr(service, name, None)
            result = GenerationDispatchPublicBoundary(service).issue(x.command())
            with self.subTest(name=name):
                self.assertEqual(result["code"], "CURRENTNESS_FENCE_UNAVAILABLE", result)
                self.assertEqual(result["writesCommitted"], 0)
        service = f.GenerationDispatchFoundation(repository=x.repo, coordination=x.fence)
        self.assertEqual(GenerationDispatchPublicBoundary(service).issue(x.command())["code"], "APPROVAL_UNAVAILABLE")
        self.assertEqual(x.records(), [])

    def test_client_injections_and_changed_expected_values_are_rejected(self):
        x = Fixture(self)
        for field in ("actorRef", "role", "verified", "permissions", "grant", "readSet", "dispatchAllowed", "testMode", "bundlePath"):
            result = x.public.issue({**x.command(), field: True})
            with self.subTest(field=field):
                self.assertEqual(result, {"schemaVersion": c.PREFIX + "error.v1", "operation": "ISSUE", "code": "INVALID_CLOSED_SCHEMA", "writesCommitted": 0, "sendPermission": "NONE"})
        for field in ("expectedSubjectDigest", "expectedApprovedPlanDigest"):
            result = x.public.issue({**x.command(), field: "f" * 64})
            self.assertEqual(result["code"], "APPROVAL_PLAN_MISMATCH")
        self.assertEqual(x.records(), [])

    def test_all_current_readers_and_write_are_inside_fence(self):
        x = Fixture(self)
        original = x.repo.append_records
        calls = []
        def append(records, **kwargs):
            x.fence.assert_held()
            calls.append((len(records), kwargs))
            return original(records, **kwargs)
        command = x.command()
        observation = TransactionObservation(x)
        with observation.observe(), patch.object(x.repo, "append_records", side_effect=append):
            result = x.public.issue(command)
        self.assertIn("grant", result, result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 1)
        validity = calls[0][1]["grant_issue_validity"]
        self.assertIs(validity.clock, x.clock)
        self.assertEqual(validity.created_at, c.utc(result["grant"]["createdAt"]))
        self.assertEqual(validity.not_before, c.utc(result["grant"]["limits"]["notBefore"]))
        self.assertEqual(validity.expires_at, c.utc(result["grant"]["limits"]["expiresAt"]))
        pretransaction_reads = [e for e in observation.events if e["phase"] == "CLOCK_READ" and not e["inTransaction"]]
        self.assertEqual(validity.last_observed_at, c.utc(pretransaction_reads[1]["value"]))
        self.assertEqual(len([e for e in observation.events if e["phase"] == "CLOCK_READ" and e["inTransaction"]]), 1)
        self.assertEqual(calls[0][1], {"expected_record_journal_head": command["snapshotTokens"]["recordJournalHead"],
            "expected_workspace_record_journal_head": command["snapshotTokens"]["workspaceRecordJournalHead"],
            "expected_evidence_revision_token": command["snapshotTokens"]["evidenceRevisionToken"],
            "grant_issue_validity": validity})
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(x.readers.calls, ["source", "backend", "runtime", "cost"] * 2)
        self.assertEqual(x.fence.trace, ["enter", "exit"])
        self.assertEqual(len(x.originals.calls), 2)

    def test_fence_exit_failure_after_commit_never_claims_zero_writes(self):
        x = Fixture(self)
        def fail():
            raise c.DispatchError("CURRENTNESS_FENCE_UNAVAILABLE")
        x.fence.on_exit = fail
        result = x.public.issue(x.command())
        self.assertEqual(result, {"schemaVersion": c.PREFIX + "indeterminate.v1", "operation": "ISSUE", "code": "COMMIT_OUTCOME_UNKNOWN", "sendPermission": "NONE"})
        self.assertEqual(len(x.records()), 1)

    def test_envelope_mismatch_rejected_by_original_repository(self):
        from dataclasses import replace
        from services.v5_core_os.episode_production.foundation import EpisodeProductionError
        from services.v5_core_os.episode_production.evidence import EvidenceRecord, InMemoryEpisodeProductionEvidenceAdapter
        x = Fixture(self)
        grant = x.public.issue(x.command())["grant"]
        base = x.records()[0]
        record = EvidenceRecord(**{k: base[k] for k in EvidenceRecord.__dataclass_fields__})
        for field, value in (("recordRef", "test-random-ref"), ("recordVersion", 2), ("createdAt", "2030-01-01T00:00:11.000000Z"),
            ("workspaceRef", "test-foreign"), ("requestDigest", "f" * 64)):
            with self.subTest(field=field), self.assertRaises(EpisodeProductionError):
                InMemoryEpisodeProductionEvidenceAdapter().append_record(replace(record, **{field: value}))
        self.assertEqual(grant, x.records()[0]["payload"])

    def test_no_new_imports_by_existing_composition_and_no_sql_in_public(self):
        root = Path(__file__).resolve().parents[2]
        names = ("generation_dispatch_contracts", "generation_dispatch_authority", "generation_dispatch_foundation", "generation_dispatch_public")
        for path in (root / "services/v5_core_os/episode_production/public.py", root / "services/v5_core_os/episode_production/__init__.py",
            root / "services/v5_core_os/lifecycle_integrity/composition.py", root / "apps/creator_workspace_mvp/server.py"):
            source = path.read_text()
            self.assertTrue(all(name not in source for name in names), str(path))
        public = root / "services/v5_core_os/episode_production/generation_dispatch_public.py"
        tree = ast.parse(public.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any("evidence" in name or "sqlite" in name or "v4" in name for name in imports))


if __name__ == "__main__":
    unittest.main()
