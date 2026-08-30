from __future__ import annotations

from copy import deepcopy
import unittest

from apps.creator_workspace_mvp import public_contract
from services.v4_platform.audio_validation import (
    AudioTechnicalAnalysisEvidence,
)
from services.v5_core_os.episode_production.audio_authority import (
    AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
    AudioGenerationRequest,
    DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION,
    DIALOGUE_ASSET_VERSION_SCHEMA_VERSION,
    VOICE_ASSET_VERSION_SCHEMA_VERSION,
    build_audio_generation_request,
    build_audio_provenance,
    build_clone_dialogue_asset_version,
    build_clone_voice_asset_version,
    build_dialogue_asset_version,
    build_requested_audio_provenance,
    build_rights_binding,
    build_voice_asset_version,
    validate_audio_generation_request,
    validate_clone_dialogue_asset_version,
    validate_dialogue_asset_version,
    validate_voice_asset_version,
)
from services.v5_core_os.episode_production.audio import (
    normalize_clone_speech_parameters,
    normalize_speech_parameters,
)
from services.v5_core_os.episode_production.audio_validation import (
    AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION,
    AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION,
    build_audio_technical_validation,
    build_pre_asset_audio_technical_validation,
    validate_audio_technical_validation,
    validate_pre_asset_audio_technical_validation,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    _digest,
)
from services.v5_core_os.episode_production.voice import (
    VOICE_LOCK_SCHEMA_VERSION,
    VOICE_LOCK_VERSION_SCHEMA_VERSION,
    VOICE_LOCK_VERSION_V2_SCHEMA_VERSION,
    VoiceLockNotConfirmedError,
    build_clone_voice_lock,
    build_clone_voice_lock_confirmation,
    validate_clone_voice_lock,
    validate_clone_voice_lock_version_v2,
    validate_confirmed_clone_voice_lock_bundle,
    validate_voice_lock_confirmation,
)
from services.v5_core_os.episode_production.voice_profile import (
    CONSENT_GRANT_ROOT_SCHEMA_VERSION,
    CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION,
    ConsentGrantVersionV2,
    SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION,
    SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION,
    SourceVoiceRecordingAssetVersion,
    SourceVoiceRecordingAssetVersionBinding,
    VOICE_PROFILE_SCHEMA_VERSION,
    VOICE_PROFILE_TEST_FIXTURE_MARKERS,
    VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION,
    VOICE_PROFILE_VERSION_SCHEMA_VERSION,
    VoiceProfileFixtureRejectedError,
    VoiceProfileLineageError,
    VoiceProfileLineageNotEffectiveError,
    VoiceProfileLineageStaleError,
    VoiceProfileVersion,
    build_voice_profile_test_fixture,
    require_active_consent_grant_version,
    validate_consent_grant_root,
    validate_consent_grant_version_v2,
    validate_source_voice_recording_asset_version,
    validate_source_voice_recording_binding,
    validate_voice_profile,
    validate_voice_profile_test_fixture,
    validate_voice_profile_lineage_graph,
    validate_voice_profile_version,
)
from tests.contract.test_m12_audio_contract import voice_bundle
from tests.contract.test_m12_audio_authority_contract import (
    clone_rights,
    cloned_voice_request_command,
    common_asset_command,
    consent_grant,
    dialogue_asset,
    local_voice_asset,
    speech_parameters,
    voice_asset_command,
)
from tests.contract.test_m12_audio_technical_validation_contract import (
    analysis_evidence,
    seal_analysis,
    technical_source,
    validation_command as v1_validation_command,
)


WORKSPACE = "workspace-m12-c1"
PROJECT = "project-m12-c1"
SERIES = "series-m12-c1"
RUN = "run-m12-c1"
SUBJECT = "character-lin"
CREATED_AT = "2026-08-30T08:00:00Z"
EVALUATED_AT = "2026-08-30T08:30:00Z"
ENGINE_ID = "QwenAudio/CosyVoice:CosyVoice3.ZERO_SHOT_LOCAL"
ENGINE_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
MODEL_ID = (
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
    "@29e01c4e8d000f4bcd70751be16fa94bf3d85a18"
)
MODEL_BUNDLE_DIGEST = (
    "f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d"
)


def sealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def source_recording_asset() -> dict:
    projection_body = {
        "schemaVersion": SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION,
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "subjectRef": SUBJECT,
        "canonicalAssetVersionRef": "audio-asset-version-source-1",
        "canonicalAssetVersionNumber": 1,
        "canonicalAssetVersionDigest": "1" * 64,
        "assetAdmissionRef": "asset-admission-source-1",
        "assetAdmissionVersion": 1,
        "assetAdmissionDigest": "8" * 64,
        "audioTechnicalValidationRef": "audio-validation-source-1",
        "audioTechnicalValidationDigest": "4" * 64,
        "mediaKind": "AUDIO",
        "immutable": True,
        "admissionState": "ADMITTED",
        "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
        "speechSynthesis": False,
        "voiceClone": False,
        "syntheticSpeech": False,
        "audioFileDigest": "2" * 64,
        "audioPcmContentDigest": "3" * 64,
        "artifactEvidenceRef": "audio-artifact-evidence-source-1",
        "artifactEvidenceDigest": "a" * 64,
        "artifactRef": "audio-artifact-source-1",
        "byteSize": 192_044,
        "mediaProbe": {
            "codec": "pcm_s16le",
            "sampleRate": 48_000,
            "channelCount": 1,
            "sampleCount": 96_000,
            "durationRational": {"numerator": 2, "denominator": 1},
        },
        "provenanceRef": "source-recording-provenance-1",
        "provenanceDigest": "b" * 64,
        "requirementRef": "source-recording-requirement-1",
        "requirementDigest": "c" * 64,
        "importEvidenceRef": "source-recording-import-evidence-1",
        "importEvidenceDigest": "d" * 64,
        "sourceKindEvidenceRef": "source-kind-evidence-1",
        "sourceKindEvidenceDigest": "9" * 64,
        "rightsBindingRef": "rights-binding-source-1",
        "rightsBindingDigest": "7" * 64,
        "classificationEvidenceKind": "AUTHORITY_EVIDENCE",
        "authorityState": "DERIVED_CANONICAL_ASSET_PROJECTION",
        "publicationAllowed": False,
        "createdAt": CREATED_AT,
        "createdBy": "v5.m12-c1.source-recording-projection.v1",
    }
    return sealed(
        {
            "sourceVoiceRecordingAssetVersionRef": (
                "source-voice-recording-asset-version-"
                + _digest(projection_body)
            ),
            **projection_body,
        }
    )


def source_binding() -> dict:
    source = source_recording_asset()
    return sealed(
        {
            "schemaVersion": SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "sourceRecordingBindingRef": "source-recording-binding-1",
            "subjectRef": SUBJECT,
            "sourceVoiceRecordingAssetVersionRef": source[
                "sourceVoiceRecordingAssetVersionRef"
            ],
            "sourceVoiceRecordingAssetVersionDigest": source[
                "payloadDigest"
            ],
            "canonicalAssetVersionRef": source["canonicalAssetVersionRef"],
            "canonicalAssetVersionNumber": source[
                "canonicalAssetVersionNumber"
            ],
            "canonicalAssetVersionDigest": source[
                "canonicalAssetVersionDigest"
            ],
            "audioFileDigest": "2" * 64,
            "audioPcmContentDigest": "3" * 64,
            "audioTechnicalValidationRef": "audio-validation-source-1",
            "audioTechnicalValidationDigest": "4" * 64,
            "mediaProbe": {
                "codec": "pcm_s16le",
                "sampleRate": 48_000,
                "channelCount": 1,
                "sampleCount": 96_000,
                "durationRational": {"numerator": 2, "denominator": 1},
            },
            "transcriptVersionRef": "transcript-version-source-1",
            "transcriptVersionDigest": "5" * 64,
            "transcriptLanguage": "zh-CN",
            "transcriptTextDigest": "6" * 64,
            "sourceRightsBindingRef": "rights-binding-source-1",
            "sourceRightsBindingDigest": "7" * 64,
            "createdAt": CREATED_AT,
            "createdBy": "v5.m12-c1.contract-test",
        }
    )


def consent_root() -> dict:
    return sealed(
        {
            "schemaVersion": CONSENT_GRANT_ROOT_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "consentGrantRef": "consent-grant-1",
            "subjectRef": SUBJECT,
            "createdAt": CREATED_AT,
        }
    )


