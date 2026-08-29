from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from services.v4_platform.audio import (
    PIPER_TTS_ADAPTER_ID,
    PiperTtsAdapter,
    audio_artifact_evidence,
    execute_piper_tts_evidence,
)
from services.v4_platform.audio_synthesis import (
    DEFAULT_MUSIC_INSTRUMENT,
    DEFAULT_MUSIC_SEQUENCE,
    DEFAULT_MUSIC_STEM_RECIPE,
    DEFAULT_MUSIC_STRUCTURE,
    AudioSynthesisExecutionEvidence,
    AudioSynthesisRequestError,
    build_audio_synthesis_execution_context,
    build_audio_synthesis_execution_request,
    build_procedural_music_synthesis_spec,
    build_programmatic_effect_synthesis_spec,
    execute_audio_synthesis,
)
from services.v4_platform.local_audio_runtime import (
    BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
)
from services.v5_core_os.episode_production.audio_authority import (
    AmbienceAssetVersion,
    AudioGenerationRequest,
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
    VoiceAssetVersion,
    build_audio_generation_request,
    build_requested_audio_provenance,
    build_rights_binding,
)
from services.v5_core_os.episode_production.audio_synthesis import (
    MUSIC_QUALITY_APPROVAL,
    PROGRAMMATIC_AMBIENCE_EFFECT_KINDS,
    PROGRAMMATIC_AUDIO_EFFECT_KINDS,
    PROGRAMMATIC_AUDIO_EFFECT_ROLE,
    PROGRAMMATIC_SFX_EFFECT_KINDS,
    ProgrammaticAudioEvidenceBindingError,
    ProgrammaticAudioSynthesisError,
    build_programmatic_audio_asset_version,
    build_programmatic_audio_execution_context,
    build_programmatic_audio_execution_request,
    build_programmatic_audio_generation_record,
    build_programmatic_audio_synthesis_spec,
    validate_programmatic_audio_generation_record,
    validate_programmatic_audio_synthesis_spec,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
)
from services.v5_core_os.episode_production.narration_synthesis import (
    NARRATION_REQUIRED_RUNTIME_STATE,
    NARRATION_TEST_AUTHORITY_STATE,
    NARRATION_TEST_FIXTURE_MARKER,
    NARRATION_TEST_RUNTIME_IDENTITY,
    NarrationEvidenceBindingError,
    NarrationExecutionContext,
    NarrationGenerationRecord,
    NarrationSynthesisError,
    NarrationTestDialogueProjection,
    NarrationTestEvidenceProjection,
    build_narration_dialogue_asset_version,
    build_narration_execution_context,
    build_narration_generation_record,
    build_narration_tts_execution_request,
    build_test_only_narration_dialogue_projection,
    build_test_only_narration_evidence_projection,
)
from tests.contract.test_m12_audio_authority_contract import (
    AS_OF,
    cloned_voice_asset,
    consent_grant,
    local_voice_asset,
    rights_binding,
    speech_parameters,
)
from tests.contract.test_m12_audio_contract import voice_bundle
from tests.contract.test_m12_audio_timing_contract import (
    build_stem_member_fixture,
    build_stem_set_fixture,
    explicit_source_assets,
    preliminary_mix_execution_context,
    validate_stem_set_fixture,
)
from services.v5_core_os.episode_production.audio_timing import (
    AUDIO_TIMELINE_BINDING_STATE,
    build_preliminary_mix_execution_request,
)
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter


WORKSPACE = "workspace-m12-pr6"
PROJECT = "project-m12-pr6"
SERIES = "series-m12-pr6"
EPISODE = "episode-m12-pr6"
RUN = "production-run-m12-pr6"
CREATED_AT = "2026-08-29T16:00:00Z"
SAMPLE_RATE = 48_000
SHORT_DURATION_SAMPLES = 48_000

EXPECTED_EFFECT_ROLE = {
    "rain": "ambience",
    "wind": "ambience",
    "room_tone": "ambience",
    "door_hinge": "sfx",
    "footsteps": "sfx",
    "paper": "sfx",
    "clothing": "sfx",
    "fire_crackle": "sfx",
    "impact_transient": "sfx",
}


def _reseal(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _programmatic_rights(
    requirement_ref: str, requirement_digest: str
) -> dict:
    manifest_ref = "rights-manifest-m12-pr6"
    manifest_digest = "a" * 64
    evidence_ref = "rights-evidence-m12-pr6"
    evidence_digest = "b" * 64
    return build_rights_binding(
        {
            "rightsBindingRef": f"rights-binding-{requirement_ref}",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED",
            "ownership": "PROJECT_OWNER",
            "usageScope": [
                "AUDIO_PRODUCTION",
                "MUSIC_GENERATION",
                "SFX_GENERATION",
                "AMBIENCE_GENERATION",
            ],
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": manifest_ref,
                    "sourceDigest": manifest_digest,
                },
                {
                    "sourceRef": evidence_ref,
                    "sourceDigest": evidence_digest,
                },
                {
                    "sourceRef": requirement_ref,
                    "sourceDigest": requirement_digest,
                },
            ],
            "rightsManifestRef": manifest_ref,
            "rightsManifestVersion": 1,
            "rightsManifestDigest": manifest_digest,
            "authorityEvidenceRef": evidence_ref,
            "authorityEvidenceDigest": evidence_digest,
        }
    )


def _effect_command(effect_kind: str, *, seed: int) -> dict:
    return {
        "audioRole": EXPECTED_EFFECT_ROLE[effect_kind],
        "effectKind": effect_kind,
        "durationSamples": SHORT_DURATION_SAMPLES,
        "sampleRate": SAMPLE_RATE,
        "channels": 1,
        "seed": seed,
        "externalSampleRefs": [],
        "networkAccessAllowed": False,
    }


