"""Independently verified V4 → V5 handoff for real M11 video candidates."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .media_jobs import (
    M11_VIDEO_PROVENANCE,
    MediaJobRepository,
    verify_media_against_request,
)


class RealVideoCandidateEvidenceError(RuntimeError):
    code = "real_video_candidate_evidence_rejected"


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class MediaJobRealVideoCandidateEvidence:
    """Projects only re-probed, digest-exact M11 SUCCEEDED jobs."""

    def __init__(
        self, repository: MediaJobRepository, artifact_root: Path | str
    ) -> None:
        self.repository = repository
        self.artifact_root = Path(artifact_root).resolve()

    def _artifact(
        self, job: Mapping[str, Any], request: Mapping[str, Any]
    ) -> dict[str, Any]:
        artifact = job.get("artifact")
        if not isinstance(artifact, Mapping):
            raise RealVideoCandidateEvidenceError("M11 artifact metadata is missing")
        try:
            path = Path(str(artifact["internalPath"])).resolve()
        except (KeyError, TypeError, ValueError) as exc:
            raise RealVideoCandidateEvidenceError("M11 artifact path is invalid") from exc
        if self.artifact_root not in path.parents or not path.is_file() or path.is_symlink():
            raise RealVideoCandidateEvidenceError("M11 artifact escaped storage")
        content = path.read_bytes()
        content_digest = sha256(content).hexdigest()
        try:
            storage_key = str(path.relative_to(self.artifact_root))
        except ValueError as exc:
            raise RealVideoCandidateEvidenceError("M11 storage key is invalid") from exc
        if (
            artifact.get("workspaceRef") != request.get("workspaceRef")
            or artifact.get("productionRunRef") != request.get("productionRunRef")
            or artifact.get("jobRef") != job.get("jobRef")
            or artifact.get("generationRequestRef")
            != request.get("generationRequestRef")
            or artifact.get("generationRequestDigest") != request.get("payloadDigest")
            or artifact.get("mediaKind") != "video"
            or artifact.get("mediaType") != "video/mp4"
            or artifact.get("storageKey") != storage_key
            or artifact.get("byteSize") != len(content)
            or artifact.get("sha256") != content_digest
            or artifact.get("provenance") != M11_VIDEO_PROVENANCE
            or artifact.get("gpuUsed") is not True
            or artifact.get("publicationAllowed") is not False
        ):
            raise RealVideoCandidateEvidenceError("M11 artifact lineage is invalid")
        probe = verify_media_against_request(path, request)
        if probe != artifact.get("probe"):
            raise RealVideoCandidateEvidenceError("M11 artifact probe changed")
        provider_execution = artifact.get("providerExecution")
        if not isinstance(provider_execution, Mapping):
            raise RealVideoCandidateEvidenceError("M11 execution evidence is missing")
        return {
            "artifactRef": f"v4-media-artifact:{content_digest[:32]}",
            "artifactDigest": content_digest,
            "artifactByteSize": len(content),
            "storageKey": storage_key,
            "storageKeyDigest": sha256(storage_key.encode("utf-8")).hexdigest(),
            "probe": deepcopy(probe),
            "executionEvidenceDigest": _digest(dict(provider_execution)),
        }

    def resolve_candidates(
        self,
        workspace_ref: str,
        production_run_ref: str,
        real_video_plan_ref: str,
        expected_requests: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if (
            not isinstance(real_video_plan_ref, str)
            or not real_video_plan_ref
            or real_video_plan_ref != real_video_plan_ref.strip()
        ):
            raise RealVideoCandidateEvidenceError("M11 plan ref is invalid")
        jobs = self.repository.list(workspace_ref, production_run_ref)
        candidates: list[dict[str, Any]] = []
        for request in expected_requests:
            matches = [
                item
                for item in jobs
                if item.get("state") == "SUCCEEDED"
                and item.get("requestDigest") == request.get("payloadDigest")
                and isinstance(item.get("request"), Mapping)
                and item["request"].get("generationRequestRef")
                == request.get("generationRequestRef")
            ]
            if len(matches) != 1:
                raise RealVideoCandidateEvidenceError(
                    "M11 request does not have one exact SUCCEEDED job"
                )
            job = matches[0]
            if job.get("request") != request:
                raise RealVideoCandidateEvidenceError("M11 job request changed")
            verified = self._artifact(job, request)
            candidate_seed = {
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestDigest": request["payloadDigest"],
                "artifactDigest": verified["artifactDigest"],
            }
            candidate_ref = f"m11-video-candidate-{_digest(candidate_seed)[:32]}"
            candidates.append(
                {
                    "candidateRef": candidate_ref,
                    "candidateVersion": 1,
                    "ordinal": request["ordinal"],
                    "slotRef": request["creativeShotVersionRef"],
                    "sourceRequestRef": request["generationRequestRef"],
                    "sourceRequestDigest": request["payloadDigest"],
                    **verified,
                    "provenance": M11_VIDEO_PROVENANCE,
                    "technicalChecks": [
                        {"check": "request-digest", "passed": True},
                        {"check": "artifact-sha256", "passed": True},
                        {"check": "media-probe", "passed": True},
                        {"check": "m11-execution-evidence", "passed": True},
                    ],
                }
            )
        candidates.sort(key=lambda item: item["ordinal"])
        if [item["ordinal"] for item in candidates] != [1, 2, 3, 4]:
            raise RealVideoCandidateEvidenceError("M11 candidate coverage is incomplete")
        handoff = {
            "schemaVersion": "v4.k2-real-video-candidate-handoff.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "realVideoPlanRef": real_video_plan_ref,
            "candidateCount": len(candidates),
            "candidateDigests": [
                _digest({key: value for key, value in item.items()})
                for item in candidates
            ],
        }
        handoff["payloadDigest"] = _digest(handoff)
        return {"handoff": handoff, "candidates": candidates}


__all__ = [
    "MediaJobRealVideoCandidateEvidence",
    "RealVideoCandidateEvidenceError",
]
