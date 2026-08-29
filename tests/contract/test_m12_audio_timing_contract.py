from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os import episode_production as episode_production_public
from services.v5_core_os.episode_production import audio_timing
from services.v5_core_os.episode_production.audio_authority import (
    build_ambience_asset_version,
    build_audio_provenance,
    build_dialogue_asset_version,
    build_music_asset_version,
    build_sfx_asset_version,
    validate_ambience_asset_version,
    validate_dialogue_asset_version,
    validate_music_asset_version,
    validate_sfx_asset_version,
)
from services.v5_core_os.episode_production.audio_timing import (
    AUDIO_INTERVAL_SEMANTICS,
    AUDIO_STEM_ROLES,
    AUDIO_TIME_AUTHORITY,
    AudioCueOverlapError,
    AudioCueRangeError,
    AudioCueScriptBindingError,
    AudioFinalTimelineFieldRejectedError,
    AudioStemRoleError,
    AudioTimingError,
    build_audio_cue,
    build_audio_stem_member,
    build_audio_stem_set,
    build_audio_timing_provenance,
    build_preliminary_mix_candidate,
    build_preliminary_mix_execution_request,
    build_source_audio_timing_evidence,
    validate_audio_cue,
    validate_audio_stem_member,
    validate_audio_stem_set,
    validate_preliminary_mix_candidate,
)
from services.v5_core_os.episode_production.foundation import (
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
)
from tests.contract.test_m12_audio_authority_contract import (
    EPISODE,
    common_asset_command,
    local_voice_asset,
    speech_parameters,
)
from tests.contract.test_m12_audio_contract import (
    PROJECT,
    RUN,
    SERIES,
    WORKSPACE,
    voice_bundle,
)


SCRIPT_VERSION_REF = "script-version-m12"
SCRIPT_VERSION_DIGEST = "a" * 64
CREATED_AT = "2026-08-29T12:30:00Z"
SAMPLE_RATE = 48_000
SAMPLE_COUNT = 48_000


def sealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def timing_provenance(
    slug: str,
    source_bindings: list[tuple[str, str]],
    *,
    parameters_digest: str | None = None,
) -> dict:
    return build_audio_timing_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "producerIdentity": "v5.m12.audio-timing.contract-test.v1",
            "recordRef": f"audio-timing-record-{slug}",
            "parametersDigest": parameters_digest
            or _digest({"audioTimingFixture": slug}),
            "sourceRefs": [
                {"sourceRef": ref, "sourceDigest": digest}
                for ref, digest in sorted(source_bindings)
            ],
        }
    )


def v4_source_evidence(role: str, asset_command: dict) -> dict:
    artifact = asset_command["artifact"]
    parameters_digest = _digest(
        {"audioRole": role, "sampleRate": SAMPLE_RATE, "channels": 1}
    )
    probe = {
        "sampleRate": SAMPLE_RATE,
        "channels": 1,
        "durationSeconds": 1.0,
        "durationSamples": SAMPLE_COUNT,
        "codec": "pcm_s16le",
        "container": "wav",
    }
    return sealed(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRequirementRef": asset_command["assetRequirementRef"],
            "assetRequirementDigest": asset_command[
                "assetRequirementDigest"
            ],
            "generationRequestRef": asset_command["generationRequestRef"],
            "generationRequestVersionRef": asset_command[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": asset_command[
                "generationRequestDigest"
            ],
            "executionRequestDigest": _digest(
                {"audioRole": role, "execution": "fixture"}
            ),
            "creativeShotRef": f"creative-shot-{role}",
            "creativeShotVersionRef": f"creative-shot-{role}-v1",
            "creativeShotDigest": "1" * 64,
            "scriptRef": "script-m12",
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
            "artifactEvidenceRef": artifact["artifactEvidenceRef"],
            "artifactRef": artifact["artifactRef"],
            "storageKey": artifact["storageKey"],
            "byteSize": artifact["byteSize"],
            "sha256": artifact["fileDigest"],
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "probe": probe,
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": parameters_digest,
            "synthesisSpecDigest": _digest(
                {"audioRole": role, "synthesis": "fixture"}
            ),
            "adapterIdentity": "v4.local-audio-contract-fixture.v1",
            "audioRole": role,
            "provenance": "LOCAL_EVIDENCE",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )


