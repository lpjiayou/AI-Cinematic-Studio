"""TEST_ONLY A14B engineering materials, not SH09, model or GPU evidence.

The byte strings below are deliberately not executable model files. Importing
this module performs no filesystem, HTTP, environment or process inspection.
"""
from copy import deepcopy
from hashlib import sha256

from services.v4_platform.backend_registry import digest
from services.v4_platform.generation_dispatch_a14b_profile import (
    A14B_ADAPTER_IDENTITY, A14B_CAPABILITY, A14B_COMPILER_IDENTITY,
    A14B_MODEL_ROLES, A14B_NODE_INPUT_CONTRACTS, A14B_POSTPROCESS,
    A14B_PROFILE_SCHEMA, A14B_REQUIRED_NODES, A14B_TEMPLATE_REF, COMFYUI_COMMIT)
from services.v4_platform.comfyui_a14b_runtime import A14B_RUNTIME_ATTESTATION_SCHEMA


def a14b_model_bytes(role):
    return ("TEST_ONLY inert A14B original: " + role).encode("ascii")


def make_a14b_source():
    return {"assetRef": "test-anchor", "assetVersionRef": "test-anchor-v1",
        "assetVersionDigest": digest("test-anchor-original"), "contentDigest": digest("test-png-bytes"),
        "mediaType": "image/png", "byteSize": 400, "width": 704, "height": 1280}


def make_a14b_profile(source_digest=None):
    files = [{"role": role, "name": "test-a14b-" + role.lower() + ".bin",
        "sha256": sha256(a14b_model_bytes(role)).hexdigest(), "sizeBytes": len(a14b_model_bytes(role))}
        for role in A14B_MODEL_ROLES]
    models = {model["role"]: model for model in files}
    pairs = []
    for index, (expert, lora) in enumerate((("HIGH_NOISE_EXPERT", "HIGH_NOISE_LORA"), ("LOW_NOISE_EXPERT", "LOW_NOISE_LORA"))):
        pairs.append({"expertRole": expert, "expertSha256": models[expert]["sha256"], "loraRole": lora,
            "loraSha256": models[lora]["sha256"], "strengthModel": 1.0, "modelShift": 5.0,
            "startAtStep": index * 4, "endAtStep": (index + 1) * 4,
            "addNoise": "enable" if index == 0 else "disable",
            "returnWithLeftoverNoise": "enable" if index == 0 else "disable"})
    return {"schemaVersion": A14B_PROFILE_SCHEMA, "modelFiles": files, "parameters": {
        "compilerIdentity": A14B_COMPILER_IDENTITY, "templateRef": A14B_TEMPLATE_REF, "evidenceClass": "TEST_ONLY",
        "comfyuiCommit": COMFYUI_COMMIT, "positivePrompt": "TEST_ONLY an inert synthetic subject slowly turns its head.",
        "negativePrompt": "TEST_ONLY blur, motion discontinuity", "seed": 17, "steps": 8, "cfg": 1.0,
        "samplerName": "euler", "scheduler": "simple", "modelPairs": pairs,
        "input": {"imageName": "test-a14b/anchor.png", "contentDigest": source_digest or make_a14b_source()["contentDigest"]},
        "nativeOutput": {"nodeId": "16", "mediaType": "image/png", "frameCount": 49, "width": 704,
            "height": 1280, "filenamePrefix": "test-a14b/native"}, "postprocess": deepcopy(A14B_POSTPROCESS),
        "resourceRequirements": {"gpuCount": 1, "minimumVramBytes": 1024, "deviceType": "cuda"}}}


