"""Generic M10 input planning and fail-closed M11 video-method routing.

The module is additive to the immutable K2 real-media revision path.  M10 reads
the canonical AssetVersion stream and its existing admission projection.  M11
uses the existing V4 MediaJobCoordinator only to reserve a MICRO_MOTION job; it
never executes an adapter in this planning boundary.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from services.v4_platform import MediaJobError

from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .execution_method_planning import M8M9ExecutionMethodPlanningService
from .foundation import (
    EpisodeProductionError,
    ExecutionNotAuthorizedError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
    _utc_now,
)
from .media import WorkerUnavailableError
from .media_candidate_review import K2MediaCandidateReviewService


METHOD_AWARE_INPUT_PLAN_RECORD_KIND = "MethodAwareInputPlanVersion"
VIDEO_METHOD_ROUTE_RECORD_KIND = "VideoMethodRouteVersion"
METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION = "v5.method-aware-input-plan.v1"
METHOD_INPUT_PLAN_SCHEMA_VERSION = "v5.method-input-plan.v1"
METHOD_INPUT_REQUIREMENT_SCHEMA_VERSION = "v5.method-input-requirement.v1"
VIDEO_METHOD_ROUTE_PLAN_SCHEMA_VERSION = "v5.video-method-route-plan.v1"
VIDEO_METHOD_ROUTE_SCHEMA_VERSION = "v5.video-method-route.v1"
METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION = (
    "v5.method-aware-video-generation-request.v1"
)
WAN_SINGLE_ANCHOR_CAPABILITY = "self-hosted-wan22-image-to-video-v1"
WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY = "v4.comfyui-wan22-image-to-video.v1"
WAN_FALLBACK_USED = False

VIDEO_METHODS = frozenset(
    {
        "SINGLE_ANCHOR_I2V",
        "CONTACT_CONDITIONED_VIDEO",
        "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
    }
)
METHOD_CAPABILITY_REGISTRY = {
    ("MICRO_MOTION", "SINGLE_ANCHOR_I2V"): WAN_SINGLE_ANCHOR_CAPABILITY,
    ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"): None,
    ("GAIT_LOCOMOTION", "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"): None,
}
METHOD_ADAPTER_IDENTITY_REGISTRY = {
    ("MICRO_MOTION", "SINGLE_ANCHOR_I2V"): WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY,
    ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"): None,
    ("GAIT_LOCOMOTION", "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"): None,
}
METHOD_CAPABILITY_REGISTRY_VERSION = "v5.video-method-capability-registry.v1"
METHOD_CAPABILITY_REGISTRY_DIGEST = _digest(
    {
        "schemaVersion": METHOD_CAPABILITY_REGISTRY_VERSION,
        "routes": [
            {
                "executionClass": execution_class,
                "executionMethod": execution_method,
                "adapterCapability": capability,
                "adapterIdentity": METHOD_ADAPTER_IDENTITY_REGISTRY[
                    (execution_class, execution_method)
                ],
            }
            for (execution_class, execution_method), capability in sorted(
                METHOD_CAPABILITY_REGISTRY.items()
            )
        ],
    }
)

_SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
_CREATE_INPUT_FIELDS = frozenset(
    {
        *_SCOPE_FIELDS,
        "productionRunRef",
        "executionMethodPlanVersionRef",
        "assetBindings",
        "idempotencyKey",
    }
)
_ASSET_BINDING_FIELDS = frozenset(
    {
        "visualExecutionRequirementRef",
        "inputRequirementKey",
        "inputRole",
        "assetVersionRef",
        "assetVersionDigest",
    }
)
_ROUTE_FIELDS = frozenset(
    {
        *_SCOPE_FIELDS,
        "productionRunRef",
        "methodAwareInputPlanVersionRef",
        "idempotencyKey",
    }
)
_INPUT_PLAN_FIELDS = frozenset(
    {
        "schemaVersion",
        "methodAwareInputPlanRef",
        "methodAwareInputPlanVersionRef",
        "inputPlanningVersion",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "executionMethodPlanRef",
        "executionMethodPlanVersionRef",
        "executionMethodPlanDigest",
        "methodInputPlans",
        "requestedAssetBindingCount",
        "resolvedAssetBindingCount",
        "inputReadyCount",
        "inputBlockedCount",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_METHOD_INPUT_FIELDS = frozenset(
    {
        "schemaVersion",
        "methodInputPlanRef",
        "inputPlanOrder",
        "visualExecutionRequirementRef",
        "visualExecutionRequirementDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "beatRef",
        "beatDigest",
        "executionClass",
        "executionMethod",
        "sourceDisposition",
        "inputRequirements",
        "inputPlanningState",
        "payloadDigest",
    }
)
_INPUT_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "inputRequirementKey",
        "acceptedInputRoles",
        "minimumAssetCount",
        "maximumAssetCount",
        "assetVersionBindings",
        "resolutionState",
        "payloadDigest",
    }
)
_RESOLVED_BINDING_FIELDS = frozenset(
    {
        "inputRequirementKey",
        "inputRole",
        "assetRef",
        "assetVersionRef",
        "assetVersionDigest",
        "assetVersionNumber",
        "mediaKind",
        "mediaType",
        "contentDigest",
        "sourceCandidateRef",
    }
)
_ROUTE_PLAN_FIELDS = frozenset(
    {
        "schemaVersion",
        "videoMethodRouteRef",
        "videoMethodRouteVersionRef",
        "routingVersion",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "methodAwareInputPlanRef",
        "methodAwareInputPlanVersionRef",
        "methodAwareInputPlanDigest",
        "executionMethodPlanVersionRef",
        "executionMethodPlanDigest",
        "capabilityRegistryVersion",
        "capabilityRegistryDigest",
        "routes",
        "videoGenerationRequests",
        "queuedJobs",
        "videoGenerationRequestCount",
        "queuedJobCount",
        "wanFallbackUsed",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_VIDEO_ROUTE_FIELDS = frozenset(
    {
        "schemaVersion",
        "routeRef",
        "routeOrder",
        "methodInputPlanRef",
        "methodInputPlanDigest",
        "visualExecutionRequirementRef",
        "visualExecutionRequirementDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "beatRef",
        "beatDigest",
        "executionClass",
        "executionMethod",
        "routingState",
        "adapterCapability",
        "adapterIdentity",
        "videoGenerationRequestRef",
        "videoGenerationRequestDigest",
        "mediaJobRef",
        "fallbackUsed",
        "targetBoundary",
        "payloadDigest",
    }
)
_ROUTING_STATES = frozenset(
    {
        "BYPASSED_STATIC_PLATE",
        "QUEUED_EXISTING_MEDIA_JOB",
        "CAPABILITY_UNAVAILABLE",
        "REJECTED_DETERMINISTIC_POSTPROCESS",
        "INPUT_BLOCKED",
    }
)
_QUEUED_JOB_FIELDS = frozenset(
    {
        "generationRequestRef",
        "generationRequestDigest",
        "mediaJobRef",
        "queueState",
        "queueReplay",
    }
)


class MediaJobDispatchPort(Protocol):
    def dispatch(
        self, request: Mapping[str, Any], *, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]: ...


def resolve_video_method_capability(
    execution_class: str, execution_method: str
) -> dict[str, Any]:
    """Resolve one closed video method without substitution or fallback."""

    pair = (execution_class, execution_method)
    if execution_method not in VIDEO_METHODS or pair not in METHOD_CAPABILITY_REGISTRY:
        raise EpisodeProductionError("execution class/method pair is not routable")
    capability = METHOD_CAPABILITY_REGISTRY[pair]
    return {
        "executionClass": execution_class,
        "executionMethod": execution_method,
        "capabilityState": (
            "AVAILABLE" if capability is not None else "CAPABILITY_UNAVAILABLE"
        ),
        "adapterCapability": capability,
        "adapterIdentity": METHOD_ADAPTER_IDENTITY_REGISTRY[pair],
        "fallbackUsed": WAN_FALLBACK_USED,
    }


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = _digest(result)
    return result


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sealed(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and _is_digest(value.get("payloadDigest"))
        and _digest(
            {key: item for key, item in value.items() if key != "payloadDigest"}
        )
        == value.get("payloadDigest")
    )


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise RepositoryUnavailableError("stored method-aware media payload is invalid")
    return deepcopy(dict(value))


def _stable_ref(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}-{_digest(value)[:32]}"


class M10M11MethodAwareMediaService:
    """Create immutable M10 plans and reserve only supported M11 jobs."""

    def __init__(
        self,
        execution_method_planning: M8M9ExecutionMethodPlanningService,
        evidence_repository: EpisodeProductionEvidenceRepository,
        candidate_review: K2MediaCandidateReviewService,
        media_jobs: MediaJobDispatchPort,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.execution_method_planning = execution_method_planning
        self.evidence_repository = evidence_repository
        self.candidate_review = candidate_review
        self.media_jobs = media_jobs
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _scope(command: Mapping[str, Any]) -> tuple[dict[str, str], str]:
        scope = {
            field: _required_ref(command.get(field), field) for field in _SCOPE_FIELDS
        }
        return scope, _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )

    def _current_execution_plan(
        self,
        scope: Mapping[str, str],
        run_ref: str,
        version_ref: Any,
    ) -> dict[str, Any]:
        return self.execution_method_planning.require_current_plan(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
            _required_ref(version_ref, "executionMethodPlanVersionRef"),
        )

    @staticmethod
    def _beat_index(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for shot in plan.get("creativeShotVersions", []):
            if not isinstance(shot, Mapping):
                raise RepositoryUnavailableError("current M9 Shot facts are invalid")
            for beat in shot.get("actionExecutionBeats", []):
                if not isinstance(beat, Mapping) or beat.get("beatRef") in result:
                    raise RepositoryUnavailableError("current M9 beat facts are invalid")
                result[str(beat["beatRef"])] = deepcopy(dict(beat))
        return result

    @staticmethod
    def _postprocess_index(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in plan.get("postprocessRequirements", []):
            if not isinstance(item, Mapping) or item.get("beatRef") in result:
                raise RepositoryUnavailableError(
                    "current M9 postprocess facts are invalid"
                )
            result[str(item["beatRef"])] = deepcopy(dict(item))
        return result

    @staticmethod
    def _input_specs(
        requirement: Mapping[str, Any],
        beat: Mapping[str, Any],
        postprocess: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        method = requirement["executionMethod"]
        requirement_ref = requirement["visualExecutionRequirementRef"]

        def spec(
            key: str,
            roles: Sequence[str],
            minimum: int = 1,
            maximum: int = 1,
        ) -> dict[str, Any]:
            return {
                "inputRequirementKey": key,
                "acceptedInputRoles": list(roles),
                "minimumAssetCount": minimum,
                "maximumAssetCount": maximum,
            }

        if method == "STATIC_PLATE_OR_REUSE":
            return [
                spec(
                    f"static-plate:{requirement_ref}",
                    ("STATIC_PLATE",),
                )
            ]
        if method == "SINGLE_ANCHOR_I2V":
            return [
                spec(
                    f"action-ready-anchor:{requirement_ref}",
                    ("ACTION_READY_ANCHOR",),
                )
            ]
        if method == "CONTACT_CONDITIONED_VIDEO":
            subjects = beat.get("subjectRefs")
            targets = beat.get("targetRefs")
            if not isinstance(subjects, list) or not subjects:
                raise RepositoryUnavailableError("contact subject facts are invalid")
            values = [
                spec(f"subject-conditioning:{ref}", ("SUBJECT_CONDITIONING",))
                for ref in subjects
            ]
            if isinstance(targets, list) and targets:
                values.extend(
                    spec(f"target-conditioning:{ref}", ("TARGET_CONDITIONING",))
                    for ref in targets
                )
            else:
                values.append(
                    spec(
                        f"target-conditioning-unresolved:{requirement_ref}",
                        ("TARGET_CONDITIONING",),
                    )
                )
            return values
        if method == "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO":
            return [
                spec(
                    f"pose-or-trajectory:{requirement_ref}",
                    ("POSE_CONDITIONING", "TRAJECTORY_CONDITIONING"),
                    maximum=2,
                )
            ]
        if method == "V3_DETERMINISTIC_COMPOSITION":
            if not isinstance(postprocess, Mapping):
                raise RepositoryUnavailableError(
                    "deterministic postprocess requirement is missing"
                )
            values = [
                spec(
                    _required_ref(
                        postprocess.get("eventFreeBaseMediaRequirementKey"),
                        "eventFreeBaseMediaRequirementKey",
                    ),
                    ("EVENT_FREE_BASE_PLATE",),
                )
            ]
            collections = (
                ("maskAssetRequirementKeys", "MASK_ASSET"),
                ("resourceAssetRequirementKeys", "RESOURCE_ASSET"),
                ("staticAssetRequirementKeys", "STATIC_ASSET"),
            )
            for field, role in collections:
                keys = postprocess.get(field)
                if not isinstance(keys, list):
                    raise RepositoryUnavailableError(
                        "deterministic input requirement facts are invalid"
                    )
                values.extend(spec(_required_ref(key, field), (role,)) for key in keys)
            return values
        raise RepositoryUnavailableError("current M9 execution method is unsupported")

    def _canonical_assets(
        self, workspace: str, run_ref: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        assets = self.candidate_review.asset_versions.list_asset_versions(
            workspace, run_ref
        )
        projection = self.candidate_review.get_projection(workspace, run_ref)
        return assets, projection

    @staticmethod
    def _resolve_asset(
        raw: Mapping[str, Any],
        *,
        assets: Sequence[Mapping[str, Any]],
        projection: Mapping[str, Any],
        input_requirement_key: str,
        input_role: str,
        creative_shot_version_ref: str,
    ) -> dict[str, Any]:
        ref = _required_ref(raw.get("assetVersionRef"), "assetVersionRef")
        digest = raw.get("assetVersionDigest")
        if not _is_digest(digest):
            raise EpisodeProductionError("assetVersionDigest is invalid")
        matches = [
            item
            for item in assets
            if item.get("assetVersionRef") == ref
            and item.get("payloadDigest") == digest
        ]
        if len(matches) != 1:
            raise StaleInputError("bound AssetVersion is unavailable or changed")
        asset = matches[0]
        logical = [
            item for item in assets if item.get("assetRef") == asset.get("assetRef")
        ]
        if not logical:
            raise StaleInputError("bound AssetVersion lineage is unavailable")
        latest = max(
            logical,
            key=lambda item: (
                int(item.get("version", 0)),
                str(item.get("assetVersionRef", "")),
            ),
        )
        if (
            latest.get("assetVersionRef") != ref
            or latest.get("payloadDigest") != digest
        ):
            raise StaleInputError("bound AssetVersion is not current")
        media_kind = str(asset.get("mediaKind", "")).upper()
        media_type = asset.get("mediaType")
        content_digest = asset.get("sha256", asset.get("fileDigest"))
        if (
            asset.get("state") != "REGISTERED"
            or asset.get("publicationAllowed") is not False
            or asset.get("creativeShotVersionRef") != creative_shot_version_ref
            or media_kind != "IMAGE"
            or media_type not in {"image/png", "image/jpeg"}
            or not _is_digest(content_digest)
        ):
            raise StaleInputError("bound AssetVersion is not a usable image")
        candidate_ref = asset.get("sourceCandidateRef")
        candidate_items = projection.get("candidates")
        candidate = next(
            (
                item
                for item in candidate_items or []
                if isinstance(item, Mapping)
                and item.get("candidateRef") == candidate_ref
            ),
            None,
        )
        if (
            not isinstance(candidate, Mapping)
            or candidate.get("technicalState") != "TECHNICALLY_VERIFIED"
            or candidate.get("visualQcState") != "SEMANTIC_QC_PASSED"
            or candidate.get("selectionState") != "SELECTED_BY_HUMAN"
            or candidate.get("admissionState") != "ADMITTED"
            or candidate.get("applicabilityState") != "CURRENT"
            or candidate.get("assetVersionRef") != ref
            or not isinstance(candidate.get("candidate"), Mapping)
            or candidate["candidate"].get("slotRef")
            != creative_shot_version_ref
        ):
            raise StaleInputError(
                "bound AssetVersion admission chain is absent or stale"
            )
        version = asset.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise RepositoryUnavailableError("bound AssetVersion version is invalid")
        return {
            "inputRequirementKey": input_requirement_key,
            "inputRole": input_role,
            "assetRef": _required_ref(asset.get("assetRef"), "assetRef"),
            "assetVersionRef": ref,
            "assetVersionDigest": digest,
            "assetVersionNumber": version,
            "mediaKind": media_kind,
            "mediaType": media_type,
            "contentDigest": content_digest,
            "sourceCandidateRef": _required_ref(candidate_ref, "sourceCandidateRef"),
        }

    def _normalize_asset_bindings(
        self,
        value: Any,
        *,
        plan: Mapping[str, Any],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        if not isinstance(value, list):
            raise EpisodeProductionError("assetBindings is invalid")
        visual = plan.get("visualExecutionRequirements")
        if not isinstance(visual, list) or not visual:
            raise RepositoryUnavailableError("current M9 visual requirements are invalid")
        visual_by_ref = {
            item.get("visualExecutionRequirementRef"): item
            for item in visual
            if isinstance(item, Mapping)
        }
        beats = self._beat_index(plan)
        posts = self._postprocess_index(plan)
        allowed: dict[tuple[str, str], dict[str, Any]] = {}
        for requirement in visual:
            ref = requirement["visualExecutionRequirementRef"]
            beat = beats.get(requirement["beatRef"])
            if beat is None:
                raise RepositoryUnavailableError("current M9 beat binding is invalid")
            for item in self._input_specs(requirement, beat, posts.get(beat["beatRef"])):
                allowed[(ref, item["inputRequirementKey"])] = item
        normalized: dict[tuple[str, str], list[dict[str, Any]]] = {}
        identities: set[tuple[str, str, str, str]] = set()
        for index, raw in enumerate(value):
            if not isinstance(raw, Mapping) or set(raw) != _ASSET_BINDING_FIELDS:
                raise EpisodeProductionError(
                    f"assetBindings[{index}] fields are invalid"
                )
            visual_ref = _required_ref(
                raw.get("visualExecutionRequirementRef"),
                "visualExecutionRequirementRef",
            )
            key = _required_ref(raw.get("inputRequirementKey"), "inputRequirementKey")
            role = _required_ref(raw.get("inputRole"), "inputRole")
            spec = allowed.get((visual_ref, key))
            if visual_ref not in visual_by_ref or spec is None:
                raise EpisodeProductionError("asset binding requirement is unknown")
            if role not in spec["acceptedInputRoles"]:
                raise EpisodeProductionError("asset binding role is not permitted")
            binding = {
                "visualExecutionRequirementRef": visual_ref,
                "inputRequirementKey": key,
                "inputRole": role,
                "assetVersionRef": _required_ref(
                    raw.get("assetVersionRef"), "assetVersionRef"
                ),
                "assetVersionDigest": raw.get("assetVersionDigest"),
            }
            if not _is_digest(binding["assetVersionDigest"]):
                raise EpisodeProductionError("assetVersionDigest is invalid")
            identity = (
                visual_ref,
                key,
                role,
                binding["assetVersionRef"],
            )
            if identity in identities:
                raise EpisodeProductionError("asset binding is duplicated")
            identities.add(identity)
            normalized.setdefault((visual_ref, key), []).append(binding)
        for group_key, bindings in normalized.items():
            if len(bindings) > allowed[group_key]["maximumAssetCount"]:
                raise EpisodeProductionError("too many assets bind one input requirement")
        return normalized

    @staticmethod
    def _request_digest(
        scope: Mapping[str, str],
        run_ref: str,
        plan: Mapping[str, Any],
        bindings: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    ) -> str:
        return _digest(
            {
                "schemaVersion": "v5.method-aware-input-plan-request.v1",
                **scope,
                "productionRunRef": run_ref,
                "executionMethodPlanVersionRef": plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": plan["payloadDigest"],
                "assetBindings": [
                    dict(item)
                    for group in sorted(bindings)
                    for item in sorted(
                        bindings[group],
                        key=lambda value: (
                            value["inputRole"], value["assetVersionRef"]
                        ),
                    )
                ],
            }
        )

    def _build_input_payload(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        plan: Mapping[str, Any],
        bindings: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
        previous: Sequence[tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        workspace = scope["workspaceRef"]
        assets: list[dict[str, Any]] = []
        projection: dict[str, Any] = {}
        if bindings:
            assets, projection = self._canonical_assets(workspace, run_ref)
        beats = self._beat_index(plan)
        posts = self._postprocess_index(plan)
        method_plans: list[dict[str, Any]] = []
        resolved_count = 0
        for requirement in plan["visualExecutionRequirements"]:
            beat = beats[requirement["beatRef"]]
            input_requirements: list[dict[str, Any]] = []
            for raw_spec in self._input_specs(
                requirement, beat, posts.get(beat["beatRef"])
            ):
                selected = bindings.get(
                    (
                        requirement["visualExecutionRequirementRef"],
                        raw_spec["inputRequirementKey"],
                    ),
                    (),
                )
                resolved = [
                    self._resolve_asset(
                        raw,
                        assets=assets,
                        projection=projection,
                        input_requirement_key=raw_spec["inputRequirementKey"],
                        input_role=raw["inputRole"],
                        creative_shot_version_ref=requirement[
                            "creativeShotVersionRef"
                        ],
                    )
                    for raw in selected
                ]
                resolved_count += len(resolved)
                ready = len(resolved) >= raw_spec["minimumAssetCount"]
                input_requirements.append(
                    _seal(
                        {
                            "schemaVersion": METHOD_INPUT_REQUIREMENT_SCHEMA_VERSION,
                            **raw_spec,
                            "assetVersionBindings": resolved,
                            "resolutionState": (
                                "RESOLVED_CURRENT_ASSET"
                                if ready
                                else "ASSET_REQUIRED"
                            ),
                        }
                    )
                )
            ready = all(
                item["resolutionState"] == "RESOLVED_CURRENT_ASSET"
                for item in input_requirements
            )
            method_plans.append(
                _seal(
                    {
                        "schemaVersion": METHOD_INPUT_PLAN_SCHEMA_VERSION,
                        "methodInputPlanRef": _required_ref(
                            self._ref_factory("method-input-plan"),
                            "methodInputPlanRef",
                        ),
                        "inputPlanOrder": len(method_plans) + 1,
                        "visualExecutionRequirementRef": requirement[
                            "visualExecutionRequirementRef"
                        ],
                        "visualExecutionRequirementDigest": requirement[
                            "payloadDigest"
                        ],
                        "creativeShotVersionRef": requirement[
                            "creativeShotVersionRef"
                        ],
                        "creativeShotVersionDigest": requirement[
                            "creativeShotVersionDigest"
                        ],
                        "beatRef": requirement["beatRef"],
                        "beatDigest": requirement["beatDigest"],
                        "executionClass": requirement["executionClass"],
                        "executionMethod": requirement["executionMethod"],
                        "sourceDisposition": requirement["disposition"],
                        "inputRequirements": input_requirements,
                        "inputPlanningState": (
                            "READY" if ready else "INPUT_REQUIRED"
                        ),
                    }
                )
            )
        version = len(previous) + 1
        plan_ref = (
            previous[-1][1]["methodAwareInputPlanRef"]
            if previous
            else _required_ref(
                self._ref_factory("method-aware-input-plan"),
                "methodAwareInputPlanRef",
            )
        )
        return _seal(
            {
                "schemaVersion": METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION,
                "methodAwareInputPlanRef": plan_ref,
                "methodAwareInputPlanVersionRef": _required_ref(
                    self._ref_factory("method-aware-input-plan-version"),
                    "methodAwareInputPlanVersionRef",
                ),
                "inputPlanningVersion": version,
                **scope,
                "productionRunRef": run_ref,
                "executionMethodPlanRef": plan["executionMethodPlanRef"],
                "executionMethodPlanVersionRef": plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": plan["payloadDigest"],
                "methodInputPlans": method_plans,
                "requestedAssetBindingCount": sum(
                    len(values) for values in bindings.values()
                ),
                "resolvedAssetBindingCount": resolved_count,
                "inputReadyCount": sum(
                    item["inputPlanningState"] == "READY" for item in method_plans
                ),
                "inputBlockedCount": sum(
                    item["inputPlanningState"] == "INPUT_REQUIRED"
                    for item in method_plans
                ),
                "publicationAllowed": False,
                "createdAt": self._clock(),
            }
        )

    @staticmethod
    def _validate_input_payload(value: Any) -> dict[str, Any]:
        if (
            not _sealed(value)
            or set(value) != _INPUT_PLAN_FIELDS
            or value.get("schemaVersion") != METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION
            or value.get("publicationAllowed") is not False
            or isinstance(value.get("inputPlanningVersion"), bool)
            or not isinstance(value.get("inputPlanningVersion"), int)
            or value["inputPlanningVersion"] < 1
            or not isinstance(value.get("methodInputPlans"), list)
            or not value["methodInputPlans"]
        ):
            raise RepositoryUnavailableError("stored M10 input plan is invalid")
        plans = value["methodInputPlans"]
        resolved = 0
        ready = 0
        for order, item in enumerate(plans, start=1):
            if (
                not _sealed(item)
                or set(item) != _METHOD_INPUT_FIELDS
                or item.get("schemaVersion") != METHOD_INPUT_PLAN_SCHEMA_VERSION
                or item.get("inputPlanOrder") != order
                or item.get("inputPlanningState") not in {"READY", "INPUT_REQUIRED"}
                or not isinstance(item.get("inputRequirements"), list)
                or not item["inputRequirements"]
            ):
                raise RepositoryUnavailableError("stored M10 method input is invalid")
            method_ready = True
            for requirement in item["inputRequirements"]:
                bindings = requirement.get("assetVersionBindings") if isinstance(
                    requirement, Mapping
                ) else None
                if (
                    not _sealed(requirement)
                    or set(requirement) != _INPUT_REQUIREMENT_FIELDS
                    or requirement.get("schemaVersion")
                    != METHOD_INPUT_REQUIREMENT_SCHEMA_VERSION
                    or not isinstance(bindings, list)
                    or any(
                        not isinstance(binding, Mapping)
                        or set(binding) != _RESOLVED_BINDING_FIELDS
                        for binding in bindings
                    )
                    or requirement.get("resolutionState")
                    not in {"RESOLVED_CURRENT_ASSET", "ASSET_REQUIRED"}
                ):
                    raise RepositoryUnavailableError(
                        "stored M10 input requirement is invalid"
                    )
                count = len(bindings)
                minimum = requirement.get("minimumAssetCount")
                maximum = requirement.get("maximumAssetCount")
                if (
                    isinstance(minimum, bool)
                    or not isinstance(minimum, int)
                    or isinstance(maximum, bool)
                    or not isinstance(maximum, int)
                    or not 0 <= minimum <= maximum
                    or count > maximum
                    or (
                        requirement["resolutionState"]
                        == "RESOLVED_CURRENT_ASSET"
                    )
                    != (count >= minimum)
                ):
                    raise RepositoryUnavailableError(
                        "stored M10 requirement count is invalid"
                    )
                resolved += count
                method_ready = method_ready and count >= minimum
            if (item["inputPlanningState"] == "READY") != method_ready:
                raise RepositoryUnavailableError("stored M10 readiness is invalid")
            ready += method_ready
        if (
            value.get("resolvedAssetBindingCount") != resolved
            or value.get("requestedAssetBindingCount") != resolved
            or value.get("inputReadyCount") != ready
            or value.get("inputBlockedCount") != len(plans) - ready
        ):
            raise RepositoryUnavailableError("stored M10 plan totals are invalid")
        return deepcopy(dict(value))

    def _input_records(
        self, workspace: str, run_ref: str
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result = []
        for expected, record in enumerate(
            self.evidence_repository.list_records(
                workspace, run_ref, record_kind=METHOD_AWARE_INPUT_PLAN_RECORD_KIND
            ),
            start=1,
        ):
            payload = self._validate_input_payload(_payload(record))
            if (
                record.get("recordKind") != METHOD_AWARE_INPUT_PLAN_RECORD_KIND
                or record.get("recordRef") != payload["methodAwareInputPlanRef"]
                or record.get("recordVersion") != payload["inputPlanningVersion"]
                or record.get("payloadDigest") != payload["payloadDigest"]
                or payload["inputPlanningVersion"] != expected
            ):
                raise RepositoryUnavailableError("stored M10 envelope is invalid")
            result.append((deepcopy(dict(record)), payload))
        return result

    def create_input_plan(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != _CREATE_INPUT_FIELDS:
            raise EpisodeProductionError(
                "command fields do not match the M10 input-plan contract"
            )
        scope, run_ref = self._scope(command)
        key = _idempotency_key(command.get("idempotencyKey"))
        plan = self._current_execution_plan(
            scope, run_ref, command.get("executionMethodPlanVersionRef")
        )
        bindings = self._normalize_asset_bindings(
            command.get("assetBindings"), plan=plan
        )
        request_digest = self._request_digest(scope, run_ref, plan, bindings)
        records = self._input_records(scope["workspaceRef"], run_ref)
        existing = self.evidence_repository.get_record_by_idempotency_key(
            scope["workspaceRef"], run_ref, key
        )
        if existing is not None:
            if (
                existing.get("recordKind") != METHOD_AWARE_INPUT_PLAN_RECORD_KIND
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError("M10 input-plan command conflicts")
            payload = self._validate_input_payload(_payload(existing))
            current = bool(records) and records[-1][1][
                "methodAwareInputPlanVersionRef"
            ] == payload["methodAwareInputPlanVersionRef"]
            return {
                **payload,
                "currentness": "CURRENT" if current else "STALE",
                "idempotentReplay": True,
            }
        journal_head = self.evidence_repository.record_journal_head(
            scope["workspaceRef"], run_ref
        )
        payload = self._build_input_payload(
            scope=scope,
            run_ref=run_ref,
            plan=plan,
            bindings=bindings,
            previous=records,
        )
        record = EvidenceRecord(
            workspaceRef=scope["workspaceRef"],
            productionRunRef=run_ref,
            recordKind=METHOD_AWARE_INPUT_PLAN_RECORD_KIND,
            recordRef=payload["methodAwareInputPlanRef"],
            recordVersion=payload["inputPlanningVersion"],
            idempotencyKey=key,
            requestDigest=request_digest,
            createdAt=self._clock(),
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        stored, replayed = self.evidence_repository.append_records(
            (record,), expected_record_journal_head=journal_head
        )
        result = self._validate_input_payload(_payload(stored[0]))
        return {**result, "currentness": "CURRENT", "idempotentReplay": replayed}

    def _bound_assets_current(
        self, workspace: str, run_ref: str, payload: Mapping[str, Any]
    ) -> bool:
        bindings = [
            (method_plan, binding)
            for method_plan in payload["methodInputPlans"]
            for requirement in method_plan["inputRequirements"]
            for binding in requirement["assetVersionBindings"]
        ]
        if not bindings:
            return True
        try:
            assets, projection = self._canonical_assets(workspace, run_ref)
            for method_plan, binding in bindings:
                resolved = self._resolve_asset(
                    binding,
                    assets=assets,
                    projection=projection,
                    input_requirement_key=binding["inputRequirementKey"],
                    input_role=binding["inputRole"],
                    creative_shot_version_ref=method_plan[
                        "creativeShotVersionRef"
                    ],
                )
                if resolved != binding:
                    return False
        except EpisodeProductionError:
            return False
        return True

    def get_input_plan(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        method_aware_input_plan_version_ref: str | None = None,
    ) -> dict[str, Any]:
        scope = {
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "projectRef": _required_ref(project_ref, "projectRef"),
            "seriesRef": _required_ref(series_ref, "seriesRef"),
            "episodeRef": _required_ref(episode_ref, "episodeRef"),
        }
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        records = self._input_records(scope["workspaceRef"], run_ref)
        if method_aware_input_plan_version_ref is None:
            selected = records[-1] if records else None
        else:
            version_ref = _required_ref(
                method_aware_input_plan_version_ref,
                "methodAwareInputPlanVersionRef",
            )
            selected = next(
                (
                    item
                    for item in records
                    if item[1]["methodAwareInputPlanVersionRef"] == version_ref
                ),
                None,
            )
        if selected is None or any(
            selected[1].get(field) != value for field, value in scope.items()
        ):
            raise RecordNotFoundError("MethodAwareInputPlanVersion was not found")
        payload = selected[1]
        current = False
        try:
            plan = self._current_execution_plan(
                scope, run_ref, payload["executionMethodPlanVersionRef"]
            )
            current = (
                selected is records[-1]
                and plan["payloadDigest"] == payload["executionMethodPlanDigest"]
                and self._bound_assets_current(scope["workspaceRef"], run_ref, payload)
            )
        except EpisodeProductionError:
            current = False
        return {
            **payload,
            "currentness": "CURRENT" if current else "STALE",
            "idempotentReplay": False,
        }

    def require_current_input_plan(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        method_aware_input_plan_version_ref: str,
    ) -> dict[str, Any]:
        plan = self.get_input_plan(
            workspace_ref,
            project_ref,
            series_ref,
            episode_ref,
            production_run_ref,
            method_aware_input_plan_version_ref,
        )
        if plan["currentness"] != "CURRENT":
            raise ExecutionNotAuthorizedError("current M10 input plan is required")
        return plan

    @staticmethod
    def _route_request_digest(
        scope: Mapping[str, str], run_ref: str, input_plan: Mapping[str, Any]
    ) -> str:
        return _digest(
            {
                "schemaVersion": "v5.video-method-route-request.v1",
                **scope,
                "productionRunRef": run_ref,
                "methodAwareInputPlanVersionRef": input_plan[
                    "methodAwareInputPlanVersionRef"
                ],
                "methodAwareInputPlanDigest": input_plan["payloadDigest"],
                "capabilityRegistryDigest": METHOD_CAPABILITY_REGISTRY_DIGEST,
            }
        )

    @staticmethod
    def _anchor(method_plan: Mapping[str, Any]) -> Mapping[str, Any] | None:
        values = [
            binding
            for requirement in method_plan["inputRequirements"]
            for binding in requirement["assetVersionBindings"]
            if binding["inputRole"] == "ACTION_READY_ANCHOR"
        ]
        return values[0] if len(values) == 1 else None

    def _micro_request(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        input_plan: Mapping[str, Any],
        method_plan: Mapping[str, Any],
        execution_plan: Mapping[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        anchor = self._anchor(method_plan)
        if anchor is None:
            raise RepositoryUnavailableError("ready MICRO_MOTION anchor is invalid")
        shot = next(
            (
                item
                for item in execution_plan["creativeShotVersions"]
                if item["creativeShotVersionRef"]
                == method_plan["creativeShotVersionRef"]
            ),
            None,
        )
        beat = next(
            (
                item
                for item in (shot or {}).get("actionExecutionBeats", [])
                if item["beatRef"] == method_plan["beatRef"]
            ),
            None,
        )
        if not isinstance(shot, Mapping) or not isinstance(beat, Mapping):
            raise RepositoryUnavailableError("M11 source Shot/beat is invalid")
        identity = {
            "methodAwareInputPlanVersionRef": input_plan[
                "methodAwareInputPlanVersionRef"
            ],
            "visualExecutionRequirementRef": method_plan[
                "visualExecutionRequirementRef"
            ],
        }
        return _seal(
            {
                "schemaVersion": METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION,
                **scope,
                "productionRunRef": run_ref,
                "generationRequestRef": _stable_ref(
                    "method-video-generation-request", identity
                ),
                "generationRequestVersionRef": _stable_ref(
                    "method-video-generation-request-version", identity
                ),
                "version": 1,
                "methodAwareInputPlanVersionRef": input_plan[
                    "methodAwareInputPlanVersionRef"
                ],
                "methodAwareInputPlanDigest": input_plan["payloadDigest"],
                "executionMethodPlanVersionRef": input_plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": input_plan[
                    "executionMethodPlanDigest"
                ],
                "visualExecutionRequirementRef": method_plan[
                    "visualExecutionRequirementRef"
                ],
                "visualExecutionRequirementDigest": method_plan[
                    "visualExecutionRequirementDigest"
                ],
                "creativeShotVersionRef": method_plan["creativeShotVersionRef"],
                "creativeShotVersionDigest": method_plan[
                    "creativeShotVersionDigest"
                ],
                "beatRef": method_plan["beatRef"],
                "beatDigest": method_plan["beatDigest"],
                "executionClass": "MICRO_MOTION",
                "executionMethod": "SINGLE_ANCHOR_I2V",
                "sourceImageAssetRef": anchor["assetRef"],
                "sourceImageAssetVersionRef": anchor["assetVersionRef"],
                "sourceImageAssetVersionDigest": anchor["assetVersionDigest"],
                "sourceImageContentDigest": anchor["contentDigest"],
                "sourceImageMediaType": anchor["mediaType"],
                "cameraInstruction": deepcopy(shot["cameraInstruction"]),
                "sourceAction": {
                    "sourceSpan": deepcopy(beat["sourceSpan"]),
                    "sourceTextDigest": beat["sourceTextDigest"],
                },
                "frameRange": {
                    "startFrameInclusive": beat["frameRangeStartInclusive"],
                    "endFrameExclusive": beat["frameRangeEndExclusive"],
                },
                "adapterCapability": WAN_SINGLE_ANCHOR_CAPABILITY,
                "executionMode": "INTERNAL_SELF_HOSTED",
                "executionAuthorizationState": "QUEUED_NOT_EXECUTED",
                "requestedProvenance": "SELF_HOSTED_AI_GENERATED",
                "selectionRequired": True,
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )

    def _build_route_payload(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        input_plan: Mapping[str, Any],
        execution_plan: Mapping[str, Any],
        client_key: str,
        previous: Sequence[tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        now = self._clock()
        requests: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []
        routes: list[dict[str, Any]] = []
        for method_plan in input_plan["methodInputPlans"]:
            execution_class = method_plan["executionClass"]
            method = method_plan["executionMethod"]
            state: str
            capability: str | None = None
            adapter_identity: str | None = None
            target: str
            request: dict[str, Any] | None = None
            job_ref: str | None = None
            if (execution_class, method) == (
                "STATIC_HOLD",
                "STATIC_PLATE_OR_REUSE",
            ):
                state = "BYPASSED_STATIC_PLATE"
                target = "M10_ASSET_OUTPUT"
            elif (execution_class, method) == (
                "DETERMINISTIC_EVENT",
                "V3_DETERMINISTIC_COMPOSITION",
            ):
                state = "REJECTED_DETERMINISTIC_POSTPROCESS"
                target = "M13_DETERMINISTIC_POSTPROCESS"
            elif method not in VIDEO_METHODS:
                raise RepositoryUnavailableError("M11 method registry is closed")
            else:
                try:
                    registry_route = resolve_video_method_capability(
                        execution_class, method
                    )
                except EpisodeProductionError as exc:
                    raise RepositoryUnavailableError(
                        "M11 execution class/method pair is unsupported"
                    ) from exc
                capability = registry_route["adapterCapability"]
                adapter_identity = registry_route["adapterIdentity"]
                target = "M11_VIDEO_EXECUTION"
                if capability is None:
                    state = "CAPABILITY_UNAVAILABLE"
                elif method_plan["inputPlanningState"] != "READY":
                    state = "INPUT_BLOCKED"
                else:
                    configured_adapter = getattr(self.media_jobs, "adapter", None)
                    if (
                        getattr(configured_adapter, "adapter_identity", None)
                        != WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY
                    ):
                        raise WorkerUnavailableError(
                            "existing MediaJobCoordinator is not bound to the "
                            "single-anchor Wan adapter"
                        )
                    request = self._micro_request(
                        scope=scope,
                        run_ref=run_ref,
                        input_plan=input_plan,
                        method_plan=method_plan,
                        execution_plan=execution_plan,
                        created_at=now,
                    )
                    child_key = _digest(
                        {
                            "routeIdempotencyKey": client_key,
                            "visualExecutionRequirementRef": method_plan[
                                "visualExecutionRequirementRef"
                            ],
                        }
                    )
                    try:
                        job, queue_replay = self.media_jobs.dispatch(
                            request, idempotency_key=child_key
                        )
                    except (AttributeError, MediaJobError) as exc:
                        raise WorkerUnavailableError(
                            "existing MediaJobCoordinator could not reserve M11 work"
                        ) from exc
                    if (
                        not isinstance(job, Mapping)
                        or job.get("requestDigest") != request["payloadDigest"]
                        or job.get("state") != "QUEUED"
                        or not isinstance(job.get("jobRef"), str)
                    ):
                        raise WorkerUnavailableError(
                            "existing MediaJobCoordinator returned an invalid reservation"
                        )
                    job_ref = job["jobRef"]
                    requests.append(request)
                    queued.append(
                        {
                            "generationRequestRef": request[
                                "generationRequestRef"
                            ],
                            "generationRequestDigest": request["payloadDigest"],
                            "mediaJobRef": job_ref,
                            "queueState": "QUEUED",
                            "queueReplay": queue_replay,
                        }
                    )
                    state = "QUEUED_EXISTING_MEDIA_JOB"
            routes.append(
                _seal(
                    {
                        "schemaVersion": VIDEO_METHOD_ROUTE_SCHEMA_VERSION,
                        "routeRef": _stable_ref(
                            "video-method-route",
                            {
                                "methodAwareInputPlanVersionRef": input_plan[
                                    "methodAwareInputPlanVersionRef"
                                ],
                                "visualExecutionRequirementRef": method_plan[
                                    "visualExecutionRequirementRef"
                                ],
                            },
                        ),
                        "routeOrder": len(routes) + 1,
                        "methodInputPlanRef": method_plan["methodInputPlanRef"],
                        "methodInputPlanDigest": method_plan["payloadDigest"],
                        "visualExecutionRequirementRef": method_plan[
                            "visualExecutionRequirementRef"
                        ],
                        "visualExecutionRequirementDigest": method_plan[
                            "visualExecutionRequirementDigest"
                        ],
                        "creativeShotVersionRef": method_plan[
                            "creativeShotVersionRef"
                        ],
                        "creativeShotVersionDigest": method_plan[
                            "creativeShotVersionDigest"
                        ],
                        "beatRef": method_plan["beatRef"],
                        "beatDigest": method_plan["beatDigest"],
                        "executionClass": execution_class,
                        "executionMethod": method,
                        "routingState": state,
                        "adapterCapability": capability,
                        "adapterIdentity": adapter_identity,
                        "videoGenerationRequestRef": (
                            request["generationRequestRef"] if request else None
                        ),
                        "videoGenerationRequestDigest": (
                            request["payloadDigest"] if request else None
                        ),
                        "mediaJobRef": job_ref,
                        "fallbackUsed": WAN_FALLBACK_USED,
                        "targetBoundary": target,
                    }
                )
            )
        version = len(previous) + 1
        route_ref = (
            previous[-1][1]["videoMethodRouteRef"]
            if previous
            else _required_ref(
                self._ref_factory("video-method-route-plan"),
                "videoMethodRouteRef",
            )
        )
        return _seal(
            {
                "schemaVersion": VIDEO_METHOD_ROUTE_PLAN_SCHEMA_VERSION,
                "videoMethodRouteRef": route_ref,
                "videoMethodRouteVersionRef": _required_ref(
                    self._ref_factory("video-method-route-plan-version"),
                    "videoMethodRouteVersionRef",
                ),
                "routingVersion": version,
                **scope,
                "productionRunRef": run_ref,
                "methodAwareInputPlanRef": input_plan[
                    "methodAwareInputPlanRef"
                ],
                "methodAwareInputPlanVersionRef": input_plan[
                    "methodAwareInputPlanVersionRef"
                ],
                "methodAwareInputPlanDigest": input_plan["payloadDigest"],
                "executionMethodPlanVersionRef": input_plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": input_plan[
                    "executionMethodPlanDigest"
                ],
                "capabilityRegistryVersion": METHOD_CAPABILITY_REGISTRY_VERSION,
                "capabilityRegistryDigest": METHOD_CAPABILITY_REGISTRY_DIGEST,
                "routes": routes,
                "videoGenerationRequests": requests,
                "queuedJobs": queued,
                "videoGenerationRequestCount": len(requests),
                "queuedJobCount": len(queued),
                "wanFallbackUsed": WAN_FALLBACK_USED,
                "publicationAllowed": False,
                "createdAt": now,
            }
        )

    @staticmethod
    def _validate_route_payload(value: Any) -> dict[str, Any]:
        if (
            not _sealed(value)
            or set(value) != _ROUTE_PLAN_FIELDS
            or value.get("schemaVersion") != VIDEO_METHOD_ROUTE_PLAN_SCHEMA_VERSION
            or value.get("capabilityRegistryVersion")
            != METHOD_CAPABILITY_REGISTRY_VERSION
            or value.get("capabilityRegistryDigest")
            != METHOD_CAPABILITY_REGISTRY_DIGEST
            or value.get("wanFallbackUsed") is not False
            or value.get("publicationAllowed") is not False
            or not isinstance(value.get("routes"), list)
            or not value["routes"]
            or not isinstance(value.get("videoGenerationRequests"), list)
            or not isinstance(value.get("queuedJobs"), list)
        ):
            raise RepositoryUnavailableError("stored M11 route plan is invalid")
        requests = value["videoGenerationRequests"]
        queued = value["queuedJobs"]
        request_by_ref = {
            item.get("generationRequestRef"): item
            for item in requests
            if isinstance(item, Mapping)
        }
        if len(request_by_ref) != len(requests) or any(
            not _sealed(request)
            or request.get("schemaVersion")
            != METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION
            or request.get("executionClass") != "MICRO_MOTION"
            or request.get("executionMethod") != "SINGLE_ANCHOR_I2V"
            or request.get("adapterCapability")
            != WAN_SINGLE_ANCHOR_CAPABILITY
            or request.get("executionAuthorizationState")
            != "QUEUED_NOT_EXECUTED"
            or request.get("publicationAllowed") is not False
            or "prompt" in request
            for request in requests
        ):
            raise RepositoryUnavailableError(
                "stored M11 generation request is invalid"
            )
        queued_by_request = {}
        for item in queued:
            if (
                not isinstance(item, Mapping)
                or set(item) != _QUEUED_JOB_FIELDS
                or item.get("queueState") != "QUEUED"
                or not isinstance(item.get("queueReplay"), bool)
                or not isinstance(item.get("generationRequestRef"), str)
                or not _is_digest(item.get("generationRequestDigest"))
                or not isinstance(item.get("mediaJobRef"), str)
                or item["generationRequestRef"] in queued_by_request
            ):
                raise RepositoryUnavailableError(
                    "stored M11 queue reservation is invalid"
                )
            queued_by_request[item["generationRequestRef"]] = item
        for order, route in enumerate(value["routes"], start=1):
            if (
                not _sealed(route)
                or set(route) != _VIDEO_ROUTE_FIELDS
                or route.get("schemaVersion") != VIDEO_METHOD_ROUTE_SCHEMA_VERSION
                or route.get("routeOrder") != order
                or route.get("routingState") not in _ROUTING_STATES
                or route.get("fallbackUsed") is not False
            ):
                raise RepositoryUnavailableError("stored M11 route is invalid")
            request_ref = route.get("videoGenerationRequestRef")
            if route["routingState"] == "QUEUED_EXISTING_MEDIA_JOB":
                request = request_by_ref.get(request_ref)
                reservation = queued_by_request.get(request_ref)
                if (
                    not isinstance(request, Mapping)
                    or not isinstance(reservation, Mapping)
                    or request.get("payloadDigest")
                    != route.get("videoGenerationRequestDigest")
                    or reservation.get("generationRequestDigest")
                    != request.get("payloadDigest")
                    or reservation.get("mediaJobRef") != route.get("mediaJobRef")
                    or route.get("adapterCapability")
                    != WAN_SINGLE_ANCHOR_CAPABILITY
                    or route.get("adapterIdentity")
                    != WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY
                    or not isinstance(route.get("mediaJobRef"), str)
                ):
                    raise RepositoryUnavailableError(
                        "stored M11 queued route is invalid"
                    )
            elif any(
                route.get(field) is not None
                for field in (
                    "videoGenerationRequestRef",
                    "videoGenerationRequestDigest",
                    "mediaJobRef",
                )
            ):
                raise RepositoryUnavailableError(
                    "stored M11 non-queued route contains dispatch evidence"
                )
            pair = (route.get("executionClass"), route.get("executionMethod"))
            state = route["routingState"]
            valid_route = (
                pair == ("STATIC_HOLD", "STATIC_PLATE_OR_REUSE")
                and state == "BYPASSED_STATIC_PLATE"
                and route.get("adapterCapability") is None
                and route.get("adapterIdentity") is None
            ) or (
                pair
                == (
                    "DETERMINISTIC_EVENT",
                    "V3_DETERMINISTIC_COMPOSITION",
                )
                and state == "REJECTED_DETERMINISTIC_POSTPROCESS"
                and route.get("adapterCapability") is None
                and route.get("adapterIdentity") is None
            ) or (
                pair
                in {
                    ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"),
                    (
                        "GAIT_LOCOMOTION",
                        "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
                    ),
                }
                and state == "CAPABILITY_UNAVAILABLE"
                and route.get("adapterCapability") is None
                and route.get("adapterIdentity") is None
            ) or (
                pair == ("MICRO_MOTION", "SINGLE_ANCHOR_I2V")
                and state in {"INPUT_BLOCKED", "QUEUED_EXISTING_MEDIA_JOB"}
                and route.get("adapterCapability")
                == WAN_SINGLE_ANCHOR_CAPABILITY
                and route.get("adapterIdentity")
                == WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY
            )
            if not valid_route:
                raise RepositoryUnavailableError(
                    "stored M11 route changed its method semantics"
                )
        if (
            value.get("videoGenerationRequestCount") != len(requests)
            or value.get("queuedJobCount") != len(queued)
            or len(requests) != len(queued)
        ):
            raise RepositoryUnavailableError("stored M11 route totals are invalid")
        return deepcopy(dict(value))

    def _route_records(
        self, workspace: str, run_ref: str
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result = []
        for expected, record in enumerate(
            self.evidence_repository.list_records(
                workspace, run_ref, record_kind=VIDEO_METHOD_ROUTE_RECORD_KIND
            ),
            start=1,
        ):
            payload = self._validate_route_payload(_payload(record))
            if (
                record.get("recordKind") != VIDEO_METHOD_ROUTE_RECORD_KIND
                or record.get("recordRef") != payload["videoMethodRouteRef"]
                or record.get("recordVersion") != payload["routingVersion"]
                or record.get("payloadDigest") != payload["payloadDigest"]
                or payload["routingVersion"] != expected
            ):
                raise RepositoryUnavailableError("stored M11 route envelope is invalid")
            result.append((deepcopy(dict(record)), payload))
        return result

    def route_video_methods(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != _ROUTE_FIELDS:
            raise EpisodeProductionError(
                "command fields do not match the M11 route contract"
            )
        scope, run_ref = self._scope(command)
        key = _idempotency_key(command.get("idempotencyKey"))
        input_plan = self.require_current_input_plan(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
            _required_ref(
                command.get("methodAwareInputPlanVersionRef"),
                "methodAwareInputPlanVersionRef",
            ),
        )
        request_digest = self._route_request_digest(scope, run_ref, input_plan)
        records = self._route_records(scope["workspaceRef"], run_ref)
        existing = self.evidence_repository.get_record_by_idempotency_key(
            scope["workspaceRef"], run_ref, key
        )
        if existing is not None:
            if (
                existing.get("recordKind") != VIDEO_METHOD_ROUTE_RECORD_KIND
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError("M11 route command conflicts")
            payload = self._validate_route_payload(_payload(existing))
            current = bool(records) and records[-1][1][
                "videoMethodRouteVersionRef"
            ] == payload["videoMethodRouteVersionRef"]
            return {
                **payload,
                "currentness": "CURRENT" if current else "STALE",
                "idempotentReplay": True,
            }
        execution_plan = self._current_execution_plan(
            scope, run_ref, input_plan["executionMethodPlanVersionRef"]
        )
        journal_head = self.evidence_repository.record_journal_head(
            scope["workspaceRef"], run_ref
        )
        payload = self._build_route_payload(
            scope=scope,
            run_ref=run_ref,
            input_plan=input_plan,
            execution_plan=execution_plan,
            client_key=key,
            previous=records,
        )
        record = EvidenceRecord(
            workspaceRef=scope["workspaceRef"],
            productionRunRef=run_ref,
            recordKind=VIDEO_METHOD_ROUTE_RECORD_KIND,
            recordRef=payload["videoMethodRouteRef"],
            recordVersion=payload["routingVersion"],
            idempotencyKey=key,
            requestDigest=request_digest,
            createdAt=self._clock(),
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        stored, replayed = self.evidence_repository.append_records(
            (record,), expected_record_journal_head=journal_head
        )
        result = self._validate_route_payload(_payload(stored[0]))
        return {**result, "currentness": "CURRENT", "idempotentReplay": replayed}

    def get_video_method_route(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        video_method_route_version_ref: str | None = None,
    ) -> dict[str, Any]:
        scope = {
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "projectRef": _required_ref(project_ref, "projectRef"),
            "seriesRef": _required_ref(series_ref, "seriesRef"),
            "episodeRef": _required_ref(episode_ref, "episodeRef"),
        }
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        records = self._route_records(scope["workspaceRef"], run_ref)
        if video_method_route_version_ref is None:
            selected = records[-1] if records else None
        else:
            version_ref = _required_ref(
                video_method_route_version_ref, "videoMethodRouteVersionRef"
            )
            selected = next(
                (
                    item
                    for item in records
                    if item[1]["videoMethodRouteVersionRef"] == version_ref
                ),
                None,
            )
        if selected is None or any(
            selected[1].get(field) != value for field, value in scope.items()
        ):
            raise RecordNotFoundError("VideoMethodRouteVersion was not found")
        payload = selected[1]
        current = False
        try:
            input_plan = self.require_current_input_plan(
                scope["workspaceRef"],
                scope["projectRef"],
                scope["seriesRef"],
                scope["episodeRef"],
                run_ref,
                payload["methodAwareInputPlanVersionRef"],
            )
            current = (
                selected is records[-1]
                and input_plan["payloadDigest"]
                == payload["methodAwareInputPlanDigest"]
                and payload["capabilityRegistryDigest"]
                == METHOD_CAPABILITY_REGISTRY_DIGEST
            )
        except EpisodeProductionError:
            current = False
        return {
            **payload,
            "currentness": "CURRENT" if current else "STALE",
            "idempotentReplay": False,
        }


__all__ = [
    "METHOD_AWARE_INPUT_PLAN_RECORD_KIND",
    "METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION",
    "METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION",
    "METHOD_ADAPTER_IDENTITY_REGISTRY",
    "METHOD_CAPABILITY_REGISTRY",
    "METHOD_CAPABILITY_REGISTRY_DIGEST",
    "METHOD_CAPABILITY_REGISTRY_VERSION",
    "METHOD_INPUT_PLAN_SCHEMA_VERSION",
    "METHOD_INPUT_REQUIREMENT_SCHEMA_VERSION",
    "M10M11MethodAwareMediaService",
    "VIDEO_METHOD_ROUTE_PLAN_SCHEMA_VERSION",
    "VIDEO_METHOD_ROUTE_RECORD_KIND",
    "VIDEO_METHOD_ROUTE_SCHEMA_VERSION",
    "VIDEO_METHODS",
    "WAN_SINGLE_ANCHOR_CAPABILITY",
    "WAN_FALLBACK_USED",
    "WAN_SINGLE_ANCHOR_ADAPTER_IDENTITY",
    "resolve_video_method_capability",
]
