from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    ProductionPolicyRequiredError,
    StaticIdentityReferenceAuthority,
    StaticProviderPolicyAuthority,
    StaticRightsEvidenceAuthority,
    create_in_memory_boundary,
    create_local_development_boundary,
)
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    run_command,
    seed_k2_roots,
)


NOW = "2026-08-17T00:05:00Z"


def canonical_digest(value):
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


class TestRightsEvidenceAuthority:
    __test__ = False
    available = True

    def verify_grant(self, grant):
        return {
            "evidenceRef": grant["evidenceRef"],
            "evidenceDigest": canonical_digest(grant),
        }


class TestProviderPolicyAuthority:
    __test__ = False
    available = True

    def verify_execution(self, execution):
        media_kind = execution["mediaKind"]
        return {
            "enabled": True,
            "endpointClass": execution["endpointClass"],
            "safetyPolicyRef": execution["safetyPolicyRef"],
            "privacyMode": execution["privacyMode"],
            "gpuAttestationSupported": True,
            "providerCapabilityRef": f"provider-capability-{media_kind}-v1",
            "credentialSourceRef": f"secret-handle-{media_kind}-v1",
            "usageTermsRef": f"usage-terms-{media_kind}-v1",
            "budgetAuthorityRef": "budget-authority-k2-v1",
            "validUntil": "2027-01-01T00:00:00Z",
            "evidenceDigest": canonical_digest(execution),
        }


def approved_identity_authority():
    def item(character_ref, media_type):
        return {
            "referenceRef": f"approved-identity-{character_ref}",
            "referenceVersionRef": f"approved-identity-{character_ref}-v1",
            "contentDigest": sha256(
                f"{character_ref}:rights-cleared:v1".encode()
            ).hexdigest(),
            "mediaType": media_type,
            "rightsState": "APPROVED",
            "provenance": "AUTHORITY_APPROVED",
            "approvalRef": f"rights-approval-{character_ref}",
        }

    return StaticIdentityReferenceAuthority(
        {
            "character-lin": item("character-lin", "image"),
            "character-gu": item("character-gu", "identity-direction"),
        }
    )


def policy_command(run, identity_bundle):
    required_inputs = [
        (
            run["scriptVersionRef"],
            "SCRIPT",
            run["upstreamSnapshot"]["script"]["versionDigest"],
            ["SCRIPT"],
        )
    ]
    required_inputs.extend(
        (
            identity["reference"]["referenceVersionRef"],
            "IDENTITY_REFERENCE",
            identity["reference"]["contentDigest"],
            ["LIKENESS"],
        )
        for identity in identity_bundle["identityLock"]["identities"]
    )
    rights_entries = [
        {
            "inputRef": input_ref,
            "inputKind": input_kind,
            "contentDigest": content_digest,
            "rightsOwnerRef": f"rights-owner-{index}",
            "grantBasis": "OWNED",
            "permittedUses": [
                "AI_GENERATION",
                "DERIVATIVE_WORK",
                "PUBLICATION",
                "COMMERCIAL_USE",
            ],
            "providerProcessingAllowed": True,
            "territories": ["WORLDWIDE"],
            "validFrom": "2026-01-01T00:00:00Z",
            "validUntil": "2027-01-01T00:00:00Z",
            "attributionText": "",
            "likenessVoiceMusicScope": scope,
            "evidenceRef": f"rights-evidence-{index}",
        }
        for index, (input_ref, input_kind, content_digest, scope) in enumerate(
            required_inputs, start=1
        )
    ]
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": run["productionRunRef"],
        "idempotencyKey": "k2-production-policy-v1",
        "actorRef": "actor-project-lead",
        "productionPolicy": {
            "targetDurationFrames": 720,
            "frameRate": 24,
            "width": 1280,
            "height": 720,
            "aspectRatio": "16:9",
            "container": "mp4",
            "videoCodec": "h264",
            "audioCodec": "aac",
            "audioSampleRate": 48000,
            "language": "zh-CN",
            "currency": "USD",
            "maxTotalCostMinor": 1000,
            "maxAttemptsPerRequest": 2,
            "retentionDays": 30,
            "intendedDestinations": [
                {
                    "destinationRef": "release-destination-test",
                    "territories": ["WORLDWIDE"],
                }
            ],
            "requiredDecisionKinds": [
                "CREATIVE_DIRECTION",
                "IDENTITY_CONTINUITY",
                "TECHNICAL_QC",
                "FINAL_MASTER",
                "PUBLICATION_AUTHORIZATION",
            ],
        },
        "rightsManifest": {"entries": rights_entries},
        "providerExecutionPolicy": {
            "allowedExecutions": [
                {
                    "mediaKind": media_kind,
                    "providerId": f"provider-{media_kind}",
                    "modelId": f"model-{media_kind}-v1",
                    "region": "approved-region-1",
                    "endpointClass": "server-side-managed",
                    "safetyPolicyRef": "safety-policy-k2-v1",
                    "privacyMode": "no-training-no-retention",
                    "maximumAttempts": 2,
                    "timeoutSeconds": 300,
                    "maxCostMinor": 100,
                    "seedPolicy": "record-when-supported",
                    "gpuAttestationRequired": media_kind == "video",
                }
                for media_kind in ("image", "video", "audio")
            ]
        },
    }


