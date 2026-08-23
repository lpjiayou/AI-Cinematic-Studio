from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from services.v5_core_os.episode_production import public as production_public
from services.v5_core_os.episode_production.delivery import (
    APPROVAL_KINDS,
    APPROVAL_SCHEMA_VERSION,
    ApprovalRequiredError,
    ApprovalSubject,
    K2DeliveryService,
    RejectingApprovalAuthority,
    VerifiedApproval,
)
from services.v5_core_os.episode_production.external_authority import (
    ExternalAuthorityConfigurationError,
)
from services.v5_core_os.episode_production.external_delivery_approval import (
    DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
    DigestPinnedDeliveryApprovalAuthority,
    delivery_approval_authority_from_environment,
)


WORKSPACE = "workspace-k2"
RUN_REF = "episode-production-run-k2-1"
AUTHORITY_REF = "delivery-approval-authority-k2-v1"
ACTOR_REF = "actor-project-lead"
DECIDED_AT = "2026-08-23T03:04:05Z"


def _subject(kind: str, *, qc_digest: str = "3" * 64) -> ApprovalSubject:
    return ApprovalSubject.create(
        workspace_ref=WORKSPACE,
        production_run_ref=RUN_REF,
        kind=kind,
        timeline_version_ref="timeline-version-k2-v1",
        timeline_digest="1" * 64,
        preview_candidate_version_ref="preview-candidate-version-k2-v1",
        preview_candidate_digest="2" * 64,
        qc_report_ref="qc-report-k2-v1",
        qc_report_digest=qc_digest,
    )


def _approval(subject: ApprovalSubject, ordinal: int) -> dict:
    approval_ref = f"approval-{ordinal}"
    authority_decision_ref = f"authority-decision-{ordinal}"
    return {
        "subject": subject.as_dict(),
        "approvalRef": approval_ref,
        "actorRef": ACTOR_REF,
        "authorityType": "HUMAN",
        "decision": "ACCEPT",
        "authorityDecisionRef": authority_decision_ref,
        "authorityDecisionDigest": VerifiedApproval.expected_decision_digest(
            authority_ref=AUTHORITY_REF,
            approval_ref=approval_ref,
            actor_ref=ACTOR_REF,
            kind=subject.kind,
            authority_type="HUMAN",
            decision="ACCEPT",
            authority_decision_ref=authority_decision_ref,
            decided_at=DECIDED_AT,
            subject_digest=subject.subject_digest,
        ),
        "decidedAt": DECIDED_AT,
    }


def _bundle(approvals: list[dict]) -> dict:
    return {
        "schemaVersion": DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,
        "authorityRef": AUTHORITY_REF,
        "approvals": approvals,
    }


def _write(path: Path, value: dict) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(payload)
    return sha256(payload).hexdigest()


def _environment(path: Path, digest: str) -> dict[str, str]:
    return {
        "CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_PATH": str(path),
        "CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SHA256": digest,
    }


class _Evidence:
    def __init__(self) -> None:
        self.gates: dict[str, dict] = {}

    def get_gate(self, workspace_ref: str, run_ref: str, gate_name: str):
        del workspace_ref, run_ref
        value = self.gates.get(gate_name)
        return deepcopy(value) if value is not None else None

    def append_gate(self, gate):
        value = {
            "workspaceRef": gate.workspaceRef,
            "productionRunRef": gate.productionRunRef,
            "gateName": gate.gateName,
            "idempotencyKey": gate.idempotencyKey,
            "rootPayloadDigest": gate.rootPayloadDigest,
            "requestDigest": gate.requestDigest,
            "fromState": gate.fromState,
            "toState": gate.toState,
            "createdAt": gate.createdAt,
            "facts": [
                {
                    "factKind": fact.factKind,
                    "factRef": fact.factRef,
                    "factVersion": fact.factVersion,
                    "payload": deepcopy(dict(fact.payload)),
                    "payloadDigest": fact.payloadDigest,
                }
                for fact in gate.facts
            ],
        }
        self.gates[gate.gateName] = value
        return deepcopy(value), False


class _Refs:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-k2-{self.counts[prefix]}"


