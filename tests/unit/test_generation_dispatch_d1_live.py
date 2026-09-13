"""D1 schema separation, no-I/O default and independent original trust tests."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from services.v4_platform.backend_registry import digest
from services.v4_platform.generation_dispatch_a14b_live import (
    LIVE_PROFILE_SCHEMA, LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_COMPILER_IDENTITY,
    LIVE_TEMPLATE_REF, LIVE_RUNTIME_SCHEMA, LIVE_ENDPOINT_CLASS, validate_live_profile)
from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
from tests.support.generation_dispatch_exact_fixtures import exact_profile, exact_runtime


def live_profile(source_digest=None, tools=None):
    result = exact_profile(source_digest, tools)
    result["schemaVersion"] = LIVE_PROFILE_SCHEMA
    result["parameters"].update(compilerIdentity=LIVE_COMPILER_IDENTITY, templateRef=LIVE_TEMPLATE_REF,
        evidenceClass="LIVE_CONFIGURATION", cameraDisposition="INDEPENDENT_OWNER_DECISION_REQUIRED")
    return result


def live_runtime(profile, process=None, config=None):
    result = exact_runtime(profile, process, config)
    result["schemaVersion"] = LIVE_RUNTIME_SCHEMA
    result["facts"].update(endpointClass=LIVE_ENDPOINT_CLASS, evidenceClass="CURRENT_RUNTIME_OBSERVATION",
        compilerIdentity=LIVE_COMPILER_IDENTITY, templateRef=LIVE_TEMPLATE_REF)
    result["factsDigest"] = digest(result["facts"])
    result["payloadDigest"] = digest({k: v for k, v in result.items() if k != "payloadDigest"})
    return result


class D1LiveContractTests(unittest.TestCase):
    def test_original_approval_requires_independent_actor_pin_and_full_verifier_result(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from hashlib import sha256
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        from services.v5_core_os.episode_production.generation_dispatch_live_sources import OriginalFile, PinnedOwnerOriginal
        from tests.support.generation_dispatch_fixtures import make_package, approval_for
        package, _ = make_package()
        approval = approval_for(package)
        evidence = {"testOnly": True, "decision": "EXACT_SUBJECT_GENERATION_EXECUTION"}
        approval["approvalEvidenceDigest"] = c.digest(evidence)
        approval = c.sealed(approval, "authorityDecisionDigest")
        with TemporaryDirectory() as root:
            def original(name, value):
                path = Path(root) / name
                raw = c.canonical(value)
                path.write_bytes(raw)
                return OriginalFile(path, sha256(raw).hexdigest())
            binding, source = original("approval.json", approval), original("evidence.json", evidence)
            args = (approval["authorityRef"], approval["authorityDecisionRef"],
                approval["approvalEvidenceRef"], approval["approvalEvidenceDigest"])
            for actor, verifier, success in ((approval["actorRef"], lambda a, e: a, True),
                    ("unrelated-actor", lambda a, e: a, False),
                    (approval["actorRef"], lambda a, e: True, False),
                    (approval["actorRef"], lambda a, e: {**a, "decision": "REVOKED"}, False)):
                reader = PinnedOwnerOriginal(binding=binding, authority_ref=approval["authorityRef"],
                    actor_ref=actor, evidence=source, verifier=verifier)
                if success:
                    self.assertEqual(reader.resolve_original(*args), approval)
                else:
                    with self.subTest(actor=actor, verifier=verifier), self.assertRaises(c.DispatchError) as stopped:
                        reader.resolve_original(*args)
                    self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
            source.path.write_bytes(b'{"testOnly":false}')
            with self.assertRaises(c.DispatchError):
                reader.resolve_original(*args)

    def test_missing_owner_verifiers_and_fake_current_runtime_are_closed(self):
        from services.v5_core_os.episode_production.generation_dispatch_live_sources import PinnedPrerequisiteOriginals, PinnedLiveMaterials
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        with self.assertRaises(c.DispatchError):
            PinnedPrerequisiteOriginals(originals={}, verifiers={}, approval_original=None, approval_evidence=None)
        with self.assertRaises(c.DispatchError):
            PinnedLiveMaterials(configuration={}, runtime_original={}, runtime_current=True, cost_owner=True)

    def test_live_profile_is_not_test_or_offline_candidate(self):
        from services.v4_platform.generation_dispatch_a14b_exact import validate_exact_profile
        from services.v4_platform.backend_registry import BackendValidationError
        value = live_profile()
        self.assertEqual(validate_live_profile(value), value)
        with self.assertRaises(BackendValidationError):
            validate_exact_profile(value)
        for evidence in ("TEST_ONLY", "OFFLINE_SOURCE_CANDIDATE"):
            changed = deepcopy(value)
            changed["parameters"]["evidenceClass"] = evidence
            with self.subTest(evidence=evidence), self.assertRaises(BackendValidationError):
                validate_live_profile(changed)
        with self.assertRaises(BackendValidationError):
            validate_live_profile(exact_profile())

    def test_runtime_checks_all_inner_version_and_material_fields(self):
        from services.v4_platform.backend_registry import BackendValidationError
        profile = live_profile()
        runtime = live_runtime(profile)
        self.assertEqual(validate_a14b_runtime_attestation(runtime, backend_profile=profile), runtime["facts"])
        changes = (("evidenceClass", "TEST_ONLY"), ("endpointClass", "TEST_ONLY_LOOPBACK"),
            ("comfyuiVersion", "wrong"), ("compilerIdentity", "wrong"), ("templateRef", "wrong"),
            ("gpuCount", 2), ("modelFiles", profile["modelFiles"][:-1]))
        for key, value in changes:
            changed = deepcopy(runtime)
            changed["facts"][key] = value
            changed["factsDigest"] = digest(changed["facts"])
            changed["payloadDigest"] = digest({k: v for k, v in changed.items() if k != "payloadDigest"})
            with self.subTest(field=key), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(changed, backend_profile=profile)

    def test_live_current_reader_requires_full_observation_input_and_local_tools(self):
        from services.v5_core_os.episode_production.generation_dispatch_live_sources import LiveRuntimeCurrentReader
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        from types import SimpleNamespace
        profile = live_profile()
        runtime = live_runtime(profile)
        configuration = {"backendProfile": profile,
            "processIdentity": runtime["facts"]["processIdentity"],
            "executionConfig": {"launchConfiguration": runtime["facts"]["launchConfiguration"],
                "launchConfigDigest": runtime["facts"]["launchConfigDigest"],
                "inputRoot": {"absolutePathDigest": "1" * 64},
                "artifactRoot": {"absolutePathDigest": "2" * 64}}}
        source = {"inputName": profile["parameters"]["input"]["imageName"],
            "contentDigest": profile["parameters"]["input"]["contentDigest"],
            "inputRootDigest": "1" * 64, "outputRootDigest": "2" * 64,
            "outputPrefixAbsent": True}
        tools = profile["parameters"]["postprocess"]["toolIdentity"]
        lease = SimpleNamespace(assert_held=lambda: None)
        def reader(observation=runtime, input_value=source, tool_value=tools):
            return LiveRuntimeCurrentReader(host_observer=lambda config, held: deepcopy(observation),
                input_observer=lambda config, held: deepcopy(input_value), tool_observer=lambda: deepcopy(tool_value))
        self.assertEqual(reader().read_current(configuration, lease), runtime["facts"])
        with self.assertRaises(c.DispatchError) as stopped:
            reader(observation=True).read_current(configuration, lease)
        self.assertEqual(stopped.exception.code, "RUNTIME_CHANGED")
        for field in ("inputName", "contentDigest", "inputRootDigest", "outputRootDigest"):
            with self.subTest(field=field), self.assertRaises(c.DispatchError) as stopped:
                reader(input_value={**source, field: "changed"}).read_current(configuration, lease)
            self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")
        with self.assertRaises(c.DispatchError) as stopped:
            reader(tool_value={}).read_current(configuration, lease)
        self.assertEqual(stopped.exception.code, "RUNTIME_CHANGED")
        collision = reader(input_value={**source, "outputPrefixAbsent": False})
        # Existing output is allowed for GET recovery, never for a fresh SEND.
        self.assertEqual(collision.read_current(configuration, lease), runtime["facts"])
        with self.assertRaises(c.DispatchError) as stopped:
            collision.assert_output_available(configuration, lease)
        self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")

    def test_each_of_six_model_roles_and_process_identity_are_bound(self):
        from services.v4_platform.backend_registry import BackendValidationError
        profile = live_profile()
        original = live_runtime(profile)
        for index in range(6):
            changed = deepcopy(original)
            changed["facts"]["modelFiles"][index]["sha256"] = "f" * 64
            changed["factsDigest"] = digest(changed["facts"])
            changed["payloadDigest"] = digest({k: v for k, v in changed.items() if k != "payloadDigest"})
            with self.subTest(role=changed["facts"]["modelFiles"][index]["role"]), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(changed, backend_profile=profile)
        for key in ("instanceRef", "comfyuiPid", "processStartTicks", "hostBootIdDigest"):
            process = deepcopy(original["facts"]["processIdentity"])
            process[key] = process[key] + 1 if type(process[key]) is int else "2" * 64 if key.endswith("Digest") else "999"
            with self.subTest(processField=key), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(original, backend_profile=profile, process_identity=process)

    def test_default_cli_and_offline_check_have_no_network_or_database(self):
        from apps.creator_workspace_mvp.generation_dispatch_operator import main
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("sqlite3.connect", side_effect=AssertionError("DB forbidden")), redirect_stdout(StringIO()):
            self.assertEqual(main(["check-offline"]), 0)
            self.assertEqual(main(["execute-one", "--target-ref", "job"]), 2)
            with self.assertRaises(SystemExit) as stopped:
                main(["--help"])
            self.assertEqual(stopped.exception.code, 0)

    def test_missing_existing_stores_refuses_before_open_or_initialize(self):
        from services.v5_core_os.episode_production.generation_dispatch_composition import open_existing_live_operator
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        with patch("sqlite3.connect", side_effect=AssertionError("DB forbidden")):
            with self.assertRaises(c.DispatchError) as stopped:
                open_existing_live_operator(storage_root="/missing-d1-private-root", lifecycle_path="/missing/lifecycle",
                    run_path="/missing/runs", queue_path="/missing/queue", artifact_root="/missing/artifacts",
                    lifecycle_authorities={}, episode_authorities={}, selection=None, endpoint=None,
                    technical_target_id="test", clock=None, worker_context=None, approval_reader=None,
                    prerequisite_reader=None, material_reader=None, backend_reader=None, runtime_reader=None,
                    cost_reader=None, issuer_service_ref="test")
            self.assertEqual(stopped.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")
