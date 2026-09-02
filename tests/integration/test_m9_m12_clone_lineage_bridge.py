from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import unittest

from services.v5_core_os.episode_production.audio_authority import (
    build_clone_voice_asset_version,
    build_m9_audio_generation_request,
    build_requested_audio_provenance,
    validate_audio_generation_request,
    validate_voice_asset_version,
)
from services.v5_core_os.episode_production.evidence import (
    InMemoryEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    _digest,
)
from services.v5_core_os.episode_production.voice import (
    InMemoryVoiceLockAdapter,
    K2VoiceLockService,
)
from services.v5_core_os.episode_production.voice_profile import (
    K2VoiceProfileLineageService,
    VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION,
    validate_consent_grant_version_v2,
    validate_source_voice_recording_binding,
    validate_voice_profile_version,
)
from tests.contract.test_m12_audio_authority_contract import rights_binding
from tests.contract.test_m12_voice_profile_lineage_contract import (
    clone_dialogue_request_command,
    clone_voice_asset_command,
)
import tests.integration.test_m12_voice_profile_lineage_sqlite as lineage_fixtures


def sealed(value):
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def current_clone_authority():
    fixtures = lineage_fixtures
    repository = InMemoryEpisodeProductionEvidenceAdapter()
    refs = fixtures.Refs()
    voice_locks = K2VoiceLockService(
        InMemoryVoiceLockAdapter(),
        ref_factory=refs,
        clock=lambda: fixtures.CREATED_AT,
    )
    service = K2VoiceProfileLineageService(
        fixtures.RootService(),
        repository,
        voice_locks=voice_locks,
        ref_factory=refs,
        clock=lambda: fixtures.CREATED_AT,
    )
    lineage = fixtures.create_lineage_to_confirmed_lock(service, repository)
    package = fixtures.synthetic_profile_package()
    technical = sealed(
        {
            "schemaVersion": VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION,
            "technicalValidationRef": package["technicalValidationRef"],
            "storageBindingRef": package["storageBindingRef"],
            "byteSize": package["byteSize"],
            "fileDigest": package["fileDigest"],
            "contentDigest": package["contentDigest"],
            "packageFormat": package["packageFormat"],
            "packageSchemaVersion": package["packageSchemaVersion"],
            "engineId": fixtures.ENGINE_ID,
            "engineCommit": fixtures.ENGINE_COMMIT,
            "modelId": fixtures.MODEL_ID,
            "modelBundleDigest": fixtures.MODEL_BUNDLE_DIGEST,
            "dependencyLockDigest": "e" * 64,
            "runtimeManifestDigest": "f" * 64,
            "validationState": "PASSED",
            "publicationAllowed": False,
        }
    )
    repository.append_record(
        fixtures.evidence_record(
            "VoiceProfileTechnicalValidation",
            technical["technicalValidationRef"],
            technical,
        )
    )
    package["technicalValidationDigest"] = technical["payloadDigest"]
    with patch.object(
        fixtures, "synthetic_profile_package", return_value=package
    ):
        historical = fixtures.seed_historical_voice_profile(
            repository, lineage
        )
    profile = historical["voiceProfileVersion"]
    authority = service.resolve_current_confirmed_voice_profile(
        fixtures.WORKSPACE,
        fixtures.RUN,
        profile["voiceProfileVersionRef"],
        profile["payloadDigest"],
    )
    proof = authority.as_dict()
    wrappers = {
        "rights": lineage["upstreams"]["RightsBinding"],
        "source": validate_source_voice_recording_binding(
            proof["sourceRecordingBinding"]
        ),
        "consent": validate_consent_grant_version_v2(
            proof["consentGrantVersion"]
        ),
        "lock": lineage["confirmedLock"],
        "profile": validate_voice_profile_version(
            proof["voiceProfileVersion"]
        ),
    }
    voice_command = clone_voice_asset_command(wrappers)
    voice_command.update(
        {
            "workspaceRef": fixtures.WORKSPACE,
            "projectRef": fixtures.PROJECT,
            "seriesRef": fixtures.SERIES,
            "episodeRef": fixtures.EPISODE,
            "productionRunRef": fixtures.RUN,
        }
    )
    voice_mapping = build_clone_voice_asset_version(
        voice_command,
        voice_profile_version=wrappers["profile"],
        confirmed_voice_lock=wrappers["lock"],
        consent_grant_version=wrappers["consent"],
        source_recording_binding=wrappers["source"],
        evaluated_at=proof["evaluatedAt"],
        current_voice_profile_authority=authority,
    )
    voice = validate_voice_asset_version(
        voice_mapping,
        voice_profile_version=wrappers["profile"],
        confirmed_voice_lock=wrappers["lock"],
        consent_grant_version=wrappers["consent"],
        source_recording_binding=wrappers["source"],
        evaluated_at=proof["evaluatedAt"],
        current_voice_profile_authority=authority,
        require_current_authority=True,
    )
    return {
        "repository": repository,
        "service": service,
        "lineage": lineage,
        "authority": authority,
        "proof": proof,
        "wrappers": wrappers,
        "voice": voice,
        "voiceMapping": voice_mapping,
    }


