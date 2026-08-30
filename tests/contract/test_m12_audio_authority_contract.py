from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os import episode_production as episode_production_public
from services.v5_core_os.episode_production.audio import (
    normalize_speech_parameters,
)
from services.v5_core_os.episode_production.audio_authority import (
    AUDIO_ASSET_VERSION_TYPES,
    AudioConsentNotEffectiveError,
    AudioConsentRequiredError,
    AudioDomainTypeMismatchError,
    AudioGenerationRequest,
    AudioProvenanceRequiredError,
    AudioRightsRequiredError,
    LegacyAudioTargetError,
    build_ambience_asset_version,
    build_audio_generation_request,
    build_audio_provenance,
    build_consent_grant,
    build_dialogue_asset_version,
    build_music_asset_version,
    build_requested_audio_provenance,
    build_rights_binding,
    build_sfx_asset_version,
    build_voice_asset_version,
    require_effective_consent_grant,
    validate_ambience_asset_version,
    validate_audio_domain_asset_version,
    validate_audio_generation_request,
    validate_consent_grant,
    validate_dialogue_asset_version,
    validate_music_asset_version,
    validate_rights_binding,
    validate_sfx_asset_version,
    validate_voice_asset_version,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.voice import (
    VoiceLockNotConfirmedError,
)
from tests.contract.test_m12_audio_contract import (
    PROJECT,
    RUN,
    SERIES,
    WORKSPACE,
    sealed,
    voice_bundle,
)


EPISODE = "episode-m12"
AS_OF = "2026-08-29T12:00:00Z"
RIGHTS_MANIFEST_REF = "rights-manifest-m12"
RIGHTS_MANIFEST_DIGEST = "a" * 64
VOICE_CLONING_USE = "VOICE_CLONING"


def resealed(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def rights_binding(
    *,
    source_refs: list[dict] | None = None,
    asset_requirement_ref: str = "asset-requirement-audio-m12",
    asset_requirement_digest: str = "6" * 64,
) -> dict:
    required_sources = [
        {
            "sourceRef": RIGHTS_MANIFEST_REF,
            "sourceDigest": RIGHTS_MANIFEST_DIGEST,
        },
        {
            "sourceRef": "rights-authority-evidence-m12",
            "sourceDigest": "c" * 64,
        },
        {
            "sourceRef": asset_requirement_ref,
            "sourceDigest": asset_requirement_digest,
        },
    ]
    for source in source_refs or []:
        if source["sourceRef"] not in {
            item["sourceRef"] for item in required_sources
        }:
            required_sources.append(deepcopy(source))
    return build_rights_binding(
        {
            "rightsBindingRef": "audio-rights-binding-m12-v1",
            "rightsSource": "RIGHTS_MANIFEST_VERSION",
            "license": "PROJECT_OWNED_AND_CONSENT_BOUND",
            "ownership": "PROJECT_OWNER",
            "usageScope": [
                "AUDIO_PRODUCTION",
                "SPEECH_SYNTHESIS",
                "VOICE_PROFILE_USE",
                "VOICE_CLONING",
                "MUSIC_GENERATION",
                "SFX_GENERATION",
                "AMBIENCE_GENERATION",
            ],
            "attributionRequirement": "",
            "sourceRefs": required_sources,
            "rightsManifestRef": RIGHTS_MANIFEST_REF,
            "rightsManifestVersion": 1,
            "rightsManifestDigest": RIGHTS_MANIFEST_DIGEST,
            "authorityEvidenceRef": "rights-authority-evidence-m12",
            "authorityEvidenceDigest": "c" * 64,
        }
    )


def consent_grant(
    *,
    subject_ref: str = "character-lin",
    allowed_uses: list[str] | None = None,
    prohibited_uses: list[str] | None = None,
    valid_from: str = "2026-01-01T00:00:00Z",
    expires_at: str = "2027-01-01T00:00:00Z",
    revocation_state: str = "ACTIVE",
) -> dict:
    return build_consent_grant(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "consentGrantRef": "consent-grant-character-lin",
            "consentGrantVersionRef": "consent-grant-character-lin-v1",
            "version": 1,
            "subjectRef": subject_ref,
            "grantorRef": "grantor-character-lin",
            "allowedUses": (
                [VOICE_CLONING_USE]
                if allowed_uses is None
                else deepcopy(allowed_uses)
            ),
            "prohibitedUses": (
                [] if prohibited_uses is None else deepcopy(prohibited_uses)
            ),
            "territories": ["WORLDWIDE"],
            "validFrom": valid_from,
            "expiresAt": expires_at,
            "revocationState": revocation_state,
            "evidenceRef": "consent-evidence-character-lin-v1",
            "evidenceDigest": "d" * 64,
            "rightsManifestRef": RIGHTS_MANIFEST_REF,
            "rightsManifestDigest": RIGHTS_MANIFEST_DIGEST,
            "supersedesConsentGrantVersionRef": None,
            "supersedesConsentGrantVersionDigest": None,
            "createdAt": "2026-01-01T00:00:00Z",
        }
    )


def audio_provenance(slug: str) -> dict:
    return build_audio_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "adapterIdentity": "v4.local-audio-test-adapter.v1",
            "generationRecordRef": f"generation-result-{slug}",
            "parametersDigest": "e" * 64,
            "artifactEvidenceRef": f"artifact-evidence-{slug}-m12",
            "artifactEvidenceDigest": "4" * 64,
            "sourceRefs": [
                {
                    "sourceRef": f"generation-request-{slug}-version-1",
                    "sourceDigest": "7" * 64,
                },
                {
                    "sourceRef": f"generation-result-{slug}",
                    "sourceDigest": "8" * 64,
                },
            ],
        }
    )