def _music_command(*, seed: int) -> dict:
    return {
        "audioRole": "music",
        "durationSamples": SHORT_DURATION_SAMPLES,
        "sampleRate": SAMPLE_RATE,
        "channels": 2,
        "seed": seed,
        "tempoBpm": 96,
        "key": "D",
        "mode": "natural_minor",
        "structure": deepcopy(DEFAULT_MUSIC_STRUCTURE),
        "sequence": deepcopy(DEFAULT_MUSIC_SEQUENCE),
        "instrument": deepcopy(DEFAULT_MUSIC_INSTRUMENT),
        "stemRecipe": deepcopy(DEFAULT_MUSIC_STEM_RECIPE),
        "musicQualityApproval": MUSIC_QUALITY_APPROVAL,
        "externalSampleRefs": [],
        "networkAccessAllowed": False,
    }


def _synthesis_spec(kind: str, *, seed: int):
    command = _music_command(seed=seed) if kind == "music" else _effect_command(
        kind, seed=seed
    )
    return build_programmatic_audio_synthesis_spec(command)


def _generation_request(kind: str, synthesis_spec, *, seed: int):
    role = "music" if kind == "music" else EXPECTED_EFFECT_ROLE[kind]
    request_kind = {
        "music": "MUSIC_GENERATION",
        "sfx": "SFX_GENERATION",
        "ambience": "AMBIENCE_GENERATION",
    }[role]
    output_type = {
        "music": "MusicAssetVersion",
        "sfx": "SfxAssetVersion",
        "ambience": "AmbienceAssetVersion",
    }[role]
    spec = synthesis_spec.as_dict()
    requirement_ref = f"asset-requirement-pr6-{kind}"
    requirement_digest = _digest(
        {"schemaVersion": "test.asset-requirement.v1", "kind": kind}
    )
    request_spec = {
        "sourceAudioCueRefs": [],
        (
            "musicSpecDigest"
            if role == "music"
            else "synthesisSpecDigest"
        ): spec["synthesisSpecDigest"],
    }
    if role == "music":
        request_spec["musicSourceKind"] = "PROGRAMMATIC"
    elif role == "sfx":
        request_spec["sfxKind"] = kind
    else:
        request_spec["ambienceKind"] = kind
    requested_provenance = build_requested_audio_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "adapterIdentity": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
            "parametersDigest": spec["synthesisSpecDigest"],
            "sourceRefs": [
                {
                    "sourceRef": requirement_ref,
                    "sourceDigest": requirement_digest,
                }
            ],
        }
    )
    mapping = build_audio_generation_request(
        {
            "requestKind": request_kind,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "generationRequestRef": f"audio-generation-request-pr6-{kind}-{seed}",
            "generationRequestVersionRef": (
                f"audio-generation-request-pr6-{kind}-{seed}-v1"
            ),
            "version": 1,
            "supersedesGenerationRequestVersionRef": None,
            "supersedesGenerationRequestVersionDigest": None,
            "assetRequirementRef": requirement_ref,
            "assetRequirementDigest": requirement_digest,
            "outputAssetVersionType": output_type,
            "outputTarget": "ASSET_VERSION",
            "requestSpec": request_spec,
            "rightsBinding": _programmatic_rights(
                requirement_ref, requirement_digest
            ),
            "requestedProvenance": requested_provenance,
            "createdBy": "v5.m12.programmatic-audio.contract-test",
            "createdAt": CREATED_AT,
        }
    )
    return AudioGenerationRequest.from_mapping(mapping)


def _execution_context(kind: str, *, storage_key: str):
    return build_programmatic_audio_execution_context(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "assetRequirementRef": f"asset-requirement-pr6-{kind}",
            "assetRequirementDigest": _digest(
                {"schemaVersion": "test.asset-requirement.v1", "kind": kind}
            ),
            "creativeShotRef": f"creative-shot-pr6-{kind}",
            "creativeShotVersionRef": f"creative-shot-pr6-{kind}-v1",
            "creativeShotDigest": "c" * 64,
            "scriptRef": "script-m12-pr6",
            "scriptVersionRef": "script-version-m12-pr6-v1",
            "scriptVersionDigest": "d" * 64,
            "storageKey": storage_key,
        }
    )


def build_programmatic_chain(
    kind: str, *, seed: int, storage_key: str
) -> dict:
    synthesis_spec = _synthesis_spec(kind, seed=seed)
    generation_request = _generation_request(kind, synthesis_spec, seed=seed)
    execution_context = _execution_context(kind, storage_key=storage_key)
    execution_request = build_programmatic_audio_execution_request(
        generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
    )
    return {
        "synthesisSpec": synthesis_spec,
        "generationRequest": generation_request,
        "executionContext": execution_context,
        "executionRequest": execution_request,
    }


def execute_programmatic_chain(
    kind: str,
    *,
    seed: int,
    storage_key: str,
    artifact_root: Path,
) -> dict:
    chain = build_programmatic_chain(kind, seed=seed, storage_key=storage_key)
    evidence = execute_audio_synthesis(
        chain["executionRequest"], artifact_root=artifact_root
    )
    record = build_programmatic_audio_generation_record(
        chain["generationRequest"],
        synthesis_spec=chain["synthesisSpec"],
        execution_context=chain["executionContext"],
        execution_request=chain["executionRequest"],
        execution_evidence=evidence,
    )
    asset = build_programmatic_audio_asset_version(
        chain["generationRequest"],
        synthesis_spec=chain["synthesisSpec"],
        execution_context=chain["executionContext"],
        execution_request=chain["executionRequest"],
        execution_evidence=evidence,
        generation_record=record,
        created_at=CREATED_AT,
    )
    chain.update(
        {
            "executionEvidence": evidence,
            "generationRecord": record,
            "assetVersion": asset,
        }
    )
    return chain


