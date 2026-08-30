from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sys
import unittest

from apps.creator_workspace_mvp import public_contract
from services.v4_platform import isolated_speech_runtime as runtime_contract
from services.v4_platform.isolated_speech_runtime import (
    COSYVOICE_BUILD_VOICE_PROFILE,
    COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION,
    COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION,
    COSYVOICE_ENGINE_COMMIT,
    COSYVOICE_ENGINE_ID,
    COSYVOICE_MANIFEST_SCHEMA_VERSION,
    COSYVOICE_MODEL_BUNDLE_SHA256,
    COSYVOICE_MODEL_ID,
    COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION,
    COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION,
    COSYVOICE_RUNTIME_KIND,
    COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    CosyVoiceIsolatedRuntimeAdapter,
    ISOLATED_SPEECH_OPERATIONS,
    IsolatedSpeechContractError,
    IsolatedSpeechRuntimeNotInstalledError,
    KOKORO_ENGINE_COMMIT,
    KOKORO_ENGINE_ID,
    KOKORO_MANIFEST_SCHEMA_VERSION,
    KOKORO_MODEL_BUNDLE_SHA256,
    KOKORO_MODEL_ID,
    KOKORO_REQUEST_SCHEMA_VERSION,
    KOKORO_RESPONSE_SCHEMA_VERSION,
    KOKORO_RUNTIME_KIND,
    KOKORO_SYNTHESIZE_FIXED_VOICE,
    KokoroIsolatedRuntimeAdapter,
    MATCHA_TTS_COMMIT,
    PROTOCOL_VERSION,
    TEST_FIXTURE_MARKERS,
    TEST_MANIFEST_SCHEMA_VERSION,
    TestOnlyIsolatedRuntimeEvidence,
    build_runtime_request,
    build_test_runtime_manifest,
    validate_runtime_manifest,
    validate_runtime_request,
    validate_runtime_response,
    validate_test_runtime_manifest,
    validate_test_runtime_response,
)
from services.v5_core_os.episode_production.audio_authority import (
    RightsBinding,
    validate_rights_binding,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
)
from services.v5_core_os.episode_production.isolated_speech import (
    build_cosyvoice_dialogue_runtime_request,
    build_cosyvoice_profile_runtime_request,
    build_kokoro_fixed_voice_runtime_request,
)
from services.v5_core_os.episode_production.voice_profile import (
    ConsentGrantVersionV2,
    CurrentConfirmedVoiceProfileAuthority,
    SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION,
    SourceVoiceRecordingAssetVersionBinding,
)
from tests.contract.test_m12_voice_profile_lineage_contract import (
    EVALUATED_AT as C1_EVALUATED_AT,
    PROJECT as C1_PROJECT,
    RUN as C1_RUN,
    SERIES as C1_SERIES,
    WORKSPACE as C1_WORKSPACE,
    clone_audio_authority_lineage,
    clone_lock_bundle,
    fixed_voice_lock_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_MODULE = ROOT / "services" / "v4_platform" / "isolated_speech_runtime.py"
BRIDGE_MODULE = (
    ROOT / "services" / "v5_core_os" / "episode_production" / "isolated_speech.py"
)
NEW_PRODUCTION_MODULES = (RUNTIME_MODULE, BRIDGE_MODULE)
SERVICES_ROOT = ROOT / "services"
PUBLIC_SERVER = ROOT / "apps" / "creator_workspace_mvp" / "server.py"

DIGESTS = tuple(character * 64 for character in "0123456789abcdef")
CREATED_AT = "2026-08-30T12:00:00Z"


def canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: dict) -> str:
    return sha256(canonical(value)).hexdigest()


def seal(value: dict) -> dict:
    selected = deepcopy(value)
    selected.pop("payloadDigest", None)
    selected["payloadDigest"] = digest(selected)
    return selected


def test_manifest(runtime_kind: str) -> dict:
    """Build only the explicitly non-production manifest allowed by M12-C2."""

    return build_test_runtime_manifest(
        runtime_kind=runtime_kind,
        executable_digest=DIGESTS[1],
        fixture_ref=f"test-runtime-manifest-{runtime_kind.lower()}",
    )


def production_lineage() -> dict:
    return {
        "workspaceRef": "workspace-m12-c2",
        "projectRef": "project-m12-c2",
        "seriesRef": "series-m12-c2",
        "episodeRef": "episode-m12-c2",
        "productionRunRef": "production-run-m12-c2",
        "assetRequirementRef": "asset-requirement-dialogue-m12-c2",
        "assetRequirementDigest": DIGESTS[5],
        "generationRequestRef": "generation-request-dialogue-m12-c2",
        "generationRequestVersionRef": "generation-request-dialogue-m12-c2-v1",
        "generationRequestDigest": DIGESTS[6],
        "creativeShotRef": "creative-shot-m12-c2",
        "creativeShotVersionRef": "creative-shot-version-m12-c2-v1",
        "creativeShotDigest": DIGESTS[7],
        "scriptRef": "script-m12-c2",
        "scriptVersionRef": "script-version-m12-c2-v1",
        "scriptVersionDigest": DIGESTS[8],
    }


