"""Pinned local evidence adapter for already executed K2 M10 image candidates.

The adapter is a V4 boundary: it owns private artifact/input paths and returns a
sanitized, independently reverified handoff to V5.  It never selects or admits
media and it cannot publish.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence
import zlib


REAL_IMAGE_EVIDENCE_ADAPTER_ID = "v4.comfyui.pinned-image-evidence.v1"
REAL_IMAGE_EVIDENCE_SCHEMA = (
    "v5.k2-m10-four-image-local-evidence-candidates.v1"
)


class RealImageCandidateEvidenceError(RuntimeError):
    """The configured evidence or its private artifacts are not trustworthy."""


class RealImageCandidateEvidenceConfigurationError(
    RealImageCandidateEvidenceError
):
    """The environment did not provide one complete pinned configuration."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _exact(value: object, allowed: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise RealImageCandidateEvidenceError(f"{label} has invalid fields")
    return value


def _hex_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RealImageCandidateEvidenceError(f"{label} is invalid")
    return value


def _safe_ref(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(character in value for character in ("/", "\\", "\x00"))
    ):
        raise RealImageCandidateEvidenceError(f"{label} is invalid")
    return value


def _contained(root: Path, candidate: object, label: str) -> Path:
    if not isinstance(candidate, str) or not candidate:
        raise RealImageCandidateEvidenceError(f"{label} is missing")
    path = Path(candidate).resolve()
    if root not in path.parents or not path.is_file():
        raise RealImageCandidateEvidenceError(f"{label} escaped its root")
    return path