def requested_provenance(
    *,
    asset_requirement_ref: str,
    asset_requirement_digest: str,
) -> dict:
    return build_requested_audio_provenance(
        {
            "originKind": "LOCAL_DETERMINISTIC_EXECUTION",
            "adapterIdentity": "v4.local-audio-test-adapter.v1",
            "parametersDigest": "2" * 64,
            "sourceRefs": [
                {
                    "sourceRef": asset_requirement_ref,
                    "sourceDigest": asset_requirement_digest,
                }
            ],
        }
    )


def artifact(slug: str, *, storage_key: str | None = None) -> dict:
    is_voice = slug == "voice"
    return {
        "artifactKind": "VOICE_PROFILE_PACKAGE" if is_voice else "PCM_AUDIO",
        "artifactEvidenceRef": f"artifact-evidence-{slug}-m12",
        "artifactEvidenceDigest": "4" * 64,
        "artifactRef": f"artifact-{slug}-m12",
        "storageKey": storage_key
        or (
            "asset-versions/audio/voice/voice-candidate.voicepkg"
            if is_voice
            else f"asset-versions/audio/{slug}/{slug}-candidate.wav"
        ),
        "byteSize": 4096,
        "fileDigest": "5" * 64,
        "mediaType": "application/octet-stream" if is_voice else "audio/wav",
    }


def common_asset_command(
    slug: str,
    *,
    rights: dict | None = None,
    provenance: dict | None = None,
    storage_key: str | None = None,
) -> dict:
    requirement_ref = f"asset-requirement-{slug}"
    requirement_digest = "6" * 64
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "assetRef": f"audio-asset-{slug}",
        "assetVersionRef": f"audio-asset-{slug}-version-1",
        "version": 1,
        "assetRequirementRef": requirement_ref,
        "assetRequirementDigest": requirement_digest,
        "generationRequestRef": f"generation-request-{slug}",
        "generationRequestVersionRef": f"generation-request-{slug}-version-1",
        "generationRequestDigest": "7" * 64,
        "generationResultRef": f"generation-result-{slug}",
        "generationResultDigest": "8" * 64,
        "artifact": artifact(slug, storage_key=storage_key),
        "supersedesAssetVersionRef": None,
        "supersedesAssetVersionDigest": None,
        "provenance": audio_provenance(slug) if provenance is None else provenance,
        "rightsBinding": (
            rights_binding(
                asset_requirement_ref=requirement_ref,
                asset_requirement_digest=requirement_digest,
            )
            if rights is None
            else rights
        ),
        "createdBy": f"v5.m12.{slug}.contract-test",
        "createdAt": "2026-08-29T12:00:00Z",
    }


