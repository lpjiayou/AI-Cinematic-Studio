from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from services.v4_platform.audio import (
    PRELIMINARY_MIX_ADAPTER_ID,
    DeterministicPreliminaryMixAdapter,
    DeterministicProgrammaticAudioAdapter,
    audio_artifact_evidence,
    emotion_parameters,
)
from services.v5_core_os.episode_production.audio import (
    build_preliminary_mix_request,
    build_programmatic_audio_request,
    build_proposed_audio_asset_version,
    build_tts_execution_request,
)
from services.v5_core_os.episode_production.audio_authority import (
    build_audio_provenance,
    build_rights_binding,
    build_sfx_asset_version,
    validate_sfx_asset_version,
)
from services.v5_core_os.episode_production.audio_timing import (
    build_audio_stem_member,
    build_audio_stem_set,
    build_audio_timing_provenance,
    build_preliminary_mix_execution_request,
    build_source_audio_timing_evidence,
    validate_audio_stem_set,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.contract.test_m12_audio_execution_contract import dialogue_context
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter


SAMPLE_RATE = 48_000
SHORT_SAMPLES = 4_800
EPISODE_REF = "episode-m12"
CREATED_AT = "2026-08-29T00:00:01Z"


def _programmatic_request(effect_kind: str, *, ordinal: int) -> dict:
    role = "ambience" if effect_kind in {"rain", "wind"} else "sfx"
    dialogue_request, _ = dialogue_context()
    return build_programmatic_audio_request(
        {
            "workspaceRef": dialogue_request["workspaceRef"],
            "productionRunRef": dialogue_request["productionRunRef"],
            "assetRequirementRef": f"requirement-{effect_kind}",
            "assetRequirementDigest": _digest(
                {"requirement": effect_kind}
            ),
            "creativeShotRef": dialogue_request["creativeShotRef"],
            "creativeShotVersionRef": dialogue_request[
                "creativeShotVersionRef"
            ],
            "creativeShotDigest": dialogue_request["creativeShotDigest"],
            "scriptRef": dialogue_request["scriptRef"],
            "scriptVersionRef": dialogue_request["scriptVersionRef"],
            "scriptVersionDigest": dialogue_request["scriptVersionDigest"],
            "scriptSceneRef": dialogue_request["scriptSceneRef"],
            "sourceCueRef": f"scene-1-audio-cue-{ordinal}",
            "sourceCueDigest": _digest(
                {"effectKind": effect_kind, "ordinal": ordinal}
            ),
            "cueOrdinal": ordinal,
            "parameters": {
                "audioRole": role,
                "synthesisKind": "programmatic",
                "effectKind": effect_kind,
                "durationSamples": SHORT_SAMPLES,
                "sampleRate": SAMPLE_RATE,
                "channels": 1,
                "seed": 17 + ordinal,
            },
            "createdAt": "2026-08-29T00:00:00Z",
        }
    )


def _execute_dialogue(
    artifact_root: Path,
    *,
    storage_key: str,
) -> tuple[dict, dict, dict, dict, FixedWavTtsAdapter]:
    request, voice_lock = dialogue_context("whisper")
    execution = build_tts_execution_request(
        request, confirmed_voice_lock=voice_lock
    )
    runtime = FixedWavTtsAdapter()
    artifact = audio_artifact_evidence(
        execution,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=runtime,
    )
    proposed_asset = build_proposed_audio_asset_version(
        request,
        artifact,
        confirmed_voice_lock=voice_lock,
        created_at="2026-08-29T00:00:01Z",
    )
    return request, execution, artifact, proposed_asset, runtime


def _execute_programmatic(
    artifact_root: Path,
    *,
    effect_kind: str,
    ordinal: int,
    storage_key: str,
) -> tuple[dict, dict, dict]:
    request = _programmatic_request(effect_kind, ordinal=ordinal)
    artifact = audio_artifact_evidence(
        request,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=DeterministicProgrammaticAudioAdapter(),
    )
    proposed_asset = build_proposed_audio_asset_version(
        request,
        artifact,
        created_at="2026-08-29T00:00:01Z",
    )
    return request, artifact, proposed_asset


def _sfx_rights_binding(
    *, asset_requirement_ref: str, asset_requirement_digest: str
) -> dict:
    manifest_ref = "rights-manifest-m12-integration"
    manifest_digest = _digest({"rightsManifest": "m12-integration"})
    authority_ref = "rights-authority-m12-integration"
    authority_digest = _digest({"rightsAuthority": "m12-integration"})
    return build_rights_binding(
        {
            "rightsBindingRef": "audio-rights-binding-sfx-m12-integration-v1",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED",
            "ownership": "PROJECT_OWNER",
            "usageScope": ["AUDIO_PRODUCTION", "SFX_GENERATION"],
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": manifest_ref,
                    "sourceDigest": manifest_digest,
                },
                {
                    "sourceRef": authority_ref,
                    "sourceDigest": authority_digest,
                },
                {
                    "sourceRef": asset_requirement_ref,
                    "sourceDigest": asset_requirement_digest,
                },
            ],
            "rightsManifestRef": manifest_ref,
            "rightsManifestVersion": 1,
            "rightsManifestDigest": manifest_digest,
            "authorityEvidenceRef": authority_ref,
            "authorityEvidenceDigest": authority_digest,
        }
    )