def consent_version(
    *,
    version_number: int = 1,
    parent: dict | None = None,
    allowed_uses: list[str] | None = None,
    valid_from: str = "2026-08-30T08:00:00Z",
    expires_at: str = "2027-08-30T08:00:00Z",
    revocation_state: str = "ACTIVE",
    subject_ref: str = SUBJECT,
    rights_digest: str = "7" * 64,
) -> dict:
    binding = source_binding()
    return sealed(
        {
            "schemaVersion": CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "consentGrantRef": "consent-grant-1",
            "consentGrantVersionRef": f"consent-grant-version-{version_number}",
            "sourceRecordingBindingRef": binding[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": binding["payloadDigest"],
            "subjectRef": subject_ref,
            "grantorRef": "grantor-lin",
            "rightsBindingRef": binding["sourceRightsBindingRef"],
            "rightsBindingDigest": rights_digest,
            "allowedUses": sorted(
                [
                    "VOICE_CLONING",
                    "VOICE_PROFILE_USE",
                    "AUDIO_PRODUCTION",
                ]
                if allowed_uses is None
                else allowed_uses
            ),
            "prohibitedUses": [],
            "territories": ["WORLDWIDE"],
            "validFrom": valid_from,
            "expiresAt": expires_at,
            "revocationState": revocation_state,
            "evidenceRef": "consent-evidence-1",
            "evidenceDigest": "8" * 64,
            "versionNumber": version_number,
            "parentConsentGrantVersionRef": (
                None if parent is None else parent["consentGrantVersionRef"]
            ),
            "parentConsentGrantVersionDigest": (
                None if parent is None else parent["payloadDigest"]
            ),
            "createdAt": CREATED_AT,
            "createdBy": "v5.m12-c1.contract-test",
        }
    )


def fixed_voice_lock_bundle() -> dict:
    version = sealed(
        {
            "schemaVersion": VOICE_LOCK_VERSION_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": "voice-identity-lin",
            "voiceLockVersionRef": "voice-lock-version-fixed-1",
            "versionNumber": 1,
            "parentVoiceLockVersionRef": None,
            "parentVoiceLockDigest": None,
            "characterRef": SUBJECT,
            "engineFamily": "local-neural-tts-v1",
            "voiceId": "fixed-voice-lin",
            "gender": "female",
            "apparentAge": 28,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "stable-low-register",
            "languageCode": "zh-CN",
            "state": "CANDIDATE",
            "immutable": True,
            "createdAt": CREATED_AT,
        }
    )
    confirmation = sealed(
        {
            "schemaVersion": "v5.voice-lock-confirmation.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceLockConfirmationRef": "voice-lock-confirmation-fixed-1",
            "voiceRef": "voice-identity-lin",
            "voiceLockVersionRef": version["voiceLockVersionRef"],
            "voiceLockDigest": version["payloadDigest"],
            "characterRef": SUBJECT,
            "state": "CONFIRMED",
            "createdAt": CREATED_AT,
        }
    )
    root = sealed(
        {
            "schemaVersion": VOICE_LOCK_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": "voice-identity-lin",
            "characterRef": SUBJECT,
            "currentVoiceLockVersionRef": version["voiceLockVersionRef"],
            "confirmedVoiceLockVersionRef": version[
                "voiceLockVersionRef"
            ],
            "confirmedVoiceLockDigest": version["payloadDigest"],
            "revision": 2,
            "createdAt": CREATED_AT,
            "updatedAt": CREATED_AT,
        }
    )
    return {
        "voiceLock": root,
        "voiceLockVersion": version,
        "voiceLockConfirmation": confirmation,
    }


def clone_lock_bundle(
    *,
    confirmed: bool = True,
    binding: dict | None = None,
    consent: dict | None = None,
    version_ref: str = "voice-lock-version-clone-2",
    confirmation_ref: str = "voice-lock-confirmation-clone-2",
) -> dict:
    selected_binding = source_binding() if binding is None else binding
    selected_consent = consent_version() if consent is None else consent
    fixed = fixed_voice_lock_bundle()
    fixed_root = fixed["voiceLock"]
    fixed_version = fixed["voiceLockVersion"]
    candidate = build_clone_voice_lock(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": "voice-identity-lin",
            "voiceLockVersionRef": version_ref,
            "baseVoiceLockVersionRef": fixed_version[
                "voiceLockVersionRef"
            ],
            "baseVoiceLockDigest": fixed_version["payloadDigest"],
            "expectedRevision": fixed_root["revision"],
            "engineFamily": ENGINE_ID,
            "voiceId": MODEL_ID,
            "gender": "female",
            "apparentAge": 28,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "stable-low-register",
            "languageCode": "zh-CN",
            "sourceRecordingBindingRef": selected_binding[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": selected_binding[
                "payloadDigest"
            ],
            "consentGrantVersionRef": selected_consent[
                "consentGrantVersionRef"
            ],
            "consentGrantVersionDigest": selected_consent["payloadDigest"],
            "rightsBindingRef": selected_consent["rightsBindingRef"],
            "rightsBindingDigest": selected_consent["rightsBindingDigest"],
            "voiceIdentityRef": "voice-identity-lin",
            "voiceIdentityVersionRef": fixed_version[
                "voiceLockVersionRef"
            ],
            "voiceIdentityDigest": fixed_version["payloadDigest"],
            "subjectRef": SUBJECT,
            "createdAt": CREATED_AT,
        },
        voice_lock=fixed_root,
        parent_voice_lock_version=fixed_version,
    )
    if not confirmed:
        return candidate
    confirmed_root = sealed(
        {
            key: value
            for key, value in candidate["voiceLock"].items()
            if key != "payloadDigest"
        }
        | {
            "confirmedVoiceLockVersionRef": candidate["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
            "confirmedVoiceLockDigest": candidate["voiceLockVersion"][
                "payloadDigest"
            ],
            "revision": candidate["voiceLock"]["revision"] + 1,
            "updatedAt": "2026-08-30T08:05:00Z",
        }
    )
    return build_clone_voice_lock_confirmation(
        {
            "voiceLockConfirmationRef": confirmation_ref,
            "createdAt": "2026-08-30T08:05:00Z",
        },
        clone_voice_lock_bundle={
            "voiceLock": confirmed_root,
            "voiceLockVersion": candidate["voiceLockVersion"],
        },
    )


def profile_package() -> dict:
    return {
        "storageBindingRef": "voice-profile-storage-binding-1",
        "byteSize": 4096,
        "fileDigest": "a" * 64,
        "contentDigest": "b" * 64,
        "packageFormat": "VOICE_PROFILE_PACKAGE",
        "packageSchemaVersion": "voice-profile-package.v1",
        "technicalValidationRef": "voice-profile-technical-validation-1",
        "technicalValidationDigest": "c" * 64,
    }


def profile_root() -> dict:
    return sealed(
        {
            "schemaVersion": VOICE_PROFILE_SCHEMA_VERSION,
            "voiceProfileRef": "voice-profile-lin",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "subjectRef": SUBJECT,
            "createdAt": CREATED_AT,
        }
    )


def profile_version(
    *,
    version_number: int = 1,
    parent: dict | None = None,
    status: str = "CONFIRMED",
    package: dict | None = None,
) -> dict:
    binding = source_binding()
    consent = consent_version()
    lock = clone_lock_bundle()
    lock_version = lock["voiceLockVersion"]
    confirmation = lock["voiceLockConfirmation"]
    return sealed(
        {
            "schemaVersion": VOICE_PROFILE_VERSION_SCHEMA_VERSION,
            "voiceProfileRef": "voice-profile-lin",
            "voiceProfileVersionRef": f"voice-profile-version-{version_number}",
            "versionNumber": version_number,
            "parentVoiceProfileVersionRef": (
                None if parent is None else parent["voiceProfileVersionRef"]
            ),
            "parentVoiceProfileVersionDigest": (
                None if parent is None else parent["payloadDigest"]
            ),
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "subjectRef": SUBJECT,
            "voiceIdentityRef": lock_version["voiceIdentityRef"],
            "voiceIdentityVersionRef": lock_version[
                "voiceIdentityVersionRef"
            ],
            "voiceIdentityDigest": lock_version["voiceIdentityDigest"],
            "voiceLockRef": lock["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": lock_version["voiceLockVersionRef"],
            "voiceLockVersionDigest": lock_version["payloadDigest"],
            "voiceLockConfirmationRef": confirmation[
                "voiceLockConfirmationRef"
            ],
            "voiceLockConfirmationDigest": confirmation["payloadDigest"],
            "sourceRecordingBindingRef": binding[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": binding["payloadDigest"],
            "consentGrantVersionRef": consent["consentGrantVersionRef"],
            "consentGrantVersionDigest": consent["payloadDigest"],
            "rightsBindingRef": consent["rightsBindingRef"],
            "rightsBindingDigest": consent["rightsBindingDigest"],
            "engineId": ENGINE_ID,
            "engineCommit": ENGINE_COMMIT,
            "modelId": MODEL_ID,
            "modelBundleDigest": MODEL_BUNDLE_DIGEST,
            "dependencyLockDigest": "e" * 64,
            "runtimeManifestDigest": "f" * 64,
            "profilePackage": profile_package() if package is None else package,
            "status": status,
            "createdAt": CREATED_AT,
            "createdBy": "v5.m12-c1.contract-test",
            "confirmedAt": (
                None
                if status == "CANDIDATE"
                else CREATED_AT
            ),
        }
    )


def lineage_graph() -> dict:
    binding = source_binding()
    grant_root = consent_root()
    grant = consent_version()
    lock = clone_lock_bundle()
    profile = profile_version(status="CANDIDATE")
    return sealed(
        {
            "schemaVersion": VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "sourceVoiceRecordingAssetVersionBindings": [binding],
            "consentGrants": [grant_root],
            "consentGrantVersions": [grant],
            "voiceLocks": [lock["voiceLock"]],
            "voiceLockVersions": [lock["voiceLockVersion"]],
            "voiceLockConfirmations": [lock["voiceLockConfirmation"]],
            "voiceProfiles": [profile_root()],
            "voiceProfileVersions": [profile],
            "publicationAllowed": False,
        }
    )


def clone_audio_authority_lineage(*, profile_status: str = "CONFIRMED") -> dict:
    rights = build_rights_binding(
        {
            "rightsBindingRef": "rights-binding-clone-audio-1",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED_AND_CONSENT_BOUND",
            "ownership": "PROJECT_OWNER",
            "usageScope": [
                "AUDIO_PRODUCTION",
                "VOICE_CLONING",
                "VOICE_PROFILE_USE",
            ],
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": "rights-manifest-clone-audio-1",
                    "sourceDigest": "7" * 64,
                },
                {
                    "sourceRef": "rights-evidence-clone-audio-1",
                    "sourceDigest": "8" * 64,
                },
                {
                    "sourceRef": "asset-requirement-voice",
                    "sourceDigest": "6" * 64,
                },
            ],
            "rightsManifestRef": "rights-manifest-clone-audio-1",
            "rightsManifestVersion": 1,
            "rightsManifestDigest": "7" * 64,
            "authorityEvidenceRef": "rights-evidence-clone-audio-1",
            "authorityEvidenceDigest": "8" * 64,
        }
    )
    source = source_binding()
    source["sourceRightsBindingRef"] = rights["rightsBindingRef"]
    source["sourceRightsBindingDigest"] = rights["payloadDigest"]
    source = sealed(source)
    consent = consent_version()
    consent.update(
        {
            "sourceRecordingBindingRef": source[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": source["payloadDigest"],
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
        }
    )
    consent = sealed(consent)
    lock = clone_lock_bundle(
        binding=source,
        consent=consent,
        version_ref="voice-lock-version-clone-audio-2",
        confirmation_ref="voice-lock-confirmation-clone-audio-2",
    )
    lock_version = lock["voiceLockVersion"]
    confirmation = lock["voiceLockConfirmation"]
    profile = profile_version(status=profile_status)
    profile.update(
        {
            "voiceIdentityRef": lock_version["voiceIdentityRef"],
            "voiceIdentityVersionRef": lock_version[
                "voiceIdentityVersionRef"
            ],
            "voiceIdentityDigest": lock_version["voiceIdentityDigest"],
            "voiceLockRef": lock["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": lock_version["voiceLockVersionRef"],
            "voiceLockVersionDigest": lock_version["payloadDigest"],
            "voiceLockConfirmationRef": confirmation[
                "voiceLockConfirmationRef"
            ],
            "voiceLockConfirmationDigest": confirmation["payloadDigest"],
            "sourceRecordingBindingRef": source[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": source["payloadDigest"],
            "consentGrantVersionRef": consent["consentGrantVersionRef"],
            "consentGrantVersionDigest": consent["payloadDigest"],
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
            "status": profile_status,
            "confirmedAt": None if profile_status == "CANDIDATE" else CREATED_AT,
        }
    )
    profile = sealed(profile)
    return {
        "rights": rights,
        "source": validate_source_voice_recording_binding(source),
        "consent": validate_consent_grant_version_v2(consent),
        "lock": lock,
        "profile": validate_voice_profile_version(profile),
    }


def clone_voice_asset_command(lineage: dict) -> dict:
    source = lineage["source"].as_dict()
    consent = lineage["consent"].as_dict()
    profile = lineage["profile"].as_dict()
    lock = lineage["lock"]
    lock_version = lock["voiceLockVersion"]
    command = common_asset_command("voice", rights=lineage["rights"])
    command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceIdentityRef": profile["voiceIdentityRef"],
            "characterRef": SUBJECT,
            "voiceProfileRef": profile["voiceProfileRef"],
            "voiceProfileVersionRef": profile["voiceProfileVersionRef"],
            "voiceProfileVersionDigest": profile["payloadDigest"],
            "voiceLockVersionRef": lock_version["voiceLockVersionRef"],
            "voiceLockVersionDigest": lock_version["payloadDigest"],
            "voiceSourceKind": "CLONED_WITH_CONSENT",
            "voiceSourceSubjectRef": SUBJECT,
            "sourceRecordingBindingRef": source[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": source["payloadDigest"],
            "consentGrantRef": consent["consentGrantRef"],
            "consentGrantVersionRef": consent["consentGrantVersionRef"],
            "consentGrantVersionDigest": consent["payloadDigest"],
            "rightsBindingRef": lineage["rights"]["rightsBindingRef"],
            "rightsBindingDigest": lineage["rights"]["payloadDigest"],
            "engineId": profile["engineId"],
            "engineCommit": profile["engineCommit"],
            "modelId": profile["modelId"],
            "modelBundleDigest": profile["modelBundleDigest"],
            "dependencyLockDigest": profile["dependencyLockDigest"],
            "runtimeManifestDigest": profile["runtimeManifestDigest"],
        }
    )
    command["artifact"]["fileDigest"] = profile["profilePackage"][
        "fileDigest"
    ]
    return command


def pre_asset_generation_evidence(
    *,
    generation_request_digest: str = "a" * 64,
    parameters_digest: str = "b" * 64,
    workspace_ref: str = WORKSPACE,
    production_run_ref: str = RUN,
) -> dict:
    """Closed V4 evidence for validation before an AssetVersion exists."""

    lineage = {
        "workspaceRef": workspace_ref,
        "productionRunRef": production_run_ref,
        "assetRequirementRef": "asset-requirement-dialogue-clone-1",
        "assetRequirementDigest": "6" * 64,
        "generationRequestRef": "audio-generation-request-clone-1",
        "generationRequestVersionRef": "audio-generation-request-clone-1-v1",
        "creativeShotRef": "creative-shot-clone-1",
        "creativeShotVersionRef": "creative-shot-clone-1-v1",
        "creativeShotDigest": "7" * 64,
        "scriptRef": "script-clone-1",
        "scriptVersionRef": "script-clone-1-v1",
        "scriptVersionDigest": "8" * 64,
    }
    file_digest = "a" * 64
    storage_key = "asset-versions/audio/m12-c1/dialogue-clone-1.wav"
    artifact_ref = "audio-artifact-" + file_digest[:32]
    artifact_evidence_ref = "audio-artifact-evidence-" + _digest(
        {
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": "9" * 64,
            "storageKey": storage_key,
            "sha256": file_digest,
        }
    )[:32]
    aliases = {
        **lineage,
        "generationRequestDigest": generation_request_digest,
        "executionRequestDigest": "9" * 64,
        "adapterIdentity": "v4.local-clone-tts.contract-fixture.v1",
        "provenance": "LOCAL_EVIDENCE",
        "artifactEvidenceRef": artifact_evidence_ref,
        "artifactRef": artifact_ref,
        "storageKey": storage_key,
        "byteSize": 192_044,
        "sha256": file_digest,
        "sampleRate": 48_000,
        "channels": 1,
        "probe": {
            "sampleRate": 48_000,
            "channels": 1,
            "durationSeconds": 2.0,
            "durationSamples": 96_000,
            "codec": "pcm_s16le",
            "container": "wav",
        },
        "parametersDigest": parameters_digest,
        "effectiveParametersDigest": "c" * 64,
        "synthesisSpecDigest": "d" * 64,
        "audioRole": "dialogue",
        "publicationAllowed": False,
    }
    evidence = sealed(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            **aliases,
            "state": "TECHNICALLY_VERIFIED",
        }
    )
    generation = sealed(
        {
            "schemaVersion": "v4.audio-generation-result.v1",
            **aliases,
            "generationResultRef": "audio-generation-result-clone-1",
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "state": "SUCCEEDED",
        }
    )
    analysis = analysis_evidence({"v4Evidence": evidence})
    return {
        "generationResult": generation,
        "artifactEvidence": evidence,
        "analysisEvidence": analysis,
    }


def pre_asset_validation_command() -> dict:
    return {
        "validationRef": "audio-technical-validation-dialogue-clone-1",
        "validationVersionRef": (
            "audio-technical-validation-dialogue-clone-1-v1"
        ),
        "version": 1,
        "supersedesValidationVersionRef": None,
        "supersedesValidationVersionDigest": None,
        "createdBy": "v5.m12-c1.contract-test",
        "createdAt": CREATED_AT,
    }


def build_pre_asset_validation_fixture(
    evidence: dict | None = None,
) -> tuple[dict, object, dict]:
    sources = pre_asset_generation_evidence() if evidence is None else evidence
    value = build_pre_asset_audio_technical_validation(
        pre_asset_validation_command(),
        generation_result=sources["generationResult"],
        artifact_evidence=sources["artifactEvidence"],
        v4_analysis_evidence=sources["analysisEvidence"],
    )
    wrapper = validate_pre_asset_audio_technical_validation(
        value,
        generation_result=sources["generationResult"],
        artifact_evidence=sources["artifactEvidence"],
        v4_analysis_evidence=sources["analysisEvidence"],
    )
    return value, wrapper, sources


def clone_dialogue_rights_binding() -> dict:
    return build_rights_binding(
        {
            "rightsBindingRef": "rights-binding-clone-dialogue-1",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED_AND_CONSENT_BOUND",
            "ownership": "PROJECT_OWNER",
            "usageScope": ["AUDIO_PRODUCTION", "SPEECH_SYNTHESIS"],
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": "rights-manifest-clone-dialogue-1",
                    "sourceDigest": "1" * 64,
                },
                {
                    "sourceRef": "rights-evidence-clone-dialogue-1",
                    "sourceDigest": "2" * 64,
                },
                {
                    "sourceRef": "asset-requirement-dialogue-clone-1",
                    "sourceDigest": "6" * 64,
                },
            ],
            "rightsManifestRef": "rights-manifest-clone-dialogue-1",
            "rightsManifestVersion": 1,
            "rightsManifestDigest": "1" * 64,
            "authorityEvidenceRef": "rights-evidence-clone-dialogue-1",
            "authorityEvidenceDigest": "2" * 64,
        }
    )


