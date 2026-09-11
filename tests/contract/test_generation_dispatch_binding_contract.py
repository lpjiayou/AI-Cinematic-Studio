"""Accepted version branches and exact four-field binding, using a real issued Job."""
from copy import deepcopy
from types import SimpleNamespace
import sqlite3
import unittest

from services.v4_platform.backend_registry import BackendValidationError
from services.v4_platform.media_jobs import _validate_job, _validate_method_aware_video_request, MediaJobError, MediaJobConflictError, SqliteMediaJobAdapter
from services.v4_platform.method_aware_execution import validate_envelope
from services.v4_platform.generation_dispatch_jobs import create_generation_dispatch_job
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_routing import validate_route_plan
from tests.support.generation_dispatch_binding_fixtures import BindingFixture, export_evidence


class GenerationDispatchBindingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = BindingFixture(SimpleNamespace(addCleanup=cls.addClassCleanup))
        cls.prepared = cls.fixture.prepare()
        issued = cls.fixture.issue()
        if "grant" not in issued: raise AssertionError(issued)
        cls.grant = issued["grant"]
        cls.route = cls.fixture.route(issued["grant"])
        cls.job = cls.fixture.jobs()[0]

    def test_current_proof_objects_required_in_prepare_and_issued_grant(self):
        package = self.prepared["planPackage"]
        expected = self.fixture.external.expected_proof_objects
        evidence = []
        for phase, read_set, selector_count in (
                ("PREPARE", self.prepared["currentSubjectReadSet"], 15),
                ("ISSUE", self.grant["issuanceEvidence"]["currentSubjectReadSet"], 16)):
            with self.subTest(phase=phase):
                self.assertEqual(len(read_set["selectors"]), selector_count)
                self.assertTrue(all(proof in read_set["objects"] for proof in expected))
                c.validate_read_set_proof_bindings(read_set, package)
            for proof in expected:
                for mutation in ("missing", "wrong_ref", "wrong_digest", "wrong_owner"):
                    value = deepcopy(read_set)
                    row = next(o for o in value["objects"] if o == proof)
                    if mutation == "missing": value["objects"].remove(row)
                    elif mutation == "wrong_ref": row["objectRef"] = "test-other-proof"
                    elif mutation == "wrong_digest": row["objectDigest"] = c.digest("test-other-proof")
                    else: row["owner"] = "V5_SCRIPT"
                    value["objects"].sort(key=lambda o: (o["owner"], o["objectKind"], o["objectRef"]))
                    with self.subTest(phase=phase, proof=proof["objectRef"], mutation=mutation):
                        with self.assertRaises(c.DispatchError) as error:
                            c.validate_read_set_proof_bindings(value, package)
                        self.assertEqual(error.exception.code, "SOURCE_CHANGED")
                        evidence.append({"phase": phase, "proof": proof, "mutation": mutation,
                                         "code": error.exception.code})
        export_evidence("readset_proof_contract", {"expected": expected,
            "prepare": self.prepared["currentSubjectReadSet"],
            "issue": self.grant["issuanceEvidence"]["currentSubjectReadSet"], "rejections": evidence})

    def test_binding_closed_at_request_envelope_job_and_route(self):
        _validate_job(self.job)
        validate_route_plan({k: v for k, v in self.route.items() if k != "idempotentReplay"})
        for field in self.job["dispatchGrantBinding"]:
            for layer in ("request", "executionEnvelope", "job"):
                value = deepcopy(self.job if layer == "job" else self.job[layer])
                del value["dispatchGrantBinding"][field]
                with self.subTest(field=field, layer=layer), self.assertRaises((MediaJobError, BackendValidationError)):
                    if layer == "request": _validate_method_aware_video_request(value)
                    elif layer == "executionEnvelope": validate_envelope(value, self.job["request"])
                    else: _validate_job(value)
        for layer in ("request", "executionEnvelope", "job"):
            value = deepcopy(self.job if layer == "job" else self.job[layer])
            value["dispatchGrantBinding"]["allowExpired"] = True
            with self.subTest(extra=layer), self.assertRaises((MediaJobError, BackendValidationError)):
                if layer == "request": _validate_method_aware_video_request(value)
                elif layer == "executionEnvelope": validate_envelope(value, self.job["request"])
                else: _validate_job(value)

    def test_cross_layer_digest_binding_and_schema_downgrade_rejected(self):
        for key in self.job["dispatchGrantBinding"]:
            envelope = deepcopy(self.job["executionEnvelope"])
            envelope["dispatchGrantBinding"][key] = "other-grant" if key.endswith("Ref") else "d" * 64
            envelope = c.sealed(envelope, "envelopeDigest")
            with self.subTest(key=key), self.assertRaises(BackendValidationError):
                validate_envelope(envelope, self.job["request"])
        for version in ("v4.media-job.v1", "v4.media-job.v2", "v4.media-job.v3"):
            downgraded = {**deepcopy(self.job), "schemaVersion": version}
            with self.subTest(version=version), self.assertRaises(MediaJobError): _validate_job(downgraded)
        request = deepcopy(self.job["request"]); request["schemaVersion"] = "v5.method-aware-video-generation-request.v1"; request["version"] = 1
        request = c.sealed(request)
        with self.assertRaises(MediaJobError): _validate_method_aware_video_request(request)
        envelope = deepcopy(self.job["executionEnvelope"]); envelope.pop("dispatchGrantBinding")
        envelope["schemaVersion"] = "v4.method-aware-media-execution-envelope.v1"
        envelope = c.sealed(envelope, "envelopeDigest")
        with self.assertRaises(BackendValidationError): validate_envelope(envelope, self.job["request"])

    def test_no_legacy_dispatch_entry_for_request_v2_and_no_internal_alias(self):
        f = self.fixture; before = f.jobs()
        with self.assertRaises(MediaJobError):
            f.coordinators[0].dispatch(self.job["request"], idempotency_key="test-old-dispatch")
        value = f.queues[0].get(self.job["workspaceRef"], self.job["productionRunRef"], self.job["jobRef"])
        value["request"]["dispatchGrantBinding"]["subjectDigest"] = "a" * 64
        self.assertEqual(f.jobs(), before)
        self.assertFalse(hasattr(f.dispatch.boundary, "consume"))

    def test_bridge_rejects_consistent_but_different_source_under_same_grant(self):
        request = deepcopy(self.job["request"])
        request["sourceImageContentDigest"] = "e" * 64
        request = c.sealed(request)
        envelope = deepcopy(self.job["executionEnvelope"])
        envelope["sourceAsset"]["contentDigest"] = request["sourceImageContentDigest"]
        envelope["generationRequestDigest"] = request["payloadDigest"]
        envelope = c.sealed(envelope, "envelopeDigest")
        validate_envelope(envelope, request)
        before = self.fixture.jobs()
        with self.assertRaises(BackendValidationError):
            create_generation_dispatch_job(self.fixture.coordinators[0], verified_grant=self.grant,
                request=request, envelope=envelope)
        self.assertEqual(self.fixture.jobs(), before)

    def test_reserved_namespace_and_legacy_history_collision_fail_closed(self):
        f = self.fixture
        path = f.root / "test-legacy-collision.sqlite3"
        repository = SqliteMediaJobAdapter(path)
        legacy = deepcopy(self.job)
        legacy.pop("dispatchGrantBinding"); legacy["schemaVersion"] = "v4.media-job.v3"
        request = legacy["request"]; request.pop("dispatchGrantBinding")
        request["schemaVersion"] = "v5.method-aware-video-generation-request.v1"; request["version"] = 1
        legacy["request"] = c.sealed(request); legacy["requestDigest"] = legacy["request"]["payloadDigest"]
        envelope = legacy["executionEnvelope"]; envelope.pop("dispatchGrantBinding")
        envelope["schemaVersion"] = "v4.method-aware-media-execution-envelope.v1"
        envelope["generationRequestDigest"] = legacy["requestDigest"]
        legacy["executionEnvelope"] = c.sealed(envelope, "envelopeDigest")
        _validate_job(legacy)
        for invalid_version in (True, 1.0):
            invalid_request = deepcopy(legacy["request"])
            invalid_request["version"] = invalid_version
            invalid_request = c.sealed(invalid_request)
            with self.subTest(legacy_version=invalid_version), self.assertRaises(MediaJobError):
                _validate_method_aware_video_request(invalid_request)
        with self.assertRaises(MediaJobError): repository.create(legacy)
        self.assertEqual(repository.list(legacy["workspaceRef"], legacy["productionRunRef"]), [])
        # Explicit TEST_ONLY historical preloaded row, separate from the actual
        # positive create path. Original schema/column order is unchanged.
        connection = sqlite3.connect(path)
        try:
            connection.execute("INSERT INTO v4_media_jobs VALUES (?,?,?,?,?,?,?,?)", (
                legacy["workspaceRef"], legacy["productionRunRef"], legacy["jobRef"], legacy["idempotencyKey"],
                legacy["requestDigest"], legacy["state"], legacy["revision"], c.canonical(legacy).decode()))
            connection.commit()
        finally: connection.close()
        before = repository.list(legacy["workspaceRef"], legacy["productionRunRef"])
        self.assertEqual(repository.create(legacy), (legacy, True))
        with self.assertRaises(MediaJobConflictError): repository.create(self.job)
        self.assertEqual(repository.list(legacy["workspaceRef"], legacy["productionRunRef"]), before)
        export_evidence("reserved_namespace_collision", {"historicalRowsPreloaded": 1,
            "historyBefore": before, "historyAfter": repository.list(legacy["workspaceRef"], legacy["productionRunRef"]),
            "newJobCount": sum(job["schemaVersion"] == "v4.media-job.v4" for job in repository.list(legacy["workspaceRef"], legacy["productionRunRef"]))})