def _typed_sfx_asset_version(
    request: dict,
    artifact_result: dict,
    *,
    project_ref: str,
    series_ref: str,
):
    evidence = artifact_result["artifactEvidence"]
    asset_ref = "audio-asset-sfx-" + evidence["sha256"][:24]
    provenance = build_audio_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "adapterIdentity": evidence["adapterIdentity"],
            "generationRecordRef": artifact_result["generationResultRef"],
            "parametersDigest": evidence["parametersDigest"],
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "sourceRefs": [
                {
                    "sourceRef": request["generationRequestVersionRef"],
                    "sourceDigest": request["payloadDigest"],
                },
                {
                    "sourceRef": artifact_result["generationResultRef"],
                    "sourceDigest": artifact_result["generationResultDigest"],
                },
            ],
        }
    )
    asset = build_sfx_asset_version(
        {
            "workspaceRef": request["workspaceRef"],
            "projectRef": project_ref,
            "seriesRef": series_ref,
            "episodeRef": EPISODE_REF,
            "productionRunRef": request["productionRunRef"],
            "assetRef": asset_ref,
            "assetVersionRef": f"{asset_ref}-v1",
            "version": 1,
            "assetRequirementRef": request["assetRequirementRef"],
            "assetRequirementDigest": request["assetRequirementDigest"],
            "generationRequestRef": request["generationRequestRef"],
            "generationRequestVersionRef": request[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": request["payloadDigest"],
            "generationResultRef": artifact_result["generationResultRef"],
            "generationResultDigest": artifact_result[
                "generationResultDigest"
            ],
            "artifact": {
                "artifactKind": "PCM_AUDIO",
                "artifactEvidenceRef": evidence["artifactEvidenceRef"],
                "artifactEvidenceDigest": evidence["payloadDigest"],
                "artifactRef": evidence["artifactRef"],
                "storageKey": evidence["storageKey"],
                "byteSize": evidence["byteSize"],
                "fileDigest": evidence["sha256"],
                "mediaType": "audio/wav",
            },
            "supersedesAssetVersionRef": None,
            "supersedesAssetVersionDigest": None,
            "provenance": provenance,
            "rightsBinding": _sfx_rights_binding(
                asset_requirement_ref=request["assetRequirementRef"],
                asset_requirement_digest=request["assetRequirementDigest"],
            ),
            "sfxKind": request["parameters"]["effectKind"],
            "synthesisSpecDigest": evidence["synthesisSpecDigest"],
            "sourceAudioCueRefs": [],
            "createdBy": "v5.m12.audio-execution.integration-test",
            "createdAt": CREATED_AT,
        }
    )
    return validate_sfx_asset_version(asset)


def _single_sfx_stem_set(
    request: dict,
    artifact_result: dict,
    *,
    project_ref: str,
    series_ref: str,
):
    evidence = artifact_result["artifactEvidence"]
    asset = _typed_sfx_asset_version(
        request,
        artifact_result,
        project_ref=project_ref,
        series_ref=series_ref,
    )
    asset_value = asset.as_dict()
    timing = build_source_audio_timing_evidence(
        evidence,
        source_asset_version=asset,
    )
    rights = asset_value["rightsBinding"]
    duration_samples = timing["sampleCount"]
    member_ref = "audio-stem-member-sfx-m12-integration"
    member = build_audio_stem_member(
        {
            "stemMemberRef": member_ref,
            "stemRole": "sfx",
            "stemLaneRef": "audio-stem-lane-sfx-m12-integration",
            "overlapPolicy": "NON_OVERLAPPING",
            "sourceAssetVersionRef": asset_value["assetVersionRef"],
            "sourceAssetVersionDigest": asset_value["payloadDigest"],
            "sourceAssetVersionType": asset_value["assetVersionType"],
            "sourceCueRef": None,
            "sourceCueVersionRef": None,
            "sourceCueDigest": None,
            "sourceStartSample": 0,
            "sourceEndSample": duration_samples,
            "stemStartSample": 0,
            "stemEndSample": duration_samples,
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
            "provenance": build_audio_timing_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "producerIdentity": "v5.m12.audio-stem.integration-test.v1",
                    "recordRef": member_ref,
                    "parametersDigest": _digest(
                        {
                            "sourceStartSample": 0,
                            "sourceEndSample": duration_samples,
                            "stemStartSample": 0,
                            "stemEndSample": duration_samples,
                        }
                    ),
                    "sourceRefs": [
                        {
                            "sourceRef": asset_value["assetVersionRef"],
                            "sourceDigest": asset_value["payloadDigest"],
                        },
                        {
                            "sourceRef": evidence["artifactEvidenceRef"],
                            "sourceDigest": evidence["payloadDigest"],
                        },
                        {
                            "sourceRef": rights["rightsBindingRef"],
                            "sourceDigest": rights["payloadDigest"],
                        },
                    ],
                }
            ),
            "createdBy": "v5.m12.audio-stem.integration-test",
            "createdAt": CREATED_AT,
        },
        source_asset_version=asset,
        source_artifact_evidence=evidence,
        source_timing_evidence=timing,
        expected_script_version_ref=request["scriptVersionRef"],
        expected_script_version_digest=request["scriptVersionDigest"],
    )
    stem_set_ref = "audio-stem-set-m12-integration"
    context = {
        "source_asset_versions": {asset_value["assetVersionRef"]: asset},
        "source_artifact_evidence": {
            asset_value["assetVersionRef"]: evidence
        },
        "source_timing_evidence": {asset_value["assetVersionRef"]: timing},
        "audio_cues": {},
        "expected_script_version_ref": request["scriptVersionRef"],
        "expected_script_version_digest": request["scriptVersionDigest"],
    }
    stem_set = build_audio_stem_set(
        {
            "workspaceRef": request["workspaceRef"],
            "projectRef": project_ref,
            "seriesRef": series_ref,
            "episodeRef": EPISODE_REF,
            "productionRunRef": request["productionRunRef"],
            "stemSetRef": stem_set_ref,
            "stemSetVersionRef": f"{stem_set_ref}-v1",
            "version": 1,
            "supersedesStemSetVersionRef": None,
            "supersedesStemSetVersionDigest": None,
            "scriptVersionRef": request["scriptVersionRef"],
            "scriptVersionDigest": request["scriptVersionDigest"],
            "sampleRate": timing["sampleRate"],
            "preliminaryDurationSamples": duration_samples,
            "members": [member],
            "provenance": build_audio_timing_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "producerIdentity": "v5.m12.audio-stem-set.integration-test.v1",
                    "recordRef": f"{stem_set_ref}-v1",
                    "parametersDigest": _digest(
                        {
                            "sampleRate": timing["sampleRate"],
                            "preliminaryDurationSamples": duration_samples,
                        }
                    ),
                    "sourceRefs": [
                        {
                            "sourceRef": request["scriptVersionRef"],
                            "sourceDigest": request["scriptVersionDigest"],
                        },
                        {
                            "sourceRef": member["stemMemberRef"],
                            "sourceDigest": member["payloadDigest"],
                        },
                    ],
                }
            ),
            "createdBy": "v5.m12.audio-stem-set.integration-test",
            "createdAt": CREATED_AT,
        },
        **context,
    )
    return validate_audio_stem_set(stem_set, **context), asset_value, timing


