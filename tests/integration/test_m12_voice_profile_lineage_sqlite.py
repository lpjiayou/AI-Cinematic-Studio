from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier, Lock
import unittest

from services.v4_platform.audio_validation import (
    AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST,
    AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
    AUDIO_TECHNICAL_VALIDATOR_VERSION,
    PCM_CLIPPING_THRESHOLD,
    PCM_CONTENT_DIGEST_SPEC,
    AudioTechnicalAnalysisEvidence,
)

from services.v5_core_os.episode_production.audio_authority import (
    AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
    DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION,
    VOICE_ASSET_VERSION_V2_SCHEMA_VERSION,
    AudioGenerationRequest,
    build_audio_generation_request,
    build_audio_provenance,
    build_clone_dialogue_asset_version,
    build_clone_voice_asset_version,
    build_dialogue_asset_version,
    build_rights_binding,
    validate_clone_dialogue_asset_version,
    validate_dialogue_asset_version,
    validate_voice_asset_version,
)
from services.v5_core_os.episode_production.audio_validation import (
    build_audio_technical_validation,
    build_pre_asset_audio_technical_validation,
    validate_pre_asset_audio_technical_validation,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    InMemoryEpisodeProductionEvidenceAdapter,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.voice_profile import (
    K2VoiceProfileLineageService,
    SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION,
    VOICE_PROFILE_SCHEMA_VERSION,
    VOICE_PROFILE_VERSION_SCHEMA_VERSION,
    VoiceProfileLineageError,
    VoiceProfileLineageNotEffectiveError,
    VoiceProfileLineageNotFoundError,
    VoiceProfileLineageStaleError,
    build_voice_profile_test_fixture,
    validate_voice_profile,
    validate_voice_profile_version,
    validate_consent_grant_version_v2,
    validate_source_voice_recording_binding,
    validate_voice_profile_lineage_graph,
)
from services.v5_core_os.episode_production.voice import (
    InMemoryVoiceLockAdapter,
    K2VoiceLockService,
    SqliteVoiceLockAdapter,
)
from tests.contract.test_m12_voice_profile_lineage_contract import (
    clone_dialogue_request_command,
    clone_voice_asset_command,
    pre_asset_generation_evidence,
    pre_asset_validation_command,
)
from tests.contract.test_m12_audio_authority_contract import (
    EPISODE as AUDIO_EPISODE,
    common_asset_command,
    local_voice_asset,
    speech_parameters,
)
from tests.contract.test_m12_audio_contract import (
    PROJECT as AUDIO_PROJECT,
    RUN as AUDIO_RUN,
    SERIES as AUDIO_SERIES,
    WORKSPACE as AUDIO_WORKSPACE,
    voice_bundle,
)
from tests.contract.test_m12_audio_technical_validation_contract import (
    analysis_evidence,
    seal_analysis,
    validation_command as v1_validation_command,
)


WORKSPACE = AUDIO_WORKSPACE
PROJECT = AUDIO_PROJECT
SERIES = AUDIO_SERIES
RUN = AUDIO_RUN
SAME_SERIES_RUN = f"{AUDIO_RUN}-same-series-successor"
FOREIGN_SERIES_RUN = f"{AUDIO_RUN}-foreign-series"
EPISODE = AUDIO_EPISODE
SUBJECT = "character-lin"
CREATED_AT = "2026-08-30T08:00:00Z"
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


class RootService:
    def get_run(self, workspace_ref: str, run_ref: str) -> dict:
        if run_ref not in {RUN, SAME_SERIES_RUN, FOREIGN_SERIES_RUN} or workspace_ref not in {
            WORKSPACE,
            "workspace-m12-c1-foreign",
        }:
            raise AssertionError("unexpected EpisodeProductionRun scope")
        project = PROJECT
        series = SERIES
        episode = EPISODE
        if run_ref == FOREIGN_SERIES_RUN:
            project = f"{PROJECT}-foreign"
            series = f"{SERIES}-foreign"
            episode = f"{EPISODE}-foreign"
        return {
            "workspaceRef": workspace_ref,
            "projectRef": project,
            "seriesRef": series,
            "episodeRef": episode,
            "productionRunRef": run_ref,
        }


class Refs:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        count = self.counts.get(prefix, 0) + 1
        self.counts[prefix] = count
        return f"{prefix}-{count}"


class ThreadSafeRefs(Refs):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()

    def __call__(self, prefix: str) -> str:
        with self._lock:
            return super().__call__(prefix)


def second_asset_admission_gate() -> GateAppend:
    payload = {
        "schemaVersion": "v5.test-second-asset-admission.v1",
        "admissionRef": "asset-admission-concurrent-second",
        "publicationAllowed": False,
    }
    return GateAppend(
        workspaceRef=WORKSPACE,
        productionRunRef=RUN,
        gateName="SECOND_ASSET_ADMISSION",
        idempotencyKey="second-asset-admission-concurrent",
        rootPayloadDigest="d" * 64,
        requestDigest=_digest({"operation": "second-asset-admission"}),
        fromState="ROOTS_READY",
        toState="AUTHORITY_READY",
        createdAt=CREATED_AT,
        facts=(
            EvidenceFact(
                factKind="AssetAdmission",
                factRef=payload["admissionRef"],
                factVersion=1,
                payload=payload,
                payloadDigest=_digest(payload),
            ),
        ),
    )


class InterveningAdmissionEvidenceAdapter(
    InMemoryEpisodeProductionEvidenceAdapter
):
    """Inject one admission gate after a C1 snapshot but before its append."""

    def __init__(self) -> None:
        super().__init__()
        self.inject_on_source_append = False

    def append_records(self, records, **kwargs):
        if self.inject_on_source_append and any(
            item.recordKind == "SourceVoiceRecordingAssetVersionBinding"
            for item in records
        ):
            self.inject_on_source_append = False
            self.append_gate(second_asset_admission_gate())
        return super().append_records(records, **kwargs)


class ConcurrentConsentEvidenceAdapter(
    InMemoryEpisodeProductionEvidenceAdapter
):
    def __init__(self) -> None:
        super().__init__()
        self.race_successors = False
        self._barrier = Barrier(2)

    def append_records(self, records, **kwargs):
        if self.race_successors and any(
            item.recordKind == "ConsentGrantVersion"
            and item.recordVersion == 2
            for item in records
        ):
            self._barrier.wait(timeout=5)
        return super().append_records(records, **kwargs)


def evidence_record(
    kind: str,
    ref: str,
    payload: dict,
    *,
    workspace: str = WORKSPACE,
    run: str = RUN,
    version: int = 1,
) -> EvidenceRecord:
    value = sealed(payload)
    return EvidenceRecord(
        workspaceRef=workspace,
        productionRunRef=run,
        recordKind=kind,
        recordRef=ref,
        recordVersion=version,
        idempotencyKey=f"seed-{workspace}-{run}-{kind}-{ref}-{version}",
        requestDigest=_digest(
            {
                "seedKind": kind,
                "seedRef": ref,
                "seedVersion": version,
                "payloadDigest": value["payloadDigest"],
            }
        ),
        createdAt=CREATED_AT,
        payload=value,
        payloadDigest=value["payloadDigest"],
    )


def rights_binding(
    *,
    asset_version_ref: str,
    asset_version_digest: str,
    source_evidence: list[dict[str, str]],
) -> dict:
    return build_rights_binding(
        {
            "rightsBindingRef": "rights-binding-source-1",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED_AND_CONSENT_BOUND",
            "ownership": "PROJECT_OWNER",
            "usageScope": [
                "AUDIO_PRODUCTION",
                "SPEECH_SYNTHESIS",
                "VOICE_CLONING",
                "VOICE_PROFILE_USE",
            ],
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": "rights-manifest-source-1",
                    "sourceDigest": "7" * 64,
                },
                {
                    "sourceRef": "rights-evidence-source-1",
                    "sourceDigest": "8" * 64,
                },
                {
                    "sourceRef": asset_version_ref,
                    "sourceDigest": asset_version_digest,
                },
                *deepcopy(source_evidence),
                {
                    "sourceRef": "consent-evidence-1",
                    "sourceDigest": "9" * 64,
                },
                {
                    "sourceRef": "asset-requirement-voice",
                    "sourceDigest": "6" * 64,
                },
                {
                    "sourceRef": "asset-requirement-dialogue-clone-1",
                    "sourceDigest": "6" * 64,
                },
            ],
            "rightsManifestRef": "rights-manifest-source-1",
            "rightsManifestVersion": 1,
            "rightsManifestDigest": "7" * 64,
            "authorityEvidenceRef": "rights-evidence-source-1",
            "authorityEvidenceDigest": "8" * 64,
        }
    )


def consent_successor_rights(
    binding: dict,
    parent_consent: dict,
    *,
    suffix: str,
    evidence_ref: str,
    evidence_digest: str,
) -> dict:
    """Build the new canonical rights fact required by a Consent successor."""

    return build_rights_binding(
        {
            "rightsBindingRef": f"rights-binding-consent-{suffix}",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED_AND_CONSENT_BOUND",
            "ownership": "PROJECT_OWNER",
            "usageScope": sorted(
                ["AUDIO_PRODUCTION", "VOICE_CLONING", "VOICE_PROFILE_USE"]
            ),
            "attributionRequirement": "",
            "sourceRefs": [
                {
                    "sourceRef": "rights-manifest-source-1",
                    "sourceDigest": "7" * 64,
                },
                {
                    "sourceRef": "rights-evidence-source-1",
                    "sourceDigest": "8" * 64,
                },
                {
                    "sourceRef": binding["canonicalAssetVersionRef"],
                    "sourceDigest": binding["canonicalAssetVersionDigest"],
                },
                {
                    "sourceRef": evidence_ref,
                    "sourceDigest": evidence_digest,
                },
                {
                    "sourceRef": parent_consent["rightsBindingRef"],
                    "sourceDigest": parent_consent["rightsBindingDigest"],
                },
            ],
            "rightsManifestRef": "rights-manifest-source-1",
            "rightsManifestVersion": 1,
            "rightsManifestDigest": "7" * 64,
            "authorityEvidenceRef": "rights-evidence-source-1",
            "authorityEvidenceDigest": "8" * 64,
        }
    )


def dialogue_technical_source() -> dict:
    """Produce the source through the real typed Dialogue builder."""

    confirmed_lock = voice_bundle(SUBJECT, "voice-source-dialogue")
    voice_asset = local_voice_asset(confirmed_lock)
    command = common_asset_command("dialogue")
    rights = deepcopy(command["rightsBinding"])
    rights["rightsBindingRef"] = "audio-rights-binding-dialogue-source-v1"
    command["rightsBinding"] = sealed(rights)
    sample_rate = 48_000
    sample_count = 48_000
    command["artifact"]["byteSize"] = 96_044
    command["artifact"]["fileDigest"] = _digest(
        {"pcmFixture": "dialogue-source", "sampleCount": sample_count}
    )
    file_digest = command["artifact"]["fileDigest"]
    artifact_ref = "audio-artifact-" + file_digest[:32]
    storage_key = command["artifact"]["storageKey"]
    artifact_evidence_ref = "audio-artifact-evidence-" + _digest(
        {
            "generationRequestDigest": command["generationRequestDigest"],
            "executionRequestDigest": _digest(
                {"audioRole": "dialogue", "execution": "fixture"}
            ),
            "storageKey": storage_key,
            "sha256": file_digest,
        }
    )[:32]
    parameters_digest = _digest(
        {"audioRole": "dialogue", "sampleRate": sample_rate, "channels": 1}
    )
    evidence = sealed(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRequirementRef": command["assetRequirementRef"],
            "assetRequirementDigest": command["assetRequirementDigest"],
            "generationRequestRef": command["generationRequestRef"],
            "generationRequestVersionRef": command[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": command["generationRequestDigest"],
            "executionRequestDigest": _digest(
                {"audioRole": "dialogue", "execution": "fixture"}
            ),
            "creativeShotRef": "creative-shot-dialogue-source",
            "creativeShotVersionRef": "creative-shot-dialogue-source-v1",
            "creativeShotDigest": "1" * 64,
            "scriptRef": "script-m12",
            "scriptVersionRef": "script-version-m12",
            "scriptVersionDigest": "a" * 64,
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactRef": artifact_ref,
            "storageKey": storage_key,
            "byteSize": command["artifact"]["byteSize"],
            "sha256": file_digest,
            "sampleRate": sample_rate,
            "channels": 1,
            "probe": {
                "sampleRate": sample_rate,
                "channels": 1,
                "durationSeconds": 1.0,
                "durationSamples": sample_count,
                "codec": "pcm_s16le",
                "container": "wav",
            },
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": parameters_digest,
            "synthesisSpecDigest": _digest(
                {"audioRole": "dialogue", "synthesis": "fixture"}
            ),
            "adapterIdentity": "v4.local-audio-contract-fixture.v1",
            "audioRole": "dialogue",
            "provenance": "LOCAL_EVIDENCE",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )
    command["artifact"].update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
        }
    )
    command["provenance"] = build_audio_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "adapterIdentity": evidence["adapterIdentity"],
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
    command.update(
        {
            "speechRole": "dialogue",
            "scriptVersionRef": "script-version-m12",
            "scriptVersionDigest": "a" * 64,
            "dialogueRef": "dialogue-line-source-m12",
            "narrationRef": None,
            "voiceAssetVersionRef": voice_asset["assetVersionRef"],
            "voiceAssetVersionDigest": voice_asset["payloadDigest"],
            "language": "zh-CN",
            "normalizedSpeechParameters": speech_parameters(
                confirmed_lock, "dialogue"
            ),
            "sourceAudioCueRefs": [],
        }
    )
    asset = build_dialogue_asset_version(
        command,
        confirmed_voice_lock=confirmed_lock,
        voice_asset_version=voice_asset,
    )
    contract = validate_dialogue_asset_version(
        asset,
        confirmed_voice_lock=confirmed_lock,
        voice_asset_version=voice_asset,
    )
    return {
        "asset": asset,
        "assetContract": contract,
        "v4Evidence": evidence,
    }