def fixed_lineage() -> dict:
    return {
        **production_lineage(),
        "voiceLockRef": "voice-lock-fixed-m12-c2",
        "voiceLockVersionRef": "voice-lock-version-fixed-m12-c2-v1",
        "voiceLockVersionDigest": DIGESTS[9],
        "voiceLockConfirmationRef": "voice-lock-confirmation-fixed-m12-c2-v1",
        "voiceLockConfirmationDigest": DIGESTS[10],
    }


def profile_lineage(text: str = "用于声音画像的精确原文。") -> dict:
    return {
        "workspaceRef": "workspace-m12-c2",
        "projectRef": "project-m12-c2",
        "seriesRef": "series-m12-c2",
        "productionRunRef": "production-run-m12-c2",
        "sourceRecordingBindingRef": "source-recording-binding-m12-c2",
        "sourceRecordingBindingDigest": DIGESTS[1],
        "canonicalAssetVersionRef": "asset-version-source-voice-m12-c2-v1",
        "canonicalAssetVersionDigest": DIGESTS[2],
        "audioFileDigest": DIGESTS[3],
        "audioPcmContentDigest": DIGESTS[4],
        "transcriptVersionRef": "source-transcript-version-m12-c2-v1",
        "transcriptVersionDigest": DIGESTS[5],
        "transcriptTextDigest": sha256(text.encode("utf-8")).hexdigest(),
        "consentGrantVersionRef": "consent-grant-version-m12-c2-v2",
        "consentGrantVersionDigest": DIGESTS[6],
        "voiceLockRef": "voice-lock-clone-m12-c2",
        "voiceLockVersionRef": "voice-lock-version-clone-m12-c2-v2",
        "voiceLockVersionDigest": DIGESTS[7],
        "voiceLockConfirmationRef": "voice-lock-confirmation-clone-m12-c2-v2",
        "voiceLockConfirmationDigest": DIGESTS[8],
        "rightsBindingRef": "rights-binding-m12-c2",
        "rightsBindingDigest": DIGESTS[9],
        "voiceIdentityRef": "voice-identity-m12-c2",
        "voiceIdentityVersionRef": "voice-identity-version-m12-c2-v1",
        "voiceIdentityDigest": DIGESTS[10],
    }


def cloned_dialogue_lineage() -> dict:
    return {
        **production_lineage(),
        "voiceProfileRef": "voice-profile-m12-c2",
        "voiceProfileVersionRef": "voice-profile-version-m12-c2-v1",
        "voiceProfileVersionDigest": DIGESTS[9],
        "voiceProfilePackageFileDigest": DIGESTS[10],
        "voiceProfilePackageContentDigest": DIGESTS[11],
        "voiceLockVersionRef": "voice-lock-version-clone-m12-c2-v2",
        "voiceLockVersionDigest": DIGESTS[12],
        "sourceRecordingBindingRef": "source-recording-binding-m12-c2",
        "sourceRecordingBindingDigest": DIGESTS[13],
        "consentGrantVersionRef": "consent-grant-version-m12-c2-v2",
        "consentGrantVersionDigest": DIGESTS[14],
        "rightsBindingRef": "rights-binding-m12-c2",
        "rightsBindingDigest": DIGESTS[15],
        "voiceAssetVersionRef": "voice-asset-version-m12-c2-v1",
        "voiceAssetVersionDigest": DIGESTS[0],
    }


def runtime_request(operation: str) -> dict:
    runtime_kind = (
        KOKORO_RUNTIME_KIND
        if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
        else COSYVOICE_RUNTIME_KIND
    )
    manifest = test_manifest(runtime_kind)
    text = (
        "用于声音画像的精确原文。"
        if operation == COSYVOICE_BUILD_VOICE_PROFILE
        else "请按确认的声音身份朗读。"
    )
    lineage = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: fixed_lineage,
        COSYVOICE_BUILD_VOICE_PROFILE: lambda: profile_lineage(text),
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: cloned_dialogue_lineage,
    }[operation]()
    return build_runtime_request(
        operation_kind=operation,
        request_ref=f"runtime-request-{operation.lower()}",
        input_lineage_refs_and_digests=lineage,
        text=text,
        language="zh-CN",
        voice_id=(
            "fixed-voice-m12-c2"
            if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
            else None
        ),
        voice_profile_version_ref=(
            lineage["voiceProfileVersionRef"]
            if operation == COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE
            else None
        ),
        effective_speech_parameters=(
            {}
            if operation == COSYVOICE_BUILD_VOICE_PROFILE
            else {
                "rateScale": 1.0,
                "pitchSemitones": 0.0,
                "emotionTag": "neutral",
            }
        ),
        sample_rate=48_000,
        channel_count=1,
        runtime_manifest_ref=manifest["runtimeManifestRef"],
        runtime_manifest_digest=manifest["payloadDigest"],
        output_artifact_binding_ref=f"output-binding-{operation.lower()}",
    )


