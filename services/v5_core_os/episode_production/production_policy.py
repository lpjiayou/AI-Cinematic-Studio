"""P0 publishable-production policy and rights authority for the existing K2 run."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol

from .authority import K2AuthorityIdentityService
from .foundation import (
    EpisodeProductionError,
    EpisodeProductionService,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _canonical_json,
    _digest,
    _idempotency_key,
    _required_ref,
)


POLICY_BUNDLE_SCHEMA_VERSION = "v5.k2-production-policy-bundle.v1"
PRODUCTION_POLICY_SCHEMA_VERSION = "v5.production-policy.v1"
RIGHTS_MANIFEST_SCHEMA_VERSION = "v5.rights-manifest.v1"
PROVIDER_POLICY_SCHEMA_VERSION = "v5.provider-execution-policy.v1"
REQUIRED_DECISIONS = (
    "CREATIVE_DIRECTION",
    "IDENTITY_CONTINUITY",
    "TECHNICAL_QC",
    "FINAL_MASTER",
    "PUBLICATION_AUTHORIZATION",
)
REQUIRED_MEDIA_KINDS = ("image", "video", "audio")
RIGHTS_ENTRY_FIELDS = (
    "inputRef", "inputKind", "contentDigest", "rightsOwnerRef", "grantBasis",
    "permittedUses", "providerProcessingAllowed", "territories", "validFrom",
    "validUntil", "attributionText", "likenessVoiceMusicScope", "evidenceRef",
)


class ProductionPolicyRequiredError(EpisodeProductionError):
    code = "production_policy_required"


class RightsEvidenceAuthorityPort(Protocol):
    available: bool

    def verify_grant(self, grant: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ProviderPolicyAuthorityPort(Protocol):
    available: bool

    def verify_execution(self, execution: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RejectingRightsEvidenceAuthority:
    available = False

    def verify_grant(self, grant: Mapping[str, Any]) -> Mapping[str, Any]:
        del grant
        raise ProductionPolicyRequiredError("rights evidence authority is unavailable")


class StaticRightsEvidenceAuthority:
    """Test/integration authority over externally supplied canonical grant facts."""

    available = True

    def __init__(self, grants_by_evidence_ref: Mapping[str, Mapping[str, Any]]) -> None:
        self._grants = deepcopy(dict(grants_by_evidence_ref))

    def verify_grant(self, grant: Mapping[str, Any]) -> Mapping[str, Any]:
        evidence_ref = grant.get("evidenceRef")
        authority = self._grants.get(str(evidence_ref))
        if not isinstance(authority, Mapping):
            raise ProductionPolicyRequiredError("rights evidence is not resolvable")
        canonical = {field: deepcopy(authority.get(field)) for field in RIGHTS_ENTRY_FIELDS}
        if canonical != {field: deepcopy(grant.get(field)) for field in RIGHTS_ENTRY_FIELDS}:
            raise ProductionPolicyRequiredError("rights evidence does not match the claimed grant")
        return {
            "evidenceRef": evidence_ref,
            "evidenceDigest": _sha256(
                authority.get("evidenceDigest"), "rights evidenceDigest"
            ),
        }


class RejectingProviderPolicyAuthority:
    available = False

    def verify_execution(self, execution: Mapping[str, Any]) -> Mapping[str, Any]:
        del execution
        raise ProductionPolicyRequiredError("provider policy authority is unavailable")


class StaticProviderPolicyAuthority:
    """Test/integration authority over approved provider/model/region capabilities."""

    available = True

    def __init__(self, capabilities: Mapping[tuple[str, str, str, str], Mapping[str, Any]]) -> None:
        self._capabilities = deepcopy(dict(capabilities))

    def verify_execution(self, execution: Mapping[str, Any]) -> Mapping[str, Any]:
        key = (
            str(execution.get("mediaKind")),
            str(execution.get("providerId")),
            str(execution.get("modelId")),
            str(execution.get("region")),
        )
        authority = self._capabilities.get(key)
        if not isinstance(authority, Mapping) or authority.get("enabled") is not True:
            raise ProductionPolicyRequiredError("provider execution is not approved")
        for field in ("endpointClass", "safetyPolicyRef", "privacyMode"):
            if execution.get(field) != authority.get(field):
                raise ProductionPolicyRequiredError(
                    "provider execution does not match approved capability"
                )
        if execution.get("gpuAttestationRequired") is True and authority.get(
            "gpuAttestationSupported"
        ) is not True:
            raise ProductionPolicyRequiredError(
                "approved provider capability cannot attest GPU execution"
            )
        return deepcopy(dict(authority))


def _exact(value: Any, fields: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise EpisodeProductionError(f"{name} fields do not match the contract")
    return value


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EpisodeProductionError(f"{field} is invalid")
    if value < minimum or value > maximum:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    text = _text(value, field, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpisodeProductionError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise EpisodeProductionError(f"{field} is invalid")
    return parsed.astimezone(timezone.utc)


def _string_list(
    value: Any,
    field: str,
    *,
    allowed: set[str] | None = None,
    maximum_items: int = 100,
) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum_items:
        raise EpisodeProductionError(f"{field} is invalid")
    normalized = [_text(item, f"{field}[]", maximum=200) for item in value]
    if len(normalized) != len(set(normalized)):
        raise EpisodeProductionError(f"{field} contains duplicates")
    if allowed is not None and any(item not in allowed for item in normalized):
        raise EpisodeProductionError(f"{field} contains an unsupported value")
    return normalized


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = _digest(result)
    return result


def _validate_production_policy(
    raw: Any, *, root: Mapping[str, Any], ref_factory: Callable[[str], str], now: str
) -> dict[str, Any]:
    value = _exact(
        raw,
        {
            "targetDurationFrames", "frameRate", "width", "height", "aspectRatio",
            "container", "videoCodec", "audioCodec", "audioSampleRate", "language",
            "currency", "maxTotalCostMinor", "maxAttemptsPerRequest", "retentionDays",
            "intendedDestinations", "requiredDecisionKinds",
        },
        "productionPolicy",
    )
    manifest = root["manifest"]
    output = manifest["output"]
    frame_rate = _integer(value["frameRate"], "frameRate", minimum=1, maximum=240)
    expected_frames = round(float(manifest["targetDurationSec"]) * frame_rate)
    if (
        _integer(
            value["targetDurationFrames"], "targetDurationFrames",
            minimum=1, maximum=5_184_000,
        )
        != expected_frames
        or frame_rate != output["frameRate"]
        or _integer(value["width"], "width", minimum=16, maximum=16384)
        != output["width"]
        or _integer(value["height"], "height", minimum=16, maximum=16384)
        != output["height"]
        or value["aspectRatio"] != output["aspectRatio"]
        or value["container"] != output["container"]
    ):
        raise StaleInputError("production policy does not match the frozen K2 target")
    destinations = value["intendedDestinations"]
    if not isinstance(destinations, list) or not destinations or len(destinations) > 20:
        raise EpisodeProductionError("intendedDestinations is invalid")
    normalized_destinations = []
    seen_destinations: set[str] = set()
    for index, raw_destination in enumerate(destinations):
        destination = _exact(
            raw_destination,
            {"destinationRef", "territories"},
            f"intendedDestinations[{index}]",
        )
        destination_ref = _required_ref(
            destination["destinationRef"], f"intendedDestinations[{index}].destinationRef"
        )
        if destination_ref in seen_destinations:
            raise EpisodeProductionError("intendedDestinations contains duplicates")
        seen_destinations.add(destination_ref)
        normalized_destinations.append(
            {
                "destinationRef": destination_ref,
                "territories": _string_list(
                    destination["territories"],
                    f"intendedDestinations[{index}].territories",
                    maximum_items=50,
                ),
            }
        )
    decisions = _string_list(
        value["requiredDecisionKinds"],
        "requiredDecisionKinds",
        allowed=set(REQUIRED_DECISIONS),
        maximum_items=len(REQUIRED_DECISIONS),
    )
    if set(decisions) != set(REQUIRED_DECISIONS):
        raise EpisodeProductionError("all publishable decision kinds are required")
    base = {
        "schemaVersion": PRODUCTION_POLICY_SCHEMA_VERSION,
        "workspaceRef": root["workspaceRef"],
        "productionRunRef": root["productionRunRef"],
        "productionPolicyRef": _required_ref(
            ref_factory("production-policy"), "productionPolicyRef"
        ),
        "version": 1,
        "rootPayloadDigest": root["payloadDigest"],
        "targetDurationFrames": expected_frames,
        "frameRate": frame_rate,
        "width": value["width"],
        "height": value["height"],
        "aspectRatio": value["aspectRatio"],
        "container": value["container"],
        "videoCodec": _text(value["videoCodec"], "videoCodec", maximum=50),
        "audioCodec": _text(value["audioCodec"], "audioCodec", maximum=50),
        "audioSampleRate": _integer(
            value["audioSampleRate"], "audioSampleRate", minimum=8000, maximum=384000
        ),
        "language": _text(value["language"], "language", maximum=40),
        "currency": _text(value["currency"], "currency", maximum=3).upper(),
        "maxTotalCostMinor": _integer(
            value["maxTotalCostMinor"], "maxTotalCostMinor", minimum=1, maximum=1_000_000_000
        ),
        "maxAttemptsPerRequest": _integer(
            value["maxAttemptsPerRequest"], "maxAttemptsPerRequest", minimum=1, maximum=10
        ),
        "retentionDays": _integer(
            value["retentionDays"], "retentionDays", minimum=1, maximum=3650
        ),
        "intendedDestinations": normalized_destinations,
        "requiredDecisionKinds": list(REQUIRED_DECISIONS),
        "createdAt": now,
    }
    return _sealed(base)


def _required_rights_inputs(
    root: Mapping[str, Any], identity_lock: Mapping[str, Any]
) -> dict[str, str]:
    required = {
        str(root["scriptVersionRef"]): str(root["upstreamSnapshot"]["script"]["versionDigest"])
    }
    identities = identity_lock.get("identities")
    if not isinstance(identities, list) or not identities:
        raise StaleInputError("identity lock is incomplete")
    for identity in identities:
        reference = identity.get("reference") if isinstance(identity, Mapping) else None
        if not isinstance(reference, Mapping):
            raise StaleInputError("identity reference is incomplete")
        if (
            reference.get("rightsState") != "APPROVED"
            or reference.get("provenance") != "AUTHORITY_APPROVED"
        ):
            raise ProductionPolicyRequiredError(
                "identity reference is not approved for publishable production"
            )
        required[_required_ref(reference.get("referenceVersionRef"), "referenceVersionRef")] = (
            _sha256(reference.get("contentDigest"), "contentDigest")
        )
    return required


def _validate_rights_manifest(
    raw: Any,
    *,
    root: Mapping[str, Any],
    identity_lock: Mapping[str, Any],
    production_policy: Mapping[str, Any],
    rights_authority: RightsEvidenceAuthorityPort,
    ref_factory: Callable[[str], str],
    now: str,
) -> dict[str, Any]:
    value = _exact(raw, {"entries"}, "rightsManifest")
    entries = value["entries"]
    if not isinstance(entries, list) or not entries or len(entries) > 200:
        raise EpisodeProductionError("rightsManifest.entries is invalid")
    required_inputs = _required_rights_inputs(root, identity_lock)
    now_value = _timestamp(now, "createdAt")
    normalized = []
    seen: set[str] = set()
    covered_territories: set[str] | None = None
    for index, raw_entry in enumerate(entries):
        entry = _exact(
            raw_entry,
            {
                "inputRef", "inputKind", "contentDigest", "rightsOwnerRef",
                "grantBasis", "permittedUses", "providerProcessingAllowed",
                "territories", "validFrom", "validUntil", "attributionText",
                "likenessVoiceMusicScope", "evidenceRef",
            },
            f"rightsManifest.entries[{index}]",
        )
        input_ref = _required_ref(entry["inputRef"], f"rightsManifest.entries[{index}].inputRef")
        if input_ref in seen:
            raise EpisodeProductionError("rights manifest contains duplicate inputs")
        seen.add(input_ref)
        valid_from = _timestamp(entry["validFrom"], f"rightsManifest.entries[{index}].validFrom")
        valid_until = _timestamp(entry["validUntil"], f"rightsManifest.entries[{index}].validUntil")
        if valid_from > now_value or valid_until <= now_value or valid_from >= valid_until:
            raise ProductionPolicyRequiredError("rights grant is not currently valid")
        uses = sorted(
            _string_list(
                entry["permittedUses"],
                f"rightsManifest.entries[{index}].permittedUses",
                allowed={"AI_GENERATION", "DERIVATIVE_WORK", "PUBLICATION", "COMMERCIAL_USE"},
                maximum_items=4,
            )
        )
        if not {"AI_GENERATION", "DERIVATIVE_WORK", "PUBLICATION"}.issubset(uses):
            raise ProductionPolicyRequiredError("rights grant does not cover production")
        if entry["providerProcessingAllowed"] is not True:
            raise ProductionPolicyRequiredError("provider processing consent is required")
        territories = set(
            _string_list(
                entry["territories"],
                f"rightsManifest.entries[{index}].territories",
                maximum_items=100,
            )
        )
        covered_territories = territories if covered_territories is None else covered_territories & territories
        normalized_entry = {
            "inputRef": input_ref,
            "inputKind": _text(entry["inputKind"], "inputKind", maximum=40),
            "contentDigest": _sha256(entry["contentDigest"], "contentDigest"),
            "rightsOwnerRef": _required_ref(entry["rightsOwnerRef"], "rightsOwnerRef"),
            "grantBasis": _text(entry["grantBasis"], "grantBasis", maximum=40),
            "permittedUses": uses,
            "providerProcessingAllowed": True,
            "territories": sorted(territories),
            "validFrom": entry["validFrom"],
            "validUntil": entry["validUntil"],
            "attributionText": (
                "" if entry["attributionText"] == "" else _text(
                    entry["attributionText"], "attributionText", maximum=1000
                )
            ),
            "likenessVoiceMusicScope": sorted(
                _string_list(
                    entry["likenessVoiceMusicScope"],
                    "likenessVoiceMusicScope",
                    maximum_items=20,
                )
            ),
            "evidenceRef": _required_ref(entry["evidenceRef"], "evidenceRef"),
        }
        authority_evidence = rights_authority.verify_grant(normalized_entry)
        normalized_entry["authorityEvidenceDigest"] = _sha256(
            authority_evidence.get("evidenceDigest"), "authority evidenceDigest"
        )
        normalized.append(normalized_entry)
    if set(required_inputs) - seen:
        raise ProductionPolicyRequiredError("rights manifest does not cover frozen inputs")
    by_ref = {item["inputRef"]: item for item in normalized}
    if any(by_ref[input_ref]["contentDigest"] != digest for input_ref, digest in required_inputs.items()):
        raise StaleInputError("rights manifest digest does not match frozen input")
    requested_territories = {
        territory
        for destination in production_policy["intendedDestinations"]
        for territory in destination["territories"]
    }
    if "WORLDWIDE" not in (covered_territories or set()) and not requested_territories.issubset(
        covered_territories or set()
    ):
        raise ProductionPolicyRequiredError("rights territories do not cover destinations")
    base = {
        "schemaVersion": RIGHTS_MANIFEST_SCHEMA_VERSION,
        "workspaceRef": root["workspaceRef"],
        "productionRunRef": root["productionRunRef"],
        "rightsManifestRef": _required_ref(
            ref_factory("rights-manifest"), "rightsManifestRef"
        ),
        "version": 1,
        "rootPayloadDigest": root["payloadDigest"],
        "productionPolicyRef": production_policy["productionPolicyRef"],
        "productionPolicyDigest": production_policy["payloadDigest"],
        "entries": sorted(normalized, key=lambda item: item["inputRef"]),
        "requiredInputRefs": sorted(required_inputs),
        "state": "RIGHTS_CLEARED",
        "createdAt": now,
    }
    return _sealed(base)


def _validate_provider_policy(
    raw: Any,
    *,
    root: Mapping[str, Any],
    production_policy: Mapping[str, Any],
    provider_authority: ProviderPolicyAuthorityPort,
    ref_factory: Callable[[str], str],
    now: str,
) -> dict[str, Any]:
    value = _exact(raw, {"allowedExecutions"}, "providerExecutionPolicy")
    executions = value["allowedExecutions"]
    if not isinstance(executions, list) or not executions or len(executions) > 30:
        raise EpisodeProductionError("allowedExecutions is invalid")
    normalized = []
    identities: set[tuple[str, str, str, str]] = set()
    media_kinds: set[str] = set()
    total_cap = 0
    for index, raw_execution in enumerate(executions):
        execution = _exact(
            raw_execution,
            {
                "mediaKind", "providerId", "modelId", "region", "endpointClass",
                "safetyPolicyRef", "privacyMode", "maximumAttempts", "timeoutSeconds",
                "maxCostMinor", "seedPolicy", "gpuAttestationRequired",
            },
            f"allowedExecutions[{index}]",
        )
        media_kind = _text(execution["mediaKind"], "mediaKind", maximum=20)
        if media_kind not in REQUIRED_MEDIA_KINDS:
            raise EpisodeProductionError("mediaKind is unsupported")
        provider_id = _text(execution["providerId"], "providerId", maximum=100)
        model_id = _text(execution["modelId"], "modelId", maximum=200)
        region = _text(execution["region"], "region", maximum=100)
        endpoint_class = _text(execution["endpointClass"], "endpointClass", maximum=80)
        identity = (media_kind, provider_id, model_id, region)
        if identity in identities:
            raise EpisodeProductionError("provider execution policy contains duplicates")
        identities.add(identity)
        media_kinds.add(media_kind)
        max_cost = _integer(
            execution["maxCostMinor"], "maxCostMinor", minimum=1, maximum=1_000_000_000
        )
        if not isinstance(execution["gpuAttestationRequired"], bool):
            raise EpisodeProductionError("gpuAttestationRequired is invalid")
        total_cap += max_cost
        normalized_execution = {
            "mediaKind": media_kind,
            "providerId": provider_id,
            "modelId": model_id,
            "region": region,
            "endpointClass": endpoint_class,
            "safetyPolicyRef": _required_ref(
                execution["safetyPolicyRef"], "safetyPolicyRef"
            ),
            "privacyMode": _text(execution["privacyMode"], "privacyMode", maximum=50),
            "maximumAttempts": _integer(
                execution["maximumAttempts"], "maximumAttempts", minimum=1,
                maximum=production_policy["maxAttemptsPerRequest"],
            ),
            "timeoutSeconds": _integer(
                execution["timeoutSeconds"], "timeoutSeconds", minimum=1, maximum=86400
            ),
            "maxCostMinor": max_cost,
            "seedPolicy": _text(execution["seedPolicy"], "seedPolicy", maximum=50),
            "gpuAttestationRequired": execution["gpuAttestationRequired"],
        }
        authority = provider_authority.verify_execution(normalized_execution)
        valid_until = _timestamp(authority.get("validUntil"), "provider validUntil")
        if valid_until <= _timestamp(now, "createdAt"):
            raise ProductionPolicyRequiredError("provider approval is expired")
        normalized_execution.update(
            {
                "providerCapabilityRef": _required_ref(
                    authority.get("providerCapabilityRef"), "providerCapabilityRef"
                ),
                "credentialSourceRef": _required_ref(
                    authority.get("credentialSourceRef"), "credentialSourceRef"
                ),
                "usageTermsRef": _required_ref(
                    authority.get("usageTermsRef"), "usageTermsRef"
                ),
                "budgetAuthorityRef": _required_ref(
                    authority.get("budgetAuthorityRef"), "budgetAuthorityRef"
                ),
                "authorityEvidenceDigest": _sha256(
                    authority.get("evidenceDigest"), "provider evidenceDigest"
                ),
                "authorityValidUntil": authority.get("validUntil"),
            }
        )
        if execution["gpuAttestationRequired"]:
            normalized_execution.update(
                {
                    "runtimeAttestationRef": _required_ref(
                        authority.get("runtimeAttestationRef"),
                        "runtimeAttestationRef",
                    ),
                    "runtimeAttestationDigest": _sha256(
                        authority.get("runtimeAttestationDigest"),
                        "runtimeAttestationDigest",
                    ),
                }
            )
        normalized.append(normalized_execution)
    if media_kinds != set(REQUIRED_MEDIA_KINDS):
        raise ProductionPolicyRequiredError("image, video and audio provider policies are required")
    if total_cap > production_policy["maxTotalCostMinor"]:
        raise EpisodeProductionError("provider cost caps exceed the production budget")
    base = {
        "schemaVersion": PROVIDER_POLICY_SCHEMA_VERSION,
        "workspaceRef": root["workspaceRef"],
        "productionRunRef": root["productionRunRef"],
        "providerExecutionPolicyRef": _required_ref(
            ref_factory("provider-execution-policy"), "providerExecutionPolicyRef"
        ),
        "version": 1,
        "rootPayloadDigest": root["payloadDigest"],
        "productionPolicyRef": production_policy["productionPolicyRef"],
        "productionPolicyDigest": production_policy["payloadDigest"],
        "allowedExecutions": sorted(
            normalized,
            key=lambda item: (item["mediaKind"], item["providerId"], item["modelId"], item["region"]),
        ),
        "state": "POLICY_RECORDED",
        "createdAt": now,
    }
    return _sealed(base)


@dataclass(frozen=True, slots=True)
class ProductionPolicyBundleRecord:
    workspaceRef: str
    productionRunRef: str
    idempotencyKey: str
    requestDigest: str
    payloadJson: str
    payloadDigest: str
    createdAt: str


class ProductionPolicyRepository(Protocol):
    persistence_class: str

    def create(self, record: ProductionPolicyBundleRecord) -> ProductionPolicyBundleRecord: ...
    def get(self, workspace_ref: str, run_ref: str) -> ProductionPolicyBundleRecord | None: ...


class InMemoryProductionPolicyAdapter:
    persistence_class = "PROCESS_LOCAL"

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ProductionPolicyBundleRecord] = {}
        self._lock = RLock()

    def create(self, record: ProductionPolicyBundleRecord) -> ProductionPolicyBundleRecord:
        with self._lock:
            key = (record.workspaceRef, record.productionRunRef)
            if key in self._records:
                raise IdempotencyConflictError("production policy bundle already exists")
            self._records[key] = record
            return record

    def get(self, workspace_ref: str, run_ref: str) -> ProductionPolicyBundleRecord | None:
        with self._lock:
            return self._records.get((workspace_ref, run_ref))


class SqliteProductionPolicyAdapter:
    """Additive local policy store; P2 production persistence remains a later gate."""

    persistence_class = "LOCAL_SQLITE_EVIDENCE"
    _TABLES = {"v5_production_policy_schema", "v5_production_policy_bundles"}
    _COLUMNS = {
        "v5_production_policy_schema": ("component", "schema_version"),
        "v5_production_policy_bundles": (
            "workspace_ref", "production_run_ref", "idempotency_key",
            "request_digest", "payload_json", "payload_digest", "created_at",
        ),
    }

    def __init__(self, database_path: Path | str, *, initialize_if_missing: bool) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.database_path.exists() and self.database_path.stat().st_size > 0
        if not existed and not initialize_if_missing:
            raise RepositoryUnavailableError("production policy initialization is required")
        connection = self._connect()
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE v5_production_policy_schema ("
                    "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO v5_production_policy_schema VALUES ('production_policy',1)"
                )
                connection.execute(
                    "CREATE TABLE v5_production_policy_bundles ("
                    "workspace_ref TEXT NOT NULL, production_run_ref TEXT NOT NULL, "
                    "idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, "
                    "payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_ref,production_run_ref), "
                    "UNIQUE(workspace_ref,production_run_ref,idempotency_key))"
                )
                connection.commit()
                tables = set(self._TABLES)
            if tables != self._TABLES:
                raise RepositoryUnavailableError("production policy schema is unsupported")
            for table, expected in self._COLUMNS.items():
                actual = tuple(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if actual != expected:
                    raise RepositoryUnavailableError(
                        "production policy columns are unsupported"
                    )
            marker = connection.execute(
                "SELECT component,schema_version FROM v5_production_policy_schema"
            ).fetchall()
            if [tuple(row) for row in marker] != [("production_policy", 1)]:
                raise RepositoryUnavailableError("production policy marker is unsupported")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RepositoryUnavailableError("production policy integrity check failed")
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("production policy database is unavailable") from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @staticmethod
    def _record(row: sqlite3.Row) -> ProductionPolicyBundleRecord:
        return ProductionPolicyBundleRecord(
            row["workspace_ref"], row["production_run_ref"], row["idempotency_key"],
            row["request_digest"], row["payload_json"], row["payload_digest"], row["created_at"],
        )

    def create(self, record: ProductionPolicyBundleRecord) -> ProductionPolicyBundleRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO v5_production_policy_bundles VALUES (?,?,?,?,?,?,?)",
                (
                    record.workspaceRef, record.productionRunRef, record.idempotencyKey,
                    record.requestDigest, record.payloadJson, record.payloadDigest, record.createdAt,
                ),
            )
            connection.commit()
            return record
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise IdempotencyConflictError("production policy bundle already exists") from exc
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RepositoryUnavailableError("production policy database is unavailable") from exc
        finally:
            connection.close()

    def get(self, workspace_ref: str, run_ref: str) -> ProductionPolicyBundleRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v5_production_policy_bundles WHERE workspace_ref=? AND production_run_ref=?",
                (workspace_ref, run_ref),
            ).fetchone()
            return None if row is None else self._record(row)
        except sqlite3.DatabaseError as exc:
            raise RepositoryUnavailableError("production policy database is unavailable") from exc
        finally:
            connection.close()


class K2ProductionPolicyService:
    def __init__(
        self,
        root_service: EpisodeProductionService,
        authority_identity: K2AuthorityIdentityService,
        repository: ProductionPolicyRepository,
        rights_authority: RightsEvidenceAuthorityPort,
        provider_authority: ProviderPolicyAuthorityPort,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.root_service = root_service
        self.authority_identity = authority_identity
        self.repository = repository
        self.rights_authority = rights_authority
        self.provider_authority = provider_authority
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _decode(record: ProductionPolicyBundleRecord) -> dict[str, Any]:
        try:
            payload = json.loads(record.payloadJson)
        except json.JSONDecodeError as exc:
            raise RepositoryUnavailableError("production policy payload is invalid") from exc
        if not isinstance(payload, dict) or _digest(payload) != record.payloadDigest:
            raise RepositoryUnavailableError("production policy digest verification failed")
        embedded = payload.get("payloadDigest")
        unsigned = dict(payload)
        unsigned.pop("payloadDigest", None)
        if embedded != _digest(unsigned):
            raise RepositoryUnavailableError(
                "production policy embedded digest verification failed"
            )
        return payload

    @staticmethod
    def _public_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
        """Project safe policy facts without exposing credential-source handles."""

        production = deepcopy(dict(bundle["productionPolicy"]))
        rights = bundle["rightsManifest"]
        provider = bundle["providerExecutionPolicy"]
        executions = []
        for raw_execution in provider["allowedExecutions"]:
            execution = deepcopy(dict(raw_execution))
            execution.pop("credentialSourceRef", None)
            execution["credentialConfigured"] = True
            executions.append(execution)
        return {
            "schemaVersion": bundle["schemaVersion"],
            "workspaceRef": bundle["workspaceRef"],
            "productionRunRef": bundle["productionRunRef"],
            "productionPolicyBundleRef": bundle["productionPolicyBundleRef"],
            "version": bundle["version"],
            "rootPayloadDigest": bundle["rootPayloadDigest"],
            "identityLockRef": bundle["identityLockRef"],
            "identityLockVersionRef": bundle["identityLockVersionRef"],
            "identityLockDigest": bundle["identityLockDigest"],
            "productionPolicy": production,
            "rightsManifest": {
                "schemaVersion": rights["schemaVersion"],
                "rightsManifestRef": rights["rightsManifestRef"],
                "version": rights["version"],
                "state": rights["state"],
                "requiredInputRefs": deepcopy(rights["requiredInputRefs"]),
                "entryCount": len(rights["entries"]),
                "payloadDigest": rights["payloadDigest"],
            },
            "providerExecutionPolicy": {
                "schemaVersion": provider["schemaVersion"],
                "providerExecutionPolicyRef": provider[
                    "providerExecutionPolicyRef"
                ],
                "version": provider["version"],
                "state": provider["state"],
                "allowedExecutions": executions,
                "payloadDigest": provider["payloadDigest"],
            },
            "recordedBy": bundle["recordedBy"],
            "state": bundle["state"],
            "publicationAllowed": False,
            "createdAt": bundle["createdAt"],
            "payloadDigest": bundle["payloadDigest"],
            "projectionClass": "PUBLIC_SAFE_POLICY_FACTS",
        }

    def record_bundle(self, command: Mapping[str, Any]) -> dict[str, Any]:
        value = _exact(
            command,
            {
                "workspaceRef", "productionRunRef", "idempotencyKey", "actorRef",
                "productionPolicy", "rightsManifest", "providerExecutionPolicy",
            },
            "command",
        )
        workspace = _required_ref(value["workspaceRef"], "workspaceRef")
        run_ref = _required_ref(value["productionRunRef"], "productionRunRef")
        idempotency_key = _idempotency_key(value["idempotencyKey"])
        actor_ref = _required_ref(value["actorRef"], "actorRef")
        root = self.root_service.verify_run_current(workspace, run_ref)
        authority = self.authority_identity.verify_authority_identity_current(workspace, run_ref)
        now = self._clock()
        for field in (
            "productionPolicy", "rightsManifest", "providerExecutionPolicy"
        ):
            if not isinstance(value[field], Mapping):
                raise EpisodeProductionError(f"{field} must be an object")
        request_digest = _digest(
            {
                "idempotencyKey": idempotency_key,
                "actorRef": actor_ref,
                "rootPayloadDigest": root["payloadDigest"],
                "identityLockDigest": authority["identityLock"]["payloadDigest"],
                "productionPolicy": deepcopy(dict(value["productionPolicy"])),
                "rightsManifest": deepcopy(dict(value["rightsManifest"])),
                "providerExecutionPolicy": deepcopy(
                    dict(value["providerExecutionPolicy"])
                ),
            }
        )
        existing = self.repository.get(workspace, run_ref)
        if existing is not None:
            if existing.idempotencyKey != idempotency_key or existing.requestDigest != request_digest:
                raise IdempotencyConflictError("production policy bundle conflicts")
            return {**self._projection(self._decode(existing)), "idempotentReplay": True}
        production = _validate_production_policy(
            value["productionPolicy"], root=root, ref_factory=self._ref_factory, now=now
        )
        rights = _validate_rights_manifest(
            value["rightsManifest"],
            root=root,
            identity_lock=authority["identityLock"],
            production_policy=production,
            rights_authority=self.rights_authority,
            ref_factory=self._ref_factory,
            now=now,
        )
        provider = _validate_provider_policy(
            value["providerExecutionPolicy"],
            root=root,
            production_policy=production,
            provider_authority=self.provider_authority,
            ref_factory=self._ref_factory,
            now=now,
        )
        bundle_base = {
            "schemaVersion": POLICY_BUNDLE_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "productionPolicyBundleRef": _required_ref(
                self._ref_factory("production-policy-bundle"), "productionPolicyBundleRef"
            ),
            "version": 1,
            "rootPayloadDigest": root["payloadDigest"],
            "identityLockRef": authority["identityLock"]["identityLockRef"],
            "identityLockVersionRef": authority["identityLock"]["identityLockVersionRef"],
            "identityLockDigest": authority["identityLock"]["payloadDigest"],
            "productionPolicy": production,
            "rightsManifest": rights,
            "providerExecutionPolicy": provider,
            "recordedBy": actor_ref,
            "state": "POLICY_RECORDED",
            "publicationAllowed": False,
            "createdAt": now,
        }
        bundle = _sealed(bundle_base)
        record = ProductionPolicyBundleRecord(
            workspace, run_ref, idempotency_key, request_digest,
            _canonical_json(bundle), _digest(bundle), now,
        )
        try:
            stored = self.repository.create(record)
        except IdempotencyConflictError:
            replay = self.repository.get(workspace, run_ref)
            if replay is None or replay.idempotencyKey != idempotency_key or replay.requestDigest != request_digest:
                raise
            return {**self._projection(self._decode(replay)), "idempotentReplay": True}
        return {**self._projection(self._decode(stored)), "idempotentReplay": False}

    def _projection(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "policyBundle": self._public_bundle(bundle),
            "readiness": {
                "state": "BLOCKED_EXTERNAL_EVIDENCE",
                "policyRecorded": True,
                "rightsState": bundle["rightsManifest"]["state"],
                "providerPolicyState": bundle["providerExecutionPolicy"]["state"],
                "persistenceClass": self.repository.persistence_class,
                "blockers": [
                    "live_provider_evidence_missing",
                    "production_runtime_evidence_missing",
                    "human_approvals_missing",
                    "publication_authority_missing",
                ],
                "publicationAllowed": False,
            },
        }

    def get_readiness(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        root = self.root_service.verify_run_current(workspace, production_run)
        try:
            authority = self.authority_identity.verify_authority_identity_current(
                workspace, production_run
            )
        except EpisodeProductionError:
            authority = None
        identity_publishable = False
        if authority is not None:
            identities = authority["identityLock"].get("identities")
            identity_publishable = isinstance(identities, list) and bool(identities) and all(
                isinstance(identity, Mapping)
                and isinstance(identity.get("reference"), Mapping)
                and identity["reference"].get("rightsState") == "APPROVED"
                and identity["reference"].get("provenance") == "AUTHORITY_APPROVED"
                for identity in identities
            )
        record = self.repository.get(workspace, production_run)
        if record is None:
            blockers = [
                "production_policy_missing",
                "rights_manifest_missing",
                "provider_execution_policy_missing",
                "live_provider_evidence_missing",
                "production_runtime_evidence_missing",
                "human_approvals_missing",
                "publication_authority_missing",
            ]
            if not self.rights_authority.available:
                blockers.insert(0, "rights_evidence_authority_missing")
            if not self.provider_authority.available:
                blockers.insert(0, "provider_policy_authority_missing")
            if authority is None:
                blockers.insert(0, "identity_lock_missing")
            elif not identity_publishable:
                blockers.insert(0, "identity_reference_rights_not_approved")
            return {
                "policyBundle": None,
                "readiness": {
                    "state": "BLOCKED_POLICY",
                    "policyRecorded": False,
                    "rightsState": "MISSING",
                    "providerPolicyState": "MISSING",
                    "persistenceClass": self.repository.persistence_class,
                    "rootPayloadDigest": root["payloadDigest"],
                    "blockers": blockers,
                    "publicationAllowed": False,
                },
            }
        bundle = self.verify_policy_current(workspace, production_run)
        return self._projection(bundle)

    def verify_policy_current(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        """Return the complete server-side policy bundle after lineage checks.

        This method is intentionally not a browser projection: provider credential
        *source refs* are needed by server-side V5 orchestration to bind a V4
        dispatch, while secret values remain outside the bundle and V5.
        """

        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        root = self.root_service.verify_run_current(workspace, production_run)
        authority = self.authority_identity.verify_authority_identity_current(
            workspace, production_run
        )
        record = self.repository.get(workspace, production_run)
        if record is None:
            raise ProductionPolicyRequiredError(
                "production policy bundle is not recorded"
            )
        bundle = self._decode(record)
        if (
            bundle.get("rootPayloadDigest") != root["payloadDigest"]
            or bundle.get("identityLockDigest") != authority["identityLock"]["payloadDigest"]
            or bundle.get("rightsManifest", {}).get("state") != "RIGHTS_CLEARED"
            or bundle.get("providerExecutionPolicy", {}).get("state")
            != "POLICY_RECORDED"
        ):
            raise StaleInputError("production policy bundle lineage is stale")
        return bundle
