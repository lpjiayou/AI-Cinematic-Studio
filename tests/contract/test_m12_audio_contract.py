from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production.audio import (
    AUDIO_ASSET_VERSION_SCHEMA_VERSION,
    K2AudioProductionService,
    normalize_speech_parameters,
    reject_speech_synthesis_in_legacy_media,
    validate_audio_asset_version_contract,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    UpstreamNotReadyError,
    _digest,
)
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.media import (
    K2MediaExecutionService,
    LegacyMediaExecutionWriteDisabledError,
)


WORKSPACE = "workspace-m12"
PROJECT = "project-m12"
SERIES = "series-m12"
RUN = "run-m12"


def sealed(value):
    result = deepcopy(value)
    result["payloadDigest"] = _digest(result)
    return result


def voice_bundle(character_ref, voice_ref):
    version = sealed(
        {
            "schemaVersion": "v5.voice-lock-version.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": voice_ref,
            "voiceLockVersionRef": f"{voice_ref}-version-1",
            "versionNumber": 1,
            "parentVoiceLockVersionRef": None,
            "parentVoiceLockDigest": None,
            "characterRef": character_ref,
            "engineFamily": "local-neural-tts-v1",
            "voiceId": f"engine-{character_ref}",
            "gender": "female" if character_ref.endswith("lin") else "male",
            "apparentAge": 30,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "中低音",
            "languageCode": "zh-CN",
            "state": "CANDIDATE",
            "immutable": True,
            "createdAt": "2026-08-29T00:00:00Z",
        }
    )
    confirmation = sealed(
        {
            "schemaVersion": "v5.voice-lock-confirmation.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceLockConfirmationRef": f"confirmation-{voice_ref}",
            "voiceRef": voice_ref,
            "voiceLockVersionRef": version["voiceLockVersionRef"],
            "voiceLockDigest": version["payloadDigest"],
            "characterRef": character_ref,
            "state": "CONFIRMED",
            "createdAt": "2026-08-29T00:00:01Z",
        }
    )
    root = sealed(
        {
            "schemaVersion": "v5.voice-lock.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": voice_ref,
            "characterRef": character_ref,
            "currentVoiceLockVersionRef": version["voiceLockVersionRef"],
            "confirmedVoiceLockVersionRef": version["voiceLockVersionRef"],
            "confirmedVoiceLockDigest": version["payloadDigest"],
            "revision": 2,
            "createdAt": "2026-08-29T00:00:00Z",
            "updatedAt": "2026-08-29T00:00:01Z",
        }
    )
    return {
        "voiceLock": root,
        "voiceLockVersion": version,
        "voiceLockConfirmation": confirmation,
    }


class VoiceReader:
    def __init__(self, values):
        self.values = values

    def get_confirmed_voice_lock(
        self, workspace_ref, project_ref, series_ref, character_ref
    ):
        if (workspace_ref, project_ref, series_ref) != (
            WORKSPACE,
            PROJECT,
            SERIES,
        ) or character_ref not in self.values:
            raise UpstreamNotReadyError("confirmed VoiceLock is required")
        return deepcopy(self.values[character_ref])


class RootService:
    def get_run(self, workspace_ref, run_ref):
        if (workspace_ref, run_ref) != (WORKSPACE, RUN):
            raise AssertionError("unexpected scope")
        return {"workspaceRef": workspace_ref, "productionRunRef": run_ref}


class ShotGraph:
    def __init__(self, verified):
        self.verified = verified
        self.root_service = RootService()

    def verify_shot_graph_current(self, workspace_ref, run_ref):
        if (workspace_ref, run_ref) != (WORKSPACE, RUN):
            raise AssertionError("unexpected scope")
        return deepcopy(self.verified)


def fixture(dialogue):
    root = sealed(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "scriptRef": "script-m12",
            "scriptVersionRef": "script-version-m12",
            "upstreamSnapshot": {"script": {"versionDigest": "1" * 64}},
        }
    )
    spans = ["/scenes/0/action"] + [
        f"/scenes/0/dialogue/{index}" for index in range(len(dialogue))
    ]
    shot = sealed(
        {
            "creativeShotRef": "shot-1",
            "creativeShotVersionRef": "shot-version-1",
            "scriptSceneRef": "scene-1",
            "sourceScriptSpans": spans,
            "dialogueRequirements": deepcopy(dialogue),
            "requiredCharacterIdentityLocks": [
                {"scriptCharacterName": "林澈", "characterRef": "character-lin"},
                {"scriptCharacterName": "顾言", "characterRef": "character-gu"},
            ],
        }
    )
    graph = sealed(
        {
            "executableShotGraphVersionRef": "graph-version-1",
            "createdAt": "2026-08-29T00:00:02Z",
            "shots": [
                {
                    "creativeShotRef": shot["creativeShotRef"],
                    "creativeShotVersionRef": shot["creativeShotVersionRef"],
                    "payloadDigest": shot["payloadDigest"],
                    "globalOrder": 1,
                }
            ],
        }
    )
    return {
        "root": root,
        "executableShotGraph": graph,
        "creativeShotVersions": [shot],
    }