def upstream_payloads(
    *,
    media_kind: str = "AUDIO",
    admitted: bool = True,
    validation_state: str = "PASSED",
    validation_file_digest: str | None = None,
    transcript_text_digest: str = "3" * 64,
    provenance_generation_engine: str | None = None,
    classification_voice_clone: bool = False,
    classification_state: str = "DETERMINATE",
    omit_classification: bool = False,
    asset_extra: dict | None = None,
    artifact_extra: dict | None = None,
) -> list[EvidenceRecord]:
    """Representative canonical human-source authority fixture.

    The marker is test-helper metadata only.  Every production payload uses
    AUTHORITY_EVIDENCE and the existing canonical AssetVersion/evidence journal.
    """

    file_digest = "2" * 64
    pcm_digest = "3" * 64
    artifact_evidence_ref = "artifact-evidence-human-source-1"
    artifact_evidence_digest = "a" * 64
    requirement = sealed(
        {
            "schemaVersion": "v5.m12-human-source-recording-requirement.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "productionRunRef": RUN,
            "requirementRef": "source-recording-requirement-1",
            "subjectRef": SUBJECT,
            "mediaKind": "AUDIO",
            "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
            "speechSynthesis": False,
            "voiceClone": False,
            "syntheticSpeech": False,
            "publicationAllowed": False,
        }
    )
    imported = sealed(
        {
            "schemaVersion": "v5.m12-source-recording-import-evidence.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "productionRunRef": RUN,
            "importEvidenceRef": "source-recording-import-evidence-1",
            "subjectRef": SUBJECT,
            "mediaKind": "AUDIO",
            "captureMethod": "HUMAN_RECORDED_IMPORT",
            "originalFileDigest": "1" * 64,
            "canonicalArtifactFileDigest": file_digest,
            "canonicalPcmContentDigest": pcm_digest,
            "classificationEvidenceKind": "AUTHORITY_EVIDENCE",
            "publicationAllowed": False,
        }
    )
    provenance = sealed(
        {
            "schemaVersion": "v5.m12-source-recording-provenance.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "productionRunRef": RUN,
            "provenanceRef": "source-recording-provenance-1",
            "subjectRef": SUBJECT,
            "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
            "importEvidenceRef": imported["importEvidenceRef"],
            "importEvidenceDigest": imported["payloadDigest"],
            "requirementRef": requirement["requirementRef"],
            "requirementDigest": requirement["payloadDigest"],
            "generationEngine": provenance_generation_engine,
            "commercialProvider": False,
            "classificationEvidenceKind": "AUTHORITY_EVIDENCE",
            "publicationAllowed": False,
        }
    )
    asset_payload = {
            "schemaVersion": "v5.k2-human-source-audio-asset-version.v1",
            "assetVersionType": "SourceRecordingCanonicalAssetVersion",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "assetRef": "audio-asset-human-source-1",
            "assetVersionRef": "audio-asset-human-source-version-1",
            "version": 1,
            "mediaKind": media_kind,
            "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
            "speechSynthesis": False,
            "voiceClone": False,
            "syntheticSpeech": False,
            "sourceRequirementRef": requirement["requirementRef"],
            "sourceRequirementDigest": requirement["payloadDigest"],
            "sourceImportEvidenceRef": imported["importEvidenceRef"],
            "sourceImportEvidenceDigest": imported["payloadDigest"],
            "sourceProvenanceRef": provenance["provenanceRef"],
            "sourceProvenanceDigest": provenance["payloadDigest"],
            "artifact": {
                "artifactEvidenceRef": artifact_evidence_ref,
                "artifactEvidenceDigest": artifact_evidence_digest,
                "artifactRef": "audio-artifact-human-source-1",
                "storageKey": "asset-versions/audio/human-source-1.wav",
                "byteSize": 96_044,
                "fileDigest": file_digest,
            },
            "immutable": True,
            "publicationAllowed": False,
            "createdAt": CREATED_AT,
        }
    if artifact_extra:
        asset_payload["artifact"].update(deepcopy(artifact_extra))
    if asset_extra:
        asset_payload.update(deepcopy(asset_extra))
    asset = sealed(asset_payload)
    classification = sealed(
        {
            "schemaVersion": "v5.m12-source-recording-classification.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "productionRunRef": RUN,
            "sourceKindEvidenceRef": "source-recording-classification-1",
            "subjectRef": SUBJECT,
            "canonicalAssetVersionRef": asset["assetVersionRef"],
            "canonicalAssetVersionDigest": asset["payloadDigest"],
            "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
            "speechSynthesis": False,
            "voiceClone": classification_voice_clone,
            "syntheticSpeech": False,
            "classificationState": classification_state,
            "provenanceRef": provenance["provenanceRef"],
            "provenanceDigest": provenance["payloadDigest"],
            "requirementRef": requirement["requirementRef"],
            "requirementDigest": requirement["payloadDigest"],
            "importEvidenceRef": imported["importEvidenceRef"],
            "importEvidenceDigest": imported["payloadDigest"],
            "classificationEvidenceKind": "AUTHORITY_EVIDENCE",
            "publicationAllowed": False,
        }
    )
    source_timing = sealed(
        {
            "schemaVersion": "v5.audio-source-timing-evidence-projection.v1",
            "sourceAssetVersionRef": asset["assetVersionRef"],
            "sourceAssetVersionDigest": asset["payloadDigest"],
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactEvidenceDigest": artifact_evidence_digest,
            "storageKey": asset["artifact"]["storageKey"],
            "fileDigest": file_digest,
            "sampleRate": 48_000,
            "channelCount": 1,
            "sampleCount": 48_000,
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        }
    )
    failed = validation_state != "PASSED"
    validation = sealed(
        {
            "schemaVersion": "v5.audio-technical-validation.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "validationRef": "audio-validation-human-source-1",
            "validationVersionRef": "audio-validation-human-source-1-v1",
            "version": 1,
            "supersedesValidationVersionRef": None,
            "supersedesValidationVersionDigest": None,
            "sourceAssetVersionType": "SourceRecordingCanonicalAssetVersion",
            "sourceAssetVersionRef": asset["assetVersionRef"],
            "sourceAssetVersionDigest": asset["payloadDigest"],
            "sourceArtifactEvidenceRef": artifact_evidence_ref,
            "sourceArtifactEvidenceDigest": artifact_evidence_digest,
            "artifactRef": asset["artifact"]["artifactRef"],
            "storageKey": asset["artifact"]["storageKey"],
            "byteSize": asset["artifact"]["byteSize"],
            "analysisEvidenceRef": "audio-analysis-human-source-1",
            "analysisEvidenceDigest": "b" * 64,
            "sourceTimingEvidence": source_timing,
            "audioCueBindings": [],
            "codec": "pcm_s16le",
            "container": "wav",
            "sampleRate": 48_000,
            "channelCount": 1,
            "channelLayout": "mono",
            "sampleCount": 48_000,
            "duration": {"numerator": 1, "denominator": 1, "unit": "SECONDS"},
            "integratedLufs": "-24.000",
            "loudnessRangeLra": "0.000",
            "truePeakDbtp": "-18.000",
            "maxSamplePeak": 32_767 if failed else 4_000,
            "silenceRanges": [],
            "clippedSampleCount": 1 if failed else 0,
            "clippingThreshold": deepcopy(PCM_CLIPPING_THRESHOLD),
            "clippingDetected": failed,
            "dcOffset": "0.000000000",
            "fileDigest": file_digest,
            "pcmContentDigest": pcm_digest,
            "pcmDigestSpec": deepcopy(PCM_CONTENT_DIGEST_SPEC),
            "analysisParametersDigest": AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST,
            "validationState": validation_state,
            "failureReasons": ["CLIPPING_THRESHOLD_EXCEEDED"] if failed else [],
            "validatorIdentity": AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
            "validatorVersion": AUDIO_TECHNICAL_VALIDATOR_VERSION,
            "state": "RECORDED",
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": "v5.m12.audio-technical-validator.v1",
            "createdAt": CREATED_AT,
        }
    )
    if validation_file_digest is not None:
        # Deliberate tamper: keep the builder's nested timing evidence intact
        # so the persisted authority validator detects the disagreement.
        validation = deepcopy(validation)
        validation["fileDigest"] = validation_file_digest
        validation = sealed(validation)
    transcript = sealed(
        {
            "schemaVersion": SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION,
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "productionRunRef": RUN,
            "transcriptVersionRef": "transcript-version-source-1",
            "sourceAssetVersionRef": asset["assetVersionRef"],
            "sourceAssetVersionDigest": asset["payloadDigest"],
            "transcriptLanguage": "zh-CN",
            "transcriptTextDigest": transcript_text_digest,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    rights = rights_binding(
        asset_version_ref=asset["assetVersionRef"],
        asset_version_digest=asset["payloadDigest"],
        source_evidence=[
            {"sourceRef": requirement["requirementRef"], "sourceDigest": requirement["payloadDigest"]},
            {"sourceRef": imported["importEvidenceRef"], "sourceDigest": imported["payloadDigest"]},
            {"sourceRef": provenance["provenanceRef"], "sourceDigest": provenance["payloadDigest"]},
            {"sourceRef": classification["sourceKindEvidenceRef"], "sourceDigest": classification["payloadDigest"]},
        ],
    )
    records = [
        evidence_record("SourceRecordingRequirement", requirement["requirementRef"], requirement),
        evidence_record("SourceRecordingImportEvidence", imported["importEvidenceRef"], imported),
        evidence_record("SourceRecordingProvenance", provenance["provenanceRef"], provenance),
        evidence_record("AssetVersion", asset["assetVersionRef"], asset),
        evidence_record(
            "AudioTechnicalValidation",
            validation["validationVersionRef"],
            validation,
        ),
        evidence_record(
            "TranscriptVersion", transcript["transcriptVersionRef"], transcript
        ),
        evidence_record("RightsBinding", rights["rightsBindingRef"], rights),
    ]
    if not omit_classification:
        records.insert(
            4,
            evidence_record(
                "SourceRecordingClassification",
                classification["sourceKindEvidenceRef"],
                classification,
            ),
        )
    if admitted:
        admission = sealed(
            {
                "schemaVersion": "v5.k2-asset-admission.v1",
                "admissionRef": "asset-admission-source-1",
                "version": 1,
                "ordinal": 1,
                "candidateRef": "asset-candidate-dialogue-source-1",
                "candidateDigest": "4" * 64,
                "selectionRef": "asset-selection-dialogue-source-1",
                "selectionVersion": 1,
                "selectionDigest": "5" * 64,
                "assetVersionRef": asset["assetVersionRef"],
                "assetVersionDigest": asset["payloadDigest"],
                "admissionState": "ADMITTED",
                "publicationAllowed": False,
                "createdAt": CREATED_AT,
            }
        )
        records.append(
            evidence_record("AssetAdmission", admission["admissionRef"], admission)
        )
    return records


def seed_upstreams(repository, **changes) -> dict[str, dict]:
    records = upstream_payloads(**changes)
    repository.append_records(records)
    return {record.recordKind: deepcopy(dict(record.payload)) for record in records}


def source_command(upstreams: dict[str, dict], *, key: str = "source-create") -> dict:
    asset = upstreams["AssetVersion"]
    validation = upstreams["AudioTechnicalValidation"]
    transcript = upstreams["TranscriptVersion"]
    rights = upstreams["RightsBinding"]
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "subjectRef": SUBJECT,
        "canonicalAssetVersionRef": asset["assetVersionRef"],
        "canonicalAssetVersionNumber": asset["version"],
        "canonicalAssetVersionDigest": asset["payloadDigest"],
        "audioTechnicalValidationRef": validation[
            "validationVersionRef"
        ],
        "audioTechnicalValidationDigest": validation["payloadDigest"],
        "transcriptVersionRef": transcript["transcriptVersionRef"],
        "transcriptVersionDigest": transcript["payloadDigest"],
        "sourceRightsBindingRef": rights["rightsBindingRef"],
        "sourceRightsBindingDigest": rights["payloadDigest"],
        "createdBy": "v5.m12-c1.integration-test",
    }


def consent_command(binding: dict, *, key: str = "consent-create") -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "sourceRecordingBindingRef": binding["sourceRecordingBindingRef"],
        "sourceRecordingBindingDigest": binding["payloadDigest"],
        "subjectRef": SUBJECT,
        "grantorRef": "grantor-lin",
        "rightsBindingRef": binding["sourceRightsBindingRef"],
        "rightsBindingDigest": binding["sourceRightsBindingDigest"],
        "allowedUses": sorted(
            ["VOICE_CLONING", "VOICE_PROFILE_USE", "AUDIO_PRODUCTION"]
        ),
        "prohibitedUses": [],
        "territories": ["WORLDWIDE"],
        "validFrom": "2026-08-30T08:00:00Z",
        "expiresAt": "2027-08-30T08:00:00Z",
        "evidenceRef": "consent-evidence-1",
        "evidenceDigest": "9" * 64,
        "createdBy": "v5.m12-c1.integration-test",
    }