def voice_asset_command(
    confirmed_voice_lock: dict,
    *,
    rights: dict | None = None,
    source_kind: str = "LOCAL_PRESET",
    consent: dict | None = None,
    subject_ref: str = "character-lin",
) -> dict:
    version = confirmed_voice_lock["voiceLockVersion"]
    command = common_asset_command("voice", rights=rights)
    command.update(
        {
            "voiceIdentityRef": confirmed_voice_lock["voiceLock"]["voiceRef"],
            "characterRef": version["characterRef"],
            "voiceLockVersionRef": version["voiceLockVersionRef"],
            "voiceLockDigest": version["payloadDigest"],
            "voiceSourceKind": source_kind,
            "voiceSourceSubjectRef": subject_ref,
            "engineRef": version["engineFamily"],
            "modelRef": version["voiceId"],
            "profilePackage": {
                "reusable": True,
                "packageKind": "LOCAL_VOICE_PROFILE",
                "packageDigest": command["artifact"]["fileDigest"],
            },
            "consentGrantRef": (
                None if consent is None else consent["consentGrantRef"]
            ),
            "consentGrantVersionRef": (
                None if consent is None else consent["consentGrantVersionRef"]
            ),
            "consentGrantDigest": (
                None if consent is None else consent["payloadDigest"]
            ),
        }
    )
    return command


def local_voice_asset(confirmed_voice_lock: dict) -> dict:
    return build_voice_asset_version(
        voice_asset_command(confirmed_voice_lock),
        confirmed_voice_lock=confirmed_voice_lock,
    )


def clone_rights(consent: dict) -> dict:
    return rights_binding(
        asset_requirement_ref="asset-requirement-voice",
        asset_requirement_digest="6" * 64,
        source_refs=[
            {
                "sourceRef": consent["consentGrantVersionRef"],
                "sourceDigest": consent["payloadDigest"],
            }
        ]
    )


def cloned_voice_asset(
    confirmed_voice_lock: dict,
    consent: dict,
    *,
    rights: dict | None = None,
    subject_ref: str = "character-lin",
) -> dict:
    """Build a sealed historical v1 read fixture without reopening v1 writes."""

    effective_rights = clone_rights(consent) if rights is None else rights
    command = voice_asset_command(
        confirmed_voice_lock,
        rights=effective_rights,
        source_kind="CLONED_WITH_CONSENT",
        consent=consent,
        subject_ref=subject_ref,
    )
    return resealed(
        {
            "schemaVersion": "v5.voice-asset-version.v1",
            "assetVersionType": "VoiceAssetVersion",
            **command,
            "assetKind": "audio",
            "audioKind": "voice",
            "state": "PROPOSED",
            "authorityState": "CONTRACT_ONLY_NOT_ADMITTED",
            "immutable": True,
            "publicationAllowed": False,
        }
    )