def runtime_response(request: dict, manifest: dict) -> dict:
    operation = request["operationKind"]
    schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION,
    }[operation]
    device_facts = {
        "deviceType": "CPU",
        "deviceCount": 1,
        "gpuUsed": False,
    }
    device_facts["deviceFactsDigest"] = digest(device_facts)
    is_kokoro = operation == KOKORO_SYNTHESIZE_FIXED_VOICE
    response = {
        "schemaVersion": schema,
        "requestRef": request["requestRef"],
        "requestDigest": request["payloadDigest"],
        "operationKind": operation,
        "engineCommit": KOKORO_ENGINE_COMMIT if is_kokoro else COSYVOICE_ENGINE_COMMIT,
        "matchaTtsCommit": None if is_kokoro else MATCHA_TTS_COMMIT,
        "modelBundleDigest": (
            KOKORO_MODEL_BUNDLE_SHA256
            if is_kokoro
            else COSYVOICE_MODEL_BUNDLE_SHA256
        ),
        "dependencyLockDigest": manifest["dependencyLockDigest"],
        "runtimeManifestDigest": manifest["payloadDigest"],
        "outputByteSize": 9_644,
        "outputFileDigest": DIGESTS[12],
        "outputPcmContentDigest": (
            request["inputLineageRefsAndDigests"]["audioPcmContentDigest"]
            if operation == COSYVOICE_BUILD_VOICE_PROFILE
            else DIGESTS[13]
        ),
        "mediaProbe": {
            "codec": "pcm_s16le",
            "sampleRate": 48_000,
            "channelCount": 1,
            "sampleCount": 4_800,
            "durationRational": {"numerator": 1, "denominator": 10},
        },
        "deviceFacts": device_facts,
        "networkUsed": False,
        "executionStartedAt": CREATED_AT,
        "executionCompletedAt": "2026-08-30T12:00:01Z",
    }
    if operation == COSYVOICE_BUILD_VOICE_PROFILE:
        response.update(
            {
                "profilePackageByteSize": response["outputByteSize"],
                "profilePackageFileDigest": response["outputFileDigest"],
                "profilePackageContentDigest": response["outputFileDigest"],
                "profilePackageSchemaVersion": "voice-profile-package.v1",
            }
        )
    return seal(response)


def mutate_and_reseal(value: dict, field: str, replacement: object) -> dict:
    selected = deepcopy(value)
    selected[field] = replacement
    return seal(selected)


def c1_speech_command(runtime_kind: str) -> dict:
    manifest = test_manifest(runtime_kind)
    return {
        "workspaceRef": C1_WORKSPACE,
        "projectRef": C1_PROJECT,
        "seriesRef": C1_SERIES,
        "episodeRef": "episode-m12-c2",
        "productionRunRef": C1_RUN,
        "assetRequirementRef": "asset-requirement-dialogue-m12-c2",
        "assetRequirementDigest": DIGESTS[5],
        "generationRequestRef": "generation-request-dialogue-m12-c2",
        "generationRequestVersionRef": "generation-request-dialogue-m12-c2-v1",
        "generationRequestDigest": DIGESTS[6],
        "creativeShotRef": "creative-shot-m12-c2",
        "creativeShotVersionRef": "creative-shot-version-m12-c2-v1",
        "creativeShotDigest": DIGESTS[7],
        "scriptRef": "script-m12-c2",
        "scriptVersionRef": "script-version-m12-c2-v1",
        "scriptVersionDigest": DIGESTS[8],
        "requestRef": f"v5-runtime-request-{runtime_kind.lower()}",
        "runtimeManifestRef": manifest["runtimeManifestRef"],
        "runtimeManifestDigest": manifest["payloadDigest"],
        "outputArtifactBindingRef": f"v5-output-{runtime_kind.lower()}",
        "text": "请按确认的声音身份朗读。",
        "language": "zh-CN",
        "effectiveSpeechParameters": {
            "rateScale": 1.0,
            "pitchSemitones": 0.0,
            "emotionTag": "neutral",
        },
        "sampleRate": 48_000,
        "channelCount": 1,
    }