def explicit_source_assets() -> dict:
    confirmed_voice_lock = voice_bundle("character-lin", "voice-lin")
    voice_asset = local_voice_asset(confirmed_voice_lock)
    sources: dict[str, dict] = {}

    for role in ("dialogue", "narration", "sfx", "ambience", "music"):
        command = common_asset_command(role)
        rights = deepcopy(command["rightsBinding"])
        rights["rightsBindingRef"] = f"audio-rights-binding-{role}-m12-v1"
        command["rightsBinding"] = sealed(rights)
        command["artifact"]["byteSize"] = 96_044
        command["artifact"]["fileDigest"] = _digest(
            {"pcmFixture": role, "sampleCount": SAMPLE_COUNT}
        )
        evidence = v4_source_evidence(role, command)
        command["artifact"]["artifactEvidenceDigest"] = evidence[
            "payloadDigest"
        ]
        command["provenance"] = build_audio_provenance(
            {
                "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                "adapterIdentity": "v4.local-audio-contract-fixture.v1",
                "generationRecordRef": command["generationResultRef"],
                "parametersDigest": evidence["parametersDigest"],
                "artifactEvidenceRef": evidence["artifactEvidenceRef"],
                "artifactEvidenceDigest": evidence["payloadDigest"],
                "sourceRefs": [
                    {
                        "sourceRef": command["generationRequestVersionRef"],
                        "sourceDigest": command["generationRequestDigest"],
                    },
                    {
                        "sourceRef": command["generationResultRef"],
                        "sourceDigest": command["generationResultDigest"],
                    },
                ],
            }
        )
        if role in {"dialogue", "narration"}:
            command.update(
                {
                    "speechRole": role,
                    "scriptVersionRef": SCRIPT_VERSION_REF,
                    "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
                    "dialogueRef": (
                        "dialogue-line-m12" if role == "dialogue" else None
                    ),
                    "narrationRef": (
                        "narration-line-m12"
                        if role == "narration"
                        else None
                    ),
                    "voiceAssetVersionRef": voice_asset["assetVersionRef"],
                    "voiceAssetVersionDigest": voice_asset["payloadDigest"],
                    "language": "zh-CN",
                    "normalizedSpeechParameters": speech_parameters(
                        confirmed_voice_lock, role
                    ),
                    "sourceAudioCueRefs": [],
                }
            )
            asset = build_dialogue_asset_version(
                command,
                confirmed_voice_lock=confirmed_voice_lock,
                voice_asset_version=voice_asset,
            )
        elif role == "sfx":
            command.update(
                {
                    "sfxKind": "paper",
                    "synthesisSpecDigest": "c" * 64,
                    "sourceAudioCueRefs": [],
                }
            )
            asset = build_sfx_asset_version(command)
        elif role == "ambience":
            command.update(
                {
                    "ambienceKind": "rain",
                    "synthesisSpecDigest": "d" * 64,
                    "sourceAudioCueRefs": [],
                }
            )
            asset = build_ambience_asset_version(command)
        else:
            command.update(
                {
                    "musicSourceKind": "PROGRAMMATIC",
                    "musicSpecDigest": "b" * 64,
                    "sourceAudioCueRefs": [],
                }
            )
            asset = build_music_asset_version(command)

        if role in {"dialogue", "narration"}:
            asset_contract = validate_dialogue_asset_version(
                asset,
                confirmed_voice_lock=confirmed_voice_lock,
                voice_asset_version=voice_asset,
            )
        elif role == "sfx":
            asset_contract = validate_sfx_asset_version(asset)
        elif role == "ambience":
            asset_contract = validate_ambience_asset_version(asset)
        else:
            asset_contract = validate_music_asset_version(asset)

        timing_evidence = build_source_audio_timing_evidence(
            evidence, source_asset_version=asset_contract
        )
        sources[role] = {
            "asset": asset,
            "assetContract": asset_contract,
            "v4Evidence": evidence,
            "timingEvidence": timing_evidence,
        }

    return {
        "confirmedVoiceLock": confirmed_voice_lock,
        "voiceAsset": voice_asset,
        "sources": sources,
    }


def cue_command(
    source: dict,
    role: str,
    *,
    suffix: str = "1",
    source_start: int = 0,
    source_end: int = 4_800,
) -> dict:
    asset = source["asset"]
    evidence = source["timingEvidence"]
    subtitle = None
    words: list[dict] = []
    phonemes: list[dict] = []
    if role == "dialogue":
        subtitle = {
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
            "language": "zh-CN",
            "sourceText": asset["normalizedSpeechParameters"]["text"],
            "textRangeStart": 0,
            "textRangeEndExclusive": 4,
            "text": "不要动。",
        }
        words = [
            {
                "wordRef": f"word-{suffix}-buyao",
                "text": "不要",
                "textRangeStart": 0,
                "textRangeEndExclusive": 2,
                "sourceStartSample": 0,
                "sourceEndSample": 2_400,
                "confidence": 9_900,
            },
            {
                "wordRef": f"word-{suffix}-dong",
                "text": "动",
                "textRangeStart": 2,
                "textRangeEndExclusive": 3,
                "sourceStartSample": 2_400,
                "sourceEndSample": 4_000,
                "confidence": 9_800,
            },
        ]
        phonemes = [
            {
                "phonemeRef": f"phoneme-{suffix}-b",
                "wordRef": f"word-{suffix}-buyao",
                "symbol": "b",
                "sourceStartSample": 0,
                "sourceEndSample": 1_200,
                "confidence": 9_700,
            },
            {
                "phonemeRef": f"phoneme-{suffix}-u",
                "wordRef": f"word-{suffix}-buyao",
                "symbol": "u",
                "sourceStartSample": 1_200,
                "sourceEndSample": 2_400,
                "confidence": 9_600,
            },
            {
                "phonemeRef": f"phoneme-{suffix}-d",
                "wordRef": f"word-{suffix}-dong",
                "symbol": "d",
                "sourceStartSample": 2_400,
                "sourceEndSample": 4_000,
                "confidence": 9_500,
            },
        ]
    elif role == "narration":
        subtitle = {
            "scriptVersionRef": SCRIPT_VERSION_REF,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
            "language": "zh-CN",
            "sourceText": asset["normalizedSpeechParameters"]["text"],
            "textRangeStart": 0,
            "textRangeEndExclusive": 7,
            "text": "夜色漫过长安。",
        }

    return {
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "cueRef": f"audio-cue-{role}-{suffix}",
        "cueVersionRef": f"audio-cue-{role}-{suffix}-v1",
        "version": 1,
        "supersedesCueVersionRef": None,
        "supersedesCueVersionDigest": None,
        "cueRole": role,
        "assetVersionRef": asset["assetVersionRef"],
        "assetVersionDigest": asset["payloadDigest"],
        "assetVersionType": asset["assetVersionType"],
        "scriptVersionRef": SCRIPT_VERSION_REF,
        "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
        "dialogueRef": asset.get("dialogueRef") if role == "dialogue" else None,
        "narrationRef": (
            asset.get("narrationRef") if role == "narration" else None
        ),
        "sourceStartSample": source_start,
        "sourceEndSample": source_end,
        "wordTimings": words,
        "phonemeTimings": phonemes,
        "subtitleTimingReference": subtitle,
        "confidence": 9_800,
        "provenance": timing_provenance(
            f"cue-{role}-{suffix}",
            [
                (asset["assetVersionRef"], asset["payloadDigest"]),
                (SCRIPT_VERSION_REF, SCRIPT_VERSION_DIGEST),
                (
                    evidence["artifactEvidenceRef"],
                    evidence["artifactEvidenceDigest"],
                ),
            ],
        ),
        "createdBy": "v5.m12.audio-cue.contract-test",
        "createdAt": CREATED_AT,
    }


