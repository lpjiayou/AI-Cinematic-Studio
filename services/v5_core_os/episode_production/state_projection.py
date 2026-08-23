"""One explicit projection over K2 root, production, runtime and visual-QC state."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping

from .evidence import EpisodeProductionEvidenceRepository
from .foundation import RepositoryUnavailableError
from .media_candidate_review import K2MediaCandidateReviewService


class K2ProductionStateProjectionService:
    """Projects four state axes without allowing one store to impersonate another."""

    def __init__(
        self,
        root_service: Any,
        evidence: EpisodeProductionEvidenceRepository,
        candidate_review: K2MediaCandidateReviewService,
        runtime_reader: Any | None = None,
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.candidate_review = candidate_review
        self.runtime_reader = runtime_reader

    def _runtime(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        if self.runtime_reader is None or not hasattr(self.runtime_reader, "list_jobs"):
            return {
                "state": "UNAVAILABLE",
                "authority": "V4_RUNTIME_NON_CANONICAL",
                "counts": {},
                "jobCount": 0,
            }
        try:
            jobs = self.runtime_reader.list_jobs(workspace_ref, run_ref)
        except Exception as exc:
            raise RepositoryUnavailableError("runtime state projection failed") from exc
        if not isinstance(jobs, list) or not all(isinstance(item, Mapping) for item in jobs):
            raise RepositoryUnavailableError("runtime state projection is invalid")
        counts = Counter(str(item.get("state", "UNKNOWN")) for item in jobs)
        if not jobs:
            state = "IDLE"
        elif counts.get("RUNNING") or counts.get("LEASED") or counts.get("QUEUED"):
            state = "ACTIVE"
        elif counts.get("FAILED") or counts.get("CANCELLED"):
            state = "ATTENTION_REQUIRED"
        elif counts.get("SUCCEEDED") == len(jobs):
            state = "SUCCEEDED"
        else:
            state = "MIXED"
        return {
            "state": state,
            "authority": "V4_RUNTIME_NON_CANONICAL",
            "counts": dict(sorted(counts.items())),
            "jobCount": len(jobs),
        }

    def _active_revision(
        self,
        candidate_projection: Mapping[str, Any],
        gates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        latest_plan_revision: str | None = None
        latest_admitted_revision: str | None = None
        for gate in reversed(gates):
            facts = gate.get("facts", [])
            if not isinstance(facts, list):
                continue
            if latest_admitted_revision is None:
                for fact in facts:
                    if (
                        isinstance(fact, Mapping)
                        and fact.get("factKind")
                        in {
                            "RealImageAdmissionManifest",
                            "RealVideoAdmissionManifest",
                        }
                        and isinstance(fact.get("payload"), Mapping)
                    ):
                        value = fact["payload"].get("revisionRef")
                        if isinstance(value, str) and value:
                            latest_admitted_revision = value
                            break
            for expected_kind, field in (
                ("RealVideoPlan", "realVideoPlanRef"),
                ("RealImagePlan", "realImagePlanRef"),
            ):
                for fact in facts:
                    if (
                        isinstance(fact, Mapping)
                        and fact.get("factKind") == expected_kind
                        and isinstance(fact.get("payload"), Mapping)
                    ):
                        value = fact["payload"].get(field)
                        if isinstance(value, str) and value:
                            latest_plan_revision = value
                            break
                if latest_plan_revision is not None:
                    break
            if latest_plan_revision is not None:
                break

        # A Candidate append is the canonical declaration that a planned or
        # successor revision has entered review.  Prefer the journal's explicit
        # latest lineage over a plan: successor revisions intentionally need not
        # manufacture another one-time production gate.  Older projections do not
        # expose this field, so their existing plan fact remains the compatibility
        # fallback.
        latest_candidate_revision = candidate_projection.get(
            "latestCandidateRevisionRef"
        )
        if latest_candidate_revision is not None:
            if (
                not isinstance(latest_candidate_revision, str)
                or not latest_candidate_revision
                or latest_candidate_revision != latest_candidate_revision.strip()
            ):
                raise RepositoryUnavailableError(
                    "candidate revision projection is invalid"
                )
            latest_candidates = [
                item
                for item in candidate_projection.get("candidates", [])
                if isinstance(item, Mapping)
                and item.get("revisionRef") == latest_candidate_revision
            ]
            # A later production plan supersedes the review focus of a fully
            # admitted predecessor revision.  An unadmitted successor Candidate
            # still becomes active without manufacturing another one-time gate.
            if (
                latest_plan_revision is not None
                and latest_plan_revision != latest_candidate_revision
                and latest_candidates
                and all(
                    item.get("admissionState") == "ADMITTED"
                    for item in latest_candidates
                )
            ):
                if latest_admitted_revision == latest_candidate_revision:
                    return {
                        "state": "ACTIVE",
                        "revisionRef": latest_candidate_revision,
                        "authority": "V5_CANONICAL_APPEND_ONLY",
                        "lineageSource": "ADMISSION_MANIFEST",
                    }
                return {
                    "state": "ACTIVE",
                    "revisionRef": latest_plan_revision,
                    "authority": "V5_CANONICAL_APPEND_ONLY",
                    "lineageSource": "PRODUCTION_PLAN_AFTER_ADMISSION",
                }
            return {
                "state": "ACTIVE",
                "revisionRef": latest_candidate_revision,
                "authority": "V5_CANONICAL_APPEND_ONLY",
                "lineageSource": "CANDIDATE_JOURNAL",
            }

        # There is deliberately no ActiveRevision fact lookup here: no accepted
        # writer owns such a fact.  A current canonical plan is the safe fallback
        # until the first Candidate for a successor lineage is appended.
        if latest_plan_revision is not None:
            return {
                "state": "ACTIVE",
                "revisionRef": latest_plan_revision,
                "authority": "V5_CANONICAL_APPEND_ONLY",
                "lineageSource": "PRODUCTION_PLAN",
            }
        candidates = candidate_projection.get("candidates", [])
        revision_refs = {
            candidate.get("revisionRef")
            or (
                candidate.get("candidate", {}).get("revisionRef")
                if isinstance(candidate.get("candidate"), Mapping)
                else None
            )
            for candidate in candidates
            if isinstance(candidate, Mapping)
        }
        revision_refs.discard(None)
        if len(revision_refs) > 1:
            return {
                "state": "BLOCKED_AMBIGUOUS",
                "revisionRef": None,
                "candidateRevisionRefs": sorted(revision_refs),
                "authority": "V5_CANONICAL_APPEND_ONLY",
            }
        if len(revision_refs) == 1:
            return {
                "state": "ACTIVE",
                "revisionRef": next(iter(revision_refs)),
                "authority": "V5_CANONICAL_APPEND_ONLY",
                "lineageSource": "CANDIDATE_JOURNAL_COMPATIBILITY",
            }
        return {
            "state": "NOT_RECORDED",
            "revisionRef": None,
            "authority": "V5_CANONICAL_APPEND_ONLY",
        }

    @staticmethod
    def _expected_candidate_count(
        gates: list[dict[str, Any]], active_revision: Mapping[str, Any]
    ) -> int | None:
        revision_ref = active_revision.get("revisionRef")
        if not isinstance(revision_ref, str):
            return None
        for gate in reversed(gates):
            facts = gate.get("facts", [])
            if not isinstance(facts, list):
                continue
            for fact in facts:
                if not isinstance(fact, Mapping) or not isinstance(
                    fact.get("payload"), Mapping
                ):
                    continue
                payload = fact["payload"]
                if fact.get("factKind") == "RealVideoPlan":
                    fact_revision_ref = payload.get("realVideoPlanRef")
                elif fact.get("factKind") == "RealImagePlan":
                    fact_revision_ref = payload.get("realImagePlanRef")
                else:
                    continue
                expected = payload.get("expectedRequestCount")
                if fact_revision_ref == revision_ref and (
                    isinstance(expected, int)
                    and not isinstance(expected, bool)
                    and expected > 0
                ):
                    return expected
        return None

    @staticmethod
    def _visual(
        candidate_projection: Mapping[str, Any],
        active_revision: Mapping[str, Any],
        gates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if active_revision.get("state") == "BLOCKED_AMBIGUOUS":
            return {
                "state": "BLOCKED_AMBIGUOUS",
                "authority": "V5_CANONICAL_APPEND_ONLY",
                "activeRevisionRef": None,
                "candidateCount": 0,
                "decisionCount": 0,
                "decisions": [],
            }
        revision_ref = active_revision.get("revisionRef")
        all_candidates = candidate_projection.get("candidates", [])
        candidates = [
            item
            for item in all_candidates
            if isinstance(item, Mapping)
            and (
                item.get("revisionRef")
                or (
                    item.get("candidate", {}).get("revisionRef")
                    if isinstance(item.get("candidate"), Mapping)
                    else None
                )
            )
            == revision_ref
        ]
        decisions = [
            item["semanticVisualQc"]
            for item in candidates
            if isinstance(item, Mapping)
            and isinstance(item.get("semanticVisualQc"), Mapping)
        ]
        expected_candidate_count = (
            K2ProductionStateProjectionService._expected_candidate_count(
                gates, active_revision
            )
        )
        if (
            expected_candidate_count is not None
            and len(candidates) > expected_candidate_count
        ):
            state = "BLOCKED_AMBIGUOUS"
        elif not candidates or not decisions:
            state = "NOT_RECORDED"
        elif any(item.get("result") == "FAIL" for item in decisions):
            state = "FAIL"
        elif (
            expected_candidate_count is not None
            and len(candidates) < expected_candidate_count
        ):
            state = "IN_PROGRESS"
        elif len(decisions) == len(candidates) and all(
            item.get("result") == "PASS" for item in decisions
        ):
            state = "PASS"
        else:
            state = "IN_PROGRESS"
        return {
            "state": state,
            "authority": "V5_CANONICAL_APPEND_ONLY",
            "activeRevisionRef": revision_ref,
            "candidateCount": len(candidates),
            "expectedCandidateCount": expected_candidate_count,
            "decisionCount": len(decisions),
            "decisions": [
                {
                    "visualQcRef": item.get("visualQcRef"),
                    "visualQcVersion": item.get("visualQcVersion"),
                    "candidateRef": item.get("candidateRef"),
                    "result": item.get("result"),
                    "payloadDigest": item.get("payloadDigest"),
                }
                for item in decisions
            ],
        }

    def get_projection(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        root = deepcopy(
            dict(self.root_service.get_run(workspace_ref, production_run_ref))
        )
        gates = self.evidence.list_gates(workspace_ref, production_run_ref)
        production_state = self.evidence.current_state(
            workspace_ref, production_run_ref
        )
        candidates = self.candidate_review.get_projection(
            workspace_ref, production_run_ref
        )
        active_revision = self._active_revision(candidates, gates)
        active_revision_ref = active_revision.get("revisionRef")
        all_candidates = candidates.get("candidates", [])
        active_candidates = [
            deepcopy(item)
            for item in all_candidates
            if isinstance(item, Mapping)
            and (
                item.get("revisionRef")
                or (
                    item.get("candidate", {}).get("revisionRef")
                    if isinstance(item.get("candidate"), Mapping)
                    else None
                )
            )
            == active_revision_ref
        ]
        active_lifecycle = deepcopy(dict(candidates))
        active_lifecycle["candidates"] = active_candidates
        active_lifecycle["activeRevisionRef"] = active_revision_ref
        active_lifecycle["historicalCandidateCount"] = (
            len(all_candidates) - len(active_candidates)
        )
        latest = gates[-1] if gates else None
        return {
            "schemaVersion": "v5.k2-production-state-projection.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            # Compatibility alias.  New callers should read productionProjection.state.
            "state": production_state,
            "productionState": production_state,
            "rootState": {
                "state": root.get("state", "ROOTS_READY"),
                "authority": "V5_ROOT_DATABASE",
                "payloadDigest": root.get("payloadDigest"),
                "version": root.get("version"),
                "mutable": False,
            },
            "productionProjection": {
                "state": production_state,
                "authority": "V5_EVIDENCE_TRANSITIONS",
                "completedGates": [item["gateName"] for item in gates],
                "latestGateName": None if latest is None else latest["gateName"],
                "latestGateDigest": None if latest is None else latest["requestDigest"],
            },
            "runtimeState": self._runtime(workspace_ref, production_run_ref),
            "visualQcState": self._visual(candidates, active_revision, gates),
            "activeRevision": active_revision,
            "candidates": active_candidates,
            "candidateLifecycle": active_lifecycle,
            "invariants": {
                "runtimeDoesNotAdvanceProduction": True,
                "visualQcDoesNotAdvanceProduction": True,
                "assetVersionAuthority": "V5_CANONICAL_EVIDENCE_ONLY",
                "publicationAllowed": False,
            },
            "publicationAllowed": False,
        }


__all__ = ["K2ProductionStateProjectionService"]