class K2ProductionPolicyTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)

    def boundary(self, identity_authority, *, policy_authorities=True):
        kwargs = {
            "project_boundary": self.assembly.project_context,
            "series_episode_boundary": self.assembly.series_episode,
            "series_planning_boundary": self.assembly.series_planning,
            "script_studio_boundary": self.assembly.script_studio,
            "identity_reference_authority": identity_authority,
            "ref_factory": self.refs,
            "clock": lambda: NOW,
        }
        if policy_authorities:
            kwargs.update(
                {
                    "rights_evidence_authority": TestRightsEvidenceAuthority(),
                    "provider_policy_authority": TestProviderPolicyAuthority(),
                }
            )
        return create_in_memory_boundary(**kwargs)

    def create_and_lock(self, boundary):
        run = boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        identity = boundary.authorize_and_lock(g2_command(run))
        return run, identity

    def test_readiness_is_truthfully_blocked_before_policy(self):
        boundary = self.boundary(approved_identity_authority())
        run = boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )

        readiness = boundary.get_production_readiness(
            WORKSPACE, run["productionRunRef"]
        )["readiness"]

        self.assertEqual(readiness["state"], "BLOCKED_POLICY")
        self.assertIn("identity_lock_missing", readiness["blockers"])
        self.assertIn("rights_manifest_missing", readiness["blockers"])
        self.assertFalse(readiness["publicationAllowed"])

    def test_default_external_policy_authorities_fail_closed(self):
        boundary = self.boundary(
            approved_identity_authority(), policy_authorities=False
        )
        run, identity = self.create_and_lock(boundary)

        readiness = boundary.get_production_readiness(
            WORKSPACE, run["productionRunRef"]
        )["readiness"]
        self.assertIn("rights_evidence_authority_missing", readiness["blockers"])
        self.assertIn("provider_policy_authority_missing", readiness["blockers"])
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.record_production_policy(policy_command(run, identity))
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "production_policy_required"),
        )

    def test_static_external_authorities_bind_exact_evidence(self):
        grant = {
            "inputRef": "input-ref-1",
            "inputKind": "REFERENCE_VIDEO",
            "contentDigest": "1" * 64,
            "rightsOwnerRef": "rights-owner-1",
            "grantBasis": "LICENSED",
            "permittedUses": [
                "AI_GENERATION", "COMMERCIAL_USE", "DERIVATIVE_WORK", "PUBLICATION"
            ],
            "providerProcessingAllowed": True,
            "territories": ["WORLDWIDE"],
            "validFrom": "2026-01-01T00:00:00Z",
            "validUntil": "2027-01-01T00:00:00Z",
            "attributionText": "",
            "likenessVoiceMusicScope": ["REFERENCE_STYLE"],
            "evidenceRef": "rights-evidence-reference-video-1",
        }
        rights = StaticRightsEvidenceAuthority(
            {
                grant["evidenceRef"]: {
                    **grant,
                    "evidenceDigest": canonical_digest(grant),
                }
            }
        )
        self.assertEqual(
            rights.verify_grant(grant)["evidenceDigest"], canonical_digest(grant)
        )
        with self.assertRaises(ProductionPolicyRequiredError):
            rights.verify_grant({**grant, "rightsOwnerRef": "forged-owner"})

        execution = {
            "mediaKind": "video",
            "providerId": "provider-video",
            "modelId": "model-video-v1",
            "region": "approved-region-1",
            "endpointClass": "server-side-managed",
            "safetyPolicyRef": "safety-policy-k2-v1",
            "privacyMode": "no-training-no-retention",
            "maximumAttempts": 2,
            "timeoutSeconds": 300,
            "maxCostMinor": 100,
            "seedPolicy": "record-when-supported",
            "gpuAttestationRequired": True,
        }
        capability = {
            "enabled": True,
            "endpointClass": execution["endpointClass"],
            "safetyPolicyRef": execution["safetyPolicyRef"],
            "privacyMode": execution["privacyMode"],
            "gpuAttestationSupported": True,
            "providerCapabilityRef": "provider-capability-video-v1",
            "credentialSourceRef": "secret-handle-video-v1",
            "usageTermsRef": "usage-terms-video-v1",
            "budgetAuthorityRef": "budget-authority-k2-v1",
            "validUntil": "2027-01-01T00:00:00Z",
            "evidenceDigest": canonical_digest(execution),
        }
        providers = StaticProviderPolicyAuthority(
            {("video", "provider-video", "model-video-v1", "approved-region-1"): capability}
        )
        self.assertEqual(
            providers.verify_execution(execution)["credentialSourceRef"],
            "secret-handle-video-v1",
        )
        with self.assertRaises(ProductionPolicyRequiredError):
            providers.verify_execution({**execution, "privacyMode": "provider-training"})

    def test_local_identity_evidence_cannot_be_promoted_by_rights_claim(self):
        from tests.unit.test_episode_production_k2 import k2_identity_authority

        boundary = self.boundary(k2_identity_authority())
        run, identity = self.create_and_lock(boundary)
        readiness = boundary.get_production_readiness(
            WORKSPACE, run["productionRunRef"]
        )["readiness"]
        self.assertIn(
            "identity_reference_rights_not_approved", readiness["blockers"]
        )

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.record_production_policy(policy_command(run, identity))
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "production_policy_required"),
        )

    def test_records_closed_world_policy_and_stable_replay(self):
        boundary = self.boundary(approved_identity_authority())
        run, identity = self.create_and_lock(boundary)
        command = policy_command(run, identity)

        first = boundary.record_production_policy(command)
        replay = boundary.record_production_policy(command)

        self.assertFalse(first["idempotentReplay"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            first["policyBundle"]["payloadDigest"],
            replay["policyBundle"]["payloadDigest"],
        )
        self.assertEqual(first["policyBundle"]["state"], "POLICY_RECORDED")
        self.assertEqual(
            first["policyBundle"]["rightsManifest"]["state"],
            "RIGHTS_CLEARED",
        )
        self.assertNotIn(
            "credentialSourceRef",
            first["policyBundle"]["providerExecutionPolicy"][
                "allowedExecutions"
            ][0],
        )
        self.assertTrue(
            first["policyBundle"]["providerExecutionPolicy"][
                "allowedExecutions"
            ][0]["credentialConfigured"]
        )
        self.assertFalse(first["policyBundle"]["publicationAllowed"])
        self.assertEqual(
            first["readiness"]["state"], "BLOCKED_EXTERNAL_EVIDENCE"
        )
        self.assertIn(
            "live_provider_evidence_missing", first["readiness"]["blockers"]
        )

    def test_changed_replay_and_stale_rights_digest_fail_closed(self):
        boundary = self.boundary(approved_identity_authority())
        run, identity = self.create_and_lock(boundary)
        command = policy_command(run, identity)
        boundary.record_production_policy(command)

        changed = deepcopy(command)
        changed["productionPolicy"]["maxTotalCostMinor"] = 900
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.record_production_policy(changed)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "idempotency_conflict"),
        )

        second_boundary = self.boundary(approved_identity_authority())
        second_run, second_identity = self.create_and_lock(second_boundary)
        stale = policy_command(second_run, second_identity)
        stale["rightsManifest"]["entries"][0]["contentDigest"] = "0" * 64
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            second_boundary.record_production_policy(stale)
        self.assertEqual(
            (caught.exception.status, caught.exception.code), (409, "stale_input")
        )

    def test_all_three_media_policies_are_required(self):
        boundary = self.boundary(approved_identity_authority())
        run, identity = self.create_and_lock(boundary)
        command = policy_command(run, identity)
        command["providerExecutionPolicy"]["allowedExecutions"].pop()

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.record_production_policy(command)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "production_policy_required"),
        )

    def test_sqlite_policy_survives_restart_without_changing_run_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode-production.sqlite3"
            evidence = root / "episode-production-evidence.sqlite3"
            policy = root / "production-policy.sqlite3"
            kwargs = {
                "project_boundary": self.assembly.project_context,
                "series_episode_boundary": self.assembly.series_episode,
                "series_planning_boundary": self.assembly.series_planning,
                "script_studio_boundary": self.assembly.script_studio,
                "evidence_database_path": evidence,
                "production_policy_database_path": policy,
                "identity_reference_authority": approved_identity_authority(),
                "rights_evidence_authority": TestRightsEvidenceAuthority(),
                "provider_policy_authority": TestProviderPolicyAuthority(),
                "ref_factory": self.refs,
                "clock": lambda: NOW,
            }
            first = create_local_development_boundary(database, **kwargs)
            run = first.create_run(
                run_command(self.project, self.series, self.episode)
            )
            identity = first.authorize_and_lock(g2_command(run))
            recorded = first.record_production_policy(policy_command(run, identity))

            restored = create_local_development_boundary(
                database, initialize_if_missing=False, **kwargs
            )
            readiness = restored.get_production_readiness(
                WORKSPACE, run["productionRunRef"]
            )
            self.assertEqual(
                readiness["policyBundle"]["payloadDigest"],
                recorded["policyBundle"]["payloadDigest"],
            )
            self.assertEqual(
                readiness["readiness"]["persistenceClass"],
                "LOCAL_SQLITE_EVIDENCE",
            )

            connection = sqlite3.connect(policy)
            try:
                payload = connection.execute(
                    "SELECT payload_json FROM v5_production_policy_bundles"
                ).fetchone()[0]
                connection.execute(
                    "UPDATE v5_production_policy_bundles SET payload_json=?",
                    (payload.replace('"state":"POLICY_RECORDED"', '"state":"TAMPERED"'),),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                restored.get_production_readiness(
                    WORKSPACE, run["productionRunRef"]
                )
            self.assertEqual(caught.exception.code, "episode_production_unavailable")

    def test_sqlite_policy_schema_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production-policy.sqlite3"
            from services.v5_core_os.episode_production.production_policy import (
                SqliteProductionPolicyAdapter,
            )

            SqliteProductionPolicyAdapter(path, initialize_if_missing=True)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "ALTER TABLE v5_production_policy_bundles ADD COLUMN unexpected TEXT"
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(RepositoryUnavailableError) as caught:
                SqliteProductionPolicyAdapter(path, initialize_if_missing=False)
            self.assertEqual(caught.exception.code, "episode_production_unavailable")


if __name__ == "__main__":
    unittest.main()