def confirmed_fixed_voice(service) -> dict:
    owner = service.voice_locks
    created = owner.create_voice_lock(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "characterRef": SUBJECT,
            "idempotencyKey": "fixed-voice-create",
            "engineFamily": "v4.local-fixed-voice.v1",
            "voiceId": "fixed-voice-identity-lin",
            "gender": "female",
            "apparentAge": 28,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "stable-low-register",
            "languageCode": "zh-CN",
        }
    )
    return owner.confirm_voice_lock(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "voiceRef": created["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": created["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
            "voiceLockDigest": created["voiceLockVersion"]["payloadDigest"],
            "expectedRevision": created["voiceLock"]["revision"],
            "idempotencyKey": "fixed-voice-confirm",
        }
    )


def clone_lock_command(
    binding: dict,
    consent: dict,
    fixed_voice: dict,
    *,
    key: str = "clone-lock-create",
) -> dict:
    fixed_root = fixed_voice["voiceLock"]
    fixed_version = fixed_voice["voiceLockVersion"]
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "voiceRef": fixed_root["voiceRef"],
        "baseVoiceLockVersionRef": fixed_version["voiceLockVersionRef"],
        "baseVoiceLockDigest": fixed_version["payloadDigest"],
        "expectedRevision": fixed_root["revision"],
        "subjectRef": SUBJECT,
        "sourceRecordingBindingRef": binding["sourceRecordingBindingRef"],
        "sourceRecordingBindingDigest": binding["payloadDigest"],
        "consentGrantVersionRef": consent["consentGrantVersionRef"],
        "consentGrantVersionDigest": consent["payloadDigest"],
        "rightsBindingRef": binding["sourceRightsBindingRef"],
        "rightsBindingDigest": binding["sourceRightsBindingDigest"],
        "voiceIdentityRef": fixed_root["voiceRef"],
        "voiceIdentityVersionRef": fixed_version["voiceLockVersionRef"],
        "voiceIdentityDigest": fixed_version["payloadDigest"],
        "engineFamily": ENGINE_ID,
        "voiceId": MODEL_ID,
        "gender": "female",
        "apparentAge": 28,
        "pitchSemitones": 0.0,
        "rateScale": 1.0,
        "timbreDescriptor": "stable-low-register",
        "languageCode": "zh-CN",
    }


def confirm_lock_command(lock: dict, *, key: str = "clone-lock-confirm") -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "voiceRef": lock["voiceLock"]["voiceRef"],
        "voiceLockVersionRef": lock["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockVersionDigest": lock["voiceLockVersion"]["payloadDigest"],
        "expectedRevision": lock["voiceLock"]["revision"],
    }


def synthetic_profile_package() -> dict:
    return {
        "storageBindingRef": "voice-profile-storage-binding-1",
        "byteSize": 4096,
        "fileDigest": "b" * 64,
        "contentDigest": "c" * 64,
        "packageFormat": "VOICE_PROFILE_PACKAGE",
        "packageSchemaVersion": "voice-profile-package.v1",
        "technicalValidationRef": "voice-profile-technical-validation-1",
        "technicalValidationDigest": "a" * 64,
    }


def seed_profile_test_fixture(repository) -> dict:
    """Seed explicitly marked non-production evidence; builders must reject it."""

    value = build_voice_profile_test_fixture(
        {
            "fixtureRef": "voice-profile-technical-validation-1",
            "profilePackage": synthetic_profile_package(),
        }
    )
    repository.append_record(
        evidence_record(
            "VoiceProfileTechnicalValidation",
            value["fixtureRef"],
            value,
        )
    )
    package = deepcopy(value["profilePackage"])
    package["technicalValidationDigest"] = value["payloadDigest"]
    return {
        **package,
        "payloadDigest": value["payloadDigest"],
    }


def seed_historical_voice_profile(
    repository,
    lineage: dict,
    *,
    status: str = "CONFIRMED",
) -> dict:
    """Journal-only historical setup; never represents runtime generation."""

    lock = lineage["confirmedLock"]
    root = validate_voice_profile(
        sealed(
            {
                "schemaVersion": VOICE_PROFILE_SCHEMA_VERSION,
                "voiceProfileRef": "voice-profile-historical-1",
                "workspaceRef": WORKSPACE,
                "projectRef": PROJECT,
                "seriesRef": SERIES,
                "subjectRef": SUBJECT,
                "createdAt": CREATED_AT,
            }
        )
    ).as_dict()
    package = synthetic_profile_package()
    immutable = {
        "schemaVersion": VOICE_PROFILE_VERSION_SCHEMA_VERSION,
        "voiceProfileRef": root["voiceProfileRef"],
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "subjectRef": SUBJECT,
        "voiceIdentityRef": lock["voiceLockVersion"]["voiceIdentityRef"],
        "voiceIdentityVersionRef": lock["voiceLockVersion"][
            "voiceIdentityVersionRef"
        ],
        "voiceIdentityDigest": lock["voiceLockVersion"]["voiceIdentityDigest"],
        "voiceLockRef": lock["voiceLock"]["voiceRef"],
        "voiceLockVersionRef": lock["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockVersionDigest": lock["voiceLockVersion"]["payloadDigest"],
        "voiceLockConfirmationRef": lock["voiceLockConfirmation"][
            "voiceLockConfirmationRef"
        ],
        "voiceLockConfirmationDigest": lock["voiceLockConfirmation"][
            "payloadDigest"
        ],
        "sourceRecordingBindingRef": lineage["binding"][
            "sourceRecordingBindingRef"
        ],
        "sourceRecordingBindingDigest": lineage["binding"]["payloadDigest"],
        "consentGrantVersionRef": lineage["consent"]["consentGrantVersionRef"],
        "consentGrantVersionDigest": lineage["consent"]["payloadDigest"],
        "rightsBindingRef": lineage["binding"]["sourceRightsBindingRef"],
        "rightsBindingDigest": lineage["binding"]["sourceRightsBindingDigest"],
        "engineId": ENGINE_ID,
        "engineCommit": ENGINE_COMMIT,
        "modelId": MODEL_ID,
        "modelBundleDigest": MODEL_BUNDLE_DIGEST,
        "dependencyLockDigest": "e" * 64,
        "runtimeManifestDigest": "f" * 64,
        "profilePackage": package,
        "createdAt": CREATED_AT,
        "createdBy": "TEST_HISTORICAL_JOURNAL_SETUP_ONLY",
    }

    versions: list[dict] = []
    candidate = validate_voice_profile_version(
        sealed(
            {
                **immutable,
                "voiceProfileVersionRef": "voice-profile-historical-1-v1",
                "versionNumber": 1,
                "parentVoiceProfileVersionRef": None,
                "parentVoiceProfileVersionDigest": None,
                "status": "CANDIDATE",
                "confirmedAt": None,
            }
        )
    ).as_dict()
    versions.append(candidate)
    if status in {"CONFIRMED", "REVOKED"}:
        confirmed = validate_voice_profile_version(
            sealed(
                {
                    **immutable,
                    "voiceProfileVersionRef": "voice-profile-historical-1-v2",
                    "versionNumber": 2,
                    "parentVoiceProfileVersionRef": candidate[
                        "voiceProfileVersionRef"
                    ],
                    "parentVoiceProfileVersionDigest": candidate["payloadDigest"],
                    "status": "CONFIRMED",
                    "confirmedAt": CREATED_AT,
                }
            )
        ).as_dict()
        versions.append(confirmed)
    if status == "REVOKED":
        parent = versions[-1]
        revoked = validate_voice_profile_version(
            sealed(
                {
                    **immutable,
                    "voiceProfileVersionRef": "voice-profile-historical-1-v3",
                    "versionNumber": 3,
                    "parentVoiceProfileVersionRef": parent[
                        "voiceProfileVersionRef"
                    ],
                    "parentVoiceProfileVersionDigest": parent["payloadDigest"],
                    "status": "REVOKED",
                    "confirmedAt": CREATED_AT,
                }
            )
        ).as_dict()
        versions.append(revoked)
    if status not in {"CANDIDATE", "CONFIRMED", "REVOKED"}:
        raise AssertionError("unsupported historical profile fixture status")

    repository.append_records(
        (
            evidence_record("VoiceProfile", root["voiceProfileRef"], root),
            *(
                evidence_record(
                    "VoiceProfileVersion",
                    version["voiceProfileVersionRef"],
                    version,
                    version=version["versionNumber"],
                )
                for version in versions
            ),
        )
    )
    return {
        "voiceProfile": root,
        "voiceProfileVersion": versions[-1],
        "voiceProfileVersions": versions,
    }


def profile_command(
    confirmed_lock: dict,
    technical: dict,
    *,
    key: str = "voice-profile-create",
) -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "voiceRef": confirmed_lock["voiceLock"]["voiceRef"],
        "voiceLockVersionRef": confirmed_lock["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockVersionDigest": confirmed_lock["voiceLockVersion"][
            "payloadDigest"
        ],
        "voiceLockConfirmationRef": confirmed_lock["voiceLockConfirmation"][
            "voiceLockConfirmationRef"
        ],
        "voiceLockConfirmationDigest": confirmed_lock[
            "voiceLockConfirmation"
        ]["payloadDigest"],
        "engineId": ENGINE_ID,
        "engineCommit": ENGINE_COMMIT,
        "modelId": MODEL_ID,
        "modelBundleDigest": MODEL_BUNDLE_DIGEST,
        "dependencyLockDigest": "e" * 64,
        "runtimeManifestDigest": "f" * 64,
        "profilePackage": {
            "storageBindingRef": technical["storageBindingRef"],
            "byteSize": technical["byteSize"],
            "fileDigest": technical["fileDigest"],
            "contentDigest": technical["contentDigest"],
            "packageFormat": technical["packageFormat"],
            "packageSchemaVersion": technical["packageSchemaVersion"],
            "technicalValidationRef": technical[
                "technicalValidationRef"
            ],
            "technicalValidationDigest": technical["payloadDigest"],
        },
        "createdBy": "v5.m12-c1.integration-test",
    }


def profile_successor_command(
    version: dict,
    *,
    status: str,
    key: str,
) -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "idempotencyKey": key,
        "voiceProfileRef": version["voiceProfileRef"],
        "baseVoiceProfileVersionRef": version["voiceProfileVersionRef"],
        "baseVoiceProfileVersionDigest": version["payloadDigest"],
        "status": status,
        "createdBy": "v5.m12-c1.integration-test",
    }


