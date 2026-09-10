"""Isolation and preservation of actual original synthetic historical records."""
import ast
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib
from pathlib import Path
import sqlite3
import struct
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.evidence import EvidenceRecord, EVIDENCE_SCHEMA_VERSION
from services.v5_core_os.episode_production.generation_dispatch_public import GenerationDispatchPublicBoundary
from tests.support.generation_dispatch_fixtures import Fixture, approval_for, rebuild_workflow, SyntheticReaders, save_evidence


class GenerationDispatchIsolationTests(unittest.TestCase):
    def test_existing_run_input_authority_candidate_asset_and_plan_are_preserved(self):
        from tests.unit.test_method_aware_input_image_admission_e3a import InputImageFixture, artifacts
        from tests.unit.test_manifest_v2_input_append_authority_e3h import complete_input
        from tests.unit.test_method_aware_media_m10_m11 import m10_command, m11_command, method_service
        # Test-only PNG probe. The original schema/digest/readers/admission/journal
        # still execute; codec/FFprobe correctness is not claimed by this test.
        def png_probe(data, media_type):
            self.assertEqual(media_type, "image/png")
            artifacts._png_structure(data)
            width, height = struct.unpack(">II", data[16:24])
            return {"width": width, "height": height, "format": "png"}
        legacy = InputImageFixture(self, manifest_v2=True)
        with patch.object(artifacts, "probe_image", side_effect=png_probe):
            legacy.configure()
            intake, qc, selection, admission = complete_input(legacy)
            input_plan = legacy.boundary.create_method_aware_input_plan(m10_command(legacy.seed, legacy.plan, [legacy.binding(admission["assetVersion"])]))
        old_records = deepcopy(legacy.records())
        old_run = deepcopy(legacy.seed["run"])
        old_state = legacy.evidence.current_state(legacy.scope["workspaceRef"], legacy.scope["productionRunRef"])
        x = Fixture(self)
        # Copy only test-created original records to the original temporary adapter.
        for row in old_records:
            x.repo.append_record(EvidenceRecord(**{key: row[key] for key in EvidenceRecord.__dataclass_fields__}))
        x.package["plan"]["scope"] = deepcopy(legacy.scope)
        x.fence.workspace_ref = legacy.scope["workspaceRef"]
        s = x.package["plan"]["subject"]
        original = legacy.input_append_subject
        s["productionRunPayloadDigest"] = original["productionRunPayloadDigest"]
        s["manifestDigest"] = original["manifestDigest"]
        for key, ref_key, digest_key in (("scriptVersion", "scriptVersionRef", "scriptVersionDigest"),
            ("consistencyValidationVersion", "consistencyValidationVersionRef", "consistencyValidationDigest"),
            ("executionMethodPlanVersion", "executionMethodPlanVersionRef", "executionMethodPlanDigest"),
            ("creativeShotVersion", "creativeShotVersionRef", "creativeShotVersionDigest"),
            ("visualExecutionRequirement", "visualExecutionRequirementRef", "visualExecutionRequirementDigest")):
            s[key] = {"ref": original[ref_key], "digest": original[digest_key]}
        s["methodAwareInputPlanVersion"] = {"ref": input_plan["methodAwareInputPlanVersionRef"], "digest": input_plan["payloadDigest"]}
        s["m6Binding"] = {key: original[key] for key in s["m6Binding"]}
        authority = next(row["payload"] for row in old_records if row["recordKind"] == "MethodAwareInputAppendAuthority")
        s["inputAppendAuthority"] = {"ref": authority["inputAppendAuthorityRef"], "digest": authority["payloadDigest"], "subjectDigest": authority["subjectDigest"]}
        asset = admission["assetVersion"]
        s["inputAsset"] = {"assetRef": asset["assetRef"], "assetVersionRef": asset["assetVersionRef"], "assetVersionDigest": asset["payloadDigest"],
            "inputRole": asset["inputRole"], "contentDigest": asset["sha256"], "mediaType": asset["mediaType"], "byteSize": asset["byteSize"],
            "width": asset["probe"]["width"], "height": asset["probe"]["height"]}
        # The fixture's full old facts remain unchanged. Further source-owner
        # assembly (including exact live Shot/Beat approval) is a later package.
        rebuild_workflow(x.package)
        x.approval = approval_for(x.package)
        x.approval_reader = x.write_approval()
        x.readers = SyntheticReaders(x.package, x.attestation)
        x.service = x.make_service()
        x.public = GenerationDispatchPublicBoundary(x.service)
        baseline = x.records()
        state_before = x.repo.current_state(legacy.scope["workspaceRef"], legacy.scope["productionRunRef"])
        issued = x.public.issue(x.command())
        self.assertIn("grant", issued, issued)
        self.assertEqual(x.public.issue({**x.command(), "idempotencyKey": "test-wrong", "expectedSubjectDigest": "f" * 64})["code"], "APPROVAL_PLAN_MISMATCH")
        revoked = x.public.revoke(x.revoke_command(issued["grant"]))
        self.assertIn("terminal", revoked, revoked)
        self.assertEqual(x.records()[:len(baseline)], baseline)
        self.assertEqual(legacy.records(), old_records)
        self.assertEqual(legacy.seed["run"], old_run)
        self.assertEqual(legacy.evidence.current_state(legacy.scope["workspaceRef"], legacy.scope["productionRunRef"]), old_state)
        self.assertEqual(x.repo.current_state(legacy.scope["workspaceRef"], legacy.scope["productionRunRef"]), state_before)
        manifest = old_run["manifest"]
        self.assertIs(manifest["dispatchAllowed"], False)
        self.assertEqual(manifest["cameraContractState"], "NOT_READY")
        self.assertEqual(manifest["shotPlanApprovalState"], "NOT_VERIFIED")
        self.assertIs(asset["providerProcessingAuthorized"], False)
        self.assertIs(original["providerProcessingAuthorized"], False)
        # Existing route remains rejecting even with the new Grant in the same journal.
        method_service(legacy.boundary).evidence_repository = x.repo
        class NoDispatch:
            calls = 0
            def dispatch(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("unexpected dispatch")
        transport = NoDispatch()
        method_service(legacy.boundary).media_jobs = transport
        with self.assertRaises(Exception) as rejected:
            legacy.boundary.route_method_aware_videos(m11_command(legacy.seed, input_plan))
        self.assertEqual(rejected.exception.code, "execution_not_authorized")
        self.assertEqual(transport.calls, 0)
        self.assertEqual(len(x.records()) - len(baseline), 2)
        save_evidence("history_invariants.json", {"testOnly": True, "pngProbe": "synthetic standard-library double; no codec execution",
            "scope": legacy.scope, "runBefore": old_run, "runAfter": legacy.seed["run"], "recordsBefore": baseline,
            "recordsAfter": x.records(), "stateBefore": state_before, "stateAfter": state_before,
            "fiveFields": [False, "NOT_READY", "NOT_VERIFIED", False, False], "oldFactIdentitiesUnchanged": True,
            "newKinds": ["GenerationDispatchGrant", "GenerationDispatchGrantTerminal"], "dispatchCalls": transport.calls,
            "liveSourceAssemblyProven": False})

    def test_original_schema_tables_indexes_and_version_do_not_change(self):
        x = Fixture(self)
        def schema():
            connection = sqlite3.connect(x.path)
            try:
                return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            finally:
                connection.close()
        before = schema()
        grant = x.public.issue(x.command())["grant"]
        x.public.revoke(x.revoke_command(grant))
        self.assertEqual(schema(), before)
        self.assertEqual(EVIDENCE_SCHEMA_VERSION, 2)
        save_evidence("schema_invariance.json", {"before": before, "after": schema(), "EVIDENCE_SCHEMA_VERSION": EVIDENCE_SCHEMA_VERSION})

    def test_no_actual_network_media_or_process_entrypoint_is_reached(self):
        from services.v4_platform import comfyui, media_jobs
        with (patch.object(comfyui.ComfyUIWan22ImageToVideoAdapter, "generate", side_effect=AssertionError("media generation forbidden")) as video,
              patch.object(media_jobs.MediaJobCoordinator, "dispatch", side_effect=AssertionError("dispatch forbidden")) as dispatch):
            x = Fixture(self)
            result = x.public.issue(x.command())
            self.assertIn("grant", result, result)
            x.public.inspect(x.inspect_command())
            x.public.revoke(x.revoke_command(result["grant"]))
        self.assertEqual(video.call_count, 0)
        self.assertEqual(dispatch.call_count, 0)
        save_evidence("no_media_calls.json", {"realAdapterGenerateCalls": video.call_count, "coordinatorDispatchCalls": dispatch.call_count, "fakeTransportSendCalls": 0})

    def test_new_module_imports_have_no_configuration_or_resource_side_effect(self):
        # Modules are already located/imported by the test loader. Reload executes
        # their module bodies; Python's ordinary source-file loader is not a runtime read.
        names = ["generation_dispatch_contracts", "generation_dispatch_authority", "generation_dispatch_foundation", "generation_dispatch_public"]
        import os
        with (patch.object(sqlite3, "connect", side_effect=AssertionError("import DB")), patch.object(os, "open", side_effect=AssertionError("import config")),
              patch.object(Path, "mkdir", side_effect=AssertionError("import mkdir"))):
            for name in names:
                module = importlib.import_module("services.v5_core_os.episode_production." + name)
                source = Path(module.__file__).read_text()
                tree = ast.parse(source)
                # Execute in an isolated namespace so class identities used by
                # other tests are not replaced as importlib.reload would do.
                namespace = {"__name__": module.__name__, "__package__": module.__package__}
                exec(compile(tree, module.__file__, "exec"), namespace)
                self.assertNotIn("consume", namespace)
        save_evidence("import_isolation.json", {"modules": names, "databaseOpens": 0, "configOpens": 0, "directoriesCreated": 0,
            "limitation": "ordinary Python source loading excluded; no application startup"})


if __name__ == "__main__":
    unittest.main()