class _Composition:
    artifact_root = Path("/tmp/k2-delivery-approval-test-artifacts")

    def finalize(self, command):
        del command
        return {
            "storageKey": "master.mp4",
            "byteSize": 101,
            "sha256": "4" * 64,
        }


def _verified_fixture():
    timeline = {
        "timelineVersionRef": "timeline-version-k2-v1",
        "payloadDigest": "1" * 64,
    }
    preview = {
        "previewCandidateVersionRef": "preview-candidate-version-k2-v1",
        "payloadDigest": "2" * 64,
        "sha256": "4" * 64,
        "storageKey": "preview.mp4",
    }
    qc = {
        "qcReportRef": "qc-report-k2-v1",
        "payloadDigest": "3" * 64,
    }
    verified = {
        "root": {
            "payloadDigest": "5" * 64,
            "episodeRef": "episode-k2",
        }
    }
    return verified, timeline, preview, qc


class DeliveryApprovalSubjectTests(unittest.TestCase):
    def test_subject_is_closed_world_and_digest_bound(self):
        subject = _subject(APPROVAL_KINDS[0])
        self.assertEqual(ApprovalSubject.from_mapping(subject.as_dict()), subject)

        extra = subject.as_dict()
        extra["displayName"] = "not-authority"
        with self.assertRaises(ApprovalRequiredError):
            ApprovalSubject.from_mapping(extra)

        changed = subject.as_dict()
        changed["qcReportDigest"] = "9" * 64
        with self.assertRaises(ApprovalRequiredError):
            ApprovalSubject.from_mapping(changed)


class DigestPinnedDeliveryApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "delivery-approvals.json"

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_is_rejecting_and_partial_or_tampered_config_fails(self):
        authority = delivery_approval_authority_from_environment({})
        self.assertIsInstance(authority, RejectingApprovalAuthority)
        with self.assertRaises(ApprovalRequiredError):
            authority.verify(
                subject=_subject(APPROVAL_KINDS[0]),
                approval_ref="approval-1",
                actor_ref=ACTOR_REF,
            )

        with self.assertRaises(ExternalAuthorityConfigurationError):
            delivery_approval_authority_from_environment(
                {
                    "CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_PATH": str(
                        self.path
                    )
                }
            )

        digest = _write(
            self.path,
            _bundle([_approval(_subject(APPROVAL_KINDS[0]), 1)]),
        )
        environment = _environment(self.path, digest)
        environment["CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SHA256"] = (
            "9" * 64
        )
        with self.assertRaises(ExternalAuthorityConfigurationError):
            delivery_approval_authority_from_environment(environment)

    def test_exact_subject_and_actor_resolve_auditable_human_decision(self):
        subject = _subject(APPROVAL_KINDS[0])
        digest = _write(self.path, _bundle([_approval(subject, 1)]))
        authority = delivery_approval_authority_from_environment(
            _environment(self.path, digest)
        )
        self.assertIsInstance(authority, DigestPinnedDeliveryApprovalAuthority)
        decision = authority.verify(
            subject=subject,
            approval_ref="approval-1",
            actor_ref=ACTOR_REF,
        )
        self.assertEqual(decision.authority_type, "HUMAN")
        self.assertEqual(decision.decision, "ACCEPT")
        self.assertEqual(decision.subject_digest, subject.subject_digest)
        self.assertEqual(decision.decided_at, DECIDED_AT)

        with self.assertRaises(ApprovalRequiredError):
            authority.verify(
                subject=_subject(APPROVAL_KINDS[0], qc_digest="8" * 64),
                approval_ref="approval-1",
                actor_ref=ACTOR_REF,
            )
        with self.assertRaises(ApprovalRequiredError):
            authority.verify(
                subject=subject,
                approval_ref="approval-1",
                actor_ref="actor-impostor",
            )

    def test_bundle_rejects_unknown_fields_non_human_and_bad_decision_digest(self):
        subject = _subject(APPROVAL_KINDS[0])
        for mutate in (
            lambda value: value["approvals"][0].update(
                {"clientRole": "OWNER"}
            ),
            lambda value: value["approvals"][0].update(
                {"authorityType": "EXTERNAL_POLICY"}
            ),
            lambda value: value["approvals"][0].update(
                {"authorityDecisionDigest": "9" * 64}
            ),
        ):
            with self.subTest(mutate=mutate):
                value = _bundle([_approval(subject, 1)])
                mutate(value)
                digest = _write(self.path, value)
                with self.assertRaises(ExternalAuthorityConfigurationError):
                    delivery_approval_authority_from_environment(
                        _environment(self.path, digest)
                    )

    def test_environment_factory_injects_exact_authority(self):
        subject = _subject(APPROVAL_KINDS[0])
        digest = _write(self.path, _bundle([_approval(subject, 1)]))
        environment = _environment(self.path, digest)
        environment["CREATOR_EPISODE_PRODUCTION_DATA_PATH"] = str(
            Path(self.temporary.name) / "episode-production.sqlite3"
        )
        sentinel = object()
        with patch.object(
            production_public,
            "create_local_development_boundary",
            return_value=sentinel,
        ) as create_boundary:
            result = (
                production_public.create_local_development_boundary_from_environment(
                    project_boundary=object(),
                    series_episode_boundary=object(),
                    series_planning_boundary=object(),
                    script_studio_boundary=object(),
                    environ=environment,
                )
            )
        self.assertIs(result, sentinel)
        self.assertIsInstance(
            create_boundary.call_args.kwargs["approval_authority"],
            DigestPinnedDeliveryApprovalAuthority,
        )