def build_cue(source: dict, role: str, **command_changes) -> dict:
    command = cue_command(source, role)
    command.update(command_changes)
    return build_audio_cue(
        command,
        source_asset_version=source["assetContract"],
        source_artifact_evidence=source["v4Evidence"],
        source_timing_evidence=source["timingEvidence"],
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )


def stem_member_command(
    source: dict,
    role: str,
    *,
    suffix: str,
    source_start: int = 0,
    source_end: int = SAMPLE_COUNT,
    stem_start: int = 0,
    lane: str | None = None,
    overlap_policy: str = "NON_OVERLAPPING",
    cue: dict | None = None,
) -> dict:
    asset = source["asset"]
    evidence = source["timingEvidence"]
    rights = asset["rightsBinding"]
    cue_sources: list[tuple[str, str]] = []
    if cue is not None:
        cue_sources.append((cue["cueVersionRef"], cue["payloadDigest"]))
    return {
        "stemMemberRef": f"stem-member-{role}-{suffix}",
        "stemRole": role,
        "stemLaneRef": lane or f"stem-lane-{role}",
        "overlapPolicy": overlap_policy,
        "sourceAssetVersionRef": asset["assetVersionRef"],
        "sourceAssetVersionDigest": asset["payloadDigest"],
        "sourceAssetVersionType": asset["assetVersionType"],
        "sourceCueRef": None if cue is None else cue["cueRef"],
        "sourceCueVersionRef": None if cue is None else cue["cueVersionRef"],
        "sourceCueDigest": None if cue is None else cue["payloadDigest"],
        "sourceStartSample": source_start,
        "sourceEndSample": source_end,
        "stemStartSample": stem_start,
        "stemEndSample": stem_start + source_end - source_start,
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "provenance": timing_provenance(
            f"stem-{role}-{suffix}",
            [
                (asset["assetVersionRef"], asset["payloadDigest"]),
                (
                    evidence["artifactEvidenceRef"],
                    evidence["artifactEvidenceDigest"],
                ),
                (rights["rightsBindingRef"], rights["payloadDigest"]),
                *cue_sources,
            ],
        ),
        "createdBy": "v5.m12.audio-stem.contract-test",
        "createdAt": CREATED_AT,
    }


def build_stem_member_fixture(
    source: dict,
    role: str,
    *,
    suffix: str,
    cue: dict | None = None,
    **changes,
) -> dict:
    command = stem_member_command(
        source, role, suffix=suffix, cue=cue, **changes
    )
    return build_audio_stem_member(
        command,
        source_asset_version=source["assetContract"],
        source_artifact_evidence=source["v4Evidence"],
        source_timing_evidence=source["timingEvidence"],
        audio_cue=cue,
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )


def stem_context(bundle: dict, cues: list[dict]) -> dict:
    sources = bundle["sources"]
    return {
        "source_asset_versions": {
            item["asset"]["assetVersionRef"]: item["assetContract"]
            for item in sources.values()
        },
        "source_artifact_evidence": {
            item["asset"]["assetVersionRef"]: item["v4Evidence"]
            for item in sources.values()
        },
        "source_timing_evidence": {
            item["asset"]["assetVersionRef"]: item["timingEvidence"]
            for item in sources.values()
        },
        "audio_cues": {item["cueVersionRef"]: item for item in cues},
        "expected_script_version_ref": SCRIPT_VERSION_REF,
        "expected_script_version_digest": SCRIPT_VERSION_DIGEST,
    }