def make_a14b_runtime(profile, process_identity=None, execution_config=None):
    launch = deepcopy(execution_config["launchConfiguration"]) if execution_config is not None else {
        "argv": ["test-python", "test-main.py"], "environmentProjection": [{"name": "TEST_SYNTHETIC", "value": "inert"}]}
    process = deepcopy(process_identity) if process_identity is not None else {
        "schemaVersion": "v5.generation-dispatch-runtime-process.v1", "instanceRef": "test-instance",
        "hostBootIdDigest": digest("test-boot"), "pidNamespaceIdDigest": digest("test-namespace"),
        "comfyuiPid": 17, "processStartTicks": "123", "comfyuiCommit": COMFYUI_COMMIT, "launchConfigDigest": digest(launch)}
    facts = {"providerId": "test-provider", "modelId": "test-a14b-model", "region": "test-region", "endpointClass": "TEST_ONLY_LOOPBACK",
        "comfyuiVersion": COMFYUI_COMMIT, "pythonVersion": "test-python", "pytorchVersion": "test-torch",
        "deviceName": "TEST_ONLY_SYNTHETIC_CUDA_NOT_OBSERVED", "deviceType": "cuda", "vramTotalBytes": 4096, "gpuCount": 1,
        "requiredNodes": list(A14B_REQUIRED_NODES), "nodeInputContracts": deepcopy(A14B_NODE_INPUT_CONTRACTS),
        "modelFiles": deepcopy(profile["modelFiles"]), "objectInfoDigest": digest("test-object-info-original"),
        "modelDigestVerification": "LOCAL_FILE_SHA256_VERIFIED", "startImageCapability": "LOAD_IMAGE_TO_WAN_IMAGE_TO_VIDEO_VERIFIED",
        "evidenceClass": "TEST_ONLY", "backendProfileDigest": digest(profile), "compilerIdentity": A14B_COMPILER_IDENTITY,
        "templateRef": A14B_TEMPLATE_REF, "comfyuiCommit": COMFYUI_COMMIT, "processIdentity": process,
        "processIdentityDigest": digest(process), "launchConfiguration": launch, "launchConfigDigest": digest(launch)}
    value = {"schemaVersion": A14B_RUNTIME_ATTESTATION_SCHEMA, "capabilityMode": "A14B_IMAGE_TO_VIDEO",
        "attestationRef": "test-a14b-attestation", "observedAt": "2030-01-01T00:00:00.000000Z", "factsDigest": digest(facts),
        "facts": facts, "authorityState": "TECHNICAL_EVIDENCE_ONLY", "publicationAllowed": False}
    return {**value, "payloadDigest": digest(value)}


def make_a14b_package():
    """Lazy existing V5 fixture extension; integration uses isolated repositories."""
    from tests.support.generation_dispatch_fixtures import make_package, SOURCE_TEXT
    from services.v5_core_os.episode_production import generation_dispatch_contracts as c
    from services.v4_platform.generation_dispatch_compiler import compile_generation_dispatch_workflow
    package, _ = make_package()
    plan, materials = package["plan"], package["materials"]
    binding, subject = plan["executionBinding"], plan["subject"]
    profile = make_a14b_profile(subject["inputAsset"]["contentDigest"])
    materials["backendProfile"] = profile
    materials["processIdentity"]["comfyuiCommit"] = COMFYUI_COMMIT
    attestation = make_a14b_runtime(profile, materials["processIdentity"], materials["executionConfig"])
    decision = binding["backendDecision"]
    decision.update({"adapterIdentity": A14B_ADAPTER_IDENTITY, "adapterCapability": A14B_CAPABILITY,
        "endpointClass": "TEST_ONLY_LOOPBACK", "modelId": "test-a14b-model", "backendProfileRef": "test-a14b-profile",
        "backendProfileDigest": digest(profile), "runtimeAttestationRef": attestation["attestationRef"],
        "runtimeAttestationDigest": attestation["payloadDigest"]})
    binding.update({"backendDecisionDigest": digest(decision),
        "executionProfile": {"ref": decision["backendProfileRef"], "digest": digest(profile)},
        "runtimeBinding": {"instanceRef": materials["processIdentity"]["instanceRef"],
            "processIdentityDigest": digest(materials["processIdentity"]), "attestationFileSha256": digest(attestation)}})
    binding["executionCode"]["comfyuiCommit"] = COMFYUI_COMMIT
    source = {key: item for key, item in subject["inputAsset"].items() if key != "inputRole"}
    materials["workflow"] = compile_generation_dispatch_workflow(
        generation_request_ref="generation-request-" + digest(c.request_identity(plan)), source_text=SOURCE_TEXT,
        camera_instruction=subject["cameraInstruction"], source_asset=source,
        backend_profile=profile, output_constraints=subject["outputConstraints"])
    binding["workflowDigest"] = digest(materials["workflow"])
    return package, attestation


