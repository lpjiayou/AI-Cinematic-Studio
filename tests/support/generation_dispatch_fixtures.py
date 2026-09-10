"""Synthetic package-1 fixtures only. No real actor, host, configuration or data.

Trusted doubles are deliberately confined to tests. They cover one synthetic
workspace; they are not evidence of the real 12-Owner writer fence/composition.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import RLock, local
from types import SimpleNamespace
from unittest.mock import patch

from services.v4_platform.backend_registry import BackendRegistry
from services.v4_platform.comfyui import ComfyUIWan22VideoAdapter, REQUIRED_NODES
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production import generation_dispatch_authority as a
from services.v5_core_os.episode_production import generation_dispatch_foundation as f
from services.v5_core_os.episode_production.generation_dispatch_public import GenerationDispatchPublicBoundary
from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord, InMemoryEpisodeProductionEvidenceAdapter, SqliteEpisodeProductionEvidenceAdapter)

NOW = "2030-01-01T00:00:10.000000Z"
START = "2030-01-01T00:00:00.000000Z"
END = "2030-01-01T01:00:00.000000Z"
SOURCE_TEXT = "A synthetic subject turns its head."
TEST_SCOPE = {k: "test-" + k[:-3].lower() for k in c.SCOPE_FIELDS}


def pin(name):
    return {"ref": "test-" + name, "digest": c.digest("test-" + name)}


def make_package():
    profile = {"schemaVersion": "v4.comfyui-i2v-backend-profile.v1",
        "parameters": {"seed": 17, "steps": 20, "cfg": 5.0, "samplerName": "uni_pc", "scheduler": "simple", "modelShift": 5, "negativePrompt": "synthetic blur"},
        "modelFiles": [{"role": role, "name": "test-" + role + ".bin", "sha256": c.digest(role)} for role in ("UNET", "TEXT_ENCODER", "VAE")]}
    facts = {"providerId": "test-provider", "modelId": "test-model", "region": "test-region", "endpointClass": "test-endpoint",
        "comfyuiVersion": "test-version", "pythonVersion": "test-python", "pytorchVersion": "test-torch",
        "deviceName": "test-synthetic-device", "deviceType": "cuda", "vramTotalBytes": 40 * 1024**3,
        "requiredNodes": list(REQUIRED_NODES) + ["LoadImage"], "modelFiles": deepcopy(profile["modelFiles"]),
        "objectInfoDigest": c.digest("test-metadata"), "modelDigestVerification": "LOCAL_FILE_SHA256_VERIFIED",
        "startImageCapability": "LOAD_IMAGE_TO_WAN_START_IMAGE_VERIFIED"}
    attestation = c.sealed({"schemaVersion": "v4.comfyui-runtime-attestation.v2", "capabilityMode": "IMAGE_TO_VIDEO",
        "attestationRef": "test-attestation", "observedAt": START, "factsDigest": c.digest(facts), "facts": facts,
        "authorityState": "TECHNICAL_EVIDENCE_ONLY", "publicationAllowed": False})
    identity = {"backendRef": "test-backend", "backendType": "SELF_HOSTED_SINGLE_GPU",
        "adapterIdentity": "v4.comfyui-wan22-image-to-video.v1", "adapterCapability": "self-hosted-wan22-image-to-video-v1",
        **{k: facts[k] for k in ("providerId", "modelId", "region", "endpointClass")},
        "backendProfileRef": "test-profile", "backendProfileDigest": c.digest(profile), "credentialSourceRef": "test-credential-source",
        "runtimeAttestationRef": attestation["attestationRef"], "runtimeAttestationDigest": attestation["payloadDigest"],
        "costCurrency": "CNY", "maxCostMinor": 2000,
        "resourceShape": {"gpuCount": 1, "minimumVramPerGpu": 1024, "minimumTotalVram": 1024, "distributionMode": "NONE"}}
    registry = BackendRegistry({"schemaVersion": "v4.video-execution-backend-registry.v1", "registryVersion": "test-registry-v1",
        "policy": {"policyRef": "test-policy", "pinnedBackendRef": "test-backend", "maxAttempts": 1, "fallbackAllowed": False},
        "backends": [{**identity, "supportedExecutionClasses": ["MICRO_MOTION"], "supportedExecutionMethods": ["SINGLE_ANCHOR_I2V"],
            "acceptedInputRoles": ["ACTION_READY_ANCHOR"], "supportedOutputFormats": ["video/mp4"], "profile": profile}]})
    decision = registry.resolve("MICRO_MOTION", "SINGLE_ANCHOR_I2V", ["ACTION_READY_ANCHOR"], {"mediaType": "video/mp4"})
    assert registry.profile(decision) == profile
    launch = {"argv": ["test-python", "test-main.py"], "environmentProjection": [{"name": "TEST_SYNTHETIC", "value": "inert"}]}
    config = {"schemaVersion": c.PREFIX + "execution-config.v1", "configRef": "test-config", "configRevision": 1,
        "backendRef": identity["backendRef"], "baseUrlDigest": c.digest("http://test.invalid:1/"),
        "credentialSourceRef": identity["credentialSourceRef"], "credentialBindingRevision": 1,
        **{k: {"locatorRef": "test-" + k, "absolutePathDigest": c.digest("/test-inert/" + k)} for k in ("sourceRoot", "inputRoot", "modelRoot", "artifactRoot")},
        "launchConfiguration": launch, "launchConfigDigest": c.digest(launch), "connectionTimeoutMs": 100,
        "requestTimeoutMs": 1000, "historyTimeoutMs": 3000, "postprocessTimeoutMs": 1000,
        "coordinationMode": "SINGLE_HOST_SINGLE_CONTROL_PROCESS",
        "transportPolicy": {"maxPromptSubmissions": 1, "postRetryAllowed": False, "redirectAllowed": False, "fallbackAllowed": False}}
    process = {"schemaVersion": c.PREFIX + "runtime-process.v1", "instanceRef": "test-instance", "hostBootIdDigest": c.digest("test-boot"),
        "pidNamespaceIdDigest": c.digest("test-namespace"), "comfyuiPid": 17, "processStartTicks": "123", "comfyuiCommit": "a" * 40,
        "launchConfigDigest": c.digest(launch)}
    prerequisite = {k: pin(k) for k in c.PREREQUISITES}
    cost = c.sealed({"schemaVersion": c.PREFIX + "cost-basis.v1", "costBasisRef": "test-cost", "currency": "CNY",
        "sourceEvidence": [pin("billing")], "reviewedByAuthorityRef": "test-cost-owner", "reviewDecision": prerequisite["costReview"],
        "validFrom": START, "validUntil": END, "costScope": "APPROVED_OPERATION_WINDOW_ONLY", "fixedCostMinor": 10,
        "computeUnitSeconds": 60, "computeUnitCostMinor": 5, "computeMinimumUnits": 1, "storageBoundMinor": 2,
        "transferBoundMinor": 3, "otherBoundMinor": 4, "roundingMode": "CEILING_EACH_COMPONENT",
        "billingResponsibility": {"powerStopOwnerRef": "test-power-owner", "dataRetentionOwnerRef": "test-data-owner", "continuingChargesEvidence": pin("continuing")}})
    subject = {"technicalTargetId": "test-single-anchor", "productionRunPayloadDigest": c.digest("test-run"), "manifestDigest": c.digest("test-manifest"),
        **{k: pin(k) for k in ("scriptVersion", "consistencyValidationVersion", "executionMethodPlanVersion", "methodAwareInputPlanVersion", "creativeShotVersion", "actionExecutionBeat", "visualExecutionRequirement")},
        "m6Binding": {"m6BaselineSnapshotRef": "test-m6", "m6BaselineCanonicalDigest": c.digest("test-m6"), "activationRevision": 1, "m6ConsumerBindingDigest": c.digest("test-m6-binding")},
        "inputAsset": {"assetRef": "test-asset", "assetVersionRef": "test-asset-v1", "assetVersionDigest": c.digest("test-asset"),
            "inputRole": "ACTION_READY_ANCHOR", "contentDigest": c.digest("test-png-bytes"), "mediaType": "image/png", "byteSize": 400, "width": 704, "height": 1280},
        "inputAppendAuthority": {**pin("input-authority"), "subjectDigest": c.digest("test-input-subject")},
        "sourceAction": {"sourceSpan": {"scriptSceneRef": "test-scene", "sourceField": "ACTION", "sourceIndex": 0,
            "startOffsetInclusive": 0, "endOffsetExclusive": len(SOURCE_TEXT)}, "sourceTextDigest": sha256(SOURCE_TEXT.encode()).hexdigest()},
        "cameraInstruction": {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"}, "frameRange": {"startFrameInclusive": 0, "endFrameExclusive": 48},
        "outputConstraints": {"mediaKind": "video", "mediaType": "video/mp4", "width": 704, "height": 1280, "durationFrames": 48, "frameRate": 24},
        "executionClass": "MICRO_MOTION", "executionMethod": "SINGLE_ANCHOR_I2V"}
    binding = {"backendDecision": decision, "backendDecisionDigest": c.digest(decision), "executionProfile": {"ref": "test-profile", "digest": c.digest(profile)},
        "executionConfigDigest": c.digest(config), "executionCode": {"coreCommit": "b" * 40, "coreTree": "c" * 40, "comfyuiCommit": "a" * 40},
        "runtimeBinding": {"instanceRef": "test-instance", "processIdentityDigest": c.digest(process), "attestationFileSha256": sha256(c.canonical(attestation)).hexdigest()},
        "workflowDigest": "0" * 64, "costBasis": {"ref": "test-cost", "digest": cost["payloadDigest"]}, "prerequisiteEvidenceDigest": c.digest(prerequisite)}
    plan = {"scope": deepcopy(TEST_SCOPE), "subject": subject, "executionBinding": binding, "permissions": deepcopy(c.PERMISSIONS),
        "limits": {"maxAttempts": 1, "maxPromptSubmissions": 1, "retryAllowed": False, "fallbackAllowed": False, "costCurrency": "CNY",
            "maxCostMinor": 1000, "executionTimeoutSeconds": 60, "notBefore": START, "expiresAt": END, "stopPolicy": "FAIL_CLOSED_NO_RESUBMISSION"}}
    package = {"plan": plan, "materials": {"backendProfile": profile, "executionConfig": config, "processIdentity": process,
        "workflow": {}, "costBasis": cost, "prerequisiteEvidence": prerequisite}}
    rebuild_workflow(package)
    return package, attestation


def rebuild_workflow(package, source_text=SOURCE_TEXT):
    """Call only the original pure build_workflow method, with inert test config.
    No adapter is constructed and no staging/generate method is called."""
    plan, m = package["plan"], package["materials"]
    models = {item["role"]: item["name"] for item in m["backendProfile"]["modelFiles"]}
    holder = SimpleNamespace(config=SimpleNamespace(unet_name=models["UNET"], clip_name=models["TEXT_ENCODER"], vae_name=models["VAE"]))
    request = {"parameters": {**m["backendProfile"]["parameters"], **{k: v for k, v in plan["subject"]["outputConstraints"].items() if k not in ("mediaKind", "mediaType")}},
        "generationRequestRef": "generation-request-" + c.digest(c.request_identity(plan))}
    m["workflow"] = ComfyUIWan22VideoAdapter.build_workflow(holder, request,
        prompt_text=source_text + "; framing: MEDIUM_CLOSE_UP; movement: LOCKED", negative_prompt_text=m["backendProfile"]["parameters"]["negativePrompt"],
        start_image_name="acs-k2-m11/" + plan["subject"]["inputAsset"]["contentDigest"] + ".png", latent_frame_count=plan["subject"]["outputConstraints"]["durationFrames"] + 1)
    plan["executionBinding"]["workflowDigest"] = c.digest(m["workflow"])


def approval_for(package=None, *, grant_digest=None, decision_ref=None):
    revoked = grant_digest is not None
    value = {"approvalRef": "test-revocation" if revoked else "test-approval", "authorityRef": "test-owner",
        "authorityDecisionRef": decision_ref or ("test-revoke-decision" if revoked else "test-issue-decision"), "actorRef": "test-human-lead",
        "actorKind": "HUMAN", "actorRole": "PROJECT_LEAD", "approvalKind": "REVOKE_EXACT_GENERATION_GRANT" if revoked else "EXACT_SUBJECT_GENERATION_EXECUTION",
        "decision": "APPROVED", "approvalEvidenceRef": "test-revoke-original" if revoked else "test-issue-original",
        "approvalEvidenceDigest": c.digest("test-independent-original-revoke" if revoked else "test-independent-original-issue"), "decidedAt": START}
    value["grantDigest" if revoked else "approvedPlanDigest"] = grant_digest if revoked else c.digest(package["plan"])
    return c.sealed(value, "authorityDecisionDigest")


class SyntheticOriginals:
    def __init__(self):
        self.decisions, self.calls, self.failure = {}, [], False

    def register(self, approval):
        self.decisions[approval["authorityDecisionRef"]] = deepcopy(approval)

    def resolve_original(self, authority_ref, decision_ref, evidence_ref, evidence_digest):
        self.calls.append(decision_ref)
        original = self.decisions.get(decision_ref)
        c.require(not self.failure and original is not None, "APPROVAL_UNAVAILABLE")
        c.require((authority_ref, evidence_ref, evidence_digest) == tuple(original[k] for k in ("authorityRef", "approvalEvidenceRef", "approvalEvidenceDigest")), "APPROVAL_UNAVAILABLE")
        return deepcopy(original)


class ControlledClock:
    def __init__(self):
        self.value, self.calls, self.sequence = NOW, 0, []

    def now(self):
        self.calls += 1
        return self.sequence.pop(0) if self.sequence else self.value


class SyntheticFence:
    def __init__(self):
        self.lock, self.thread = RLock(), local()
        self.epoch = c.digest("test-controlled-epoch")
        self.available, self.trace, self.on_enter, self.on_exit = True, [], None, None
        self.workspace_ref = TEST_SCOPE["workspaceRef"]

    @contextmanager
    def critical_section(self, workspace_ref):
        c.require(self.available and workspace_ref == self.workspace_ref, "CURRENTNESS_FENCE_UNAVAILABLE")
        with self.lock:
            self.thread.depth = getattr(self.thread, "depth", 0) + 1
            self.trace.append("enter")
            try:
                if self.on_enter:
                    self.on_enter()
                yield self
            finally:
                self.trace.append("exit")
                self.thread.depth -= 1
                if self.on_exit:
                    self.on_exit()

    def assert_held(self):
        c.require(self.available and getattr(self.thread, "depth", 0) > 0, "CURRENTNESS_FENCE_UNAVAILABLE")


def read_set_for(package, approval, epoch, phase="ISSUE"):
    plan, m = package["plan"], package["materials"]
    s, scope = plan["subject"], plan["scope"]
    selected = {name: pin(name) for name in c.SELECTORS}
    for name, field in (("CURRENT_PROJECT", "projectRef"), ("CURRENT_SERIES", "seriesRef"), ("CURRENT_EPISODE", "episodeRef")):
        selected[name] = {"ref": scope[field], "digest": c.digest(scope[field])}
    for name, field in (("CURRENT_CONFIRMED_SCRIPT", "scriptVersion"), ("CURRENT_M7_PASS", "consistencyValidationVersion"),
        ("CURRENT_METHOD_PLAN", "executionMethodPlanVersion"), ("CURRENT_INPUT_PLAN", "methodAwareInputPlanVersion")):
        selected[name] = s[field]
    selected["ACTIVE_M6_BINDING"] = {"ref": s["m6Binding"]["m6BaselineSnapshotRef"], "digest": s["m6Binding"]["m6BaselineCanonicalDigest"]}
    selected["CURRENT_OWNER_APPROVAL"] = {"ref": approval["authorityDecisionRef"], "digest": approval["authorityDecisionDigest"]}
    selected["CURRENT_BACKEND_CONFIG"] = {"ref": m["executionConfig"]["configRef"], "digest": c.digest(m["executionConfig"])}
    selected["CURRENT_RUNTIME_PROCESS"] = {"ref": m["processIdentity"]["instanceRef"], "digest": c.digest(m["processIdentity"])}
    for name, field in (("CURRENT_IDENTITY_REFERENCE", "identityReferenceEvaluation"), ("CURRENT_RIGHTS_EVALUATION", "rightsEvaluation"),
        ("CURRENT_PROVIDER_POLICY", "providerPolicyEvaluation")):
        selected[name] = m["prerequisiteEvidence"][field]
    selectors, objects = [], []
    def add(owner, kind, value):
        objects.append({"owner": owner, "objectKind": kind, "objectRef": value["ref"], "objectDigest": value["digest"]})
    for name, (owner, scope_key) in c.SELECTORS.items():
        if name == "CURRENT_OWNER_APPROVAL" and phase == "PREPARE":
            continue
        value = selected[name]
        selectors.append({"owner": owner, "selectorKind": name, "scopeRef": scope[scope_key], "selectedRef": value["ref"], "selectedDigest": value["digest"], "coordinationRevision": 0})
        add(owner, name, value)
    for name in ("creativeShotVersion", "actionExecutionBeat", "visualExecutionRequirement"):
        add("V5_EPISODE_PRODUCTION", name, s[name])
    for name, ref_key, digest_key in (("inputAsset", "assetVersionRef", "assetVersionDigest"), ("inputAppendAuthority", "ref", "digest")):
        add("V5_EPISODE_PRODUCTION", name, {"ref": s[name][ref_key], "digest": s[name][digest_key]})
    add("V5_EPISODE_PRODUCTION", "ProductionRun", {"ref": scope["productionRunRef"], "digest": s["productionRunPayloadDigest"]})
    add("V4_BACKEND_CONFIG", "backendProfile", plan["executionBinding"]["executionProfile"])
    add("V4_BACKEND_CONFIG", "costBasis", plan["executionBinding"]["costBasis"])
    for name, owner in (("scriptOwnerAcceptance", "V5_SCRIPT"), ("costReview", "V4_BACKEND_CONFIG")):
        add(owner, name, m["prerequisiteEvidence"][name])
    add("OWNER_APPROVAL", "ApprovalOriginal", {"ref": approval["approvalEvidenceRef"], "digest": approval["approvalEvidenceDigest"]})
    return {"schemaVersion": c.PREFIX + "read-set.v1", "scope": deepcopy(scope), "phase": phase, "coordinationEpoch": epoch,
        "objects": sorted(objects, key=lambda o: (o["owner"], o["objectKind"], o["objectRef"])),
        "selectors": sorted(selectors, key=lambda o: (o["owner"], o["selectorKind"], o["scopeRef"]))}


class SyntheticReaders:
    def __init__(self, package, attestation):
        self.package, self.attestation = deepcopy(package), deepcopy(attestation)
        self.calls, self.failure, self.source_hook = [], None, None

    def check(self, name, lease):
        lease.assert_held()
        self.calls.append(name)
        if self.failure == name:
            raise c.DispatchError({"source": "SOURCE_CHANGED", "backend": "CONFIG_CHANGED", "runtime": "RUNTIME_CHANGED", "cost": "COST_BOUND_UNVERIFIED"}[name])

    def source(self, package, approval, phase, lease):
        self.check("source", lease)
        if self.source_hook:
            self.source_hook()
        c.require(c.canonical(package["plan"]["subject"]) == c.canonical(self.package["plan"]["subject"]), "SOURCE_CHANGED")
        return read_set_for(self.package, approval, lease.epoch, phase)

    def backend(self, package, lease):
        self.check("backend", lease)
        b, m = self.package["plan"]["executionBinding"], self.package["materials"]
        return f.BackendObservation(deepcopy(b["backendDecision"]), deepcopy(m["backendProfile"]), deepcopy(m["executionConfig"]), deepcopy(b["executionCode"]))

    def runtime(self, package, lease):
        self.check("runtime", lease)
        return f.RuntimeObservation(deepcopy(self.package["materials"]["processIdentity"]),
            self.package["plan"]["executionBinding"]["runtimeBinding"]["attestationFileSha256"], deepcopy(self.attestation))

    def cost(self, package, lease):
        self.check("cost", lease)
        return deepcopy(self.package["materials"]["costBasis"])


class Fixture:
    def __init__(self, case, *, memory=False):
        self.temp = tempfile.TemporaryDirectory(prefix="test-grant-")
        case.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.package, self.attestation = make_package()
        self.approval = approval_for(self.package)
        self.originals, self.fence, self.clock = SyntheticOriginals(), SyntheticFence(), ControlledClock()
        self.readers = SyntheticReaders(self.package, self.attestation)
        self.path = self.root / "evidence.sqlite3"
        self.repo = InMemoryEpisodeProductionEvidenceAdapter() if memory else SqliteEpisodeProductionEvidenceAdapter(self.path, initialize_if_missing=True)
        self.approval_reader = self.write_approval()
        self.revocation_reader = None
        self.service = self.make_service()
        self.public = GenerationDispatchPublicBoundary(self.service)

    def write_approval(self):
        self.originals.register(self.approval)
        self.bundle = {"schemaVersion": c.APPROVAL_SCHEMA, "authorityRef": "test-owner", "approvals": [{"planPackage": deepcopy(self.package), "approval": deepcopy(self.approval)}]}
        self.approval_path = self.root / "test-approval.json"
        self.approval_path.write_bytes(c.canonical(self.bundle))
        self.approval_pin = sha256(self.approval_path.read_bytes()).hexdigest()
        return a.PinnedApprovalReader(self.approval_path, self.approval_pin, original=self.originals)

    def make_service(self, repo=None):
        return f.GenerationDispatchFoundation(repository=self.repo if repo is None else repo, approval_reader=self.approval_reader,
            revocation_reader=self.revocation_reader, source_reader=SimpleNamespace(read_current=self.readers.source),
            backend_reader=SimpleNamespace(read_current=self.readers.backend), runtime_reader=SimpleNamespace(read_current=self.readers.runtime),
            cost_reader=SimpleNamespace(read_current=self.readers.cost), coordination=self.fence, clock=self.clock, issuer_service_ref="test-v5-issuer")

    def snapshot(self):
        return {"recordJournalHead": self.repo.record_journal_head(self.package["plan"]["scope"]["workspaceRef"], self.package["plan"]["scope"]["productionRunRef"]),
            "workspaceRecordJournalHead": self.repo.workspace_record_journal_head(self.package["plan"]["scope"]["workspaceRef"]),
            "evidenceRevisionToken": self.repo.read_snapshot(self.package["plan"]["scope"]["workspaceRef"], self.package["plan"]["scope"]["productionRunRef"]).revisionToken}

    def command(self, key="test-issue-key"):
        s, b = self.package["plan"]["subject"], self.package["plan"]["executionBinding"]
        return {"workspaceRef": self.package["plan"]["scope"]["workspaceRef"], "productionRunRef": self.package["plan"]["scope"]["productionRunRef"],
            "methodAwareInputPlanVersionRef": s["methodAwareInputPlanVersion"]["ref"], "creativeShotVersionRef": s["creativeShotVersion"]["ref"],
            "beatRef": s["actionExecutionBeat"]["ref"], "inputAssetVersionRef": s["inputAsset"]["assetVersionRef"], "backendRef": b["backendDecision"]["backendRef"],
            "expectedSubjectDigest": c.subject_digest(self.package["plan"]), "expectedApprovedPlanDigest": c.digest(self.package["plan"]),
            "authorityDecisionRef": self.approval["authorityDecisionRef"], "idempotencyKey": key, "snapshotTokens": self.snapshot()}

    def inspect_command(self):
        return {"workspaceRef": self.package["plan"]["scope"]["workspaceRef"], "productionRunRef": self.package["plan"]["scope"]["productionRunRef"], "generationDispatchGrantRef": c.grant_ref(self.package["plan"])}

    def revoke_command(self, grant, key="test-revoke-key"):
        self.revocation = approval_for(grant_digest=grant["payloadDigest"])
        self.originals.register(self.revocation)
        bundle = {"schemaVersion": c.REVOCATION_SCHEMA, "authorityRef": "test-owner", "revocations": [self.revocation]}
        path = self.root / "test-revocation.json"
        path.write_bytes(c.canonical(bundle))
        self.revocation_reader = a.PinnedApprovalReader(path, sha256(path.read_bytes()).hexdigest(), original=self.originals, revocation=True)
        self.service.revocation_reader = self.revocation_reader
        return {**self.inspect_command(), "generationDispatchGrantDigest": grant["payloadDigest"], "authorityDecisionRef": self.revocation["authorityDecisionRef"],
            "idempotencyKey": key, "snapshotTokens": self.snapshot()}

    def records(self):
        return self.repo.list_records(self.package["plan"]["scope"]["workspaceRef"], self.package["plan"]["scope"]["productionRunRef"])

    def reopen(self):
        self.repo = SqliteEpisodeProductionEvidenceAdapter(self.path, initialize_if_missing=False)
        self.service = self.make_service()
        self.public = GenerationDispatchPublicBoundary(self.service)


def synthetic_consumption(fixture, grant):
    """Preloaded terminal data for rejection tests, not a consume implementation."""
    read_set = read_set_for(fixture.package, fixture.approval, fixture.fence.epoch, "CONSUME")
    terminal = c.sealed({"schemaVersion": c.TERMINAL_SCHEMA, "grantTerminalRef": grant["generationDispatchGrantRef"] + ":terminal",
        "generationDispatchGrantRef": grant["generationDispatchGrantRef"], "generationDispatchGrantDigest": grant["payloadDigest"],
        "workspaceRef": grant["workspaceRef"], "productionRunRef": grant["productionRunRef"], "kind": "CONSUMPTION_COMMITTED", "revocationApproval": None,
        "attemptBinding": {"mediaJobRef": "test-never-executed-job", "attemptRef": "test-never-executed-attempt", "workerRef": "test-worker",
            "workerProcessIdentityDigest": c.digest("test-controller"), "jobRevision": 1, "leaseTokenDigest": c.digest("test-inert-lease"),
            "executionEnvelopeDigest": c.digest("test-inert-envelope"), "workflowDigest": grant["executionBinding"]["workflowDigest"],
            "currentSubjectReadSet": read_set, "currentSubjectReadSetDigest": c.digest(read_set)},
        "requestDigest": c.digest("test-preload-only"), "snapshotTokens": fixture.snapshot(), "createdAt": NOW})
    command = {k: terminal[k] for k in ("workspaceRef", "productionRunRef", "generationDispatchGrantRef", "generationDispatchGrantDigest")}
    command.update({k: terminal["attemptBinding"][k] for k in ("mediaJobRef", "attemptRef", "workerRef")})
    command["expectedLeaseTokenDigest"] = terminal["attemptBinding"]["leaseTokenDigest"]
    terminal["requestDigest"] = c.consumption_request_digest(command, grant["payloadDigest"], terminal["attemptBinding"])
    terminal = c.sealed(terminal)
    return EvidenceRecord(grant["workspaceRef"], grant["productionRunRef"], "GenerationDispatchGrantTerminal", terminal["grantTerminalRef"], 1,
        "test-preloaded-consumption", terminal["requestDigest"], NOW, terminal, terminal["payloadDigest"])


class ConnectionFault:
    """Test-only wrapper around an actual adapter connection; never creates DDL."""
    def __init__(self, connection, phase):
        self.connection, self.phase, self.inserted = connection, phase, False

    def __getattr__(self, key):
        return getattr(self.connection, key)

    def execute(self, sql, parameters=()):
        result = self.connection.execute(sql, parameters)
        if sql.startswith("INSERT INTO v5_episode_production_records"):
            self.inserted = True
        if self.inserted and self.phase == "after_insert":
            raise sqlite3.OperationalError("test fault after actual insert before commit")
        return result

    def commit(self):
        if self.phase == "before_commit":
            raise sqlite3.OperationalError("test fault before actual commit")
        self.connection.commit()
        if self.phase == "after_commit":
            raise sqlite3.OperationalError("test receipt lost after actual commit")


@contextmanager
def fault_at(repo, phase):
    original = repo._connect
    with patch.object(repo, "_connect", side_effect=lambda: ConnectionFault(original(), phase)):
        yield


class TransactionObservation:
    """Forward actual SQLite operations; advance only the synthetic trusted clock."""
    def __init__(self, fixture, *, advance_at=None, value=END, clock_error=None,
                 rollback_fault=None, close_fault=False):
        self.fixture, self.advance_at, self.value = fixture, advance_at, value
        self.clock_error, self.rollback_fault = clock_error, rollback_fault
        self.close_fault = close_fault
        self.events, self.connections, self.advanced = [], [], False

    def event(self, phase, **fields):
        entry = {"phase": phase, "inTransaction": any(
            connection.in_transaction for connection in self.connections), **fields}
        self.events.append(entry)
        return entry

    def advance(self, phase):
        if phase == self.advance_at and not self.advanced:
            self.fixture.clock.value = self.value
            self.advanced = True
            self.event("CLOCK_ADVANCED", value=self.value, after=phase)

    @contextmanager
    def observe(self):
        original_connect = self.fixture.repo._connect
        original_now = self.fixture.clock.now
        original_decode = self.fixture.repo._decode_record
        owner = self

        class Connection:
            def __init__(self, connection):
                self.connection, self.closed = connection, False
                self.write_started = False
                owner.connections.append(self)

            @property
            def in_transaction(self):
                return False if self.closed else self.connection.in_transaction

            def __getattr__(self, key):
                return getattr(self.connection, key)

            def execute(self, sql, parameters=()):
                result = self.connection.execute(sql, parameters)
                if sql == "BEGIN IMMEDIATE":
                    self.write_started = True
                    owner.event("BEGIN_COMPLETED")
                    owner.advance("BEGIN_COMPLETED")
                elif sql.startswith("INSERT INTO v5_episode_production_records"):
                    owner.event("INSERT_COMPLETED", recordKind=parameters[3],
                        recordRef=parameters[4], payloadDigest=parameters[9], createdAt=parameters[10])
                    owner.advance("INSERT_COMPLETED")
                return result

            def commit(self):
                owner.event("COMMIT_CALLED")
                self.connection.commit()
                owner.event("COMMIT_COMPLETED")

            def rollback(self):
                owner.event("ROLLBACK_CALLED")
                if self.write_started and owner.rollback_fault == "before":
                    owner.event("ROLLBACK_RAISED", fault="before")
                    raise sqlite3.OperationalError("test rollback acknowledgement unavailable")
                self.connection.rollback()
                owner.event("ROLLBACK_COMPLETED")
                if self.write_started and owner.rollback_fault == "after":
                    owner.event("ROLLBACK_RAISED", fault="after")
                    raise sqlite3.OperationalError("test rollback receipt unavailable")

            def close(self):
                was_active = self.in_transaction
                self.connection.close()
                self.closed = True
                if was_active:
                    owner.event("CLOSE_COMPLETED", activeBeforeClose=was_active)
                if self.write_started and owner.close_fault:
                    owner.event("CLOSE_RAISED", actualCloseCompleted=self.closed)
                    raise sqlite3.OperationalError("test close receipt unavailable")

        def now():
            if self.advanced and self.clock_error is not None:
                self.event("CLOCK_RAISED", exception=type(self.clock_error).__name__)
                raise self.clock_error
            value = original_now()
            self.event("CLOCK_READ", value=value)
            return value

        def decode(row):
            result = original_decode(row)
            if any(connection.in_transaction for connection in self.connections):
                self.event("DECODE_COMPLETED", recordKind=result["recordKind"])
            return result

        with patch.object(self.fixture.repo, "_connect", side_effect=lambda: Connection(original_connect())), \
                patch.object(self.fixture.clock, "now", side_effect=now), \
                patch.object(self.fixture.repo, "_decode_record", side_effect=decode):
            yield self


def save_evidence(name, value):
    """Optional test runner-owned evidence directory; no production configuration."""
    location = os.environ.get("PKG1_TEST_EVIDENCE_DIR")
    if location:
        root = Path(location)
        assert root.is_dir() and Path(name).name == name
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