def stem_set_command(
    members: list[dict],
    *,
    suffix: str,
    duration: int = SAMPLE_COUNT,
) -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "stemSetRef": f"audio-stem-set-{suffix}",
        "stemSetVersionRef": f"audio-stem-set-{suffix}-v1",
        "version": 1,
        "supersedesStemSetVersionRef": None,
        "supersedesStemSetVersionDigest": None,
        "scriptVersionRef": SCRIPT_VERSION_REF,
        "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
        "sampleRate": SAMPLE_RATE,
        "preliminaryDurationSamples": duration,
        "members": deepcopy(members),
        "provenance": timing_provenance(
            f"stem-set-{suffix}",
            [
                (SCRIPT_VERSION_REF, SCRIPT_VERSION_DIGEST),
                *sorted(
                    (member["stemMemberRef"], member["payloadDigest"])
                    for member in members
                ),
            ],
        ),
        "createdBy": "v5.m12.audio-stem-set.contract-test",
        "createdAt": CREATED_AT,
    }


def build_stem_set_fixture(
    bundle: dict,
    members: list[dict],
    *,
    suffix: str,
    cues: list[dict] | None = None,
    duration: int = SAMPLE_COUNT,
) -> dict:
    context = stem_context(bundle, cues or [])
    return build_audio_stem_set(
        stem_set_command(members, suffix=suffix, duration=duration),
        **context,
    )


def validate_stem_set_fixture(
    bundle: dict,
    stem_set: dict,
    *,
    cues: list[dict] | None = None,
):
    return validate_audio_stem_set(
        stem_set,
        **stem_context(bundle, cues or []),
    )


def preliminary_mix_execution_context() -> dict:
    return {
        "creativeShotRef": "creative-shot-preliminary-mix-m12",
        "creativeShotVersionRef": "creative-shot-preliminary-mix-m12-v1",
        "creativeShotDigest": "3" * 64,
        "scriptRef": "script-m12",
        "scriptSceneRef": "script-scene-preliminary-mix-m12",
    }


def projected_mix_parameters(stem_set: dict) -> dict:
    priority = {
        "dialogue": 3,
        "narration": 3,
        "sfx": 2,
        "ambience": 1,
        "music": 0,
    }
    tracks = []
    for member in stem_set["members"]:
        evidence = member["sourceTimingEvidence"]
        tracks.append(
            {
                "audioRole": member["stemRole"],
                "assetVersionRef": member["sourceAssetVersionRef"],
                "assetVersionDigest": member["sourceAssetVersionDigest"],
                "storageKey": evidence["storageKey"],
                "sha256": evidence["fileDigest"],
                "sampleRate": stem_set["sampleRate"],
                "channels": evidence["channelCount"],
                "durationSamples": stem_set["preliminaryDurationSamples"],
            }
        )
    tracks.sort(
        key=lambda item: (-priority[item["audioRole"]], item["assetVersionRef"])
    )
    return {
        "mixKind": "preliminary",
        "sampleRate": stem_set["sampleRate"],
        "channels": tracks[0]["channels"],
        "durationSamples": stem_set["preliminaryDurationSamples"],
        "tracks": tracks,
    }


