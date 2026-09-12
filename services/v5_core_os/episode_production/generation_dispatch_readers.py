"""Read exact original Owner facts for generation dispatch; never append sources."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from . import generation_dispatch_contracts as c
from .foundation import EpisodeProductionService, EpisodeProductionError
from .method_aware_media import M10M11MethodAwareMediaService
from .method_aware_input_assets import (
    MethodAwareInputAssetService, RECEIPT_KIND, exact_record,
    validate_asset_version, validate_receipt_authority,
)


def _one(values, predicate):
    matches = [v for v in values if predicate(v)]
    c.require(len(matches) == 1, "SOURCE_CHANGED")
    return deepcopy(matches[0])


def _persisted(value):
    # These two fields are explicitly computed by the existing read services.
    payload = {k: deepcopy(v) for k, v in value.items()
        if k not in {"currentness", "idempotentReplay"}}
    c.verify_seal(payload)
    return payload


@dataclass(frozen=True)
class ResolvedGenerationSubject:
    scope: dict
    subject: dict
    source_text: str
    objects: tuple
    selectors: dict
    originals: dict


@dataclass(frozen=True)
class VerifiedOriginalObservation:
    """Internal trusted-port observation of a complete original, never a DTO."""
    owner: str
    object_kind: str
    object_ref: str
    original: dict
    digest_field: str | None = None

    def as_object(self):
        c.ref(self.object_ref)
        if self.digest_field is None:
            digest = c.digest(self.original)
        else:
            c.verify_seal(self.original, self.digest_field)
            digest = self.original[self.digest_field]
        return {"owner": self.owner, "objectKind": self.object_kind,
            "objectRef": self.object_ref, "objectDigest": digest}


@dataclass(frozen=True)
class VerifiedOwnerContribution:
    originals: tuple[VerifiedOriginalObservation, ...]
    selectors: dict

    def read(self):
        c.require(bool(self.originals) and all(isinstance(o, VerifiedOriginalObservation)
            for o in self.originals), "SOURCE_CHANGED")
        objects = [o.as_object() for o in self.originals]
        for selector, value in self.selectors.items():
            c.require(selector in c.SELECTORS and any(o["owner"] == c.SELECTORS[selector][0]
                and (o["objectRef"], o["objectDigest"]) == tuple(value) for o in objects), "SOURCE_CHANGED")
        return objects, deepcopy(self.selectors)


def validate_material_proof_originals(contribution, plan_package):
    """Match requirements to complete originals returned by the trusted port.

    Cost proof semantics belong to the original material Owner. Recomputing
    each original's digest here prevents a pin-only read-set entry from being
    substituted for the original. Runtime keeps its existing V4 validator.
    File-byte attestation pins remain the separate runtime-reader contract.
    """
    c.require(isinstance(contribution, VerifiedOwnerContribution), "SOURCE_CHANGED")
    c.require(all(isinstance(o, VerifiedOriginalObservation) for o in contribution.originals),
              "SOURCE_CHANGED")
    for proof in c.required_read_set_proofs(plan_package):
        matches = [o for o in contribution.originals
                   if (o.owner, o.object_kind, o.object_ref) ==
                   (proof["owner"], proof["objectKind"], proof["objectRef"])]
        c.require(len(matches) == 1, "SOURCE_CHANGED")
        observed = matches[0]
        c.require(type(observed.original) is dict and bool(observed.original), "SOURCE_CHANGED")
        try:
            actual = observed.as_object()
        except (c.DispatchError, KeyError, TypeError) as exc:
            raise c.DispatchError("SOURCE_CHANGED") from exc
        c.require(actual == proof, "SOURCE_CHANGED")
        if proof["objectKind"] == "RuntimeAttestation":
            from services.v4_platform.comfyui import ComfyUIConfigurationError, validate_runtime_attestation
            from services.v4_platform.generation_dispatch_a14b_profile import A14B_PROFILE_SCHEMA
            from services.v4_platform.generation_dispatch_a14b_exact import EXACT_PROFILE_SCHEMA
            from services.v4_platform.comfyui_a14b_runtime import (
                A14B_CAPABILITY_MODE, validate_a14b_runtime_attestation,
            )
            materials = plan_package["materials"]
            a14b = materials["backendProfile"]["schemaVersion"] in {A14B_PROFILE_SCHEMA, EXACT_PROFILE_SCHEMA}
            try:
                facts = (validate_a14b_runtime_attestation(observed.original,
                    backend_profile=materials["backendProfile"],
                    process_identity=materials["processIdentity"],
                    execution_config=materials["executionConfig"])
                    if a14b else validate_runtime_attestation(observed.original))
            except (ComfyUIConfigurationError, ValueError, TypeError, KeyError, AttributeError) as exc:
                raise c.DispatchError("RUNTIME_CHANGED") from exc
            binding = plan_package["plan"]["executionBinding"]
            decision = binding["backendDecision"]
            c.require(observed.digest_field == "payloadDigest"
                      and observed.original["attestationRef"] == proof["objectRef"]
                      and observed.original.get("capabilityMode") ==
                          (A14B_CAPABILITY_MODE if a14b else "IMAGE_TO_VIDEO")
                      and c.canonical(facts["modelFiles"]) ==
                          c.canonical(plan_package["materials"]["backendProfile"]["modelFiles"]),
                      "RUNTIME_CHANGED")
            c.require(all(facts[k] == decision[k]
                          for k in ("providerId", "modelId", "region", "endpointClass"))
                      and facts["vramTotalBytes"] >= max(decision["resourceShape"]["minimumVramPerGpu"],
                                                       decision["resourceShape"]["minimumTotalVram"]),
                      "RUNTIME_CHANGED")


class GenerationDispatchOwnerReaders:
    def __init__(self, *, root_service, method_media, input_assets, coordination,
            technical_target_id, prerequisite_reader, material_reader):
        c.require(isinstance(root_service, EpisodeProductionService)
            and isinstance(method_media, M10M11MethodAwareMediaService)
            and isinstance(input_assets, MethodAwareInputAssetService), "CURRENTNESS_FENCE_UNAVAILABLE")
        c.ref(technical_target_id)
        c.require(method_media.execution_method_planning.run_service is root_service
            and input_assets.planning is method_media, "CURRENTNESS_FENCE_UNAVAILABLE")
        self.root = root_service
        self.media = method_media
        self.inputs = input_assets
        self.coordination = coordination
        self.technical_target_id = technical_target_id
        # Both are independent server-side ports, not fields on the prepare DTO.
        self.prerequisites = prerequisite_reader
        self.materials = material_reader

    def resolve(self, command, lease):
        lease.assert_held()
        c.require(lease.coordinator is self.coordination, "CURRENTNESS_FENCE_UNAVAILABLE")
        try:
            return self._resolve(command, lease)
        except c.DispatchError:
            raise
        except (EpisodeProductionError, ValueError, KeyError, TypeError) as exc:
            raise c.DispatchError("SOURCE_CHANGED") from exc

    def _resolve(self, command, lease):
        root = self.root.verify_run_current(command["workspaceRef"], command["productionRunRef"])
        scope = {k: root[k] for k in c.SCOPE_FIELDS}
        c.scope(scope)
        c.require(scope["workspaceRef"] == lease.workspace_ref, "SCOPE_MISMATCH")
        w, p, s, e, run = (scope[k] for k in
            ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef"))
        context = self.root.project_reader.build_context(w, p, s, e)
        project = self.root.project_reader.get_project(w, p)
        series = self.root.series_reader.get_series(w, s)
        episode = self.root.series_reader.get_episode(w, s, e)
        c.require(context["project"] == project and context["series"] == series
            and context["episode"] == episode, "SOURCE_CHANGED")
        plan_workspace = self.root.planning_reader.get_workspace(w, p, s)
        plan = plan_workspace["plan"]
        c.require(plan["status"] == "confirmed", "SOURCE_CHANGED")
        version = _one(plan_workspace["versions"],
            lambda v: v["seriesPlanVersionRef"] == plan["confirmedSeriesPlanVersionRef"])
        binding = _one(version["episodePlanItemBindings"], lambda b: b["episodeRef"] == e)
        item = _one(version["episodePlanItems"],
            lambda i: i["episodePlanItemRef"] == binding["episodePlanItemRef"])
        m5 = {"seriesPlanRef": plan["seriesPlanRef"],
            "seriesPlanVersionRef": version["seriesPlanVersionRef"],
            "planVersion": plan["version"], "versionNumber": version["versionNumber"],
            "episodeRef": e, "episodePlanItemRef": item["episodePlanItemRef"],
            "binding": binding, "planItem": item}
        c.require(root["seriesPlanVersionRef"] == version["seriesPlanVersionRef"]
            and root["episodePlanItemRef"] == item["episodePlanItemRef"], "SOURCE_CHANGED")
        scripts = self.root.script_reader.get_workspace(w, s, e)
        script = _one(scripts["versions"],
            lambda v: v["scriptVersionRef"] == scripts["script"]["confirmedScriptVersionRef"])
        c.require(script["scriptVersionRef"] == root["scriptVersionRef"], "SOURCE_CHANGED")
        input_plan = self.media.require_current_input_plan(w, p, s, e, run,
            command["methodAwareInputPlanVersionRef"])
        method = _one(input_plan["methodInputPlans"],
            lambda m: m["creativeShotVersionRef"] == command["creativeShotVersionRef"]
                and m["beatRef"] == command["beatRef"])
        c.require(method["inputPlanningState"] == "READY"
            and method["executionClass"] == "MICRO_MOTION"
            and method["executionMethod"] == "SINGLE_ANCHOR_I2V", "SOURCE_CHANGED")
        execution = self.media.execution_method_planning
        execution_plan = execution.require_current_plan(w, p, s, e, run,
            input_plan["executionMethodPlanVersionRef"])
        validation = execution.narrative_validation.require_m8_ready_validation(w, p, s, e, run,
            execution_plan["consistencyValidationVersionRef"])
        c.require(execution_plan["scriptVersionRef"] == script["scriptVersionRef"]
            and execution_plan["scriptVersionDigest"] == c.digest(script)
            and execution_plan["payloadDigest"] == input_plan["executionMethodPlanDigest"]
            and validation["payloadDigest"] == execution_plan["consistencyValidationDigest"], "SOURCE_CHANGED")
        shot = _one(execution_plan["creativeShotVersions"],
            lambda v: v["creativeShotVersionRef"] == command["creativeShotVersionRef"])
        beat = _one(shot["actionExecutionBeats"], lambda b: b["beatRef"] == command["beatRef"])
        requirement = _one(execution_plan["visualExecutionRequirements"],
            lambda v: v["visualExecutionRequirementRef"] == method["visualExecutionRequirementRef"])
        c.require(shot["payloadDigest"] == method["creativeShotVersionDigest"]
            and beat["payloadDigest"] == method["beatDigest"]
            and requirement["payloadDigest"] == method["visualExecutionRequirementDigest"], "SOURCE_CHANGED")
        anchors = [a for r in method["inputRequirements"] for a in r["assetVersionBindings"]]
        c.require(len(anchors) == 1 and anchors[0]["inputRole"] == "ACTION_READY_ANCHOR"
            and anchors[0]["assetVersionRef"] == command["inputAssetVersionRef"], "SOURCE_CHANGED")
        assets = self.media.candidate_review.asset_versions.list_asset_versions(w, run)
        asset = _one(assets, lambda a: a["assetVersionRef"] == command["inputAssetVersionRef"])
        records = self.inputs.evidence.list_records(w, run)
        asset = validate_asset_version(asset, records=records, workspace_ref=w, run_ref=run, root=root)
        c.require(asset["payloadDigest"] == anchors[0]["assetVersionDigest"], "SOURCE_CHANGED")
        receipt = exact_record(records, RECEIPT_KIND, asset["sourceArtifactReceiptRef"],
            asset["sourceArtifactReceiptDigest"], version=None)
        input_authority = validate_receipt_authority(receipt, records)
        c.require(input_authority is not None, "SOURCE_CHANGED")
        # Existing authority verifies read-current input legitimacy, not generation.
        self.inputs._authority_for_receipt(receipt, "METHOD_AWARE_INPUT_PLAN")
        selection = exact_record(records, "HumanSelectionDecision", asset["humanSelectionRef"],
            asset["humanSelectionDigest"], version=None)
        self.inputs._selection_chain(selection, w, run, "METHOD_AWARE_INPUT_PLAN")
        current_m6 = self.root.script_reader.resolve_current_m6_consumer_context(w, p, s, e)
        m6_binding = current_m6["m6ConsumerBinding"]
        c.require(m6_binding["payloadDigest"] == validation["m6ConsumerBindingDigest"]
            and script["m6ConsumerBinding"] == m6_binding, "SOURCE_CHANGED")
        context = execution.resolve_current_video_execution_context(w, p, s, e, run,
            execution_plan["executionMethodPlanVersionRef"], shot["creativeShotVersionRef"], beat["beatRef"])
        subject = {"technicalTargetId": self.technical_target_id,
            "productionRunPayloadDigest": root["payloadDigest"], "manifestDigest": c.digest(root["manifest"]),
            "scriptVersion": {"ref": script["scriptVersionRef"], "digest": c.digest(script)},
            "m6Binding": {k: validation[k] for k in
                ("m6BaselineSnapshotRef", "m6BaselineCanonicalDigest", "activationRevision", "m6ConsumerBindingDigest")},
            "consistencyValidationVersion": {"ref": validation["consistencyValidationVersionRef"], "digest": validation["payloadDigest"]},
            "executionMethodPlanVersion": {"ref": execution_plan["executionMethodPlanVersionRef"], "digest": execution_plan["payloadDigest"]},
            "methodAwareInputPlanVersion": {"ref": input_plan["methodAwareInputPlanVersionRef"], "digest": input_plan["payloadDigest"]},
            "creativeShotVersion": {"ref": shot["creativeShotVersionRef"], "digest": shot["payloadDigest"]},
            "actionExecutionBeat": {"ref": beat["beatRef"], "digest": beat["payloadDigest"]},
            "visualExecutionRequirement": {"ref": requirement["visualExecutionRequirementRef"], "digest": requirement["payloadDigest"]},
            "inputAsset": {"assetRef": asset["assetRef"], "assetVersionRef": asset["assetVersionRef"],
                "assetVersionDigest": asset["payloadDigest"], "inputRole": asset["inputRole"],
                "contentDigest": asset["sha256"], "mediaType": asset["mediaType"],
                "byteSize": asset["byteSize"], "width": asset["probe"]["width"], "height": asset["probe"]["height"]},
            "inputAppendAuthority": {"ref": input_authority["inputAppendAuthorityRef"],
                "digest": input_authority["payloadDigest"], "subjectDigest": input_authority["subjectDigest"]},
            "sourceAction": {"sourceSpan": deepcopy(beat["sourceSpan"]), "sourceTextDigest": beat["sourceTextDigest"]},
            "cameraInstruction": deepcopy(shot["cameraInstruction"]),
            "frameRange": {"startFrameInclusive": beat["frameRangeStartInclusive"], "endFrameExclusive": beat["frameRangeEndExclusive"]},
            "outputConstraints": context["outputConstraints"], "executionClass": "MICRO_MOTION",
            "executionMethod": "SINGLE_ANCHOR_I2V"}
        c.validate_subject(subject)
        objects, selectors = [], {}
        def add(owner, kind, reference, original, digest=None, selector=None):
            value = digest if digest is not None else c.digest(original)
            c.ref(reference); c.sha(value)
            objects.append({"owner": owner, "objectKind": kind, "objectRef": reference, "objectDigest": value})
            if selector:
                selectors[selector] = (reference, value)
        add("V5_PROJECT_CONTEXT", "Project", p, project, selector="CURRENT_PROJECT")
        add("V5_SERIES_EPISODE", "Series", s, series, selector="CURRENT_SERIES")
        add("V5_SERIES_EPISODE", "Episode", e, episode, selector="CURRENT_EPISODE")
        add("V5_SERIES_PLANNING", "SeriesPlan", plan["seriesPlanRef"], plan)
        add("V5_SERIES_PLANNING", "SeriesPlanVersion", version["seriesPlanVersionRef"], version,
            selector="CURRENT_CONFIRMED_SERIES_PLAN")
        add("V5_SERIES_PLANNING", "M5BindingObservation", item["episodePlanItemRef"], m5,
            selector="CURRENT_EPISODE_PLAN_BINDING")
        add("V5_SERIES_PLANNING", "EpisodePlanItem", item["episodePlanItemRef"], item)
        add("V5_SCRIPT", "ScriptVersion", script["scriptVersionRef"], script,
            selector="CURRENT_CONFIRMED_SCRIPT")
        add("V5_M6", "M6BaselineSnapshot", validation["m6BaselineSnapshotRef"], current_m6,
            validation["m6BaselineCanonicalDigest"], "ACTIVE_M6_BINDING")
        add("V5_M6", "M6ConsumerBinding", validation["m6BaselineSnapshotRef"], m6_binding,
            validation["m6ConsumerBindingDigest"])
        add("V5_EPISODE_PRODUCTION", "EpisodeProductionRun", run, root, root["payloadDigest"])
        for value, kind, reference, selector in (
                (validation, "ConsistencyValidationVersion", validation["consistencyValidationVersionRef"], "CURRENT_M7_PASS"),
                (execution_plan, "ExecutionMethodPlanVersion", execution_plan["executionMethodPlanVersionRef"], "CURRENT_METHOD_PLAN"),
                (input_plan, "MethodAwareInputPlanVersion", input_plan["methodAwareInputPlanVersionRef"], "CURRENT_INPUT_PLAN"),
                (shot, "CreativeShotVersion", shot["creativeShotVersionRef"], None),
                (beat, "ActionExecutionBeat", beat["beatRef"], None),
                (requirement, "VisualExecutionRequirement", requirement["visualExecutionRequirementRef"], None)):
            _persisted(value)
            add("V5_EPISODE_PRODUCTION", kind, reference, value, value["payloadDigest"], selector)
        chain = {asset[k] for k in asset if k.endswith("Ref")} | {input_authority["inputAppendAuthorityRef"]}
        for record in records:
            if record["recordRef"] in chain:
                add("V5_EPISODE_PRODUCTION", record["recordKind"], record["recordRef"],
                    record["payload"], record["payloadDigest"])
        lease.assert_held()
        return ResolvedGenerationSubject(scope, subject, context["sourceText"], tuple(objects), selectors,
            {"run": root, "project": project, "series": series, "episode": episode,
                "m5Workspace": plan_workspace, "scriptVersion": script, "m6": current_m6,
                "validation": validation, "executionPlan": execution_plan, "inputPlan": input_plan,
                "asset": asset, "inputAppendAuthority": input_authority})

    def read_current(self, plan_package, approval, phase, lease):
        plan = plan_package["plan"]
        subject = plan["subject"]
        command = {"workspaceRef": plan["scope"]["workspaceRef"],
            "productionRunRef": plan["scope"]["productionRunRef"],
            "methodAwareInputPlanVersionRef": subject["methodAwareInputPlanVersion"]["ref"],
            "creativeShotVersionRef": subject["creativeShotVersion"]["ref"],
            "beatRef": subject["actionExecutionBeat"]["ref"],
            "inputAssetVersionRef": subject["inputAsset"]["assetVersionRef"]}
        resolved = self.resolve(command, lease)
        c.require(c.canonical(resolved.subject) == c.canonical(subject)
            and resolved.scope == plan["scope"], "SOURCE_CHANGED")
        return self.build_read_set(resolved, plan_package, approval, phase, lease)

    def build_read_set(self, resolved, package, approval, phase, lease):
        c.require(self.prerequisites is not None and self.materials is not None,
            "CURRENTNESS_FENCE_UNAVAILABLE")
        # Ports must validate their own original schemas/approval semantics and
        # supply originals; none of these observations comes from the command.
        extra = self.prerequisites.read_current(resolved, package, approval, phase, lease)
        materials = self.materials.read_current(resolved, package, approval, phase, lease)
        validate_material_proof_originals(materials, package)
        objects = list(deepcopy(resolved.objects))
        selectors = deepcopy(resolved.selectors)
        for observation in (extra, materials):
            c.require(isinstance(observation, VerifiedOwnerContribution), "SOURCE_CHANGED")
            observed_objects, observed_selectors = observation.read()
            objects.extend(observed_objects)
            c.require(not (set(selectors) & set(observed_selectors)), "SOURCE_CHANGED")
            selectors.update(observed_selectors)
        rows = []
        for kind, (reference, digest) in selectors.items():
            c.require(kind in c.SELECTORS, "CURRENTNESS_FENCE_UNAVAILABLE")
            owner, scope_key = c.SELECTORS[kind]
            rows.append({"owner": owner, "selectorKind": kind, "scopeRef": resolved.scope[scope_key],
                "selectedRef": reference, "selectedDigest": digest,
                "coordinationRevision": self.coordination.revision(lease, owner, kind, resolved.scope[scope_key])})
        read_set = {"schemaVersion": c.PREFIX + "read-set.v1", "scope": deepcopy(resolved.scope),
            "phase": phase, "coordinationEpoch": lease.epoch,
            "objects": sorted(objects, key=lambda o: (o["owner"], o["objectKind"], o["objectRef"])),
            "selectors": sorted(rows, key=lambda row: (row["owner"], row["selectorKind"], row["scopeRef"]))}
        c.validate_read_set(read_set, expected_scope=resolved.scope, phase=phase)
        c.validate_read_set_bindings(read_set, package["plan"], approval)
        c.validate_read_set_proof_bindings(read_set, package)
        return deepcopy(read_set)
