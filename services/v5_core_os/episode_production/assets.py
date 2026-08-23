"""G4 V5 asset requirements and provider-neutral media generation requests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from .evidence import EpisodeProductionEvidenceRepository, EvidenceFact, GateAppend
from .foundation import (
    EpisodeProductionError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .shot_graph import K2ShotGraphService, ValidationFailedError


ASSET_RESOLUTION_GATE = "G4_ASSET_RESOLUTION"
ASSET_REQUIREMENT_SCHEMA_VERSION = "v5.asset-requirement.v1"
GENERATION_REQUEST_SCHEMA_VERSION = "v5.generation-request.v1"
ASSET_PLAN_SCHEMA_VERSION = "v5.asset-resolution-manifest.v1"
RESOLVER_ID = "v5.k2.asset-resolver.v1"


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _fact(gate: Mapping[str, Any], kind: str) -> dict[str, Any]:
    matches = [
        item for item in gate.get("facts", [])
        if isinstance(item, Mapping) and item.get("factKind") == kind
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("payload"), Mapping):
        raise RepositoryUnavailableError("G4 evidence fact is inconsistent")
    return deepcopy(dict(matches[0]["payload"]))


def _facts_with_prefix(
    gate: Mapping[str, Any], prefix: str
) -> list[dict[str, Any]]:
    values = [
        deepcopy(dict(item["payload"]))
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and str(item.get("factKind", "")).startswith(prefix)
        and isinstance(item.get("payload"), Mapping)
    ]
    return sorted(values, key=lambda item: item["ordinal"])


class K2AssetPipelineService:
    def __init__(
        self,
        shot_graph: K2ShotGraphService,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.shot_graph = shot_graph
        self.evidence = evidence
        self._ref_factory = ref_factory
        self._clock = clock

    def _authority_requirements(
        self,
        *,
        workspace: str,
        run_ref: str,
        graph: Mapping[str, Any],
        shots: list[Mapping[str, Any]],
        created_at: str,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for shot in shots:
            for seed in shot["assetRequirementSeeds"]:
                key = seed["requirementKey"]
                semantic = {
                    field: seed[field]
                    for field in (
                        "requirementKey", "requirementType", "authorityRef",
                        "authorityVersionRef", "authorityDigest", "required",
                    )
                }
                existing = grouped.get(key)
                if existing is None:
                    grouped[key] = {
                        "semantic": semantic,
                        "creativeShotRefs": [shot["creativeShotRef"]],
                        "creativeShotVersionRefs": [shot["creativeShotVersionRef"]],
                    }
                elif existing["semantic"] != semantic:
                    raise ValidationFailedError(
                        "one asset requirement key resolves to conflicting authority"
                    )
                else:
                    existing["creativeShotRefs"].append(shot["creativeShotRef"])
                    existing["creativeShotVersionRefs"].append(
                        shot["creativeShotVersionRef"]
                    )
        requirements: list[dict[str, Any]] = []
        for ordinal, key in enumerate(sorted(grouped), start=1):
            item = grouped[key]
            requirements.append(
                _sealed(
                    {
                        "schemaVersion": ASSET_REQUIREMENT_SCHEMA_VERSION,
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "assetRequirementRef": _required_ref(
                            self._ref_factory("asset-requirement"),
                            "assetRequirementRef",
                        ),
                        "version": 1,
                        "ordinal": ordinal,
                        **item["semantic"],
                        "creativeShotRefs": item["creativeShotRefs"],
                        "creativeShotVersionRefs": item[
                            "creativeShotVersionRefs"
                        ],
                        "executableShotGraphVersionRef": graph[
                            "executableShotGraphVersionRef"
                        ],
                        "executableShotGraphDigest": graph["payloadDigest"],
                        "resolutionState": "RESOLVED_AUTHORITY",
                        "resolutionKind": "IMMUTABLE_AUTHORITY_REFERENCE",
                        "provenance": "ACCEPTED_UPSTREAM_AUTHORITY",
                        "rightsState": "INHERITED_RESTRICTED",
                        "publicationAllowed": False,
                        "createdBy": RESOLVER_ID,
                        "createdAt": created_at,
                    }
                )
            )
        return requirements

    def _media_requirements_and_requests(
        self,
        *,
        workspace: str,
        run_ref: str,
        graph: Mapping[str, Any],
        shots: list[Mapping[str, Any]],
        first_ordinal: int,
        created_at: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        requirements: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        output = graph["output"]
        ordinal = first_ordinal
        for shot in shots:
            seed_keys = sorted(
                seed["requirementKey"] for seed in shot["assetRequirementSeeds"]
            )
            for media_kind in ("video", "audio"):
                requirement_ref = _required_ref(
                    self._ref_factory("asset-requirement"),
                    "assetRequirementRef",
                )
                media_type = "video/mp4" if media_kind == "video" else "audio/wav"
                requirement = _sealed(
                    {
                        "schemaVersion": ASSET_REQUIREMENT_SCHEMA_VERSION,
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "assetRequirementRef": requirement_ref,
                        "version": 1,
                        "ordinal": ordinal,
                        "requirementKey": (
                            f"shot-{media_kind}:{shot['creativeShotRef']}"
                        ),
                        "requirementType": f"shot-{media_kind}",
                        "required": True,
                        "mediaType": media_type,
                        "creativeShotRef": shot["creativeShotRef"],
                        "creativeShotVersionRef": shot[
                            "creativeShotVersionRef"
                        ],
                        "creativeShotDigest": shot["payloadDigest"],
                        "upstreamAuthorityRequirementKeys": seed_keys,
                        "executableShotGraphVersionRef": graph[
                            "executableShotGraphVersionRef"
                        ],
                        "executableShotGraphDigest": graph["payloadDigest"],
                        "resolutionState": "GENERATION_REQUESTED",
                        "resolutionKind": "V4_ADAPTER_REQUIRED",
                        "requestedProvenance": "LOCAL_EVIDENCE",
                        "rightsState": "LOCAL_EVIDENCE_ONLY",
                        "publicationAllowed": False,
                        "createdBy": RESOLVER_ID,
                        "createdAt": created_at,
                    }
                )
                parameters: dict[str, Any] = {
                    "durationFrames": shot["durationFrames"],
                    "frameRate": shot["frameRate"],
                }
                if media_kind == "video":
                    parameters.update(
                        {
                            "width": output["width"],
                            "height": output["height"],
                            "container": "mp4",
                            "videoCodec": "h264",
                            "pixelFormat": "yuv420p",
                            "visualSeedDigest": _digest(
                                {
                                    "camera": shot["cameraInstruction"],
                                    "action": shot["action"],
                                    "identities": shot[
                                        "requiredCharacterIdentityLocks"
                                    ],
                                    "requirements": shot[
                                        "assetRequirementSeeds"
                                    ],
                                }
                            ),
                        }
                    )
                    capability = "deterministic-local-video-v1"
                else:
                    parameters.update(
                        {
                            "sampleRate": 48_000,
                            "channels": 2,
                            "sampleFormat": "s16",
                            "container": "wav",
                            "toneFrequencyHz": 220 + shot["globalOrder"] * 55,
                            "speechSynthesis": False,
                        }
                    )
                    capability = "deterministic-local-audio-v1"
                request = _sealed(
                    {
                        "schemaVersion": GENERATION_REQUEST_SCHEMA_VERSION,
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "generationRequestRef": _required_ref(
                            self._ref_factory("generation-request"),
                            "generationRequestRef",
                        ),
                        "generationRequestVersionRef": _required_ref(
                            self._ref_factory("generation-request-version"),
                            "generationRequestVersionRef",
                        ),
                        "version": 1,
                        "ordinal": ordinal - first_ordinal + 1,
                        "assetRequirementRef": requirement_ref,
                        "assetRequirementDigest": requirement["payloadDigest"],
                        "creativeShotRef": shot["creativeShotRef"],
                        "creativeShotVersionRef": shot[
                            "creativeShotVersionRef"
                        ],
                        "creativeShotDigest": shot["payloadDigest"],
                        "mediaKind": media_kind,
                        "mediaType": media_type,
                        "adapterCapability": capability,
                        "providerSelection": "UNSELECTED",
                        "parameters": parameters,
                        "state": "READY_FOR_DISPATCH",
                        "requestedProvenance": "LOCAL_EVIDENCE",
                        "publicationAllowed": False,
                        "createdBy": RESOLVER_ID,
                        "createdAt": created_at,
                    }
                )
                requirements.append(requirement)
                requests.append(request)
                ordinal += 1
        return requirements, requests

    @staticmethod
    def _validate_plan(
        graph: Mapping[str, Any],
        requirements: list[Mapping[str, Any]],
        requests: list[Mapping[str, Any]],
    ) -> None:
        requirement_refs = {
            item.get("assetRequirementRef"): item for item in requirements
        }
        if (
            len(requirement_refs) != len(requirements)
            or any(ref is None for ref in requirement_refs)
            or any(
                item.get("resolutionState")
                not in {"RESOLVED_AUTHORITY", "GENERATION_REQUESTED"}
                for item in requirements
            )
        ):
            raise ValidationFailedError("asset requirements are incomplete")
        request_refs = [item.get("generationRequestRef") for item in requests]
        if len(request_refs) != len(set(request_refs)) or any(
            item.get("state") != "READY_FOR_DISPATCH"
            or item.get("providerSelection") != "UNSELECTED"
            or item.get("publicationAllowed") is not False
            or item.get("assetRequirementRef") not in requirement_refs
            or requirement_refs[item["assetRequirementRef"]].get(
                "payloadDigest"
            )
            != item.get("assetRequirementDigest")
            for item in requests
        ):
            raise ValidationFailedError("generation requests are inconsistent")
        shot_refs = {item["creativeShotRef"] for item in graph["shots"]}
        requested_pairs = {
            (item.get("creativeShotRef"), item.get("mediaKind"))
            for item in requests
        }
        if requested_pairs != {
            (shot_ref, kind) for shot_ref in shot_refs for kind in ("video", "audio")
        }:
            raise ValidationFailedError("every shot requires video and audio media")

    def resolve_assets(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey"
        }:
            raise EpisodeProductionError("command fields do not match the G4 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        verified = self.shot_graph.verify_shot_graph_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        shots = verified["creativeShotVersions"]
        created_at = self._clock()
        authority_requirements = self._authority_requirements(
            workspace=workspace,
            run_ref=run_ref,
            graph=graph,
            shots=shots,
            created_at=created_at,
        )
        media_requirements, requests = self._media_requirements_and_requests(
            workspace=workspace,
            run_ref=run_ref,
            graph=graph,
            shots=shots,
            first_ordinal=len(authority_requirements) + 1,
            created_at=created_at,
        )
        requirements = authority_requirements + media_requirements
        self._validate_plan(graph, requirements, requests)
        manifest = _sealed(
            {
                "schemaVersion": ASSET_PLAN_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "assetResolutionManifestRef": _required_ref(
                    self._ref_factory("asset-resolution-manifest"),
                    "assetResolutionManifestRef",
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "assetRequirementRefs": [
                    item["assetRequirementRef"] for item in requirements
                ],
                "generationRequestRefs": [
                    item["generationRequestRef"] for item in requests
                ],
                "summary": {
                    "requirements": len(requirements),
                    "resolvedAuthority": len(authority_requirements),
                    "generationRequested": len(media_requirements),
                    "blocked": 0,
                    "generationRequests": len(requests),
                },
                "state": "READY_FOR_V4_DISPATCH",
                "provenance": "LOCAL_EVIDENCE",
                "publicationAllowed": False,
                "createdBy": RESOLVER_ID,
                "createdAt": created_at,
            }
        )
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "rootPayloadDigest": root["payloadDigest"],
                "shotGraphDigest": graph["payloadDigest"],
                "resolverId": RESOLVER_ID,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"AssetRequirement:{item['ordinal']:04d}",
                item["assetRequirementRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in requirements
        ) + tuple(
            EvidenceFact(
                f"GenerationRequest:{item['ordinal']:04d}",
                item["generationRequestVersionRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in requests
        ) + (
            EvidenceFact(
                "AssetResolutionManifest",
                manifest["assetResolutionManifestRef"],
                1,
                manifest,
                manifest["payloadDigest"],
            ),
        )
        gate, replay = self.evidence.append_gate(
            GateAppend(
                workspace,
                run_ref,
                ASSET_RESOLUTION_GATE,
                _digest({"clientIdempotencyKey": client_key, "stage": "assets"}),
                root["payloadDigest"],
                request_digest,
                "SHOTS_COMPILED",
                "ASSETS_READY",
                created_at,
                facts,
            )
        )
        return {**self._bundle(gate), "idempotentReplay": replay}

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "assetResolutionManifest": _fact(gate, "AssetResolutionManifest"),
            "assetRequirements": _facts_with_prefix(gate, "AssetRequirement:"),
            "generationRequests": _facts_with_prefix(gate, "GenerationRequest:"),
            "state": gate["toState"],
        }

    def get_asset_plan(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        self.shot_graph.root_service.get_run(workspace_ref, production_run_ref)
        gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, ASSET_RESOLUTION_GATE
        )
        if gate is None:
            raise UpstreamNotReadyError("G4 asset plan is not ready")
        return self._bundle(gate)

    def verify_asset_plan_current(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        verified = self.shot_graph.verify_shot_graph_current(
            workspace_ref, production_run_ref
        )
        bundle = self.get_asset_plan(workspace_ref, production_run_ref)
        graph = verified["executableShotGraph"]
        manifest = bundle["assetResolutionManifest"]
        if (
            manifest.get("rootPayloadDigest")
            != verified["root"]["payloadDigest"]
            or manifest.get("executableShotGraphDigest")
            != graph["payloadDigest"]
            or manifest.get("state") != "READY_FOR_V4_DISPATCH"
            or manifest.get("publicationAllowed") is not False
        ):
            raise StaleInputError("G4 asset plan lineage is stale")
        self._validate_plan(
            graph, bundle["assetRequirements"], bundle["generationRequests"]
        )
        if (
            manifest.get("assetRequirementRefs")
            != [item["assetRequirementRef"] for item in bundle["assetRequirements"]]
            or manifest.get("generationRequestRefs")
            != [item["generationRequestRef"] for item in bundle["generationRequests"]]
        ):
            raise StaleInputError("G4 manifest contents are stale")
        return {**verified, **bundle}
