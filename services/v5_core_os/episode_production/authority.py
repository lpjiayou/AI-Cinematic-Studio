"""G2 M6 authority decision and separate V5 Identity Lock."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Protocol, Sequence

from .evidence import (
    EpisodeProductionEvidenceRepository,
    EvidenceFact,
    GateAppend,
)
from .foundation import (
    EpisodeProductionError,
    EpisodeProductionService,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)


AUTHORITY_DECISION_SCHEMA_VERSION = "v5.m6-authority-decision.v1"
IDENTITY_LOCK_SCHEMA_VERSION = "v5.identity-lock.v1"
AUTHORITY_GATE = "G2_AUTHORITY_IDENTITY"


class AuthorityRequiredError(EpisodeProductionError):
    code = "authority_required"


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StaleInputError(f"{field} is invalid")
    return value


class IdentityReferenceAuthorityPort(Protocol):
    def authorize_reference(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        character: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class RejectingIdentityReferenceAuthority:
    def authorize_reference(self, **_: Any) -> Mapping[str, Any]:
        raise AuthorityRequiredError("identity reference authority is unavailable")


class StaticIdentityReferenceAuthority:
    """Explicit injectable authority for tests and bounded local evidence."""

    def __init__(self, references: Mapping[str, Mapping[str, Any]]) -> None:
        self._references = deepcopy(dict(references))

    def authorize_reference(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        character: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del workspace_ref, production_run_ref
        character_ref = character.get("characterRef")
        if not isinstance(character_ref, str) or character_ref not in self._references:
            raise AuthorityRequiredError("identity reference was not authorized")
        return deepcopy(dict(self._references[character_ref]))


def _m6_baseline(operation: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
    try:
        result = operation()
    except Exception as exc:
        code = str(getattr(exc, "code", ""))
        if code == "m6_consumer_authority_unavailable":
            raise AuthorityRequiredError("M6 authority is unavailable") from None
        if code in {"m6_baseline_not_available", "m6_episode_mapping_unavailable"}:
            raise UpstreamNotReadyError("active M6 baseline is required") from None
        if code in {"m6_baseline_stale", "m6_lineage_mismatch"}:
            raise StaleInputError("M6 baseline is stale or inconsistent") from None
        if code in {"m6_consumer_internal_error", "lifecycle_unavailable"}:
            raise RepositoryUnavailableError("M6 baseline reader is unavailable") from None
        raise
    if not isinstance(result, Mapping):
        raise RepositoryUnavailableError("M6 baseline projection is unavailable")
    return result


def _identity_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthorityRequiredError("identity reference authority returned no decision")
    exact = {
        "referenceRef", "referenceVersionRef", "contentDigest", "mediaType",
        "rightsState", "provenance", "approvalRef",
    }
    if set(value) != exact:
        raise AuthorityRequiredError("identity reference decision is not closed-world")
    try:
        digest = _sha256(value.get("contentDigest"), "contentDigest")
    except StaleInputError:
        raise AuthorityRequiredError("identity reference digest is invalid") from None
    media_type = value.get("mediaType")
    if media_type not in {"image", "image/png", "video", "identity-direction"}:
        raise AuthorityRequiredError("identity reference media type is unsupported")
    rights_state = value.get("rightsState")
    if rights_state not in {"APPROVED", "LOCAL_EVIDENCE_ONLY"}:
        raise AuthorityRequiredError("identity reference rights state is unresolved")
    provenance = value.get("provenance")
    if provenance not in {"AUTHORITY_APPROVED", "LOCAL_EVIDENCE"}:
        raise AuthorityRequiredError("identity reference provenance is invalid")
    if rights_state == "LOCAL_EVIDENCE_ONLY" and provenance != "LOCAL_EVIDENCE":
        raise AuthorityRequiredError("local identity reference provenance is inconsistent")
    if rights_state == "APPROVED" and provenance != "AUTHORITY_APPROVED":
        raise AuthorityRequiredError("approved identity reference provenance is inconsistent")
    return {
        "referenceRef": _required_ref(value.get("referenceRef"), "referenceRef"),
        "referenceVersionRef": _required_ref(
            value.get("referenceVersionRef"), "referenceVersionRef"
        ),
        "contentDigest": digest,
        "mediaType": media_type,
        "rightsState": rights_state,
        "provenance": provenance,
        "approvalRef": _required_ref(value.get("approvalRef"), "approvalRef"),
    }


class K2AuthorityIdentityService:
    def __init__(
        self,
        root_service: EpisodeProductionService,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        m6_reader: Any,
        identity_reference_authority: IdentityReferenceAuthorityPort,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.m6_reader = m6_reader
        self.identity_reference_authority = identity_reference_authority
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _fact(gate: Mapping[str, Any], kind: str) -> dict[str, Any]:
        matches = [item for item in gate.get("facts", []) if item.get("factKind") == kind]
        if len(matches) != 1:
            raise RepositoryUnavailableError("episode gate fact is inconsistent")
        return deepcopy(dict(matches[0]["payload"]))

    def project_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        result = deepcopy(dict(run))
        workspace = str(result["workspaceRef"])
        run_ref = str(result["productionRunRef"])
        result["state"] = self.evidence.current_state(workspace, run_ref)
        result["completedGates"] = [
            item["gateName"] for item in self.evidence.list_gates(workspace, run_ref)
        ]
        return result

    def get_authority_identity(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        self.root_service.get_run(workspace_ref, production_run_ref)
        gate = self.evidence.get_gate(workspace_ref, production_run_ref, AUTHORITY_GATE)
        if gate is None:
            raise UpstreamNotReadyError("authority and identity lock are not ready")
        return {
            "authorityDecision": self._fact(gate, "M6AuthorityDecision"),
            "identityLock": self._fact(gate, "IdentityLock"),
            "transition": {
                "fromState": gate["fromState"],
                "toState": gate["toState"],
                "createdAt": gate["createdAt"],
            },
        }

    def verify_authority_identity_current(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        root = self.root_service.verify_run_current(
            workspace_ref, production_run_ref
        )
        bundle = self.get_authority_identity(workspace_ref, production_run_ref)
        authority = bundle["authorityDecision"]
        identity = bundle["identityLock"]
        baseline = _m6_baseline(
            lambda: self.m6_reader.get_m6_episode_baseline(
                workspace_ref,
                root["projectRef"],
                root["seriesRef"],
                root["episodeRef"],
            )
        )
        expected_scope = (
            workspace_ref,
            root["projectRef"],
            root["seriesRef"],
            root["episodeRef"],
            root["episodePlanItemRef"],
            root["seriesPlanVersionRef"],
        )
        actual_scope = tuple(
            baseline.get(field)
            for field in (
                "workspaceRef", "projectRef", "seriesRef", "episodeRef",
                "episodePlanItemRef", "seriesPlanVersionRef",
            )
        )
        if actual_scope != expected_scope or baseline.get("compatibility") != "CURRENT":
            raise StaleInputError("M6 authority no longer matches K2 roots")
        lineage_pairs = (
            ("m6BaselineSnapshotRef", "m6BaselineSnapshotRef"),
            ("activationRevision", "activationRevision"),
            ("m6BaselineCanonicalDigest", "m6BaselineCanonicalDigest"),
            ("seriesPlanVersionRef", "seriesPlanVersionRef"),
            ("seriesPlanVersionDigest", "seriesPlanVersionDigest"),
            ("seriesBibleVersionRef", "seriesBibleVersionRef"),
            ("seriesBibleVersionDigest", "seriesBibleVersionDigest"),
            ("characterContinuityVersionRef", "characterContinuityVersionRef"),
            (
                "characterContinuityVersionDigest",
                "characterContinuityVersionDigest",
            ),
        )
        if any(
            authority.get(authority_field) != baseline.get(baseline_field)
            for authority_field, baseline_field in lineage_pairs
        ):
            raise StaleInputError("recorded M6 authority is stale")
        if (
            authority.get("rootPayloadDigest") != root["payloadDigest"]
            or authority.get("scriptVersionRef") != root["scriptVersionRef"]
            or identity.get("rootPayloadDigest") != root["payloadDigest"]
            or identity.get("authorityDecisionRef")
            != authority.get("authorityDecisionRef")
            or identity.get("authorityDecisionDigest")
            != authority.get("payloadDigest")
            or identity.get("state") != "LOCKED"
            or identity.get("publicationAllowed") is not False
        ):
            raise StaleInputError("identity lock lineage is stale or inconsistent")
        identities = identity.get("identities")
        locked_names = (
            [item.get("scriptCharacterName") for item in identities]
            if isinstance(identities, list)
            and all(isinstance(item, Mapping) for item in identities)
            else []
        )
        if (
            not isinstance(identities, list)
            or not all(isinstance(item, Mapping) for item in identities)
            or not all(isinstance(name, str) for name in locked_names)
            or sorted(locked_names)
            != sorted(root["manifest"]["requiredCharacterNames"])
        ):
            raise StaleInputError("identity lock does not cover the frozen manifest")
        return {"root": root, **bundle, "m6Baseline": deepcopy(dict(baseline))}

    def authorize_and_lock(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping):
            raise EpisodeProductionError("command must be an object")
        allowed = {
            "workspaceRef", "productionRunRef", "idempotencyKey", "characterMappings"
        }
        if set(command) != allowed:
            raise EpisodeProductionError("command fields do not match the G2 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        idempotency_key = _idempotency_key(command.get("idempotencyKey"))
        root = self.root_service.verify_run_current(workspace, run_ref)
        mappings = command.get("characterMappings")
        if not isinstance(mappings, list) or not mappings:
            raise EpisodeProductionError("characterMappings must not be empty")
        required_names = root["manifest"].get("requiredCharacterNames")
        if not isinstance(required_names, list) or not required_names:
            raise RepositoryUnavailableError("K2 manifest character set is unavailable")
        normalized_mappings: list[dict[str, str]] = []
        seen_names: set[str] = set()
        seen_refs: set[str] = set()
        for index, item in enumerate(mappings):
            if not isinstance(item, Mapping) or set(item) != {
                "scriptCharacterName", "characterRef"
            }:
                raise EpisodeProductionError(f"characterMappings[{index}] is invalid")
            name = item.get("scriptCharacterName")
            if not isinstance(name, str) or name != name.strip() or not name:
                raise EpisodeProductionError(f"characterMappings[{index}] name is invalid")
            character_ref = _required_ref(
                item.get("characterRef"), f"characterMappings[{index}].characterRef"
            )
            if name in seen_names or character_ref in seen_refs:
                raise EpisodeProductionError("characterMappings must be one-to-one")
            seen_names.add(name)
            seen_refs.add(character_ref)
            normalized_mappings.append(
                {"scriptCharacterName": name, "characterRef": character_ref}
            )
        if sorted(seen_names) != sorted(required_names):
            raise EpisodeProductionError("characterMappings must cover the frozen manifest")

        baseline = _m6_baseline(
            lambda: self.m6_reader.get_m6_episode_baseline(
                workspace, root["projectRef"], root["seriesRef"], root["episodeRef"]
            )
        )
        expected = (
            workspace,
            root["projectRef"],
            root["seriesRef"],
            root["episodeRef"],
            root["episodePlanItemRef"],
            root["seriesPlanVersionRef"],
        )
        actual = tuple(
            baseline.get(field)
            for field in (
                "workspaceRef", "projectRef", "seriesRef", "episodeRef",
                "episodePlanItemRef", "seriesPlanVersionRef",
            )
        )
        if actual != expected or baseline.get("compatibility") != "CURRENT":
            raise StaleInputError("M6 baseline does not match the frozen K2 roots")
        if baseline.get("schemaVersion") != "v5.m6-episode-baseline-input.v1":
            raise StaleInputError("M6 baseline schema is unsupported")
        activation_revision = baseline.get("activationRevision")
        if (
            isinstance(activation_revision, bool)
            or not isinstance(activation_revision, int)
            or activation_revision < 1
        ):
            raise StaleInputError("M6 activation revision is invalid")
        m6_digest = _sha256(
            baseline.get("m6BaselineCanonicalDigest"),
            "m6BaselineCanonicalDigest",
        )
        series_plan_digest = _sha256(
            baseline.get("seriesPlanVersionDigest"), "seriesPlanVersionDigest"
        )
        character_continuity_digest = _sha256(
            baseline.get("characterContinuityVersionDigest"),
            "characterContinuityVersionDigest",
        )
        series_bible_digest = _sha256(
            baseline.get("seriesBibleVersionDigest"), "seriesBibleVersionDigest"
        )
        facts = baseline.get("applicableFacts")
        characters = facts.get("characters") if isinstance(facts, Mapping) else None
        if not isinstance(characters, list) or not all(
            isinstance(item, Mapping) for item in characters
        ):
            raise StaleInputError("M6 character facts are unavailable")
        characters_by_ref: dict[str, Mapping[str, Any]] = {}
        for character in characters:
            character_ref = character.get("characterRef")
            if not isinstance(character_ref, str) or character_ref in characters_by_ref:
                raise StaleInputError("M6 character identity is ambiguous")
            characters_by_ref[character_ref] = character
        locked_identities = []
        for mapping in sorted(normalized_mappings, key=lambda item: item["scriptCharacterName"]):
            character = characters_by_ref.get(mapping["characterRef"])
            if character is None:
                raise StaleInputError("mapped M6 character was not found")
            reference = _identity_reference(
                self.identity_reference_authority.authorize_reference(
                    workspace_ref=workspace,
                    production_run_ref=run_ref,
                    character=character,
                )
            )
            locked_identities.append(
                {
                    **mapping,
                    "characterFactDigest": _digest(dict(character)),
                    "visualIdentityRules": deepcopy(character.get("visualIdentityRules", [])),
                    "reference": reference,
                }
            )

        # Re-read both accepted authorities immediately before recording the gate.
        # This closes the ordinary read/authorize window without pretending that
        # two independently owned domains share one database transaction.
        self.root_service.verify_run_current(workspace, run_ref)
        refreshed_baseline = _m6_baseline(
            lambda: self.m6_reader.get_m6_episode_baseline(
                workspace, root["projectRef"], root["seriesRef"], root["episodeRef"]
            )
        )
        baseline_fields = (
            "schemaVersion", "workspaceRef", "projectRef", "seriesRef",
            "episodeRef", "episodePlanItemRef", "m6BaselineSnapshotRef",
            "activationRevision", "m6BaselineCanonicalDigest",
            "seriesPlanVersionRef", "seriesPlanVersionDigest",
            "seriesBibleVersionRef", "seriesBibleVersionDigest",
            "characterContinuityVersionRef", "characterContinuityVersionDigest",
            "compatibility",
        )
        if tuple(refreshed_baseline.get(field) for field in baseline_fields) != tuple(
            baseline.get(field) for field in baseline_fields
        ):
            raise StaleInputError("M6 baseline changed during identity authorization")

        now = self._clock()
        request_digest = _digest(
            {
                "idempotencyKey": idempotency_key,
                "rootPayloadDigest": root["payloadDigest"],
                "m6BaselineSnapshotRef": baseline.get("m6BaselineSnapshotRef"),
                "m6BaselineCanonicalDigest": m6_digest,
                "characterMappings": sorted(
                    normalized_mappings,
                    key=lambda item: item["scriptCharacterName"],
                ),
                "lockedIdentities": locked_identities,
            }
        )
        authority_base = {
            "schemaVersion": AUTHORITY_DECISION_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "authorityDecisionRef": _required_ref(
                self._ref_factory("m6-authority-decision"), "authorityDecisionRef"
            ),
            "decision": "AUTHORIZED",
            "decisionSource": "M6_ACTIVE_BASELINE",
            "rootPayloadDigest": root["payloadDigest"],
            "projectRef": root["projectRef"],
            "seriesRef": root["seriesRef"],
            "episodeRef": root["episodeRef"],
            "episodePlanItemRef": root["episodePlanItemRef"],
            "scriptVersionRef": root["scriptVersionRef"],
            "m6BaselineSnapshotRef": _required_ref(
                baseline.get("m6BaselineSnapshotRef"), "m6BaselineSnapshotRef"
            ),
            "activationRevision": activation_revision,
            "m6BaselineCanonicalDigest": m6_digest,
            "seriesPlanVersionRef": _required_ref(
                baseline.get("seriesPlanVersionRef"), "seriesPlanVersionRef"
            ),
            "seriesPlanVersionDigest": series_plan_digest,
            "seriesBibleVersionRef": _required_ref(
                baseline.get("seriesBibleVersionRef"), "seriesBibleVersionRef"
            ),
            "seriesBibleVersionDigest": series_bible_digest,
            "characterContinuityVersionRef": _required_ref(
                baseline.get("characterContinuityVersionRef"),
                "characterContinuityVersionRef",
            ),
            "characterContinuityVersionDigest": character_continuity_digest,
            "createdAt": now,
            "createdBy": "v5.episode-production.authority",
            "version": 1,
        }
        authority = {**authority_base, "payloadDigest": _digest(authority_base)}
        lock_base = {
            "schemaVersion": IDENTITY_LOCK_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "identityLockRef": _required_ref(
                self._ref_factory("identity-lock"), "identityLockRef"
            ),
            "identityLockVersionRef": _required_ref(
                self._ref_factory("identity-lock-version"), "identityLockVersionRef"
            ),
            "authorityDecisionRef": authority["authorityDecisionRef"],
            "authorityDecisionDigest": authority["payloadDigest"],
            "rootPayloadDigest": root["payloadDigest"],
            "m6BaselineSnapshotRef": authority["m6BaselineSnapshotRef"],
            "seriesBibleVersionRef": authority["seriesBibleVersionRef"],
            "seriesBibleVersionDigest": authority["seriesBibleVersionDigest"],
            "characterContinuityVersionRef": authority[
                "characterContinuityVersionRef"
            ],
            "characterContinuityVersionDigest": authority[
                "characterContinuityVersionDigest"
            ],
            "mappingSource": "EXPLICIT_CHARACTER_REF_MAPPING",
            "identities": locked_identities,
            "executionMode": root["manifest"]["executionMode"],
            "publicationAllowed": False,
            "state": "LOCKED",
            "createdAt": now,
            "createdBy": "v5.identity-lock.service",
            "version": 1,
        }
        identity_lock = {**lock_base, "payloadDigest": _digest(lock_base)}
        gate, replay = self.evidence.append_gate(
            GateAppend(
                workspace,
                run_ref,
                AUTHORITY_GATE,
                idempotency_key,
                root["payloadDigest"],
                request_digest,
                "ROOTS_READY",
                "AUTHORITY_READY",
                now,
                (
                    EvidenceFact(
                        "M6AuthorityDecision",
                        authority["authorityDecisionRef"],
                        1,
                        authority,
                        authority["payloadDigest"],
                    ),
                    EvidenceFact(
                        "IdentityLock",
                        identity_lock["identityLockRef"],
                        1,
                        identity_lock,
                        identity_lock["payloadDigest"],
                    ),
                ),
            )
        )
        return {
            "authorityDecision": self._fact(gate, "M6AuthorityDecision"),
            "identityLock": self._fact(gate, "IdentityLock"),
            "state": gate["toState"],
            "idempotentReplay": replay,
        }