def build_typed_narration_sources() -> dict:
    confirmed_voice_lock = voice_bundle("character-lin", "voice-lin")
    voice_mapping = local_voice_asset(confirmed_voice_lock)
    voice_asset = VoiceAssetVersion.from_mapping(
        voice_mapping, confirmed_voice_lock=confirmed_voice_lock
    )
    requirement_ref = "asset-requirement-narration-pr6"
    requirement_digest = "e" * 64
    parameters = speech_parameters(confirmed_voice_lock, "narration")
    request_mapping = build_audio_generation_request(
        {
            "requestKind": "NARRATION_SYNTHESIS",
            "workspaceRef": confirmed_voice_lock["voiceLock"]["workspaceRef"],
            "projectRef": confirmed_voice_lock["voiceLock"]["projectRef"],
            "seriesRef": confirmed_voice_lock["voiceLock"]["seriesRef"],
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "generationRequestRef": "audio-generation-request-narration-pr6",
            "generationRequestVersionRef": (
                "audio-generation-request-narration-pr6-v1"
            ),
            "version": 1,
            "supersedesGenerationRequestVersionRef": None,
            "supersedesGenerationRequestVersionDigest": None,
            "assetRequirementRef": requirement_ref,
            "assetRequirementDigest": requirement_digest,
            "outputAssetVersionType": "DialogueAssetVersion",
            "outputTarget": "ASSET_VERSION",
            "requestSpec": {
                "speechRole": "narration",
                "scriptVersionRef": "script-version-m12-pr6-v1",
                "scriptVersionDigest": "d" * 64,
                "dialogueRef": None,
                "narrationRef": "narration-line-m12-pr6",
                "voiceAssetVersionRef": voice_mapping["assetVersionRef"],
                "voiceAssetVersionDigest": voice_mapping["payloadDigest"],
                "language": "zh-CN",
                "normalizedSpeechParameters": parameters,
                "sourceAudioCueRefs": [],
            },
            "rightsBinding": rights_binding(
                asset_requirement_ref=requirement_ref,
                asset_requirement_digest=requirement_digest,
            ),
            "requestedProvenance": build_requested_audio_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "adapterIdentity": PIPER_TTS_ADAPTER_ID,
                    "parametersDigest": _digest(parameters),
                    "sourceRefs": [
                        {
                            "sourceRef": requirement_ref,
                            "sourceDigest": requirement_digest,
                        }
                    ],
                }
            ),
            "createdBy": "v5.m12.narration.contract-test",
            "createdAt": CREATED_AT,
        },
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_mapping,
    )
    generation_request = AudioGenerationRequest.from_mapping(
        request_mapping,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_mapping,
    )
    return {
        "confirmedVoiceLock": confirmed_voice_lock,
        "voiceAssetVersion": voice_asset,
        "generationRequest": generation_request,
    }


def build_typed_narration_context(
    generation_request: AudioGenerationRequest,
    *,
    storage_key: str,
) -> NarrationExecutionContext:
    request = generation_request.as_dict()
    return build_narration_execution_context(
        {
            **{
                field: request[field]
                for field in (
                    "workspaceRef",
                    "projectRef",
                    "seriesRef",
                    "episodeRef",
                    "productionRunRef",
                    "assetRequirementRef",
                    "assetRequirementDigest",
                )
            },
            "creativeShotRef": "creative-shot-narration-pr6",
            "creativeShotVersionRef": "creative-shot-narration-pr6-v1",
            "creativeShotDigest": "c" * 64,
            "scriptRef": "script-m12-pr6",
            "scriptSceneRef": "script-scene-narration-pr6",
            "sourceScriptSpan": "narration-line-m12-pr6[0:7]",
            "narrationOrdinal": 1,
            "storageKey": storage_key,
        }
    )


def execute_typed_narration_test_chain(
    *, artifact_root: Path, storage_key: str
) -> dict:
    sources = build_typed_narration_sources()
    context = build_typed_narration_context(
        sources["generationRequest"], storage_key=storage_key
    )
    execution_request = build_narration_tts_execution_request(
        sources["generationRequest"],
        confirmed_voice_lock=sources["confirmedVoiceLock"],
        voice_asset_version=sources["voiceAssetVersion"],
        execution_context=context,
    )
    adapter = FixedWavTtsAdapter()
    artifact_bundle = audio_artifact_evidence(
        execution_request,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=adapter,
    )
    test_evidence = build_test_only_narration_evidence_projection(
        sources["generationRequest"],
        confirmed_voice_lock=sources["confirmedVoiceLock"],
        voice_asset_version=sources["voiceAssetVersion"],
        execution_context=context,
        execution_request=execution_request,
        test_only_fixed_wav_artifact_bundle=artifact_bundle,
    )
    dialogue_projection = build_test_only_narration_dialogue_projection(
        sources["generationRequest"],
        confirmed_voice_lock=sources["confirmedVoiceLock"],
        voice_asset_version=sources["voiceAssetVersion"],
        execution_context=context,
        execution_request=execution_request,
        test_only_fixed_wav_artifact_bundle=artifact_bundle,
        test_evidence_projection=test_evidence,
        created_at=CREATED_AT,
    )
    return {
        **sources,
        "executionContext": context,
        "executionRequest": execution_request,
        "adapter": adapter,
        "artifactBundle": artifact_bundle,
        "testEvidenceProjection": test_evidence,
        "dialogueProjection": dialogue_projection,
    }