def create_lineage_to_confirmed_lock(service, repository) -> dict:
    upstreams = seed_upstreams(repository)
    binding = service.create_source_recording_binding(
        source_command(upstreams)
    )["sourceVoiceRecordingAssetVersionBinding"]
    consent = service.create_consent_grant(consent_command(binding))[
        "consentGrantVersion"
    ]
    fixed_voice = confirmed_fixed_voice(service)
    candidate = service.create_clone_voice_lock(
        clone_lock_command(binding, consent, fixed_voice)
    )
    confirmed = service.confirm_clone_voice_lock(confirm_lock_command(candidate))
    return {
        "upstreams": upstreams,
        "binding": binding,
        "consent": consent,
        "fixedVoice": fixed_voice,
        "candidateLock": candidate,
        "confirmedLock": confirmed,
    }


def build_historical_clone_dialogue_chain(service, repository) -> dict:
    """Build sealed historical v2 mappings without production authority.

    C1 has no real voice-clone runtime evidence, so this fixture deliberately
    exercises only the public read validators.  Production builders are tested
    separately to reject these mappings without a service-issued current proof.
    """

    lineage = create_lineage_to_confirmed_lock(service, repository)
    historical = seed_historical_voice_profile(repository, lineage)
    profile = validate_voice_profile_version(
        historical["voiceProfileVersion"]
    )
    source = validate_source_voice_recording_binding(lineage["binding"])
    consent = validate_consent_grant_version_v2(lineage["consent"])
    rights = lineage["upstreams"]["RightsBinding"]
    self_contained = {
        "rights": rights,
        "source": source,
        "consent": consent,
        "lock": lineage["confirmedLock"],
        "profile": profile,
    }
    voice_command = clone_voice_asset_command(self_contained)
    voice_command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": "episode-m12-c1-sqlite",
            "productionRunRef": RUN,
        }
    )
    voice_mapping = sealed(
        {
            "schemaVersion": VOICE_ASSET_VERSION_V2_SCHEMA_VERSION,
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
        voice_mapping,
        voice_profile_version=profile,
        confirmed_voice_lock=lineage["confirmedLock"],
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=CREATED_AT,
        require_current_authority=False,
    )
    request_command = clone_dialogue_request_command(
        voice_mapping, lineage["confirmedLock"], rights
    )
    request_command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": "episode-m12-c1-sqlite",
            "productionRunRef": RUN,
        }
    )
    request_mapping = sealed(
        {
            "schemaVersion": AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
            **request_command,
            "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    request = AudioGenerationRequest.from_mapping(
        request_mapping,
        confirmed_voice_lock=lineage["confirmedLock"],
        voice_asset_version=voice,
        voice_profile_version=profile,
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=CREATED_AT,
        require_current_authority=False,
    )
    evidence = pre_asset_generation_evidence(
        generation_request_digest=request_mapping["payloadDigest"],
        parameters_digest=request_mapping["requestedProvenance"][
            "parametersDigest"
        ],
        workspace_ref=WORKSPACE,
        production_run_ref=RUN,
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
    artifact = evidence["artifactEvidence"]
    request_spec = request_mapping["requestSpec"]
    dialogue_command = common_asset_command("dialogue", rights=rights)
    dialogue_command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": "episode-m12-c1-sqlite",
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
                "artifactEvidenceRef": artifact["artifactEvidenceRef"],
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "artifactRef": artifact["artifactRef"],
                "storageKey": artifact["storageKey"],
                "byteSize": artifact["byteSize"],
                "fileDigest": artifact["sha256"],
                "mediaType": "audio/wav",
            },
            "provenance": build_audio_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "adapterIdentity": artifact["adapterIdentity"],
                    "generationRecordRef": generation[
                        "generationResultRef"
                    ],
                    "parametersDigest": artifact["parametersDigest"],
                    "artifactEvidenceRef": artifact["artifactEvidenceRef"],
                    "artifactEvidenceDigest": artifact["payloadDigest"],
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
    dialogue = sealed(
        {
            "schemaVersion": DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION,
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
    validate_clone_dialogue_asset_version(
        dialogue,
        voice_asset_version=voice,
        audio_generation_request=request,
        generation_result=generation,
        artifact_evidence=artifact,
        audio_technical_validation=technical,
        confirmed_voice_lock=lineage["confirmedLock"],
        voice_profile_version=profile,
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=CREATED_AT,
    )
    return {
        **lineage,
        "profile": profile,
        "source": source,
        "consent": consent,
        "rights": rights,
        "voice": voice,
        "voiceMapping": voice_mapping,
        "voiceCommand": voice_command,
        "request": request,
        "requestMapping": request_mapping,
        "requestCommand": request_command,
        "evidence": evidence,
        "technical": technical,
        "technicalMapping": technical_mapping,
        "dialogueCommand": dialogue_command,
        "dialogue": dialogue,
    }


def consent_successor_command(
    consent: dict,
    *,
    rights: dict,
    key: str,
    state: str,
    run: str = RUN,
) -> dict:
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run,
        "idempotencyKey": key,
        "consentGrantRef": consent["consentGrantRef"],
        "baseConsentGrantVersionRef": consent["consentGrantVersionRef"],
        "baseConsentGrantVersionDigest": consent["payloadDigest"],
        "allowedUses": deepcopy(consent["allowedUses"]),
        "prohibitedUses": deepcopy(consent["prohibitedUses"]),
        "territories": deepcopy(consent["territories"]),
        "validFrom": consent["validFrom"],
        "expiresAt": consent["expiresAt"],
        "revocationState": state,
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "evidenceRef": f"consent-{state.lower()}-evidence",
        "evidenceDigest": ("a" if state == "ACTIVE" else "b") * 64,
        "createdBy": "v5.m12-c1.integration-test",
    }


class M12VoiceProfileLineageServiceTests(unittest.TestCase):
    def service(self, repository, *, clock=None, refs=None, voice_locks=None):
        selected_clock = clock or (lambda: CREATED_AT)
        selected_refs = refs or Refs()
        if voice_locks is None:
            voice_locks = getattr(repository, "_m12_voice_locks", None)
        if voice_locks is None:
            voice_locks = K2VoiceLockService(
                InMemoryVoiceLockAdapter(),
                ref_factory=selected_refs,
                clock=selected_clock,
            )
            setattr(repository, "_m12_voice_locks", voice_locks)
        return K2VoiceProfileLineageService(
            RootService(),
            repository,
            voice_locks=voice_locks,
            ref_factory=selected_refs,
            clock=selected_clock,
        )

    def test_source_binding_resolves_one_admitted_audio_asset_and_upstreams(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        result = self.service(repository).create_source_recording_binding(
            source_command(upstreams)
        )
        binding = result["sourceVoiceRecordingAssetVersionBinding"]
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(
            binding["canonicalAssetVersionDigest"],
            upstreams["AssetVersion"]["payloadDigest"],
        )
        self.assertEqual(
            binding["audioFileDigest"],
            upstreams["AssetVersion"]["artifact"]["fileDigest"],
        )
        self.assertEqual(
            binding["audioPcmContentDigest"],
            upstreams["AudioTechnicalValidation"]["pcmContentDigest"],
        )
        self.assertEqual(binding["transcriptTextDigest"], "3" * 64)
        self.assertEqual(
            upstreams["AssetVersion"]["artifact"]["storageKey"],
            "asset-versions/audio/human-source-1.wav",
        )
        self.assertNotIn("storageKey", binding)
        self.assertNotIn("consentGrantVersionRef", binding)

    def test_source_binding_rejects_generated_clone_and_indeterminate_evidence(self):
        cases = (
            ("piper-provenance", {"provenance_generation_engine": "Piper"}),
            (
                "voice-clone-provenance",
                {"provenance_generation_engine": "VOICE_CLONE"},
            ),
            ("voice-clone-classification", {"classification_voice_clone": True}),
            ("classification-missing", {"omit_classification": True}),
            ("classification-indeterminate", {"classification_state": "INDETERMINATE"}),
            (
                "canonical-speech-synthesis",
                {"asset_extra": {"speechSynthesis": True}},
            ),
            (
                "canonical-dialogue-schema",
                {
                    "asset_extra": {
                        "schemaVersion": "v5.m12-dialogue-asset-version.v2"
                    }
                },
            ),
            (
                "canonical-dialogue-type",
                {"asset_extra": {"assetVersionType": "DialogueAssetVersion"}},
            ),
        )
        for name, changes in cases:
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository, **changes)
            with self.subTest(case=name), self.assertRaises(
                EpisodeProductionError
            ):
                self.service(repository).create_source_recording_binding(
                    source_command(upstreams, key=f"source-{name}")
                )

    def test_source_binding_rejects_paths_urls_and_legacy_media_refs(self):
        cases = (
            ("absolute-path", {"asset_extra": {"absolutePath": "/tmp/source.wav"}}),
            (
                "artifact-url",
                {"artifact_extra": {"url": "https://example.invalid/source.wav"}},
            ),
            (
                "artifact-legacy-media",
                {"artifact_extra": {"legacyMediaRef": "legacy-media-source-1"}},
            ),
        )
        for name, changes in cases:
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository, **changes)
            with self.subTest(case=name), self.assertRaises(
                EpisodeProductionError
            ):
                self.service(repository).create_source_recording_binding(
                    source_command(upstreams, key=f"source-{name}")
                )

    def test_source_binding_composite_cas_rejects_second_admission_gate(self):
        repository = InterveningAdmissionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        repository.inject_on_source_append = True

        with self.assertRaises(StaleInputError):
            self.service(repository).create_source_recording_binding(
                source_command(upstreams)
            )

        self.assertEqual(
            repository.list_records(
                WORKSPACE,
                RUN,
                record_kind="SourceVoiceRecordingAssetVersionBinding",
            ),
            [],
        )
        self.assertIsNotNone(
            repository.get_gate(WORKSPACE, RUN, "SECOND_ASSET_ADMISSION")
        )

    def test_source_binding_rejects_nonadmitted_nonaudio_and_foreign_scope(self):
        cases = (
            ("not-admitted", {"admitted": False}, VoiceProfileLineageNotEffectiveError),
            ("not-audio", {"media_kind": "VIDEO"}, VoiceProfileLineageNotEffectiveError),
        )
        for name, changes, exception in cases:
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository, **changes)
            with self.subTest(name=name), self.assertRaises(exception):
                self.service(repository).create_source_recording_binding(
                    source_command(upstreams)
                )

        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        command = source_command(upstreams)
        command["workspaceRef"] = "workspace-m12-c1-foreign"
        with self.assertRaises(VoiceProfileLineageNotFoundError):
            self.service(repository).create_source_recording_binding(command)

    def test_source_binding_rejects_same_ref_authority_digest_collisions(self):
        cases = (
            (
                "asset-admission",
                "AssetAdmission",
                "admissionRef",
                "asset-admission-source-collision",
                "assetVersionDigest",
            ),
            (
                "source-classification",
                "SourceRecordingClassification",
                "sourceKindEvidenceRef",
                "source-recording-classification-collision",
                "canonicalAssetVersionDigest",
            ),
        )
        for name, kind, ref_field, conflicting_ref, digest_field in cases:
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository)
            conflicting = deepcopy(upstreams[kind])
            conflicting[ref_field] = conflicting_ref
            conflicting[digest_field] = "0" * 64
            conflicting = sealed(conflicting)
            repository.append_records(
                [evidence_record(kind, conflicting_ref, conflicting)]
            )

            with self.subTest(case=name), self.assertRaises(
                VoiceProfileLineageStaleError
            ):
                self.service(repository).create_source_recording_binding(
                    source_command(upstreams, key=f"source-{name}-collision")
                )

    def test_source_binding_rejects_file_validation_and_transcript_drift(self):
        cases = (
            (
                "file",
                {"validation_file_digest": "4" * 64},
                None,
            ),
            (
                "validation-failed",
                {"validation_state": "FAILED"},
                None,
            ),
            ("transcript", {}, "transcriptVersionDigest"),
        )
        for name, changes, command_field in cases:
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository, **changes)
            command = source_command(upstreams, key=f"source-{name}")
            if command_field is not None:
                command[command_field] = "0" * 64
            with self.subTest(name=name), self.assertRaises(
                (VoiceProfileLineageStaleError, VoiceProfileLineageNotEffectiveError)
            ):
                self.service(repository).create_source_recording_binding(command)

        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        command = source_command(upstreams, key="source-canonical-digest-drift")
        command["canonicalAssetVersionDigest"] = "0" * 64
        with self.assertRaises(
            (VoiceProfileLineageStaleError, VoiceProfileLineageNotFoundError)
        ):
            self.service(repository).create_source_recording_binding(command)

    def test_source_binding_command_rejects_descendants_paths_and_full_asset_mapping(self):
        for forbidden, value in (
            ("consentGrantVersionRef", "consent-version-forged"),
            ("storageKey", "asset-versions/audio/source.wav"),
            ("absolutePath", "/tmp/source.wav"),
            ("sourceAssetVersion", {"assetVersionRef": "forged"}),
        ):
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository)
            command = source_command(upstreams, key=f"source-{forbidden}")
            command[forbidden] = value
            with self.subTest(forbidden=forbidden), self.assertRaises(
                VoiceProfileLineageError
            ):
                self.service(repository).create_source_recording_binding(command)

    def test_consent_requires_existing_source_all_uses_subject_and_rights(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        service = self.service(repository)
        missing = consent_command(
            {
                "sourceRecordingBindingRef": "missing-source",
                "payloadDigest": "0" * 64,
                "sourceRightsBindingRef": upstreams["RightsBinding"][
                    "rightsBindingRef"
                ],
                "sourceRightsBindingDigest": upstreams["RightsBinding"][
                    "payloadDigest"
                ],
            },
            key="consent-before-source",
        )
        with self.assertRaises(VoiceProfileLineageNotFoundError):
            service.create_consent_grant(missing)

        binding = service.create_source_recording_binding(
            source_command(upstreams)
        )["sourceVoiceRecordingAssetVersionBinding"]
        base = consent_command(binding)
        mutations = {
            "missing-use": lambda value: value["allowedUses"].remove(
                "VOICE_CLONING"
            ),
            "subject": lambda value: value.__setitem__(
                "subjectRef", "character-other"
            ),
            "rights": lambda value: value.__setitem__(
                "rightsBindingDigest", "0" * 64
            ),
        }
        for name, mutate in mutations.items():
            invalid = deepcopy(base)
            invalid["idempotencyKey"] = f"consent-{name}"
            mutate(invalid)
            with self.subTest(name=name), self.assertRaises(
                EpisodeProductionError
            ):
                service.create_consent_grant(invalid)

    def test_exact_replay_and_changed_replay_conflict_without_legacy_writes(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        service = self.service(repository)
        command = source_command(upstreams)
        first = service.create_source_recording_binding(command)
        replay = service.create_source_recording_binding(deepcopy(command))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            replay["sourceVoiceRecordingAssetVersionBinding"],
            first["sourceVoiceRecordingAssetVersionBinding"],
        )
        changed = deepcopy(command)
        changed["subjectRef"] = "character-other"
        with self.assertRaises(IdempotencyConflictError):
            service.create_source_recording_binding(changed)

        records = repository.list_records(WORKSPACE, RUN)
        self.assertFalse(
            any(
                item["recordKind"].lower() in {"media", "legacymedia"}
                for item in records
            )
        )
        self.assertFalse(
            any(
                forbidden in item["payload"]
                for item in records
                for forbidden in ("absolutePath", "sourcePath")
            )
        )

    def test_clone_lock_requires_exact_source_consent_and_confirmation(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        upstreams = seed_upstreams(repository)
        service = self.service(repository)
        binding = service.create_source_recording_binding(
            source_command(upstreams)
        )["sourceVoiceRecordingAssetVersionBinding"]
        consent = service.create_consent_grant(consent_command(binding))[
            "consentGrantVersion"
        ]
        fixed_voice = confirmed_fixed_voice(service)
        base = clone_lock_command(binding, consent, fixed_voice)
        for name, field in (
            ("missing-source", "sourceRecordingBindingRef"),
            ("missing-consent", "consentGrantVersionRef"),
        ):
            invalid = deepcopy(base)
            invalid["idempotencyKey"] = name
            invalid[field] = f"{name}-not-found"
            with self.subTest(name=name), self.assertRaises(
                VoiceProfileLineageNotFoundError
            ):
                service.create_clone_voice_lock(invalid)

        candidate = service.create_clone_voice_lock(base)
        technical = {
            **synthetic_profile_package(),
            "payloadDigest": "a" * 64,
        }
        fake_confirmed = {
            **candidate,
            "voiceLockConfirmation": {
                "voiceLockConfirmationRef": "missing-confirmation",
                "payloadDigest": "0" * 64,
            },
        }
        with self.assertRaises(EpisodeProductionError):
            service.create_voice_profile(
                profile_command(fake_confirmed, technical)
            )

        confirmed = service.confirm_clone_voice_lock(
            confirm_lock_command(candidate)
        )
        self.assertEqual(
            confirmed["voiceLockConfirmation"]["voiceLockDigest"],
            confirmed["voiceLockVersion"]["payloadDigest"],
        )

    def test_revoked_or_expired_consent_cannot_authorize_new_clone_lock(self):
        for name, expiry, revoke in (
            ("expired", "2026-08-30T07:59:59Z", False),
            ("revoked", "2027-08-30T08:00:00Z", True),
        ):
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            upstreams = seed_upstreams(repository)
            service = self.service(repository)
            binding = service.create_source_recording_binding(
                source_command(upstreams)
            )["sourceVoiceRecordingAssetVersionBinding"]
            command = consent_command(binding, key=f"consent-{name}")
            if name == "expired":
                command["validFrom"] = "2025-08-30T08:00:00Z"
                command["expiresAt"] = expiry
            first = service.create_consent_grant(command)[
                "consentGrantVersion"
            ]
            selected = first
            fixed_voice = confirmed_fixed_voice(service)
            if revoke:
                successor_rights = consent_successor_rights(
                    binding,
                    first,
                    suffix="revoked",
                    evidence_ref="consent-revoked-evidence",
                    evidence_digest="b" * 64,
                )
                repository.append_record(
                    evidence_record(
                        "RightsBinding",
                        successor_rights["rightsBindingRef"],
                        successor_rights,
                    )
                )
                selected = service.create_consent_grant_successor(
                    consent_successor_command(
                        first,
                        rights=successor_rights,
                        key="consent-revoke",
                        state="REVOKED",
                    )
                )["consentGrantVersion"]
            with self.subTest(name=name), self.assertRaises(
                VoiceProfileLineageNotEffectiveError
            ):
                service.create_clone_voice_lock(
                    clone_lock_command(
                        binding,
                        selected,
                        fixed_voice,
                        key=f"clone-lock-{name}",
                    )
                )

    def test_same_series_cross_run_reads_and_revokes_owner_lineage(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        refs = Refs()
        owner = self.service(repository, refs=refs)
        lineage = create_lineage_to_confirmed_lock(owner, repository)
        consumer = self.service(repository, refs=refs)

        before = consumer.get_voice_profile_lineage(WORKSPACE, SAME_SERIES_RUN)
        self.assertEqual(len(before["sourceVoiceRecordingAssetVersionBindings"]), 1)
        self.assertEqual(
            [item["revocationState"] for item in before["consentGrantVersions"]],
            ["ACTIVE"],
        )

        successor_rights = consent_successor_rights(
            lineage["binding"],
            lineage["consent"],
            suffix="same-series-cross-run-revoked",
            evidence_ref="consent-revoked-evidence",
            evidence_digest="b" * 64,
        )
        repository.append_record(
            evidence_record(
                "RightsBinding",
                successor_rights["rightsBindingRef"],
                successor_rights,
                run=SAME_SERIES_RUN,
            )
        )
        successor = consumer.create_consent_grant_successor(
            consent_successor_command(
                lineage["consent"],
                rights=successor_rights,
                key="consent-cross-run-revoke",
                state="REVOKED",
                run=SAME_SERIES_RUN,
            )
        )["consentGrantVersion"]

        self.assertEqual(successor["versionNumber"], 2)
        owner_records = repository.list_records(
            WORKSPACE, RUN, record_kind="ConsentGrantVersion"
        )
        consumer_records = repository.list_records(
            WORKSPACE, SAME_SERIES_RUN, record_kind="ConsentGrantVersion"
        )
        self.assertEqual(len(owner_records), 2)
        self.assertEqual(consumer_records, [])
        after = owner.get_voice_profile_lineage(WORKSPACE, RUN)
        self.assertEqual(
            [item["revocationState"] for item in after["consentGrantVersions"]],
            ["ACTIVE", "REVOKED"],
        )
        with self.assertRaises(VoiceProfileLineageNotEffectiveError):
            consumer.create_clone_voice_lock(
                {
                    **clone_lock_command(
                        lineage["binding"],
                        successor,
                        lineage["fixedVoice"],
                        key="clone-lock-cross-run-revoked",
                    ),
                    "productionRunRef": SAME_SERIES_RUN,
                    "rightsBindingRef": successor_rights["rightsBindingRef"],
                    "rightsBindingDigest": successor_rights["payloadDigest"],
                }
            )

    def test_consent_successor_requires_new_exact_rights_lineage(self):
        for name in (
            "not-persisted",
            "reuses-parent",
            "missing-source-asset",
            "missing-current-evidence",
            "missing-parent-rights",
            "missing-clone-use",
        ):
            repository = InMemoryEpisodeProductionEvidenceAdapter()
            service = self.service(repository)
            lineage = create_lineage_to_confirmed_lock(service, repository)
            rights = consent_successor_rights(
                lineage["binding"],
                lineage["consent"],
                suffix=name,
                evidence_ref="consent-revoked-evidence",
                evidence_digest="b" * 64,
            )
            if name == "reuses-parent":
                rights = lineage["upstreams"]["RightsBinding"]
            elif name != "not-persisted":
                command = {
                    key: deepcopy(value)
                    for key, value in rights.items()
                    if key
                    not in {"schemaVersion", "authorityState", "payloadDigest"}
                }
                if name == "missing-clone-use":
                    command["usageScope"].remove("VOICE_PROFILE_USE")
                else:
                    omitted = {
                        "missing-source-asset": lineage["binding"][
                            "canonicalAssetVersionRef"
                        ],
                        "missing-current-evidence": "consent-revoked-evidence",
                        "missing-parent-rights": lineage["consent"][
                            "rightsBindingRef"
                        ],
                    }[name]
                    command["sourceRefs"] = [
                        item
                        for item in command["sourceRefs"]
                        if item["sourceRef"] != omitted
                    ]
                rights = build_rights_binding(command)
            if name != "not-persisted":
                repository.append_record(
                    evidence_record(
                        "RightsBinding", rights["rightsBindingRef"], rights
                    )
                )

            with self.subTest(name=name), self.assertRaises(
                (
                    VoiceProfileLineageNotFoundError
                    if name == "not-persisted"
                    else VoiceProfileLineageNotEffectiveError
                )
            ):
                service.create_consent_grant_successor(
                    consent_successor_command(
                        lineage["consent"],
                        rights=rights,
                        key=f"consent-successor-{name}",
                        state="REVOKED",
                    )
                )

    def test_same_series_cross_run_successor_race_has_one_winner(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        refs = ThreadSafeRefs()
        owner = self.service(repository, refs=refs)
        lineage = create_lineage_to_confirmed_lock(owner, repository)
        other = self.service(repository, refs=refs)
        candidates = []
        for suffix, run, digit in (
            ("owner-race", RUN, "b"),
            ("other-run-race", SAME_SERIES_RUN, "c"),
        ):
            evidence_ref = f"consent-{suffix}-evidence"
            evidence_digest = digit * 64
            rights = consent_successor_rights(
                lineage["binding"],
                lineage["consent"],
                suffix=suffix,
                evidence_ref=evidence_ref,
                evidence_digest=evidence_digest,
            )
            repository.append_record(
                evidence_record(
                    "RightsBinding",
                    rights["rightsBindingRef"],
                    rights,
                    run=run,
                )
            )
            command = consent_successor_command(
                lineage["consent"],
                rights=rights,
                key=f"consent-{suffix}",
                state="REVOKED",
                run=run,
            )
            command["evidenceRef"] = evidence_ref
            command["evidenceDigest"] = evidence_digest
            candidates.append((owner if run == RUN else other, command))

        def attempt(item):
            service, command = item
            try:
                return service.create_consent_grant_successor(command)
            except EpisodeProductionError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, candidates))

        self.assertEqual(
            sum(isinstance(item, dict) for item in results),
            1,
        )
        self.assertEqual(
            sum(isinstance(item, StaleInputError) for item in results),
            1,
        )
        versions = repository.list_records(
            WORKSPACE, RUN, record_kind="ConsentGrantVersion"
        )
        self.assertEqual(len(versions), 2)

    def test_active_consent_successor_and_clone_creation_are_serialized(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        refs = ThreadSafeRefs()
        owner = self.service(repository, refs=refs)
        other = self.service(repository, refs=refs)
        upstreams = seed_upstreams(repository)
        binding = owner.create_source_recording_binding(
            source_command(upstreams)
        )["sourceVoiceRecordingAssetVersionBinding"]
        consent = owner.create_consent_grant(consent_command(binding))[
            "consentGrantVersion"
        ]
        fixed_voice = confirmed_fixed_voice(owner)
        successor_rights = consent_successor_rights(
            binding,
            consent,
            suffix="active-race",
            evidence_ref="consent-active-evidence",
            evidence_digest="a" * 64,
        )
        repository.append_record(
            evidence_record(
                "RightsBinding",
                successor_rights["rightsBindingRef"],
                successor_rights,
            )
        )
        successor = consent_successor_command(
            consent,
            rights=successor_rights,
            key="consent-active-race",
            state="ACTIVE",
        )
        clone = clone_lock_command(
            binding,
            consent,
            fixed_voice,
            key="clone-active-consent-race",
        )

        def attempt(operation):
            try:
                if operation == "successor":
                    return other.create_consent_grant_successor(successor)
                return owner.create_clone_voice_lock(clone)
            except EpisodeProductionError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("successor", "clone")))

        successes = [item for item in results if isinstance(item, dict)]
        failures = [item for item in results if isinstance(item, EpisodeProductionError)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        clone_won = "voiceLockVersion" in successes[0]
        successor_won = "consentGrantVersion" in successes[0]
        self.assertNotEqual(clone_won, successor_won)
        self.assertEqual(
            len(
                owner.voice_locks.list_clone_voice_lock_versions(
                    WORKSPACE, PROJECT, SERIES
                )
            ),
            1 if clone_won else 0,
        )
        consent_versions = repository.list_records(
            WORKSPACE, RUN, record_kind="ConsentGrantVersion"
        )
        self.assertEqual(len(consent_versions), 1 if clone_won else 2)

    def test_revocation_and_clone_confirmation_have_only_legal_serial_orders(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        refs = ThreadSafeRefs()
        owner = self.service(repository, refs=refs)
        other = self.service(repository, refs=refs)
        upstreams = seed_upstreams(repository)
        binding = owner.create_source_recording_binding(
            source_command(upstreams)
        )["sourceVoiceRecordingAssetVersionBinding"]
        consent = owner.create_consent_grant(consent_command(binding))[
            "consentGrantVersion"
        ]
        fixed_voice = confirmed_fixed_voice(owner)
        candidate = owner.create_clone_voice_lock(
            clone_lock_command(binding, consent, fixed_voice)
        )
        revoked_rights = consent_successor_rights(
            binding,
            consent,
            suffix="confirm-race-revoked",
            evidence_ref="consent-revoked-evidence",
            evidence_digest="b" * 64,
        )
        repository.append_record(
            evidence_record(
                "RightsBinding",
                revoked_rights["rightsBindingRef"],
                revoked_rights,
            )
        )
        revoke = consent_successor_command(
            consent,
            rights=revoked_rights,
            key="consent-confirm-race-revoke",
            state="REVOKED",
        )
        confirm = confirm_lock_command(
            candidate, key="clone-confirm-revocation-race"
        )

        def attempt(operation):
            try:
                if operation == "revoke":
                    return other.create_consent_grant_successor(revoke)
                return owner.confirm_clone_voice_lock(confirm)
            except EpisodeProductionError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            revoked_result, confirmed_result = list(
                pool.map(attempt, ("revoke", "confirm"))
            )

        self.assertIsInstance(revoked_result, dict)
        self.assertEqual(
            revoked_result["consentGrantVersion"]["revocationState"],
            "REVOKED",
        )
        if isinstance(confirmed_result, EpisodeProductionError):
            with self.assertRaises(EpisodeProductionError):
                owner.get_confirmed_clone_voice_lock(
                    WORKSPACE, RUN, candidate["voiceLock"]["voiceRef"]
                )
            return

        self.assertIsInstance(confirmed_result, dict)
        lineage = {
            "upstreams": upstreams,
            "binding": binding,
            "consent": consent,
            "fixedVoice": fixed_voice,
            "candidateLock": candidate,
            "confirmedLock": confirmed_result,
        }
        profile = seed_historical_voice_profile(repository, lineage)[
            "voiceProfileVersion"
        ]
        with self.assertRaises(EpisodeProductionError):
            owner.resolve_current_confirmed_voice_profile(
                WORKSPACE,
                RUN,
                profile["voiceProfileVersionRef"],
                profile["payloadDigest"],
                evaluated_at=CREATED_AT,
            )

    def test_foreign_series_same_source_ref_and_key_do_not_leak_or_conflict(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        upstreams = seed_upstreams(repository)
        binding = service.create_source_recording_binding(
            source_command(upstreams)
        )["sourceVoiceRecordingAssetVersionBinding"]
        owner_record = repository.list_records(
            WORKSPACE,
            RUN,
            record_kind="SourceVoiceRecordingAssetVersionBinding",
        )[0]
        foreign_binding = sealed(
            {
                **binding,
                "projectRef": f"{PROJECT}-foreign",
                "seriesRef": f"{SERIES}-foreign",
            }
        )
        repository.append_record(
            EvidenceRecord(
                workspaceRef=WORKSPACE,
                productionRunRef=FOREIGN_SERIES_RUN,
                recordKind=owner_record["recordKind"],
                recordRef=owner_record["recordRef"],
                recordVersion=owner_record["recordVersion"],
                idempotencyKey=owner_record["idempotencyKey"],
                requestDigest=owner_record["requestDigest"],
                createdAt=owner_record["createdAt"],
                payload=foreign_binding,
                payloadDigest=foreign_binding["payloadDigest"],
            )
        )

        owner_graph = service.get_voice_profile_lineage(WORKSPACE, RUN)
        foreign_graph = service.get_voice_profile_lineage(
            WORKSPACE, FOREIGN_SERIES_RUN
        )
        self.assertEqual(
            [
                item["projectRef"]
                for item in owner_graph[
                    "sourceVoiceRecordingAssetVersionBindings"
                ]
            ],
            [PROJECT],
        )
        self.assertEqual(
            [
                item["projectRef"]
                for item in foreign_graph[
                    "sourceVoiceRecordingAssetVersionBindings"
                ]
            ],
            [f"{PROJECT}-foreign"],
        )

    def test_cross_run_revocation_invalidates_observed_workspace_head(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        refs = Refs()
        owner = self.service(repository, refs=refs)
        lineage = create_lineage_to_confirmed_lock(owner, repository)
        successor_rights = consent_successor_rights(
            lineage["binding"],
            lineage["consent"],
            suffix="workspace-head-revocation",
            evidence_ref="consent-revoked-evidence",
            evidence_digest="b" * 64,
        )
        repository.append_record(
            evidence_record(
                "RightsBinding",
                successor_rights["rightsBindingRef"],
                successor_rights,
            )
        )
        observed_head = repository.workspace_record_journal_head(WORKSPACE)
        observed_other_run_revision = repository.read_snapshot(
            WORKSPACE, SAME_SERIES_RUN
        ).revisionToken

        owner.create_consent_grant_successor(
            consent_successor_command(
                lineage["consent"],
                rights=successor_rights,
                key="consent-revoke-workspace-head",
                state="REVOKED",
            )
        )
        self.assertEqual(
            repository.read_snapshot(
                WORKSPACE, SAME_SERIES_RUN
            ).revisionToken,
            observed_other_run_revision,
        )
        with self.assertRaises(StaleInputError):
            repository.append_records(
                (
                    evidence_record(
                        "Candidate",
                        "candidate-after-cross-run-revocation",
                        {
                            "schemaVersion": "test.candidate.v1",
                            "publicationAllowed": False,
                        },
                        run=SAME_SERIES_RUN,
                    ),
                ),
                expected_workspace_record_journal_head=observed_head,
                expected_evidence_revision_token=observed_other_run_revision,
            )

    def test_profile_create_rejects_missing_runtime_evidence(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        technical = {
            **synthetic_profile_package(),
            "payloadDigest": "a" * 64,
        }
        command = profile_command(lineage["confirmedLock"], technical)
        with self.assertRaises(VoiceProfileLineageNotFoundError):
            service.create_voice_profile(command)

    def test_profile_rejects_explicit_test_fixture_package(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        technical = seed_profile_test_fixture(repository)
        command = profile_command(lineage["confirmedLock"], technical)
        with self.assertRaises(EpisodeProductionError):
            service.create_voice_profile(command)

    def test_historical_profile_successors_are_immutable_and_contiguous(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        historical = seed_historical_voice_profile(
            repository, lineage, status="REVOKED"
        )
        candidate, confirmed, revoked = historical["voiceProfileVersions"]
        self.assertEqual(
            [item["status"] for item in historical["voiceProfileVersions"]],
            ["CANDIDATE", "CONFIRMED", "REVOKED"],
        )
        self.assertEqual(confirmed["versionNumber"], 2)
        self.assertEqual(revoked["versionNumber"], 3)
        self.assertEqual(
            confirmed["parentVoiceProfileVersionDigest"], candidate["payloadDigest"]
        )
        self.assertEqual(
            revoked["parentVoiceProfileVersionDigest"], confirmed["payloadDigest"]
        )
        self.assertEqual(candidate["status"], "CANDIDATE")
        self.assertEqual(confirmed["status"], "CONFIRMED")
        graph = service.get_voice_profile_lineage(WORKSPACE, RUN)
        self.assertEqual(
            [item["payloadDigest"] for item in graph["voiceProfileVersions"]],
            [item["payloadDigest"] for item in historical["voiceProfileVersions"]],
        )
        with self.assertRaises(VoiceProfileLineageNotEffectiveError):
            service.create_voice_profile_successor(
                profile_successor_command(
                    revoked, status="CONFIRMED", key="profile-illegal-revive"
                )
            )

    def test_historical_clone_dialogue_reads_but_production_builders_need_authority(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        chain = build_historical_clone_dialogue_chain(service, repository)
        dialogue = chain["dialogue"]
        self.assertEqual(
            dialogue["schemaVersion"], "v5.m12-dialogue-asset-version.v2"
        )
        self.assertEqual(
            dialogue["audioTechnicalValidationDigest"],
            chain["technicalMapping"]["payloadDigest"],
        )
        self.assertEqual(
            dialogue["audioFileDigest"], dialogue["artifact"]["fileDigest"]
        )
        self.assertEqual(
            dialogue["audioPcmContentDigest"],
            chain["technicalMapping"]["pcmContentDigest"],
        )
        self.assertTrue(
            {
                "sourceAssetVersionRef",
                "sourceAssetVersionDigest",
                "sourceAssetVersionType",
            }.isdisjoint(chain["technicalMapping"])
        )
        self.assertNotIn(
            dialogue["assetVersionRef"], repr(chain["technicalMapping"])
        )
        with self.assertRaises(EpisodeProductionError):
            service.resolve_current_confirmed_voice_profile(
                WORKSPACE,
                RUN,
                chain["profile"]["voiceProfileVersionRef"],
                chain["profile"]["payloadDigest"],
                evaluated_at=CREATED_AT,
            )
        with self.assertRaises(EpisodeProductionError):
            build_clone_voice_asset_version(
                chain["voiceCommand"],
                voice_profile_version=chain["profile"],
                confirmed_voice_lock=chain["confirmedLock"],
                consent_grant_version=chain["consent"],
                source_recording_binding=chain["source"],
                evaluated_at=CREATED_AT,
                current_voice_profile_authority=None,
            )
        with self.assertRaises(EpisodeProductionError):
            build_audio_generation_request(
                chain["requestCommand"],
                confirmed_voice_lock=chain["confirmedLock"],
                voice_asset_version=chain["voice"],
                voice_profile_version=chain["profile"],
                consent_grant_version=chain["consent"],
                source_recording_binding=chain["source"],
                evaluated_at=CREATED_AT,
                current_voice_profile_authority=None,
            )
        with self.assertRaises(EpisodeProductionError):
            build_clone_dialogue_asset_version(
                chain["dialogueCommand"],
                voice_asset_version=chain["voice"],
                audio_generation_request=chain["request"],
                generation_result=chain["evidence"]["generationResult"],
                artifact_evidence=chain["evidence"]["artifactEvidence"],
                audio_technical_validation=chain["technical"],
                confirmed_voice_lock=chain["confirmedLock"],
                voice_profile_version=chain["profile"],
                consent_grant_version=chain["consent"],
                source_recording_binding=chain["source"],
                evaluated_at=CREATED_AT,
                current_voice_profile_authority=None,
            )

    def test_lineage_graph_rejects_self_direct_indirect_cycles_and_scope_drift(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        seed_historical_voice_profile(repository, lineage)
        graph = service.get_voice_profile_lineage(WORKSPACE, RUN)
        self.assertEqual(validate_voice_profile_lineage_graph(graph), graph)
        original = graph["voiceProfileVersions"][0]

        self_cycle = deepcopy(graph)
        node = deepcopy(original)
        node.update(
            {
                "voiceProfileVersionRef": "profile-cycle-self",
                "versionNumber": 2,
                "parentVoiceProfileVersionRef": "profile-cycle-self",
                "parentVoiceProfileVersionDigest": "1" * 64,
            }
        )
        self_cycle["voiceProfileVersions"] = [sealed(node)]
        self_cycle = sealed(self_cycle)

        direct = deepcopy(graph)
        left = deepcopy(original)
        left.update(
            {
                "voiceProfileVersionRef": "profile-cycle-left",
                "versionNumber": 2,
                "parentVoiceProfileVersionRef": "profile-cycle-right",
                "parentVoiceProfileVersionDigest": "2" * 64,
            }
        )
        right = deepcopy(original)
        right.update(
            {
                "voiceProfileVersionRef": "profile-cycle-right",
                "versionNumber": 3,
                "parentVoiceProfileVersionRef": "profile-cycle-left",
                "parentVoiceProfileVersionDigest": "3" * 64,
            }
        )
        direct["voiceProfileVersions"] = [sealed(left), sealed(right)]
        direct = sealed(direct)

        indirect = deepcopy(graph)
        nodes = []
        refs = ["profile-cycle-a", "profile-cycle-b", "profile-cycle-c"]
        for index, ref in enumerate(refs):
            node = deepcopy(original)
            node.update(
                {
                    "voiceProfileVersionRef": ref,
                    "versionNumber": index + 2,
                    "parentVoiceProfileVersionRef": refs[(index + 1) % 3],
                    "parentVoiceProfileVersionDigest": str(index + 4) * 64,
                }
            )
            nodes.append(sealed(node))
        indirect["voiceProfileVersions"] = nodes
        indirect = sealed(indirect)

        scope_drift = deepcopy(graph)
        changed_source = deepcopy(
            scope_drift["sourceVoiceRecordingAssetVersionBindings"][0]
        )
        changed_source["projectRef"] = "project-other"
        changed_source["seriesRef"] = "series-other"
        scope_drift["sourceVoiceRecordingAssetVersionBindings"][0] = sealed(
            changed_source
        )
        scope_drift = sealed(scope_drift)

        for name, value in (
            ("self", self_cycle),
            ("direct", direct),
            ("indirect", indirect),
            ("project-series-scope", scope_drift),
        ):
            with self.subTest(case=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(value)

    def test_lineage_graph_rejects_forks_stale_heads_and_cross_lineage_drift(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        seed_historical_voice_profile(repository, lineage)
        graph = service.get_voice_profile_lineage(WORKSPACE, RUN)

        consent_fork = deepcopy(graph)
        consent_parent = consent_fork["consentGrantVersions"][0]
        consent_children = []
        for suffix, digit in (("left", "4"), ("right", "5")):
            child = deepcopy(consent_parent)
            child.update(
                {
                    "consentGrantVersionRef": f"consent-version-fork-{suffix}",
                    "versionNumber": 2,
                    "parentConsentGrantVersionRef": consent_parent[
                        "consentGrantVersionRef"
                    ],
                    "parentConsentGrantVersionDigest": consent_parent[
                        "payloadDigest"
                    ],
                    "revocationState": "REVOKED",
                    "evidenceRef": f"consent-evidence-fork-{suffix}",
                    "evidenceDigest": digit * 64,
                }
            )
            consent_children.append(sealed(child))
        consent_fork["consentGrantVersions"] = [
            consent_parent,
            *consent_children,
        ]
        consent_fork = sealed(consent_fork)

        profile_fork = deepcopy(graph)
        profile_parent, profile_confirmed = profile_fork["voiceProfileVersions"]
        profile_sibling = deepcopy(profile_confirmed)
        profile_sibling["voiceProfileVersionRef"] = "voice-profile-fork-v2"
        profile_fork["voiceProfileVersions"].append(sealed(profile_sibling))
        profile_fork = sealed(profile_fork)

        lock_fork = deepcopy(graph)
        lock_sibling = deepcopy(lock_fork["voiceLockVersions"][0])
        lock_sibling["voiceLockVersionRef"] = "voice-lock-version-fork-v2"
        lock_fork["voiceLockVersions"].append(sealed(lock_sibling))
        lock_fork = sealed(lock_fork)

        stale_lock_head = deepcopy(graph)
        stale_root = deepcopy(stale_lock_head["voiceLocks"][0])
        stale_root["currentVoiceLockVersionRef"] = "voice-lock-version-missing"
        stale_lock_head["voiceLocks"] = [sealed(stale_root)]
        stale_lock_head = sealed(stale_lock_head)

        lock_consent_source_drift = deepcopy(graph)
        changed_lock = deepcopy(lock_consent_source_drift["voiceLockVersions"][0])
        changed_lock["sourceRecordingBindingDigest"] = "0" * 64
        changed_lock = sealed(changed_lock)
        changed_root = deepcopy(lock_consent_source_drift["voiceLocks"][0])
        changed_root["confirmedVoiceLockDigest"] = changed_lock["payloadDigest"]
        changed_root = sealed(changed_root)
        changed_confirmation = deepcopy(
            lock_consent_source_drift["voiceLockConfirmations"][0]
        )
        changed_confirmation["voiceLockDigest"] = changed_lock["payloadDigest"]
        changed_confirmation = sealed(changed_confirmation)
        lock_consent_source_drift["voiceLockVersions"] = [changed_lock]
        lock_consent_source_drift["voiceLocks"] = [changed_root]
        lock_consent_source_drift["voiceLockConfirmations"] = [
            changed_confirmation
        ]
        lock_consent_source_drift = sealed(lock_consent_source_drift)

        profile_source_drift = deepcopy(graph)
        changed_profiles = []
        parent = None
        for profile in profile_source_drift["voiceProfileVersions"]:
            changed = deepcopy(profile)
            changed["sourceRecordingBindingDigest"] = "0" * 64
            if parent is not None:
                changed["parentVoiceProfileVersionDigest"] = parent[
                    "payloadDigest"
                ]
            parent = sealed(changed)
            changed_profiles.append(parent)
        profile_source_drift["voiceProfileVersions"] = changed_profiles
        profile_source_drift = sealed(profile_source_drift)

        profile_consent_drift = deepcopy(graph)
        changed_profiles = []
        parent = None
        for profile in profile_consent_drift["voiceProfileVersions"]:
            changed = deepcopy(profile)
            changed["consentGrantVersionDigest"] = "0" * 64
            if parent is not None:
                changed["parentVoiceProfileVersionDigest"] = parent[
                    "payloadDigest"
                ]
            parent = sealed(changed)
            changed_profiles.append(parent)
        profile_consent_drift["voiceProfileVersions"] = changed_profiles
        profile_consent_drift = sealed(profile_consent_drift)

        missing_confirmation = deepcopy(graph)
        missing_confirmation["voiceLockConfirmations"] = []
        missing_confirmation = sealed(missing_confirmation)

        for name, value in (
            ("consent-fork", consent_fork),
            ("profile-fork", profile_fork),
            ("voice-lock-fork", lock_fork),
            ("stale-voice-lock-current", stale_lock_head),
            ("voice-lock-consent-source", lock_consent_source_drift),
            ("profile-voice-lock-source", profile_source_drift),
            ("profile-voice-lock-consent", profile_consent_drift),
            ("confirmed-v2-without-confirmation", missing_confirmation),
        ):
            with self.subTest(case=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_voice_profile_lineage_graph(value)

    def test_clone_dialogue_rejects_generation_artifact_analysis_file_and_pcm_drift(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        chain = build_historical_clone_dialogue_chain(service, repository)

        changed_generation = deepcopy(
            chain["evidence"]["generationResult"]
        )
        changed_generation["generationResultRef"] = "generation-result-drift"
        changed_generation = sealed(changed_generation)

        changed_evidence = deepcopy(chain["evidence"]["artifactEvidence"])
        changed_evidence["artifactEvidenceRef"] = "artifact-evidence-drift"
        changed_evidence = sealed(changed_evidence)
        artifact_generation = deepcopy(
            chain["evidence"]["generationResult"]
        )
        artifact_generation.update(
            {
                "artifactEvidenceRef": changed_evidence[
                    "artifactEvidenceRef"
                ],
                "artifactEvidenceDigest": changed_evidence["payloadDigest"],
            }
        )
        artifact_generation = sealed(artifact_generation)

        changed_analysis = chain["evidence"]["analysisEvidence"].as_dict()
        changed_analysis["integratedLufs"] = "-23.000"
        changed_analysis = AudioTechnicalAnalysisEvidence._from_analyzer(
            seal_analysis(changed_analysis)
        )
        changed_technical_mapping = build_pre_asset_audio_technical_validation(
            pre_asset_validation_command(),
            generation_result=chain["evidence"]["generationResult"],
            artifact_evidence=chain["evidence"]["artifactEvidence"],
            v4_analysis_evidence=changed_analysis,
        )
        changed_technical = validate_pre_asset_audio_technical_validation(
            changed_technical_mapping,
            generation_result=chain["evidence"]["generationResult"],
            artifact_evidence=chain["evidence"]["artifactEvidence"],
            v4_analysis_evidence=changed_analysis,
        )

        upstream_cases = (
            (
                "generation",
                changed_generation,
                chain["evidence"]["artifactEvidence"],
                chain["technical"],
            ),
            (
                "artifact",
                artifact_generation,
                changed_evidence,
                chain["technical"],
            ),
            (
                "analysis",
                chain["evidence"]["generationResult"],
                chain["evidence"]["artifactEvidence"],
                changed_technical,
            ),
        )
        for name, generation, evidence, technical in upstream_cases:
            with self.subTest(drift=name), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_dialogue_asset_version(
                    chain["dialogue"],
                    voice_asset_version=chain["voice"],
                    audio_generation_request=chain["request"],
                    generation_result=generation,
                    artifact_evidence=evidence,
                    audio_technical_validation=technical,
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

        for field in ("audioFileDigest", "audioPcmContentDigest"):
            changed_dialogue = deepcopy(chain["dialogue"])
            changed_dialogue[field] = "0" * 64
            changed_dialogue = sealed(changed_dialogue)
            with self.subTest(drift=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_dialogue_asset_version(
                    changed_dialogue,
                    voice_asset_version=chain["voice"],
                    audio_generation_request=chain["request"],
                    generation_result=chain["evidence"]["generationResult"],
                    artifact_evidence=chain["evidence"]["artifactEvidence"],
                    audio_technical_validation=chain["technical"],
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

    def test_clone_dialogue_rejects_request_result_and_provenance_drift(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        chain = build_historical_clone_dialogue_chain(service, repository)

        def request_wrapper(value: dict) -> AudioGenerationRequest:
            return AudioGenerationRequest.from_mapping(
                value,
                confirmed_voice_lock=chain["confirmedLock"],
                voice_asset_version=chain["voice"],
                voice_profile_version=chain["profile"],
                consent_grant_version=chain["consent"],
                source_recording_binding=chain["source"],
                evaluated_at=CREATED_AT,
                require_current_authority=False,
            )

        for field, changed_value in (
            ("assetRequirementRef", "asset-requirement-dialogue-drift"),
            ("assetRequirementDigest", "0" * 64),
        ):
            changed = deepcopy(chain["requestMapping"])
            changed[field] = changed_value
            changed = sealed(changed)
            with self.subTest(request=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_dialogue_asset_version(
                    chain["dialogue"],
                    voice_asset_version=chain["voice"],
                    audio_generation_request=request_wrapper(changed),
                    generation_result=chain["evidence"]["generationResult"],
                    artifact_evidence=chain["evidence"]["artifactEvidence"],
                    audio_technical_validation=chain["technical"],
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

        for field, changed_value in (
            ("scriptVersionRef", "script-version-drift"),
            ("scriptVersionDigest", "0" * 64),
            ("audioRole", "narration"),
            ("assetRequirementRef", "asset-requirement-dialogue-drift"),
            ("assetRequirementDigest", "0" * 64),
        ):
            changed = deepcopy(chain["evidence"]["generationResult"])
            changed[field] = changed_value
            changed = sealed(changed)
            with self.subTest(result=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_dialogue_asset_version(
                    chain["dialogue"],
                    voice_asset_version=chain["voice"],
                    audio_generation_request=chain["request"],
                    generation_result=changed,
                    artifact_evidence=chain["evidence"]["artifactEvidence"],
                    audio_technical_validation=chain["technical"],
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

        for field, changed_value in (
            ("adapterIdentity", "v4.local-clone-tts.other.v1"),
            ("parametersDigest", "0" * 64),
            ("originKind", "OTHER_LOCAL_EXECUTION"),
        ):
            changed = deepcopy(chain["requestMapping"])
            provenance = deepcopy(changed["requestedProvenance"])
            provenance[field] = changed_value
            changed["requestedProvenance"] = sealed(provenance)
            changed = sealed(changed)
            with self.subTest(requested_provenance=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_clone_dialogue_asset_version(
                    chain["dialogue"],
                    voice_asset_version=chain["voice"],
                    audio_generation_request=request_wrapper(changed),
                    generation_result=chain["evidence"]["generationResult"],
                    artifact_evidence=chain["evidence"]["artifactEvidence"],
                    audio_technical_validation=chain["technical"],
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

        for synchronize_digest in (False, True):
            changed = deepcopy(chain["requestMapping"])
            changed["requestSpec"]["normalizedSpeechParameters"]["text"] = (
                "不要再动。"
            )
            if synchronize_digest:
                provenance = deepcopy(changed["requestedProvenance"])
                provenance["parametersDigest"] = _digest(
                    changed["requestSpec"]["normalizedSpeechParameters"]
                )
                changed["requestedProvenance"] = sealed(provenance)
            changed = sealed(changed)
            with self.subTest(
                normalized_parameters_digest_synchronized=synchronize_digest
            ), self.assertRaises(EpisodeProductionError):
                validate_clone_dialogue_asset_version(
                    chain["dialogue"],
                    voice_asset_version=chain["voice"],
                    audio_generation_request=request_wrapper(changed),
                    generation_result=chain["evidence"]["generationResult"],
                    artifact_evidence=chain["evidence"]["artifactEvidence"],
                    audio_technical_validation=chain["technical"],
                    confirmed_voice_lock=chain["confirmedLock"],
                    voice_profile_version=chain["profile"],
                    consent_grant_version=chain["consent"],
                    source_recording_binding=chain["source"],
                    evaluated_at=CREATED_AT,
                )

        changed_dialogue = deepcopy(chain["dialogue"])
        changed_dialogue["language"] = "en-US"
        changed_dialogue = sealed(changed_dialogue)
        with self.assertRaises(EpisodeProductionError):
            validate_clone_dialogue_asset_version(
                changed_dialogue,
                voice_asset_version=chain["voice"],
                audio_generation_request=chain["request"],
                generation_result=chain["evidence"]["generationResult"],
                artifact_evidence=chain["evidence"]["artifactEvidence"],
                audio_technical_validation=chain["technical"],
                confirmed_voice_lock=chain["confirmedLock"],
                voice_profile_version=chain["profile"],
                consent_grant_version=chain["consent"],
                source_recording_binding=chain["source"],
                evaluated_at=CREATED_AT,
            )

    def test_revoked_profile_consent_and_expiry_block_current_resolution(self):
        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        profile = seed_historical_voice_profile(repository, lineage)[
            "voiceProfileVersion"
        ]
        successor_rights = consent_successor_rights(
            lineage["binding"],
            lineage["consent"],
            suffix="revoked-current-resolution",
            evidence_ref="consent-revoked-evidence",
            evidence_digest="b" * 64,
        )
        repository.append_record(
            evidence_record(
                "RightsBinding",
                successor_rights["rightsBindingRef"],
                successor_rights,
            )
        )
        service.create_consent_grant_successor(
            consent_successor_command(
                lineage["consent"],
                rights=successor_rights,
                key="consent-revoke-before-current-resolution",
                state="REVOKED",
            )
        )
        with self.assertRaises(EpisodeProductionError):
            service.resolve_current_confirmed_voice_profile(
                WORKSPACE,
                RUN,
                profile["voiceProfileVersionRef"],
                profile["payloadDigest"],
                evaluated_at=CREATED_AT,
            )

        repository = InMemoryEpisodeProductionEvidenceAdapter()
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        historical = seed_historical_voice_profile(
            repository, lineage, status="REVOKED"
        )
        confirmed = historical["voiceProfileVersions"][1]
        with self.assertRaises(EpisodeProductionError):
            service.resolve_current_confirmed_voice_profile(
                WORKSPACE,
                RUN,
                confirmed["voiceProfileVersionRef"],
                confirmed["payloadDigest"],
                evaluated_at=CREATED_AT,
            )

        repository = InMemoryEpisodeProductionEvidenceAdapter()
        creator = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(creator, repository)
        profile = seed_historical_voice_profile(repository, lineage)[
            "voiceProfileVersion"
        ]
        expired = self.service(
            repository, clock=lambda: "2028-08-30T08:00:00Z"
        )
        with self.assertRaises(EpisodeProductionError):
            expired.resolve_current_confirmed_voice_profile(
                WORKSPACE,
                RUN,
                profile["voiceProfileVersionRef"],
                profile["payloadDigest"],
                evaluated_at="2028-08-30T08:00:00Z",
            )


class M12VoiceProfileLineageSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "episode-production-evidence.sqlite3"
        self.voice_database = Path(self.temporary.name) / "voice-lock.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def adapter(self, *, initialize: bool):
        return SqliteEpisodeProductionEvidenceAdapter(
            self.database, initialize_if_missing=initialize
        )

    def service(self, repository, *, refs: Refs | None = None):
        selected_refs = refs or Refs()
        voice_locks = K2VoiceLockService(
            SqliteVoiceLockAdapter(
                self.voice_database,
                initialize_if_missing=not self.voice_database.exists(),
            ),
            ref_factory=selected_refs,
            clock=lambda: CREATED_AT,
        )
        return K2VoiceProfileLineageService(
            RootService(),
            repository,
            voice_locks=voice_locks,
            ref_factory=selected_refs,
            clock=lambda: CREATED_AT,
        )

    def test_source_and_consent_survive_restart_with_exact_replay(self):
        repository = self.adapter(initialize=True)
        upstreams = seed_upstreams(repository)
        service = self.service(repository)
        source_input = source_command(upstreams)
        source_result = service.create_source_recording_binding(source_input)
        binding = source_result["sourceVoiceRecordingAssetVersionBinding"]
        consent_input = consent_command(binding)
        consent_result = service.create_consent_grant(consent_input)

        restarted = self.service(self.adapter(initialize=False))
        source_replay = restarted.create_source_recording_binding(source_input)
        consent_replay = restarted.create_consent_grant(consent_input)
        self.assertTrue(source_replay["idempotentReplay"])
        self.assertTrue(consent_replay["idempotentReplay"])
        self.assertEqual(
            source_replay["sourceVoiceRecordingAssetVersionBinding"], binding
        )
        self.assertEqual(
            consent_replay["consentGrantVersion"],
            consent_result["consentGrantVersion"],
        )

    def test_tampered_sqlite_evidence_fails_closed_after_restart(self):
        repository = self.adapter(initialize=True)
        upstreams = seed_upstreams(repository)
        command = source_command(upstreams)
        result = self.service(repository).create_source_recording_binding(command)
        binding = result["sourceVoiceRecordingAssetVersionBinding"]
        tampered = deepcopy(binding)
        tampered["subjectRef"] = "character-forged"
        payload_json = json.dumps(
            tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_episode_production_records SET payload_json=? "
                "WHERE record_kind='SourceVoiceRecordingAssetVersionBinding'",
                (payload_json,),
            )

        with self.assertRaises(RepositoryUnavailableError):
            self.adapter(initialize=False)

    def test_resealed_binding_transcript_drift_fails_get_and_replay(self):
        repository = self.adapter(initialize=True)
        upstreams = seed_upstreams(repository)
        command = source_command(upstreams)
        binding = self.service(repository).create_source_recording_binding(command)[
            "sourceVoiceRecordingAssetVersionBinding"
        ]
        original_json = json.dumps(
            binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

        for field, value in (
            ("transcriptLanguage", "en-US"),
            ("transcriptTextDigest", "0" * 64),
            ("sourceVoiceRecordingAssetVersionDigest", "0" * 64),
        ):
            tampered = deepcopy(binding)
            tampered[field] = value
            tampered = sealed(tampered)
            payload_json = json.dumps(
                tampered,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with sqlite3.connect(self.database) as connection:
                connection.execute(
                    "UPDATE v5_episode_production_records SET payload_json=?, "
                    "payload_digest=? WHERE record_kind="
                    "'SourceVoiceRecordingAssetVersionBinding'",
                    (payload_json, tampered["payloadDigest"]),
                )

            restarted = self.service(self.adapter(initialize=False))
            with self.subTest(field=field, operation="get"), self.assertRaises(
                EpisodeProductionError
            ):
                restarted.get_source_recording_binding(
                    WORKSPACE, RUN, binding["sourceRecordingBindingRef"]
                )
            with self.subTest(field=field, operation="replay"), self.assertRaises(
                EpisodeProductionError
            ):
                restarted.create_source_recording_binding(command)
            with self.subTest(
                field=field, operation="downstream-consent"
            ), self.assertRaises(EpisodeProductionError):
                restarted.create_consent_grant(
                    consent_command(tampered, key=f"consent-tampered-{field}")
                )

            with sqlite3.connect(self.database) as connection:
                connection.execute(
                    "UPDATE v5_episode_production_records SET payload_json=?, "
                    "payload_digest=? WHERE record_kind="
                    "'SourceVoiceRecordingAssetVersionBinding'",
                    (original_json, binding["payloadDigest"]),
                )

    def test_full_lineage_and_exact_versions_survive_sqlite_restart(self):
        repository = self.adapter(initialize=True)
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        confirmed = seed_historical_voice_profile(
            repository, lineage, status="CONFIRMED"
        )["voiceProfileVersion"]

        restarted = self.service(self.adapter(initialize=False))
        clone_versions = restarted.voice_locks.list_clone_voice_lock_versions(
            WORKSPACE, PROJECT, SERIES
        )
        self.assertEqual(len(clone_versions), 1)
        self.assertEqual(clone_versions[0]["versionNumber"], 2)
        self.assertEqual(
            clone_versions[0]["parentVoiceLockVersionRef"],
            lineage["fixedVoice"]["voiceLockVersion"]["voiceLockVersionRef"],
        )
        self.assertFalse(
            any(
                record["recordKind"]
                in {"VoiceLock", "VoiceLockVersion", "VoiceLockConfirmation"}
                for record in restarted.evidence.list_records(WORKSPACE, RUN)
            )
        )
        self.assertEqual(
            restarted.get_source_recording_binding(
                WORKSPACE, RUN, lineage["binding"]["sourceRecordingBindingRef"]
            ),
            lineage["binding"],
        )
        self.assertEqual(
            restarted.get_consent_grant_version(
                WORKSPACE, RUN, lineage["consent"]["consentGrantVersionRef"]
            ),
            lineage["consent"],
        )
        self.assertEqual(
            restarted.get_confirmed_clone_voice_lock(
                WORKSPACE, RUN, lineage["confirmedLock"]["voiceLock"]["voiceRef"]
            ),
            {
                key: lineage["confirmedLock"][key]
                for key in (
                    "voiceLock",
                    "voiceLockVersion",
                    "voiceLockConfirmation",
                )
            },
        )
        self.assertEqual(
            restarted.get_voice_profile_version(
                WORKSPACE, RUN, confirmed["voiceProfileVersionRef"]
            ),
            confirmed,
        )

    def test_coordinated_profile_predecessor_tamper_fails_on_lineage_read(self):
        repository = self.adapter(initialize=True)
        service = self.service(repository)
        lineage = create_lineage_to_confirmed_lock(service, repository)
        historical = seed_historical_voice_profile(
            repository, lineage, status="CONFIRMED"
        )
        confirmed = historical["voiceProfileVersion"]

        tampered = deepcopy(confirmed)
        tampered["parentVoiceProfileVersionDigest"] = "0" * 64
        tampered = sealed(tampered)
        payload_json = json.dumps(
            tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_episode_production_records SET payload_json=?, "
                "payload_digest=? WHERE record_kind='VoiceProfileVersion' "
                "AND record_ref=?",
                (
                    payload_json,
                    tampered["payloadDigest"],
                    confirmed["voiceProfileVersionRef"],
                ),
            )

        restarted = self.service(self.adapter(initialize=False))
        with self.assertRaises(EpisodeProductionError):
            restarted.get_voice_profile_lineage(WORKSPACE, RUN)


if __name__ == "__main__":
    unittest.main()
