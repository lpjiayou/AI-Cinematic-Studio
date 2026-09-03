"""Test-only construction of immutable pre-cutover K2 G4/G5 history.

Production entry points cannot create these facts after the method-aware
cutover.  Older tests still need representative, byte-valid history to prove
that downstream readers and exact replay remain compatible, so this helper
uses the frozen v1 builders directly against an isolated test repository.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from services.v5_core_os.episode_production.assets import (
    ASSET_PLAN_SCHEMA_VERSION,
    ASSET_RESOLUTION_GATE,
    RESOLVER_ID,
    _sealed as _sealed_asset,
)
from services.v5_core_os.episode_production.audio import (
    reject_speech_synthesis_in_legacy_media,
)
from services.v5_core_os.episode_production.evidence import EvidenceFact, GateAppend
from services.v5_core_os.episode_production.foundation import (
    _digest,
    _idempotency_key,
    _required_ref,
)
from services.v5_core_os.episode_production.media import (
    ADMISSION_ID,
    ASSET_VERSION_SCHEMA_VERSION,
    GENERATION_RESULT_SCHEMA_VERSION,
    MEDIA_EXECUTION_GATE,
    MEDIA_MANIFEST_SCHEMA_VERSION,
    _sealed as _sealed_media,
)
from services.v5_core_os.episode_production.shot_graph import (
    require_legacy_executable_graph,
)


def _assets(boundary):
    return boundary._EpisodeProductionPublicBoundary__assets


def _media(boundary):
    return boundary._EpisodeProductionPublicBoundary__media


def seed_legacy_g4(boundary, command: Mapping[str, Any]) -> dict[str, Any]:
    """Append one historic G4 gate in an isolated test repository."""

    service = _assets(boundary)
    workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
    run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
    client_key = _idempotency_key(command.get("idempotencyKey"))
    existing = service.evidence.get_gate(workspace, run_ref, ASSET_RESOLUTION_GATE)
    if existing is not None:
        return {**service._bundle(existing), "idempotentReplay": True}
    verified = service.shot_graph.verify_shot_graph_current(workspace, run_ref)
    root = verified["root"]
    graph = verified["executableShotGraph"]
    shots = verified["creativeShotVersions"]
    require_legacy_executable_graph(graph)
    created_at = service._clock()
    authority_requirements = service._authority_requirements(
        workspace=workspace,
        run_ref=run_ref,
        graph=graph,
        shots=shots,
        created_at=created_at,
    )
    media_requirements, requests = service._media_requirements_and_requests(
        workspace=workspace,
        run_ref=run_ref,
        graph=graph,
        shots=shots,
        first_ordinal=len(authority_requirements) + 1,
        created_at=created_at,
    )
    requirements = authority_requirements + media_requirements
    service._validate_plan(graph, requirements, requests)
    manifest = _sealed_asset(
        {
            "schemaVersion": ASSET_PLAN_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "assetResolutionManifestRef": _required_ref(
                service._ref_factory("asset-resolution-manifest"),
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
    gate, replay = service.evidence.append_gate(
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
    return {**service._bundle(gate), "idempotentReplay": replay}


def seed_legacy_g5(boundary, command: Mapping[str, Any]) -> dict[str, Any]:
    """Execute and append one pre-cutover G5 history fixture."""

    service = _media(boundary)
    workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
    run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
    client_key = _idempotency_key(command.get("idempotencyKey"))
    existing = service.evidence.get_gate(workspace, run_ref, MEDIA_EXECUTION_GATE)
    if existing is not None:
        return {
            **service._bundle(existing),
            "jobs": service.list_jobs(workspace, run_ref),
            "idempotentReplay": True,
        }
    verified = service.assets.verify_asset_plan_current(workspace, run_ref)
    root = verified["root"]
    graph = verified["executableShotGraph"]
    require_legacy_executable_graph(graph)
    asset_manifest = verified["assetResolutionManifest"]
    requests = verified["generationRequests"]
    reject_speech_synthesis_in_legacy_media(requests)
    jobs = service.execution.execute_batch(
        workspace,
        run_ref,
        requests,
        batch_idempotency_key=client_key,
    )
    jobs_by_request = {
        job["request"]["generationRequestRef"]: job for job in jobs
    }
    now = service._clock()
    results = []
    asset_versions = []
    for ordinal, generation_request in enumerate(requests, start=1):
        job = jobs_by_request[generation_request["generationRequestRef"]]
        artifact, _ = service._verify_handoff(job, generation_request)
        accepted_attempt = job["attempts"][-1]
        result = _sealed_media(
            {
                "schemaVersion": GENERATION_RESULT_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "generationResultRef": _required_ref(
                    service._ref_factory("generation-result"),
                    "generationResultRef",
                ),
                "version": 1,
                "ordinal": ordinal,
                "generationRequestRef": generation_request[
                    "generationRequestRef"
                ],
                "generationRequestVersionRef": generation_request[
                    "generationRequestVersionRef"
                ],
                "generationRequestDigest": generation_request["payloadDigest"],
                "jobRef": job["jobRef"],
                "attemptRef": accepted_attempt["attemptRef"],
                "attemptNumber": accepted_attempt["attemptNumber"],
                "adapterIdentity": artifact["adapterIdentity"],
                "parameters": deepcopy(generation_request["parameters"]),
                "mediaKind": generation_request["mediaKind"],
                "mediaType": generation_request["mediaType"],
                "artifactSha256": artifact["sha256"],
                "artifactByteSize": artifact["byteSize"],
                "probe": deepcopy(artifact["probe"]),
                "state": "VERIFIED",
                "provenance": "LOCAL_EVIDENCE",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "gpuUsed": False,
                "publicationAllowed": False,
                "createdBy": ADMISSION_ID,
                "createdAt": now,
            }
        )
        asset_version = _sealed_media(
            {
                "schemaVersion": ASSET_VERSION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "assetRef": _required_ref(
                    service._ref_factory("generated-asset"), "assetRef"
                ),
                "assetVersionRef": _required_ref(
                    service._ref_factory("generated-asset-version"),
                    "assetVersionRef",
                ),
                "version": 1,
                "ordinal": ordinal,
                "assetRequirementRef": generation_request[
                    "assetRequirementRef"
                ],
                "generationRequestRef": generation_request[
                    "generationRequestRef"
                ],
                "generationRequestVersionRef": generation_request[
                    "generationRequestVersionRef"
                ],
                "generationRequestDigest": generation_request["payloadDigest"],
                "generationResultRef": result["generationResultRef"],
                "generationResultDigest": result["payloadDigest"],
                "creativeShotRef": generation_request["creativeShotRef"],
                "creativeShotVersionRef": generation_request[
                    "creativeShotVersionRef"
                ],
                "creativeShotDigest": generation_request["creativeShotDigest"],
                "mediaKind": generation_request["mediaKind"],
                "mediaType": generation_request["mediaType"],
                "storageKey": artifact["storageKey"],
                "byteSize": artifact["byteSize"],
                "sha256": artifact["sha256"],
                "probe": deepcopy(artifact["probe"]),
                "adapterIdentity": artifact["adapterIdentity"],
                "provenance": "LOCAL_EVIDENCE",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "state": "REGISTERED",
                "publicationAllowed": False,
                "createdBy": ADMISSION_ID,
                "createdAt": now,
            }
        )
        results.append(result)
        asset_versions.append(asset_version)
    manifest = _sealed_media(
        {
            "schemaVersion": MEDIA_MANIFEST_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "mediaManifestRef": _required_ref(
                service._ref_factory("media-manifest"), "mediaManifestRef"
            ),
            "version": 1,
            "rootPayloadDigest": root["payloadDigest"],
            "executableShotGraphVersionRef": graph[
                "executableShotGraphVersionRef"
            ],
            "executableShotGraphDigest": graph["payloadDigest"],
            "assetResolutionManifestRef": asset_manifest[
                "assetResolutionManifestRef"
            ],
            "assetResolutionManifestDigest": asset_manifest["payloadDigest"],
            "generationResultRefs": [item["generationResultRef"] for item in results],
            "assetVersionRefs": [item["assetVersionRef"] for item in asset_versions],
            "summary": {
                "requested": len(requests),
                "verifiedResults": len(results),
                "registeredAssets": len(asset_versions),
                "videoAssets": sum(
                    item["mediaKind"] == "video" for item in asset_versions
                ),
                "audioAssets": sum(
                    item["mediaKind"] == "audio" for item in asset_versions
                ),
                "failed": 0,
            },
            "state": "MEDIA_VERIFIED",
            "executionScope": "SINGLE_EPISODE",
            "provenance": "LOCAL_EVIDENCE",
            "gpuUsed": False,
            "publicationAllowed": False,
            "createdBy": ADMISSION_ID,
            "createdAt": now,
        }
    )
    facts = tuple(
        EvidenceFact(
            f"GenerationResult:{item['ordinal']:04d}",
            item["generationResultRef"],
            1,
            item,
            item["payloadDigest"],
        )
        for item in results
    ) + tuple(
        EvidenceFact(
            f"AssetVersion:{item['ordinal']:04d}",
            item["assetVersionRef"],
            1,
            item,
            item["payloadDigest"],
        )
        for item in asset_versions
    ) + (
        EvidenceFact(
            "MediaManifest",
            manifest["mediaManifestRef"],
            1,
            manifest,
            manifest["payloadDigest"],
        ),
    )
    gate, replay = service.evidence.append_gate(
        GateAppend(
            workspace,
            run_ref,
            MEDIA_EXECUTION_GATE,
            _digest({"clientIdempotencyKey": client_key, "stage": "media"}),
            root["payloadDigest"],
            _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "rootPayloadDigest": root["payloadDigest"],
                    "assetPlanDigest": asset_manifest["payloadDigest"],
                    "generationRequestDigests": [
                        item["payloadDigest"] for item in requests
                    ],
                    "admissionId": ADMISSION_ID,
                }
            ),
            "ASSETS_READY",
            "MEDIA_READY",
            now,
            facts,
        )
    )
    return {
        **service._bundle(gate),
        "jobs": service.list_jobs(workspace, run_ref),
        "idempotentReplay": replay,
    }