class M12ProgrammaticAudioContractTests(unittest.TestCase):
    def test_nine_effect_kinds_have_one_exact_role_and_unknown_fails_closed(self):
        self.assertEqual(PROGRAMMATIC_AUDIO_EFFECT_ROLE, EXPECTED_EFFECT_ROLE)
        self.assertEqual(
            PROGRAMMATIC_AUDIO_EFFECT_KINDS, frozenset(EXPECTED_EFFECT_ROLE)
        )
        self.assertEqual(
            PROGRAMMATIC_AMBIENCE_EFFECT_KINDS,
            frozenset({"rain", "wind", "room_tone"}),
        )
        self.assertEqual(
            PROGRAMMATIC_SFX_EFFECT_KINDS,
            frozenset(
                {
                    "door_hinge",
                    "footsteps",
                    "paper",
                    "clothing",
                    "fire_crackle",
                    "impact_transient",
                }
            ),
        )
        for effect_kind, role in EXPECTED_EFFECT_ROLE.items():
            with self.subTest(effect_kind=effect_kind):
                spec = _synthesis_spec(effect_kind, seed=17).as_dict()
                self.assertEqual(spec["executionSpec"]["audioRole"], role)
                self.assertEqual(spec["executionSpec"]["effectKind"], effect_kind)

                wrong_role = _effect_command(effect_kind, seed=17)
                wrong_role["audioRole"] = "sfx" if role == "ambience" else "ambience"
                with self.assertRaises(ProgrammaticAudioSynthesisError):
                    build_programmatic_audio_synthesis_spec(wrong_role)

        unknown = _effect_command("rain", seed=17)
        unknown["effectKind"] = "thunder_library_hit"
        with self.assertRaises(ProgrammaticAudioSynthesisError):
            build_programmatic_audio_synthesis_spec(unknown)

    def test_external_inputs_and_commercial_controls_fail_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory) / "must-not-exist"
            effect = {
                key: value
                for key, value in _effect_command("rain", seed=19).items()
                if key not in {"externalSampleRefs", "networkAccessAllowed"}
            }
            music = {
                key: value
                for key, value in _music_command(seed=19).items()
                if key not in {"externalSampleRefs", "networkAccessAllowed"}
            }
            invalid_specs = []
            for key, value in (
                ("sourcePath", "/licensed-library/rain.wav"),
                ("inputUrl", "https://commercial.example/rain.wav"),
                ("sample", b"RIFF\x00\x00test-only-bytes"),
            ):
                nested = deepcopy(effect)
                nested["seed"] = {key: value}
                invalid_specs.append(nested)
            for key, value in (
                ("sampleLibrary", "Hollywood Edge"),
                ("filterGraph", "caller-selected-filter"),
                ("pluginRef", "commercial-vst"),
            ):
                nested = deepcopy(music)
                nested["instrument"][key] = value
                invalid_specs.append(nested)

            for invalid in invalid_specs:
                builder = (
                    build_procedural_music_synthesis_spec
                    if invalid.get("audioRole") == "music"
                    else build_programmatic_effect_synthesis_spec
                )
                with self.subTest(keys=sorted(invalid)), self.assertRaises(
                    AudioSynthesisRequestError
                ):
                    builder(invalid)

            valid_v4_spec = build_programmatic_effect_synthesis_spec(effect)
            context = {
                "creativeShotRef": {
                    "sourceUrl": "https://commercial.example/source.wav"
                },
                "creativeShotVersionRef": "creative-shot-rain-v1",
                "creativeShotDigest": "c" * 64,
                "scriptRef": "script-m12-pr6",
                "scriptVersionRef": "script-version-m12-pr6-v1",
                "scriptVersionDigest": "d" * 64,
                "storageKey": "asset-versions/audio/pr6/rain.wav",
                "synthesisSpec": valid_v4_spec,
            }
            with self.assertRaises(AudioSynthesisRequestError):
                build_audio_synthesis_execution_context(context)

            valid_chain = build_programmatic_chain(
                "rain",
                seed=19,
                storage_key="asset-versions/audio/pr6/rain-no-write.wav",
            )
            projected = valid_chain["executionRequest"].as_dict()
            valid_context = build_audio_synthesis_execution_context(
                {
                    "creativeShotRef": projected["creativeShotRef"],
                    "creativeShotVersionRef": projected[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": projected["creativeShotDigest"],
                    "scriptRef": projected["scriptRef"],
                    "scriptVersionRef": projected["scriptVersionRef"],
                    "scriptVersionDigest": projected["scriptVersionDigest"],
                    "storageKey": projected["storageKey"],
                    "synthesisSpec": projected["synthesisSpec"],
                }
            )
            request_with_url = valid_chain["generationRequest"].as_dict()
            request_with_url["requestSpec"]["sourceAudioCueRefs"] = [
                {"sourceUrl": "https://commercial.example/source.wav"}
            ]
            with self.assertRaises(AudioSynthesisRequestError):
                build_audio_synthesis_execution_request(
                    _reseal(request_with_url),
                    execution_context=valid_context,
                )

            for external_refs, network in ((["sample-asset-v1"], False), ([], True)):
                invalid = _effect_command("rain", seed=19)
                invalid["externalSampleRefs"] = external_refs
                invalid["networkAccessAllowed"] = network
                with self.assertRaises(ProgrammaticAudioSynthesisError):
                    build_programmatic_audio_synthesis_spec(invalid)

            self.assertFalse(artifact_root.exists())

    def test_music_spec_is_closed_human_gated_and_seed_digest_bound(self):
        first = _synthesis_spec("music", seed=23).as_dict()
        repeated = _synthesis_spec("music", seed=23).as_dict()
        changed = _synthesis_spec("music", seed=24).as_dict()
        self.assertEqual(first["payloadDigest"], repeated["payloadDigest"])
        self.assertEqual(first["synthesisSpecDigest"], repeated["synthesisSpecDigest"])
        self.assertNotEqual(first["payloadDigest"], changed["payloadDigest"])
        self.assertNotEqual(
            first["synthesisSpecDigest"], changed["synthesisSpecDigest"]
        )
        self.assertEqual(
            first["executionSpec"]["musicQualityApproval"], "HUMAN_REQUIRED"
        )
        self.assertEqual(first["externalSampleRefs"], [])
        self.assertIs(first["networkAccessAllowed"], False)
        self.assertEqual(
            first["executionSpec"]["stemRecipe"], DEFAULT_MUSIC_STEM_RECIPE
        )

        for field, value in (
            ("musicQualityApproval", "AUTO_APPROVED"),
            ("stemRecipe", {**DEFAULT_MUSIC_STEM_RECIPE, "outputStem": "copyrighted"}),
        ):
            invalid = _music_command(seed=23)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(
                ProgrammaticAudioSynthesisError
            ):
                build_programmatic_audio_synthesis_spec(invalid)

    def test_exact_wrappers_and_digest_bindings_fail_closed(self):
        chain = build_programmatic_chain(
            "paper",
            seed=29,
            storage_key="asset-versions/audio/pr6/paper-contract.wav",
        )
        with self.assertRaises(ProgrammaticAudioSynthesisError):
            build_programmatic_audio_execution_request(
                chain["generationRequest"].as_dict(),
                synthesis_spec=chain["synthesisSpec"],
                execution_context=chain["executionContext"],
            )
        with self.assertRaises(ProgrammaticAudioSynthesisError):
            build_programmatic_audio_execution_request(
                chain["generationRequest"],
                synthesis_spec=chain["synthesisSpec"].as_dict(),
                execution_context=chain["executionContext"],
            )
        with self.assertRaises(ProgrammaticAudioSynthesisError):
            build_programmatic_audio_execution_request(
                chain["generationRequest"],
                synthesis_spec=chain["synthesisSpec"],
                execution_context=chain["executionContext"].as_dict(),
            )

        class AudioGenerationRequestSubclass(AudioGenerationRequest):
            pass

        subclass_request = AudioGenerationRequestSubclass.from_mapping(
            chain["generationRequest"].as_dict()
        )
        with self.assertRaises(ProgrammaticAudioSynthesisError):
            build_programmatic_audio_execution_request(
                subclass_request,
                synthesis_spec=chain["synthesisSpec"],
                execution_context=chain["executionContext"],
            )

        stale_spec = chain["synthesisSpec"].as_dict()
        stale_spec["synthesisSpecDigest"] = "0" * 64
        stale_spec = _reseal(stale_spec)
        with self.assertRaises(StaleInputError):
            validate_programmatic_audio_synthesis_spec(stale_spec)

        stale_request = chain["generationRequest"].as_dict()
        provenance = deepcopy(stale_request["requestedProvenance"])
        provenance["parametersDigest"] = "0" * 64
        stale_request["requestedProvenance"] = _reseal(provenance)
        stale_request = AudioGenerationRequest.from_mapping(
            _reseal(stale_request)
        )
        with self.assertRaises(StaleInputError):
            build_programmatic_audio_execution_request(
                stale_request,
                synthesis_spec=chain["synthesisSpec"],
                execution_context=chain["executionContext"],
            )

        cue_claim = chain["generationRequest"].as_dict()
        cue_claim["requestSpec"]["sourceAudioCueRefs"] = ["audio-cue-v1"]
        with self.assertRaises(UpstreamNotReadyError):
            AudioGenerationRequest.from_mapping(_reseal(cue_claim))

    def test_exact_pr3_to_v4_to_record_to_typed_asset_lineage(self):
        expected_types = {
            "music": MusicAssetVersion,
            "paper": SfxAssetVersion,
            "rain": AmbienceAssetVersion,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_music_sequence: list[int] | None = None
            for ordinal, (kind, expected_type) in enumerate(
                expected_types.items(), start=1
            ):
                with self.subTest(kind=kind):
                    storage_key = f"asset-versions/audio/pr6/{kind}-contract.wav"
                    chain = execute_programmatic_chain(
                        kind,
                        seed=100 + ordinal,
                        storage_key=storage_key,
                        artifact_root=root,
                    )
                    request = chain["generationRequest"].as_dict()
                    execution = chain["executionRequest"].as_dict()
                    evidence = chain["executionEvidence"].as_dict()
                    record = chain["generationRecord"].as_dict()
                    asset_wrapper = chain["assetVersion"]
                    asset = asset_wrapper.as_dict()

                    self.assertIs(type(asset_wrapper), expected_type)
                    self.assertEqual(record["generationRequestDigest"], request["payloadDigest"])
                    self.assertEqual(record["executionRequestDigest"], execution["payloadDigest"])
                    self.assertEqual(record["executionEvidenceDigest"], evidence["payloadDigest"])
                    self.assertEqual(record["rightsBindingDigest"], request["rightsBinding"]["payloadDigest"])
                    self.assertEqual(record["pcmContentDigest"], evidence["technicalAnalysisEvidence"]["pcmContentDigest"])
                    self.assertEqual(asset["generationResultRef"], record["generationRecordRef"])
                    self.assertEqual(asset["generationResultDigest"], record["payloadDigest"])
                    self.assertEqual(asset["provenance"]["generationRecordRef"], record["generationRecordRef"])
                    self.assertEqual(asset["rightsBinding"], request["rightsBinding"])
                    self.assertIsNot(asset["rightsBinding"], request["rightsBinding"])
                    self.assertEqual(asset["sourceAudioCueRefs"], [])
                    self.assertEqual(asset["artifact"]["storageKey"], storage_key)
                    self.assertTrue((root / storage_key).is_file())
                    provenance_sources = {
                        (source["sourceRef"], source["sourceDigest"])
                        for source in asset["provenance"]["sourceRefs"]
                    }
                    self.assertIn(
                        (execution["executionRequestRef"], execution["payloadDigest"]),
                        provenance_sources,
                    )
                    self.assertIn(
                        (evidence["executionEvidenceRef"], evidence["payloadDigest"]),
                        provenance_sources,
                    )
                    if kind == "music":
                        self.assertEqual(record["musicQualityApproval"], "HUMAN_REQUIRED")
                        self.assertEqual(asset["musicSourceKind"], "PROGRAMMATIC")
                        self.assertEqual(
                            record["deterministicNoteSequence"],
                            evidence["recipe"]["derivedNoteSequence"],
                        )
                        self.assertEqual(
                            len(record["deterministicNoteSequence"]), 16
                        )
                        first_music_sequence = record[
                            "deterministicNoteSequence"
                        ]
                    else:
                        self.assertIsNone(record["deterministicNoteSequence"])
                        self.assertIsNone(
                            evidence["recipe"].get("derivedNoteSequence")
                        )

                    later_asset = build_programmatic_audio_asset_version(
                        chain["generationRequest"],
                        synthesis_spec=chain["synthesisSpec"],
                        execution_context=chain["executionContext"],
                        execution_request=chain["executionRequest"],
                        execution_evidence=chain["executionEvidence"],
                        generation_record=chain["generationRecord"],
                        created_at="2026-08-29T16:00:01Z",
                    ).as_dict()
                    self.assertNotEqual(asset["assetRef"], later_asset["assetRef"])
                    self.assertNotEqual(
                        asset["assetVersionRef"],
                        later_asset["assetVersionRef"],
                    )
                    self.assertNotEqual(
                        asset["payloadDigest"], later_asset["payloadDigest"]
                    )

                    with self.assertRaises(ProgrammaticAudioSynthesisError):
                        build_programmatic_audio_generation_record(
                            chain["generationRequest"],
                            synthesis_spec=chain["synthesisSpec"],
                            execution_context=chain["executionContext"],
                            execution_request=chain["executionRequest"],
                            execution_evidence=evidence,
                        )

                    class AudioSynthesisExecutionEvidenceSubclass(
                        AudioSynthesisExecutionEvidence
                    ):
                        pass

                    evidence_subclass = (
                        AudioSynthesisExecutionEvidenceSubclass._from_executor(
                            evidence,
                            chain[
                                "executionEvidence"
                            ].technical_analysis_evidence(),
                        )
                    )
                    with self.assertRaises(ProgrammaticAudioSynthesisError):
                        build_programmatic_audio_generation_record(
                            chain["generationRequest"],
                            synthesis_spec=chain["synthesisSpec"],
                            execution_context=chain["executionContext"],
                            execution_request=chain["executionRequest"],
                            execution_evidence=evidence_subclass,
                        )
                    stale_record = deepcopy(record)
                    stale_record["payloadDigest"] = "0" * 64
                    with self.assertRaises(StaleInputError):
                        validate_programmatic_audio_generation_record(
                            stale_record,
                            generation_request=chain["generationRequest"],
                            synthesis_spec=chain["synthesisSpec"],
                            execution_context=chain["executionContext"],
                            execution_request=chain["executionRequest"],
                            execution_evidence=chain["executionEvidence"],
                        )

            same_music = execute_programmatic_chain(
                "music",
                seed=101,
                storage_key="asset-versions/audio/pr6/music-sequence-same.wav",
                artifact_root=root,
            )["generationRecord"].as_dict()["deterministicNoteSequence"]
            different_music = execute_programmatic_chain(
                "music",
                seed=10_101,
                storage_key=(
                    "asset-versions/audio/pr6/music-sequence-different.wav"
                ),
                artifact_root=root,
            )["generationRecord"].as_dict()["deterministicNoteSequence"]
            self.assertIsNotNone(first_music_sequence)
            self.assertEqual(first_music_sequence, same_music)
            self.assertNotEqual(first_music_sequence, different_music)

    def test_typed_narration_projects_to_v4_and_piper_absence_writes_nothing(self):
        sources = build_typed_narration_sources()
        request = sources["generationRequest"]
        context = build_typed_narration_context(
            request,
            storage_key="asset-versions/audio/pr6/narration-piper.wav",
        )
        execution = build_narration_tts_execution_request(
            request,
            confirmed_voice_lock=sources["confirmedVoiceLock"],
            voice_asset_version=sources["voiceAssetVersion"],
            execution_context=context,
        )
        request_value = request.as_dict()
        voice_value = sources["voiceAssetVersion"].as_dict()
        self.assertEqual(execution["generationRequestDigest"], request_value["payloadDigest"])
        self.assertEqual(execution["voiceRef"], voice_value["voiceIdentityRef"])
        self.assertEqual(execution["parameters"], request_value["requestSpec"]["normalizedSpeechParameters"])
        self.assertEqual(execution["parameters"]["audioRole"], "narration")

        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            with self.assertRaisesRegex(
                NotImplementedError, "PIPER_RUNTIME_ABSENT"
            ):
                execute_piper_tts_evidence(
                    execution,
                    artifact_root=artifact_root,
                    storage_key=context.as_dict()["storageKey"],
                )
            self.assertEqual(list(artifact_root.iterdir()), [])

    def test_narration_direct_mappings_reject_invalid_identity_and_authority(self):
        sources = build_typed_narration_sources()
        base = sources["generationRequest"].as_dict()
        voice_mapping = sources["voiceAssetVersion"].as_dict()

        invalid_cases: list[tuple[str, dict]] = []
        version_false = deepcopy(base)
        version_false["version"] = False
        invalid_cases.append(("version-bool", _reseal(version_false)))

        self_parent = deepcopy(base)
        self_parent["version"] = 2
        self_parent["supersedesGenerationRequestVersionRef"] = self_parent[
            "generationRequestVersionRef"
        ]
        self_parent["supersedesGenerationRequestVersionDigest"] = "f" * 64
        invalid_cases.append(("self-predecessor", _reseal(self_parent)))

        rights_none = deepcopy(base)
        rights_none["rightsBinding"] = None
        invalid_cases.append(("rights-none", _reseal(rights_none)))

        control_character = deepcopy(base)
        control_character["createdBy"] = "invalid\ncreator"
        invalid_cases.append(("control-character", _reseal(control_character)))

        duplicate_sources = deepcopy(base)
        requested = deepcopy(duplicate_sources["requestedProvenance"])
        requested["sourceRefs"].append(deepcopy(requested["sourceRefs"][0]))
        duplicate_sources["requestedProvenance"] = _reseal(requested)
        invalid_cases.append(("duplicate-source-ref", _reseal(duplicate_sources)))

        created_by_non_string = deepcopy(base)
        created_by_non_string["createdBy"] = 17
        invalid_cases.append(("createdBy-non-string", _reseal(created_by_non_string)))

        naive_timestamp = deepcopy(base)
        naive_timestamp["createdAt"] = "2026-08-29T16:00:00"
        invalid_cases.append(("naive-timestamp", _reseal(naive_timestamp)))

        cue_claim = deepcopy(base)
        cue_claim["requestSpec"]["sourceAudioCueRefs"] = ["audio-cue-v1"]
        invalid_cases.append(("nonempty-audio-cue", _reseal(cue_claim)))

        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            for label, invalid in invalid_cases:
                with self.subTest(case=label), self.assertRaises(
                    EpisodeProductionError
                ):
                    AudioGenerationRequest.from_mapping(
                        invalid,
                        confirmed_voice_lock=sources["confirmedVoiceLock"],
                        voice_asset_version=voice_mapping,
                    )
            self.assertEqual(list(artifact_root.iterdir()), [])

    def test_fixed_wav_builds_only_zero_authority_narration_projections(self):
        self.assertIn("test-only", (FixedWavTtsAdapter.__doc__ or "").lower())
        self.assertEqual(FixedWavTtsAdapter.__module__, "tests.stub_tts_adapter")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = "asset-versions/audio/pr6/narration-fixed-test.wav"
            chain = execute_typed_narration_test_chain(
                artifact_root=root, storage_key=storage_key
            )
            request = chain["generationRequest"].as_dict()
            voice = chain["voiceAssetVersion"].as_dict()
            execution = chain["executionRequest"]
            bundle = chain["artifactBundle"]
            evidence_wrapper = chain["testEvidenceProjection"]
            dialogue_wrapper = chain["dialogueProjection"]
            evidence = evidence_wrapper.as_dict()
            dialogue = dialogue_wrapper.as_dict()

            self.assertIs(type(evidence_wrapper), NarrationTestEvidenceProjection)
            self.assertIs(type(dialogue_wrapper), NarrationTestDialogueProjection)
            self.assertNotIsInstance(dialogue_wrapper, DialogueAssetVersion)
            self.assertEqual(chain["adapter"].calls, [execution])
            self.assertEqual((root / storage_key).read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(evidence["generationRequestDigest"], request["payloadDigest"])
            self.assertEqual(evidence["executionRequestDigest"], execution["payloadDigest"])
            self.assertEqual(evidence["v4GenerationResultRef"], bundle["generationResultRef"])
            self.assertEqual(evidence["v4GenerationResultDigest"], bundle["generationResultDigest"])
            self.assertEqual(evidence["voiceAssetVersionRef"], voice["assetVersionRef"])
            self.assertEqual(evidence["rightsBindingRef"], request["rightsBinding"]["rightsBindingRef"])
            self.assertEqual(evidence["rightsBindingDigest"], request["rightsBinding"]["payloadDigest"])
            self.assertEqual(evidence["testFixtureOnly"], NARRATION_TEST_FIXTURE_MARKER)
            self.assertEqual(evidence["actualRuntimeIdentity"], NARRATION_TEST_RUNTIME_IDENTITY)
            self.assertEqual(evidence["requiredRuntimeState"], NARRATION_REQUIRED_RUNTIME_STATE)
            self.assertEqual(evidence["authorityState"], NARRATION_TEST_AUTHORITY_STATE)
            self.assertFalse(evidence["assetVersionAllowed"])
            self.assertFalse(evidence["publicationAllowed"])
            self.assertEqual(
                evidence["provenance"]["parametersDigest"],
                evidence["effectiveParametersDigest"],
            )
            self.assertNotEqual(
                evidence["provenance"]["parametersDigest"],
                evidence["parametersDigest"],
            )
            self.assertEqual(dialogue["testEvidenceProjectionRef"], evidence["testEvidenceProjectionRef"])
            self.assertEqual(dialogue["testEvidenceProjectionDigest"], evidence["payloadDigest"])
            self.assertEqual(dialogue["speechRole"], "narration")
            self.assertIsNone(dialogue["dialogueRef"])
            self.assertEqual(dialogue["narrationRef"], request["requestSpec"]["narrationRef"])
            self.assertEqual(dialogue["sourceAudioCueRefs"], [])
            self.assertEqual(dialogue["storageKey"], storage_key)
            self.assertEqual(dialogue["rightsBindingRef"], evidence["rightsBindingRef"])
            self.assertEqual(dialogue["rightsBindingDigest"], evidence["rightsBindingDigest"])
            self.assertEqual(dialogue["provenance"], evidence["provenance"])
            self.assertEqual(dialogue["testFixtureOnly"], NARRATION_TEST_FIXTURE_MARKER)
            self.assertEqual(dialogue["authorityState"], NARRATION_TEST_AUTHORITY_STATE)
            self.assertFalse(dialogue["assetVersionAllowed"])
            self.assertFalse(dialogue["publicationAllowed"])
            for forbidden in (
                "assetRef",
                "assetVersionRef",
                "assetVersionType",
                "generationResultRef",
                "generationResultDigest",
            ):
                self.assertNotIn(forbidden, dialogue)

            later = build_test_only_narration_dialogue_projection(
                chain["generationRequest"],
                confirmed_voice_lock=chain["confirmedVoiceLock"],
                voice_asset_version=chain["voiceAssetVersion"],
                execution_context=chain["executionContext"],
                execution_request=chain["executionRequest"],
                test_only_fixed_wav_artifact_bundle=chain["artifactBundle"],
                test_evidence_projection=chain["testEvidenceProjection"],
                created_at="2026-08-29T16:00:01Z",
            ).as_dict()
            self.assertNotEqual(
                dialogue["dialogueProjectionRef"], later["dialogueProjectionRef"]
            )
            self.assertNotEqual(dialogue["payloadDigest"], later["payloadDigest"])

            with self.assertRaises(NarrationSynthesisError):
                build_narration_generation_record(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=chain["executionContext"],
                    execution_request=chain["executionRequest"],
                    execution_evidence=chain["artifactBundle"],
                )
            with self.assertRaises(NarrationSynthesisError):
                build_narration_dialogue_asset_version(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=chain["executionContext"],
                    execution_request=chain["executionRequest"],
                    execution_evidence=chain["artifactBundle"],
                    generation_record=chain["testEvidenceProjection"],
                    created_at=CREATED_AT,
                )

    def test_typed_narration_wrong_voice_stale_evidence_and_subclasses_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            chain = execute_typed_narration_test_chain(
                artifact_root=Path(directory),
                storage_key="asset-versions/audio/pr6/narration-fail-closed.wav",
            )

            wrong_lock = voice_bundle("character-other", "voice-other")
            wrong_mapping = local_voice_asset(wrong_lock)
            wrong_voice = VoiceAssetVersion.from_mapping(
                wrong_mapping, confirmed_voice_lock=wrong_lock
            )
            with self.assertRaises(EpisodeProductionError):
                build_narration_tts_execution_request(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=wrong_voice,
                    execution_context=chain["executionContext"],
                )

            grant = consent_grant()
            cloned_mapping = cloned_voice_asset(
                chain["confirmedVoiceLock"], grant
            )
            cloned_voice = VoiceAssetVersion.from_mapping(
                cloned_mapping,
                confirmed_voice_lock=chain["confirmedVoiceLock"],
                consent_grant=grant,
                evaluated_at=AS_OF,
            )
            with self.assertRaises(EpisodeProductionError):
                build_narration_tts_execution_request(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=cloned_voice,
                    execution_context=chain["executionContext"],
                )

            context_command = chain["executionContext"].as_dict()
            context_command.pop("schemaVersion")
            context_command.pop("payloadDigest")
            context_command["assetRequirementDigest"] = "0" * 64
            stale_context = build_narration_execution_context(context_command)
            with self.assertRaises(NarrationEvidenceBindingError):
                build_narration_tts_execution_request(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=stale_context,
                )

            class NarrationExecutionContextSubclass(NarrationExecutionContext):
                pass

            context_subclass = NarrationExecutionContextSubclass.from_mapping(
                chain["executionContext"].as_dict()
            )
            with self.assertRaises(NarrationSynthesisError):
                build_narration_tts_execution_request(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=context_subclass,
                )

            stale_bundle = deepcopy(chain["artifactBundle"])
            stale_bundle["sha256"] = "0" * 64
            stale_bundle = _reseal(stale_bundle)
            with self.assertRaises(StaleInputError):
                build_test_only_narration_evidence_projection(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=chain["executionContext"],
                    execution_request=chain["executionRequest"],
                    test_only_fixed_wav_artifact_bundle=stale_bundle,
                )

            class NarrationTestEvidenceProjectionSubclass(
                NarrationTestEvidenceProjection
            ):
                pass

            evidence_subclass = NarrationTestEvidenceProjectionSubclass._from_derived(
                chain["testEvidenceProjection"].as_dict()
            )
            with self.assertRaises(NarrationSynthesisError):
                build_test_only_narration_dialogue_projection(
                    chain["generationRequest"],
                    confirmed_voice_lock=chain["confirmedVoiceLock"],
                    voice_asset_version=chain["voiceAssetVersion"],
                    execution_context=chain["executionContext"],
                    execution_request=chain["executionRequest"],
                    test_only_fixed_wav_artifact_bundle=chain["artifactBundle"],
                    test_evidence_projection=evidence_subclass,
                    created_at=CREATED_AT,
                )

    def test_music_stem_projects_to_preliminary_mix_without_timeline_authority(self):
        source_bundle = explicit_source_assets()
        source = source_bundle["sources"]["music"]
        member = build_stem_member_fixture(
            source, "music", suffix="pr6-programmatic-music"
        )
        stem_mapping = build_stem_set_fixture(
            source_bundle,
            [member],
            suffix="pr6-programmatic-music",
        )
        stem_set = validate_stem_set_fixture(source_bundle, stem_mapping)
        mix_request = build_preliminary_mix_execution_request(
            preliminary_mix_execution_context(), stem_set=stem_set
        )
        stems = stem_set.as_dict()
        self.assertEqual(stems["members"][0]["stemRole"], "music")
        self.assertEqual(
            mix_request["parameters"]["tracks"][0]["audioRole"], "music"
        )
        self.assertEqual(
            stems["timelineBindingState"], AUDIO_TIMELINE_BINDING_STATE
        )
        self.assertEqual(AUDIO_TIMELINE_BINDING_STATE, "UNASSIGNED")
        forbidden = {
            "timelineRef",
            "timelineVersionRef",
            "timelineClipRef",
            "timelineTrackRef",
            "timelineStartSample",
            "timelineEndSample",
        }
        self.assertTrue(forbidden.isdisjoint(stems))
        self.assertTrue(forbidden.isdisjoint(mix_request))


if __name__ == "__main__":
    unittest.main()