def audio_asset_version(request, *, storage_key):
    return sealed(
        {
            "schemaVersion": AUDIO_ASSET_VERSION_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRef": "audio-asset-1",
            "assetVersionRef": "audio-asset-version-1",
            "version": 1,
            "assetKind": "audio",
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "assetAdmissionRef": "audio-admission-1",
            "assetAdmissionVersion": 1,
            "assetAdmissionDigest": "2" * 64,
            "assetRequirementRef": request["assetRequirementRef"],
            "assetRequirementDigest": request["assetRequirementDigest"],
            "generationRequestRef": request["generationRequestRef"],
            "generationRequestVersionRef": request[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": request["payloadDigest"],
            "generationResultRef": "generation-result-1",
            "generationResultDigest": "3" * 64,
            "creativeShotRef": request["creativeShotRef"],
            "creativeShotVersionRef": request["creativeShotVersionRef"],
            "creativeShotDigest": request["creativeShotDigest"],
            "scriptRef": request["scriptRef"],
            "scriptVersionRef": request["scriptVersionRef"],
            "scriptVersionDigest": request["scriptVersionDigest"],
            "scriptSceneRef": request["scriptSceneRef"],
            "sourceScriptSpan": request["sourceScriptSpan"],
            "dialogueOrdinal": request["dialogueOrdinal"],
            "dialogueSourceDigest": request["dialogueSourceDigest"],
            "characterRef": request["characterRef"],
            "voiceRef": request["voiceRef"],
            "voiceLockVersionRef": request["voiceLockVersionRef"],
            "voiceLockDigest": request["voiceLockDigest"],
            "engineFamily": request["adapterCapability"],
            "voiceId": "engine-character-lin",
            "generationParametersDigest": _digest(request["parameters"]),
            "audioRole": request["parameters"]["audioRole"],
            "artifactEvidenceRef": "tts-evidence-1",
            "artifactEvidenceDigest": "4" * 64,
            "artifactRef": "tts-artifact-1",
            "storageKey": storage_key,
            "byteSize": 4096,
            "sha256": "a" * 64,
            "sampleRate": 48_000,
            "channels": 1,
            "probe": {
                "sampleRate": 48_000,
                "channels": 1,
                "durationSeconds": 1.25,
                "codec": "pcm_s16le",
                "container": "wav",
            },
            "supersedesAssetVersionRef": None,
            "supersedesAssetVersionDigest": None,
            "provenance": "LOCAL_EVIDENCE",
            "rightsState": "LOCAL_EVIDENCE_ONLY",
            "state": "REGISTERED",
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": "v5.k2.audio-admission.v1",
            "createdAt": "2026-08-29T00:00:03Z",
        }
    )


class M12AudioContractTests(unittest.TestCase):
    def setUp(self):
        self.voices = VoiceReader(
            {
                "character-lin": voice_bundle("character-lin", "voice-lin"),
                "character-gu": voice_bundle("character-gu", "voice-gu"),
            }
        )

    def service(self, dialogue):
        return K2AudioProductionService(
            ShotGraph(fixture(dialogue)),
            self.voices,
        )

    def test_speech_synthesis_requires_text_voice_and_confirmed_lock(self):
        bundle = self.voices.get_confirmed_voice_lock(
            WORKSPACE, PROJECT, SERIES, "character-lin"
        )
        base = {
            "speechSynthesis": True,
            "text": "不要动。",
            "voiceRef": "voice-lin",
            "audioRole": "dialogue",
        }
        for field in ("text", "voiceRef"):
            invalid = {key: value for key, value in base.items() if key != field}
            with self.subTest(field=field), self.assertRaises(EpisodeProductionError):
                normalize_speech_parameters(
                    invalid, confirmed_voice_lock=bundle
                )
        with self.assertRaises(UpstreamNotReadyError):
            normalize_speech_parameters(base)

        unconfirmed = deepcopy(bundle)
        unconfirmed["voiceLockConfirmation"]["state"] = "CANDIDATE"
        unconfirmed["voiceLockConfirmation"] = sealed(
            {
                key: value
                for key, value in unconfirmed["voiceLockConfirmation"].items()
                if key != "payloadDigest"
            }
        )
        with self.assertRaises(EpisodeProductionError):
            normalize_speech_parameters(
                base, confirmed_voice_lock=unconfirmed
            )

    def test_true_parameters_fill_defaults_and_enforce_enums(self):
        bundle = self.voices.get_confirmed_voice_lock(
            WORKSPACE, PROJECT, SERIES, "character-lin"
        )
        normalized = normalize_speech_parameters(
            {
                "speechSynthesis": True,
                "text": "不要动。",
                "voiceRef": "voice-lin",
                "emotionTag": "tense",
                "audioRole": "dialogue",
            },
            confirmed_voice_lock=bundle,
        )
        self.assertEqual(normalized["sampleRate"], 48_000)
        self.assertEqual(normalized["channels"], 1)
        self.assertEqual(normalized["emotionTag"], "tense")
        for field, value in (
            ("emotionTag", "happy"),
            ("emotionTag", []),
            ("audioRole", "bgm"),
            ("audioRole", {}),
        ):
            invalid = deepcopy(normalized)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(EpisodeProductionError):
                normalize_speech_parameters(
                    invalid, confirmed_voice_lock=bundle
                )

    def test_dialogue_speaker_type_fails_closed(self):
        dialogue = [{"speaker": [], "text": "不要动。", "emotion": "克制"}]
        with patch(
            "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
        ), self.assertRaises(EpisodeProductionError):
            self.service(dialogue).plan_dialogue_requests(WORKSPACE, RUN)

    def test_dialogue_plan_is_ordered_voice_bound_and_not_dispatchable(self):
        dialogue = [
            {"speaker": "林澈", "text": "不要动。", "emotion": "克制"},
            {"speaker": "顾言", "text": "把门关上。", "emotion": "紧张"},
        ]
        with patch(
            "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
        ):
            plan = self.service(dialogue).plan_dialogue_requests(WORKSPACE, RUN)
        requests = plan["generationRequests"]
        self.assertEqual(plan["summary"], {"dialogueRequests": 2})
        self.assertEqual(plan["authorityState"], "CONTRACT_ONLY_NOT_DURABLE")
        self.assertFalse(plan["dispatchAllowed"])
        self.assertEqual([item["ordinal"] for item in requests], [1, 2])
        self.assertEqual([item["dialogueOrdinal"] for item in requests], [1, 2])
        self.assertEqual(
            [item["characterRef"] for item in requests],
            ["character-lin", "character-gu"],
        )
        self.assertEqual(
            [item["voiceRef"] for item in requests], ["voice-lin", "voice-gu"]
        )
        self.assertTrue(
            all(item["parameters"]["speechSynthesis"] for item in requests)
        )
        self.assertTrue(all("emotionTag" not in item["parameters"] for item in requests))

    def test_no_dialogue_produces_no_dialogue_audio_request(self):
        with patch(
            "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
        ):
            plan = self.service([]).plan_dialogue_requests(WORKSPACE, RUN)
        self.assertEqual(plan["audioRequirements"], [])
        self.assertEqual(plan["generationRequests"], [])

    def test_audio_asset_version_contract_rejects_legacy_path_without_writing(self):
        dialogue = [{"speaker": "林澈", "text": "不要动。", "emotion": "克制"}]
        patcher = patch(
            "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
        )
        with patcher:
            request = self.service(dialogue).plan_dialogue_requests(WORKSPACE, RUN)[
                "generationRequests"
            ][0]
        valid = audio_asset_version(
            request,
            storage_key="asset-versions/audio/shot-1/dialogue-1.wav",
        )
        self.assertEqual(
            validate_audio_asset_version_contract(valid),
            valid,
        )
        legacy = audio_asset_version(
            request,
            storage_key="jobs/request/audio.wav",
        )
        with self.assertRaises(EpisodeProductionError):
            validate_audio_asset_version_contract(legacy)

        successor = sealed(
            {
                **{
                    key: value
                    for key, value in valid.items()
                    if key != "payloadDigest"
                },
                "assetVersionRef": "audio-asset-version-2",
                "version": 2,
                "supersedesAssetVersionRef": valid["assetVersionRef"],
                "supersedesAssetVersionDigest": valid["payloadDigest"],
            }
        )
        self.assertEqual(
            validate_audio_asset_version_contract(successor),
            successor,
        )

        non_string_role = sealed(
            {
                **{
                    key: value
                    for key, value in valid.items()
                    if key != "payloadDigest"
                },
                "audioRole": [],
            }
        )
        with self.assertRaises(EpisodeProductionError):
            validate_audio_asset_version_contract(non_string_role)

        self_cycle = sealed(
            {
                **{
                    key: value
                    for key, value in valid.items()
                    if key != "payloadDigest"
                },
                "version": 2,
                "supersedesAssetVersionRef": valid["assetVersionRef"],
                "supersedesAssetVersionDigest": valid["payloadDigest"],
            }
        )
        with self.assertRaises(EpisodeProductionError):
            validate_audio_asset_version_contract(self_cycle)

    def test_plan_reads_each_character_voice_once(self):
        class OneReadVoiceReader(VoiceReader):
            def __init__(self, values):
                super().__init__(values)
                self.reads = 0

            def get_confirmed_voice_lock(
                self, workspace_ref, project_ref, series_ref, character_ref
            ):
                self.reads += 1
                if self.reads > 1:
                    raise AssertionError("voice changed inside one plan")
                return super().get_confirmed_voice_lock(
                    workspace_ref, project_ref, series_ref, character_ref
                )

        reader = OneReadVoiceReader(
            {"character-lin": voice_bundle("character-lin", "voice-lin")}
        )
        dialogue = [
            {"speaker": "林澈", "text": "第一句。", "emotion": "克制"},
            {"speaker": "林澈", "text": "第二句。", "emotion": "克制"},
        ]
        with patch(
            "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
        ):
            plan = K2AudioProductionService(
                ShotGraph(fixture(dialogue)), reader
            ).plan_dialogue_requests(WORKSPACE, RUN)
        self.assertEqual(len(plan["generationRequests"]), 2)
        self.assertEqual(reader.reads, 1)

    def test_legacy_false_parameters_are_unchanged_and_true_is_rejected(self):
        legacy = {
            "durationFrames": 24,
            "frameRate": 24,
            "sampleRate": 48_000,
            "channels": 2,
            "sampleFormat": "s16",
            "container": "wav",
            "toneFrequencyHz": 275,
            "speechSynthesis": False,
        }
        self.assertEqual(normalize_speech_parameters(legacy), legacy)
        reject_speech_synthesis_in_legacy_media(
            [{"mediaKind": "audio", "parameters": legacy}]
        )
        with self.assertRaises(EpisodeProductionError):
            reject_speech_synthesis_in_legacy_media(
                [
                    {
                        "mediaKind": "audio",
                        "parameters": {
                            "speechSynthesis": True,
                            "text": "不要动。",
                            "voiceRef": "voice-lin",
                        },
                    }
                ]
            )

    def test_legacy_g5_rejects_all_new_work_before_worker_or_canonical_write(self):
        class Root:
            def get_run(self, workspace_ref, run_ref):
                return {"workspaceRef": workspace_ref, "productionRunRef": run_ref}

        class ShotGraph:
            root_service = Root()

        class Assets:
            shot_graph = ShotGraph()

            def verify_asset_plan_current(self, workspace_ref, run_ref):
                self.scope = (workspace_ref, run_ref)
                return {
                    "root": {"payloadDigest": "1" * 64},
                    "executableShotGraph": {},
                    "assetResolutionManifest": {"payloadDigest": "2" * 64},
                    "generationRequests": [
                        {
                            "mediaKind": "audio",
                            "parameters": {
                                "speechSynthesis": True,
                                "text": "不要动。",
                                "voiceRef": "voice-lin",
                            },
                        }
                    ],
                }

        class Execution:
            def __init__(self):
                self.called = False

            def execute_batch(self, *args, **kwargs):
                del args, kwargs
                self.called = True
                return []

        evidence = InMemoryEpisodeProductionEvidenceAdapter()
        execution = Execution()
        service = K2MediaExecutionService(
            Assets(),
            evidence,
            execution,
            ref_factory=lambda prefix: f"{prefix}-1",
            clock=lambda: "2026-08-29T00:00:03Z",
        )
        with self.assertRaises(LegacyMediaExecutionWriteDisabledError):
            service.execute_media(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": RUN,
                    "idempotencyKey": "legacy-tts-must-stop",
                }
            )
        self.assertFalse(execution.called)
        self.assertIsNone(evidence.get_gate(WORKSPACE, RUN, "G5_MEDIA_EXECUTION"))


if __name__ == "__main__":
    unittest.main()