def clone_dialogue_request_command(
    voice_asset: dict,
    confirmed_voice_lock: dict,
    rights: dict,
) -> dict:
    parameters = normalize_clone_speech_parameters(
        {
            "speechSynthesis": True,
            "text": "不要动。",
            "voiceRef": confirmed_voice_lock["voiceLock"]["voiceRef"],
            "emotionTag": "tense",
            "audioRole": "dialogue",
        },
        confirmed_voice_lock=confirmed_voice_lock,
    )
    return {
        "requestKind": "DIALOGUE_SYNTHESIS",
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": "episode-m12-c1",
        "productionRunRef": RUN,
        "generationRequestRef": "audio-generation-request-clone-1",
        "generationRequestVersionRef": "audio-generation-request-clone-1-v1",
        "version": 1,
        "supersedesGenerationRequestVersionRef": None,
        "supersedesGenerationRequestVersionDigest": None,
        "assetRequirementRef": "asset-requirement-dialogue-clone-1",
        "assetRequirementDigest": "6" * 64,
        "outputAssetVersionType": "DialogueAssetVersion",
        "outputTarget": "ASSET_VERSION",
        "requestSpec": {
            "speechRole": "dialogue",
            "scriptVersionRef": "script-clone-1-v1",
            "scriptVersionDigest": "8" * 64,
            "dialogueRef": "dialogue-line-clone-1",
            "narrationRef": None,
            "voiceAssetVersionRef": voice_asset["assetVersionRef"],
            "voiceAssetVersionDigest": voice_asset["payloadDigest"],
            "language": "zh-CN",
            "normalizedSpeechParameters": parameters,
            "sourceAudioCueRefs": [],
        },
        "rightsBinding": rights,
        "requestedProvenance": build_requested_audio_provenance(
            {
                "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                "adapterIdentity": "v4.local-clone-tts.contract-fixture.v1",
                "parametersDigest": _digest(parameters),
                "sourceRefs": [
                    {
                        "sourceRef": "asset-requirement-dialogue-clone-1",
                        "sourceDigest": "6" * 64,
                    }
                ],
            }
        ),
        "createdBy": "v5.m12-c1.contract-test",
        "createdAt": CREATED_AT,
    }