def c1_profile_components(
    *,
    text: str = "用于声音画像的精确原文。",
    revocation_state: str = "ACTIVE",
    expires_at: str = "2027-08-30T08:00:00Z",
) -> tuple[
    SourceVoiceRecordingAssetVersionBinding,
    ConsentGrantVersionV2,
    dict,
    dict,
    RightsBinding,
]:
    lineage = clone_audio_authority_lineage()
    rights_mapping = lineage["rights"]
    rights = validate_rights_binding(rights_mapping)
    source = lineage["source"].as_dict()
    transcript = seal(
        {
            "schemaVersion": SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION,
            "workspaceRef": C1_WORKSPACE,
            "projectRef": C1_PROJECT,
            "seriesRef": C1_SERIES,
            "productionRunRef": C1_RUN,
            "transcriptVersionRef": source["transcriptVersionRef"],
            "sourceAssetVersionRef": source["canonicalAssetVersionRef"],
            "sourceAssetVersionDigest": source["canonicalAssetVersionDigest"],
            "transcriptLanguage": "zh-CN",
            "transcriptTextDigest": sha256(text.encode("utf-8")).hexdigest(),
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    source.update(
        {
            "transcriptVersionDigest": transcript["payloadDigest"],
            "transcriptTextDigest": transcript["transcriptTextDigest"],
        }
    )
    source = seal(source)
    source_wrapper = SourceVoiceRecordingAssetVersionBinding.from_mapping(source)

    consent = lineage["consent"].as_dict()
    consent.update(
        {
            "sourceRecordingBindingRef": source["sourceRecordingBindingRef"],
            "sourceRecordingBindingDigest": source["payloadDigest"],
            "revocationState": revocation_state,
            "expiresAt": expires_at,
        }
    )
    consent = seal(consent)
    consent_wrapper = ConsentGrantVersionV2.from_mapping(consent)
    confirmed_lock = clone_lock_bundle(binding=source, consent=consent)
    return source_wrapper, consent_wrapper, confirmed_lock, transcript, rights


def c1_profile_command(text: str = "用于声音画像的精确原文。") -> dict:
    manifest = test_manifest(COSYVOICE_RUNTIME_KIND)
    return {
        "requestRef": "v5-runtime-request-cosyvoice-profile",
        "runtimeManifestRef": manifest["runtimeManifestRef"],
        "runtimeManifestDigest": manifest["payloadDigest"],
        "outputArtifactBindingRef": "v5-output-cosyvoice-profile",
        "productionRunRef": C1_RUN,
        "evaluatedAt": C1_EVALUATED_AT,
        "transcriptText": text,
        "sampleRate": 48_000,
        "channelCount": 1,
    }


class M12IsolatedSpeechC1BridgeContractTests(unittest.TestCase):
    def test_kokoro_builder_consumes_only_confirmed_fixed_v1_voice_lock(self):
        command = c1_speech_command(KOKORO_RUNTIME_KIND)
        fixed = fixed_voice_lock_bundle()
        request = build_kokoro_fixed_voice_runtime_request(
            command, confirmed_voice_lock=fixed
        )
        self.assertEqual(request["operationKind"], KOKORO_SYNTHESIZE_FIXED_VOICE)
        self.assertEqual(
            request["inputLineageRefsAndDigests"]["voiceLockVersionRef"],
            fixed["voiceLockVersion"]["voiceLockVersionRef"],
        )
        self.assertEqual(request["voiceId"], fixed["voiceLockVersion"]["voiceId"])
        self.assertIsNone(request["voiceProfileVersionRef"])

        source, consent, clone_lock, _, _ = c1_profile_components()
        del source, consent
        with self.assertRaises(EpisodeProductionError):
            build_kokoro_fixed_voice_runtime_request(
                command, confirmed_voice_lock=clone_lock
            )

        for forbidden_field, value in (
            ("sourceRecordingBindingRef", "caller-reference-audio"),
            ("voiceProfileVersionRef", "caller-profile-version"),
            ("voiceClone", True),
        ):
            invalid = {**command, forbidden_field: value}
            with self.subTest(field=forbidden_field), self.assertRaises(
                EpisodeProductionError
            ):
                build_kokoro_fixed_voice_runtime_request(
                    invalid, confirmed_voice_lock=fixed
                )

    def test_profile_builder_requires_complete_active_clone_c1_authority(self):
        text = "用于声音画像的精确原文。"
        source, consent, clone_lock, transcript, rights = c1_profile_components(
            text=text
        )
        command = c1_profile_command(text)
        request = build_cosyvoice_profile_runtime_request(
            command,
            source_recording_binding=source,
            consent_grant_version=consent,
            confirmed_voice_lock=clone_lock,
            transcript_version=transcript,
            rights_binding=rights,
        )
        lineage = request["inputLineageRefsAndDigests"]
        self.assertEqual(request["operationKind"], COSYVOICE_BUILD_VOICE_PROFILE)
        self.assertEqual(
            lineage["sourceRecordingBindingDigest"], source.as_dict()["payloadDigest"]
        )
        self.assertEqual(
            lineage["consentGrantVersionDigest"], consent.as_dict()["payloadDigest"]
        )
        self.assertEqual(
            lineage["voiceLockVersionDigest"],
            clone_lock["voiceLockVersion"]["payloadDigest"],
        )
        self.assertEqual(lineage["transcriptVersionDigest"], transcript["payloadDigest"])
        self.assertEqual(lineage["rightsBindingDigest"], rights.as_dict()["payloadDigest"])

        fixed = fixed_voice_lock_bundle()
        with self.assertRaises(EpisodeProductionError):
            build_cosyvoice_profile_runtime_request(
                command,
                source_recording_binding=source,
                consent_grant_version=consent,
                confirmed_voice_lock=fixed,
                transcript_version=transcript,
                rights_binding=rights,
            )

        unconfirmed = clone_lock_bundle(
            confirmed=False,
            binding=source.as_dict(),
            consent=consent.as_dict(),
        )
        with self.assertRaises(EpisodeProductionError):
            build_cosyvoice_profile_runtime_request(
                command,
                source_recording_binding=source,
                consent_grant_version=consent,
                confirmed_voice_lock=unconfirmed,
                transcript_version=transcript,
                rights_binding=rights,
            )

        required_wrappers = {
            "source_recording_binding": source,
            "consent_grant_version": consent,
            "rights_binding": rights,
        }
        for missing in required_wrappers:
            arguments = {
                **required_wrappers,
                "confirmed_voice_lock": clone_lock,
                "transcript_version": transcript,
            }
            arguments[missing] = None
            with self.subTest(missing=missing), self.assertRaises(
                EpisodeProductionError
            ):
                build_cosyvoice_profile_runtime_request(command, **arguments)

        with self.assertRaises(EpisodeProductionError):
            build_cosyvoice_profile_runtime_request(
                command,
                source_recording_binding=source,
                consent_grant_version=consent,
                confirmed_voice_lock=None,
                transcript_version=transcript,
                rights_binding=rights,
            )

        with self.assertRaises(EpisodeProductionError):
            build_cosyvoice_profile_runtime_request(
                command,
                source_recording_binding=source,
                consent_grant_version=consent,
                confirmed_voice_lock=clone_lock,
                transcript_version=None,
                rights_binding=rights,
            )

    def test_profile_builder_rejects_revoked_expired_and_transcript_drift(self):
        command = c1_profile_command()
        for case, changes in (
            ("revoked", {"revocation_state": "REVOKED"}),
            ("expired", {"expires_at": "2026-08-30T08:15:00Z"}),
        ):
            source, consent, clone_lock, transcript, rights = c1_profile_components(
                **changes
            )
            with self.subTest(case=case), self.assertRaises(EpisodeProductionError):
                build_cosyvoice_profile_runtime_request(
                    command,
                    source_recording_binding=source,
                    consent_grant_version=consent,
                    confirmed_voice_lock=clone_lock,
                    transcript_version=transcript,
                    rights_binding=rights,
                )

        source, consent, clone_lock, transcript, rights = c1_profile_components()
        with self.assertRaises(EpisodeProductionError):
            build_cosyvoice_profile_runtime_request(
                c1_profile_command("篡改后的源录音文本。"),
                source_recording_binding=source,
                consent_grant_version=consent,
                confirmed_voice_lock=clone_lock,
                transcript_version=transcript,
                rights_binding=rights,
            )

    def test_clone_dialogue_rejects_missing_mapping_or_revoked_profile_authority(self):
        command = c1_speech_command(COSYVOICE_RUNTIME_KIND)
        self.assertFalse(
            hasattr(CurrentConfirmedVoiceProfileAuthority, "from_mapping")
        )
        self.assertTrue(
            callable(CurrentConfirmedVoiceProfileAuthority.assert_current)
        )
        revoked_profile = clone_audio_authority_lineage(
            profile_status="REVOKED"
        )["profile"]
        for authority in (None, {}, revoked_profile):
            with self.subTest(authority_type=type(authority).__name__), self.assertRaises(
                EpisodeProductionError
            ):
                build_cosyvoice_dialogue_runtime_request(
                    command,
                    current_voice_profile_authority=authority,
                    voice_asset_version=None,
                )


class M12IsolatedSpeechClosedContractTests(unittest.TestCase):
    def test_only_three_operations_and_their_exact_schemas_are_accepted(self):
        self.assertEqual(
            ISOLATED_SPEECH_OPERATIONS,
            {
                KOKORO_SYNTHESIZE_FIXED_VOICE,
                COSYVOICE_BUILD_VOICE_PROFILE,
                COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
            },
        )
        expected_schemas = {
            KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_REQUEST_SCHEMA_VERSION,
            COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION,
            COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION,
        }
        for operation, expected_schema in expected_schemas.items():
            with self.subTest(operation=operation):
                request = runtime_request(operation)
                self.assertEqual(validate_runtime_request(request), request)
                self.assertEqual(request["schemaVersion"], expected_schema)

        invalid = deepcopy(runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE))
        invalid["operationKind"] = "UNSEALED_OR_UNKNOWN_OPERATION"
        invalid = seal(invalid)
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(invalid)

    def test_operation_lineage_is_closed_and_cannot_cross_voice_kinds(self):
        fixed = runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE)
        profile = runtime_request(COSYVOICE_BUILD_VOICE_PROFILE)
        dialogue = runtime_request(COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE)

        fixed_with_reference = deepcopy(fixed)
        fixed_with_reference["inputLineageRefsAndDigests"].update(
            {
                "sourceRecordingBindingRef": "forbidden-source-binding",
                "sourceRecordingBindingDigest": DIGESTS[0],
            }
        )
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(seal(fixed_with_reference))

        fixed_with_profile = mutate_and_reseal(
            fixed, "voiceProfileVersionRef", "forbidden-profile-version"
        )
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(fixed_with_profile)

        clone_lock_in_kokoro = deepcopy(fixed)
        clone_lock_in_kokoro["inputLineageRefsAndDigests"] = {
            **clone_lock_in_kokoro["inputLineageRefsAndDigests"],
            "sourceRecordingBindingRef": "clone-source-binding",
        }
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(seal(clone_lock_in_kokoro))

        fixed_lock_in_profile = deepcopy(profile)
        fixed_lock_in_profile["inputLineageRefsAndDigests"] = fixed_lineage()
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(seal(fixed_lock_in_profile))

        dialogue_with_raw_reference = deepcopy(dialogue)
        dialogue_with_raw_reference["inputLineageRefsAndDigests"][
            "audioFileDigest"
        ] = DIGESTS[3]
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(seal(dialogue_with_raw_reference))

    def test_profile_requires_every_c1_lineage_edge_and_exact_transcript_bytes(self):
        request = runtime_request(COSYVOICE_BUILD_VOICE_PROFILE)
        required_edges = (
            "sourceRecordingBindingRef",
            "consentGrantVersionRef",
            "voiceLockVersionRef",
            "voiceLockConfirmationRef",
            "transcriptVersionRef",
            "rightsBindingRef",
            "voiceIdentityVersionRef",
        )
        for field in required_edges:
            invalid = deepcopy(request)
            invalid["inputLineageRefsAndDigests"].pop(field)
            with self.subTest(missing=field), self.assertRaises(
                IsolatedSpeechContractError
            ):
                validate_runtime_request(seal(invalid))

        stale_text = mutate_and_reseal(request, "text", "篡改后的源录音文本。")
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(stale_text)

    def test_clone_dialogue_requires_exact_profile_lineage_and_matching_top_level_ref(self):
        request = runtime_request(COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE)
        for field in (
            "voiceProfileVersionRef",
            "voiceProfileVersionDigest",
            "voiceProfilePackageFileDigest",
            "voiceProfilePackageContentDigest",
            "consentGrantVersionRef",
            "voiceLockVersionRef",
            "sourceRecordingBindingRef",
            "rightsBindingRef",
        ):
            invalid = deepcopy(request)
            invalid["inputLineageRefsAndDigests"].pop(field)
            with self.subTest(missing=field), self.assertRaises(
                IsolatedSpeechContractError
            ):
                validate_runtime_request(seal(invalid))

        stale_profile = mutate_and_reseal(
            request,
            "voiceProfileVersionRef",
            "different-confirmed-profile-version",
        )
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(stale_profile)

    def test_request_digest_and_all_caller_overrides_fail_closed(self):
        request = runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE)
        stale = deepcopy(request)
        stale["payloadDigest"] = DIGESTS[0]
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_request(stale)

        forbidden = (
            "absolutePath",
            "storageKey",
            "modelPath",
            "pythonPath",
            "shellCommand",
            "environmentOverride",
            "downloadUrl",
            "networkEndpoint",
            "engineOverride",
            "modelOverride",
            "rawAudioBytes",
            "rawAssetVersion",
            "rawConsent",
            "rawVoiceProfile",
            "inputFd",
            "outputFd",
        )
        for field in forbidden:
            invalid = deepcopy(request)
            invalid[field] = "caller-controlled"
            with self.subTest(field=field), self.assertRaises(
                IsolatedSpeechContractError
            ):
                validate_runtime_request(seal(invalid))

        for adapter_type in (
            KokoroIsolatedRuntimeAdapter,
            CosyVoiceIsolatedRuntimeAdapter,
        ):
            for configuration in (
                {"executable": "/tmp/caller-runtime"},
                {"runtime_root": "/tmp/caller-root"},
                {"model_override": "caller-model"},
                {"network_endpoint": "https://example.invalid"},
            ):
                with self.subTest(
                    adapter=adapter_type.__name__, configuration=configuration
                ), self.assertRaises(IsolatedSpeechContractError):
                    adapter_type(**configuration)