def _png_dimensions(path: Path) -> tuple[int, int]:
    content = path.read_bytes()
    if content[:8] != b"\x89PNG\r\n\x1a\n":
        raise RealImageCandidateEvidenceError("candidate is not a PNG")
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    saw_iend = False
    while offset < len(content):
        if offset + 12 > len(content):
            raise RealImageCandidateEvidenceError("candidate PNG is truncated")
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(content):
            raise RealImageCandidateEvidenceError("candidate PNG chunk is truncated")
        data = content[offset + 8 : offset + 8 + length]
        recorded_crc = struct.unpack(">I", content[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != recorded_crc:
            raise RealImageCandidateEvidenceError("candidate PNG CRC is invalid")
        if dimensions is None:
            if chunk_type != b"IHDR" or length != 13:
                raise RealImageCandidateEvidenceError("candidate PNG has no IHDR")
            dimensions = struct.unpack(">II", data[:8])
            if dimensions[0] <= 0 or dimensions[1] <= 0:
                raise RealImageCandidateEvidenceError(
                    "candidate PNG dimensions are invalid"
                )
        elif chunk_type == b"IHDR":
            raise RealImageCandidateEvidenceError("candidate PNG repeats IHDR")
        if chunk_type == b"IDAT":
            saw_idat = True
        if chunk_type == b"IEND":
            if length != 0 or end != len(content):
                raise RealImageCandidateEvidenceError(
                    "candidate PNG has an invalid IEND"
                )
            saw_iend = True
            break
        offset = end
    if dimensions is None or not saw_idat or not saw_iend:
        raise RealImageCandidateEvidenceError("candidate PNG is incomplete")
    return dimensions


class PinnedRealImageCandidateEvidence:
    """Reverify one digest-pinned four-image evidence receipt and its bytes."""

    def __init__(
        self,
        evidence_path: Path | str,
        evidence_sha256: str,
        artifact_root: Path | str,
        input_root: Path | str,
    ) -> None:
        self.evidence_path = Path(evidence_path).resolve()
        self.evidence_sha256 = _hex_digest(
            evidence_sha256, "candidate evidence digest"
        )
        self.artifact_root = Path(artifact_root).resolve()
        self.input_root = Path(input_root).resolve()
        if (
            not self.evidence_path.is_absolute()
            or not self.evidence_path.is_file()
            or not self.artifact_root.is_dir()
            or not self.input_root.is_dir()
        ):
            raise RealImageCandidateEvidenceConfigurationError(
                "candidate evidence paths are unavailable"
            )
        if _sha256_file(self.evidence_path) != self.evidence_sha256:
            raise RealImageCandidateEvidenceConfigurationError(
                "candidate evidence digest mismatch"
            )

    def _load(self) -> Mapping[str, Any]:
        try:
            value = json.loads(
                self.evidence_path.read_text(encoding="utf-8"),
                object_pairs_hook=self._reject_duplicate_keys,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RealImageCandidateEvidenceError(
                "candidate evidence is unreadable"
            ) from exc
        if not isinstance(value, Mapping):
            raise RealImageCandidateEvidenceError(
                "candidate evidence is not an object"
            )
        return _exact(
            value,
            {
                "schemaVersion",
                "state",
                "workspaceRef",
                "productionRunRef",
                "realImagePlanRef",
                "realImagePlanDigest",
                "technicalSmokeReceipt",
                "technicalSmokeReceiptDigest",
                "modelSetDigest",
                "startedAt",
                "finishedAt",
                "repositoryCommit",
                "candidateCount",
                "candidates",
                "candidateSelectionState",
                "assetAdmissionState",
                "canonicalMutationCount",
                "publicationAllowed",
                "payloadDigest",
            }
            if "payloadDigest" in value
            else {
                "schemaVersion",
                "state",
                "workspaceRef",
                "productionRunRef",
                "realImagePlanRef",
                "realImagePlanDigest",
                "technicalSmokeReceipt",
                "technicalSmokeReceiptDigest",
                "modelSetDigest",
                "startedAt",
                "finishedAt",
                "repositoryCommit",
                "candidateCount",
                "candidates",
                "candidateSelectionState",
                "assetAdmissionState",
                "canonicalMutationCount",
                "publicationAllowed",
            },
            "candidate evidence",
        )

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise RealImageCandidateEvidenceError(
                    "candidate evidence contains duplicate keys"
                )
            value[key] = item
        return value

    def _verify_workflow(
        self,
        candidate: Mapping[str, Any],
        expected_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        ordinal = candidate["ordinal"]
        workflow_path = self.evidence_path.parent / (
            f"shot-{ordinal:02d}-workflow.json"
        )
        if (
            not workflow_path.is_file()
            or _sha256_file(workflow_path) != candidate["workflowDigest"]
        ):
            raise RealImageCandidateEvidenceError("workflow digest mismatch")
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RealImageCandidateEvidenceError("workflow is unreadable") from exc
        if not isinstance(workflow, Mapping):
            raise RealImageCandidateEvidenceError("workflow is invalid")
        if len(workflow) != candidate["workflowNodeCount"]:
            raise RealImageCandidateEvidenceError("workflow node count mismatch")
        load_nodes = {
            node_id: node
            for node_id, node in workflow.items()
            if isinstance(node, Mapping) and node.get("class_type") == "LoadImage"
        }
        adapters = [
            node
            for node in workflow.values()
            if isinstance(node, Mapping)
            and node.get("class_type") == "IPAdapterAdvanced"
        ]
        if len(load_nodes) != 2 or len(adapters) != 2:
            raise RealImageCandidateEvidenceError(
                "workflow is not a two-reference IPAdapter graph"
            )
        input_digests = set()
        load_ids = set(load_nodes)
        for node in load_nodes.values():
            raw_name = node.get("inputs", {}).get("image")
            if not isinstance(raw_name, str) or Path(raw_name).is_absolute():
                raise RealImageCandidateEvidenceError("workflow input path is unsafe")
            resolved = (self.input_root / raw_name).resolve()
            if self.input_root not in resolved.parents or not resolved.is_file():
                raise RealImageCandidateEvidenceError("workflow input escaped its root")
            input_digests.add(_sha256_file(resolved))
        expected_digests = {
            item.get("referenceContentDigest")
            for item in expected_request.get("identityInputs", [])
        }
        if len(expected_digests) != 2 or input_digests != expected_digests:
            raise RealImageCandidateEvidenceError(
                "workflow identity inputs do not match the current request"
            )
        adapter_load_ids = set()
        adapter_masks = set()
        for node in adapters:
            inputs = node.get("inputs")
            if not isinstance(inputs, Mapping):
                raise RealImageCandidateEvidenceError("IPAdapter inputs are invalid")
            image_link = inputs.get("image")
            mask_link = inputs.get("attn_mask")
            if (
                not isinstance(image_link, list)
                or len(image_link) != 2
                or image_link[0] not in load_ids
                or image_link[1] != 0
                or not isinstance(mask_link, list)
                or len(mask_link) != 2
                or not isinstance(mask_link[0], str)
            ):
                raise RealImageCandidateEvidenceError(
                    "IPAdapter reference binding is invalid"
                )
            adapter_load_ids.add(image_link[0])
            adapter_masks.add(mask_link[0])
        if adapter_load_ids != load_ids or len(adapter_masks) != 2:
            raise RealImageCandidateEvidenceError(
                "workflow references are not independently masked"
            )
        latent_nodes = [
            node
            for node in workflow.values()
            if isinstance(node, Mapping)
            and node.get("class_type") == "EmptyLatentImage"
        ]
        if len(latent_nodes) != 1 or (
            latent_nodes[0].get("inputs", {}).get("width"),
            latent_nodes[0].get("inputs", {}).get("height"),
        ) != (
            expected_request["parameters"]["width"],
            expected_request["parameters"]["height"],
        ):
            raise RealImageCandidateEvidenceError("workflow dimensions are stale")
        return deepcopy(dict(workflow))

    def resolve_candidates(
        self,
        workspace_ref: str,
        production_run_ref: str,
        real_image_plan_ref: str,
        expected_requests: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        value = self._load()
        if (
            value.get("schemaVersion") != REAL_IMAGE_EVIDENCE_SCHEMA
            or value.get("state")
            != "FOUR_UNSELECTED_LOCAL_EVIDENCE_CANDIDATES_READY"
            or value.get("workspaceRef") != workspace_ref
            or value.get("productionRunRef") != production_run_ref
            or value.get("realImagePlanRef") != real_image_plan_ref
            or value.get("candidateCount") != 4
            or value.get("candidateSelectionState") != "NOT_STARTED"
            or value.get("assetAdmissionState") != "NOT_STARTED"
            or value.get("canonicalMutationCount") != 0
            or value.get("publicationAllowed") is not False
        ):
            raise RealImageCandidateEvidenceError(
                "candidate evidence scope or state is invalid"
            )
        model_set_digest = _hex_digest(
            value.get("modelSetDigest"), "model set digest"
        )
        technical_path = Path(str(value.get("technicalSmokeReceipt", ""))).resolve()
        evidence_root = self.evidence_path.parent.parent.resolve()
        if (
            evidence_root not in technical_path.parents
            or not technical_path.is_file()
            or _sha256_file(technical_path)
            != _hex_digest(
                value.get("technicalSmokeReceiptDigest"),
                "technical smoke receipt digest",
            )
        ):
            raise RealImageCandidateEvidenceError(
                "technical smoke receipt is unavailable"
            )
        requests = {
            item.get("generationRequestRef"): item
            for item in expected_requests
            if isinstance(item, Mapping)
        }
        raw_candidates = value.get("candidates")
        if len(requests) != 4 or not isinstance(raw_candidates, list) or len(raw_candidates) != 4:
            raise RealImageCandidateEvidenceError("candidate/request count mismatch")
        result = []
        seen_refs: set[str] = set()
        seen_ordinals: set[int] = set()
        for raw in raw_candidates:
            candidate = _exact(
                raw,
                {
                    "ordinal",
                    "generationRequestRef",
                    "generationRequestDigest",
                    "creativeShotVersionRef",
                    "workflowDigest",
                    "workflowNodeCount",
                    "seed",
                    "steps",
                    "submittedAt",
                    "finishedAt",
                    "latencySeconds",
                    "comfyPromptId",
                    "gpuUsed",
                    "maxGpuObservation",
                    "localEvidenceCandidateKey",
                    "state",
                    "validationState",
                    "output",
                },
                "candidate",
            )
            request = requests.get(candidate.get("generationRequestRef"))
            ordinal = candidate.get("ordinal")
            candidate_ref = _safe_ref(
                candidate.get("localEvidenceCandidateKey"), "candidate ref"
            )
            if (
                not isinstance(request, Mapping)
                or ordinal != request.get("ordinal")
                or candidate.get("generationRequestDigest")
                != request.get("payloadDigest")
                or candidate.get("creativeShotVersionRef")
                != request.get("creativeShotVersionRef")
                or candidate.get("state")
                != "UNSELECTED_LOCAL_EVIDENCE_CANDIDATE"
                or candidate.get("validationState") != "TECHNICALLY_VERIFIED"
                or candidate.get("gpuUsed") is not True
                or candidate_ref in seen_refs
                or ordinal in seen_ordinals
            ):
                raise RealImageCandidateEvidenceError(
                    "candidate lineage or state is invalid"
                )
            seen_refs.add(candidate_ref)
            seen_ordinals.add(ordinal)
            self._verify_workflow(candidate, request)
            output = _exact(
                candidate.get("output"),
                {
                    "contentDigest",
                    "byteSize",
                    "width",
                    "height",
                    "mediaType",
                    "artifactFile",
                    "reviewFile",
                },
                "candidate output",
            )
            path = _contained(
                self.artifact_root,
                output.get("artifactFile"),
                "candidate artifact",
            )
            content_digest = _hex_digest(
                output.get("contentDigest"), "candidate content digest"
            )
            width, height = _png_dimensions(path)
            if (
                output.get("mediaType") != "image/png"
                or output.get("byteSize") != path.stat().st_size
                or content_digest != _sha256_file(path)
                or (output.get("width"), output.get("height"))
                != (width, height)
                or (width, height)
                != (
                    request["parameters"]["width"],
                    request["parameters"]["height"],
                )
            ):
                raise RealImageCandidateEvidenceError(
                    "candidate artifact verification failed"
                )
            result.append(
                {
                    "candidateRef": candidate_ref,
                    "ordinal": ordinal,
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "creativeShotVersionRef": request["creativeShotVersionRef"],
                    "workflowDigest": candidate["workflowDigest"],
                    "workflowNodeCount": candidate["workflowNodeCount"],
                    "seed": candidate["seed"],
                    "steps": candidate["steps"],
                    "comfyPromptId": _safe_ref(
                        candidate["comfyPromptId"], "ComfyUI prompt ref"
                    ),
                    "latencySeconds": candidate["latencySeconds"],
                    "maxGpuObservation": deepcopy(
                        candidate["maxGpuObservation"]
                    ),
                    "artifact": {
                        "internalPath": str(path),
                        "storageKey": str(path.relative_to(self.artifact_root)),
                        "sha256": content_digest,
                        "byteSize": path.stat().st_size,
                        "width": width,
                        "height": height,
                        "mediaType": "image/png",
                    },
                    "adapterIdentity": REAL_IMAGE_EVIDENCE_ADAPTER_ID,
                    "modelSetDigest": model_set_digest,
                    "state": "TECHNICALLY_VERIFIED",
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                    "gpuUsed": True,
                    "publicationAllowed": False,
                }
            )
        if seen_ordinals != {1, 2, 3, 4}:
            raise RealImageCandidateEvidenceError("candidate ordinals are incomplete")
        return {
            "candidateEvidenceRef": "candidate-evidence-" + self.evidence_sha256[:24],
            "candidateEvidenceDigest": self.evidence_sha256,
            "artifactStoreRef": "artifact-store-"
            + sha256(str(self.artifact_root).encode("utf-8")).hexdigest()[:24],
            "modelSetDigest": model_set_digest,
            "adapterIdentity": REAL_IMAGE_EVIDENCE_ADAPTER_ID,
            "candidates": sorted(result, key=lambda item: item["ordinal"]),
            "publicationAllowed": False,
        }


def real_image_candidate_evidence_from_environment(
    environ: Mapping[str, str] | None = None,
) -> PinnedRealImageCandidateEvidence | None:
    values = os.environ if environ is None else environ
    names = {
        "path": "K2_M10_CANDIDATE_EVIDENCE_PATH",
        "digest": "K2_M10_CANDIDATE_EVIDENCE_SHA256",
        "artifacts": "K2_M10_CANDIDATE_ARTIFACT_ROOT",
        "inputs": "K2_M10_COMFYUI_INPUT_ROOT",
    }
    configured = {
        key: str(values.get(name, "")).strip() for key, name in names.items()
    }
    if not any(configured.values()):
        return None
    if not all(configured.values()):
        raise RealImageCandidateEvidenceConfigurationError(
            "M10 candidate evidence configuration is incomplete"
        )
    if not Path(configured["path"]).is_absolute():
        raise RealImageCandidateEvidenceConfigurationError(
            "M10 candidate evidence path must be absolute"
        )
    if not Path(configured["artifacts"]).is_absolute() or not Path(
        configured["inputs"]
    ).is_absolute():
        raise RealImageCandidateEvidenceConfigurationError(
            "M10 private roots must be absolute"
        )
    return PinnedRealImageCandidateEvidence(
        configured["path"],
        configured["digest"],
        configured["artifacts"],
        configured["inputs"],
    )


__all__ = [
    "PinnedRealImageCandidateEvidence",
    "REAL_IMAGE_EVIDENCE_ADAPTER_ID",
    "REAL_IMAGE_EVIDENCE_SCHEMA",
    "RealImageCandidateEvidenceConfigurationError",
    "RealImageCandidateEvidenceError",
    "real_image_candidate_evidence_from_environment",
]