def m9_clone_request(context):
    fixtures = lineage_fixtures
    text = "不要动。"
    creative_shot = sealed(
        {"creativeShotVersionRef": "creative-shot-clone-m9-v1"}
    )
    requirement = sealed(
        {
            "audioRequirementRef": "audio-requirement-clone-m9-1",
            "audioType": "DIALOGUE",
            "scriptVersionRef": "script-clone-1-v1",
            "scriptVersionDigest": "8" * 64,
            "creativeShotVersionRef": creative_shot[
                "creativeShotVersionRef"
            ],
            "creativeShotVersionDigest": creative_shot["payloadDigest"],
            "speakerCharacterRef": fixtures.SUBJECT,
            "sourceSpan": {
                "scriptSceneRef": "script-scene-clone-1",
                "sourceField": "DIALOGUE",
                "sourceIndex": 0,
                "startOffsetInclusive": 0,
                "endOffsetExclusive": len(text),
            },
            "sourceTextDigest": sha256(text.encode("utf-8")).hexdigest(),
            "timingReference": {
                "startFrameInclusive": 0,
                "endFrameExclusive": 24,
            },
        }
    )
    plan = sealed(
        {
            "executionMethodPlanVersionRef": "execution-method-plan-clone-m9-v1",
            "audioRequirements": [requirement],
            "creativeShotVersions": [creative_shot],
        }
    )
    request_rights = rights_binding(
        asset_requirement_ref=requirement["audioRequirementRef"],
        asset_requirement_digest=requirement["payloadDigest"],
    )
    command = clone_dialogue_request_command(
        context["voiceMapping"],
        context["wrappers"]["lock"],
        request_rights,
    )
    parameters = command["requestSpec"]["normalizedSpeechParameters"]
    command.update(
        {
            "workspaceRef": fixtures.WORKSPACE,
            "projectRef": fixtures.PROJECT,
            "seriesRef": fixtures.SERIES,
            "episodeRef": fixtures.EPISODE,
            "productionRunRef": fixtures.RUN,
            "assetRequirementRef": requirement["audioRequirementRef"],
            "assetRequirementDigest": requirement["payloadDigest"],
            "rightsBinding": request_rights,
            "requestedProvenance": build_requested_audio_provenance(
                {
                    "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
                    "adapterIdentity": "v4.local-clone-tts.contract-fixture.v1",
                    "parametersDigest": _digest(parameters),
                    "sourceRefs": [
                        {
                            "sourceRef": requirement["audioRequirementRef"],
                            "sourceDigest": requirement["payloadDigest"],
                        }
                    ],
                }
            ),
        }
    )
    validation = {
        "confirmed_voice_lock": context["wrappers"]["lock"],
        "voice_asset_version": context["voice"],
        "voice_profile_version": context["wrappers"]["profile"],
        "consent_grant_version": context["wrappers"]["consent"],
        "source_recording_binding": context["wrappers"]["source"],
        "evaluated_at": context["proof"]["evaluatedAt"],
        "current_voice_profile_authority": context["authority"],
    }
    request = build_m9_audio_generation_request(
        command,
        audio_requirement=requirement,
        execution_method_plan=plan,
        **validation,
    )
    return request, requirement, plan, validation


class M9M12CloneLineageBridgeTests(unittest.TestCase):
    def test_request_pins_current_consent_voice_lock_and_voice_profile(self):
        context = current_clone_authority()
        request, requirement, plan, validation = m9_clone_request(context)
        voice = context["voiceMapping"]
        self.assertEqual(
            request["voiceLineage"],
            {
                "consentGrantRef": voice["consentGrantRef"],
                "consentGrantVersionRef": voice["consentGrantVersionRef"],
                "consentGrantVersionDigest": voice[
                    "consentGrantVersionDigest"
                ],
                "voiceLockVersionRef": voice["voiceLockVersionRef"],
                "voiceLockVersionDigest": voice["voiceLockVersionDigest"],
                "voiceProfileRef": voice["voiceProfileRef"],
                "voiceProfileVersionRef": voice["voiceProfileVersionRef"],
                "voiceProfileVersionDigest": voice[
                    "voiceProfileVersionDigest"
                ],
            },
        )

        for field in (
            "consentGrantVersionDigest",
            "voiceLockVersionDigest",
            "voiceProfileVersionDigest",
        ):
            invalid = deepcopy(request)
            invalid["voiceLineage"][field] = "0" * 64
            invalid = sealed(invalid)
            with self.subTest(lineage_drift=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_audio_generation_request(
                    invalid,
                    audio_requirement=requirement,
                    execution_method_plan=plan,
                    require_current_authority=True,
                    **validation,
                )

        fixtures = lineage_fixtures
        lineage = context["lineage"]
        successor_rights = fixtures.consent_successor_rights(
            lineage["binding"],
            lineage["consent"],
            suffix="m9-m12-revoked",
            evidence_ref="consent-revoked-evidence",
            evidence_digest="b" * 64,
        )
        context["repository"].append_record(
            fixtures.evidence_record(
                "RightsBinding",
                successor_rights["rightsBindingRef"],
                successor_rights,
            )
        )
        context["service"].create_consent_grant_successor(
            fixtures.consent_successor_command(
                lineage["consent"],
                rights=successor_rights,
                key="m9-m12-consent-revoke",
                state="REVOKED",
            )
        )
        with self.assertRaises(EpisodeProductionError):
            validate_audio_generation_request(
                request,
                audio_requirement=requirement,
                execution_method_plan=plan,
                require_current_authority=True,
                **validation,
            )


if __name__ == "__main__":
    unittest.main()
