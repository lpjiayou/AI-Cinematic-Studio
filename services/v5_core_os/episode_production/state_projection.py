"""One explicit projection over K2 root, production, runtime and visual-QC state."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping

from .evidence import EpisodeProductionEvidenceRepository, EvidenceSnapshot
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
        activation_reader: Any | None = None,
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.candidate_review = candidate_review
        self.runtime_reader = runtime_reader
        self.activation_reader = activation_reader

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

    @classmethod
    def _active_candidates(
        cls,
        candidate_projection: Mapping[str, Any],
        active_revision: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        all_candidates = candidate_projection.get("candidates", [])
        candidate_refs = active_revision.get("candidateRefs")
        if isinstance(candidate_refs, list):
            expected = set(candidate_refs)
            return [
                deepcopy(dict(item))
                for item in all_candidates
                if isinstance(item, Mapping)
                and item.get("candidateRef") in expected
            ]
        revision_ref = active_revision.get("revisionRef")
        return [
            deepcopy(dict(item))
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

    def _active_revision(
        self,
        candidate_projection: Mapping[str, Any],
        gates: list[dict[str, Any]],
        production_state: str,
        video_activation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if production_state in {
                "REAL_VIDEO_PLAN_READY",
                "REAL_VIDEO_READY",
                "REAL_PREVIEW_READY",
                "REAL_QC_READY",
                "APPROVAL_READY",
                "MASTER_READY",
        }:
            media_kind = "VIDEO"
        elif production_state in {"REAL_IMAGE_PLAN_READY", "REAL_IMAGE_READY"}:
            media_kind = "IMAGE"
        else:
            latest_by_kind = candidate_projection.get(
                "latestCandidateRevisionRefs", {}
            )
            media_kind = (
                "VIDEO"
                if isinstance(latest_by_kind, Mapping)
                and isinstance(latest_by_kind.get("VIDEO"), str)
                else "IMAGE"
            )
        latest_plan_revision: str | None = None
        latest_plan_kind: str | None = None
        latest_plan_expected_count: int | None = None
        activation_manifest_ref: str | None = None
        activation_manifest_digest: str | None = None
        activation_revision_ref: str | None = None
        activation_lineage_current = False
        activation_candidate_identities: set[tuple[Any, Any]] = set()
        for gate in reversed(gates):
            facts = gate.get("facts", [])
            if not isinstance(facts, list):
                continue
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
                            latest_plan_kind = (
                                "VIDEO" if expected_kind == "RealVideoPlan" else "IMAGE"
                            )
                            expected = fact["payload"].get("expectedRequestCount")
                            if (
                                isinstance(expected, int)
                                and not isinstance(expected, bool)
                                and expected > 0
                            ):
                                latest_plan_expected_count = expected
                            break
                if latest_plan_revision is not None:
                    break
            if latest_plan_revision is not None:
                break
        if media_kind == "VIDEO" and isinstance(video_activation, Mapping):
            activation_manifest_ref = video_activation.get("manifestRef")
            activation_manifest_digest = video_activation.get("manifestDigest")
            activation_revision_ref = video_activation.get("revisionRef")
            activation_lineage_current = (
                video_activation.get("lineageCurrent") is True
            )
            identities = video_activation.get("candidateIdentities")
            if isinstance(identities, list):
                activation_candidate_identities = {
                    (item.get("candidateRef"), item.get("candidateDigest"))
                    for item in identities
                    if isinstance(item, Mapping)
                }

        current_candidates = []
        for item in candidate_projection.get("candidates", []):
            payload = item.get("candidate") if isinstance(item, Mapping) else None
            if (
                isinstance(item, Mapping)
                and (
                    not isinstance(payload, Mapping)
                    or payload.get("mediaKind") == media_kind
                )
                and item.get("applicabilityState", "CURRENT") == "CURRENT"
            ):
                current_candidates.append(item)
        latest_refs = candidate_projection.get("latestCandidateRevisionRefs", {})
        candidate_revision = (
            latest_refs.get(media_kind) if isinstance(latest_refs, Mapping) else None
        )
        if candidate_revision is None:
            candidate_revision = candidate_projection.get(
                "latestCandidateRevisionRef"
            )
        if isinstance(candidate_revision, str) and candidate_revision:
            revision_carriers = [
                item.get("candidate")
                for item in current_candidates
                if isinstance(item.get("candidate"), Mapping)
                and item.get("revisionRef") == candidate_revision
                and isinstance(
                    item["candidate"].get("consumedRealVideoRevision"), Mapping
                )
            ]
            if revision_carriers:
                revision_payload = revision_carriers[-1][
                    "consumedRealVideoRevision"
                ]
                allowed_digests = set(
                    revision_payload.get("generationRequestDigests", [])
                )
                current_candidates = [
                    item
                    for item in current_candidates
                    if isinstance(item.get("candidate"), Mapping)
                    and item["candidate"].get("sourceRequestDigest")
                    in allowed_digests
                ]
            else:
                current_candidates = [
                    item
                    for item in current_candidates
                    if (
                        item.get("revisionRef")
                        or (
                            item.get("candidate", {}).get("revisionRef")
                            if isinstance(item.get("candidate"), Mapping)
                            else None
                        )
                    )
                    == candidate_revision
                ]
        by_slot: dict[str, Mapping[str, Any]] = {}
        for item in current_candidates:
            payload = item.get("candidate")
            slot_ref = (
                payload.get("slotRef")
                if isinstance(payload, Mapping)
                else item.get("candidateRef")
            )
            if not isinstance(slot_ref, str) or slot_ref in by_slot:
                return {
                    "state": "BLOCKED_AMBIGUOUS",
                    "revisionRef": None,
                    "mediaKind": media_kind,
                    "candidateRefs": [],
                    "activationManifestRef": activation_manifest_ref,
                    "activationManifestDigest": activation_manifest_digest,
                    "authority": "V5_CANONICAL_APPEND_ONLY",
                }
            by_slot[slot_ref] = item
        revision_ref = (
            candidate_revision
            if isinstance(candidate_revision, str) and candidate_revision
            else (
                latest_plan_revision
                if latest_plan_kind == media_kind
                else None
            )
        )
        if revision_ref is not None:
            activation_state = (
                "CURRENT"
                if activation_lineage_current
                and activation_revision_ref == revision_ref
                and (
                    len(by_slot) == latest_plan_expected_count
                    if latest_plan_expected_count is not None
                    else bool(by_slot)
                )
                and (
                    not activation_candidate_identities
                    or activation_candidate_identities
                    == {
                        (
                            item.get("candidateRef"),
                            item.get("candidate", {}).get("payloadDigest")
                            if isinstance(item.get("candidate"), Mapping)
                            else None,
                        )
                        for item in by_slot.values()
                    }
                )
                else "STALE"
            )
            return {
                "state": (
                    "STALE_BLOCKED"
                    if activation_manifest_ref is not None
                    and activation_state != "CURRENT"
                    else "ACTIVE"
                ),
                "revisionRef": revision_ref,
                "mediaKind": media_kind,
                "candidateRefs": [
                    item["candidateRef"]
                    for _, item in sorted(by_slot.items())
                ],
                "activationState": activation_state,
                "activationManifestRef": activation_manifest_ref,
                "activationManifestDigest": activation_manifest_digest,
                "activationRevisionRef": activation_revision_ref,
                "authority": "V5_CANONICAL_APPEND_ONLY",
                "lineageSource": (
                    "ADMISSION_MANIFEST"
                    if activation_state == "CURRENT"
                    else (
                        "CANDIDATE_JOURNAL"
                        if candidate_revision is not None
                        else "PRODUCTION_PLAN"
                    )
                ),
            }
        return {
            "state": "NOT_RECORDED",
            "revisionRef": None,
            "mediaKind": media_kind,
            "candidateRefs": [],
            "activationManifestRef": activation_manifest_ref,
            "activationManifestDigest": activation_manifest_digest,
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
                if (
                    fact_revision_ref == revision_ref
                    or (
                        active_revision.get("mediaKind") == "VIDEO"
                        and fact.get("factKind") == "RealVideoPlan"
                    )
                    or (
                        active_revision.get("mediaKind") == "IMAGE"
                        and fact.get("factKind") == "RealImagePlan"
                    )
                ) and (
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
        candidates = K2ProductionStateProjectionService._active_candidates(
            candidate_projection, active_revision
        )
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
        if active_revision.get("state") == "STALE_BLOCKED":
            state = "STALE_BLOCKED"
        elif any(
            item.get("visualQcState") == "STALE"
            for item in candidates
            if isinstance(item, Mapping)
        ):
            state = "STALE"
        elif (
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
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        evidence_snapshot: EvidenceSnapshot | None = None,
    ) -> dict[str, Any]:
        root = deepcopy(
            dict(self.root_service.get_run(workspace_ref, production_run_ref))
        )
        snapshot = evidence_snapshot or self.evidence.read_snapshot(
            workspace_ref, production_run_ref
        )
        if (
            snapshot.workspaceRef != workspace_ref
            or snapshot.productionRunRef != production_run_ref
        ):
            raise RepositoryUnavailableError("evidence snapshot scope is invalid")
        gates = [deepcopy(dict(item)) for item in snapshot.gates]
        production_state = snapshot.currentState
        candidates = self.candidate_review.get_projection(
            workspace_ref,
            production_run_ref,
            records=snapshot.records,
            gates=snapshot.gates,
        )
        video_activation = None
        if self.activation_reader is not None and hasattr(
            self.activation_reader, "get_video_activation_projection"
        ):
            video_activation = self.activation_reader.get_video_activation_projection(
                workspace_ref,
                production_run_ref,
                records=snapshot.records,
                gates=snapshot.gates,
            )
        active_revision = self._active_revision(
            candidates, gates, production_state, video_activation
        )
        all_candidates = candidates.get("candidates", [])
        active_revision_ref = active_revision.get("revisionRef")
        active_candidates = self._active_candidates(candidates, active_revision)
        active_lifecycle = deepcopy(dict(candidates))
        active_lifecycle["candidates"] = active_candidates
        active_lifecycle["activeRevisionRef"] = active_revision_ref
        active_lifecycle["historicalCandidateCount"] = (
            len(all_candidates) - len(active_candidates)
        )
        latest = gates[-1] if gates else None
        runtime = self._runtime(workspace_ref, production_run_ref)
        runtime["observedSeparatelyFromEvidenceRevision"] = True
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
            "runtimeState": runtime,
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
            "evidenceRevisionToken": snapshot.revisionToken,
            "publicationAllowed": False,
        }


__all__ = ["K2ProductionStateProjectionService"]
