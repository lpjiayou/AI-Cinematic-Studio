"""Bounded technical-input material adapter for the original live Operator.

The trusted host installs original configuration, runtime/cost readers and input
staging. Construction is inert. No SSH, endpoint discovery, model installation,
new store, approval substitution or workflow submission occurs in this module.
"""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import time

from . import generation_dispatch_contracts as c
from .generation_dispatch_live_sources import LiveRuntimeCurrentReader, OriginalFile
from .generation_dispatch_readers import VerifiedOriginalObservation


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _proof_value(proof):
    c.require(type(proof) is VerifiedOriginalObservation, "SOURCE_CHANGED")
    proof.as_object()
    return {"owner": proof.owner, "objectKind": proof.object_kind,
        "objectRef": proof.object_ref, "original": deepcopy(proof.original),
        "digestField": proof.digest_field}


def create_image_video_installation(*, policy, configuration, runtime_original,
        runtime_current, cost_owner, endpoint_url, clock=None):
    """Inert host assembly for ``open_existing_live_operator``'s optional port.

    The endpoint and pinned runtime original come from installed host sources,
    never from a Creator command. Each explicit upload re-reads those originals
    and independent live metadata before constructing the existing transport.
    No default execution window, authority decision or attestation is invented.
    """
    from .image_video import ImageVideoInstallation
    c.require(type(configuration) is OriginalFile and type(runtime_original) is OriginalFile
        and type(runtime_current) is LiveRuntimeCurrentReader
        and type(endpoint_url) is str and bool(endpoint_url)
        and (clock is None or callable(clock)), "CURRENTNESS_FENCE_UNAVAILABLE")
    installed_policy, current_clock = deepcopy(policy), clock or _now

    def stage_input(derived, png_bytes, lease):
        from services.v4_platform.comfyui_staged_transport import _bind_staged_transport
        from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
        limits = installed_policy["limits"]

        def authorize(_phase):
            lease.assert_held()
            c.require(c.utc(limits["notBefore"]) <= c.utc(current_clock()) < c.utc(limits["expiresAt"]),
                "OUTSIDE_VALIDITY_WINDOW")
            c.require(configuration.read() == template, "CONFIG_CHANGED")
            c.require(runtime_original.read() == original, "RUNTIME_CHANGED")

        lease.assert_held()
        template, original = configuration.read(), runtime_original.read()
        # Only the same three immutable user-input fields may differ. In
        # particular, the selected endpoint, process, models and tools cannot.
        expected = deepcopy(template)
        parameters = expected["backendProfile"]["parameters"]
        for field in ("positivePrompt", "input", "nativeOutput"):
            if field == "nativeOutput":
                parameters[field]["filenamePrefix"] = derived["backendProfile"]["parameters"][field]["filenamePrefix"]
            else:
                parameters[field] = deepcopy(derived["backendProfile"]["parameters"][field])
        expected["backendDecision"]["backendProfileRef"] = (
            "image-video-profile-" + c.digest(expected["backendProfile"])[:48])
        expected["backendDecision"]["backendProfileDigest"] = c.digest(expected["backendProfile"])
        c.require(c.canonical(derived) == c.canonical(expected), "CONFIG_CHANGED")
        image = parameters["input"]
        c.require(image["imageName"] == "acs-user-image-video/" + sha256(png_bytes).hexdigest() + ".png"
            and image["contentDigest"] == sha256(png_bytes).hexdigest(), "SOURCE_CHANGED")
        original_facts = validate_a14b_runtime_attestation(original,
            backend_profile=template["backendProfile"], process_identity=template["processIdentity"],
            execution_config=template["executionConfig"])
        # This observes the selected service and existing pinned input, not the
        # new file that has not been staged yet. Old outputs may already exist.
        observed = runtime_current.read_current(deepcopy(template), lease)
        runtime_current.assert_matches_original(template, original_facts, observed, lease)
        authorize("INPUT_PREPARE")
        runtime_binding = {"instanceRef": template["processIdentity"]["instanceRef"],
            "processIdentityDigest": c.digest(template["processIdentity"]),
            "attestationFileSha256": runtime_original.file_sha256}
        transport = _bind_staged_transport(endpoint_url,
            execution_config=derived["executionConfig"], runtime_binding=runtime_binding,
            backend_decision=derived["backendDecision"])
        seconds = min(derived["executionConfig"]["requestTimeoutMs"] / 1000,
            (c.utc(limits["expiresAt"]) - c.utc(current_clock())).total_seconds())
        c.require(seconds > 0, "OUTSIDE_VALIDITY_WINDOW")
        return transport.upload_input_png(png_bytes, image["contentDigest"],
            deadline_monotonic=time.monotonic() + seconds, authorize=authorize)

    materials = ImageVideoMaterials(configuration=configuration, runtime_current=runtime_current,
        cost_owner=cost_owner, stage_input=stage_input, clock=current_clock)
    installation = ImageVideoInstallation(policy=installed_policy, materials=materials)
    installation.validate()
    return installation