def make_a14b_execution_fixture(case, endpoint):
    """Original upstream/SQLite/Grant composition with inert model originals.

    This factory's monkeypatch changes only an existing TEST_ONLY external-owner
    fixture at construction; formal domain readers, gate, queue and repositories
    are unchanged. The caller owns the fresh random-port loopback listener.
    """
    from unittest.mock import patch
    from tests.support import generation_dispatch_binding_fixtures as binding_fixtures
    from tests.support.generation_dispatch_execution_fixtures import ExecutionFixture, TestWorkerExecutionContext
    from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
    from services.v4_platform.comfyui_staged_transport import _bind_staged_transport
    from services.v4_platform.generation_dispatch_execution import GenerationDispatchExecutor, MediaJobGenerationDispatchPort
    from services.v4_platform.generation_dispatch_live_result import GenerationDispatchLiveResultBoundary
    from services.v5_core_os.episode_production import generation_dispatch_contracts as c
    from services.v5_core_os.episode_production.generation_dispatch_consumption import GenerationDispatchConsumer

    class A14BExternalOwners(binding_fixtures.TestOnlyExternalOwners):
        def __init__(self, fixture):
            super().__init__(fixture)
            materials, binding = self.template["materials"], self.template["plan"]["executionBinding"]
            profile = make_a14b_profile(fixture.content_digest)
            self.input_path = fixture.source_root / profile["parameters"]["input"]["imageName"]
            self.input_path.parent.mkdir()
            self.input_path.write_bytes(fixture.content)
            self.model_paths = {}
            model_root = fixture.root / "test-inert-a14b-model-originals"
            model_root.mkdir()
            for model in profile["modelFiles"]:
                path = model_root / model["name"]
                path.write_bytes(a14b_model_bytes(model["role"]))
                self.model_paths[model["role"]] = path
            materials["backendProfile"] = profile
            materials["processIdentity"]["comfyuiCommit"] = COMFYUI_COMMIT
            config = materials["executionConfig"]
            config.update(baseUrlDigest=digest(endpoint), connectionTimeoutMs=1000, requestTimeoutMs=2000,
                historyTimeoutMs=10000, postprocessTimeoutMs=30000)
            for key, path in (("sourceRoot", fixture.source_root), ("modelRoot", model_root),
                    ("inputRoot", fixture.source_root), ("artifactRoot", fixture.root / "artifacts")):
                config[key]["absolutePathDigest"] = digest(str(path))
            self.attestation = make_a14b_runtime(profile, materials["processIdentity"], config)
            old_reference = self.proof_roles["attestation"]
            self.proof_files.pop(old_reference)
            self.proof_originals.pop(old_reference)
            self.expected_proof_objects = [obj for obj in self.expected_proof_objects if obj["objectKind"] != "RuntimeAttestation"]
            self._store_proof("attestation", self.attestation["attestationRef"], self.attestation,
                "RUNTIME_PROCESS", "RuntimeAttestation", self.attestation["payloadDigest"])
            decision = binding["backendDecision"]
            decision.update(adapterIdentity=A14B_ADAPTER_IDENTITY, adapterCapability=A14B_CAPABILITY,
                endpointClass="TEST_ONLY_LOOPBACK", modelId="test-a14b-model", backendProfileRef="test-a14b-profile",
                backendProfileDigest=digest(profile), runtimeAttestationRef=self.attestation["attestationRef"],
                runtimeAttestationDigest=self.attestation["payloadDigest"])
            binding.update(backendDecisionDigest=digest(decision), executionProfile={"ref": "test-a14b-profile", "digest": digest(profile)},
                executionConfigDigest=digest(config), runtimeBinding={"instanceRef": materials["processIdentity"]["instanceRef"],
                    "processIdentityDigest": digest(materials["processIdentity"]),
                    "attestationFileSha256": self.proof_files[self.attestation["attestationRef"]]["sha256"]})
            binding["executionCode"]["comfyuiCommit"] = COMFYUI_COMMIT
            self.expected_proof_objects.sort(key=lambda obj: (obj["owner"], obj["objectKind"], obj["objectRef"]))
            self.write_originals()

        def write_originals(self):
            value = {"templateMaterials": self.template["materials"], "backendBinding": self.template["plan"]["executionBinding"],
                "attestation": self.attestation, "originals": self.originals}
            self.path.write_bytes(c.canonical(value))
            self.pin = sha256(self.path.read_bytes()).hexdigest()

        def verify_subject(self, resolved, lease):
            value = super().verify_subject(resolved, lease)
            c.require(self.fixture.source.read_bytes() == self.fixture.content
                and self.input_path.read_bytes() == self.fixture.content
                and sha256(self.fixture.content).hexdigest() == resolved.subject["inputAsset"]["contentDigest"], "SOURCE_CHANGED")
            return value

        def _runtime_original(self, lease, proof_files):
            reference = self.template["plan"]["executionBinding"]["backendDecision"]["runtimeAttestationRef"]
            original, file_sha = self._read_proof(reference, proof_files, lease, "RUNTIME_CHANGED")
            materials = self.read_original_file(lease)["templateMaterials"]
            try:
                facts = validate_a14b_runtime_attestation(original, backend_profile=materials["backendProfile"],
                    process_identity=materials["processIdentity"], execution_config=materials["executionConfig"])
                for model in materials["backendProfile"]["modelFiles"]:
                    raw = self.model_paths[model["role"]].read_bytes()
                    c.require(len(raw) == model["sizeBytes"] and sha256(raw).hexdigest() == model["sha256"], "RUNTIME_CHANGED")
            except (ValueError, OSError, KeyError, TypeError) as exc:
                raise c.DispatchError("RUNTIME_CHANGED") from exc
            decision = self.template["plan"]["executionBinding"]["backendDecision"]
            c.require(original["attestationRef"] == reference and original["payloadDigest"] == decision["runtimeAttestationDigest"]
                and facts["endpointClass"] == "TEST_ONLY_LOOPBACK", "RUNTIME_CHANGED")
            self.proof_read_observations.append({"reference": reference, "stage": "A14B_ORIGINAL_VALIDATED",
                "validator": "services.v4_platform.comfyui_a14b_runtime.validate_a14b_runtime_attestation",
                "objectDigest": original["payloadDigest"], "fileSha256": file_sha, "TEST_ONLY": True})
            return original, file_sha

    class A14BExecutionFixture(binding_fixtures.BindingFixture):
        claim_command = ExecutionFixture.claim_command
        claim_and_consume = ExecutionFixture.claim_and_consume
        execute = ExecutionFixture.execute
        current_job = ExecutionFixture.current_job

        def __init__(self):
            with patch.object(binding_fixtures, "TestOnlyExternalOwners", A14BExternalOwners):
                super().__init__(case)
            self.clock.monotonic_value = 1000.0
            self.clock.monotonic = lambda: self.clock.monotonic_value
            issued = self.issue()
            if "grant" not in issued:
                raise AssertionError(issued)
            self.grant = issued["grant"]
            self.route_result = self.route(self.grant)
            self.job = self.jobs()[0]
            self.worker_context = TestWorkerExecutionContext("test-a14b-worker")
            self.job_port = MediaJobGenerationDispatchPort(coordinator=self.coordinators[0],
                coordination=self.dispatch.coordination, clock=self.clock)
            self.consumer = GenerationDispatchConsumer(foundation=self.dispatch.boundary._foundation,
                job_port=self.job_port, worker_context=self.worker_context, clock=self.clock)
            self.transport = _bind_staged_transport(endpoint, execution_config=self.external.template["materials"]["executionConfig"],
                runtime_binding=self.grant["executionBinding"]["runtimeBinding"], backend_decision=self.grant["executionBinding"]["backendDecision"])
            self.result_boundary = GenerationDispatchLiveResultBoundary(self.coordinators[0], clock=self.clock)
            self.executor = GenerationDispatchExecutor.compose_live(coordinator=self.coordinators[0], consumer=self.consumer,
                worker_context=self.worker_context, transport=self.transport, clock=self.clock,
                coordination=self.dispatch.coordination, result_boundary=self.result_boundary, job_port=self.job_port)

    return A14BExecutionFixture()