class M12IsolatedSpeechManifestAndResponseTests(unittest.TestCase):
    def test_production_contract_freezes_both_engines_without_fake_manifest(self):
        # M12-C2 has no real lock or wheelhouse, so this suite deliberately does
        # not fabricate a production manifest merely to make validation pass.
        self.assertEqual(KOKORO_ENGINE_ID, "hexgrad/kokoro:LOCAL_FIXED_VOICE")
        self.assertEqual(
            KOKORO_ENGINE_COMMIT,
            "dfb907a02bba8152ca444717ca5d78747ccb4bec",
        )
        self.assertEqual(
            KOKORO_MODEL_BUNDLE_SHA256,
            "849ed6061f60a9b82ba13ff9538380fca4014fe19f1762475ab0997a2590cc92",
        )
        self.assertEqual(
            COSYVOICE_ENGINE_ID,
            "QwenAudio/CosyVoice:CosyVoice3.ZERO_SHOT_LOCAL",
        )
        self.assertEqual(
            COSYVOICE_ENGINE_COMMIT,
            "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc",
        )
        self.assertEqual(
            MATCHA_TTS_COMMIT,
            "dd9105b34bf2be2230f4aa1e4769fb586a3c824e",
        )
        self.assertEqual(
            COSYVOICE_MODEL_BUNDLE_SHA256,
            "f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d",
        )
        self.assertEqual(KOKORO_MANIFEST_SCHEMA_VERSION, "m12.kokoro-isolated-runtime-manifest.v1")
        self.assertEqual(COSYVOICE_MANIFEST_SCHEMA_VERSION, "m12.cosyvoice-isolated-runtime-manifest.v1")

    def test_production_and_test_manifest_types_can_never_cross(self):
        fake = build_test_runtime_manifest(
            runtime_kind=KOKORO_RUNTIME_KIND,
            executable_digest=DIGESTS[1],
            fixture_ref="test-runtime-manifest-kokoro",
        )
        self.assertEqual(validate_test_runtime_manifest(fake), fake)
        self.assertEqual(fake["schemaVersion"], TEST_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(fake["fixtureMarkers"], sorted(TEST_FIXTURE_MARKERS))
        self.assertFalse(fake["publicationAllowed"])
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_manifest(fake, runtime_kind=KOKORO_RUNTIME_KIND)
        request = runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE)
        with self.assertRaises(IsolatedSpeechContractError):
            validate_runtime_response(
                runtime_response(request, fake), request=request, manifest=fake
            )

        with self.assertRaises(IsolatedSpeechContractError):
            KokoroIsolatedRuntimeAdapter(manifest=fake)

    def test_test_manifest_marker_or_digest_drift_is_rejected(self):
        manifest = test_manifest(COSYVOICE_RUNTIME_KIND)
        drifts = {
            "schemaVersion": "m12.cosyvoice-isolated-runtime-manifest.v1",
            "dependencyLockDigest": DIGESTS[2],
            "fixtureMarkers": ["TEST_FIXTURE_ONLY"],
            "protocolVersion": "caller-protocol",
            "publicationAllowed": True,
        }
        for field, replacement in drifts.items():
            invalid = mutate_and_reseal(manifest, field, replacement)
            with self.subTest(field=field), self.assertRaises(
                IsolatedSpeechContractError
            ):
                validate_test_runtime_manifest(invalid)

        stale_payload = deepcopy(manifest)
        stale_payload["payloadDigest"] = DIGESTS[0]
        with self.assertRaises(IsolatedSpeechContractError):
            validate_test_runtime_manifest(stale_payload)

    def test_production_adapters_report_runtime_not_installed_without_fallback(self):
        cases = (
            (
                KokoroIsolatedRuntimeAdapter(),
                runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE),
            ),
            (
                CosyVoiceIsolatedRuntimeAdapter(),
                runtime_request(COSYVOICE_BUILD_VOICE_PROFILE),
            ),
            (
                CosyVoiceIsolatedRuntimeAdapter(),
                runtime_request(COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE),
            ),
        )
        for adapter, request in cases:
            with self.subTest(operation=request["operationKind"]), self.assertRaises(
                IsolatedSpeechRuntimeNotInstalledError
            ) as error:
                adapter.execute(request)
            self.assertEqual(error.exception.code, "M12_RUNTIME_NOT_INSTALLED")

        for adapter, wrong_request in (
            (
                KokoroIsolatedRuntimeAdapter(),
                runtime_request(COSYVOICE_BUILD_VOICE_PROFILE),
            ),
            (
                CosyVoiceIsolatedRuntimeAdapter(),
                runtime_request(KOKORO_SYNTHESIZE_FIXED_VOICE),
            ),
        ):
            with self.subTest(
                adapter=type(adapter).__name__, cross_runtime=True
            ), self.assertRaises(IsolatedSpeechContractError):
                adapter.execute(wrong_request)

    def test_response_request_manifest_and_all_pins_are_exactly_bound(self):
        for operation in ISOLATED_SPEECH_OPERATIONS:
            runtime_kind = (
                KOKORO_RUNTIME_KIND
                if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
                else COSYVOICE_RUNTIME_KIND
            )
            request = runtime_request(operation)
            manifest = test_manifest(runtime_kind)
            response = runtime_response(request, manifest)
            with self.subTest(operation=operation):
                self.assertEqual(
                    validate_test_runtime_response(
                        response, request=request, manifest=manifest
                    ),
                    response,
                )

            stale_request = mutate_and_reseal(
                request, "runtimeManifestDigest", DIGESTS[0]
            )
            with self.subTest(operation=operation, drift="request-manifest"):
                with self.assertRaises(IsolatedSpeechContractError):
                    validate_test_runtime_response(
                        response, request=stale_request, manifest=manifest
                    )

            stale_ref = mutate_and_reseal(
                request, "runtimeManifestRef", "different-test-manifest"
            )
            with self.subTest(operation=operation, drift="request-manifest-ref"):
                with self.assertRaises(IsolatedSpeechContractError):
                    validate_test_runtime_response(
                        response, request=stale_ref, manifest=manifest
                    )

            response_drifts = {
                "requestDigest": DIGESTS[0],
                "engineCommit": "f" * 40,
                "modelBundleDigest": DIGESTS[0],
                "dependencyLockDigest": DIGESTS[1],
                "runtimeManifestDigest": DIGESTS[2],
                "networkUsed": True,
            }
            if runtime_kind == COSYVOICE_RUNTIME_KIND:
                response_drifts["matchaTtsCommit"] = "e" * 40
            for field, replacement in response_drifts.items():
                invalid = mutate_and_reseal(response, field, replacement)
                with self.subTest(
                    operation=operation, drift=field
                ), self.assertRaises(IsolatedSpeechContractError):
                    validate_test_runtime_response(
                        invalid, request=request, manifest=manifest
                    )

            stale_digest = deepcopy(response)
            stale_digest["payloadDigest"] = DIGESTS[0]
            with self.subTest(operation=operation, drift="response-payload"):
                with self.assertRaises(IsolatedSpeechContractError):
                    validate_test_runtime_response(
                        stale_digest, request=request, manifest=manifest
                    )

    def test_response_cannot_leak_paths_source_bytes_transcript_or_credentials(self):
        request = runtime_request(COSYVOICE_BUILD_VOICE_PROFILE)
        manifest = test_manifest(COSYVOICE_RUNTIME_KIND)
        response = runtime_response(request, manifest)
        forbidden = {
            "absolutePath": "/server/private/source.wav",
            "sourceRecordingBytes": "base64-private-source",
            "sourceTranscript": request["text"],
            "token": "secret-token",
            "environmentVariables": {"SECRET": "value"},
            "commandLine": ["runtime", "--private-path"],
        }
        for field, replacement in forbidden.items():
            invalid = deepcopy(response)
            invalid[field] = replacement
            with self.subTest(field=field), self.assertRaises(
                IsolatedSpeechContractError
            ):
                validate_test_runtime_response(
                    seal(invalid), request=request, manifest=manifest
                )


