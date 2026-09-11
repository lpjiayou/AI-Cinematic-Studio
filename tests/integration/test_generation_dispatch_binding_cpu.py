"""Actual original upstream, Package1 and original SQLite queue CPU witness."""
import unittest
from copy import deepcopy
from tests.support.generation_dispatch_binding_fixtures import BindingFixture, export_evidence, schema_snapshot
from services.v5_core_os.episode_production import generation_dispatch_contracts as c


class GenerationDispatchBindingCpuTests(unittest.TestCase):
    def test_original_owners_prepare_issue_and_unique_queue(self):
        f = BindingFixture(self)
        before = f.records()
        schema_before = schema_snapshot(f.domain.paths)
        state_before = f.evidence.current_state(f.scope["workspaceRef"], f.scope["productionRunRef"])
        prepared = f.prepare()
        self.assertEqual(prepared, f.prepare())
        after_prepare = f.records()
        self.assertEqual(before, after_prepare)
        self.assertEqual(f.jobs(), [])
        self.assertEqual(15, len(prepared["currentSubjectReadSet"]["selectors"]))
        expected_proofs = deepcopy(f.external.expected_proof_objects)
        for proof in expected_proofs:
            self.assertEqual([item for item in prepared["currentSubjectReadSet"]["objects"]
                if (item["owner"], item["objectKind"], item["objectRef"]) ==
                   (proof["owner"], proof["objectKind"], proof["objectRef"])], [proof])
        self.assertEqual(len(prepared["planPackage"]["materials"]["costBasis"]["sourceEvidence"]), 2)
        runtime = prepared["planPackage"]["plan"]["executionBinding"]
        self.assertNotEqual(runtime["backendDecision"]["runtimeAttestationDigest"],
            runtime["runtimeBinding"]["attestationFileSha256"])
        result = f.issue()
        self.assertEqual(result.get("operation"), "ISSUE", result)
        self.assertIn("grant", result, result)
        self.assertEqual(len(result["grant"]["issuanceEvidence"]["currentSubjectReadSet"]["selectors"]), 16)
        after_issue = f.records()
        self.assertEqual(after_issue[:len(before)], before)
        self.assertEqual([record["recordKind"] for record in after_issue[len(before):]], ["GenerationDispatchGrant"])
        self.assertEqual(after_issue[-1]["payload"], result["grant"])
        for proof in expected_proofs:
            self.assertEqual([item for item in result["grant"]["issuanceEvidence"]["currentSubjectReadSet"]["objects"]
                if (item["owner"], item["objectKind"], item["objectRef"]) ==
                   (proof["owner"], proof["objectKind"], proof["objectRef"])], [proof])
        proof_objects = {(item["owner"], item["objectKind"], item["objectRef"]) for item in expected_proofs}
        prepare_projection = [item for item in prepared["currentSubjectReadSet"]["objects"]
            if (item["owner"], item["objectKind"], item["objectRef"]) in proof_objects]
        issue_projection = [item for item in result["grant"]["issuanceEvidence"]["currentSubjectReadSet"]["objects"]
            if (item["owner"], item["objectKind"], item["objectRef"]) in proof_objects]
        self.assertEqual(prepare_projection, expected_proofs)
        self.assertEqual(issue_projection, expected_proofs)
        first = f.route(result["grant"])
        second = f.route(result["grant"], "test-route-two")
        self.assertEqual(first["queuedJobs"][0]["mediaJobRef"], second["queuedJobs"][0]["mediaJobRef"])
        self.assertEqual(len(f.jobs()), 1)
        self.assertEqual(f.jobs()[0]["attempts"], [])
        self.assertIsNone(f.jobs()[0]["lease"])
        self.assertEqual(f.records()[:len(before)], before)
        self.assertEqual(schema_snapshot(f.domain.paths), schema_before)
        self.assertEqual(f.evidence.current_state(f.scope["workspaceRef"], f.scope["productionRunRef"]), state_before)
        self.assertEqual([r["recordKind"] for r in f.records()[len(before):]],
            ["GenerationDispatchGrant", "VideoMethodRouteVersion", "VideoMethodRouteVersion"])
        self.assertEqual(result["sendPermission"], "NONE")
        export_evidence("positive_original_chain", {"prepare": prepared, "issue": result,
            "firstRoute": first, "secondRoute": second, "jobs": f.jobs(),
            "historyBefore": before, "historyAfter": f.records(), "schemaBefore": schema_before,
            "schemaAfter": schema_snapshot(f.domain.paths), "stateBefore": state_before,
            "stateAfter": f.evidence.current_state(f.scope["workspaceRef"], f.scope["productionRunRef"]),
            "coverage": f.dispatch.coverage, "writerObservations": f.dispatch.coordination.observations,
            "externalFixture": "TEST_ONLY; no real authority, runtime or cost verified"})
        export_evidence("readset_proof_positive", {"testId": self.id(), "TEST_ONLY": True,
            "proofSources": f.external.proof_evidence(), "expectedObjects": expected_proofs,
            "prepare": prepared, "issue": result, "persistedGrant": after_issue[-1],
            "recordsBeforePrepare": before, "recordsAfterPrepare": after_prepare,
            "recordsAfterIssueBeforeRoute": after_issue,
            "prepareProofProjection": prepare_projection, "issueProofProjection": issue_projection,
            "attestationPayloadDigest": runtime["backendDecision"]["runtimeAttestationDigest"],
            "attestationFileSha256": runtime["runtimeBinding"]["attestationFileSha256"],
            "actualGrantAppendCount": len(after_issue) - len(before),
            "sendPermission": result["sendPermission"]})

    def test_each_required_proof_failure_refuses_prepare_and_first_issue_without_writes(self):
        f = BindingFixture(self)
        normal = f.external.proof_material_port()
        f.dispatch.selections["materials"].select_port(normal)

        def state():
            records = f.records()
            workspace, run = f.scope["workspaceRef"], f.scope["productionRunRef"]
            return {"records": records, "jobs": f.jobs(), "tokens": {
                "recordJournalHead": f.evidence.record_journal_head(workspace, run),
                "workspaceRecordJournalHead": f.evidence.workspace_record_journal_head(workspace),
                "evidenceRevisionToken": f.evidence.read_snapshot(workspace, run).revisionToken},
                "poisonedWorkspaces": sorted(f.dispatch.coordination._poisoned),
                "domainUncertain": f.domain._uncertain}

        def projection(value):
            return {"fullStateDigest": c.digest(value),
                "recordCount": len(value["records"]), "recordsDigest": c.digest(value["records"]),
                "recordIdentities": [{key: record[key] for key in ("recordKind", "recordRef", "payloadDigest")}
                    for record in value["records"]], "jobs": value["jobs"], "tokens": value["tokens"],
                "poisonedWorkspaces": value["poisonedWorkspaces"], "domainUncertain": value["domainUncertain"]}

        baseline = state()
        state_snapshots = {c.digest(baseline): deepcopy(baseline)}
        outcomes = []
        try:
            for phase in ("PREPARE", "ISSUE"):
                for role in ("attestation", "source:0", "source:1", "continuing"):
                    for fault in ("missing_original", "omit_contribution", "wrong_ref", "wrong_digest", "wrong_owner"):
                        with self.subTest(phase=phase, dependency=role, fault=fault):
                            # Establish a valid current package before selecting
                            # this fault. ISSUE uses this exact approved package;
                            # it does not call the fixture's prepare-again helper.
                            prepared = f.prepare()
                            command = f.approved_issue_command(prepared) if phase == "ISSUE" else f.prepare_command()
                            before = state()
                            first_read = len(f.external.proof_read_observations)
                            port = f.external.proof_material_port(role, fault)
                            f.dispatch.selections["materials"].select_port(port)
                            try:
                                result = (f.dispatch.boundary.prepare(command) if phase == "PREPARE"
                                    else f.dispatch.boundary.issue(command))
                                after = state()
                                for actual in (before, after):
                                    state_snapshots[c.digest(actual)] = deepcopy(actual)
                                reads = deepcopy(f.external.proof_read_observations[first_read:])
                                expected_code = ("RUNTIME_CHANGED" if role == "attestation" else "COST_BOUND_UNVERIFIED") \
                                    if fault == "missing_original" else "SOURCE_CHANGED"
                                outcomes.append({"phase": phase, "dependency": role, "fault": fault,
                                    "expectedCode": expected_code, "result": result,
                                    "preparedPlanDigest": prepared["approvedPlanDigest"],
                                    "preparedSnapshotTokens": prepared["snapshotTokens"],
                                    "before": projection(before), "after": projection(after),
                                    "actualReadsAndValidation": reads})
                                self.assertEqual(result.get("code"), expected_code, result)
                                self.assertEqual(result["writesCommitted"], 0)
                                self.assertEqual(result["sendPermission"], "NONE")
                                self.assertEqual(before, after)
                                self.assertEqual(after, baseline)
                                if fault != "missing_original":
                                    reference = f.external.proof_roles[role]
                                    self.assertTrue(any(item["reference"] == reference
                                        and item["stage"] == "ORIGINAL_VALIDATED" for item in reads))
                                    self.assertTrue(any(item["reference"] == reference
                                        and item["stage"] == "CONTRIBUTION_FAULT_AFTER_ORIGINAL_VALIDATION" for item in reads))
                            finally:
                                # Real controlled locator selection restores only
                                # our port. It never clears poison or rewrites data.
                                f.dispatch.selections["materials"].select_port(normal)
        finally:
            export_evidence("readset_proof_rejections", {"testId": self.id(), "TEST_ONLY": True,
                "initialRecords": baseline["records"], "initialState": projection(baseline),
                "stateSnapshots": state_snapshots,
                "expectedObjects": deepcopy(f.external.expected_proof_objects), "outcomes": outcomes,
                "subTestRowsAreNotIndependentTestIds": True})

    def test_wrong_scope_missing_and_old_source_selection_refuse_read_only(self):
        f = BindingFixture(self)
        before = f.records()
        outcomes = []
        for field in ("workspaceRef", "productionRunRef", "methodAwareInputPlanVersionRef",
                "creativeShotVersionRef", "beatRef", "inputAssetVersionRef", "backendRef", "executionConfigRef", "costBasisRef"):
            command = f.prepare_command(); command[field] = "test-missing-or-other-scope"
            result = f.dispatch.boundary.prepare(command)
            self.assertIn("code", result, (field, result))
            self.assertEqual(result["writesCommitted"], 0)
            outcomes.append({"field": field, "result": result})
        self.assertEqual(before, f.records())
        self.assertEqual([], f.jobs())
        export_evidence("prepare_missing_scope_selection", {"outcomes": outcomes, "recordsBefore": before, "recordsAfter": f.records(), "jobsAfter": f.jobs()})

    def test_independent_config_and_approval_drift_refuse_new_route(self):
        f = BindingFixture(self)
        result = f.issue(); self.assertIn("grant", result, result)
        original = f.external.path.read_bytes()
        f.external.path.write_bytes(original + b" ")
        with self.assertRaises(c.DispatchError):
            f.route(result["grant"])
        self.assertEqual([], f.jobs())
        f.external.path.write_bytes(original)
        path = f.root / "test-generation-approval.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(c.DispatchError):
            f.route(result["grant"])
        self.assertEqual([], f.jobs())
        export_evidence("independent_pin_drift", {"grant": result["grant"], "jobsAfter": f.jobs(),
            "externalReadCalls": f.external.calls, "sourceBytesRestoredForSecondIndependentCheck": True})

    def test_history_replay_is_not_a_new_eligibility_or_send_permission(self):
        f = BindingFixture(self)
        issued = f.issue(); self.assertIn("grant", issued, issued)
        route = f.route(issued["grant"])
        records, jobs = f.records(), f.jobs()
        f.clock.value = f.external.template["plan"]["limits"]["expiresAt"]
        replay = f.dispatch.boundary.issue(f.issue_command)
        self.assertEqual(replay["grant"], issued["grant"])
        self.assertEqual(replay["eligibility"], "EXPIRED")
        self.assertEqual(replay["sendPermission"], "NONE")
        self.assertTrue(f.route(issued["grant"])["idempotentReplay"])
        with self.assertRaises(c.DispatchError) as error:
            f.route(issued["grant"], "new-expired-route")
        self.assertEqual(error.exception.code, "OUTSIDE_VALIDITY_WINDOW")
        self.assertEqual(f.records(), records); self.assertEqual(f.jobs(), jobs)
        export_evidence("history_expiry", {"issueReplay": replay, "originalRoute": route,
            "recordsBefore": records, "recordsAfter": f.records(), "jobsBefore": jobs, "jobsAfter": f.jobs()})