def clone_dialogue_chain() -> dict:
    lineage = clone_audio_authority_lineage()
    voice_mapping = build_clone_voice_asset_version(
        clone_voice_asset_command(lineage),
        voice_profile_version=lineage["profile"],
        confirmed_voice_lock=lineage["lock"],
        consent_grant_version=lineage["consent"],
        source_recording_binding=lineage["source"],
        evaluated_at=EVALUATED_AT,
    )
    voice = validate_voice_asset_version(
        voice_mapping,
        voice_profile_version=lineage["profile"],
        confirmed_voice_lock=lineage["lock"],
        consent_grant_version=lineage["consent"],
        source_recording_binding=lineage["source"],
        evaluated_at=EVALUATED_AT,
    )
    rights = clone_dialogue_rights_binding()
    request_mapping = build_audio_generation_request(
        clone_dialogue_request_command(voice_mapping, lineage["lock"], rights),
        confirmed_voice_lock=lineage["lock"],
        voice_asset_version=voice,
        voice_profile_version=lineage["profile"],
        consent_grant_version=lineage["consent"],
        source_recording_binding=lineage["source"],
        evaluated_at=EVALUATED_AT,
    )
    request = AudioGenerationRequest.from_mapping(
        request_mapping,
        confirmed_voice_lock=lineage["lock"],
        voice_asset_version=voice,
        voice_profile_version=lineage["profile"],
        consent_grant_version=lineage["consent"],
        source_recording_binding=lineage["source"],
        evaluated_at=EVALUATED_AT,
    )
    evidence = pre_asset_generation_evidence(
        generation_request_digest=request_mapping["payloadDigest"]
    )
    technical_mapping = build_pre_asset_audio_technical_validation(
        pre_asset_validation_command(),
        generation_result=evidence["generationResult"],
        artifact_evidence=evidence["artifactEvidence"],
        v4_analysis_evidence=evidence["analysisEvidence"],
    )
    technical = validate_pre_asset_audio_technical_validation(
        technical_mapping,
        generation_result=evidence["generationResult"],
        artifact_evidence=evidence["artifactEvidence"],
        v4_analysis_evidence=evidence["analysisEvidence"],
    )
    generation = evidence["generationResult"]
    artifact_evidence = evidence["artifactEvidence"]
    request_spec = request_mapping["requestSpec"]
    command = common_asset_command("dialogue", rights=rights)
    command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": "episode-m12-c1",
            "productionRunRef": RUN,
            "assetRequirementRef": request_mapping["assetRequirementRef"],
            "assetRequirementDigest": request_mapping[
                "assetRequirementDigest"
            ],
            "generationRequestRef": request_mapping["generationRequestRef"],
            "generationRequestVersionRef": request_mapping[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": request_mapping["payloadDigest"],
            "generationResultRef": generation["generationResultRef"],
            "generationResultDigest": generation["payloadDigest"],
            "artifact": {
                "artifactKind": "PCM_AUDIO",
                "artifactEvidenceRef": artifact_evidence[
                    "artifactEvidenceRef"
                ],
                "artifactEvidenceDigest": artifact_evidence["payloadDigest"],
                "artifactRef": artifact_evidence["artifactRef"],
                "storageKey": artifact_evidence["storageKey"],
                "byteSize": artifact_evidence["byteSize"],
                "fileDigest": artifact_evidence["sha256"],
                "mediaType": "audio/wav",
            },
            "provenance": build_audio_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "adapterIdentity": artifact_evidence["adapterIdentity"],
                    "generationRecordRef": generation[
                        "generationResultRef"
                    ],
                    "parametersDigest": artifact_evidence[
                        "parametersDigest"
                    ],
                    "artifactEvidenceRef": artifact_evidence[
                        "artifactEvidenceRef"
                    ],
                    "artifactEvidenceDigest": artifact_evidence[
                        "payloadDigest"
                    ],
                    "sourceRefs": [
                        {
                            "sourceRef": request_mapping[
                                "generationRequestVersionRef"
                            ],
                            "sourceDigest": request_mapping["payloadDigest"],
                        },
                        {
                            "sourceRef": generation["generationResultRef"],
                            "sourceDigest": generation["payloadDigest"],
                        },
                    ],
                }
            ),
            "speechRole": request_spec["speechRole"],
            "scriptVersionRef": request_spec["scriptVersionRef"],
            "scriptVersionDigest": request_spec["scriptVersionDigest"],
            "dialogueRef": request_spec["dialogueRef"],
            "narrationRef": request_spec["narrationRef"],
            "voiceAssetVersionRef": request_spec["voiceAssetVersionRef"],
            "voiceAssetVersionDigest": request_spec[
                "voiceAssetVersionDigest"
            ],
            "language": request_spec["language"],
            "normalizedSpeechParameters": request_spec[
                "normalizedSpeechParameters"
            ],
            "sourceAudioCueRefs": request_spec["sourceAudioCueRefs"],
            "audioTechnicalValidationRef": technical_mapping[
                "validationVersionRef"
            ],
            "audioTechnicalValidationDigest": technical_mapping[
                "payloadDigest"
            ],
            "audioFileDigest": technical_mapping["fileDigest"],
            "audioPcmContentDigest": technical_mapping[
                "pcmContentDigest"
            ],
        }
    )
    dialogue = build_clone_dialogue_asset_version(
        command,
        voice_asset_version=voice,
        audio_generation_request=request,
        generation_result=generation,
        artifact_evidence=artifact_evidence,
        audio_technical_validation=technical,
        confirmed_voice_lock=lineage["lock"],
        voice_profile_version=lineage["profile"],
        consent_grant_version=lineage["consent"],
        source_recording_binding=lineage["source"],
        evaluated_at=EVALUATED_AT,
    )
    return {
        **lineage,
        "voice": voice,
        "voiceMapping": voice_mapping,
        "request": request,
        "requestMapping": request_mapping,
        "evidence": evidence,
        "technical": technical,
        "technicalMapping": technical_mapping,
        "dialogue": dialogue,
    }


