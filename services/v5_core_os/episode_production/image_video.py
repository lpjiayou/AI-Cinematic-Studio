"""Authenticated technical inputs, using the original journal and D1 Operator.

This is not a production Shot/Asset owner. The host installs a finite policy and
current material ports. No default policy, endpoint, grant, database or worker is
created at import. Input records reserve a bounded cost even after uncertainty;
read/refresh/restart never resubmit them.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from threading import RLock, Thread
from uuid import UUID, uuid4

from . import generation_dispatch_contracts as c
from . import image_video_contracts as ic
from .evidence import EvidenceRecord
from .generation_dispatch_authority import SelectedApproval
from .generation_dispatch_foundation import BackendObservation, RuntimeObservation
from .generation_dispatch_readers import ResolvedGenerationSubject, VerifiedOriginalObservation
from .generation_workspace import GenerationWorkspaceError

INPUT = "UserImageVideoInput"
APPROVAL = "UserImageVideoApproval"
FAILURE = "UserImageVideoFailure"
MAX_INPUT = 8 * 1024 * 1024
OUTPUT = {"mediaKind": "video", "mediaType": "video/mp4", "width": 704,
    "height": 1280, "durationFrames": 48, "frameRate": 24}


@dataclass(frozen=True)
class ImageVideoInstallation:
    """Trusted host-only construction; never deserialized from HTTP input."""
    policy: dict
    materials: object

    def validate(self):
        p = c.exact(self.policy, {"schemaVersion", "policyRef", "authorityRef", "scope",
            "credentialActors", "limits", "maxTotalCostMinor", "maxGenerations", "payloadDigest"})
        c.require(p["schemaVersion"] == "v5.user-image-video-policy.v1")
        c.ref(p["policyRef"]); c.ref(p["authorityRef"]); c.scope(p["scope"])
        c.validate_limits(p["limits"])
        c.require(c.integer(p["maxTotalCostMinor"]) >= p["limits"]["maxCostMinor"])
        c.require(c.integer(p["maxGenerations"]) <= 100)
        c.require(type(p["credentialActors"]) is dict and bool(p["credentialActors"]))
        for credential, actor in p["credentialActors"].items():
            c.ref(credential); c.ref(actor)
        c.verify_seal(p)
        c.require(callable(getattr(self.materials, "prepare_input", None))
            and callable(getattr(self.materials, "verify_current", None)), "CONFIG_CHANGED")


def normalize_image(raw, media_type):
    """Bounded decode, orientation correction, metadata removal and RGB PNG.

    The original byte digest is retained separately; a JPEG is not relabelled PNG.
    Animated files, invalid formats and decompression bombs are refused.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT:
        raise GenerationWorkspaceError("payload_too_large", 413)
    if media_type not in {"image/png", "image/jpeg"}:
        raise GenerationWorkspaceError("unsupported_media_type", 415)
    try:
        with Image.open(BytesIO(raw)) as image:
            if (image.format != {"image/png": "PNG", "image/jpeg": "JPEG"}[media_type]
                    or getattr(image, "n_frames", 1) != 1
                    or not 0 < image.width <= 16384 or not 0 < image.height <= 16384
                    or image.width * image.height > 16_777_216):
                raise ValueError("unsupported input")
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGB")
            clean = Image.new("RGB", image.size)
            clean.paste(image)
            output = BytesIO()
            clean.save(output, format="PNG", optimize=False, compress_level=6)
            png = output.getvalue()
            if len(png) > MAX_INPUT:
                raise GenerationWorkspaceError("payload_too_large", 413)
            return png, clean.width, clean.height
    except GenerationWorkspaceError:
        raise
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise GenerationWorkspaceError("invalid_image", 400) from exc


