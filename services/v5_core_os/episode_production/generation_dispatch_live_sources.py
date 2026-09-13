"""Trusted original-file reader adapters for D1's existing Owner ports.

Bindings are installed by the internal composition, never accepted in an
Operator command. Original schema/decision semantics remain with the respective
Owner verifier; this reader cannot mint an approval or a NOT_REQUIRED decision.
"""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from . import generation_dispatch_contracts as c
from .generation_dispatch_authority import read_pinned_file
from .generation_dispatch_foundation import BackendObservation, RuntimeObservation
from .generation_dispatch_readers import VerifiedOriginalObservation, VerifiedOwnerContribution


@dataclass(frozen=True)
class OriginalFile:
    path: Path
    file_sha256: str

    def read(self):
        return c.strict_json(read_pinned_file(Path(self.path), self.file_sha256))


class LiveRuntimeCurrentReader:
    """Observe through the host's authenticated metadata/original-file ports.

    Ports are installed in the trusted host, not a CLI payload. The host observer
    must return current complete facts from the selected instance and verify the
    selected six byte streams (or its controlled immutable-retention originals).
    It may not use the pinned attestation as its observation. No SSH locator is
    guessed here, and no network client or provider stack is created.
    """
    def __init__(self, *, host_observer, input_observer, tool_observer):
        c.require(all(callable(p) for p in (host_observer, input_observer, tool_observer)),
            "CURRENTNESS_FENCE_UNAVAILABLE")
        self._host, self._input, self._tools = host_observer, input_observer, tool_observer

    def read_current(self, configuration, lease):
        from services.v4_platform.generation_dispatch_a14b_live import LIVE_RUNTIME_SCHEMA
        from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
        lease.assert_held()
        # The original attestation file is deliberately not passed to observers.
        observed = self._host(deepcopy(configuration), lease)
        c.require(type(observed) is dict and observed.get("schemaVersion") == LIVE_RUNTIME_SCHEMA, "RUNTIME_CHANGED")
        try:
            facts = validate_a14b_runtime_attestation(observed,
                backend_profile=configuration["backendProfile"], process_identity=configuration["processIdentity"],
                execution_config=configuration["executionConfig"])
        except (ValueError, KeyError, TypeError) as exc:
            raise c.DispatchError("RUNTIME_CHANGED") from exc
        profile = configuration["backendProfile"]
        source = self._input(deepcopy(configuration), lease)
        c.exact(source, {"inputName", "contentDigest", "inputRootDigest", "outputRootDigest", "outputPrefixAbsent"})
        c.require(source["inputName"] == profile["parameters"]["input"]["imageName"]
            and source["contentDigest"] == profile["parameters"]["input"]["contentDigest"]
            and source["inputRootDigest"] == configuration["executionConfig"]["inputRoot"]["absolutePathDigest"]
            and source["outputRootDigest"] == configuration["executionConfig"]["artifactRoot"]["absolutePathDigest"]
            and type(source["outputPrefixAbsent"]) is bool, "SOURCE_CHANGED")
        c.require(c.canonical(self._tools()) == c.canonical(profile["parameters"]["postprocess"]["toolIdentity"]),
            "RUNTIME_CHANGED")
        lease.assert_held()
        return facts

    def assert_output_available(self, configuration, lease):
        lease.assert_held()
        source = self._input(deepcopy(configuration), lease)
        c.require(source.get("outputPrefixAbsent") is True, "SOURCE_CHANGED")
        lease.assert_held()


class PinnedOwnerOriginal:
    """Independent authority association + original verifier, not a boolean pin."""
    def __init__(self, *, binding, authority_ref, actor_ref, evidence, verifier):
        c.ref(authority_ref); c.ref(actor_ref)
        c.require(type(binding) is OriginalFile and type(evidence) is OriginalFile
            and callable(verifier), "APPROVAL_UNAVAILABLE")
        self._binding, self._evidence = binding, evidence
        self._authority, self._actor, self._verify = authority_ref, actor_ref, verifier

    def resolve_original(self, authority_ref, decision_ref, evidence_ref, evidence_digest):
        c.require(authority_ref == self._authority, "APPROVAL_UNAVAILABLE")
        original, evidence = self._binding.read(), self._evidence.read()
        c.validate_approval(original)
        c.require(original["authorityRef"] == self._authority and original["actorRef"] == self._actor
            and original["authorityDecisionRef"] == decision_ref
            and original["approvalEvidenceRef"] == evidence_ref
            and original["approvalEvidenceDigest"] == evidence_digest
            and c.digest(evidence) == evidence_digest, "APPROVAL_UNAVAILABLE")
        verified = self._verify(deepcopy(original), deepcopy(evidence))
        c.require(type(verified) is dict and c.canonical(verified) == c.canonical(original), "APPROVAL_UNAVAILABLE")
        return original