class M12VoiceProfileLineageContractTests(unittest.TestCase):
    def test_source_recording_asset_is_deterministic_human_audio_projection(self):
        value = source_recording_asset()
        wrapper = validate_source_voice_recording_asset_version(value)
        self.assertEqual(wrapper.as_dict(), value)
        self.assertEqual(
            value["schemaVersion"],
            SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION,
        )
        self.assertEqual(value["sourceAudioKind"], "HUMAN_SOURCE_RECORDING")
        self.assertFalse(value["speechSynthesis"])
        self.assertFalse(value["voiceClone"])
        self.assertFalse(value["syntheticSpeech"])
        self.assertEqual(source_recording_asset(), value)
        self.assertTrue(
            value["sourceVoiceRecordingAssetVersionRef"].startswith(
                "source-voice-recording-asset-version-"
            )
        )

    def test_source_projection_ref_pins_file_time_and_creator_body_fields(self):
        original = source_recording_asset()
        mutations = {
            "audio-file-digest": lambda value: value.__setitem__(
                "audioFileDigest", "e" * 64
            ),
            "created-at": lambda value: value.__setitem__(
                "createdAt", "2026-08-30T08:00:01Z"
            ),
            "created-by": lambda value: value.__setitem__(
                "createdBy", "v5.m12-c1.source-recording-projection.v2"
            ),
        }
        for name, mutate in mutations.items():
            same_ref_drift = deepcopy(original)
            mutate(same_ref_drift)
            same_ref_drift = sealed(same_ref_drift)
            self.assertEqual(
                same_ref_drift["sourceVoiceRecordingAssetVersionRef"],
                original["sourceVoiceRecordingAssetVersionRef"],
            )
            with self.subTest(field=name), self.assertRaises(
                VoiceProfileLineageStaleError
            ):
                validate_source_voice_recording_asset_version(same_ref_drift)

    def test_synthetic_dialogue_clone_fixture_and_indeterminate_sources_fail_closed(self):
        mutations = {
            "dialogue-asset-version": lambda value: value.__setitem__(
                "schemaVersion", DIALOGUE_ASSET_VERSION_SCHEMA_VERSION
            ),
            "tts-speech-synthesis": lambda value: value.__setitem__(
                "speechSynthesis", True
            ),
            "tts-synthetic-speech": lambda value: value.__setitem__(
                "syntheticSpeech", True
            ),
            "voice-clone": lambda value: value.__setitem__(
                "voiceClone", True
            ),
            "fixture-marker": lambda value: value.__setitem__(
                "createdBy", "TEST_FIXTURE_ONLY"
            ),
            "source-kind-indeterminate": lambda value: value.__setitem__(
                "sourceAudioKind", "INDETERMINATE"
            ),
            "forged-projection-ref": lambda value: value.__setitem__(
                "sourceVoiceRecordingAssetVersionRef",
                "source-voice-recording-asset-version-forged",
            ),
        }
        for name, mutate in mutations.items():
            invalid = source_recording_asset()
            mutate(invalid)
            invalid = sealed(invalid)
            with self.subTest(case=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_source_voice_recording_asset_version(invalid)

    def test_source_binding_is_closed_acyclic_and_path_free(self):
        value = source_binding()
        source = source_recording_asset()
        wrapper = validate_source_voice_recording_binding(value)
        self.assertEqual(wrapper.as_dict(), value)
        self.assertEqual(
            value["sourceVoiceRecordingAssetVersionRef"],
            source["sourceVoiceRecordingAssetVersionRef"],
        )
        self.assertEqual(
            value["sourceVoiceRecordingAssetVersionDigest"],
            source["payloadDigest"],
        )
        self.assertEqual(
            value["canonicalAssetVersionDigest"],
            source["canonicalAssetVersionDigest"],
        )
        for forbidden in (
            "consentGrantRef",
            "consentGrantVersionRef",
            "consentGrantVersionDigest",
            "voiceLockRef",
            "voiceProfileRef",
            "voiceAssetVersionRef",
            "dialogueAssetVersionRef",
            "storageKey",
            "absolutePath",
            "sourcePath",
        ):
            self.assertNotIn(forbidden, value)
            injected = deepcopy(value)
            injected[forbidden] = "forged-descendant"
            injected = sealed(injected)
            with self.subTest(forbidden=forbidden), self.assertRaises(
                VoiceProfileLineageError
            ):
                validate_source_voice_recording_binding(injected)

    def test_source_binding_digest_probe_and_payload_tampering_fail_closed(self):
        original = source_binding()
        mutations = {
            "asset-digest": lambda value: value.__setitem__(
                "sourceVoiceRecordingAssetVersionDigest", "x" * 64
            ),
            "canonical-asset-digest": lambda value: value.__setitem__(
                "canonicalAssetVersionDigest", "x" * 64
            ),
            "file-digest": lambda value: value.__setitem__(
                "audioFileDigest", "0" * 63
            ),
            "pcm-digest": lambda value: value.__setitem__(
                "audioPcmContentDigest", "A" * 64
            ),
            "probe": lambda value: value["mediaProbe"].__setitem__(
                "sampleCount", 0
            ),
            "transcript": lambda value: value.__setitem__(
                "transcriptTextDigest", None
            ),
            "sealed-payload": lambda value: value.__setitem__(
                "subjectRef", "character-other"
            ),
        }
        for name, mutate in mutations.items():
            changed = deepcopy(original)
            mutate(changed)
            if name != "sealed-payload":
                changed = sealed(changed)
            with self.subTest(name=name), self.assertRaises(
                (VoiceProfileLineageError, VoiceProfileLineageStaleError)
            ):
                validate_source_voice_recording_binding(changed)

    def test_lineage_wrappers_cannot_be_directly_forged_or_mutated(self):
        cases = (
            (SourceVoiceRecordingAssetVersion, source_recording_asset()),
            (SourceVoiceRecordingAssetVersionBinding, source_binding()),
            (ConsentGrantVersionV2, consent_version()),
            (VoiceProfileVersion, profile_version()),
        )
        for contract_type, value in cases:
            with self.subTest(contract=contract_type.__name__), self.assertRaises(
                TypeError
            ):
                contract_type(value)
        wrappers = (
            validate_source_voice_recording_asset_version(
                source_recording_asset()
            ),
            validate_source_voice_recording_binding(source_binding()),
            validate_consent_grant_version_v2(consent_version()),
            validate_voice_profile_version(profile_version()),
        )
        for wrapper in wrappers:
            self.assertFalse(hasattr(wrapper, "_value"))
            detached = wrapper.as_dict()
            detached["subjectRef"] = "forged-subject"
            self.assertNotEqual(wrapper.as_dict()["subjectRef"], "forged-subject")

    def test_consent_root_and_v2_are_distinct_immutable_contracts(self):
        root = consent_root()
        version = consent_version()
        self.assertEqual(validate_consent_grant_root(root).as_dict(), root)
        self.assertEqual(
            validate_consent_grant_version_v2(version).as_dict(), version
        )
        self.assertNotIn("sourceRecordingBindingRef", root)
        self.assertEqual(version["versionNumber"], 1)

        detached = validate_consent_grant_version_v2(version).as_dict()
        detached["subjectRef"] = "forged"
        self.assertEqual(
            validate_consent_grant_version_v2(version).as_dict()["subjectRef"],
            SUBJECT,
        )

    def test_consent_requires_all_closed_clone_uses(self):
        required = {
            "VOICE_CLONING",
            "VOICE_PROFILE_USE",
            "AUDIO_PRODUCTION",
        }
        for missing in sorted(required):
            grant = consent_version(
                allowed_uses=sorted(required - {missing})
            )
            with self.subTest(missing=missing), self.assertRaises(
                VoiceProfileLineageNotEffectiveError
            ):
                require_active_consent_grant_version(
                    grant, evaluated_at=EVALUATED_AT
                )

        unknown = consent_version(
            allowed_uses=sorted(required | {"UNBOUNDED_UNKNOWN_USE"})
        )
        with self.assertRaises(VoiceProfileLineageError):
            validate_consent_grant_version_v2(unknown)

    def test_consent_time_and_revocation_are_evaluated_at_explicit_utc(self):
        cases = {
            "future": consent_version(
                valid_from="2026-08-31T00:00:00Z",
                expires_at="2027-08-31T00:00:00Z",
            ),
            "expired": consent_version(
                valid_from="2025-08-30T00:00:00Z",
                expires_at="2026-08-30T08:29:59Z",
            ),
            "revoked": consent_version(revocation_state="REVOKED"),
        }
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaises(
                VoiceProfileLineageNotEffectiveError
            ):
                require_active_consent_grant_version(
                    value, evaluated_at=EVALUATED_AT
                )

        local_time = consent_version()
        local_time["validFrom"] = "2026-08-30T08:00:00+08:00"
        local_time = sealed(local_time)
        with self.assertRaises(VoiceProfileLineageError):
            validate_consent_grant_version_v2(local_time)

    def test_consent_subject_source_and_rights_are_digest_pinned(self):
        grant = consent_version()
        binding = source_binding()
        expected = {
            "expected_subject_ref": SUBJECT,
            "expected_source_binding_ref": binding[
                "sourceRecordingBindingRef"
            ],
            "expected_source_binding_digest": binding["payloadDigest"],
            "expected_rights_binding_ref": binding[
                "sourceRightsBindingRef"
            ],
            "expected_rights_binding_digest": binding[
                "sourceRightsBindingDigest"
            ],
        }
        self.assertEqual(
            require_active_consent_grant_version(
                grant, evaluated_at=EVALUATED_AT, **expected
            ).as_dict(),
            grant,
        )
        stale_cases = {
            "subject": {"expected_subject_ref": "character-other"},
            "source": {"expected_source_binding_digest": "0" * 64},
            "rights": {"expected_rights_binding_digest": "0" * 64},
        }
        for name, changed in stale_cases.items():
            arguments = {**expected, **changed}
            with self.subTest(name=name), self.assertRaises(
                VoiceProfileLineageStaleError
            ):
                require_active_consent_grant_version(
                    grant, evaluated_at=EVALUATED_AT, **arguments
                )

    def test_consent_successor_requires_exact_predecessor_shape(self):
        first = consent_version()
        successor = consent_version(version_number=2, parent=first)
        self.assertEqual(
            validate_consent_grant_version_v2(successor).as_dict(), successor
        )
        for field, value in (
            ("parentConsentGrantVersionRef", None),
            ("parentConsentGrantVersionDigest", "0" * 63),
            ("consentGrantVersionRef", first["consentGrantVersionRef"]),
        ):
            invalid = deepcopy(successor)
            invalid[field] = value
            invalid = sealed(invalid)
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_consent_grant_version_v2(invalid)

    def test_clone_voice_lock_v2_cannot_be_confused_with_fixed_voice_v1(self):
        confirmed = clone_lock_bundle()
        fixed = fixed_voice_lock_bundle()
        validated = validate_confirmed_clone_voice_lock_bundle(confirmed)
        self.assertEqual(
            validated["voiceLockVersion"]["schemaVersion"],
            VOICE_LOCK_VERSION_V2_SCHEMA_VERSION,
        )
        self.assertEqual(
            validated["voiceLockConfirmation"]["voiceLockDigest"],
            validated["voiceLockVersion"]["payloadDigest"],
        )
        self.assertEqual(
            validated["voiceLock"]["voiceRef"],
            fixed["voiceLock"]["voiceRef"],
        )
        self.assertEqual(
            validated["voiceLockVersion"]["parentVoiceLockVersionRef"],
            fixed["voiceLockVersion"]["voiceLockVersionRef"],
        )
        self.assertEqual(
            validated["voiceLockVersion"]["parentVoiceLockDigest"],
            fixed["voiceLockVersion"]["payloadDigest"],
        )
        with self.assertRaises(VoiceLockNotConfirmedError):
            validate_confirmed_clone_voice_lock_bundle(
                voice_bundle("character-lin", "voice-lin")
            )
        for field, value in (
            ("engineFamily", "hexgrad/Kokoro-82M:FIXED_VOICE_LOCAL"),
            ("voiceId", "fixed-voice-af-heart"),
        ):
            invalid = deepcopy(confirmed["voiceLockVersion"])
            invalid[field] = value
            invalid = sealed(invalid)
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_voice_lock_version_v2(invalid)

    def test_fixed_and_clone_speech_normalizers_reject_wrong_lock_generation(self):
        fixed = fixed_voice_lock_bundle()
        clone = clone_lock_bundle()
        parameters = {
            "speechSynthesis": True,
            "text": "不要动。",
            "voiceRef": fixed["voiceLock"]["voiceRef"],
            "emotionTag": "tense",
            "audioRole": "dialogue",
        }
        self.assertEqual(
            normalize_speech_parameters(
                parameters,
                confirmed_voice_lock=fixed,
            )["voiceRef"],
            fixed["voiceLock"]["voiceRef"],
        )
        self.assertEqual(
            normalize_clone_speech_parameters(
                parameters,
                confirmed_voice_lock=clone,
            )["voiceRef"],
            clone["voiceLock"]["voiceRef"],
        )
        with self.assertRaises(VoiceLockNotConfirmedError):
            normalize_speech_parameters(
                parameters,
                confirmed_voice_lock=clone,
            )
        with self.assertRaises(VoiceLockNotConfirmedError):
            normalize_clone_speech_parameters(
                parameters,
                confirmed_voice_lock=fixed,
            )

    def test_clone_voice_lock_contracts_require_source_consent_and_confirmation(self):
        confirmed = clone_lock_bundle()
        root = confirmed["voiceLock"]
        self.assertEqual(validate_clone_voice_lock(root), root)
        self.assertEqual(root["schemaVersion"], VOICE_LOCK_SCHEMA_VERSION)
        self.assertEqual(
            confirmed["voiceLockVersion"]["versionNumber"], 2
        )
        self.assertEqual(
            confirmed["voiceLockVersion"]["parentVoiceLockVersionRef"],
            fixed_voice_lock_bundle()["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
        )
        for parallel_root_field in (
            "cloneVoiceLockRef",
            "voiceIdentityVersionRef",
            "sourceRecordingBindingRef",
        ):
            parallel_root = deepcopy(root)
            parallel_root[parallel_root_field] = "forbidden-parallel-root"
            parallel_root = sealed(parallel_root)
            with self.subTest(
                parallel_root_field=parallel_root_field
            ), self.assertRaises(EpisodeProductionError):
                validate_clone_voice_lock(parallel_root)
        self.assertEqual(
            validate_clone_voice_lock_version_v2(
                confirmed["voiceLockVersion"]
            ),
            confirmed["voiceLockVersion"],
        )
        self.assertEqual(
            validate_voice_lock_confirmation(
                confirmed["voiceLockConfirmation"]
            ),
            confirmed["voiceLockConfirmation"],
        )

        for missing in (
            "sourceRecordingBindingRef",
            "consentGrantVersionRef",
        ):
            invalid = deepcopy(confirmed["voiceLockVersion"])
            invalid.pop(missing)
            invalid = sealed(invalid)
            with self.subTest(missing=missing), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_voice_lock_version_v2(invalid)

        with self.assertRaises(EpisodeProductionError):
            validate_confirmed_clone_voice_lock_bundle(
                clone_lock_bundle(confirmed=False)
            )

    def test_voice_profile_contract_pins_full_clone_lineage(self):
        root = profile_root()
        version = profile_version()
        self.assertEqual(validate_voice_profile(root).as_dict(), root)
        self.assertEqual(
            validate_voice_profile_version(version).as_dict(), version
        )
        expected_pins = {
            "voiceIdentityDigest",
            "voiceLockVersionDigest",
            "voiceLockConfirmationDigest",
            "sourceRecordingBindingDigest",
            "consentGrantVersionDigest",
            "rightsBindingDigest",
            "modelBundleDigest",
            "dependencyLockDigest",
            "runtimeManifestDigest",
        }
        self.assertTrue(expected_pins.issubset(version))

    def test_voice_profile_digest_and_package_tampering_fail_closed(self):
        original = profile_version()
        mutations = {
            "engine-id-valid-drift": lambda value: value.__setitem__(
                "engineId", "QwenAudio/CosyVoice:CosyVoice3.OTHER_LOCAL"
            ),
            "engine-commit": lambda value: value.__setitem__(
                "engineCommit", "a" * 40
            ),
            "model-id-valid-drift": lambda value: value.__setitem__(
                "modelId",
                "FunAudioLLM/Fun-CosyVoice3-0.5B-2512@" + "a" * 40,
            ),
            "model-bundle-valid-drift": lambda value: value.__setitem__(
                "modelBundleDigest", "0" * 64
            ),
            "model": lambda value: value.__setitem__(
                "modelBundleDigest", "0" * 63
            ),
            "dependency": lambda value: value.__setitem__(
                "dependencyLockDigest", "G" * 64
            ),
            "runtime": lambda value: value.__setitem__(
                "runtimeManifestDigest", None
            ),
            "package-file": lambda value: value["profilePackage"].__setitem__(
                "fileDigest", None
            ),
            "package-content": lambda value: value[
                "profilePackage"
            ].__setitem__("contentDigest", ""),
        }
        for name, mutate in mutations.items():
            invalid = deepcopy(original)
            mutate(invalid)
            invalid = sealed(invalid)
            with self.subTest(name=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_version(invalid)

    def test_profile_successor_is_new_immutable_version_with_exact_parent(self):
        first = profile_version()
        second = profile_version(version_number=2, parent=first)
        self.assertEqual(
            validate_voice_profile_version(second).as_dict(), second
        )
        self.assertEqual(
            second["parentVoiceProfileVersionDigest"], first["payloadDigest"]
        )
        detached = validate_voice_profile_version(second).as_dict()
        detached["status"] = "REVOKED"
        self.assertEqual(
            validate_voice_profile_version(second).as_dict()["status"],
            "CONFIRMED",
        )

        for field, value in (
            ("parentVoiceProfileVersionRef", None),
            ("parentVoiceProfileVersionDigest", "0" * 63),
            ("voiceProfileVersionRef", first["voiceProfileVersionRef"]),
        ):
            invalid = deepcopy(second)
            invalid[field] = value
            invalid = sealed(invalid)
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_version(invalid)

    def test_test_fixture_is_sealed_nonproduction_and_rejected_as_profile_package(self):
        fixture = build_voice_profile_test_fixture(
            {
                "fixtureRef": "voice-profile-fixture-1",
                "profilePackage": profile_package(),
            }
        )
        self.assertEqual(validate_voice_profile_test_fixture(fixture), fixture)
        self.assertEqual(
            set(fixture["fixtureMarkers"]),
            set(VOICE_PROFILE_TEST_FIXTURE_MARKERS),
        )
        self.assertFalse(fixture["publicationAllowed"])

        marked_package = profile_package()
        marked_package["packageFormat"] = "TEST_FIXTURE_ONLY"
        invalid = profile_version(package=marked_package)
        with self.assertRaises(VoiceProfileFixtureRejectedError):
            validate_voice_profile_version(invalid)

    def test_lineage_is_forward_only_and_cycle_injection_is_rejected(self):
        binding = source_binding()
        grant = consent_version()
        lock = clone_lock_bundle()
        profile = profile_version()
        ordered = [binding, grant, lock["voiceLockVersion"], profile]
        refs = [
            binding["sourceRecordingBindingRef"],
            grant["consentGrantVersionRef"],
            lock["voiceLockVersion"]["voiceLockVersionRef"],
            profile["voiceProfileVersionRef"],
        ]
        for ancestor_index, ancestor in enumerate(ordered):
            encoded = repr(ancestor)
            for descendant_ref in refs[ancestor_index + 1 :]:
                self.assertNotIn(descendant_ref, encoded)

        cyclic = deepcopy(binding)
        cyclic["voiceProfileVersionRef"] = profile[
            "voiceProfileVersionRef"
        ]
        cyclic = sealed(cyclic)
        with self.assertRaises(VoiceProfileLineageError):
            validate_source_voice_recording_binding(cyclic)

    def test_lineage_graph_binds_every_single_root_authority_edge_exactly(self):
        original = lineage_graph()
        self.assertEqual(validate_voice_profile_lineage_graph(original), original)

        def changed_item(
            collection: str,
            field: str,
            value: object,
            *,
            preserve_lock_envelope: bool = False,
        ) -> dict:
            changed = deepcopy(original)
            item = deepcopy(changed[collection][0])
            item[field] = value
            item = sealed(item)
            changed[collection][0] = item
            if preserve_lock_envelope:
                root = deepcopy(changed["voiceLocks"][0])
                root["confirmedVoiceLockDigest"] = item["payloadDigest"]
                changed["voiceLocks"][0] = sealed(root)
                confirmation = deepcopy(changed["voiceLockConfirmations"][0])
                confirmation["voiceLockDigest"] = item["payloadDigest"]
                confirmation = sealed(confirmation)
                changed["voiceLockConfirmations"][0] = confirmation
                profile = deepcopy(changed["voiceProfileVersions"][0])
                profile["voiceLockVersionDigest"] = item["payloadDigest"]
                profile["voiceLockConfirmationDigest"] = confirmation[
                    "payloadDigest"
                ]
                changed["voiceProfileVersions"][0] = sealed(profile)
            return sealed(changed)

        lock_cases = (
            (
                "lock-source-digest",
                "sourceRecordingBindingDigest",
                "0" * 64,
            ),
            (
                "lock-consent-ref",
                "consentGrantVersionRef",
                "consent-version-other",
            ),
            (
                "lock-rights-digest",
                "rightsBindingDigest",
                "0" * 64,
            ),
            (
                "lock-identity-root",
                "voiceIdentityRef",
                "parallel-voice-root",
            ),
            (
                "lock-identity-version",
                "voiceIdentityVersionRef",
                "voice-version-other",
            ),
            (
                "lock-identity-digest",
                "voiceIdentityDigest",
                "0" * 64,
            ),
        )
        for name, field, value in lock_cases:
            invalid = changed_item(
                "voiceLockVersions",
                field,
                value,
                preserve_lock_envelope=True,
            )
            with self.subTest(edge=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(invalid)

        profile_cases = (
            (
                "profile-source-digest",
                "sourceRecordingBindingDigest",
                "0" * 64,
            ),
            (
                "profile-consent-ref",
                "consentGrantVersionRef",
                "consent-version-other",
            ),
            (
                "profile-lock-digest",
                "voiceLockVersionDigest",
                "0" * 64,
            ),
            (
                "profile-confirmation-ref",
                "voiceLockConfirmationRef",
                "confirmation-other",
            ),
            (
                "profile-confirmation-digest",
                "voiceLockConfirmationDigest",
                "0" * 64,
            ),
        )
        for name, field, value in profile_cases:
            invalid = changed_item("voiceProfileVersions", field, value)
            with self.subTest(edge=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(invalid)

        for name, field, value in (
            (
                "confirmation-version-ref",
                "voiceLockVersionRef",
                "voice-version-other",
            ),
            (
                "confirmation-version-digest",
                "voiceLockDigest",
                "0" * 64,
            ),
        ):
            invalid = changed_item("voiceLockConfirmations", field, value)
            with self.subTest(edge=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(invalid)

    def test_lineage_graph_and_nested_contract_envelopes_are_closed(self):
        original = lineage_graph()

        unexpected_graph_field = deepcopy(original)
        unexpected_graph_field["voiceLockRepository"] = "parallel-store"
        unexpected_graph_field = sealed(unexpected_graph_field)

        unexpected_source_field = deepcopy(original)
        source = deepcopy(
            unexpected_source_field[
                "sourceVoiceRecordingAssetVersionBindings"
            ][0]
        )
        source["consentGrantVersionDigest"] = "0" * 64
        unexpected_source_field[
            "sourceVoiceRecordingAssetVersionBindings"
        ][0] = sealed(source)
        unexpected_source_field = sealed(unexpected_source_field)

        missing_nested_digest = deepcopy(original)
        missing_nested_digest["consentGrantVersions"][0].pop(
            "payloadDigest"
        )
        missing_nested_digest = sealed(missing_nested_digest)

        stale_outer_digest = deepcopy(original)
        stale_outer_digest["productionRunRef"] = "run-drifted-after-seal"

        for name, invalid in (
            ("unexpected-graph-field", unexpected_graph_field),
            ("descendant-in-source-envelope", unexpected_source_field),
            ("missing-nested-digest", missing_nested_digest),
            ("stale-outer-digest", stale_outer_digest),
        ):
            with self.subTest(envelope=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(invalid)

    def test_clone_voice_asset_requires_independent_profile_authority_not_v1_nested_package(self):
        fixed_lock = voice_bundle("character-lin", "voice-lin")
        old_nested_command = voice_asset_command(fixed_lock)
        with self.assertRaises(EpisodeProductionError):
            build_clone_voice_asset_version(
                old_nested_command,
                voice_profile_version=None,
                confirmed_voice_lock=fixed_lock,
                consent_grant_version=None,
                source_recording_binding=None,
                evaluated_at=EVALUATED_AT,
                current_voice_profile_authority=None,
            )

    def test_clone_voice_asset_requires_service_issued_current_authority(self):
        for status in ("CONFIRMED", "REVOKED"):
            lineage = clone_audio_authority_lineage(profile_status=status)
            command = clone_voice_asset_command(lineage)
            with self.subTest(status=status), self.assertRaises(
                EpisodeProductionError
            ):
                build_clone_voice_asset_version(
                    command,
                    voice_profile_version=lineage["profile"],
                    confirmed_voice_lock=lineage["lock"],
                    consent_grant_version=lineage["consent"],
                    source_recording_binding=lineage["source"],
                    evaluated_at=EVALUATED_AT,
                    current_voice_profile_authority=None,
                )

    def test_v1_fixed_voice_asset_remains_readable(self):
        fixed_lock = voice_bundle("character-lin", "voice-lin")
        fixed = local_voice_asset(fixed_lock)
        validated = validate_voice_asset_version(
            fixed, confirmed_voice_lock=fixed_lock
        )
        self.assertEqual(validated.as_dict(), fixed)
        self.assertEqual(fixed["schemaVersion"], "v5.voice-asset-version.v1")
        self.assertIn("profilePackage", fixed)

    def test_v1_clone_history_reads_but_all_legacy_clone_builders_reject(self):
        fixed_lock = voice_bundle("character-lin", "voice-lin")
        legacy_consent = consent_grant()
        rights = clone_rights(legacy_consent)
        voice_command = voice_asset_command(
            fixed_lock,
            rights=rights,
            source_kind="CLONED_WITH_CONSENT",
            consent=legacy_consent,
        )
        historical_voice = sealed(
            {
                "schemaVersion": VOICE_ASSET_VERSION_SCHEMA_VERSION,
                "assetVersionType": "VoiceAssetVersion",
                **voice_command,
                "assetKind": "audio",
                "audioKind": "voice",
                "state": "PROPOSED",
                "authorityState": "CONTRACT_ONLY_NOT_ADMITTED",
                "immutable": True,
                "publicationAllowed": False,
            }
        )
        voice = validate_voice_asset_version(
            historical_voice,
            confirmed_voice_lock=fixed_lock,
            consent_grant=legacy_consent,
            evaluated_at=EVALUATED_AT,
        )
        self.assertEqual(voice.as_dict(), historical_voice)
        with self.assertRaises(EpisodeProductionError):
            build_voice_asset_version(
                voice_command,
                confirmed_voice_lock=fixed_lock,
                consent_grant=legacy_consent,
                evaluated_at=EVALUATED_AT,
            )

        request_command = cloned_voice_request_command(
            fixed_lock, legacy_consent, rights
        )
        historical_request = sealed(
            {
                "schemaVersion": AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
                **request_command,
                "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
                "immutable": True,
                "publicationAllowed": False,
            }
        )
        request = AudioGenerationRequest.from_mapping(
            historical_request,
            confirmed_voice_lock=fixed_lock,
            consent_grant=legacy_consent,
            evaluated_at=EVALUATED_AT,
        )
        self.assertEqual(request.as_dict(), historical_request)
        with self.assertRaises(EpisodeProductionError):
            build_audio_generation_request(
                request_command,
                confirmed_voice_lock=fixed_lock,
                consent_grant=legacy_consent,
                evaluated_at=EVALUATED_AT,
            )

        dialogue_command = common_asset_command("dialogue")
        dialogue_command.update(
            {
                "speechRole": "dialogue",
                "scriptVersionRef": "script-version-m12",
                "scriptVersionDigest": "a" * 64,
                "dialogueRef": "dialogue-line-m12",
                "narrationRef": None,
                "voiceAssetVersionRef": historical_voice["assetVersionRef"],
                "voiceAssetVersionDigest": historical_voice["payloadDigest"],
                "language": "zh-CN",
                "normalizedSpeechParameters": speech_parameters(
                    fixed_lock, "dialogue"
                ),
                "sourceAudioCueRefs": [],
            }
        )
        historical_dialogue = sealed(
            {
                "schemaVersion": DIALOGUE_ASSET_VERSION_SCHEMA_VERSION,
                "assetVersionType": "DialogueAssetVersion",
                **dialogue_command,
                "assetKind": "audio",
                "audioKind": "dialogue",
                "state": "PROPOSED",
                "authorityState": "CONTRACT_ONLY_NOT_ADMITTED",
                "immutable": True,
                "publicationAllowed": False,
            }
        )
        dialogue = validate_dialogue_asset_version(
            historical_dialogue,
            confirmed_voice_lock=fixed_lock,
            voice_asset_version=historical_voice,
            consent_grant=legacy_consent,
            evaluated_at=EVALUATED_AT,
        )
        self.assertEqual(dialogue.as_dict(), historical_dialogue)
        with self.assertRaises(EpisodeProductionError):
            build_dialogue_asset_version(
                dialogue_command,
                confirmed_voice_lock=fixed_lock,
                voice_asset_version=historical_voice,
                consent_grant=legacy_consent,
                evaluated_at=EVALUATED_AT,
            )

    def test_pre_asset_validation_v2_builds_initial_acyclic_version(self):
        value, wrapper, sources = build_pre_asset_validation_fixture()
        self.assertEqual(
            value["schemaVersion"],
            AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION,
        )
        self.assertEqual(wrapper.as_dict(), value)
        self.assertEqual(value["version"], 1)
        self.assertIsNone(value["supersedesValidationVersionRef"])
        self.assertIsNone(value["supersedesValidationVersionDigest"])
        self.assertEqual(
            value["generationResultDigest"],
            sources["generationResult"]["payloadDigest"],
        )
        self.assertEqual(
            value["artifactEvidenceDigest"],
            sources["artifactEvidence"]["payloadDigest"],
        )
        self.assertEqual(
            value["analysisEvidenceDigest"],
            sources["analysisEvidence"].as_dict()["payloadDigest"],
        )
        self.assertEqual(value["fileDigest"], "a" * 64)
        self.assertEqual(
            value["pcmContentDigest"],
            sources["analysisEvidence"].as_dict()["pcmContentDigest"],
        )
        forbidden = {
            "sourceAssetVersionType",
            "sourceAssetVersionRef",
            "sourceAssetVersionDigest",
            "dialogueAssetVersionRef",
            "voiceAssetVersionRef",
        }
        self.assertTrue(forbidden.isdisjoint(value))

    def test_pre_asset_validation_v2_rejects_generation_and_artifact_drift(self):
        value, _, sources = build_pre_asset_validation_fixture()

        generation_drift = deepcopy(sources)
        changed_result = deepcopy(generation_drift["generationResult"])
        changed_result["generationResultRef"] = (
            "audio-generation-result-clone-drift"
        )
        generation_drift["generationResult"] = sealed(changed_result)

        artifact_drift = deepcopy(sources)
        changed_evidence = deepcopy(artifact_drift["artifactEvidence"])
        changed_evidence["artifactEvidenceRef"] = (
            "audio-artifact-evidence-clone-drift"
        )
        changed_evidence = sealed(changed_evidence)
        changed_result = deepcopy(artifact_drift["generationResult"])
        changed_result.update(
            {
                "artifactEvidenceRef": changed_evidence[
                    "artifactEvidenceRef"
                ],
                "artifactEvidenceDigest": changed_evidence["payloadDigest"],
            }
        )
        artifact_drift.update(
            {
                "generationResult": sealed(changed_result),
                "artifactEvidence": changed_evidence,
            }
        )

        for name, changed in (
            ("generation", generation_drift),
            ("artifact", artifact_drift),
        ):
            with self.subTest(drift=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_pre_asset_audio_technical_validation(
                    value,
                    generation_result=changed["generationResult"],
                    artifact_evidence=changed["artifactEvidence"],
                    v4_analysis_evidence=changed["analysisEvidence"],
                )

    def test_pre_asset_validation_v2_rejects_analysis_file_and_pcm_drift(self):
        value, _, sources = build_pre_asset_validation_fixture()

        changed_analysis = sources["analysisEvidence"].as_dict()
        changed_analysis["integratedLufs"] = "-23.000"
        analysis_drift = AudioTechnicalAnalysisEvidence._from_analyzer(
            seal_analysis(changed_analysis)
        )

        file_sources = deepcopy(sources)
        changed_evidence = deepcopy(file_sources["artifactEvidence"])
        changed_evidence["sha256"] = "e" * 64
        changed_evidence["artifactRef"] = "audio-artifact-" + "e" * 32
        changed_evidence["artifactEvidenceRef"] = (
            "audio-artifact-evidence-"
            + _digest(
                {
                    "generationRequestDigest": changed_evidence[
                        "generationRequestDigest"
                    ],
                    "executionRequestDigest": changed_evidence[
                        "executionRequestDigest"
                    ],
                    "storageKey": changed_evidence["storageKey"],
                    "sha256": changed_evidence["sha256"],
                }
            )[:32]
        )
        changed_evidence = sealed(changed_evidence)
        changed_result = deepcopy(file_sources["generationResult"])
        changed_result.update(
            {
                "sha256": changed_evidence["sha256"],
                "artifactRef": changed_evidence["artifactRef"],
                "artifactEvidenceRef": changed_evidence[
                    "artifactEvidenceRef"
                ],
                "artifactEvidenceDigest": changed_evidence["payloadDigest"],
            }
        )
        file_sources.update(
            {
                "generationResult": sealed(changed_result),
                "artifactEvidence": changed_evidence,
                "analysisEvidence": analysis_evidence(
                    {"v4Evidence": changed_evidence}
                ),
            }
        )

        changed_analysis = sources["analysisEvidence"].as_dict()
        changed_analysis["pcmContentDigest"] = "f" * 64
        pcm_drift = AudioTechnicalAnalysisEvidence._from_analyzer(
            seal_analysis(changed_analysis)
        )

        cases = (
            ("analysis", sources, analysis_drift),
            ("file", file_sources, file_sources["analysisEvidence"]),
            ("pcm", sources, pcm_drift),
        )
        for name, changed, analysis in cases:
            with self.subTest(drift=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_pre_asset_audio_technical_validation(
                    value,
                    generation_result=changed["generationResult"],
                    artifact_evidence=changed["artifactEvidence"],
                    v4_analysis_evidence=analysis,
                )

    def test_audio_technical_validation_v1_remains_readable(self):
        source = technical_source()
        analysis = analysis_evidence(source)
        value = build_audio_technical_validation(
            v1_validation_command("m12-c1-v1-compat"),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        wrapper = validate_audio_technical_validation(
            value,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        self.assertEqual(
            value["schemaVersion"], AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION
        )
        self.assertEqual(wrapper.as_dict(), value)
        self.assertIn("sourceAssetVersionRef", value)
        self.assertNotIn("generationResultRef", value)

    def test_clone_dialogue_v2_cannot_omit_technical_validation_lineage(self):
        fixed_lock = voice_bundle("character-lin", "voice-lin")
        fixed_voice = local_voice_asset(fixed_lock)
        old_dialogue = dialogue_asset(fixed_lock, fixed_voice)
        forged_v2 = deepcopy(old_dialogue)
        forged_v2["schemaVersion"] = DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION
        forged_v2.update(
            {
                # Deliberately omit audioTechnicalValidationRef.  A caller may
                # not upgrade a v1 object by attaching detached digest fields.
                "audioTechnicalValidationDigest": "1" * 64,
                "audioFileDigest": old_dialogue["artifact"]["fileDigest"],
                "audioPcmContentDigest": "2" * 64,
            }
        )
        forged_v2 = sealed(forged_v2)
        with self.assertRaises(EpisodeProductionError):
            validate_clone_dialogue_asset_version(
                forged_v2,
                voice_asset_version=None,
                audio_generation_request=None,
                generation_result=None,
                artifact_evidence=None,
                audio_technical_validation=None,
                confirmed_voice_lock=fixed_lock,
                voice_profile_version=None,
                consent_grant_version=None,
                source_recording_binding=None,
                evaluated_at=EVALUATED_AT,
            )

    def test_no_creator_http_voice_profile_routes_are_added(self):
        routes = {
            value
            for name, value in vars(public_contract).items()
            if name.endswith("_ENDPOINT") and isinstance(value, str)
        }
        forbidden_fragments = {
            "voice-profile",
            "voice-lock",
            "source-voice-recording",
            "consent-grant",
        }
        self.assertFalse(
            any(fragment in route for fragment in forbidden_fragments for route in routes)
        )
        m12 = next(
            item
            for item in public_contract.capability_payload()["capabilities"]
            if item["id"] == "M12"
        )
        self.assertEqual(
            m12["publicResources"],
            [
                "episode-production-runs/production-readiness",
                "episode-production-runs/media",
            ],
        )


if __name__ == "__main__":
    unittest.main()