def _input_subject(payload):
    meta = payload["input"]
    digest = c.digest(meta)
    png = base64.b64decode(payload["pngBase64"], validate=True)
    c.require(sha256(png).hexdigest() == meta["inputImage"]["contentDigest"]
        and len(png) == meta["inputImage"]["byteSize"], "SOURCE_CHANGED")
    subject = {"schemaVersion": ic.SUBJECT_SCHEMA, "generationRef": meta["generationRef"],
        "inputDigest": digest, "inputImage": deepcopy(meta["inputImage"]),
        "description": meta["description"], "descriptionDigest": sha256(meta["description"].encode()).hexdigest(),
        "cameraInstruction": {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"},
        "outputConstraints": deepcopy(OUTPUT), "executionClass": "MICRO_MOTION", "executionMethod": "SINGLE_ANCHOR_I2V"}
    return ic.validate_subject(subject)


def validate_image_video_record(record):
    """Validate new journal envelopes without granting external callers authority."""
    payload = dict(record.payload)
    c.verify_seal(payload)
    c.require(payload["payloadDigest"] == record.payloadDigest and record.recordVersion == 1
        and payload["createdAt"] == record.createdAt, "SOURCE_CHANGED")
    c.utc(payload["createdAt"])
    if record.recordKind == INPUT:
        c.exact(payload, {"schemaVersion", "input", "pngBase64", "createdAt", "payloadDigest"})
        c.require(payload["schemaVersion"] == "v5.user-image-video-input.v1")
        meta = c.exact(payload["input"], {"generationRef", "scope", "createdAt", "credentialRef", "actorRef",
            "policyDigest", "originalSha256", "originalMediaType", "description", "inputImage"})
        c.scope(meta["scope"])
        c.require(meta["generationRef"] == record.recordRef
            and meta["scope"]["workspaceRef"] == record.workspaceRef
            and meta["scope"]["productionRunRef"] == record.productionRunRef
            and meta["createdAt"] == record.createdAt)
        c.ref(meta["credentialRef"]); c.ref(meta["actorRef"])
        c.sha(meta["policyDigest"]); c.sha(meta["originalSha256"])
        c.require(meta["originalMediaType"] in {"image/png", "image/jpeg"}
            and type(payload["pngBase64"]) is str and len(payload["pngBase64"]) <= (MAX_INPUT + 2) // 3 * 4)
        _input_subject(payload)
    elif record.recordKind == APPROVAL:
        c.exact(payload, {"schemaVersion", "generationRef", "policyDigest", "planPackage",
            "materialSnapshot", "approval", "createdAt", "payloadDigest"})
        c.require(payload["schemaVersion"] == "v5.user-image-video-approval.v1")
        c.validate_plan_package(payload["planPackage"])
        ic.validate_package_approval(payload["planPackage"], payload["approval"])
        c.require(payload["generationRef"] == payload["planPackage"]["plan"]["subject"]["generationRef"]
            and payload["policyDigest"] == payload["approval"]["approvalEvidenceDigest"]
            and record.recordRef == payload["generationRef"] + ":approval"
            and payload["planPackage"]["plan"]["scope"]["workspaceRef"] == record.workspaceRef
            and payload["planPackage"]["plan"]["scope"]["productionRunRef"] == record.productionRunRef)
    else:
        c.exact(payload, {"schemaVersion", "generationRef", "errorCode", "createdAt", "payloadDigest"})
        c.require(payload["schemaVersion"] == "v5.user-image-video-failure.v1"
            and record.recordRef == payload["generationRef"] + ":failure")
        c.ref(payload["generationRef"]); c.ref(payload["errorCode"])


class ImageVideoRuntime:
    """One optional participant of the existing controlled storage composition."""
    def __init__(self, installation, *, evidence, root, coordination, clock):
        installation.validate()
        self.policy = deepcopy(installation.policy)
        self.material_port = installation.materials
        self.evidence, self.root, self.coordination, self.clock = evidence, root, coordination, clock
        self.scope = deepcopy(self.policy["scope"])
        self._lock, self._thread, self._active = RLock(), None, None
        self._pending_materials = {}
        self.operator = None
        # These interfaces are injected as original controlled source ports.
        self.materials = self
        self.prerequisites = _Prerequisites(self)

    def attach_operator(self, operator):
        if self.operator is not None:
            raise RuntimeError("image/video runtime already attached")
        self.operator = operator

    def _auth(self, scope, credential, *, write=False):
        if scope != self.scope:
            raise GenerationWorkspaceError("generation_target_not_found", 404)
        if credential not in self.policy["credentialActors"]:
            raise GenerationWorkspaceError("generation_operation_not_authorized", 403)
        if write:
            self._current_policy()

    def _current_policy(self):
        now, limits = c.utc(self.clock.now()), self.policy["limits"]
        c.require(c.utc(limits["notBefore"]) <= now < c.utc(limits["expiresAt"]), "OUTSIDE_VALIDITY_WINDOW")

    def _record(self, generation_ref, kind=INPUT):
        suffix = {INPUT: "", APPROVAL: ":approval", FAILURE: ":failure"}[kind]
        row = self.evidence.get_record(self.scope["workspaceRef"], self.scope["productionRunRef"],
            c.ref(generation_ref) + suffix, 1)
        c.require(row is not None and row["recordKind"] == kind, "SOURCE_CHANGED")
        c.verify_seal(row["payload"])
        c.require(row["payloadDigest"] == row["payload"]["payloadDigest"], "SOURCE_CHANGED")
        if kind == INPUT:
            c.require(row["payload"]["input"]["scope"] == self.scope, "SCOPE_MISMATCH")
        return row

    def _append(self, kind, reference, payload, key, request_digest):
        payload = c.sealed(payload)
        w, r = self.scope["workspaceRef"], self.scope["productionRunRef"]
        record = EvidenceRecord(w, r, kind, reference, 1, key, request_digest,
            payload["createdAt"], payload, payload["payloadDigest"])
        rows, replay = self.evidence.append_records((record,),
            expected_record_journal_head=self.evidence.record_journal_head(w, r))
        return rows[0], replay

    def _parents(self, lease):
        lease.assert_held()
        c.require(lease.coordinator is self.coordination and lease.workspace_ref == self.scope["workspaceRef"], "SCOPE_MISMATCH")
        s = self.scope
        run = self.root.get_run(s["workspaceRef"], s["productionRunRef"])
        c.require(all(run[k] == v for k, v in s.items()), "SCOPE_MISMATCH")
        # Access context only. No copied M1-M9 readiness or production gate claim.
        context = self.root.project_reader.build_context(s["workspaceRef"], s["projectRef"], s["seriesRef"], s["episodeRef"])
        return {key: context[key] for key in ("project", "series", "episode")}

    def resolve_subject(self, command, lease):
        parents = self._parents(lease)
        c.require(all(command.get(k) == self.scope[k] for k in ("workspaceRef", "productionRunRef")), "SCOPE_MISMATCH")
        row = self._record(command["generationRef"])
        payload = row["payload"]
        c.require(payload["input"]["scope"] == self.scope and payload["input"]["policyDigest"] == self.policy["payloadDigest"], "SOURCE_CHANGED")
        self._current_policy()
        subject = _input_subject(payload)
        objects, selectors = [], {}
        for key, kind in (("project", "CURRENT_PROJECT"), ("series", "CURRENT_SERIES"), ("episode", "CURRENT_EPISODE")):
            owner, field = ic.SELECTORS[kind]
            digest = c.digest(parents[key])
            objects.append({"owner": owner, "objectKind": key.title(), "objectRef": self.scope[field], "objectDigest": digest})
            selectors[kind] = (self.scope[field], digest)
        objects.append({"owner": "V5_EPISODE_PRODUCTION", "objectKind": INPUT,
            "objectRef": subject["generationRef"], "objectDigest": subject["inputDigest"]})
        selectors["CURRENT_INPUT_PLAN"] = (subject["generationRef"], subject["inputDigest"])
        return ResolvedGenerationSubject(deepcopy(self.scope), subject, subject["description"],
            tuple(objects), selectors, {"input": payload})

    def snapshot(self, generation_ref):
        if generation_ref in self._pending_materials:
            return deepcopy(self._pending_materials[generation_ref])
        return deepcopy(self._record(generation_ref, APPROVAL)["payload"]["materialSnapshot"])

    def _verify_material(self, subject, lease):
        self._current_policy()
        snapshot = self.snapshot(subject["generationRef"])
        verified = self.material_port.verify_current(deepcopy(snapshot), deepcopy(self.scope),
            deepcopy(subject), deepcopy(self.policy["limits"]), lease)
        c.require(c.canonical(verified) == c.canonical(snapshot), "CONFIG_CHANGED")
        return snapshot

    def prepare(self, resolved, command, lease):
        snapshot = self._verify_material(resolved.subject, lease)
        b, r = snapshot["backend"], snapshot["runtime"]
        return {"backend": BackendObservation(**b), "runtime": RuntimeObservation(**r), "costBasis": snapshot["costBasis"]}

    def build_read_set(self, resolved, package, approval, phase, lease):
        snapshot = self._verify_material(resolved.subject, lease)
        objects, selectors = list(deepcopy(resolved.objects)), deepcopy(resolved.selectors)
        b, r, cost = snapshot["backend"], snapshot["runtime"], snapshot["costBasis"]
        def add(owner, kind, ref, digest):
            objects.append({"owner": owner, "objectKind": kind, "objectRef": ref, "objectDigest": digest})
        add("V4_BACKEND_CONFIG", "BackendProfile", b["decision"]["backendProfileRef"], c.digest(b["profile"]))
        add("V4_BACKEND_CONFIG", "ExecutionConfig", b["execution_config"]["configRef"], c.digest(b["execution_config"]))
        add("V4_BACKEND_CONFIG", "CostBasis", cost["costBasisRef"], cost["payloadDigest"])
        add("RUNTIME_PROCESS", "ProcessIdentity", r["process_identity"]["instanceRef"], c.digest(r["process_identity"]))
        add("RUNTIME_PROCESS", "RuntimeAttestation", r["attestation"]["attestationRef"], r["attestation"]["payloadDigest"])
        for item in snapshot["proofOriginals"]:
            observation = VerifiedOriginalObservation(item["owner"], item["objectKind"], item["objectRef"], item["original"], item["digestField"])
            objects.append(observation.as_object())
        selectors["CURRENT_BACKEND_CONFIG"] = (b["execution_config"]["configRef"], c.digest(b["execution_config"]))
        selectors["CURRENT_RUNTIME_PROCESS"] = (r["process_identity"]["instanceRef"], c.digest(r["process_identity"]))
        if phase != "PREPARE":
            selected = self.resolve_approval(approval["authorityDecisionRef"])
            c.require(selected.approval == approval, "APPROVAL_UNAVAILABLE")
            add("OWNER_APPROVAL", "ExecutionPolicy", self.policy["policyRef"], self.policy["payloadDigest"])
            add("OWNER_APPROVAL", "UserDecision", approval["authorityDecisionRef"], approval["authorityDecisionDigest"])
            selectors["CURRENT_OWNER_APPROVAL"] = (approval["authorityDecisionRef"], approval["authorityDecisionDigest"])
        rows = []
        for kind, (ref, digest) in selectors.items():
            owner, field = ic.SELECTORS[kind]
            rows.append({"owner": owner, "selectorKind": kind, "scopeRef": self.scope[field], "selectedRef": ref,
                "selectedDigest": digest, "coordinationRevision": self.coordination.revision(lease, owner, kind, self.scope[field])})
        unique = {}
        for item in objects:
            key = (item["owner"], item["objectKind"], item["objectRef"])
            c.require(key not in unique or unique[key] == item, "SOURCE_CHANGED")
            unique[key] = item
        value = {"schemaVersion": ic.READ_SET_SCHEMA, "scope": deepcopy(self.scope), "phase": phase,
            "coordinationEpoch": lease.epoch, "objects": [unique[k] for k in sorted(unique)],
            "selectors": sorted(rows, key=lambda row: (row["owner"], row["selectorKind"], row["scopeRef"]))}
        c.validate_read_set(value, expected_scope=self.scope, phase=phase)
        c.validate_read_set_bindings(value, package["plan"], approval)
        c.validate_read_set_proof_bindings(value, package)
        return value

    def read_current(self, package, approval, phase, lease):
        subject = package["plan"]["subject"]
        resolved = self.resolve_subject({**self.scope, "generationRef": subject["generationRef"]}, lease)
        c.require(resolved.subject == subject, "SOURCE_CHANGED")
        return self.build_read_set(resolved, package, approval, phase, lease)

    def resolve_approval(self, decision_ref):
        prefix = "user-image-video-approval-"
        c.require(decision_ref.startswith(prefix), "APPROVAL_UNAVAILABLE")
        generation_ref = "image-video-" + decision_ref[len(prefix):]
        row = self._record(generation_ref, APPROVAL)["payload"]
        original = self._record(generation_ref)["payload"]["input"]
        c.require(row["policyDigest"] == self.policy["payloadDigest"]
            and original["actorRef"] == self.policy["credentialActors"].get(original["credentialRef"]), "APPROVAL_UNAVAILABLE")
        approval = c.validate_approval(row["approval"], plan=row["planPackage"]["plan"])
        c.require(approval["authorityDecisionRef"] == decision_ref
            and approval["approvalEvidenceDigest"] == self.policy["payloadDigest"]
            and row["planPackage"]["plan"]["subject"] == _input_subject(self._record(generation_ref)["payload"]), "APPROVAL_UNAVAILABLE")
        return SelectedApproval(deepcopy(row["planPackage"]), approval,
            c.digest({"planPackage": row["planPackage"], "approval": approval}))

    def _inputs(self):
        return [row for row in self.evidence.list_records(self.scope["workspaceRef"], self.scope["productionRunRef"], record_kind=INPUT)
            if row["payload"]["input"]["scope"] == self.scope]

    def _job(self, generation_ref):
        jobs = self.operator._coordinator.repository.list(self.scope["workspaceRef"], self.scope["productionRunRef"])
        found = [job for job in jobs if job.get("request", {}).get("schemaVersion") == "v5.user-image-video-generation-request.v1"
            and job["request"]["generationRef"] == generation_ref]
        c.require(len(found) <= 1, "PERSISTENCE_UNAVAILABLE")
        return found[0] if found else None

    def _projection(self, generation_ref):
        original = self._record(generation_ref)["payload"]["input"]
        job = self._job(generation_ref)
        failure = self.evidence.get_record(self.scope["workspaceRef"], self.scope["productionRunRef"], generation_ref + ":failure", 1)
        if job:
            state = "UNKNOWN" if (job.get("dispatchResult") or {}).get("outcome") == "UNKNOWN" else job["state"]
            # A preparation/execution exception must not leave the public view
            # claiming an active queued job forever. Do not change queue facts
            # or authorize a replay when the durable outcome is uncertain.
            if (failure or self._active != generation_ref) and state in {"QUEUED", "LEASED", "RUNNING"}:
                state = "UNKNOWN"
            elif state == "LEASED":
                state = "RUNNING"
            elif state not in {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"}:
                state = "UNKNOWN"
        else:
            state = "PREPARING" if self._active == generation_ref else "FAILED" if failure else "UNKNOWN"
        artifact = None
        if job and state == "SUCCEEDED" and job.get("artifact") and job.get("artifactCommitIntent") is None:
            artifact = {k: job["artifact"][k] for k in ("sha256", "byteSize", "mediaType")}
            artifact.update({k: OUTPUT[k] for k in ("width", "height", "durationFrames", "frameRate")})
        return {"schemaVersion": "creator.image-video-generation.v1",
            **{k: v for k, v in self.scope.items() if k != "workspaceRef"}, "generationRef": generation_ref,
            "mediaJobRef": job["jobRef"] if job else None, "state": state,
            "attemptCount": len(job["attempts"]) if job else 0, "description": original["description"],
            "inputSha256": original["originalSha256"], "createdAt": original["createdAt"],
            "errorCode": failure["payload"]["errorCode"] if failure else ((job or {}).get("dispatchResult") or {}).get("failureCode"),
            "artifact": artifact, "publicationAllowed": False, "automaticRetryAllowed": False}

    def workspace(self, scope, credential_ref):
        self._auth(scope, credential_ref)
        with self._lock, self.coordination.critical_section(scope["workspaceRef"]) as lease:
            self._parents(lease)
            generations = [self._projection(row["recordRef"]) for row in self._inputs()]
            try:
                self._current_policy()
                self._capacity(generations)
                available, reason = True, None
            except (c.DispatchError, GenerationWorkspaceError) as exc:
                available, reason = False, exc.code
            limits = self.policy["limits"]
            return {"schemaVersion": "creator.image-video-workspace.v1",
                **{k: v for k, v in scope.items() if k != "workspaceRef"},
                "policy": {"policyDigest": self.policy["payloadDigest"], "maxInputBytes": MAX_INPUT,
                    "maxDescriptionChars": 1000, "output": {k: OUTPUT[k] for k in ("width", "height", "durationFrames", "frameRate")},
                    "maxCostMinor": limits["maxCostMinor"], "currency": "CNY", "executionTimeoutSeconds": limits["executionTimeoutSeconds"]},
                "available": available, "reason": reason, "generations": generations}

    def _capacity(self, generations):
        inputs = [row for row in self._inputs() if row["payload"]["input"]["policyDigest"] == self.policy["payloadDigest"]]
        if (len(inputs) >= self.policy["maxGenerations"]
                or (len(inputs) + 1) * self.policy["limits"]["maxCostMinor"] > self.policy["maxTotalCostMinor"]):
            raise GenerationWorkspaceError("generation_budget_exhausted", 409)
        if self._active or any(item["state"] in {"PREPARING", "QUEUED", "RUNNING", "UNKNOWN"} for item in generations):
            raise GenerationWorkspaceError("generation_already_active", 409)

    def create(self, scope, credential_ref, command):
        self._auth(scope, credential_ref, write=True)
        if set(command) != {"description", "imageBase64", "imageMediaType", "idempotencyKey", "expectedPolicyDigest"}:
            raise GenerationWorkspaceError("invalid_request", 400)
        description = command["description"]
        if (type(description) is not str or not 0 < len(description) <= 1000 or not description.strip()
                or any(ord(char) < 32 for char in description)):
            raise GenerationWorkspaceError("invalid_description", 400)
        try:
            if str(UUID(command["idempotencyKey"])) != command["idempotencyKey"]:
                raise ValueError()
            if type(command["imageBase64"]) is not str or len(command["imageBase64"]) > (MAX_INPUT + 2) // 3 * 4:
                raise ValueError()
            raw = base64.b64decode(command["imageBase64"], validate=True)
        except (ValueError, TypeError, AttributeError) as exc:
            raise GenerationWorkspaceError("invalid_request", 400) from exc
        if command["expectedPolicyDigest"] != self.policy["payloadDigest"]:
            raise GenerationWorkspaceError("generation_policy_changed", 409)
        png, width, height = normalize_image(raw, command["imageMediaType"])
        original_digest = sha256(raw).hexdigest()
        request_digest = c.digest({"scope": scope, "credentialRef": credential_ref, "originalSha256": original_digest,
            "description": description, "policyDigest": self.policy["payloadDigest"], "mediaType": command["imageMediaType"]})
        key = "user-image-video-" + command["idempotencyKey"]
        with self._lock, self.coordination.critical_section(scope["workspaceRef"]) as lease:
            # Decoding or lock contention may have crossed the approved window.
            # Recheck inside the authoritative boundary before reserving input.
            self._current_policy()
            self._parents(lease)
            previous = self.evidence.get_record_by_idempotency_key(scope["workspaceRef"], scope["productionRunRef"], key)
            if previous:
                if previous["recordKind"] != INPUT or previous["requestDigest"] != request_digest:
                    raise GenerationWorkspaceError("idempotency_conflict", 409)
                return self._projection(previous["recordRef"])
            self._capacity([self._projection(row["recordRef"]) for row in self._inputs()])
            reference = "image-video-" + uuid4().hex
            created = self.clock.now()
            meta = {"generationRef": reference, "scope": deepcopy(scope), "createdAt": created,
                "credentialRef": credential_ref, "actorRef": self.policy["credentialActors"][credential_ref],
                "policyDigest": self.policy["payloadDigest"], "originalSha256": original_digest,
                "originalMediaType": command["imageMediaType"], "description": description,
                "inputImage": {"inputRef": reference + ":input", "contentDigest": sha256(png).hexdigest(),
                    "mediaType": "image/png", "byteSize": len(png), "width": width, "height": height}}
            self._append(INPUT, reference, {"schemaVersion": "v5.user-image-video-input.v1", "input": meta,
                "pngBase64": base64.b64encode(png).decode("ascii"), "createdAt": created}, key, request_digest)
            self._active = reference
            self._thread = Thread(target=self._work, args=(reference,), name="creator-image-video-operator", daemon=False)
            try:
                self._thread.start()
            except Exception:
                self._active, self._thread = None, None
                self._failure(reference, "generation_start_failed")
            return self._projection(reference)

    def _selection(self, generation_ref, *, approved=False):
        from .generation_dispatch_operator import OperatorSelection
        snapshot = self.snapshot(generation_ref)
        b = snapshot["backend"]
        command = {"workspaceRef": self.scope["workspaceRef"], "productionRunRef": self.scope["productionRunRef"],
            "generationRef": generation_ref, "backendRef": b["decision"]["backendRef"],
            "executionConfigRef": b["execution_config"]["configRef"], "costBasisRef": snapshot["costBasis"]["costBasisRef"],
            "limits": deepcopy(self.policy["limits"])}
        if not approved:
            return OperatorSelection(command)
        row = self._record(generation_ref, APPROVAL)["payload"]
        return OperatorSelection(command, c.digest(row["planPackage"]["plan"]), row["approval"]["authorityDecisionRef"],
            generation_ref + ":issue", generation_ref + ":route")

    def _operator_for(self, generation_ref, *, approved=False):
        from .generation_dispatch_operator import GenerationDispatchOperator
        old = self.operator
        return GenerationDispatchOperator(assembly=old._assembly, coordinator=old._coordinator,
            clock=old._clock, worker_context=old._worker, endpoint=old._endpoint,
            selection=self._selection(generation_ref, approved=approved), public_boundaries=old.public_boundaries())

    def _failure(self, generation_ref, code):
        self._append(FAILURE, generation_ref + ":failure", {"schemaVersion": "v5.user-image-video-failure.v1",
            "generationRef": generation_ref, "errorCode": code, "createdAt": self.clock.now()},
            generation_ref + ":failure", c.digest({"generationRef": generation_ref, "errorCode": code}))

    def _work(self, generation_ref):
        try:
            with self.coordination.critical_section(self.scope["workspaceRef"]) as lease:
                resolved = self.resolve_subject({**self.scope, "generationRef": generation_ref}, lease)
                original = resolved.originals["input"]
                snapshot = self.material_port.prepare_input(deepcopy(self.scope), deepcopy(resolved.subject),
                    base64.b64decode(original["pngBase64"], validate=True), deepcopy(self.policy["limits"]), lease)
                c.canonical(snapshot)
                self._pending_materials[generation_ref] = deepcopy(snapshot)
                prepared = self._operator_for(generation_ref).prepare()
                c.require("planPackage" in prepared, prepared.get("code", "CONFIG_CHANGED"))
                package = prepared["planPackage"]
                approval = c.sealed({"approvalRef": generation_ref + ":approval", "authorityRef": self.policy["authorityRef"],
                    "authorityDecisionRef": "user-image-video-approval-" + generation_ref.removeprefix("image-video-"),
                    "actorRef": original["input"]["actorRef"], "actorKind": "HUMAN", "actorRole": "AUTHORIZED_CREATOR",
                    "approvalKind": "USER_IMAGE_VIDEO_EXECUTION", "decision": "APPROVED",
                    "approvedPlanDigest": c.digest(package["plan"]), "approvalEvidenceRef": self.policy["policyRef"],
                    "approvalEvidenceDigest": self.policy["payloadDigest"], "decidedAt": self.clock.now()}, "authorityDecisionDigest")
                c.validate_approval(approval, plan=package["plan"])
                self._append(APPROVAL, generation_ref + ":approval", {"schemaVersion": "v5.user-image-video-approval.v1",
                    "generationRef": generation_ref, "policyDigest": self.policy["payloadDigest"], "planPackage": package,
                    "materialSnapshot": snapshot, "approval": approval, "createdAt": self.clock.now()},
                    generation_ref + ":approval", c.digest(approval))
                self._pending_materials.pop(generation_ref, None)
                operator = self._operator_for(generation_ref, approved=True)
                issued = operator.issue()
                c.require("grant" in issued, issued.get("code", "APPROVAL_UNAVAILABLE"))
                routed = operator.route(issued["grant"]["generationDispatchGrantRef"])
                job_ref = routed["queuedJobs"][0]["mediaJobRef"]
            # No workspace lock over GPU wait; original Executor owns claim and
            # L1/L2 fences. Thread supervision is not another queue/authority.
            operator.execute_one(job_ref)
        except Exception as exc:
            try:
                with self.coordination.critical_section(self.scope["workspaceRef"]):
                    self._failure(generation_ref, exc.code if isinstance(exc, c.DispatchError) else "generation_operation_failed")
            except Exception:
                # An unknown persistence outcome must not be retried or relabelled
                # success. The surviving input projects UNKNOWN after restart.
                pass
        finally:
            with self._lock:
                self._pending_materials.pop(generation_ref, None)
                self._active = None

    def get(self, scope, credential_ref, generation_ref):
        self._auth(scope, credential_ref)
        with self._lock, self.coordination.critical_section(scope["workspaceRef"]):
            try:
                return self._projection(generation_ref)
            except c.DispatchError as exc:
                raise GenerationWorkspaceError("generation_result_not_found", 404) from exc

    def content(self, scope, credential_ref, generation_ref, sha256):
        self._auth(scope, credential_ref)
        with self.coordination.critical_section(scope["workspaceRef"]):
            value = self._projection(generation_ref)
            if value["state"] != "SUCCEEDED" or not value["artifact"] or value["artifact"]["sha256"] != sha256:
                raise GenerationWorkspaceError("generation_result_not_found", 404)
            operator = self._operator_for(generation_ref, approved=True)
            return operator.read_job_content(value["mediaJobRef"])

    def close(self):
        if self._thread is not None:
            self._thread.join()


class _Prerequisites:
    def __init__(self, runtime):
        self.runtime = runtime

    def prepare(self, resolved, command, lease):
        runtime = self.runtime
        return {"inputConsent": {"ref": resolved.subject["generationRef"], "digest": resolved.subject["inputDigest"]},
            "executionPolicy": {"ref": runtime.policy["policyRef"], "digest": runtime.policy["payloadDigest"]},
            "costReview": runtime.snapshot(resolved.subject["generationRef"])["costBasis"]["reviewDecision"]}


class ImageVideoSource:
    def __init__(self, original, runtime):
        self.original, self.runtime = original, runtime
        self.materials, self.prerequisites = original.materials, _PrerequisiteMux(original.prerequisites, runtime)

    def resolve(self, command, lease):
        return self.runtime.resolve_subject(command, lease) if "generationRef" in command else self.original.resolve(command, lease)

    def read_current(self, package, approval, phase, lease):
        if package["plan"]["subject"].get("schemaVersion") == ic.SUBJECT_SCHEMA:
            return self.runtime.read_current(package, approval, phase, lease)
        return self.original.read_current(package, approval, phase, lease)

    def build_read_set(self, resolved, package, approval, phase, lease):
        if resolved.subject.get("schemaVersion") == ic.SUBJECT_SCHEMA:
            return self.runtime.build_read_set(resolved, package, approval, phase, lease)
        return self.original.build_read_set(resolved, package, approval, phase, lease)


class _PrerequisiteMux:
    def __init__(self, original, runtime):
        self.original, self.runtime = original, runtime
    def prepare(self, resolved, command, lease):
        target = self.runtime.prerequisites if "generationRef" in command else self.original
        return target.prepare(resolved, command, lease)


class ImageVideoPort:
    """Selected once during original assembly enrollment, not by HTTP callers."""
    def __init__(self, original, runtime, kind):
        self.original, self.runtime, self.kind = original, runtime, kind

    def resolve(self, reference):
        if reference.startswith("user-image-video-approval-"):
            return self.runtime.resolve_approval(reference)
        return self.original.resolve(reference)

    def prepare(self, resolved, command, lease):
        if "generationRef" in command:
            return self.runtime.prepare(resolved, command, lease)
        return self.original.prepare(resolved, command, lease)

    def read_current(self, *args, **kwargs):
        # Materials' old read_current has 5 positional args, others have 2.
        package = args[0] if self.kind != "materials" else args[1]
        if package["plan"]["subject"].get("schemaVersion") != ic.SUBJECT_SCHEMA:
            return self.original.read_current(*args, **kwargs)
        snapshot = self.runtime._verify_material(package["plan"]["subject"], args[-1])
        if self.kind == "backend":
            return BackendObservation(**snapshot["backend"])
        if self.kind == "runtime":
            return RuntimeObservation(**snapshot["runtime"])
        if self.kind == "cost":
            return deepcopy(snapshot["costBasis"])
        raise c.DispatchError("CONFIG_CHANGED")
