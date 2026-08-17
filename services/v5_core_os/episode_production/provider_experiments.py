"""P1 live-provider experiments on the existing K2 production lineage.

The service binds a current V5 rights/policy bundle and an existing M9 generation
request to the existing V4 job boundary.  A successful provider response remains an
untrusted, unselected candidate.  It cannot create an AssetVersion, advance the K2
gate journal, satisfy a human decision or allow publication.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from services.v4_platform import (
    ArtifactVerificationError as V4ArtifactVerificationError,
    COMFYUI_ADAPTER_ID,
    COMFYUI_CAPABILITY,
    MediaJobError as V4MediaJobError,
    verify_media_against_request,
)

from .assets import K2AssetPipelineService
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .media import MediaExecutionPort, RejectingMediaExecution
from .production_policy import (
    K2ProductionPolicyService,
    ProductionPolicyRequiredError,
)


EXPERIMENT_REQUEST_SCHEMA_VERSION = "v5.provider-experiment-request.v1"
EXPERIMENT_CANDIDATE_SCHEMA_VERSION = "v5.provider-experiment-candidate.v1"
EXPERIMENT_PROFILE_ID = "k2.wan22-ti2v.p1-smoke.v1"
EXPERIMENT_SERVICE_ID = "v5.k2.provider-experiment.v1"


class ProviderExperimentUnavailableError(EpisodeProductionError):
    code = "worker_unavailable"


class ProviderCandidateRejectedError(EpisodeProductionError):
    code = "artifact_verification_failed"


@dataclass(frozen=True, slots=True)
class ProviderExperimentRecord:
    workspaceRef: str
    productionRunRef: str
    experimentRef: str
    idempotencyKey: str
    requestDigest: str
    payloadJson: str
    payloadDigest: str
    createdAt: str


class ProviderExperimentRepository(Protocol):
    persistence_class: str

    def create(
        self, record: ProviderExperimentRecord
    ) -> ProviderExperimentRecord: ...

    def get_by_idempotency(
        self, workspace_ref: str, run_ref: str, idempotency_key: str
    ) -> ProviderExperimentRecord | None: ...

    def list(
        self, workspace_ref: str, run_ref: str
    ) -> list[ProviderExperimentRecord]: ...


class InMemoryProviderExperimentAdapter:
    persistence_class = "PROCESS_LOCAL"

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], ProviderExperimentRecord] = {}
        self._lock = RLock()

    def create(self, record: ProviderExperimentRecord) -> ProviderExperimentRecord:
        key = (record.workspaceRef, record.productionRunRef, record.idempotencyKey)
        with self._lock:
            if key in self._records:
                raise IdempotencyConflictError("provider experiment already exists")
            self._records[key] = record
            return record

    def get_by_idempotency(
        self, workspace_ref: str, run_ref: str, idempotency_key: str
    ) -> ProviderExperimentRecord | None:
        with self._lock:
            return self._records.get((workspace_ref, run_ref, idempotency_key))

    def list(
        self, workspace_ref: str, run_ref: str
    ) -> list[ProviderExperimentRecord]:
        with self._lock:
            records = [
                record
                for (workspace, run, _), record in self._records.items()
                if workspace == workspace_ref and run == run_ref
            ]
        return sorted(records, key=lambda item: (item.createdAt, item.experimentRef))


class SqliteProviderExperimentAdapter:
    """Additive P1 evidence store; explicitly not the P2 production store."""

    persistence_class = "LOCAL_SQLITE_EXPERIMENT_EVIDENCE"
    _TABLES = {
        "v5_provider_experiment_schema",
        "v5_provider_experiments",
    }
    _COLUMNS = {
        "v5_provider_experiment_schema": ("component", "schema_version"),
        "v5_provider_experiments": (
            "workspace_ref", "production_run_ref", "experiment_ref",
            "idempotency_key", "request_digest", "payload_json",
            "payload_digest", "created_at",
        ),
    }

    def __init__(
        self, database_path: Path | str, *, initialize_if_missing: bool = True
    ) -> None:
        self.path = Path(database_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists() and self.path.stat().st_size > 0
        if not existed and not initialize_if_missing:
            raise RepositoryUnavailableError(
                "provider experiment initialization is required"
            )
        connection = self._connect()
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE v5_provider_experiment_schema ("
                    "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO v5_provider_experiment_schema VALUES "
                    "('provider_experiments',1)"
                )
                connection.execute(
                    "CREATE TABLE v5_provider_experiments ("
                    "workspace_ref TEXT NOT NULL, production_run_ref TEXT NOT NULL, "
                    "experiment_ref TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
                    "request_digest TEXT NOT NULL, payload_json TEXT NOT NULL, "
                    "payload_digest TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_ref,production_run_ref,experiment_ref), "
                    "UNIQUE(workspace_ref,production_run_ref,idempotency_key))"
                )
                connection.commit()
                tables = set(self._TABLES)
            if tables != self._TABLES:
                raise RepositoryUnavailableError(
                    "provider experiment schema is unsupported"
                )
            for table, expected in self._COLUMNS.items():
                actual = tuple(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if actual != expected:
                    raise RepositoryUnavailableError(
                        "provider experiment columns are unsupported"
                    )
            marker = connection.execute(
                "SELECT component,schema_version FROM v5_provider_experiment_schema"
            ).fetchall()
            if [tuple(row) for row in marker] != [("provider_experiments", 1)]:
                raise RepositoryUnavailableError(
                    "provider experiment marker is unsupported"
                )
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RepositoryUnavailableError(
                    "provider experiment integrity check failed"
                )
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError(
                "provider experiment database is unavailable"
            ) from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @staticmethod
    def _record(row: sqlite3.Row) -> ProviderExperimentRecord:
        return ProviderExperimentRecord(
            row["workspace_ref"], row["production_run_ref"],
            row["experiment_ref"], row["idempotency_key"],
            row["request_digest"], row["payload_json"],
            row["payload_digest"], row["created_at"],
        )

    def create(self, record: ProviderExperimentRecord) -> ProviderExperimentRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO v5_provider_experiments VALUES (?,?,?,?,?,?,?,?)",
                (
                    record.workspaceRef, record.productionRunRef,
                    record.experimentRef, record.idempotencyKey,
                    record.requestDigest, record.payloadJson,
                    record.payloadDigest, record.createdAt,
                ),
            )
            connection.commit()
            return record
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise IdempotencyConflictError(
                "provider experiment already exists"
            ) from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError(
                "provider experiment database is unavailable"
            ) from exc
        finally:
            connection.close()

    def get_by_idempotency(
        self, workspace_ref: str, run_ref: str, idempotency_key: str
    ) -> ProviderExperimentRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_provider_experiments WHERE workspace_ref=? "
                "AND production_run_ref=? AND idempotency_key=?",
                (workspace_ref, run_ref, idempotency_key),
            ).fetchone()
            return None if row is None else self._record(row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError(
                "provider experiment database is unavailable"
            ) from exc
        finally:
            connection.close()

    def list(
        self, workspace_ref: str, run_ref: str
    ) -> list[ProviderExperimentRecord]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM v5_provider_experiments WHERE workspace_ref=? "
                "AND production_run_ref=? ORDER BY created_at,experiment_ref",
                (workspace_ref, run_ref),
            ).fetchall()
            return [self._record(row) for row in rows]
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError(
                "provider experiment database is unavailable"
            ) from exc
        finally:
            connection.close()


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = _digest(result)
    return result


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


class K2ProviderExperimentService:
    def __init__(
        self,
        assets: K2AssetPipelineService,
        production_policy: K2ProductionPolicyService,
        repository: ProviderExperimentRepository,
        execution: MediaExecutionPort | None,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.assets = assets
        self.production_policy = production_policy
        self.repository = repository
        self.execution = execution or RejectingMediaExecution()
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _decode(record: ProviderExperimentRecord) -> dict[str, Any]:
        try:
            payload = json.loads(record.payloadJson)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RepositoryUnavailableError(
                "provider experiment payload is invalid"
            ) from exc
        if not isinstance(payload, dict) or _digest(payload) != record.payloadDigest:
            raise RepositoryUnavailableError(
                "provider experiment record digest verification failed"
            )
        embedded = payload.get("payloadDigest")
        unsigned = dict(payload)
        unsigned.pop("payloadDigest", None)
        if embedded != _digest(unsigned):
            raise RepositoryUnavailableError(
                "provider experiment embedded digest verification failed"
            )
        return payload

    @staticmethod
    def _public(candidate: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(candidate))
        value.pop("artifactStorageKey", None)
        value["artifactAvailable"] = True
        value["projectionClass"] = "PUBLIC_SAFE_PROVIDER_EXPERIMENT"
        return value

    @staticmethod
    def _select_source(
        verified: Mapping[str, Any], source_ref: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        requests = [
            item for item in verified["generationRequests"]
            if item.get("generationRequestRef") == source_ref
        ]
        if len(requests) != 1 or requests[0].get("mediaKind") != "video":
            raise UpstreamNotReadyError(
                "source video generation request is unavailable"
            )
        source = requests[0]
        shots = [
            item for item in verified["creativeShotVersions"]
            if item.get("creativeShotVersionRef")
            == source.get("creativeShotVersionRef")
        ]
        if len(shots) != 1:
            raise StaleInputError("source creative shot is stale")
        return source, shots[0]

    @staticmethod
    def _select_provider(
        policy: Mapping[str, Any], capability_ref: str
    ) -> Mapping[str, Any]:
        executions = [
            item
            for item in policy["providerExecutionPolicy"]["allowedExecutions"]
            if item.get("mediaKind") == "video"
            and item.get("providerCapabilityRef") == capability_ref
        ]
        if len(executions) != 1:
            raise ProductionPolicyRequiredError(
                "one exact approved video provider capability is required"
            )
        execution = executions[0]
        if (
            execution.get("gpuAttestationRequired") is not True
            or not execution.get("credentialSourceRef")
            or not execution.get("usageTermsRef")
            or not execution.get("budgetAuthorityRef")
            or not execution.get("runtimeAttestationRef")
            or not execution.get("runtimeAttestationDigest")
        ):
            raise ProductionPolicyRequiredError(
                "video provider execution authority is incomplete"
            )
        return execution

    @staticmethod
    def _profile(
        production_policy: Mapping[str, Any], source: Mapping[str, Any]
    ) -> dict[str, Any]:
        width = max(32, min(640, int(production_policy["width"])))
        width -= width % 32
        proportional = width * int(production_policy["height"]) / int(
            production_policy["width"]
        )
        height = max(32, int(round(proportional / 32)) * 32)
        return {
            "profileId": EXPERIMENT_PROFILE_ID,
            "durationFrames": 49,
            "frameRate": int(production_policy["frameRate"]),
            "width": width,
            "height": height,
            "negativePrompt": (
                "text, watermark, logo, subtitles, malformed anatomy, duplicate "
                "subject, temporal flicker, abrupt camera jump"
            ),
            "seed": int(source["payloadDigest"][:16], 16),
            "steps": 20,
            "cfg": 5.0,
            "samplerName": "uni_pc",
            "scheduler": "simple",
            "modelShift": 8.0,
        }

    @staticmethod
    def _prompt(shot: Mapping[str, Any]) -> str:
        identities = [
            str(item.get("scriptCharacterName") or item.get("characterRef"))
            for item in shot.get("requiredCharacterIdentityLocks", [])
            if isinstance(item, Mapping)
        ]
        camera = json.dumps(
            shot.get("cameraInstruction", {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        continuity = "; ".join(
            str(item) for item in shot.get("continuityConstraints", [])[:6]
        )
        prompt = (
            "Cinematic production experiment. "
            f"Action: {shot.get('action', '')}. "
            f"Characters: {', '.join(identities) or 'none'}. "
            f"Camera: {camera}. "
            f"Continuity: {continuity}. "
            "Natural coherent motion, stable identity, cinematic lighting, no text."
        )
        return prompt[:4000].strip()

    def _request(
        self,
        *,
        verified: Mapping[str, Any],
        policy: Mapping[str, Any],
        source: Mapping[str, Any],
        shot: Mapping[str, Any],
        provider: Mapping[str, Any],
        request_fingerprint: str,
    ) -> dict[str, Any]:
        production = policy["productionPolicy"]
        rights = policy["rightsManifest"]
        provider_policy = policy["providerExecutionPolicy"]
        profile = self._profile(production, source)
        parameters = {
            key: value for key, value in profile.items() if key != "profileId"
        }
        parameters["prompt"] = self._prompt(shot)
        request_ref = f"provider-generation-request-{request_fingerprint[:32]}"
        return _sealed(
            {
                "schemaVersion": EXPERIMENT_REQUEST_SCHEMA_VERSION,
                "workspaceRef": source["workspaceRef"],
                "productionRunRef": source["productionRunRef"],
                "generationRequestRef": request_ref,
                "generationRequestVersionRef": f"{request_ref}-v1",
                "version": 1,
                "ordinal": 1,
                "sourceGenerationRequestRef": source["generationRequestRef"],
                "sourceGenerationRequestDigest": source["payloadDigest"],
                "assetRequirementRef": source["assetRequirementRef"],
                "assetRequirementDigest": source["assetRequirementDigest"],
                "creativeShotRef": source["creativeShotRef"],
                "creativeShotVersionRef": source["creativeShotVersionRef"],
                "creativeShotDigest": source["creativeShotDigest"],
                "assetResolutionManifestDigest": verified[
                    "assetResolutionManifest"
                ]["payloadDigest"],
                "productionPolicyBundleRef": policy[
                    "productionPolicyBundleRef"
                ],
                "productionPolicyBundleDigest": policy["payloadDigest"],
                "mediaKind": "video",
                "mediaType": "video/mp4",
                "adapterCapability": COMFYUI_CAPABILITY,
                "providerSelection": {
                    "providerId": provider["providerId"],
                    "modelId": provider["modelId"],
                    "region": provider["region"],
                    "endpointClass": provider["endpointClass"],
                    "providerCapabilityRef": provider["providerCapabilityRef"],
                    "providerExecutionPolicyRef": provider_policy[
                        "providerExecutionPolicyRef"
                    ],
                    "providerExecutionPolicyDigest": provider_policy[
                        "payloadDigest"
                    ],
                    "rightsManifestRef": rights["rightsManifestRef"],
                    "rightsManifestDigest": rights["payloadDigest"],
                    "productionPolicyRef": production["productionPolicyRef"],
                    "productionPolicyDigest": production["payloadDigest"],
                    "credentialSourceRef": provider["credentialSourceRef"],
                    "usageTermsRef": provider["usageTermsRef"],
                    "budgetAuthorityRef": provider["budgetAuthorityRef"],
                    "runtimeAttestationRef": provider[
                        "runtimeAttestationRef"
                    ],
                    "runtimeAttestationDigest": provider[
                        "runtimeAttestationDigest"
                    ],
                    "costCurrency": production["currency"],
                    "maxCostMinor": provider["maxCostMinor"],
                    "timeoutSeconds": provider["timeoutSeconds"],
                },
                "parameters": parameters,
                "experimentProfileId": profile["profileId"],
                "state": "READY_FOR_DISPATCH",
                "requestedProvenance": "LIVE_PROVIDER",
                "experimentOnly": True,
                "publicationAllowed": False,
            }
        )

    def _verify_job(
        self,
        job: Mapping[str, Any],
        request: Mapping[str, Any],
        provider: Mapping[str, Any],
        production_policy: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Mapping[str, Any]]:
        artifact = job.get("artifact")
        if (
            job.get("state") != "SUCCEEDED"
            or job.get("requestDigest") != request["payloadDigest"]
            or job.get("request", {}).get("generationRequestRef")
            != request["generationRequestRef"]
            or not isinstance(artifact, Mapping)
        ):
            raise ProviderCandidateRejectedError(
                "V4 provider experiment handoff is inconsistent"
            )
        root = Path(self.execution.artifact_root).resolve()
        try:
            path = Path(artifact["internalPath"]).resolve()
        except (KeyError, TypeError):
            raise ProviderCandidateRejectedError(
                "provider candidate path is missing"
            ) from None
        if root not in path.parents or not path.is_file():
            raise ProviderCandidateRejectedError(
                "provider candidate escaped configured storage"
            )
        try:
            storage_key = str(path.relative_to(root))
        except ValueError:
            raise ProviderCandidateRejectedError(
                "provider candidate storage key is invalid"
            ) from None
        content_digest, content_size = _file_digest_and_size(path)
        execution = artifact.get("providerExecution")
        if (
            artifact.get("adapterIdentity") != COMFYUI_ADAPTER_ID
            or artifact.get("provenance") != "LIVE_PROVIDER"
            or artifact.get("gpuUsed") is not True
            or artifact.get("publicationAllowed") is not False
            or artifact.get("generationRequestDigest") != request["payloadDigest"]
            or artifact.get("storageKey") != storage_key
            or artifact.get("byteSize") != content_size
            or artifact.get("sha256") != content_digest
            or not isinstance(execution, Mapping)
        ):
            raise ProviderCandidateRejectedError(
                "provider candidate metadata verification failed"
            )
        if any(
            execution.get(field) != provider.get(field)
            for field in ("providerId", "modelId", "region", "endpointClass")
        ):
            raise ProviderCandidateRejectedError(
                "provider execution does not match the approved policy"
            )
        runtime_facts = execution.get("runtimeFacts")
        if (
            not isinstance(runtime_facts, Mapping)
            or runtime_facts.get("runtimeAttestationRef")
            != provider["runtimeAttestationRef"]
            or runtime_facts.get("runtimeAttestationDigest")
            != provider["runtimeAttestationDigest"]
        ):
            raise ProviderCandidateRejectedError(
                "provider runtime attestation does not match the approved policy"
            )
        if (
            execution.get("costCurrency") != production_policy["currency"]
            or execution.get("costMinor", provider["maxCostMinor"] + 1)
            > provider["maxCostMinor"]
            or execution.get("costMinor", production_policy["maxTotalCostMinor"] + 1)
            > production_policy["maxTotalCostMinor"]
            or execution.get("latencyMs", provider["timeoutSeconds"] * 1000 + 1)
            > provider["timeoutSeconds"] * 1000
        ):
            raise ProviderCandidateRejectedError(
                "provider execution exceeded the approved budget"
            )
        try:
            probe = verify_media_against_request(path, request)
        except V4ArtifactVerificationError as exc:
            raise ProviderCandidateRejectedError(
                "independent provider candidate probe failed"
            ) from exc
        if probe != artifact.get("probe"):
            raise ProviderCandidateRejectedError(
                "V4 and V5 provider candidate probes disagree"
            )
        attempts = job.get("attempts")
        if (
            not isinstance(attempts, list)
            or not attempts
            or attempts[-1].get("state") != "SUCCEEDED"
            or attempts[-1].get("attemptRef") != artifact.get("attemptRef")
        ):
            raise ProviderCandidateRejectedError(
                "provider attempt evidence is incomplete"
            )
        return deepcopy(dict(artifact)), attempts[-1]

    def run_video_experiment(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey",
            "sourceGenerationRequestRef", "providerCapabilityRef",
        }:
            raise EpisodeProductionError(
                "command fields do not match the provider experiment contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        idempotency_key = _idempotency_key(command.get("idempotencyKey"))
        source_ref = _required_ref(
            command.get("sourceGenerationRequestRef"),
            "sourceGenerationRequestRef",
        )
        capability_ref = _required_ref(
            command.get("providerCapabilityRef"), "providerCapabilityRef"
        )
        verified = self.assets.verify_asset_plan_current(workspace, run_ref)
        policy = self.production_policy.verify_policy_current(workspace, run_ref)
        source, shot = self._select_source(verified, source_ref)
        provider = self._select_provider(policy, capability_ref)
        profile = self._profile(policy["productionPolicy"], source)
        request_fingerprint = _digest(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "sourceGenerationRequestDigest": source["payloadDigest"],
                "creativeShotDigest": shot["payloadDigest"],
                "assetResolutionManifestDigest": verified[
                    "assetResolutionManifest"
                ]["payloadDigest"],
                "productionPolicyBundleDigest": policy["payloadDigest"],
                "providerCapabilityRef": capability_ref,
                "providerPolicyDigest": policy["providerExecutionPolicy"][
                    "payloadDigest"
                ],
                "experimentProfile": profile,
                "serviceId": EXPERIMENT_SERVICE_ID,
            }
        )
        existing = self.repository.get_by_idempotency(
            workspace, run_ref, idempotency_key
        )
        if existing is not None:
            if existing.requestDigest != request_fingerprint:
                raise IdempotencyConflictError(
                    "provider experiment command conflicts"
                )
            candidate = self._decode(existing)
            return {
                "candidate": self._public(candidate),
                "readiness": self._readiness([candidate]),
                "idempotentReplay": True,
            }
        request = self._request(
            verified=verified,
            policy=policy,
            source=source,
            shot=shot,
            provider=provider,
            request_fingerprint=request_fingerprint,
        )
        try:
            jobs = self.execution.execute_batch(
                workspace,
                run_ref,
                [request],
                batch_idempotency_key=idempotency_key,
            )
        except V4ArtifactVerificationError as exc:
            raise ProviderCandidateRejectedError(
                "V4 rejected the provider candidate evidence"
            ) from exc
        except V4MediaJobError as exc:
            raise ProviderExperimentUnavailableError(
                "V4 provider experiment did not complete"
            ) from exc
        if len(jobs) != 1:
            raise ProviderExperimentUnavailableError(
                "V4 returned an incomplete provider experiment"
            )
        artifact, attempt = self._verify_job(
            jobs[0], request, provider, policy["productionPolicy"]
        )
        execution = deepcopy(dict(artifact["providerExecution"]))
        now = self._clock()
        candidate = _sealed(
            {
                "schemaVersion": EXPERIMENT_CANDIDATE_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "experimentRef": _required_ref(
                    self._ref_factory("provider-experiment"), "experimentRef"
                ),
                "candidateRef": _required_ref(
                    self._ref_factory("provider-candidate"), "candidateRef"
                ),
                "candidateVersionRef": _required_ref(
                    self._ref_factory("provider-candidate-version"),
                    "candidateVersionRef",
                ),
                "version": 1,
                "sourceGenerationRequestRef": source["generationRequestRef"],
                "sourceGenerationRequestDigest": source["payloadDigest"],
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestDigest": request["payloadDigest"],
                "creativeShotRef": source["creativeShotRef"],
                "creativeShotVersionRef": source["creativeShotVersionRef"],
                "creativeShotDigest": source["creativeShotDigest"],
                "assetResolutionManifestDigest": verified[
                    "assetResolutionManifest"
                ]["payloadDigest"],
                "productionPolicyBundleRef": policy[
                    "productionPolicyBundleRef"
                ],
                "productionPolicyBundleDigest": policy["payloadDigest"],
                "rightsManifestRef": policy["rightsManifest"][
                    "rightsManifestRef"
                ],
                "rightsManifestDigest": policy["rightsManifest"][
                    "payloadDigest"
                ],
                "providerExecutionPolicyRef": policy[
                    "providerExecutionPolicy"
                ]["providerExecutionPolicyRef"],
                "providerExecutionPolicyDigest": policy[
                    "providerExecutionPolicy"
                ]["payloadDigest"],
                "providerCapabilityRef": provider["providerCapabilityRef"],
                "providerSelection": {
                    "providerId": provider["providerId"],
                    "modelId": provider["modelId"],
                    "region": provider["region"],
                    "endpointClass": provider["endpointClass"],
                    "usageTermsRef": provider["usageTermsRef"],
                    "budgetAuthorityRef": provider["budgetAuthorityRef"],
                    "credentialConfigured": True,
                },
                "jobRef": jobs[0]["jobRef"],
                "attemptRef": attempt["attemptRef"],
                "attemptNumber": attempt["attemptNumber"],
                "adapterIdentity": artifact["adapterIdentity"],
                "providerExecution": execution,
                "parameters": deepcopy(request["parameters"]),
                "mediaKind": "video",
                "mediaType": "video/mp4",
                "artifactStorageKey": artifact["storageKey"],
                "artifactStoreRef": sha256(
                    str(Path(self.execution.artifact_root).resolve()).encode(
                        "utf-8"
                    )
                ).hexdigest(),
                "artifactSha256": artifact["sha256"],
                "artifactByteSize": artifact["byteSize"],
                "probe": deepcopy(artifact["probe"]),
                "state": "UNTRUSTED_PROVIDER_CANDIDATE",
                "validationState": "TECHNICALLY_VERIFIED",
                "selectionState": "UNSELECTED",
                "admissionState": "NOT_ADMITTED",
                "rightsState": "BOUND_TO_RECORDED_MANIFEST",
                "provenance": "LIVE_PROVIDER",
                "gpuUsed": True,
                "experimentOnly": True,
                "publicationAllowed": False,
                "createdBy": EXPERIMENT_SERVICE_ID,
                "createdAt": now,
            }
        )
        record = ProviderExperimentRecord(
            workspace,
            run_ref,
            candidate["experimentRef"],
            idempotency_key,
            request_fingerprint,
            _canonical_json(candidate),
            _digest(candidate),
            now,
        )
        try:
            stored = self.repository.create(record)
        except IdempotencyConflictError:
            replay = self.repository.get_by_idempotency(
                workspace, run_ref, idempotency_key
            )
            if replay is None or replay.requestDigest != request_fingerprint:
                raise
            candidate = self._decode(replay)
            return {
                "candidate": self._public(candidate),
                "readiness": self._readiness([candidate]),
                "idempotentReplay": True,
            }
        candidate = self._decode(stored)
        return {
            "candidate": self._public(candidate),
            "readiness": self._readiness([candidate]),
            "idempotentReplay": False,
        }

    @staticmethod
    def _readiness(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
        video_count = sum(
            item.get("mediaKind") == "video"
            and item.get("validationState") == "TECHNICALLY_VERIFIED"
            and item.get("gpuUsed") is True
            for item in candidates
        )
        return {
            "checkpoint": "P1",
            "state": "PARTIAL_EXPERIMENT_EVIDENCE" if video_count else "BLOCKED",
            "verifiedVideoExperiments": video_count,
            "verifiedImageExperiments": 0,
            "verifiedAudioExperiments": 0,
            "blockers": [
                "live_image_provider_evidence_missing",
                "live_audio_provider_evidence_missing",
                "candidate_selection_not_started",
                "p2_production_runtime_not_started",
            ],
            "publicationAllowed": False,
        }

    def list_experiments(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        verified = self.assets.verify_asset_plan_current(workspace, production_run)
        policy = self.production_policy.verify_policy_current(
            workspace, production_run
        )
        source_digests = {
            item["generationRequestRef"]: item["payloadDigest"]
            for item in verified["generationRequests"]
        }
        candidates = [
            self._decode(record)
            for record in self.repository.list(workspace, production_run)
        ]
        for candidate in candidates:
            if (
                candidate.get("productionPolicyBundleDigest")
                != policy["payloadDigest"]
                or source_digests.get(candidate.get("sourceGenerationRequestRef"))
                != candidate.get("sourceGenerationRequestDigest")
                or candidate.get("assetResolutionManifestDigest")
                != verified["assetResolutionManifest"]["payloadDigest"]
                or candidate.get("publicationAllowed") is not False
                or candidate.get("selectionState") != "UNSELECTED"
                or candidate.get("admissionState") != "NOT_ADMITTED"
            ):
                raise StaleInputError("provider experiment lineage is stale")
            root = Path(self.execution.artifact_root).resolve()
            if candidate.get("artifactStoreRef") != sha256(
                str(root).encode("utf-8")
            ).hexdigest():
                raise ProviderCandidateRejectedError(
                    "provider experiment artifact store is unavailable"
                )
            storage_key = candidate.get("artifactStorageKey")
            if not isinstance(storage_key, str) or not storage_key:
                raise ProviderCandidateRejectedError(
                    "provider experiment storage key is unavailable"
                )
            path = (root / storage_key).resolve()
            if root not in path.parents or not path.is_file():
                raise ProviderCandidateRejectedError(
                    "provider experiment artifact is unavailable"
                )
            content_digest, content_size = _file_digest_and_size(path)
            if (
                content_size != candidate.get("artifactByteSize")
                or content_digest != candidate.get("artifactSha256")
            ):
                raise ProviderCandidateRejectedError(
                    "provider experiment artifact digest changed"
                )
        return {
            "candidates": [self._public(item) for item in candidates],
            "readiness": self._readiness(candidates),
            "persistenceClass": self.repository.persistence_class,
        }