def cloned_voice_request_command(
    confirmed_voice_lock: dict,
    consent: dict,
    rights: dict,
) -> dict:
    version = confirmed_voice_lock["voiceLockVersion"]
    return {
        "requestKind": "VOICE_PROFILE_CREATION",
        "workspaceRef": WORKSPACE,
        "projectRef": PROJECT,
        "seriesRef": SERIES,
        "episodeRef": EPISODE,
        "productionRunRef": RUN,
        "generationRequestRef": "audio-generation-request-voice-m12",
        "generationRequestVersionRef": "audio-generation-request-voice-m12-v1",
        "version": 1,
        "supersedesGenerationRequestVersionRef": None,
        "supersedesGenerationRequestVersionDigest": None,
        "assetRequirementRef": "asset-requirement-voice",
        "assetRequirementDigest": "6" * 64,
        "outputAssetVersionType": "VoiceAssetVersion",
        "outputTarget": "ASSET_VERSION",
        "requestSpec": {
            "voiceIdentityRef": confirmed_voice_lock["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": version["voiceLockVersionRef"],
            "voiceLockDigest": version["payloadDigest"],
            "voiceSourceKind": "CLONED_WITH_CONSENT",
            "voiceSourceSubjectRef": consent["subjectRef"],
            "engineRef": version["engineFamily"],
            "modelRef": version["voiceId"],
            "profilePackageSpec": {
                "reusable": True,
                "packageKind": "LOCAL_VOICE_PROFILE",
            },
            "consentGrantRef": consent["consentGrantRef"],
            "consentGrantVersionRef": consent["consentGrantVersionRef"],
            "consentGrantDigest": consent["payloadDigest"],
        },
        "rightsBinding": rights,
        "requestedProvenance": requested_provenance(
            asset_requirement_ref="asset-requirement-voice",
            asset_requirement_digest="6" * 64,
        ),
        "createdBy": "v5.m12.voice-profile-request.contract-test",
        "createdAt": AS_OF,
    }


def speech_parameters(confirmed_voice_lock: dict, role: str) -> dict:
    return normalize_speech_parameters(
        {
            "speechSynthesis": True,
            "text": "不要动。" if role == "dialogue" else "夜色漫过长安。",
            "voiceRef": confirmed_voice_lock["voiceLock"]["voiceRef"],
            "emotionTag": "tense" if role == "dialogue" else "neutral",
            "audioRole": role,
        },
        confirmed_voice_lock=confirmed_voice_lock,
    )


def dialogue_asset(
    confirmed_voice_lock: dict,
    voice_asset: dict,
    *,
    role: str = "dialogue",
) -> dict:
    command = common_asset_command(role)
    command.update(
        {
            "speechRole": role,
            "scriptVersionRef": "script-version-m12",
            "scriptVersionDigest": "a" * 64,
            "dialogueRef": "dialogue-line-m12" if role == "dialogue" else None,
            "narrationRef": "narration-line-m12" if role == "narration" else None,
            "voiceAssetVersionRef": voice_asset["assetVersionRef"],
            "voiceAssetVersionDigest": voice_asset["payloadDigest"],
            "language": "zh-CN",
            "normalizedSpeechParameters": speech_parameters(
                confirmed_voice_lock, role
            ),
            "sourceAudioCueRefs": [],
        }
    )
    return build_dialogue_asset_version(
        command,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset,
    )


def programmatic_assets() -> dict[str, dict]:
    music = common_asset_command("music")
    music.update(
        {
            "musicSourceKind": "PROGRAMMATIC",
            "musicSpecDigest": "b" * 64,
            "sourceAudioCueRefs": [],
        }
    )
    sfx = common_asset_command("sfx")
    sfx.update(
        {
            "sfxKind": "paper",
            "synthesisSpecDigest": "c" * 64,
            "sourceAudioCueRefs": [],
        }
    )
    ambience = common_asset_command("ambience")
    ambience.update(
        {
            "ambienceKind": "rain",
            "synthesisSpecDigest": "d" * 64,
            "sourceAudioCueRefs": [],
        }
    )
    return {
        "music": build_music_asset_version(music),
        "sfx": build_sfx_asset_version(sfx),
        "ambience": build_ambience_asset_version(ambience),
    }


class M12AudioAuthorityContractTests(unittest.TestCase):
    def confirmed_voice_lock(self) -> dict:
        return voice_bundle("character-lin", "voice-lin")

    def asset_cases(self):
        confirmed = self.confirmed_voice_lock()
        voice = local_voice_asset(confirmed)
        generated = programmatic_assets()
        assets = {
            "dialogue": dialogue_asset(confirmed, voice),
            "voice": voice,
            **generated,
        }
        validators = {
            "dialogue": lambda value: validate_dialogue_asset_version(
                value,
                confirmed_voice_lock=confirmed,
                voice_asset_version=voice,
            ),
            "voice": lambda value: validate_voice_asset_version(
                value, confirmed_voice_lock=confirmed
            ),
            "music": validate_music_asset_version,
            "sfx": validate_sfx_asset_version,
            "ambience": validate_ambience_asset_version,
        }
        union_arguments = {
            "dialogue": {
                "confirmed_voice_lock": confirmed,
                "voice_asset_version": voice,
            },
            "voice": {"confirmed_voice_lock": confirmed},
            "music": {},
            "sfx": {},
            "ambience": {},
        }
        return confirmed, voice, assets, validators, union_arguments

    def test_audio_generation_request_is_exact_digest_bound_and_asset_targeted(self):
        command = {
            "requestKind": "SFX_GENERATION",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "generationRequestRef": "audio-generation-request-sfx-m12",
            "generationRequestVersionRef": "audio-generation-request-sfx-m12-v1",
            "version": 1,
            "supersedesGenerationRequestVersionRef": None,
            "supersedesGenerationRequestVersionDigest": None,
            "assetRequirementRef": "asset-requirement-sfx-m12",
            "assetRequirementDigest": "e" * 64,
            "outputAssetVersionType": "SfxAssetVersion",
            "outputTarget": "ASSET_VERSION",
            "requestSpec": {
                "sfxKind": "paper",
                "synthesisSpecDigest": "f" * 64,
                "sourceAudioCueRefs": [],
            },
            "rightsBinding": rights_binding(
                asset_requirement_ref="asset-requirement-sfx-m12",
                asset_requirement_digest="e" * 64,
            ),
            "requestedProvenance": requested_provenance(
                asset_requirement_ref="asset-requirement-sfx-m12",
                asset_requirement_digest="e" * 64,
            ),
            "createdBy": "v5.m12.audio-generation-request.contract-test",
            "createdAt": AS_OF,
        }
        request = build_audio_generation_request(command)
        validated = validate_audio_generation_request(request)
        self.assertIsInstance(validated, AudioGenerationRequest)
        self.assertEqual(validated.as_dict(), request)
        self.assertFalse(request["publicationAllowed"])
        self.assertEqual(request["outputTarget"], "ASSET_VERSION")

        tampered_digest = deepcopy(request)
        tampered_digest["payloadDigest"] = "0" * 64
        with self.assertRaises(StaleInputError):
            validate_audio_generation_request(tampered_digest)

        unknown_kind = resealed({**request, "requestKind": "UNKNOWN"})
        with self.assertRaises(AudioDomainTypeMismatchError):
            validate_audio_generation_request(unknown_kind)

        for field, value in (
            ("outputTarget", "LEGACY_MEDIA"),
            ("outputAssetVersionType", "AmbienceAssetVersion"),
        ):
            invalid = resealed({**request, field: value})
            with self.subTest(field=field), self.assertRaises(
                LegacyAudioTargetError
            ):
                validate_audio_generation_request(invalid)

        incomplete = deepcopy(command)
        incomplete.pop("assetRequirementRef")
        with self.assertRaises(EpisodeProductionError):
            build_audio_generation_request(incomplete)

    def test_five_asset_contracts_validate_independently_and_voice_is_not_lock(self):
        confirmed, voice, assets, validators, union_arguments = self.asset_cases()
        for name in (
            "AudioGenerationRequest",
            "DialogueAssetVersion",
            "VoiceAssetVersion",
            "MusicAssetVersion",
            "SfxAssetVersion",
            "AmbienceAssetVersion",
            "ConsentGrant",
            "RightsBinding",
        ):
            with self.subTest(export=name):
                self.assertIn(name, episode_production_public.__all__)
                self.assertTrue(hasattr(episode_production_public, name))
        self.assertEqual(
            {value["assetVersionType"] for value in assets.values()},
            set(AUDIO_ASSET_VERSION_TYPES),
        )
        for name, value in assets.items():
            with self.subTest(name=name):
                self.assertEqual(validators[name](value).as_dict(), value)
                self.assertEqual(
                    validate_audio_domain_asset_version(
                        value, **union_arguments[name]
                    ).as_dict(),
                    value,
                )
                self.assertEqual(value["authorityState"], "CONTRACT_ONLY_NOT_ADMITTED")
                self.assertFalse(value["publicationAllowed"])

        self.assertNotEqual(
            voice["assetVersionRef"],
            confirmed["voiceLockVersion"]["voiceLockVersionRef"],
        )
        with self.assertRaises(EpisodeProductionError):
            validate_voice_asset_version(
                confirmed,
                confirmed_voice_lock=confirmed,
            )

        narration = dialogue_asset(confirmed, voice, role="narration")
        self.assertEqual(narration["speechRole"], "narration")
        self.assertIsNone(narration["dialogueRef"])
        self.assertIsNotNone(narration["narrationRef"])

    def test_audio_kind_and_domain_validator_mismatches_fail_closed(self):
        _, _, assets, validators, _ = self.asset_cases()
        kind_ring = {
            "dialogue": "voice",
            "voice": "music",
            "music": "sfx",
            "sfx": "ambience",
            "ambience": "dialogue",
        }
        for name, value in assets.items():
            invalid = resealed({**value, "audioKind": kind_ring[name]})
            with self.subTest(name=name), self.assertRaises(
                AudioDomainTypeMismatchError
            ):
                validators[name](invalid)

        with self.assertRaises(EpisodeProductionError):
            validate_music_asset_version(assets["sfx"])
        with self.assertRaises(EpisodeProductionError):
            validate_sfx_asset_version(assets["ambience"])

    def test_rights_and_provenance_are_required_for_every_asset_type(self):
        _, _, assets, validators, _ = self.asset_cases()
        for name, value in assets.items():
            missing_provenance = resealed({**value, "provenance": None})
            with self.subTest(name=name, field="provenance"), self.assertRaises(
                AudioProvenanceRequiredError
            ):
                validators[name](missing_provenance)

            missing_rights = resealed({**value, "rightsBinding": None})
            with self.subTest(name=name, field="rightsBinding"), self.assertRaises(
                AudioRightsRequiredError
            ):
                validators[name](missing_rights)

        valid_rights = rights_binding()
        self.assertEqual(validate_rights_binding(valid_rights).as_dict(), valid_rights)

        empty_sources = resealed({**valid_rights, "sourceRefs": []})
        with self.assertRaises(EpisodeProductionError):
            validate_rights_binding(empty_sources)

        overclaim = resealed(
            {**valid_rights, "authorityState": "RIGHTS_APPROVED"}
        )
        with self.assertRaises(AudioRightsRequiredError):
            validate_rights_binding(overclaim)

        unrelated_use = resealed(
            {**assets["sfx"]["rightsBinding"], "usageScope": ["IMAGE_ONLY"]}
        )
        with self.assertRaises(AudioRightsRequiredError):
            validate_sfx_asset_version(
                resealed({**assets["sfx"], "rightsBinding": unrelated_use})
            )

        stale_provenance = resealed(
            {
                **assets["ambience"]["provenance"],
                "generationRecordRef": "generation-result-other",
            }
        )
        with self.assertRaises(StaleInputError):
            validate_ambience_asset_version(
                resealed(
                    {**assets["ambience"], "provenance": stale_provenance}
                )
            )

    def test_consent_effective_window_revocation_and_exact_binding_fail_closed(self):
        valid = consent_grant(valid_from=AS_OF)
        self.assertEqual(validate_consent_grant(valid).as_dict(), valid)
        self.assertEqual(
            require_effective_consent_grant(
                valid,
                evaluated_at=AS_OF,
                required_use=VOICE_CLONING_USE,
                expected_subject_ref="character-lin",
                expected_grant_ref=valid["consentGrantRef"],
                expected_version_ref=valid["consentGrantVersionRef"],
                expected_digest=valid["payloadDigest"],
                territory="WORLDWIDE",
            ).as_dict(),
            valid,
        )

        ineffective = {
            "revoked": consent_grant(revocation_state="REVOKED"),
            "expired": consent_grant(expires_at=AS_OF),
            "not-yet-valid": consent_grant(
                valid_from="2026-08-30T00:00:00Z",
                expires_at="2027-01-01T00:00:00Z",
            ),
            "use-not-granted": consent_grant(
                allowed_uses=["DIALOGUE_SYNTHESIS"]
            ),
        }
        for name, grant in ineffective.items():
            with self.subTest(name=name), self.assertRaises(
                AudioConsentNotEffectiveError
            ):
                require_effective_consent_grant(
                    grant,
                    evaluated_at=AS_OF,
                    required_use=VOICE_CLONING_USE,
                )

        with self.assertRaises(EpisodeProductionError):
            consent_grant(
                allowed_uses=[VOICE_CLONING_USE],
                prohibited_uses=[VOICE_CLONING_USE],
            )
        with self.assertRaises(EpisodeProductionError):
            consent_grant(valid_from="2026-08-29T00:00:00")

        for field, kwargs in (
            ("subject", {"expected_subject_ref": "character-other"}),
            ("root-ref", {"expected_grant_ref": "consent-other"}),
            ("version-ref", {"expected_version_ref": "consent-version-other"}),
            ("digest", {"expected_digest": "0" * 64}),
        ):
            with self.subTest(field=field), self.assertRaises(StaleInputError):
                require_effective_consent_grant(
                    valid,
                    evaluated_at=AS_OF,
                    required_use=VOICE_CLONING_USE,
                    **kwargs,
                )

    def test_cloned_voice_requires_consent_and_confirmed_voice_lock(self):
        confirmed = self.confirmed_voice_lock()
        consent = consent_grant()
        rights = clone_rights(consent)
        command = voice_asset_command(
            confirmed,
            rights=rights,
            source_kind="CLONED_WITH_CONSENT",
            consent=consent,
        )
        clone = cloned_voice_asset(confirmed, consent, rights=rights)
        self.assertEqual(
            validate_voice_asset_version(
                clone,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            ).as_dict(),
            clone,
        )
        with self.assertRaises(AudioDomainTypeMismatchError):
            build_voice_asset_version(
                command,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

        request_command = cloned_voice_request_command(
            confirmed,
            consent,
            rights,
        )
        request = resealed(
            {
                "schemaVersion": "v5.audio-generation-request.v1",
                **request_command,
                "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
                "immutable": True,
                "publicationAllowed": False,
            }
        )
        self.assertEqual(
            validate_audio_generation_request(
                request,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            ).as_dict(),
            request,
        )
        with self.assertRaises(AudioDomainTypeMismatchError):
            build_audio_generation_request(
                request_command,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

        with self.assertRaises(AudioConsentRequiredError):
            validate_voice_asset_version(
                clone,
                confirmed_voice_lock=confirmed,
                evaluated_at=AS_OF,
            )
        with self.assertRaises(VoiceLockNotConfirmedError):
            validate_voice_asset_version(
                clone,
                confirmed_voice_lock=None,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

        unconfirmed = deepcopy(confirmed)
        confirmation = deepcopy(unconfirmed["voiceLockConfirmation"])
        confirmation.pop("payloadDigest")
        confirmation["state"] = "CANDIDATE"
        unconfirmed["voiceLockConfirmation"] = sealed(confirmation)
        with self.assertRaises(EpisodeProductionError):
            validate_voice_asset_version(
                clone,
                confirmed_voice_lock=unconfirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

        mismatched_subject = deepcopy(clone)
        mismatched_subject["voiceSourceSubjectRef"] = "character-other"
        mismatched_subject = resealed(mismatched_subject)
        with self.assertRaises(StaleInputError):
            validate_voice_asset_version(
                mismatched_subject,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

        stale_rights = cloned_voice_asset(
            confirmed,
            consent,
            rights=rights_binding(
                asset_requirement_ref="asset-requirement-voice",
                asset_requirement_digest="6" * 64,
            ),
        )
        with self.assertRaises(StaleInputError):
            validate_voice_asset_version(
                stale_rights,
                confirmed_voice_lock=confirmed,
                consent_grant=consent,
                evaluated_at=AS_OF,
            )

    def test_expired_or_revoked_consent_cannot_build_cloned_voice(self):
        confirmed = self.confirmed_voice_lock()
        for name, consent in (
            ("revoked", consent_grant(revocation_state="REVOKED")),
            ("expired", consent_grant(expires_at=AS_OF)),
        ):
            command = voice_asset_command(
                confirmed,
                rights=clone_rights(consent),
                source_kind="CLONED_WITH_CONSENT",
                consent=consent,
            )
            with self.subTest(name=name), self.assertRaises(
                AudioDomainTypeMismatchError
            ):
                build_voice_asset_version(
                    command,
                    confirmed_voice_lock=confirmed,
                    consent_grant=consent,
                    evaluated_at=AS_OF,
                )
            historical = cloned_voice_asset(
                confirmed,
                consent,
                rights=clone_rights(consent),
            )
            with self.subTest(name=f"{name}-historical-read"), self.assertRaises(
                AudioConsentNotEffectiveError
            ):
                validate_voice_asset_version(
                    historical,
                    confirmed_voice_lock=confirmed,
                    consent_grant=consent,
                    evaluated_at=AS_OF,
                )

    def test_all_explicit_audio_outputs_reject_legacy_storage_without_mutation(self):
        _, _, assets, validators, _ = self.asset_cases()
        paths = {
            "dialogue": "jobs/request/dialogue.wav",
            "voice": "legacy/media/voice.pkg",
            "music": "media/music.wav",
            "sfx": "/asset-versions/audio/sfx.wav",
            "ambience": "asset-versions/audio/../ambience.wav",
        }
        for name, value in assets.items():
            snapshot = deepcopy(value)
            invalid = deepcopy(value)
            invalid["artifact"]["storageKey"] = paths[name]
            invalid = resealed(invalid)
            with self.subTest(name=name), self.assertRaises(
                LegacyAudioTargetError
            ):
                validators[name](invalid)
            self.assertEqual(value, snapshot)


if __name__ == "__main__":
    unittest.main()