def v4_premix_artifact_result(
    execution_request: dict,
    *,
    parameters_digest: str | None = None,
) -> dict:
    parameters = execution_request["parameters"]
    duration = parameters["durationSamples"]
    mix_parameters_digest = parameters_digest or _digest(parameters)
    adapter_identity = "v4.deterministic-preliminary-ffmpeg-mix.v2"
    execution_digest = execution_request["payloadDigest"]
    synthesis_spec_digest = _digest(
        {
            "adapterIdentity": adapter_identity,
            "parameters": parameters,
        }
    )
    probe = {
        "sampleRate": parameters["sampleRate"],
        "channels": parameters["channels"],
        "durationSeconds": duration / parameters["sampleRate"],
        "durationSamples": duration,
        "codec": "pcm_s16le",
        "container": "wav",
    }
    lineage = {
        field: execution_request[field]
        for field in (
            "workspaceRef",
            "productionRunRef",
            "assetRequirementRef",
            "assetRequirementDigest",
            "generationRequestRef",
            "generationRequestVersionRef",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "scriptRef",
            "scriptVersionRef",
            "scriptVersionDigest",
        )
    }
    storage_key = (
        "asset-versions/audio/preliminary-mix-"
        f"{execution_digest[:16]}.wav"
    )
    file_digest = _digest(
        {"executionRequestDigest": execution_digest, "artifactKind": "PCM_AUDIO"}
    )
    artifact_evidence_ref = "audio-artifact-evidence-" + _digest(
        {
            "generationRequestDigest": execution_digest,
            "executionRequestDigest": execution_digest,
            "storageKey": storage_key,
            "sha256": file_digest,
        }
    )[:32]
    artifact_ref = "audio-artifact-" + file_digest[:32]
    common = {
        "generationRequestDigest": execution_digest,
        "executionRequestDigest": execution_digest,
        "adapterIdentity": adapter_identity,
        "provenance": "LOCAL_EVIDENCE",
        "artifactEvidenceRef": artifact_evidence_ref,
        "artifactRef": artifact_ref,
        "storageKey": storage_key,
        "byteSize": 44 + duration * parameters["channels"] * 2,
        "sha256": file_digest,
        "sampleRate": parameters["sampleRate"],
        "channels": parameters["channels"],
        "probe": probe,
        "parametersDigest": mix_parameters_digest,
        "effectiveParametersDigest": mix_parameters_digest,
        "synthesisSpecDigest": synthesis_spec_digest,
    }
    evidence = sealed(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            **lineage,
            **common,
            "audioRole": "preliminary_mix",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )
    generation_result = sealed(
        {
            "schemaVersion": "v4.audio-generation-result.v1",
            **lineage,
            **common,
            "generationResultRef": "audio-generation-result-pending",
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "audioRole": "preliminary_mix",
            "state": "SUCCEEDED",
            "publicationAllowed": False,
        }
    )
    generation_result_ref = "audio-generation-result-" + _digest(
        {
            "generationRequestDigest": execution_digest,
            "executionRequestDigest": execution_digest,
            "artifactEvidenceDigest": evidence["payloadDigest"],
        }
    )[:32]
    generation_result = sealed(
        {
            **generation_result,
            "generationResultRef": generation_result_ref,
        }
    )
    return sealed(
        {
            "schemaVersion": "v4.audio-artifact-result.v1",
            **lineage,
            **common,
            "generationResultRef": generation_result_ref,
            "generationResultDigest": generation_result["payloadDigest"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "audioRole": "preliminary_mix",
            "generationResult": generation_result,
            "artifactEvidence": evidence,
            "publicationAllowed": False,
        }
    )


def candidate_command(
    stem_set,
    execution_request: dict,
    artifact_result: dict,
) -> dict:
    stems = stem_set.as_dict() if hasattr(stem_set, "as_dict") else stem_set
    return {
        "candidateRef": "preliminary-mix-candidate-m12",
        "provenance": timing_provenance(
            "preliminary-mix-candidate",
            [
                (stems["stemSetVersionRef"], stems["payloadDigest"]),
                (
                    execution_request["generationRequestVersionRef"],
                    execution_request["payloadDigest"],
                ),
                (
                    artifact_result["generationResultRef"],
                    artifact_result["generationResultDigest"],
                ),
                (
                    artifact_result["artifactEvidenceRef"],
                    artifact_result["artifactEvidenceDigest"],
                ),
            ],
            parameters_digest=artifact_result["parametersDigest"],
        ),
        "createdBy": "v5.m12.preliminary-mix.contract-test",
        "createdAt": CREATED_AT,
    }


class M12AudioTimingContractTests(unittest.TestCase):
    def test_audio_cue_binds_sentence_word_text_and_phoneme_deterministically(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["dialogue"]
        command = cue_command(source, "dialogue")
        cue = build_audio_cue(
            deepcopy(command),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            source_timing_evidence=source["timingEvidence"],
            expected_script_version_ref=SCRIPT_VERSION_REF,
            expected_script_version_digest=SCRIPT_VERSION_DIGEST,
        )
        repeated = build_audio_cue(
            deepcopy(command),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            source_timing_evidence=source["timingEvidence"],
            expected_script_version_ref=SCRIPT_VERSION_REF,
            expected_script_version_digest=SCRIPT_VERSION_DIGEST,
        )

        self.assertEqual(cue, repeated)
        self.assertEqual(cue["payloadDigest"], repeated["payloadDigest"])
        self.assertEqual(cue["sourceStartTime"], {"numerator": 0, "denominator": 1})
        self.assertEqual(cue["sourceEndTime"], {"numerator": 1, "denominator": 10})
        self.assertEqual(cue["intervalSemantics"], AUDIO_INTERVAL_SEMANTICS)
        self.assertEqual(cue["timeAuthority"], AUDIO_TIME_AUTHORITY)
        self.assertEqual(
            cue["subtitleTimingReference"]["sourceText"][0:4],
            cue["subtitleTimingReference"]["text"],
        )
        self.assertEqual(
            [item["text"] for item in cue["wordTimings"]], ["不要", "动"]
        )
        self.assertEqual(
            {item["wordRef"] for item in cue["phonemeTimings"]},
            {item["wordRef"] for item in cue["wordTimings"]},
        )
        self.assertEqual(
            validate_audio_cue(
                cue,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            ).as_dict(),
            cue,
        )

        optional_phonemes = deepcopy(command)
        optional_phonemes.pop("phonemeTimings")
        without_phonemes = build_audio_cue(
            optional_phonemes,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            source_timing_evidence=source["timingEvidence"],
            expected_script_version_ref=SCRIPT_VERSION_REF,
            expected_script_version_digest=SCRIPT_VERSION_DIGEST,
        )
        self.assertEqual(without_phonemes["phonemeTimings"], [])

    def test_audio_cue_rejects_empty_reversed_out_of_bounds_and_rational_drift(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["sfx"]
        for label, start, end in (
            ("empty", 1_200, 1_200),
            ("reversed", 2_400, 1_200),
            ("past_source_extent", 0, SAMPLE_COUNT + 1),
        ):
            command = cue_command(
                source, "sfx", suffix=label, source_start=start, source_end=end
            )
            with self.subTest(label=label), self.assertRaises(
                AudioCueRangeError
            ):
                build_audio_cue(
                    command,
                    source_asset_version=source["assetContract"],
                    source_artifact_evidence=source["v4Evidence"],
                    source_timing_evidence=source["timingEvidence"],
                    expected_script_version_ref=SCRIPT_VERSION_REF,
                    expected_script_version_digest=SCRIPT_VERSION_DIGEST,
                )

        valid = build_cue(source, "sfx")
        rational_drift = sealed(
            {**valid, "sourceEndTime": {"numerator": 1, "denominator": 5}}
        )
        with self.assertRaises(AudioCueRangeError):
            validate_audio_cue(
                rational_drift,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

        inflated_projection = sealed(
            {
                **source["timingEvidence"],
                "sampleCount": SAMPLE_COUNT * 2,
            }
        )
        with self.assertRaises(StaleInputError):
            build_audio_cue(
                cue_command(
                    source,
                    "sfx",
                    suffix="forged-extent",
                    source_end=SAMPLE_COUNT + 1,
                ),
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=inflated_projection,
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

    def test_audio_cue_rejects_script_dialogue_and_subtitle_text_drift(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["dialogue"]

        with self.assertRaises(UpstreamNotReadyError):
            build_audio_cue(
                cue_command(source, "dialogue", suffix="raw-asset"),
                source_asset_version=source["asset"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

        stale_script = cue_command(source, "dialogue", suffix="stale-script")
        stale_script["scriptVersionRef"] = "script-version-stale"
        with self.assertRaises(AudioCueScriptBindingError):
            build_audio_cue(
                stale_script,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

        stale_dialogue = cue_command(source, "dialogue", suffix="stale-line")
        stale_dialogue["dialogueRef"] = "dialogue-line-stale"
        with self.assertRaises(AudioCueScriptBindingError):
            build_audio_cue(
                stale_dialogue,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

        stale_text = cue_command(source, "dialogue", suffix="stale-text")
        stale_text["subtitleTimingReference"]["text"] = "不要"
        with self.assertRaises(AudioCueScriptBindingError):
            build_audio_cue(
                stale_text,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                source_timing_evidence=source["timingEvidence"],
                expected_script_version_ref=SCRIPT_VERSION_REF,
                expected_script_version_digest=SCRIPT_VERSION_DIGEST,
            )

    def test_audio_cue_rejects_invalid_word_and_phoneme_bindings(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["dialogue"]

        cases = []
        bad_text = cue_command(source, "dialogue", suffix="word-text")
        bad_text["wordTimings"][0]["textRangeStart"] = 1
        bad_text["wordTimings"][0]["textRangeEndExclusive"] = 3
        cases.append(("word_text_range", bad_text, AudioCueScriptBindingError))

        word_outside = cue_command(source, "dialogue", suffix="word-range")
        word_outside["wordTimings"][1]["sourceStartSample"] = 4_700
        word_outside["wordTimings"][1]["sourceEndSample"] = 5_000
        cases.append(("word_outside_cue", word_outside, AudioCueRangeError))

        word_overlap = cue_command(source, "dialogue", suffix="word-overlap")
        word_overlap["wordTimings"][1]["sourceStartSample"] = 2_399
        cases.append(("word_overlap", word_overlap, AudioCueOverlapError))

        missing_word = cue_command(source, "dialogue", suffix="missing-word")
        missing_word["phonemeTimings"][0]["wordRef"] = "word-missing"
        cases.append(("phoneme_word", missing_word, AudioCueScriptBindingError))

        phoneme_outside = cue_command(
            source, "dialogue", suffix="phoneme-range"
        )
        phoneme_outside["phonemeTimings"][0]["sourceEndSample"] = 2_401
        cases.append(("phoneme_outside_word", phoneme_outside, AudioCueRangeError))

        phoneme_overlap = cue_command(
            source, "dialogue", suffix="phoneme-overlap"
        )
        phoneme_overlap["phonemeTimings"][1]["sourceStartSample"] = 1_199
        cases.append(("phoneme_overlap", phoneme_overlap, AudioCueOverlapError))

        for label, command, error in cases:
            with self.subTest(label=label), self.assertRaises(error):
                build_audio_cue(
                    command,
                    source_asset_version=source["assetContract"],
                    source_artifact_evidence=source["v4Evidence"],
                    source_timing_evidence=source["timingEvidence"],
                    expected_script_version_ref=SCRIPT_VERSION_REF,
                    expected_script_version_digest=SCRIPT_VERSION_DIGEST,
                )

    def test_five_stem_roles_are_explicit_and_unknown_or_mismatched_fail_closed(self):
        bundle = explicit_source_assets()
        sources = bundle["sources"]
        cues = {
            role: build_cue(sources[role], role)
            for role in ("dialogue", "narration")
        }
        members = {}
        for role in sorted(AUDIO_STEM_ROLES):
            cue = cues.get(role)
            members[role] = build_stem_member_fixture(
                sources[role],
                role,
                suffix=f"role-{role}",
                cue=cue,
                source_end=4_800 if cue is not None else SAMPLE_COUNT,
            )
            self.assertEqual(members[role]["stemRole"], role)
            self.assertEqual(
                members[role]["sourceAssetVersionType"],
                sources[role]["asset"]["assetVersionType"],
            )
        self.assertEqual(
            set(members),
            {"dialogue", "narration", "sfx", "ambience", "music"},
        )
        self.assertIsNone(members["music"]["sourceCueVersionRef"])

        for label, claimed_role in (
            ("unknown", "foley"),
            ("asset_kind_mismatch", "ambience"),
        ):
            command = stem_member_command(
                sources["sfx"], "sfx", suffix=label
            )
            command["stemRole"] = claimed_role
            with self.subTest(label=label), self.assertRaises(
                AudioStemRoleError
            ):
                build_audio_stem_member(
                    command,
                    source_asset_version=sources["sfx"]["assetContract"],
                    source_artifact_evidence=sources["sfx"]["v4Evidence"],
                    source_timing_evidence=sources["sfx"]["timingEvidence"],
                    expected_script_version_ref=SCRIPT_VERSION_REF,
                    expected_script_version_digest=SCRIPT_VERSION_DIGEST,
                )

    def test_stem_set_uses_half_open_lane_rules_including_reversed_input(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["sfx"]
        first = build_stem_member_fixture(
            source,
            "sfx",
            suffix="lane-first",
            source_start=0,
            source_end=2_400,
            stem_start=0,
            lane="sfx-lane-a",
        )
        adjacent = build_stem_member_fixture(
            source,
            "sfx",
            suffix="lane-adjacent",
            source_start=2_400,
            source_end=4_800,
            stem_start=2_400,
            lane="sfx-lane-a",
        )
        canonical = build_stem_set_fixture(
            bundle, [first, adjacent], suffix="half-open", duration=4_800
        )
        reversed_input = build_stem_set_fixture(
            bundle, [adjacent, first], suffix="half-open", duration=4_800
        )
        self.assertEqual(canonical, reversed_input)
        self.assertEqual(canonical["payloadDigest"], reversed_input["payloadDigest"])

        overlap = build_stem_member_fixture(
            source,
            "sfx",
            suffix="lane-overlap",
            source_start=2_400,
            source_end=4_800,
            stem_start=2_399,
            lane="sfx-lane-a",
        )
        for label, order in (
            ("forward", [first, overlap]),
            ("reversed", [overlap, first]),
        ):
            with self.subTest(label=label), self.assertRaises(
                AudioCueOverlapError
            ):
                build_stem_set_fixture(
                    bundle, order, suffix=f"overlap-{label}", duration=4_800
                )

        other_lane = build_stem_member_fixture(
            source,
            "sfx",
            suffix="other-lane",
            source_start=2_400,
            source_end=4_800,
            stem_start=2_399,
            lane="sfx-lane-b",
        )
        accepted = build_stem_set_fixture(
            bundle,
            [first, other_lane],
            suffix="different-lanes",
            duration=4_800,
        )
        self.assertEqual(len(accepted["members"]), 2)

    def test_preliminary_mix_candidate_pins_stem_set_and_supports_music(self):
        bundle = explicit_source_assets()
        sources = bundle["sources"]
        executable_members = [
            build_stem_member_fixture(
                sources[role], role, suffix=f"premix-{role}"
            )
            for role in ("dialogue", "sfx", "ambience")
        ]
        stem_set_mapping = build_stem_set_fixture(
            bundle, executable_members, suffix="premix"
        )
        stem_set = validate_stem_set_fixture(bundle, stem_set_mapping)
        execution_request = build_preliminary_mix_execution_request(
            preliminary_mix_execution_context(), stem_set=stem_set
        )
        artifact_result = v4_premix_artifact_result(execution_request)
        command = candidate_command(
            stem_set, execution_request, artifact_result
        )
        candidate = build_preliminary_mix_candidate(
            command,
            stem_set=stem_set,
            v4_execution_request=execution_request,
            v4_artifact_result=artifact_result,
        )
        stems = stem_set.as_dict()
        self.assertEqual(candidate["sourceStemSetRef"], stems["stemSetRef"])
        self.assertEqual(
            candidate["sourceStemSetVersionRef"], stems["stemSetVersionRef"]
        )
        self.assertEqual(
            candidate["sourceStemSetDigest"], stems["payloadDigest"]
        )
        self.assertEqual(
            execution_request["parameters"], projected_mix_parameters(stems)
        )
        self.assertEqual(
            candidate["mixParametersDigest"],
            _digest(projected_mix_parameters(stems)),
        )
        self.assertEqual(
            validate_preliminary_mix_candidate(
                candidate,
                stem_set=stem_set,
                v4_execution_request=execution_request,
                v4_artifact_result=artifact_result,
            ).as_dict(),
            candidate,
        )

        stale_pin = sealed(
            {**candidate, "sourceStemSetDigest": "0" * 64}
        )
        with self.assertRaises(StaleInputError):
            validate_preliminary_mix_candidate(
                stale_pin,
                stem_set=stem_set,
                v4_execution_request=execution_request,
                v4_artifact_result=artifact_result,
            )

        wrong_parameters = v4_premix_artifact_result(
            execution_request, parameters_digest="f" * 64
        )
        with self.assertRaises(StaleInputError):
            build_preliminary_mix_candidate(
                candidate_command(
                    stem_set, execution_request, wrong_parameters
                ),
                stem_set=stem_set,
                v4_execution_request=execution_request,
                v4_artifact_result=wrong_parameters,
            )

        music_member = build_stem_member_fixture(
            sources["music"], "music", suffix="premix-music"
        )
        music_stem_set_mapping = build_stem_set_fixture(
            bundle, [music_member], suffix="premix-music"
        )
        music_stem_set = validate_stem_set_fixture(
            bundle, music_stem_set_mapping
        )
        music_request = build_preliminary_mix_execution_request(
            preliminary_mix_execution_context(),
            stem_set=music_stem_set,
        )
        self.assertEqual(
            music_request["parameters"],
            projected_mix_parameters(music_stem_set.as_dict()),
        )
        self.assertEqual(
            music_request["parameters"]["tracks"][0]["audioRole"],
            "music",
        )

    def test_final_timeline_fields_fail_closed_for_builders_and_validators(self):
        bundle = explicit_source_assets()
        source = bundle["sources"]["sfx"]
        cue_cmd = cue_command(source, "sfx", suffix="timeline")
        cue = build_cue(source, "sfx")
        member_cmd = stem_member_command(
            source, "sfx", suffix="timeline"
        )
        member = build_stem_member_fixture(
            source, "sfx", suffix="timeline"
        )
        stem_cmd = stem_set_command([member], suffix="timeline")
        context = stem_context(bundle, [])
        stem_set_mapping = build_stem_set_fixture(
            bundle, [member], suffix="timeline"
        )
        stem_set = validate_stem_set_fixture(bundle, stem_set_mapping)
        execution_request = build_preliminary_mix_execution_request(
            preliminary_mix_execution_context(), stem_set=stem_set
        )
        artifact_result = v4_premix_artifact_result(execution_request)
        mix_cmd = candidate_command(
            stem_set, execution_request, artifact_result
        )
        candidate = build_preliminary_mix_candidate(
            mix_cmd,
            stem_set=stem_set,
            v4_execution_request=execution_request,
            v4_artifact_result=artifact_result,
        )

        builder_cases = (
            (
                "cue",
                build_audio_cue,
                {**cue_cmd, "timelineStartSample": 0},
                {
                    "source_asset_version": source["assetContract"],
                    "source_artifact_evidence": source["v4Evidence"],
                    "source_timing_evidence": source["timingEvidence"],
                    "expected_script_version_ref": SCRIPT_VERSION_REF,
                    "expected_script_version_digest": SCRIPT_VERSION_DIGEST,
                },
            ),
            (
                "member",
                build_audio_stem_member,
                {**member_cmd, "timelineTrackRef": "timeline-track-a"},
                {
                    "source_asset_version": source["assetContract"],
                    "source_artifact_evidence": source["v4Evidence"],
                    "source_timing_evidence": source["timingEvidence"],
                    "expected_script_version_ref": SCRIPT_VERSION_REF,
                    "expected_script_version_digest": SCRIPT_VERSION_DIGEST,
                },
            ),
            (
                "stem_set",
                build_audio_stem_set,
                {**stem_cmd, "timelineVersionRef": "timeline-version-a"},
                context,
            ),
            (
                "candidate",
                build_preliminary_mix_candidate,
                {**mix_cmd, "episodeMasterRef": "episode-master-a"},
                {
                    "stem_set": stem_set,
                    "v4_execution_request": execution_request,
                    "v4_artifact_result": artifact_result,
                },
            ),
        )
        for label, builder, command, kwargs in builder_cases:
            with self.subTest(builder=label), self.assertRaises(
                AudioFinalTimelineFieldRejectedError
            ):
                builder(command, **kwargs)

        validator_cases = (
            (
                "cue",
                validate_audio_cue,
                sealed({**cue, "timelineRef": "timeline-a"}),
                {
                    "source_asset_version": source["assetContract"],
                    "source_artifact_evidence": source["v4Evidence"],
                    "source_timing_evidence": source["timingEvidence"],
                    "expected_script_version_ref": SCRIPT_VERSION_REF,
                    "expected_script_version_digest": SCRIPT_VERSION_DIGEST,
                },
            ),
            (
                "member",
                validate_audio_stem_member,
                sealed({**member, "timelineClipRef": "timeline-clip-a"}),
                {
                    "source_asset_version": source["assetContract"],
                    "source_artifact_evidence": source["v4Evidence"],
                    "source_timing_evidence": source["timingEvidence"],
                    "expected_script_version_ref": SCRIPT_VERSION_REF,
                    "expected_script_version_digest": SCRIPT_VERSION_DIGEST,
                },
            ),
            (
                "stem_set",
                validate_audio_stem_set,
                sealed(
                    {
                        **stem_set_mapping,
                        "timelineVersionRef": "timeline-version-a",
                    }
                ),
                context,
            ),
            (
                "candidate",
                validate_preliminary_mix_candidate,
                sealed({**candidate, "previewCandidateRef": "preview-a"}),
                {
                    "stem_set": stem_set,
                    "v4_execution_request": execution_request,
                    "v4_artifact_result": artifact_result,
                },
            ),
        )
        for label, validator, value, kwargs in validator_cases:
            with self.subTest(validator=label), self.assertRaises(
                AudioFinalTimelineFieldRejectedError
            ):
                validator(value, **kwargs)

        for name in audio_timing.__all__:
            with self.subTest(public_export=name):
                self.assertIn(name, episode_production_public.__all__)
                self.assertIs(
                    getattr(episode_production_public, name),
                    getattr(audio_timing, name),
                )

        provenance_command = {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "producerIdentity": "v5.m12.audio-timing.contract-test.v1",
            "recordRef": "audio-timing-determinism-record",
            "parametersDigest": "3" * 64,
            "sourceRefs": [
                {"sourceRef": "source-a", "sourceDigest": "4" * 64}
            ],
        }
        first = build_audio_timing_provenance(deepcopy(provenance_command))
        second = build_audio_timing_provenance(deepcopy(provenance_command))
        self.assertEqual(first, second)
        self.assertEqual(first["payloadDigest"], second["payloadDigest"])


if __name__ == "__main__":
    unittest.main()