class DeliveryApprovalPersistenceTests(unittest.TestCase):
    def test_delivery_persists_exact_subject_and_authority_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery-approvals.json"
            subjects = {
                kind: _subject(kind) for kind in APPROVAL_KINDS
            }
            approvals = [
                _approval(subjects[kind], ordinal)
                for ordinal, kind in enumerate(APPROVAL_KINDS, start=1)
            ]
            digest = _write(path, _bundle(approvals))
            authority = delivery_approval_authority_from_environment(
                _environment(path, digest)
            )
            evidence = _Evidence()
            service = K2DeliveryService(
                Mock(),
                evidence,
                _Composition(),
                authority,
                ref_factory=_Refs(),
                clock=lambda: "2026-08-23T03:05:00Z",
            )
            service._verified_preview_qc = Mock(  # type: ignore[method-assign]
                return_value=_verified_fixture()
            )
            service._verify_artifact = Mock(  # type: ignore[method-assign]
                return_value=(Path("/tmp/master.mp4"), {"streams": []})
            )
            command = {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN_REF,
                "idempotencyKey": "delivery-approval-exact-subject-v1",
                "decisions": [
                    {
                        "kind": kind,
                        "decision": "ACCEPT",
                        "approvalRef": f"approval-{ordinal}",
                        "actorRef": ACTOR_REF,
                    }
                    for ordinal, kind in enumerate(APPROVAL_KINDS, start=1)
                ],
            }

            result = service.approve_and_finalize(command)
            self.assertEqual(result["state"], "MASTER_READY")
            self.assertEqual(len(result["approvalDecisions"]), 4)
            for decision in result["approvalDecisions"]:
                subject = subjects[decision["kind"]]
                self.assertEqual(decision["schemaVersion"], APPROVAL_SCHEMA_VERSION)
                self.assertEqual(decision["subjectDigest"], subject.subject_digest)
                self.assertEqual(decision["authorityRef"], AUTHORITY_REF)
                self.assertEqual(decision["authorityType"], "HUMAN")
                self.assertEqual(
                    decision["authorityDecidedAt"], DECIDED_AT
                )
                self.assertEqual(
                    decision["authorityDecisionDigest"],
                    VerifiedApproval.expected_decision_digest(
                        authority_ref=decision["authorityRef"],
                        approval_ref=decision["approvalRef"],
                        actor_ref=decision["actorRef"],
                        kind=decision["kind"],
                        authority_type=decision["authorityType"],
                        decision=decision["decision"],
                        authority_decision_ref=decision[
                            "authorityDecisionRef"
                        ],
                        decided_at=decision["authorityDecidedAt"],
                        subject_digest=decision["subjectDigest"],
                    ),
                )

            service.approval_authority = RejectingApprovalAuthority()
            replay = service.approve_and_finalize(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(
                replay["approvalDecisions"], result["approvalDecisions"]
            )


if __name__ == "__main__":
    unittest.main()