class M12AudioExecutionIntegrationTests(unittest.TestCase):
    def test_dialogue_flows_through_fake_piper_to_direct_proposed_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = "asset-versions/audio/shot-1/dialogue-1.wav"
            request, execution, artifact, asset, runtime = _execute_dialogue(
                root,
                storage_key=storage_key,
            )

            effective = deepcopy(execution["parameters"])
            effective["emotionParameters"] = emotion_parameters("whisper")
            self.assertNotEqual(request["payloadDigest"], execution["payloadDigest"])
            self.assertEqual(
                artifact["generationRequestDigest"], request["payloadDigest"]
            )
            self.assertEqual(
                artifact["executionRequestDigest"], execution["payloadDigest"]
            )
            self.assertEqual(
                artifact["parametersDigest"], _digest(execution["parameters"])
            )
            self.assertEqual(
                artifact["effectiveParametersDigest"], _digest(effective)
            )
            self.assertEqual(
                runtime.calls[0]["parameters"], execution["parameters"]
            )

            for field in (
                "assetRequirementRef",
                "assetRequirementDigest",
                "creativeShotRef",
                "creativeShotVersionRef",
                "creativeShotDigest",
                "scriptRef",
                "scriptVersionRef",
                "scriptVersionDigest",
                "scriptSceneRef",
            ):
                self.assertEqual(asset[field], request[field], field)
            self.assertEqual(
                asset["sourceBinding"],
                {
                    "kind": "scriptDialogue",
                    "sourceRef": request["sourceScriptSpan"],
                    "sourceDigest": request["dialogueSourceDigest"],
                    "ordinal": request["dialogueOrdinal"],
                },
            )
            self.assertEqual(
                asset["voiceBinding"]["voiceLockVersionRef"],
                request["voiceLockVersionRef"],
            )
            self.assertEqual(
                asset["voiceBinding"]["voiceLockDigest"],
                request["voiceLockDigest"],
            )
            self.assertEqual(
                asset["generationParametersDigest"],
                artifact["effectiveParametersDigest"],
            )
            for field in (
                "artifactEvidenceRef",
                "artifactEvidenceDigest",
                "artifactRef",
                "storageKey",
                "sha256",
                "sampleRate",
                "channels",
            ):
                self.assertEqual(asset[field], artifact[field], field)

            output = root / storage_key
            self.assertEqual(output.read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(list(root.rglob("*.wav")), [output])
            self.assertEqual(
                PurePosixPath(asset["storageKey"]).parts[:2],
                ("asset-versions", "audio"),
            )
            self.assertTrue(
                {"jobs", "legacy", "media"}.isdisjoint(
                    PurePosixPath(asset["storageKey"]).parts
                )
            )
            self.assertFalse(asset["publicationAllowed"])
            self.assertEqual(asset["state"], "PROPOSED")
            self.assertNotIn("assetAdmissionRef", asset)
            self.assertFalse(artifact["publicationAllowed"])
            self.assertFalse(artifact["generationResult"]["publicationAllowed"])
            self.assertFalse(artifact["artifactEvidence"]["publicationAllowed"])

    def test_rain_and_paper_are_deterministic_role_specific_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for ordinal, (effect_kind, expected_role) in enumerate(
                (("rain", "ambience"), ("paper", "sfx")), start=1
            ):
                with self.subTest(effect_kind=effect_kind):
                    request = _programmatic_request(effect_kind, ordinal=ordinal)
                    first = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=(
                            f"asset-versions/audio/shot-1/{effect_kind}-1.wav"
                        ),
                        adapter=DeterministicProgrammaticAudioAdapter(),
                    )
                    second = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=(
                            f"asset-versions/audio/shot-1/{effect_kind}-2.wav"
                        ),
                        adapter=DeterministicProgrammaticAudioAdapter(),
                    )
                    asset = build_proposed_audio_asset_version(
                        request,
                        first,
                        created_at="2026-08-29T00:00:01Z",
                    )

                    self.assertEqual(first["sha256"], second["sha256"])
                    self.assertEqual(first["probe"], second["probe"])
                    self.assertEqual(first["probe"]["durationSamples"], SHORT_SAMPLES)
                    self.assertEqual(asset["audioRole"], expected_role)
                    self.assertEqual(asset["sourceBinding"]["kind"], "audioCue")
                    self.assertEqual(
                        asset["sourceBinding"]["sourceRef"],
                        request["sourceCueRef"],
                    )
                    self.assertEqual(
                        asset["sourceBinding"]["sourceDigest"],
                        request["sourceCueDigest"],
                    )
                    self.assertIsNone(asset["voiceBinding"])
                    self.assertEqual(
                        asset["synthesisBinding"]["effectKind"], effect_kind
                    )
                    self.assertEqual(
                        asset["synthesisBinding"]["synthesisSpecDigest"],
                        first["synthesisSpecDigest"],
                    )
                    self.assertEqual(
                        asset["generationRequestDigest"], request["payloadDigest"]
                    )
                    self.assertEqual(
                        asset["generationParametersDigest"],
                        first["effectiveParametersDigest"],
                    )
                    self.assertFalse(asset["publicationAllowed"])

    def test_preliminary_mix_ducks_internal_tracks_and_canonicalizes_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, dialogue_asset, _ = _execute_dialogue(
                root,
                storage_key="asset-versions/audio/shot-1/dialogue-stem.wav",
            )
            _, _, ambience_asset = _execute_programmatic(
                root,
                effect_kind="rain",
                ordinal=1,
                storage_key="asset-versions/audio/shot-1/rain-stem.wav",
            )
            _, _, sfx_asset = _execute_programmatic(
                root,
                effect_kind="paper",
                ordinal=2,
                storage_key="asset-versions/audio/shot-1/paper-stem.wav",
            )
            assets = [dialogue_asset, sfx_asset, ambience_asset]
            first_request = build_preliminary_mix_request(assets)
            second_request = build_preliminary_mix_request(
                list(reversed(assets))
            )
            adapter = DeterministicPreliminaryMixAdapter(root)

            first = audio_artifact_evidence(
                first_request,
                artifact_root=root,
                storage_key="asset-versions/audio/shot-1/preliminary-mix-1.wav",
                adapter=adapter,
            )
            second = audio_artifact_evidence(
                second_request,
                artifact_root=root,
                storage_key="asset-versions/audio/shot-1/preliminary-mix-2.wav",
                adapter=adapter,
            )

            self.assertEqual(
                {
                    track["audioRole"]
                    for track in first_request["parameters"]["tracks"]
                },
                {"dialogue", "sfx", "ambience"},
            )
            self.assertEqual(first["audioRole"], "preliminary_mix")
            self.assertEqual(first["adapterIdentity"], PRELIMINARY_MIX_ADAPTER_ID)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["probe"], second["probe"])
            self.assertEqual(first["probe"]["durationSamples"], SHORT_SAMPLES)
            self.assertNotIn(
                first["sha256"], {asset["sha256"] for asset in (
                    dialogue_asset,
                    sfx_asset,
                    ambience_asset,
                )}
            )
            self.assertEqual(first["generationResult"]["state"], "SUCCEEDED")
            self.assertEqual(
                first["artifactEvidence"]["state"], "TECHNICALLY_VERIFIED"
            )
            self.assertFalse(first["publicationAllowed"])

    def test_stem_set_projection_executes_through_v4_preliminary_mix_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_request = _programmatic_request("paper", ordinal=3)
            source_result = audio_artifact_evidence(
                source_request,
                artifact_root=root,
                storage_key="asset-versions/audio/shot-1/stem-source-paper.wav",
                adapter=DeterministicProgrammaticAudioAdapter(),
            )
            _, voice_lock = dialogue_context()
            scope = voice_lock["voiceLock"]
            stem_set, source_asset, source_timing = _single_sfx_stem_set(
                source_request,
                source_result,
                project_ref=scope["projectRef"],
                series_ref=scope["seriesRef"],
            )
            mix_request = build_preliminary_mix_execution_request(
                {
                    "creativeShotRef": source_request["creativeShotRef"],
                    "creativeShotVersionRef": source_request[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": source_request[
                        "creativeShotDigest"
                    ],
                    "scriptRef": source_request["scriptRef"],
                    "scriptSceneRef": source_request["scriptSceneRef"],
                },
                stem_set=stem_set,
            )
            mix_storage_key = (
                "asset-versions/audio/shot-1/stem-set-preliminary-mix.wav"
            )
            mix_result = audio_artifact_evidence(
                mix_request,
                artifact_root=root,
                storage_key=mix_storage_key,
                adapter=DeterministicPreliminaryMixAdapter(root),
            )

            self.assertEqual(
                mix_request["parameters"]["tracks"],
                [
                    {
                        "audioRole": "sfx",
                        "assetVersionRef": source_asset["assetVersionRef"],
                        "assetVersionDigest": source_asset["payloadDigest"],
                        "storageKey": source_timing["storageKey"],
                        "sha256": source_timing["fileDigest"],
                        "sampleRate": SAMPLE_RATE,
                        "channels": 1,
                        "durationSamples": SHORT_SAMPLES,
                    }
                ],
            )
            self.assertEqual(
                mix_result["generationRequestDigest"],
                mix_request["payloadDigest"],
            )
            self.assertEqual(
                mix_result["executionRequestDigest"],
                mix_request["payloadDigest"],
            )
            self.assertEqual(
                mix_result["parametersDigest"],
                _digest(mix_request["parameters"]),
            )
            self.assertEqual(
                mix_result["artifactEvidenceDigest"],
                mix_result["artifactEvidence"]["payloadDigest"],
            )
            self.assertEqual(
                mix_result["generationResultDigest"],
                mix_result["generationResult"]["payloadDigest"],
            )
            self.assertEqual(mix_result["audioRole"], "preliminary_mix")
            self.assertEqual(
                mix_result["adapterIdentity"], PRELIMINARY_MIX_ADAPTER_ID
            )
            self.assertEqual(mix_result["generationResult"]["state"], "SUCCEEDED")
            self.assertEqual(
                mix_result["artifactEvidence"]["state"],
                "TECHNICALLY_VERIFIED",
            )
            self.assertEqual(
                mix_result["probe"],
                {
                    "sampleRate": SAMPLE_RATE,
                    "channels": 1,
                    "durationSeconds": SHORT_SAMPLES / SAMPLE_RATE,
                    "durationSamples": SHORT_SAMPLES,
                    "codec": "pcm_s16le",
                    "container": "wav",
                },
            )
            self.assertNotEqual(
                mix_result["sha256"], source_result["sha256"]
            )
            output = root.joinpath(*PurePosixPath(mix_storage_key).parts)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 44)
            self.assertFalse(mix_result["publicationAllowed"])


if __name__ == "__main__":
    unittest.main()