class M12IsolatedSpeechArchitectureCensusTests(unittest.TestCase):
    def test_core_production_import_graph_contains_no_ml_packages(self):
        forbidden = {
            "torch",
            "torchaudio",
            "transformers",
            "onnxruntime",
            "kokoro",
            "cosyvoice",
            "matcha",
        }
        violations: list[str] = []
        for path in SERVICES_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported: str | None = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0].lower() in forbidden:
                            violations.append(
                                f"{path.relative_to(ROOT)}: import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported = (node.module or "").split(".", 1)[0].lower()
                elif (
                    isinstance(node, ast.Call)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "__import__"
                        or isinstance(node.func, ast.Attribute)
                        and node.func.attr == "import_module"
                    )
                ):
                    imported = node.args[0].value.split(".", 1)[0].lower()
                if imported in forbidden:
                    violations.append(
                        f"{path.relative_to(ROOT)}: dynamic/from import {imported}"
                    )
        self.assertEqual(violations, [])

    def test_new_runtime_has_zero_third_party_dependencies(self):
        allowed_roots = set(sys.stdlib_module_names) | {"__future__", "services"}
        for path in NEW_PRODUCTION_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_roots = {
                alias.name.split(".", 1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                (node.module or "").split(".", 1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level == 0
            }
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(
                    imported_roots <= allowed_roots,
                    imported_roots - allowed_roots,
                )
        dependency_manifests = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file()
            and (
                path.name in {
                    "pyproject.toml",
                    "poetry.lock",
                    "uv.lock",
                    "Pipfile",
                    "Pipfile.lock",
                    "setup.py",
                    "setup.cfg",
                }
                or path.name.startswith("requirements")
            )
            and ".git" not in path.parts
        }
        self.assertEqual(dependency_manifests, set())

    def test_no_creator_http_runtime_route_was_added(self):
        routes = {
            value
            for name, value in vars(public_contract).items()
            if name.endswith("_ENDPOINT") and isinstance(value, str)
        }
        forbidden_fragments = {
            "kokoro",
            "cosyvoice",
            "isolated-runtime",
            "voice-profile",
            "voice-clone",
        }
        self.assertFalse(
            any(fragment in route for fragment in forbidden_fragments for route in routes)
        )
        server_source = PUBLIC_SERVER.read_text(encoding="utf-8").lower()
        self.assertFalse(any(fragment in server_source for fragment in forbidden_fragments))

    def test_single_audio_voice_profile_and_voice_lock_authorities_remain(self):
        selected_names = {
            "K2AudioProductionService",
            "K2VoiceProfileLineageService",
            "CurrentConfirmedVoiceProfileAuthority",
            "K2VoiceLockService",
        }
        locations: dict[str, list[str]] = {name: [] for name in selected_names}
        for path in SERVICES_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name in selected_names:
                    locations[node.name].append(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            locations,
            {
                "K2AudioProductionService": [
                    "services/v5_core_os/episode_production/audio.py"
                ],
                "K2VoiceProfileLineageService": [
                    "services/v5_core_os/episode_production/voice_profile.py"
                ],
                "CurrentConfirmedVoiceProfileAuthority": [
                    "services/v5_core_os/episode_production/voice_profile.py"
                ],
                "K2VoiceLockService": [
                    "services/v5_core_os/episode_production/voice.py"
                ],
            },
        )
        for path in NEW_PRODUCTION_MODULES:
            runtime_classes = {
                node.name
                for node in ast.walk(
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                )
                if isinstance(node, ast.ClassDef)
            }
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(
                    any(
                        token in name
                        for name in runtime_classes
                        for token in (
                            "Repository",
                            "Registry",
                            "AudioProductionService",
                            "VoiceProfileAuthority",
                            "VoiceLockAuthority",
                        )
                    )
                )

    def test_fixture_evidence_cannot_mint_assets_and_legacy_media_writes_are_zero(self):
        with self.assertRaises(IsolatedSpeechContractError):
            TestOnlyIsolatedRuntimeEvidence._from_harness(
                {}, analysis=None, token=object()
            )
        self.assertNotIn("AssetVersion", TestOnlyIsolatedRuntimeEvidence.__name__)
        self.assertEqual(
            inspect.signature(
                runtime_contract.TestOnlyIsolatedRuntimeHarness.execute
            ).return_annotation,
            "TestOnlyIsolatedRuntimeEvidence",
        )
        self.assertFalse(
            any("AssetVersion" in name for name in runtime_contract.__all__)
        )
        runtime_tree = ast.parse(
            RUNTIME_MODULE.read_text(encoding="utf-8"), filename=str(RUNTIME_MODULE)
        )
        harness = next(
            node
            for node in runtime_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestOnlyIsolatedRuntimeHarness"
        )
        called_attributes = {
            node.func.attr
            for node in ast.walk(harness)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("_from_adapter", called_attributes)

        for path in NEW_PRODUCTION_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            absolute_imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level == 0
            }
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(
                    any(
                        name.startswith(
                            (
                                "services.v4_platform.media_jobs",
                                "services.v5_core_os.episode_production.media",
                            )
                        )
                        for name in absolute_imports
                    )
                )
                self.assertNotIn("LEGACY_MEDIA", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
