import json
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path

from services.v5_core_os.episode_production.external_authority import (
    ExternalAuthorityConfigurationError,
)
from services.v5_core_os.episode_production.external_media_selection_approval import (
    MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
    DigestPinnedMediaSelectionApprovalAuthority,
    media_selection_approval_authority_from_environment,
)
from services.v5_core_os.episode_production.media_candidate_review import (
    MediaSelectionApprovalRequiredError,
    MediaSelectionSubject,
    RejectingMediaSelectionApprovalAuthority,
    VerifiedMediaSelection,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)


class K2MediaSelectionApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.subject = MediaSelectionSubject.create(
            workspace_ref="workspace-media-approval",
            production_run_ref="episode-production-run-media-approval",
            revision_ref="real-video-plan-media-approval-v1",
            slot_ref="shot-0001",
            source_request_ref="generation-request-shot-0001-v1",
            source_request_digest="1" * 64,
            candidate_ref="candidate-shot-0001-v1",
            candidate_version=1,
            candidate_digest="2" * 64,
            artifact_digest="3" * 64,
            visual_qc_ref="visual-qc-shot-0001-v1",
            visual_qc_version=1,
            visual_qc_digest="4" * 64,
        )
        self.authority_ref = "media-selection-authority-project-lead-v1"
        self.approval_ref = "media-selection-approval-shot-0001-v1"
        self.actor_ref = "public-credential-project-lead"
        self.authority_decision_ref = "authority-decision-shot-0001-v1"
        self.decided_at = "2026-08-24T01:00:00Z"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _decision(self, *, decision="SELECTED", subject=None):
        selected_subject = subject or self.subject
        digest = VerifiedMediaSelection.expected_decision_digest(
            authority_ref=self.authority_ref,
            approval_ref=self.approval_ref,
            actor_ref=self.actor_ref,
            actor_kind="HUMAN",
            decision=decision,
            authority_decision_ref=self.authority_decision_ref,
            decided_at=self.decided_at,
            subject_digest=selected_subject.subject_digest,
        )
        return {
            "subject": selected_subject.as_dict(),
            "approvalRef": self.approval_ref,
            "actorRef": self.actor_ref,
            "actorKind": "HUMAN",
            "decision": decision,
            "authorityDecisionRef": self.authority_decision_ref,
            "authorityDecisionDigest": digest,
            "decidedAt": self.decided_at,
        }

    def _environment(self, bundle):
        path = Path(self.temporary_directory.name) / "media-selection.json"
        payload = json.dumps(
            bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        path.write_bytes(payload)
        return {
            "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_PATH": str(path),
            "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_SHA256": sha256(
                payload
            ).hexdigest(),
        }

    def test_exact_digest_pinned_subject_resolves_server_held_actor(self):
        environ = self._environment(
            {
                "schemaVersion": MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
                "authorityRef": self.authority_ref,
                "approvals": [self._decision()],
            }
        )
        authority = media_selection_approval_authority_from_environment(environ)
        self.assertIsInstance(
            authority, DigestPinnedMediaSelectionApprovalAuthority
        )
        resolved = authority.verify(
            subject=self.subject,
            approval_ref=self.approval_ref,
            decision="SELECTED",
        )
        self.assertEqual(resolved.actor_ref, self.actor_ref)
        self.assertEqual(resolved.authority_ref, self.authority_ref)
        self.assertEqual(resolved.subject_digest, self.subject.subject_digest)

    def test_missing_configuration_and_subject_mismatch_fail_closed(self):
        authority = media_selection_approval_authority_from_environment({})
        self.assertIsInstance(authority, RejectingMediaSelectionApprovalAuthority)
        with self.assertRaises(MediaSelectionApprovalRequiredError):
            authority.verify(
                subject=self.subject,
                approval_ref=self.approval_ref,
                decision="SELECTED",
            )

        environ = self._environment(
            {
                "schemaVersion": MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
                "authorityRef": self.authority_ref,
                "approvals": [self._decision()],
            }
        )
        configured = media_selection_approval_authority_from_environment(environ)
        changed = MediaSelectionSubject.create(
            workspace_ref=self.subject.workspace_ref,
            production_run_ref=self.subject.production_run_ref,
            revision_ref=self.subject.revision_ref,
            slot_ref=self.subject.slot_ref,
            source_request_ref=self.subject.source_request_ref,
            source_request_digest=self.subject.source_request_digest,
            candidate_ref=self.subject.candidate_ref,
            candidate_version=self.subject.candidate_version,
            candidate_digest=self.subject.candidate_digest,
            artifact_digest="5" * 64,
            visual_qc_ref=self.subject.visual_qc_ref,
            visual_qc_version=self.subject.visual_qc_version,
            visual_qc_digest=self.subject.visual_qc_digest,
        )
        with self.assertRaises(MediaSelectionApprovalRequiredError):
            configured.verify(
                subject=changed,
                approval_ref=self.approval_ref,
                decision="SELECTED",
            )
        with self.assertRaises(MediaSelectionApprovalRequiredError):
            configured.verify(
                subject=self.subject,
                approval_ref=self.approval_ref,
                decision="REJECTED",
            )

    def test_incomplete_or_tampered_configuration_is_rejected(self):
        with self.assertRaises(ExternalAuthorityConfigurationError):
            media_selection_approval_authority_from_environment(
                {
                    "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_PATH": (
                        "/tmp/media-selection-authority.json"
                    )
                }
            )

        environ = self._environment(
            {
                "schemaVersion": MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
                "authorityRef": self.authority_ref,
                "approvals": [self._decision()],
            }
        )
        environ[
            "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_SHA256"
        ] = "f" * 64
        with self.assertRaises(ExternalAuthorityConfigurationError):
            media_selection_approval_authority_from_environment(environ)

    def test_bundle_rejects_non_human_or_unsealed_decision(self):
        decision = self._decision()
        decision["actorKind"] = "SERVICE"
        environ = self._environment(
            {
                "schemaVersion": MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
                "authorityRef": self.authority_ref,
                "approvals": [decision],
            }
        )
        with self.assertRaises(ExternalAuthorityConfigurationError):
            media_selection_approval_authority_from_environment(environ)

    def test_public_boundary_maps_missing_selection_authority_to_forbidden(self):
        mapped = EpisodeProductionPublicBoundary._error(
            MediaSelectionApprovalRequiredError(
                "an external media selection authority is required"
            )
        )
        self.assertEqual(mapped.status, 403)
        self.assertEqual(mapped.code, "media_selection_approval_required")


if __name__ == "__main__":
    unittest.main()