class PinnedLiveMaterials:
    """Original configuration plus fresh runtime and cost authority ports.

runtime_current.read_current must observe the selected host, not load this
configuration's embedded attestation as its own corroboration. Cost proofs are
returned by the existing cost Owner including full rate/bound/continuing-charge
originals. Configuration cannot substitute for either independent port.
"""
    def __init__(self, *, configuration, runtime_original, runtime_current, cost_owner):
        c.require(type(configuration) is OriginalFile and type(runtime_original) is OriginalFile
            and callable(getattr(runtime_current, "read_current", None))
            and callable(getattr(runtime_current, "assert_output_available", None))
            and callable(getattr(cost_owner, "read_current", None))
            and callable(getattr(cost_owner, "proof_originals", None)), "CURRENTNESS_FENCE_UNAVAILABLE")
        self._configuration, self._runtime_file = configuration, runtime_original
        self._runtime_current, self._cost_owner = runtime_current, cost_owner

    def _read(self, lease):
        lease.assert_held()
        value = self._configuration.read()
        c.exact(value, {"backendDecision", "backendProfile", "executionConfig", "executionCode", "processIdentity"})
        from services.v4_platform.generation_dispatch_a14b_live import validate_live_profile, LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS
        validate_live_profile(value["backendProfile"])
        c.validate_execution_config(value["executionConfig"])
        c.validate_process(value["processIdentity"])
        decision = c.backend.validate_decision(value["backendDecision"])
        c.require(decision["adapterIdentity"] == LIVE_ADAPTER_IDENTITY
            and decision["adapterCapability"] == LIVE_CAPABILITY and decision["endpointClass"] == LIVE_ENDPOINT_CLASS,
            "CONFIG_CHANGED")
        c.require(decision["backendProfileDigest"] == c.digest(value["backendProfile"]), "CONFIG_CHANGED")
        return value

    def backend(self, package, lease):
        value = self._read(lease)
        return BackendObservation(value["backendDecision"], value["backendProfile"],
            value["executionConfig"], value["executionCode"])

    def runtime(self, package, lease):
        from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
        value, original = self._read(lease), self._runtime_file.read()
        facts = validate_a14b_runtime_attestation(original, backend_profile=value["backendProfile"],
            process_identity=value["processIdentity"], execution_config=value["executionConfig"])
        observed = self._runtime_current.read_current(deepcopy(value), lease)
        # The current reader returns full facts, not a trusted=True flag. It must
        # check process/launch, six model bytes or trusted immutable retention,
        # node contracts, source/input reachability and tool/host identity.
        c.require(type(observed) is dict and c.canonical(observed) == c.canonical(facts), "RUNTIME_CHANGED")
        lease.assert_held()
        return RuntimeObservation(value["processIdentity"], self._runtime_file.file_sha256, original)

    def cost(self, package, lease):
        return c.validate_cost(self._cost_owner.read_current(package, lease))

    def prepare(self, resolved, command, lease):
        self._runtime_current.assert_output_available(self._read(lease), lease)
        return {"backend": self.backend(None, lease), "runtime": self.runtime(None, lease),
            "costBasis": self.cost({"scope": resolved.scope, "limits": command["limits"]}, lease)}

    def read_current(self, resolved, package, approval, phase, lease):
        value = self._read(lease)
        self._runtime_current.assert_output_available(value, lease)
        runtime, cost = self.runtime(package, lease), self.cost(package, lease)
        decision = value["backendDecision"]
        c.require(c.canonical(value["backendProfile"]) == c.canonical(package["materials"]["backendProfile"])
            and c.canonical(value["executionConfig"]) == c.canonical(package["materials"]["executionConfig"]), "CONFIG_CHANGED")
        entries = (
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "ExecutionConfig", value["executionConfig"]["configRef"], value["executionConfig"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "BackendProfile", decision["backendProfileRef"], value["backendProfile"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "CostBasis", cost["costBasisRef"], cost, "payloadDigest"),
            VerifiedOriginalObservation("RUNTIME_PROCESS", "ProcessIdentity", runtime.process_identity["instanceRef"], runtime.process_identity),
            VerifiedOriginalObservation("RUNTIME_PROCESS", "RuntimeAttestation", runtime.attestation["attestationRef"], runtime.attestation, "payloadDigest"),
        )
        proofs = self._cost_owner.proof_originals(package, lease)
        c.require(type(proofs) is tuple and all(type(o) is VerifiedOriginalObservation for o in proofs), "COST_BOUND_UNVERIFIED")
        return VerifiedOwnerContribution((*entries, *proofs), {
            "CURRENT_BACKEND_CONFIG": (entries[0].object_ref, entries[0].as_object()["objectDigest"]),
            "CURRENT_RUNTIME_PROCESS": (entries[3].object_ref, entries[3].as_object()["objectDigest"])})


class PinnedPrerequisiteOriginals:
    """Five existing Owner decisions, independently verified at every gate.

    A verifier is installed by its existing Owner, not deserialized from the
    selected file. In particular this adapter cannot decide NOT_REQUIRED.
    """
    _owners = {"scriptOwnerAcceptance": ("V5_SCRIPT", None),
        "costReview": ("V4_BACKEND_CONFIG", None),
        "identityReferenceEvaluation": ("V5_IDENTITY", "CURRENT_IDENTITY_REFERENCE"),
        "rightsEvaluation": ("V5_RIGHTS", "CURRENT_RIGHTS_EVALUATION"),
        "providerPolicyEvaluation": ("V5_PROVIDER_POLICY", "CURRENT_PROVIDER_POLICY")}

    def __init__(self, *, originals, verifiers, approval_original, approval_evidence):
        c.require(set(originals) == set(verifiers) == set(self._owners)
            and all(type(v) is OriginalFile for v in originals.values())
            and all(callable(v) for v in verifiers.values())
            and type(approval_original) is PinnedOwnerOriginal
            and type(approval_evidence) is OriginalFile, "APPROVAL_UNAVAILABLE")
        self._originals, self._verifiers = dict(originals), dict(verifiers)
        self._approval_original, self._approval_evidence = approval_original, approval_evidence

    def _read(self, resolved, lease):
        lease.assert_held()
        records = {}
        for kind, file in self._originals.items():
            original = file.read()
            verified = self._verifiers[kind](deepcopy(original), resolved, lease)
            c.require(type(verified) is VerifiedOriginalObservation
                and verified.owner == self._owners[kind][0] and verified.object_kind == kind
                and c.canonical(verified.original) == c.canonical(original), "SOURCE_CHANGED")
            records[kind] = verified
        lease.assert_held()
        return records

    def prepare(self, resolved, command, lease):
        return {k: {"ref": o.object_ref, "digest": o.as_object()["objectDigest"]}
            for k, o in self._read(resolved, lease).items()}

    def read_current(self, resolved, package, approval, phase, lease):
        records = self._read(resolved, lease)
        selectors = {}
        for kind, observation in records.items():
            pin = {"ref": observation.object_ref, "digest": observation.as_object()["objectDigest"]}
            c.require(pin == package["materials"]["prerequisiteEvidence"][kind], "SOURCE_CHANGED")
            selector = self._owners[kind][1]
            if selector:
                selectors[selector] = (pin["ref"], pin["digest"])
        observations = list(records.values())
        if phase != "PREPARE":
            c.require(approval is not None, "APPROVAL_UNAVAILABLE")
            original = self._approval_original.resolve_original(approval["authorityRef"],
                approval["authorityDecisionRef"], approval["approvalEvidenceRef"], approval["approvalEvidenceDigest"])
            c.require(c.canonical(original) == c.canonical(approval), "APPROVAL_UNAVAILABLE")
            observations.extend((VerifiedOriginalObservation("OWNER_APPROVAL", "OwnerDecision",
                approval["authorityDecisionRef"], original, "authorityDecisionDigest"),
                VerifiedOriginalObservation("OWNER_APPROVAL", "ApprovalOriginal",
                    approval["approvalEvidenceRef"], self._approval_evidence.read())))
            selectors["CURRENT_OWNER_APPROVAL"] = (approval["authorityDecisionRef"], approval["authorityDecisionDigest"])
        return VerifiedOwnerContribution(tuple(observations), selectors)
