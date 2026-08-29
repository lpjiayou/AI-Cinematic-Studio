"""M12 voice-bound dialogue requests and canonical audio AssetVersions.

This module deliberately does not execute a TTS engine.  It plans immutable,
provider-neutral speech requests from the current ExecutableShotGraph lineage and
validates the proposed audio AssetVersion output contract without admission or
storage.  The legacy G4/G5 deterministic sine path remains a separate compatibility
path.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Mapping, Protocol

from .assets import ASSET_REQUIREMENT_SCHEMA_VERSION, GENERATION_REQUEST_SCHEMA_VERSION
from .foundation import (
    EpisodeProductionError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _required_ref,
)
from .shot_graph import K2ShotGraphService, require_legacy_executable_graph
from .voice import validate_confirmed_voice_lock_bundle


AUDIO_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-audio-asset-version.v1"
AUDIO_REQUEST_PLANNER_ID = "v5.k2.audio-request-planner.v1"
AUDIO_ASSET_ADMISSION_ID = "v5.k2.audio-admission.v1"
AUDIO_STORAGE_PREFIX = "asset-versions/audio/"
SPEECH_EMOTION_TAGS = frozenset({"neutral", "tense", "whisper", "weary"})
AUDIO_ROLES = frozenset({"dialogue", "narration"})
_AUDIO_ASSET_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "version",
        "assetKind",
        "mediaKind",
        "mediaType",
        "assetAdmissionRef",
        "assetAdmissionVersion",
        "assetAdmissionDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceScriptSpan",
        "dialogueOrdinal",
        "dialogueSourceDigest",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "engineFamily",
        "voiceId",
        "generationParametersDigest",
        "audioRole",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "sha256",
        "sampleRate",
        "channels",
        "probe",
        "supersedesAssetVersionRef",
        "supersedesAssetVersionDigest",
        "provenance",
        "rightsState",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)


class ConfirmedVoiceLockReader(Protocol):
    def get_confirmed_voice_lock(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        character_ref: str,
    ) -> Mapping[str, Any]: ...


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 8_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in value
        )
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _verify_sealed(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EpisodeProductionError(f"{field} must be an object")
    result = deepcopy(dict(value))
    claimed = result.pop("payloadDigest", None)
    if claimed != _digest(result):
        raise StaleInputError(f"{field} payload digest is invalid")
    result["payloadDigest"] = claimed
    return result


def _confirmed_voice_version(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the VoiceLock public bundle without trusting caller aliases."""

    if value is None:
        raise UpstreamNotReadyError("confirmed VoiceLock is required")
    return validate_confirmed_voice_lock_bundle(value)["voiceLockVersion"]


