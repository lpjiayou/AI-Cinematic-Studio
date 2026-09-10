"""Pure ADR-0022 schemas and exact canonical digest relationships."""
from copy import deepcopy
from hashlib import sha256
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_fixtures import make_package, approval_for, rebuild_workflow, Fixture, synthetic_consumption, START, END


class GenerationDispatchContractTests(unittest.TestCase):
    def setUp(self):
        self.package, _ = make_package()

    def test_complete_package_and_raw_json_roundtrip(self):
        approval = approval_for(self.package)
        bundle = {"schemaVersion": c.APPROVAL_SCHEMA, "authorityRef": approval["authorityRef"], "approvals": [{"planPackage": self.package, "approval": approval}]}
        self.assertEqual(c.validate_bundle(c.strict_json(c.canonical(bundle))), bundle)
        self.assertEqual(c.subject_digest(self.package["plan"]), c.digest({**self.package["plan"]["scope"], "subject": self.package["plan"]["subject"]}))

    def test_each_material_is_required_and_digest_only_is_insufficient(self):
        for name in self.package["materials"]:
            for replacement in (None, c.digest(self.package["materials"][name])):
                bad = deepcopy(self.package)
                bad["materials"][name] = replacement
                with self.subTest(name=name, replacement=replacement), self.assertRaises(c.DispatchError):
                    c.validate_plan_package(bad)
            bad = deepcopy(self.package)
            del bad["materials"][name]
            with self.assertRaises(c.DispatchError):
                c.validate_plan_package(bad)

    def test_duplicate_keys_utf8_nonfinite_deep_and_unknown_json_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":"\xff"}',
                    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"a":"\\ud800"}', b'{}' * 2,
                    b'{"a":' + b'[' * 70 + b'0' + b']' * 70 + b'}', b'\xff\xfe{\x00}\x00'):
            with self.subTest(raw=raw[:30]), self.assertRaises(c.DispatchError):
                c.strict_json(raw)
        bad = deepcopy(self.package)
        bad["materials"]["executionConfig"]["allow"] = True
        with self.assertRaises(c.DispatchError):
            c.validate_plan_package(bad)

    def test_primitives_are_strict_and_time_is_canonical(self):
        cases = [(c.ref, "*"), (c.ref, "a/b"), (c.ref, "a\n"), (c.ref, "x" * 201), (c.ref, 1),
            (c.sha, "A" * 64), (c.sha, "a" * 40), (c.git_id, "a" * 64), (c.integer, True), (c.integer, 5.0),
            (c.integer, 0), (c.utc, "2030-01-01T00:00:00Z"), (c.utc, "2030-01-01T00:00:00.000000+00:00"),
            (c.utc, "2030-02-30T00:00:00.000000Z")]
        for validator, value in cases:
            with self.subTest(value=value), self.assertRaises(c.DispatchError):
                validator(value)
        self.assertLess(c.utc(START), c.utc(END))

    def test_recursive_closed_fields_and_null_placeholders(self):
        paths = [("plan",), ("plan", "scope"), ("plan", "subject"), ("plan", "subject", "inputAsset"),
            ("plan", "subject", "m6Binding"), ("plan", "permissions"), ("plan", "limits"),
            ("plan", "executionBinding", "runtimeBinding"), ("materials", "executionConfig", "sourceRoot"),
            ("materials", "executionConfig", "launchConfiguration"), ("materials", "processIdentity"),
            ("materials", "costBasis", "billingResponsibility"), ("materials", "prerequisiteEvidence")]
        for path in paths:
            for mode in ("unknown", "missing", "null"):
                bad = deepcopy(self.package)
                target = bad
                for part in path:
                    target = target[part]
                if mode == "unknown":
                    target["unknown"] = 1
                elif mode == "missing":
                    del target[next(iter(target))]
                else:
                    target[next(iter(target))] = None
                with self.subTest(path=path, mode=mode), self.assertRaises(c.DispatchError):
                    c.validate_plan_package(bad)

    def test_material_changes_do_not_reuse_approval(self):
        approved = approval_for(self.package)
        for path, value in [(("plan", "scope", "episodeRef"), "test-other-episode"),
            (("plan", "subject", "inputAsset", "contentDigest"), "e" * 64),
            (("materials", "backendProfile", "parameters", "seed"), 99),
            (("materials", "backendProfile", "modelFiles", 0, "sha256"), "d" * 64),
            (("plan", "limits", "maxCostMinor"), 999), (("plan", "limits", "expiresAt"), "2030-01-01T00:59:00.000000Z"),
            (("materials", "workflow", "8", "inputs", "steps"), 22)]:
            bad = deepcopy(self.package)
            target = bad
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(c.DispatchError):
                c.validate_plan_package(bad)
                c.validate_approval(approved, plan=bad["plan"])

    def test_integer_and_float_profile_are_distinct_approved_bytes(self):
        original = approval_for(self.package)
        changed = deepcopy(self.package)
        changed["materials"]["backendProfile"]["parameters"]["cfg"] = 5
        binding = changed["plan"]["executionBinding"]
        binding["executionProfile"]["digest"] = c.digest(changed["materials"]["backendProfile"])
        binding["backendDecision"]["backendProfileDigest"] = binding["executionProfile"]["digest"]
        binding["backendDecisionDigest"] = c.digest(binding["backendDecision"])
        rebuild_workflow(changed)
        c.validate_plan_package(changed)
        self.assertNotEqual(c.digest(self.package["plan"]), c.digest(changed["plan"]))
        with self.assertRaises(c.DispatchError):
            c.validate_approval(original, plan=changed["plan"])

    def test_permissions_limits_cost_and_output_bounds(self):
        for path, value in [(("plan", "permissions", "dispatchAllowed"), 1), (("plan", "limits", "maxAttempts"), True),
            (("plan", "limits", "retryAllowed"), 0), (("plan", "limits", "maxCostMinor"), 1),
            (("plan", "limits", "notBefore"), END), (("materials", "costBasis", "computeUnitCostMinor"), 5.0),
            (("plan", "subject", "outputConstraints", "durationFrames"), 49), (("plan", "subject", "outputConstraints", "width"), 705),
            (("plan", "subject", "sourceAction", "sourceSpan", "sourceIndex"), 1),
            (("materials", "processIdentity", "processStartTicks"), "0123")]:
            bad = deepcopy(self.package)
            target = bad
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(c.DispatchError):
                c.validate_plan_package(bad)
        cost, limits = self.package["materials"]["costBasis"], self.package["plan"]["limits"]
        self.assertEqual(c.cost_bound(cost, limits), 24)
        self.assertEqual(c.cost_bound(cost, {**limits, "executionTimeoutSeconds": 61}), 29)

    def test_workflow_extra_nodes_inputs_and_numeric_coercion_rejected(self):
        for mode in ("node", "input", "denoise", "load", "prefix"):
            bad = deepcopy(self.package)
            graph = bad["materials"]["workflow"]
            if mode == "node": graph["13"] = deepcopy(graph["1"])
            if mode == "input": graph["1"]["inputs"]["extra"] = 1
            if mode == "denoise": graph["8"]["inputs"]["denoise"] = 1
            if mode == "load": graph["12"]["inputs"]["image"] = "anything.png"
            if mode == "prefix": graph["11"]["inputs"]["filename_prefix"] = "different"
            bad["plan"]["executionBinding"]["workflowDigest"] = c.digest(graph)
            with self.subTest(mode=mode), self.assertRaises(c.DispatchError):
                c.validate_plan_package(bad)

    def test_grant_terminal_seals_time_branches_and_immutable_copies(self):
        x = Fixture(self, memory=True)
        result = x.public.issue(x.command())
        self.assertIn("grant", result, result)
        grant = result["grant"]
        c.validate_grant(grant)
        record = synthetic_consumption(x, grant)
        c.validate_terminal(record.payload)
        for key, value in (("attemptBinding", None), ("revocationApproval", {}), ("grantTerminalRef", "test-random"), ("kind", "UNKNOWN")):
            bad = c.sealed({**record.payload, key: value})
            with self.subTest(key=key), self.assertRaises(c.DispatchError):
                c.validate_terminal(bad)
        for key, value in (("version", True), ("createdAt", START.replace("00.000000Z", "01.000000Z")), ("subjectDigest", "f" * 64), ("used", False)):
            bad = deepcopy(grant)
            bad[key] = value
            if key == "createdAt": bad[key] = "2029-12-31T23:59:59.000000Z"
            bad = c.sealed(bad)
            with self.subTest(key=key), self.assertRaises(c.DispatchError):
                c.validate_grant(bad)
        result["grant"]["subject"]["inputAsset"]["width"] = 1
        self.assertEqual(x.records()[0]["payload"]["subject"]["inputAsset"]["width"], 704)

    def test_read_set_owner_selector_scope_and_duplicates(self):
        x = Fixture(self, memory=True)
        read_set = x.public.issue(x.command())["grant"]["issuanceEvidence"]["currentSubjectReadSet"]
        for mode in ("owner", "missing", "duplicate", "scope", "revision", "object", "epoch"):
            bad = deepcopy(read_set)
            if mode == "owner": bad["selectors"][0]["owner"] = "OTHER"
            if mode == "missing": bad["selectors"].pop()
            if mode == "duplicate": bad["selectors"].append(deepcopy(bad["selectors"][0]))
            if mode == "scope": bad["selectors"][0]["scopeRef"] = "test-foreign"
            if mode == "revision": bad["selectors"][0]["coordinationRevision"] = True
            if mode == "object": bad["objects"] = []
            if mode == "epoch": bad["coordinationEpoch"] = "x"
            with self.subTest(mode=mode), self.assertRaises(c.DispatchError):
                c.validate_read_set(bad)

    def test_resealed_records_cannot_hide_request_or_required_read_set_tampering(self):
        x = Fixture(self, memory=True)
        grant = x.public.issue(x.command())["grant"]
        bad = deepcopy(grant)
        bad["issuanceEvidence"]["requestDigest"] = "f" * 64
        with self.assertRaises(c.DispatchError): c.validate_grant(c.sealed(bad))
        bad = deepcopy(grant)
        read_set = bad["issuanceEvidence"]["currentSubjectReadSet"]
        read_set["objects"] = [o for o in read_set["objects"] if o["objectKind"] != "inputAsset"]
        bad["issuanceEvidence"]["currentSubjectReadSetDigest"] = c.digest(read_set)
        with self.assertRaises(c.DispatchError): c.validate_grant(c.sealed(bad))
        terminal = deepcopy(synthetic_consumption(x, grant).payload)
        terminal["requestDigest"] = "f" * 64
        with self.assertRaises(c.DispatchError): c.validate_terminal(c.sealed(terminal))


if __name__ == "__main__":
    unittest.main()
