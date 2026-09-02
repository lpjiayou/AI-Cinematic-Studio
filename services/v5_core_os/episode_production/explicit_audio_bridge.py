"""Explicit M9 AudioRequirement to M12 request bridge.

The bridge records one immutable route decision on the existing Episode
Production evidence journal.  It creates an additive M12
``AudioGenerationRequest`` only for explicit speech, SFX or ambience
requirements.  It never calls a runtime, provider, media adapter or legacy
``GenerationRequest`` path.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping
from uuid import uuid4

from .audio import normalize_clone_speech_parameters, normalize_speech_parameters
from .audio_authority import (
    AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
    VOICE_ASSET_VERSION_V2_SCHEMA_VERSION,
    build_m9_audio_generation_request,
    build_requested_audio_provenance,
    validate_audio_generation_request,
    validate_rights_binding,
    validate_voice_asset_version,
)
from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .execution_method_planning import M8M9ExecutionMethodPlanningService
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
    _utc_now,
)
from .voice import K2VoiceLockService
from .voice_profile import K2VoiceProfileLineageService


AUDIO_REQUIREMENT_ROUTE_RECORD_KIND = "AudioRequirementRouteVersion"
AUDIO_REQUIREMENT_ROUTE_SCHEMA_VERSION = "v5.m9-m12-audio-requirement-route.v1"
AUDIO_CUE_TIMING_BINDING_SCHEMA_VERSION = "v5.m9-m12-audio-cue-timing-binding.v1"
M12_RUNTIME_STATE = "NOT_INSTALLED_G0_NOT_COMPLETE"
M12_RUNTIME_INSTALLED = False

AUDIO_ROUTE_DISPOSITIONS = frozenset(
    {
        "REQUEST_CREATED",
        "NO_REQUEST_SILENCE",
        "MUSIC_NOT_IMPLEMENTED",
    }
)
_REQUEST_KIND_BY_AUDIO_TYPE = {
    "DIALOGUE": "DIALOGUE_SYNTHESIS",
    "NARRATION": "NARRATION_SYNTHESIS",
    "SFX": "SFX_GENERATION",
    "AMBIENCE": "AMBIENCE_GENERATION",
}
_OUTPUT_TYPE_BY_AUDIO_TYPE = {
    "DIALOGUE": "DialogueAssetVersion",
    "NARRATION": "DialogueAssetVersion",
    "SFX": "SfxAssetVersion",
    "AMBIENCE": "AmbienceAssetVersion",
}
_SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
_CREATE_FIELDS = frozenset(
    {
        *_SCOPE_FIELDS,
        "productionRunRef",
        "executionMethodPlanVersionRef",
        "audioRequirementRef",
        "idempotencyKey",
    }
)
_CREATE_OPTIONAL_FIELDS = frozenset({"rightsBinding", "voiceAssetVersion"})
_ROUTE_FIELDS = frozenset(
    {
        "schemaVersion",
        "audioRequirementRouteRef",
        "audioRequirementRouteVersionRef",
        "routeVersion",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "executionMethodPlanVersionRef",
        "executionMethodPlanDigest",
        "audioRequirementRef",
        "audioRequirementDigest",
        "audioType",
        "routeDisposition",
        "voiceAssetVersionSnapshot",
        "audioGenerationRequest",
        "audioCueTimingBinding",
        "m12RuntimeState",
        "m12RuntimeInstalled",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_CUE_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "audioRequirementRef",
        "audioRequirementDigest",
        "audioGenerationRequestVersionRef",
        "audioGenerationRequestDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "audioRole",
        "timingReference",
        "timelineAuthority",
        "bindingState",
        "payloadDigest",
    }
)
_TIMING_FIELDS = frozenset({"startFrameInclusive", "endFrameExclusive"})


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


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RepositoryUnavailableError(f"stored {label} fields are invalid")
    result = deepcopy(dict(value))
    if not _is_digest(result.get("payloadDigest")) or _digest(
        {key: item for key, item in result.items() if key != "payloadDigest"}
    ) != result["payloadDigest"]:
        raise StaleInputError(f"stored {label} digest is stale")
    return result


def _stable_ref(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}-{_digest(value)[:32]}"


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise RepositoryUnavailableError("stored M9/M12 route payload is invalid")
    return deepcopy(dict(value))


class M9M12ExplicitAudioBridgeService:
    """Create zero or one M12 request from one current M9 requirement."""

    def __init__(
        self,
        execution_method_planning: M8M9ExecutionMethodPlanningService,
        evidence_repository: EpisodeProductionEvidenceRepository,
        voice_locks: K2VoiceLockService,
        voice_profile_lineage: K2VoiceProfileLineageService,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.execution_method_planning = execution_method_planning
        self.evidence_repository = evidence_repository
        self.voice_locks = voice_locks
        self.voice_profile_lineage = voice_profile_lineage
        self._ref_factory = ref_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self._clock = clock

    @staticmethod
    def _scope(command: Mapping[str, Any]) -> tuple[dict[str, str], str]:
        scope = {
            field: _required_ref(command.get(field), field)
            for field in _SCOPE_FIELDS
        }
        return scope, _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )

    def _current_requirement(
        self,
        scope: Mapping[str, str],
        run_ref: str,
        plan_version_ref: Any,
        requirement_ref: Any,
    ) -> dict[str, Any]:
        return self.execution_method_planning.resolve_current_audio_requirement(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
            _required_ref(
                plan_version_ref, "executionMethodPlanVersionRef"
            ),
            _required_ref(requirement_ref, "audioRequirementRef"),
        )

    @staticmethod
    def _normalized_inputs(
        command: Mapping[str, Any], requirement: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        audio_type = requirement["audioType"]
        rights_value = command.get("rightsBinding")
        voice_value = command.get("voiceAssetVersion")
        if audio_type in {"SILENCE", "MUSIC"}:
            if rights_value is not None or voice_value is not None:
                raise EpisodeProductionError(
                    "non-requesting AudioRequirement cannot accept request inputs"
                )
            return None, None
        if rights_value is None:
            raise EpisodeProductionError(
                "requesting AudioRequirement requires RightsBinding"
            )
        rights = validate_rights_binding(rights_value).as_dict()
        if audio_type in {"DIALOGUE", "NARRATION"}:
            if not isinstance(voice_value, Mapping):
                raise EpisodeProductionError(
                    "speech AudioRequirement requires VoiceAssetVersion"
                )
            voice = deepcopy(dict(voice_value))
        else:
            if voice_value is not None:
                raise EpisodeProductionError(
                    "non-speech AudioRequirement cannot select a voice"
                )
            voice = None
        return rights, voice

    @staticmethod
    def _request_digest(
        scope: Mapping[str, str],
        run_ref: str,
        resolved: Mapping[str, Any],
        rights: Mapping[str, Any] | None,
        voice: Mapping[str, Any] | None,
    ) -> str:
        plan = resolved["executionMethodPlan"]
        requirement = resolved["audioRequirement"]
        return _digest(
            {
                "schemaVersion": "v5.m9-m12-audio-route-request.v1",
                **scope,
                "productionRunRef": run_ref,
                "executionMethodPlanVersionRef": plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": plan["payloadDigest"],
                "audioRequirementRef": requirement["audioRequirementRef"],
                "audioRequirementDigest": requirement["payloadDigest"],
                "rightsBindingDigest": (
                    None if rights is None else rights["payloadDigest"]
                ),
                "voiceAssetVersionRef": (
                    None if voice is None else voice.get("assetVersionRef")
                ),
                "voiceAssetVersionDigest": (
                    None if voice is None else voice.get("payloadDigest")
                ),
            }
        )

    def _voice_context(
        self,
        scope: Mapping[str, str],
        run_ref: str,
        voice: Mapping[str, Any],
    ) -> dict[str, Any]:
        schema = voice.get("schemaVersion")
        if schema == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION:
            confirmed = self.voice_locks.get_confirmed_clone_voice_lock(
                scope["workspaceRef"],
                scope["projectRef"],
                scope["seriesRef"],
                _required_ref(voice.get("voiceIdentityRef"), "voiceIdentityRef"),
            )
            authority = (
                self.voice_profile_lineage.resolve_current_confirmed_voice_profile(
                    scope["workspaceRef"],
                    run_ref,
                    _required_ref(
                        voice.get("voiceProfileVersionRef"),
                        "voiceProfileVersionRef",
                    ),
                    voice.get("voiceProfileVersionDigest"),
                )
            )
            proof = authority.as_dict()
            wrapper = validate_voice_asset_version(
                voice,
                confirmed_voice_lock=confirmed,
                voice_profile_version=proof["voiceProfileVersion"],
                consent_grant_version=proof["consentGrantVersion"],
                source_recording_binding=proof["sourceRecordingBinding"],
                evaluated_at=proof["evaluatedAt"],
                current_voice_profile_authority=authority,
                require_current_authority=True,
            )
            return {
                "voiceAssetVersion": wrapper,
                "confirmedVoiceLock": confirmed,
                "voiceProfileVersion": proof["voiceProfileVersion"],
                "consentGrantVersion": proof["consentGrantVersion"],
                "sourceRecordingBinding": proof["sourceRecordingBinding"],
                "currentVoiceProfileAuthority": authority,
                "evaluatedAt": proof["evaluatedAt"],
            }
        character_ref = _required_ref(voice.get("characterRef"), "characterRef")
        confirmed = self.voice_locks.get_confirmed_voice_lock(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            character_ref,
        )
        wrapper = validate_voice_asset_version(
            voice, confirmed_voice_lock=confirmed
        )
        return {
            "voiceAssetVersion": wrapper,
            "confirmedVoiceLock": confirmed,
            "voiceProfileVersion": None,
            "consentGrantVersion": None,
            "sourceRecordingBinding": None,
            "currentVoiceProfileAuthority": None,
            "evaluatedAt": None,
        }

    @staticmethod
    def _voice_validation_kwargs(context: Mapping[str, Any] | None) -> dict[str, Any]:
        if context is None:
            return {}
        return {
            "confirmed_voice_lock": context["confirmedVoiceLock"],
            "voice_asset_version": context["voiceAssetVersion"],
            "evaluated_at": context["evaluatedAt"],
            "voice_profile_version": context["voiceProfileVersion"],
            "consent_grant_version": context["consentGrantVersion"],
            "source_recording_binding": context["sourceRecordingBinding"],
            "current_voice_profile_authority": context[
                "currentVoiceProfileAuthority"
            ],
        }

    @staticmethod
    def _speech_parameters(
        audio_type: str,
        source_text: str,
        voice_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        confirmed = voice_context["confirmedVoiceLock"]
        root = confirmed["voiceLock"]
        command = {
            "speechSynthesis": True,
            "text": source_text,
            "voiceRef": root["voiceRef"],
            "audioRole": audio_type.lower(),
        }
        if voice_context["voiceProfileVersion"] is not None:
            return normalize_clone_speech_parameters(
                command, confirmed_voice_lock=confirmed
            )
        return normalize_speech_parameters(
            command, confirmed_voice_lock=confirmed
        )

    def _generation_request(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        resolved: Mapping[str, Any],
        rights: Mapping[str, Any],
        voice: Mapping[str, Any] | None,
        created_at: str,
    ) -> dict[str, Any]:
        plan = resolved["executionMethodPlan"]
        requirement = resolved["audioRequirement"]
        audio_type = requirement["audioType"]
        identity = {
            "audioRequirementRef": requirement["audioRequirementRef"],
            "audioRequirementDigest": requirement["payloadDigest"],
        }
        request_ref = _stable_ref("m9-audio-generation-request", identity)
        voice_context = (
            None
            if voice is None
            else self._voice_context(scope, run_ref, voice)
        )
        if audio_type in {"DIALOGUE", "NARRATION"}:
            if not isinstance(resolved.get("sourceText"), str) or voice_context is None:
                raise RepositoryUnavailableError(
                    "speech AudioRequirement authority is incomplete"
                )
            if (
                audio_type == "DIALOGUE"
                and voice_context["voiceAssetVersion"].as_dict()["characterRef"]
                != requirement["speakerCharacterRef"]
            ):
                raise StaleInputError(
                    "dialogue VoiceAssetVersion speaker binding is stale"
                )
            parameters = self._speech_parameters(
                audio_type, resolved["sourceText"], voice_context
            )
            source_ref = _stable_ref(
                "m9-dialogue" if audio_type == "DIALOGUE" else "m9-narration",
                identity,
            )
            request_spec = {
                "speechRole": audio_type.lower(),
                "scriptVersionRef": requirement["scriptVersionRef"],
                "scriptVersionDigest": requirement["scriptVersionDigest"],
                "dialogueRef": source_ref if audio_type == "DIALOGUE" else None,
                "narrationRef": source_ref if audio_type == "NARRATION" else None,
                "voiceAssetVersionRef": voice_context[
                    "voiceAssetVersion"
                ].as_dict()["assetVersionRef"],
                "voiceAssetVersionDigest": voice_context[
                    "voiceAssetVersion"
                ].as_dict()["payloadDigest"],
                "language": voice_context["confirmedVoiceLock"][
                    "voiceLockVersion"
                ]["languageCode"],
                "normalizedSpeechParameters": parameters,
                "sourceAudioCueRefs": [],
            }
            parameters_digest = _digest(parameters)
        else:
            spec_digest = _digest(
                {
                    "schemaVersion": "v5.m9-programmatic-audio-spec.v1",
                    "audioRequirementRef": requirement["audioRequirementRef"],
                    "audioRequirementDigest": requirement["payloadDigest"],
                    "audioRole": audio_type.lower(),
                    "timingReference": requirement["timingReference"],
                }
            )
            request_spec = {
                (
                    "sfxKind" if audio_type == "SFX" else "ambienceKind"
                ): (
                    "M9_EXPLICIT_SFX"
                    if audio_type == "SFX"
                    else "M9_EXPLICIT_AMBIENCE"
                ),
                "synthesisSpecDigest": spec_digest,
                "sourceAudioCueRefs": [],
            }
            parameters_digest = spec_digest
        provenance = build_requested_audio_provenance(
            {
                "originKind": "M9_EXPLICIT_AUDIO_REQUIREMENT",
                "adapterIdentity": "M12_RUNTIME_NOT_INSTALLED",
                "parametersDigest": parameters_digest,
                "sourceRefs": [
                    {
                        "sourceRef": requirement["audioRequirementRef"],
                        "sourceDigest": requirement["payloadDigest"],
                    },
                    {
                        "sourceRef": requirement["scriptVersionRef"],
                        "sourceDigest": requirement["scriptVersionDigest"],
                    },
                    {
                        "sourceRef": requirement["creativeShotVersionRef"],
                        "sourceDigest": requirement[
                            "creativeShotVersionDigest"
                        ],
                    },
                ],
            }
        )
        command = {
            "requestKind": _REQUEST_KIND_BY_AUDIO_TYPE[audio_type],
            **scope,
            "productionRunRef": run_ref,
            "generationRequestRef": request_ref,
            "generationRequestVersionRef": f"{request_ref}-v1",
            "version": 1,
            "supersedesGenerationRequestVersionRef": None,
            "supersedesGenerationRequestVersionDigest": None,
            "assetRequirementRef": requirement["audioRequirementRef"],
            "assetRequirementDigest": requirement["payloadDigest"],
            "outputAssetVersionType": _OUTPUT_TYPE_BY_AUDIO_TYPE[audio_type],
            "outputTarget": "ASSET_VERSION",
            "requestSpec": request_spec,
            "rightsBinding": deepcopy(dict(rights)),
            "requestedProvenance": provenance,
            "createdBy": "v5.m9-m12-explicit-audio-bridge.v1",
            "createdAt": created_at,
        }
        return build_m9_audio_generation_request(
            command,
            audio_requirement=requirement,
            execution_method_plan=plan,
            **self._voice_validation_kwargs(voice_context),
        )

    @staticmethod
    def _cue_binding(
        request: Mapping[str, Any], requirement: Mapping[str, Any]
    ) -> dict[str, Any]:
        return _seal(
            {
                "schemaVersion": AUDIO_CUE_TIMING_BINDING_SCHEMA_VERSION,
                "audioRequirementRef": requirement["audioRequirementRef"],
                "audioRequirementDigest": requirement["payloadDigest"],
                "audioGenerationRequestVersionRef": request[
                    "generationRequestVersionRef"
                ],
                "audioGenerationRequestDigest": request["payloadDigest"],
                "creativeShotVersionRef": requirement[
                    "creativeShotVersionRef"
                ],
                "creativeShotVersionDigest": requirement[
                    "creativeShotVersionDigest"
                ],
                "audioRole": request["audioRole"],
                "timingReference": deepcopy(requirement["timingReference"]),
                "timelineAuthority": "M13_EXISTING_TIMELINE_AUTHORITY",
                "bindingState": "AWAITING_TYPED_AUDIO_ASSET",
            }
        )

    def _build_payload(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        resolved: Mapping[str, Any],
        rights: Mapping[str, Any] | None,
        voice: Mapping[str, Any] | None,
        route_version: int,
        created_at: str,
    ) -> dict[str, Any]:
        plan = resolved["executionMethodPlan"]
        requirement = resolved["audioRequirement"]
        audio_type = requirement["audioType"]
        request = None
        cue_binding = None
        if audio_type in _REQUEST_KIND_BY_AUDIO_TYPE:
            if rights is None:
                raise RepositoryUnavailableError("RightsBinding is unavailable")
            request = self._generation_request(
                scope=scope,
                run_ref=run_ref,
                resolved=resolved,
                rights=rights,
                voice=voice,
                created_at=created_at,
            )
            cue_binding = self._cue_binding(request, requirement)
            disposition = "REQUEST_CREATED"
        elif audio_type == "SILENCE":
            disposition = "NO_REQUEST_SILENCE"
        elif audio_type == "MUSIC":
            disposition = "MUSIC_NOT_IMPLEMENTED"
        else:
            raise RepositoryUnavailableError("AudioRequirement type is invalid")
        identity = {
            "productionRunRef": run_ref,
            "audioRequirementRef": requirement["audioRequirementRef"],
        }
        return _seal(
            {
                "schemaVersion": AUDIO_REQUIREMENT_ROUTE_SCHEMA_VERSION,
                "audioRequirementRouteRef": _stable_ref(
                    "m9-m12-audio-route", identity
                ),
                "audioRequirementRouteVersionRef": _required_ref(
                    self._ref_factory("m9-m12-audio-route-version"),
                    "audioRequirementRouteVersionRef",
                ),
                "routeVersion": route_version,
                **scope,
                "productionRunRef": run_ref,
                "executionMethodPlanVersionRef": plan[
                    "executionMethodPlanVersionRef"
                ],
                "executionMethodPlanDigest": plan["payloadDigest"],
                "audioRequirementRef": requirement["audioRequirementRef"],
                "audioRequirementDigest": requirement["payloadDigest"],
                "audioType": audio_type,
                "routeDisposition": disposition,
                "voiceAssetVersionSnapshot": (
                    None if voice is None else deepcopy(dict(voice))
                ),
                "audioGenerationRequest": request,
                "audioCueTimingBinding": cue_binding,
                "m12RuntimeState": M12_RUNTIME_STATE,
                "m12RuntimeInstalled": M12_RUNTIME_INSTALLED,
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )

    @staticmethod
    def _validate_cue_binding(
        value: Any,
        *,
        request: Mapping[str, Any],
        requirement: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = _verify_sealed(value, _CUE_BINDING_FIELDS, "AudioCue timing binding")
        timing = result["timingReference"]
        if not isinstance(timing, Mapping) or set(timing) != _TIMING_FIELDS:
            raise RepositoryUnavailableError(
                "stored AudioCue timing reference is invalid"
            )
        if (
            result["schemaVersion"] != AUDIO_CUE_TIMING_BINDING_SCHEMA_VERSION
            or result["audioRequirementRef"] != request["audioRequirementRef"]
            or result["audioRequirementDigest"]
            != request["audioRequirementDigest"]
            or result["audioGenerationRequestVersionRef"]
            != request["generationRequestVersionRef"]
            or result["audioGenerationRequestDigest"] != request["payloadDigest"]
            or result["creativeShotVersionRef"]
            != request["creativeShotVersionRef"]
            or result["creativeShotVersionDigest"]
            != request["creativeShotVersionDigest"]
            or result["audioRole"] != request["audioRole"]
            or result["timingReference"] != request["timingReference"]
            or result["timelineAuthority"]
            != "M13_EXISTING_TIMELINE_AUTHORITY"
            or result["bindingState"] != "AWAITING_TYPED_AUDIO_ASSET"
        ):
            raise RepositoryUnavailableError(
                "stored AudioCue timing binding is stale"
            )
        if requirement is not None and (
            result["audioRequirementRef"]
            != requirement["audioRequirementRef"]
            or result["audioRequirementDigest"] != requirement["payloadDigest"]
            or result["timingReference"] != requirement["timingReference"]
        ):
            raise StaleInputError("AudioCue timing requirement changed")
        return result

    def _validate_payload(
        self,
        payload: Any,
        *,
        resolved: Mapping[str, Any] | None = None,
        voice_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        value = _verify_sealed(payload, _ROUTE_FIELDS, "M9/M12 route")
        for field in (
            "audioRequirementRouteRef",
            "audioRequirementRouteVersionRef",
            *_SCOPE_FIELDS,
            "productionRunRef",
            "executionMethodPlanVersionRef",
            "audioRequirementRef",
        ):
            _required_ref(value[field], field)
        for field in (
            "executionMethodPlanDigest",
            "audioRequirementDigest",
        ):
            if not _is_digest(value[field]):
                raise RepositoryUnavailableError(
                    f"stored {field} is invalid"
                )
        if (
            value["schemaVersion"] != AUDIO_REQUIREMENT_ROUTE_SCHEMA_VERSION
            or isinstance(value["routeVersion"], bool)
            or not isinstance(value["routeVersion"], int)
            or value["routeVersion"] < 1
            or value["routeDisposition"] not in AUDIO_ROUTE_DISPOSITIONS
            or value["m12RuntimeState"] != M12_RUNTIME_STATE
            or value["m12RuntimeInstalled"] is not False
            or value["publicationAllowed"] is not False
        ):
            raise RepositoryUnavailableError("stored M9/M12 route semantics are invalid")
        request = value["audioGenerationRequest"]
        cue = value["audioCueTimingBinding"]
        voice_snapshot = value["voiceAssetVersionSnapshot"]
        expected_disposition = {
            "SILENCE": "NO_REQUEST_SILENCE",
            "MUSIC": "MUSIC_NOT_IMPLEMENTED",
        }.get(value["audioType"], "REQUEST_CREATED")
        if value["routeDisposition"] != expected_disposition:
            raise RepositoryUnavailableError("stored M9/M12 route disposition is invalid")
        if expected_disposition == "REQUEST_CREATED":
            if not isinstance(request, Mapping) or not isinstance(cue, Mapping):
                raise RepositoryUnavailableError("stored M12 request is unavailable")
            if request.get("schemaVersion") != AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION:
                raise RepositoryUnavailableError("stored M12 request schema is invalid")
            if resolved is not None:
                kwargs = self._voice_validation_kwargs(voice_context)
                validated = validate_audio_generation_request(
                    request,
                    audio_requirement=resolved["audioRequirement"],
                    execution_method_plan=resolved["executionMethodPlan"],
                    **kwargs,
                ).as_dict()
                if validated != request:
                    raise RepositoryUnavailableError("stored M12 request changed")
            elif not _is_digest(request.get("payloadDigest")) or _digest(
                {
                    key: item
                    for key, item in request.items()
                    if key != "payloadDigest"
                }
            ) != request.get("payloadDigest"):
                raise StaleInputError("stored M12 request digest is stale")
            self._validate_cue_binding(
                cue,
                request=request,
                requirement=(
                    None if resolved is None else resolved["audioRequirement"]
                ),
            )
        elif request is not None or cue is not None:
            raise RepositoryUnavailableError(
                "non-requesting AudioRequirement created M12 artifacts"
            )
        if value["audioType"] in {"DIALOGUE", "NARRATION"}:
            if not isinstance(voice_snapshot, Mapping):
                raise RepositoryUnavailableError(
                    "stored speech VoiceAssetVersion snapshot is unavailable"
                )
        elif voice_snapshot is not None:
            raise RepositoryUnavailableError(
                "non-speech route cannot store a VoiceAssetVersion snapshot"
            )
        if resolved is not None:
            plan = resolved["executionMethodPlan"]
            requirement = resolved["audioRequirement"]
            if (
                value["executionMethodPlanVersionRef"]
                != plan["executionMethodPlanVersionRef"]
                or value["executionMethodPlanDigest"] != plan["payloadDigest"]
                or value["audioRequirementRef"]
                != requirement["audioRequirementRef"]
                or value["audioRequirementDigest"] != requirement["payloadDigest"]
                or value["audioType"] != requirement["audioType"]
            ):
                raise StaleInputError("M9/M12 route upstream binding is stale")
        return value

    def _records(
        self, workspace: str, run_ref: str
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result = []
        for expected, record in enumerate(
            self.evidence_repository.list_records(
                workspace,
                run_ref,
                record_kind=AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
            ),
            start=1,
        ):
            payload = self._validate_payload(_payload(record))
            if (
                record.get("recordKind") != AUDIO_REQUIREMENT_ROUTE_RECORD_KIND
                or record.get("recordRef")
                != payload["audioRequirementRouteRef"]
                or record.get("recordVersion") != payload["routeVersion"]
                or record.get("payloadDigest") != payload["payloadDigest"]
                or payload["routeVersion"] != expected
            ):
                raise RepositoryUnavailableError(
                    "stored M9/M12 route envelope is invalid"
                )
            result.append((deepcopy(dict(record)), payload))
        return result

    def _resolved_voice_context(
        self,
        scope: Mapping[str, str],
        run_ref: str,
        command_voice: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if command_voice is None:
            return None
        return self._voice_context(scope, run_ref, command_voice)

    def _payload_is_current(
        self,
        payload: Mapping[str, Any],
        scope: Mapping[str, str],
        run_ref: str,
        *,
        voice: Mapping[str, Any] | None,
    ) -> bool:
        try:
            resolved = self._current_requirement(
                scope,
                run_ref,
                payload["executionMethodPlanVersionRef"],
                payload["audioRequirementRef"],
            )
            context = self._resolved_voice_context(
                scope,
                run_ref,
                (
                    voice
                    if voice is not None
                    else payload.get("voiceAssetVersionSnapshot")
                ),
            )
            self._validate_payload(
                payload, resolved=resolved, voice_context=context
            )
            return True
        except EpisodeProductionError:
            return False

    def create_route(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or not _CREATE_FIELDS.issubset(
            command
        ) or not set(command).issubset(_CREATE_FIELDS | _CREATE_OPTIONAL_FIELDS):
            raise EpisodeProductionError(
                "command fields do not match the M9/M12 bridge contract"
            )
        scope, run_ref = self._scope(command)
        key = _idempotency_key(command.get("idempotencyKey"))
        resolved = self._current_requirement(
            scope,
            run_ref,
            command.get("executionMethodPlanVersionRef"),
            command.get("audioRequirementRef"),
        )
        rights, voice = self._normalized_inputs(
            command, resolved["audioRequirement"]
        )
        request_digest = self._request_digest(
            scope, run_ref, resolved, rights, voice
        )
        records = self._records(scope["workspaceRef"], run_ref)
        existing = self.evidence_repository.get_record_by_idempotency_key(
            scope["workspaceRef"], run_ref, key
        )
        if existing is not None:
            if (
                existing.get("recordKind")
                != AUDIO_REQUIREMENT_ROUTE_RECORD_KIND
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError(
                    "M9/M12 bridge idempotency content changed"
                )
            payload = self._validate_payload(_payload(existing))
            current = self._payload_is_current(
                payload, scope, run_ref, voice=voice
            )
            return {
                **payload,
                "currentness": "CURRENT" if current else "STALE",
                "idempotentReplay": True,
            }

        journal_head = self.evidence_repository.record_journal_head(
            scope["workspaceRef"], run_ref
        )
        created_at = self._clock()
        payload = self._build_payload(
            scope=scope,
            run_ref=run_ref,
            resolved=resolved,
            rights=rights,
            voice=voice,
            route_version=len(records) + 1,
            created_at=created_at,
        )
        voice_context = self._resolved_voice_context(
            scope, run_ref, voice
        )
        self._validate_payload(
            payload, resolved=resolved, voice_context=voice_context
        )
        refreshed = self._current_requirement(
            scope,
            run_ref,
            payload["executionMethodPlanVersionRef"],
            payload["audioRequirementRef"],
        )
        if (
            refreshed["executionMethodPlan"]["payloadDigest"]
            != resolved["executionMethodPlan"]["payloadDigest"]
            or refreshed["audioRequirement"]["payloadDigest"]
            != resolved["audioRequirement"]["payloadDigest"]
            or refreshed.get("sourceText") != resolved.get("sourceText")
        ):
            raise StaleInputError("M9 audio authority changed before append")
        if voice is not None:
            self._resolved_voice_context(scope, run_ref, voice)
        record = EvidenceRecord(
            workspaceRef=scope["workspaceRef"],
            productionRunRef=run_ref,
            recordKind=AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
            recordRef=payload["audioRequirementRouteRef"],
            recordVersion=payload["routeVersion"],
            idempotencyKey=key,
            requestDigest=request_digest,
            createdAt=created_at,
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        stored, replayed = self.evidence_repository.append_records(
            (record,), expected_record_journal_head=journal_head
        )
        stored_payload = self._validate_payload(_payload(stored[0]))
        return {
            **stored_payload,
            "currentness": "CURRENT",
            "idempotentReplay": replayed,
        }

    def get_route(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        audio_requirement_route_version_ref: str | None = None,
        *,
        voice_asset_version: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope = {
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "projectRef": _required_ref(project_ref, "projectRef"),
            "seriesRef": _required_ref(series_ref, "seriesRef"),
            "episodeRef": _required_ref(episode_ref, "episodeRef"),
        }
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        records = self._records(scope["workspaceRef"], run_ref)
        if audio_requirement_route_version_ref is None:
            selected = records[-1] if records else None
        else:
            version_ref = _required_ref(
                audio_requirement_route_version_ref,
                "audioRequirementRouteVersionRef",
            )
            selected = next(
                (
                    item
                    for item in records
                    if item[1]["audioRequirementRouteVersionRef"]
                    == version_ref
                ),
                None,
            )
        if selected is None or any(
            selected[1].get(field) != expected
            for field, expected in scope.items()
        ):
            raise RecordNotFoundError("AudioRequirementRouteVersion was not found")
        payload = selected[1]
        current = self._payload_is_current(
            payload,
            scope,
            run_ref,
            voice=voice_asset_version,
        )
        return {
            **payload,
            "currentness": "CURRENT" if current else "STALE",
            "idempotentReplay": False,
        }


__all__ = [
    "AUDIO_CUE_TIMING_BINDING_SCHEMA_VERSION",
    "AUDIO_REQUIREMENT_ROUTE_RECORD_KIND",
    "AUDIO_REQUIREMENT_ROUTE_SCHEMA_VERSION",
    "AUDIO_ROUTE_DISPOSITIONS",
    "M12_RUNTIME_INSTALLED",
    "M12_RUNTIME_STATE",
    "M9M12ExplicitAudioBridgeService",
]
