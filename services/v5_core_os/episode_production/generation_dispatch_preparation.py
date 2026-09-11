"""Read-only preparation of the Accepted exact plan, before independent approval."""
from __future__ import annotations

from copy import deepcopy

from services.v4_platform.generation_dispatch_compiler import compile_generation_dispatch_workflow
from . import generation_dispatch_contracts as c
from .generation_dispatch_foundation import BackendObservation, RuntimeObservation


class GenerationDispatchPreparation:
    def __init__(self, *, source_reader=None, repository=None, coordination=None):
        self.source = source_reader
        self.repository = repository
        self.coordination = coordination

    def prepare(self, command):
        command = c.validate_command("PREPARE", command)
        c.require(all(p is not None for p in (self.source, self.repository, self.coordination)),
            "CURRENTNESS_FENCE_UNAVAILABLE")
        with self.coordination.critical_section(command["workspaceRef"]) as lease:
            resolved = self.source.resolve(command, lease)
            c.require(self.source.materials is not None and self.source.prerequisites is not None,
                "CURRENTNESS_FENCE_UNAVAILABLE")
            observations = self.source.materials.prepare(resolved, command, lease)
            c.require(type(observations) is dict and set(observations) == {"backend", "runtime", "costBasis"},
                "CURRENTNESS_FENCE_UNAVAILABLE")
            backend, runtime = observations["backend"], observations["runtime"]
            c.require(isinstance(backend, BackendObservation) and isinstance(runtime, RuntimeObservation),
                "CURRENTNESS_FENCE_UNAVAILABLE")
            config = c.validate_execution_config(backend.execution_config)
            process = c.validate_process(runtime.process_identity)
            cost = c.validate_cost(observations["costBasis"])
            c.require(config["configRef"] == command["executionConfigRef"]
                and config["backendRef"] == command["backendRef"]
                and backend.decision["backendRef"] == command["backendRef"], "CONFIG_CHANGED")
            c.require(cost["costBasisRef"] == command["costBasisRef"], "COST_BOUND_UNVERIFIED")
            prerequisites = self.source.prerequisites.prepare(resolved, command, lease)
            c.exact(prerequisites, c.PREREQUISITES)
            for item in prerequisites.values():
                c.pinned(item)
            # The request identity does not depend on workflow/approval/Grant.
            binding = {"backendDecision": deepcopy(backend.decision),
                "backendDecisionDigest": c.digest(backend.decision),
                "executionProfile": {"ref": backend.decision["backendProfileRef"],
                    "digest": backend.decision["backendProfileDigest"]},
                "executionConfigDigest": c.digest(config), "executionCode": deepcopy(backend.execution_code),
                "runtimeBinding": {"instanceRef": process["instanceRef"],
                    "processIdentityDigest": c.digest(process), "attestationFileSha256": runtime.attestation_file_sha256},
                "costBasis": {"ref": cost["costBasisRef"], "digest": cost["payloadDigest"]},
                "prerequisiteEvidenceDigest": c.digest(prerequisites)}
            plan = {"scope": deepcopy(resolved.scope), "subject": deepcopy(resolved.subject),
                "executionBinding": binding, "permissions": deepcopy(c.PERMISSIONS),
                "limits": deepcopy(command["limits"])}
            request_ref = "generation-request-" + c.digest(c.request_identity(plan))
            workflow = compile_generation_dispatch_workflow(generation_request_ref=request_ref,
                source_text=resolved.source_text, camera_instruction=resolved.subject["cameraInstruction"],
                source_asset={k: v for k, v in resolved.subject["inputAsset"].items() if k != "inputRole"},
                backend_profile=backend.profile, output_constraints=resolved.subject["outputConstraints"])
            binding["workflowDigest"] = c.digest(workflow)
            package = {"plan": plan, "materials": {"backendProfile": deepcopy(backend.profile),
                "executionConfig": config, "processIdentity": process, "workflow": workflow,
                "costBasis": cost, "prerequisiteEvidence": deepcopy(prerequisites)}}
            c.validate_plan_package(package)
            read_set = self.source.build_read_set(resolved, package, None, "PREPARE", lease)
            w, r = resolved.scope["workspaceRef"], resolved.scope["productionRunRef"]
            tokens = {"recordJournalHead": self.repository.record_journal_head(w, r),
                "workspaceRecordJournalHead": self.repository.workspace_record_journal_head(w),
                "evidenceRevisionToken": self.repository.read_snapshot(w, r).revisionToken}
            c.tokens(tokens)
            lease.assert_held()
            return {"schemaVersion": c.PREFIX + "prepare-result.v1", "operation": "PREPARE_ONLY",
                "planPackage": deepcopy(package), "subjectDigest": c.subject_digest(plan),
                "approvedPlanDigest": c.digest(plan), "currentSubjectReadSet": read_set,
                "snapshotTokens": tokens, "sendPermission": "NONE"}