def normalize_speech_parameters(
    value: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one audio parameter object while preserving the legacy false branch.

    Existing ``speechSynthesis=false`` requests are returned byte-for-byte (as a
    detached copy).  The new true branch is closed-world and fills only the two
    documented defaults.
    """

    if not isinstance(value, Mapping):
        raise EpisodeProductionError("audio parameters must be an object")
    parameters = deepcopy(dict(value))
    speech_synthesis = parameters.get("speechSynthesis")
    if speech_synthesis is False:
        return parameters
    allowed = {
        "speechSynthesis",
        "text",
        "voiceRef",
        "emotionTag",
        "sampleRate",
        "channels",
        "audioRole",
    }
    if speech_synthesis is not True or set(parameters) - allowed:
        raise EpisodeProductionError("speech synthesis parameters are invalid")
    text = _text(parameters.get("text"), "text", maximum=2_000)
    voice_ref = _required_ref(parameters.get("voiceRef"), "voiceRef")
    emotion = parameters.get("emotionTag")
    if emotion is not None and (
        not isinstance(emotion, str) or emotion not in SPEECH_EMOTION_TAGS
    ):
        raise EpisodeProductionError("emotionTag is invalid")
    sample_rate = _integer(
        parameters.get("sampleRate", 48_000),
        "sampleRate",
        minimum=8_000,
        maximum=384_000,
    )
    channels = _integer(
        parameters.get("channels", 1), "channels", minimum=1, maximum=2
    )
    audio_role = parameters.get("audioRole")
    if not isinstance(audio_role, str) or audio_role not in AUDIO_ROLES:
        raise EpisodeProductionError("audioRole is invalid")
    if confirmed_voice_lock is None:
        raise UpstreamNotReadyError("confirmed VoiceLock is required")
    version = _confirmed_voice_version(confirmed_voice_lock)
    if version.get("voiceRef") != voice_ref:
        raise UpstreamNotReadyError("voiceRef is not the confirmed VoiceLock")
    normalized: dict[str, Any] = {
        "speechSynthesis": True,
        "text": text,
        "voiceRef": voice_ref,
        "sampleRate": sample_rate,
        "channels": channels,
        "audioRole": audio_role,
    }
    if emotion is not None:
        normalized["emotionTag"] = emotion
    return normalized


def _source_dialogue_spans(shot: Mapping[str, Any]) -> list[str]:
    raw = shot.get("sourceScriptSpans")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise StaleInputError("CreativeShotVersion source spans are malformed")
    return [item for item in raw if "/dialogue/" in item]


def _voice_bundle(
    reader: ConfirmedVoiceLockReader,
    *,
    workspace_ref: str,
    project_ref: str,
    series_ref: str,
    character_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        bundle = reader.get_confirmed_voice_lock(
            workspace_ref, project_ref, series_ref, character_ref
        )
    except EpisodeProductionError:
        raise
    except Exception as exc:
        raise RepositoryUnavailableError("VoiceLock repository is unavailable") from exc
    version = _confirmed_voice_version(bundle)
    if (
        version.get("workspaceRef") != workspace_ref
        or version.get("projectRef") != project_ref
        or version.get("seriesRef") != series_ref
        or version.get("characterRef") != character_ref
    ):
        raise StaleInputError("confirmed VoiceLock scope is inconsistent")
    return deepcopy(dict(bundle)), version


def validate_audio_asset_version_contract(value: Any) -> dict[str, Any]:
    """Validate the proposed M12 output shape without admitting or storing it."""

    asset = _verify_sealed(value, "audio AssetVersion")
    if set(asset) != _AUDIO_ASSET_VERSION_FIELDS:
        raise RepositoryUnavailableError(
            "audio AssetVersion fields do not match the contract"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "assetAdmissionRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationResultRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "engineFamily",
        "voiceId",
        "artifactEvidenceRef",
        "artifactRef",
    ):
        _required_ref(asset.get(field), field)
    for field in (
        "assetRequirementDigest",
        "assetAdmissionDigest",
        "generationRequestDigest",
        "generationResultDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "dialogueSourceDigest",
        "voiceLockDigest",
        "generationParametersDigest",
        "artifactEvidenceDigest",
        "sha256",
    ):
        _sha256(asset.get(field), field)
    audio_role = asset.get("audioRole")
    if (
        asset.get("schemaVersion") != AUDIO_ASSET_VERSION_SCHEMA_VERSION
        or asset.get("assetKind") != "audio"
        or asset.get("mediaKind") != "audio"
        or asset.get("mediaType") != "audio/wav"
        or not isinstance(audio_role, str)
        or audio_role not in AUDIO_ROLES
        or asset.get("provenance") != "LOCAL_EVIDENCE"
        or asset.get("rightsState") != "LOCAL_EVIDENCE_ONLY"
        or asset.get("state") != "REGISTERED"
        or asset.get("immutable") is not True
        or asset.get("publicationAllowed") is not False
        or asset.get("createdBy") != AUDIO_ASSET_ADMISSION_ID
    ):
        raise RepositoryUnavailableError("audio AssetVersion semantics are invalid")
    _text(asset.get("sourceScriptSpan"), "sourceScriptSpan")
    _text(asset.get("createdAt"), "createdAt", maximum=64)
    version = _integer(asset.get("version"), "version", minimum=1, maximum=10_000)
    _integer(
        asset.get("assetAdmissionVersion"),
        "assetAdmissionVersion",
        minimum=1,
        maximum=10_000,
    )
    _integer(asset.get("dialogueOrdinal"), "dialogueOrdinal", minimum=1, maximum=10_000)
    _integer(asset.get("byteSize"), "byteSize", minimum=1, maximum=10_000_000_000)
    _integer(asset.get("sampleRate"), "sampleRate", minimum=8_000, maximum=384_000)
    _integer(asset.get("channels"), "channels", minimum=1, maximum=2)
    predecessor_ref = asset.get("supersedesAssetVersionRef")
    predecessor_digest = asset.get("supersedesAssetVersionDigest")
    if version == 1:
        if predecessor_ref is not None or predecessor_digest is not None:
            raise RepositoryUnavailableError(
                "initial audio AssetVersion cannot have a predecessor"
            )
    else:
        _required_ref(predecessor_ref, "supersedesAssetVersionRef")
        _sha256(predecessor_digest, "supersedesAssetVersionDigest")
        if predecessor_ref == asset.get("assetVersionRef"):
            raise RepositoryUnavailableError(
                "audio AssetVersion cannot supersede itself"
            )
    probe = asset.get("probe")
    if not isinstance(probe, Mapping) or set(probe) != {
        "sampleRate",
        "channels",
        "durationSeconds",
        "codec",
        "container",
    }:
        raise RepositoryUnavailableError("audio AssetVersion probe is invalid")
    duration = probe.get("durationSeconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
        or probe.get("sampleRate") != asset.get("sampleRate")
        or probe.get("channels") != asset.get("channels")
        or probe.get("container") != "wav"
    ):
        raise RepositoryUnavailableError("audio AssetVersion probe is inconsistent")
    _text(probe.get("codec"), "probe.codec", maximum=64)
    storage_key = asset.get("storageKey")
    if (
        not isinstance(storage_key, str)
        or not storage_key.startswith(AUDIO_STORAGE_PREFIX)
        or storage_key.startswith("/")
        or ".." in storage_key.split("/")
        or storage_key.endswith("/")
    ):
        raise RepositoryUnavailableError("audio AssetVersion storage path is invalid")
    return asset


class K2AudioProductionService:
    """Provider-neutral M12 contract service; it never invokes a TTS engine."""

    def __init__(
        self,
        shot_graph: K2ShotGraphService,
        voice_locks: ConfirmedVoiceLockReader,
    ) -> None:
        self.shot_graph = shot_graph
        self.voice_locks = voice_locks

    @staticmethod
    def _shot_lineage(
        verified: Mapping[str, Any], graph_node: Mapping[str, Any]
    ) -> dict[str, Any]:
        shots = verified.get("creativeShotVersions")
        if not isinstance(shots, list):
            raise RepositoryUnavailableError("CreativeShotVersion bundle is unavailable")
        matches = [
            item
            for item in shots
            if isinstance(item, Mapping)
            and item.get("creativeShotVersionRef")
            == graph_node.get("creativeShotVersionRef")
            and item.get("payloadDigest") == graph_node.get("payloadDigest")
        ]
        if len(matches) != 1:
            raise StaleInputError("ExecutableShotGraph shot lineage is ambiguous")
        shot = _verify_sealed(matches[0], "CreativeShotVersion")
        if shot.get("creativeShotRef") != graph_node.get("creativeShotRef"):
            raise StaleInputError("ExecutableShotGraph shot ref is stale")
        return shot

    @staticmethod
    def _character_by_name(shot: Mapping[str, Any]) -> dict[str, str]:
        locks = shot.get("requiredCharacterIdentityLocks")
        if not isinstance(locks, list) or not all(
            isinstance(item, Mapping) for item in locks
        ):
            raise StaleInputError("shot character identity bindings are unavailable")
        result: dict[str, str] = {}
        character_refs: set[str] = set()
        for item in locks:
            name = item.get("scriptCharacterName")
            character_ref = item.get("characterRef")
            if (
                not isinstance(name, str)
                or not isinstance(character_ref, str)
                or name in result
                or character_ref in character_refs
            ):
                raise StaleInputError("shot character identity bindings are ambiguous")
            result[name] = character_ref
            character_refs.add(character_ref)
        return result

    @staticmethod
    def _requirement(
        *,
        root: Mapping[str, Any],
        graph: Mapping[str, Any],
        shot: Mapping[str, Any],
        line: Mapping[str, Any],
        source_span: str,
        dialogue_ordinal: int,
        global_ordinal: int,
        voice_version: Mapping[str, Any],
    ) -> dict[str, Any]:
        semantic = {
            "workspaceRef": root["workspaceRef"],
            "productionRunRef": root["productionRunRef"],
            "creativeShotVersionRef": shot["creativeShotVersionRef"],
            "creativeShotDigest": shot["payloadDigest"],
            "dialogueOrdinal": dialogue_ordinal,
            "dialogueSourceDigest": _digest(
                {
                    "scriptVersionRef": root["scriptVersionRef"],
                    "scriptSceneRef": shot["scriptSceneRef"],
                    "sourceScriptSpan": source_span,
                    "line": deepcopy(dict(line)),
                }
            ),
            "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
            "voiceLockDigest": voice_version["payloadDigest"],
        }
        requirement_ref = "m12-dialogue-requirement-" + _digest(semantic)[:32]
        return _sealed(
            {
                "schemaVersion": ASSET_REQUIREMENT_SCHEMA_VERSION,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "assetRequirementRef": requirement_ref,
                "version": 1,
                "ordinal": global_ordinal,
                "requirementKey": (
                    f"shot-dialogue:{shot['creativeShotRef']}:{dialogue_ordinal}"
                ),
                "requirementType": "shot-dialogue-audio",
                "required": True,
                "mediaType": "audio/wav",
                "creativeShotRef": shot["creativeShotRef"],
                "creativeShotVersionRef": shot["creativeShotVersionRef"],
                "creativeShotDigest": shot["payloadDigest"],
                "scriptRef": root["scriptRef"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "scriptSceneRef": shot["scriptSceneRef"],
                "sourceScriptSpan": source_span,
                "dialogueOrdinal": dialogue_ordinal,
                "dialogueSourceDigest": semantic["dialogueSourceDigest"],
                "characterRef": voice_version["characterRef"],
                "voiceRef": voice_version["voiceRef"],
                "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
                "voiceLockDigest": voice_version["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "resolutionState": "GENERATION_REQUESTED",
                "resolutionKind": "M12_TTS_ADAPTER_REQUIRED",
                "requestedProvenance": "LOCAL_EVIDENCE",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "publicationAllowed": False,
                "createdBy": AUDIO_REQUEST_PLANNER_ID,
                "createdAt": graph["createdAt"],
            }
        )

    @staticmethod
    def _request(
        *,
        root: Mapping[str, Any],
        graph: Mapping[str, Any],
        shot: Mapping[str, Any],
        line: Mapping[str, Any],
        source_span: str,
        dialogue_ordinal: int,
        global_ordinal: int,
        requirement: Mapping[str, Any],
        voice_bundle: Mapping[str, Any],
        voice_version: Mapping[str, Any],
    ) -> dict[str, Any]:
        parameters = normalize_speech_parameters(
            {
                "speechSynthesis": True,
                "text": line.get("text"),
                "voiceRef": voice_version["voiceRef"],
                "sampleRate": 48_000,
                "channels": 1,
                "audioRole": "dialogue",
            },
            confirmed_voice_lock=voice_bundle,
        )
        semantic = {
            "assetRequirementDigest": requirement["payloadDigest"],
            "creativeShotDigest": shot["payloadDigest"],
            "dialogueSourceDigest": requirement["dialogueSourceDigest"],
            "voiceLockDigest": voice_version["payloadDigest"],
            "parameters": parameters,
        }
        request_ref = "m12-dialogue-generation-request-" + _digest(semantic)[:32]
        return _sealed(
            {
                "schemaVersion": GENERATION_REQUEST_SCHEMA_VERSION,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "generationRequestRef": request_ref,
                "generationRequestVersionRef": f"{request_ref}-v1",
                "version": 1,
                "ordinal": global_ordinal,
                "assetRequirementRef": requirement["assetRequirementRef"],
                "assetRequirementDigest": requirement["payloadDigest"],
                "creativeShotRef": shot["creativeShotRef"],
                "creativeShotVersionRef": shot["creativeShotVersionRef"],
                "creativeShotDigest": shot["payloadDigest"],
                "scriptRef": root["scriptRef"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "scriptSceneRef": shot["scriptSceneRef"],
                "sourceScriptSpan": source_span,
                "dialogueOrdinal": dialogue_ordinal,
                "dialogueSourceDigest": requirement["dialogueSourceDigest"],
                "characterRef": voice_version["characterRef"],
                "voiceRef": voice_version["voiceRef"],
                "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
                "voiceLockDigest": voice_version["payloadDigest"],
                "mediaKind": "audio",
                "mediaType": "audio/wav",
                "adapterCapability": voice_version["engineFamily"],
                "providerSelection": "UNSELECTED",
                "parameters": parameters,
                "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
                "requestedProvenance": "LOCAL_EVIDENCE",
                "publicationAllowed": False,
                "createdBy": AUDIO_REQUEST_PLANNER_ID,
                "createdAt": graph["createdAt"],
            }
        )

    def plan_dialogue_requests(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        verified = self.shot_graph.verify_shot_graph_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        require_legacy_executable_graph(graph)
        requirements: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        voice_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        global_ordinal = 0
        nodes = sorted(graph["shots"], key=lambda item: item["globalOrder"])
        for node in nodes:
            shot = self._shot_lineage(verified, node)
            dialogue = shot.get("dialogueRequirements")
            if not isinstance(dialogue, list) or not all(
                isinstance(item, Mapping) for item in dialogue
            ):
                raise StaleInputError("CreativeShotVersion dialogue is malformed")
            spans = _source_dialogue_spans(shot)
            if len(spans) != len(dialogue):
                raise StaleInputError("CreativeShotVersion dialogue lineage is incomplete")
            character_by_name = self._character_by_name(shot)
            for dialogue_index, (raw_line, source_span) in enumerate(
                zip(dialogue, spans), start=1
            ):
                line = deepcopy(dict(raw_line))
                if set(line) != {"speaker", "text", "emotion"}:
                    raise StaleInputError("Script dialogue contract is malformed")
                speaker = line.get("speaker")
                if not isinstance(speaker, str):
                    raise StaleInputError(
                        "dialogue speaker has no exact shot character"
                    )
                character_ref = character_by_name.get(speaker)
                if not isinstance(character_ref, str):
                    raise StaleInputError("dialogue speaker has no exact shot character")
                if character_ref not in voice_cache:
                    voice_cache[character_ref] = _voice_bundle(
                        self.voice_locks,
                        workspace_ref=workspace,
                        project_ref=root["projectRef"],
                        series_ref=root["seriesRef"],
                        character_ref=character_ref,
                    )
                bundle, version = voice_cache[character_ref]
                global_ordinal += 1
                requirement = self._requirement(
                    root=root,
                    graph=graph,
                    shot=shot,
                    line=line,
                    source_span=source_span,
                    dialogue_ordinal=dialogue_index,
                    global_ordinal=global_ordinal,
                    voice_version=version,
                )
                request = self._request(
                    root=root,
                    graph=graph,
                    shot=shot,
                    line=line,
                    source_span=source_span,
                    dialogue_ordinal=dialogue_index,
                    global_ordinal=global_ordinal,
                    requirement=requirement,
                    voice_bundle=bundle,
                    voice_version=version,
                )
                requirements.append(requirement)
                requests.append(request)
        return _sealed({
            "schemaVersion": "v5.k2-dialogue-audio-plan.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "rootPayloadDigest": root["payloadDigest"],
            "executableShotGraphVersionRef": graph[
                "executableShotGraphVersionRef"
            ],
            "executableShotGraphDigest": graph["payloadDigest"],
            "audioRequirements": requirements,
            "generationRequests": requests,
            "summary": {"dialogueRequests": len(requests)},
            "authorityState": "CONTRACT_ONLY_NOT_DURABLE",
            "dispatchAllowed": False,
            "publicationAllowed": False,
        })

def reject_speech_synthesis_in_legacy_media(
    requests: list[Mapping[str, Any]],
) -> None:
    """Fail closed before the legacy G5 runner can turn TTS into a sine wave."""

    for request in requests:
        parameters = request.get("parameters")
        if request.get("mediaKind") == "audio" and (
            not isinstance(parameters, Mapping)
            or parameters.get("speechSynthesis") is not False
        ):
            raise EpisodeProductionError(
                "speech synthesis audio cannot use legacy G5 media"
            )