class ImageVideoMaterials:
    """One host-approved template; only the exact user input fields can vary."""

    def __init__(self, *, configuration, runtime_current, cost_owner, stage_input, clock=None):
        c.require(type(configuration) is OriginalFile
            and type(runtime_current) is LiveRuntimeCurrentReader
            and callable(getattr(cost_owner, "read_current", None))
            and callable(getattr(cost_owner, "proof_originals", None))
            and callable(stage_input) and (clock is None or callable(clock)),
            "CURRENTNESS_FENCE_UNAVAILABLE")
        self._configuration, self._runtime = configuration, runtime_current
        self._cost, self._stage = cost_owner, stage_input
        self._clock = clock or _now

    def read_environment(self, lease):
        """Return a closed, read-only observation for Creator presentation.

        The trusted host reader remains the only observer of the selected GPU
        runtime. This projection deliberately excludes endpoints, process
        identifiers, model paths and credentials, and performs no staging,
        approval, grant, queue mutation or workflow submission.
        """
        from services.v4_platform.generation_dispatch_a14b_live import (
            LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS,
            validate_live_profile,
        )
        lease.assert_held()
        value = self._configuration.read()
        c.exact(value, {"backendDecision", "backendProfile", "executionConfig",
            "executionCode", "processIdentity"})
        profile = validate_live_profile(value["backendProfile"])
        c.validate_execution_config(value["executionConfig"])
        c.validate_process(value["processIdentity"])
        for identifier in c.exact(value["executionCode"], {
                "coreCommit", "coreTree", "comfyuiCommit"}).values():
            c.git_id(identifier)
        decision = c.backend.validate_decision(value["backendDecision"])
        c.require(value["executionCode"]["comfyuiCommit"]
            == value["processIdentity"]["comfyuiCommit"]
            == profile["parameters"]["comfyuiCommit"], "CONFIG_CHANGED")
        c.require(decision["adapterIdentity"] == LIVE_ADAPTER_IDENTITY
            and decision["adapterCapability"] == LIVE_CAPABILITY
            and decision["endpointClass"] == LIVE_ENDPOINT_CLASS
            and decision["backendProfileDigest"] == c.digest(profile)
            and value["executionConfig"]["backendRef"] == decision["backendRef"],
            "CONFIG_CHANGED")
        facts = self._runtime.read_current(deepcopy(value), lease)
        observed_at = self._clock()
        c.utc(observed_at)
        lease.assert_held()
        return {
            "observedAt": observed_at,
            "evidenceClass": facts["evidenceClass"],
            "gpuCount": facts["gpuCount"],
            "deviceType": facts["deviceType"],
            "comfyuiVersion": facts["comfyuiVersion"],
        }

    def _configuration_for(self, scope, subject, limits, lease):
        from services.v4_platform.generation_dispatch_a14b_live import (
            LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS,
            validate_live_profile,
        )
        from .image_video_contracts import validate_subject
        lease.assert_held()
        c.scope(scope)
        validate_subject(subject)
        c.validate_limits(limits)
        c.require(c.utc(limits["notBefore"]) <= c.utc(self._clock()) < c.utc(limits["expiresAt"]),
            "OUTSIDE_VALIDITY_WINDOW")
        value = self._configuration.read()
        c.exact(value, {"backendDecision", "backendProfile", "executionConfig",
            "executionCode", "processIdentity"})
        profile = validate_live_profile(value["backendProfile"])
        c.validate_execution_config(value["executionConfig"])
        c.validate_process(value["processIdentity"])
        for identifier in c.exact(value["executionCode"], {"coreCommit", "coreTree", "comfyuiCommit"}).values():
            c.git_id(identifier)
        c.require(value["executionCode"]["comfyuiCommit"] == value["processIdentity"]["comfyuiCommit"]
            == profile["parameters"]["comfyuiCommit"], "CONFIG_CHANGED")
        decision = c.backend.validate_decision(value["backendDecision"])
        c.require(decision["adapterIdentity"] == LIVE_ADAPTER_IDENTITY
            and decision["adapterCapability"] == LIVE_CAPABILITY
            and decision["endpointClass"] == LIVE_ENDPOINT_CLASS
            and decision["backendProfileDigest"] == c.digest(profile)
            and value["executionConfig"]["backendRef"] == decision["backendRef"], "CONFIG_CHANGED")
        # No alteration of models, sampler, encoding, negative prompt, seed,
        # resource shape, execution code, fee policy, endpoint or launch options.
        profile["parameters"]["positivePrompt"] = subject["description"]
        profile["parameters"]["input"] = {
            "imageName": "acs-user-image-video/" + subject["inputImage"]["contentDigest"] + ".png",
            "contentDigest": subject["inputImage"]["contentDigest"],
        }
        profile["parameters"]["nativeOutput"]["filenamePrefix"] = (
            "acs-user-image-video/" + subject["generationRef"]
        )
        value["backendProfile"] = validate_live_profile(profile)
        decision["backendProfileRef"] = "image-video-profile-" + c.digest(profile)[:48]
        decision["backendProfileDigest"] = c.digest(profile)
        value["backendDecision"] = decision
        lease.assert_held()
        return value

    def _cost_snapshot(self, scope, subject, limits, lease):
        package = {"scope": deepcopy(scope), "subject": deepcopy(subject), "limits": deepcopy(limits)}
        cost = c.validate_cost(self._cost.read_current(package, lease))
        c.require(c.utc(cost["validFrom"]) <= c.utc(limits["notBefore"])
            and c.utc(cost["validUntil"]) >= c.utc(limits["expiresAt"])
            and c.cost_bound(cost, limits) <= limits["maxCostMinor"], "COST_BOUND_UNVERIFIED")
        proofs = self._cost.proof_originals(package, lease)
        c.require(type(proofs) is tuple
            and all(type(proof) is VerifiedOriginalObservation for proof in proofs), "COST_BOUND_UNVERIFIED")
        expected = {}
        for pin in [*cost["sourceEvidence"], cost["billingResponsibility"]["continuingChargesEvidence"]]:
            c.require(pin["ref"] not in expected or expected[pin["ref"]] == pin["digest"], "COST_BOUND_UNVERIFIED")
            expected[pin["ref"]] = pin["digest"]
        c.require(len(proofs) == len(expected), "COST_BOUND_UNVERIFIED")
        observed = {}
        for proof in proofs:
            c.require(proof.owner == "V4_BACKEND_CONFIG" and proof.object_kind == "CostEvidence"
                and proof.object_ref not in observed, "COST_BOUND_UNVERIFIED")
            observed[proof.object_ref] = proof.as_object()["objectDigest"]
        c.require(observed == expected, "COST_BOUND_UNVERIFIED")
        lease.assert_held()
        return cost, proofs

    def _snapshot(self, configuration, attestation, cost, cost_proofs):
        from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
        value = deepcopy(configuration)
        validate_a14b_runtime_attestation(attestation,
            backend_profile=value["backendProfile"], process_identity=value["processIdentity"],
            execution_config=value["executionConfig"])
        decision = value["backendDecision"]
        decision["runtimeAttestationRef"] = attestation["attestationRef"]
        decision["runtimeAttestationDigest"] = attestation["payloadDigest"]
        c.backend.validate_decision(decision)
        entries = (
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "ExecutionConfig", value["executionConfig"]["configRef"], value["executionConfig"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "BackendProfile", decision["backendProfileRef"], value["backendProfile"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "CostBasis", cost["costBasisRef"], cost, "payloadDigest"),
            VerifiedOriginalObservation("RUNTIME_PROCESS", "ProcessIdentity", value["processIdentity"]["instanceRef"], value["processIdentity"]),
            VerifiedOriginalObservation("RUNTIME_PROCESS", "RuntimeAttestation", attestation["attestationRef"], attestation, "payloadDigest"),
        )
        return {"backend": {"decision": decision, "profile": value["backendProfile"],
                "execution_config": value["executionConfig"], "execution_code": value["executionCode"]},
            "runtime": {"process_identity": value["processIdentity"],
                "attestation_file_sha256": sha256(c.canonical(attestation)).hexdigest(),
                "attestation": deepcopy(attestation)},
            "costBasis": deepcopy(cost),
            "proofOriginals": [_proof_value(proof) for proof in (*entries, *cost_proofs)]}

    def prepare_input(self, scope, subject, png_bytes, limits, lease):
        from services.v4_platform.generation_dispatch_a14b_live import LIVE_RUNTIME_SCHEMA
        from services.v4_platform.generation_dispatch_live_result import _validate_png
        configuration = self._configuration_for(scope, subject, limits, lease)
        image = subject["inputImage"]
        c.require(type(png_bytes) is bytes and len(png_bytes) == image["byteSize"]
            and sha256(png_bytes).hexdigest() == image["contentDigest"], "SOURCE_CHANGED")
        _validate_png(png_bytes, image["width"], image["height"])
        # Cost/policy failure must precede even bounded input upload. The caller
        # already holds the original policy-checked coordination lease.
        cost, proofs = self._cost_snapshot(scope, subject, limits, lease)
        lease.assert_held()
        staged = self._stage(deepcopy(configuration), png_bytes, lease)
        c.exact(staged, {"inputName", "contentDigest", "mediaType", "byteSize"})
        c.require(staged == {"inputName": configuration["backendProfile"]["parameters"]["input"]["imageName"],
            "contentDigest": image["contentDigest"], "mediaType": "image/png",
            "byteSize": image["byteSize"]}, "SOURCE_CHANGED")
        self._runtime.assert_output_available(configuration, lease)
        facts = self._runtime.read_current(deepcopy(configuration), lease)
        # Fresh validated facts form a new technical observation. No historical
        # SH09 attestation or frozen package is overwritten or called "current".
        observed_at = self._clock()
        c.utc(observed_at)
        attestation = c.sealed({"schemaVersion": LIVE_RUNTIME_SCHEMA,
            "capabilityMode": "A14B_IMAGE_TO_VIDEO",
            "attestationRef": "image-video-runtime-" + c.digest({"scope": scope, "subject": subject})[:48],
            "observedAt": observed_at, "factsDigest": c.digest(facts), "facts": facts,
            "authorityState": "TECHNICAL_EVIDENCE_ONLY", "publicationAllowed": False})
        lease.assert_held()
        return self._snapshot(configuration, attestation, cost, proofs)

    def verify_current(self, snapshot, scope, subject, limits, lease):
        c.exact(snapshot, {"backend", "runtime", "costBasis", "proofOriginals"})
        configuration = self._configuration_for(scope, subject, limits, lease)
        runtime = c.exact(snapshot["runtime"], {"process_identity", "attestation_file_sha256", "attestation"})
        original = runtime["attestation"]
        c.require(runtime["attestation_file_sha256"] == sha256(c.canonical(original)).hexdigest(), "RUNTIME_CHANGED")
        self._runtime.assert_output_available(configuration, lease)
        observed = self._runtime.read_current(deepcopy(configuration), lease)
        self._runtime.assert_matches_original(configuration, original["facts"], observed, lease)
        cost, proofs = self._cost_snapshot(scope, subject, limits, lease)
        verified = self._snapshot(configuration, original, cost, proofs)
        c.require(c.canonical(verified) == c.canonical(snapshot), "CONFIG_CHANGED")
        lease.assert_held()
        return deepcopy(snapshot)
