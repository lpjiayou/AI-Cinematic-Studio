"""Exact-scope K2 internal self-hosted P1 execution grant.

This module does not create rights, provider-policy, budget or publication
authority.  It binds one operator-enabled Creator process to one existing
workspace/run and one configured ComfyUI/Wan2.2 technical profile.  V5 still owns
lineage and admission; V4 still owns execution; publication remains disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from .foundation import EpisodeProductionError, _required_ref


INTERNAL_EXECUTION_MODE = "INTERNAL_SELF_HOSTED"
INTERNAL_EXECUTION_SCOPE = "K2_P1_SINGLE_EPISODE_VIDEO_SMOKE"
INTERNAL_EXECUTION_GRANT_VALUE = "GRANTED_INTERNAL"
INTERNAL_EXECUTION_GRANT_SCHEMA = "v5.k2-internal-execution-grant.v1"


class InternalExecutionConfigurationError(EpisodeProductionError):
    code = "internal_execution_configuration_invalid"


def _canonical_digest(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InternalExecutionConfigurationError(
            "internal execution grant is not canonical"
        ) from exc
    return sha256(encoded).hexdigest()


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InternalExecutionConfigurationError(f"{field} is invalid")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InternalExecutionConfigurationError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InternalExecutionConfigurationError(f"{field} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class K2InternalExecutionGrant:
    workspace_ref: str
    production_run_ref: str
    provider_id: str
    model_id: str
    region: str
    endpoint_class: str
    runtime_attestation_ref: str
    runtime_attestation_digest: str
    cost_currency: str
    max_cost_minor: int
    timeout_seconds: int
    execution_grant_ref: str
    execution_grant_digest: str

    @classmethod
    def create(
        cls,
        *,
        workspace_ref: str,
        production_run_ref: str,
        provider_id: str,
        model_id: str,
        region: str,
        endpoint_class: str,
        runtime_attestation_ref: str,
        runtime_attestation_digest: str,
        cost_currency: str,
        max_cost_minor: int,
        timeout_seconds: int,
    ) -> "K2InternalExecutionGrant":
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        provider = _required_ref(provider_id, "providerId")
        model = _required_ref(model_id, "modelId")
        selected_region = _required_ref(region, "region")
        endpoint = _required_ref(endpoint_class, "endpointClass")
        attestation_ref = _required_ref(
            runtime_attestation_ref, "runtimeAttestationRef"
        )
        attestation_digest = _sha256(
            runtime_attestation_digest, "runtimeAttestationDigest"
        )
        if (
            not isinstance(cost_currency, str)
            or len(cost_currency) != 3
            or not cost_currency.isalpha()
            or cost_currency != cost_currency.upper()
        ):
            raise InternalExecutionConfigurationError("costCurrency is invalid")
        cost_limit = _non_negative_int(max_cost_minor, "maxCostMinor")
        timeout = _positive_int(timeout_seconds, "timeoutSeconds")
        payload = {
            "schemaVersion": INTERNAL_EXECUTION_GRANT_SCHEMA,
            "executionMode": INTERNAL_EXECUTION_MODE,
            "scope": INTERNAL_EXECUTION_SCOPE,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "providerId": provider,
            "modelId": model,
            "region": selected_region,
            "endpointClass": endpoint,
            "runtimeAttestationRef": attestation_ref,
            "runtimeAttestationDigest": attestation_digest,
            "costCurrency": cost_currency,
            "maxCostMinor": cost_limit,
            "timeoutSeconds": timeout,
            "publicationAllowed": False,
        }
        digest = _canonical_digest(payload)
        return cls(
            workspace,
            run_ref,
            provider,
            model,
            selected_region,
            endpoint,
            attestation_ref,
            attestation_digest,
            cost_currency,
            cost_limit,
            timeout,
            f"k2-internal-execution-grant-{digest[:24]}",
            digest,
        )

    def matches(self, workspace_ref: str, run_ref: str) -> bool:
        return (
            workspace_ref == self.workspace_ref
            and run_ref == self.production_run_ref
        )

    def provider_selection(self) -> dict[str, Any]:
        return {
            "executionMode": INTERNAL_EXECUTION_MODE,
            "executionGrantRef": self.execution_grant_ref,
            "executionGrantDigest": self.execution_grant_digest,
            "providerId": self.provider_id,
            "modelId": self.model_id,
            "region": self.region,
            "endpointClass": self.endpoint_class,
            "runtimeAttestationRef": self.runtime_attestation_ref,
            "runtimeAttestationDigest": self.runtime_attestation_digest,
            "costCurrency": self.cost_currency,
            "maxCostMinor": self.max_cost_minor,
            "timeoutSeconds": self.timeout_seconds,
        }

    def public_projection(self) -> dict[str, Any]:
        return {
            "schemaVersion": INTERNAL_EXECUTION_GRANT_SCHEMA,
            "executionMode": INTERNAL_EXECUTION_MODE,
            "scope": INTERNAL_EXECUTION_SCOPE,
            "workspaceRef": self.workspace_ref,
            "productionRunRef": self.production_run_ref,
            "executionGrantRef": self.execution_grant_ref,
            "executionGrantDigest": self.execution_grant_digest,
            "providerId": self.provider_id,
            "modelId": self.model_id,
            "region": self.region,
            "endpointClass": self.endpoint_class,
            "runtimeAttestationRef": self.runtime_attestation_ref,
            "runtimeAttestationDigest": self.runtime_attestation_digest,
            "publicationAllowed": False,
        }


def internal_execution_grant_from_environment(
    environ: Mapping[str, str],
    *,
    provider_profile: Mapping[str, Any] | None,
) -> K2InternalExecutionGrant | None:
    """Resolve an exact internal grant from server-held configuration.

    Partial configuration fails closed.  Provider/model and runtime values are
    copied from the already validated V4 adapter profile, never from a browser
    command.
    """

    marker = str(environ.get("K2_P1_EXECUTION_AUTHORITY", "")).strip()
    workspace = str(environ.get("K2_P1_INTERNAL_WORKSPACE_REF", "")).strip()
    run_ref = str(environ.get("K2_P1_INTERNAL_PRODUCTION_RUN_REF", "")).strip()
    if not marker:
        if workspace or run_ref:
            raise InternalExecutionConfigurationError(
                "internal execution scope is partially configured"
            )
        return None
    if marker != INTERNAL_EXECUTION_GRANT_VALUE:
        raise InternalExecutionConfigurationError(
            "internal execution authority marker is invalid"
        )
    if not workspace or not run_ref or provider_profile is None:
        raise InternalExecutionConfigurationError(
            "internal execution grant is incomplete"
        )
    try:
        timeout_seconds = max(1, int(provider_profile["timeoutSeconds"]))
        return K2InternalExecutionGrant.create(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            provider_id=provider_profile["providerId"],
            model_id=provider_profile["modelId"],
            region=provider_profile["region"],
            endpoint_class=provider_profile["endpointClass"],
            runtime_attestation_ref=provider_profile[
                "runtimeAttestationRef"
            ],
            runtime_attestation_digest=provider_profile[
                "runtimeAttestationDigest"
            ],
            cost_currency=provider_profile["costCurrency"],
            max_cost_minor=provider_profile["maxCostMinor"],
            timeout_seconds=timeout_seconds,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InternalExecutionConfigurationError(
            "internal execution provider profile is incomplete"
        ) from exc
