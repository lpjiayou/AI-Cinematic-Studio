"""E3H manifest-v2 input append authority and bounded lifecycle tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import input_append_authority as authority
from services.v5_core_os.episode_production import method_aware_input_assets as assets
from services.v5_core_os.episode_production import public
from services.v5_core_os.episode_production.foundation import (
    ExecutionNotAuthorizedError,
)
from tests.unit.test_method_aware_input_image_admission_e3a import (
    InputImageFixture,
    artifacts,
)
from tests.unit.test_method_aware_media_m10_m11 import (
    m10_command,
    m11_command,
    method_service,
)
from tests.unit.test_narrative_currentness_m7 import advance_m6


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def complete_input(fixture):
    intake = fixture.boundary.ingest_public_method_aware_input_candidate(
        fixture.command()
    )
    qc = fixture.boundary.record_semantic_visual_qc(
        fixture.qc_command(intake)
    )["semanticVisualQc"]
    selection = fixture.boundary.record_human_selection(
        fixture.approve(intake, qc)
    )["humanSelection"]
    admission = fixture.boundary.admit_public_method_aware_input_image(
        fixture.admission_command(selection)
    )
    return intake, qc, selection, admission


class InputAppendAuthorityBundleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        self.fixture.configure()

    def test_absent_partial_and_exact_configuration(self):
        self.assertIsInstance(
            authority.input_append_authority_from_environment({}),
            authority.RejectingInputAppendAuthority,
        )
        for name in authority.CONFIG_NAMES:
            with self.subTest(name=name), self.assertRaises(
                authority.InputAppendAuthorityConfigurationError
            ):
                authority.input_append_authority_from_environment(
                    {name: self.fixture.input_append_environment[name]}
                )
        verified = authority.input_append_authority_from_environment(
            self.fixture.input_append_environment
        ).verify(
            subject=self.fixture.input_append_subject,
            operation="TECHNICAL_INPUT_INTAKE",
        )
        self.assertEqual(
            verified.input_append_authority_ref,
            "synthetic-m10-input-append-grant",
        )
        self.assertFalse(verified.subject["dispatchAllowed"])

    def test_closed_bundle_pin_subject_and_operation_fail_closed(self):
        fixture = self.fixture
        bundle_path = Path(
            fixture.input_append_environment[authority.CONFIG_NAMES[0]]
        )
        original = bundle_path.read_bytes()
        cases = []
        unknown = deepcopy(fixture.input_append_bundle)
        unknown["unknown"] = True
        cases.append(artifacts.canonical(unknown))
        grant_unknown = deepcopy(fixture.input_append_bundle)
        grant_unknown["grants"][0]["unknown"] = True
        cases.append(artifacts.canonical(grant_unknown))
        boolean_grant_version = deepcopy(fixture.input_append_bundle)
        grant = boolean_grant_version["grants"][0]
        grant["version"] = True
        boolean_grant_version["grants"][0] = assets.sealed(
            {key: value for key, value in grant.items() if key != "payloadDigest"}
        )
        cases.append(artifacts.canonical(boolean_grant_version))
        cases.extend(
            (
                b'{"schemaVersion":1,"schemaVersion":2}',
                b'{"invalid":NaN}',
                b"[" * 70 + b"0" + b"]" * 70,
            )
        )
        for data in cases:
            with self.subTest(data=data[:50]), self.assertRaises(
                authority.InputAppendAuthorityConfigurationError
            ):
                bundle_path.write_bytes(data)
                authority.DigestPinnedInputAppendAuthority(
                    bundle_path, sha256(data).hexdigest()
                )
        bundle_path.write_bytes(original + b" ")
        with self.assertRaises(authority.InputAppendAuthorityConfigurationError):
            authority.DigestPinnedInputAppendAuthority(
                bundle_path,
                fixture.input_append_environment[authority.CONFIG_NAMES[1]],
            )

        bundle_path.write_bytes(original)
        symlink = fixture.root / "authority-link.json"
        symlink.symlink_to(bundle_path)
        with self.assertRaises(authority.InputAppendAuthorityConfigurationError):
            authority.DigestPinnedInputAppendAuthority(
                symlink, sha256(original).hexdigest()
            )
        real_parent = fixture.root / "real-authority-parent"
        real_parent.mkdir()
        nested_bundle = real_parent / "authority.json"
        nested_bundle.write_bytes(original)
        linked_parent = fixture.root / "linked-authority-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(authority.InputAppendAuthorityConfigurationError):
            authority.DigestPinnedInputAppendAuthority(
                linked_parent / "authority.json", sha256(original).hexdigest()
            )

        port = authority.DigestPinnedInputAppendAuthority(
            bundle_path, sha256(original).hexdigest()
        )
        verified = port.verify(
            subject=fixture.input_append_subject,
            operation="TECHNICAL_INPUT_INTAKE",
        )
        evidence = verified.evidence_payload(created_at="2026-09-08T06:00:01Z")
        evidence["version"] = True
        evidence = assets.sealed(
            {key: value for key, value in evidence.items() if key != "payloadDigest"}
        )
        with self.assertRaises(authority.InputAppendAuthorityConfigurationError):
            authority.validate_evidence(evidence)
        changed = deepcopy(fixture.input_append_subject)
        changed["manifestDigest"] = "f" * 64
        changed.pop("payloadDigest")
        changed = authority.seal_subject(changed)
        with self.assertRaises(ExecutionNotAuthorizedError):
            port.verify(subject=changed, operation="TECHNICAL_INPUT_INTAKE")
        with self.assertRaises(ExecutionNotAuthorizedError):
            port.verify(
                subject=fixture.input_append_subject,
                operation="EXECUTION_DISPATCH",
            )

        for field, changed_value in (
            ("shotPlanAuthorityState", "VERIFIED"),
            ("shotPlanApprovalState", "VERIFIED"),
            ("cameraContractState", "READY"),
            ("dispatchAllowed", True),
            ("providerProcessingAuthorized", True),
            ("publicationAllowed", True),
        ):
            subject = {
                key: value
                for key, value in fixture.input_append_subject.items()
                if key != "payloadDigest"
            }
            subject[field] = changed_value
            with self.subTest(field=field), self.assertRaises(
                authority.InputAppendAuthorityConfigurationError
            ):
                authority.seal_subject(subject)

    def test_operator_builder_only_creates_and_validates_bundle(self):
        fixture = self.fixture
        subject_path = fixture.root / "subject.json"
        subject_path.write_bytes(artifacts.canonical(fixture.input_append_subject))
        output_path = fixture.root / "operator-built-authority.json"
        before = fixture.records()
        command = [
            sys.executable,
            "scripts/method_aware_input_append_authority.py",
            "build",
            "--subject-path",
            str(subject_path),
            "--bundle-path",
            str(output_path),
            "--authority-ref",
            "operator-test-authority",
            "--input-append-authority-ref",
            "operator-test-grant",
            "--authority-decision-ref",
            "operator-test-decision",
            "--decided-at",
            "2026-09-08T06:10:00Z",
        ]
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        built = json.loads(result.stdout)
        validated = subprocess.run(
            [
                sys.executable,
                "scripts/method_aware_input_append_authority.py",
                "validate",
                "--bundle-path",
                str(output_path),
                "--bundle-sha256",
                built["bundleSha256"],
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["validation"], "PASS")
        self.assertEqual(fixture.records(), before)
        self.assertFalse(any("sqlite" in item.lower() for item in command))

        real_parent = fixture.root / "operator-real-parent"
        real_parent.mkdir()
        linked_parent = fixture.root / "operator-linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        rejected = subprocess.run(
            [
                *command[:-10],
                "--bundle-path",
                str(linked_parent / "must-not-write.json"),
                *command[-8:],
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertFalse((real_parent / "must-not-write.json").exists())


class ManifestV2InputLifecycleTests(unittest.TestCase):
    def test_default_v2_rejection_and_generic_review_guard_are_preserved(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure(authorize_v2=False)
        before = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            fixture.boundary.ingest_public_method_aware_input_candidate(
                fixture.command()
            )
        self.assertEqual((caught.exception.status, caught.exception.code),
                         (409, "execution_not_authorized"))
        with self.assertRaises(ExecutionNotAuthorizedError):
            fixture.review.prepare_candidate_record(
                {
                    "workspaceRef": fixture.scope["workspaceRef"],
                    "productionRunRef": fixture.scope["productionRunRef"],
                    "idempotencyKey": "generic-v2-candidate",
                }
            )
        self.assertEqual(fixture.records(), before)

        authorized = InputImageFixture(self, sqlite=True, manifest_v2=True)
        authorized.configure()
        before = authorized.records()
        with self.assertRaises(ExecutionNotAuthorizedError):
            authorized.review.prepare_candidate_record(
                {
                    "workspaceRef": authorized.scope["workspaceRef"],
                    "productionRunRef": authorized.scope["productionRunRef"],
                    "idempotencyKey": "generic-cannot-borrow-input-grant",
                }
            )
        context = authorized.input_append_authority.verify(
            subject=authorized.input_append_subject,
            operation="TECHNICAL_INPUT_INTAKE",
        )
        subject = authorized.input_append_subject
        base_candidate = {
            "workspaceRef": authorized.scope["workspaceRef"],
            "productionRunRef": authorized.scope["productionRunRef"],
            "revisionRef": "caller-chosen-receipt",
            "slotRef": subject["creativeShotVersionRef"],
            "sourceRequestRef": subject["visualExecutionRequirementRef"],
            "sourceRequestDigest": subject["visualExecutionRequirementDigest"],
            "artifactRef": subject["stagedArtifactRef"],
            "artifactDigest": subject["artifactContentDigest"],
            "artifactByteSize": subject["artifactByteSize"],
            "provenance": "IMPORTED",
        }
        for media_kind, source_assets in (
            ("IMAGE", []),
            (
                "VIDEO",
                [
                    {
                        "assetVersionRef": "caller-video-source",
                        "assetVersionDigest": "1" * 64,
                    }
                ],
            ),
        ):
            with self.subTest(media_kind=media_kind), self.assertRaises(
                ExecutionNotAuthorizedError
            ):
                authorized.review.prepare_candidate_record(
                    {
                        **base_candidate,
                        "candidateRef": "caller-chosen-" + media_kind.lower(),
                        "mediaKind": media_kind,
                        "sourceAssetVersions": source_assets,
                        "idempotencyKey": "borrowed-input-grant-" + media_kind.lower(),
                    },
                    input_append_context=context,
                )
        for operation, command in (
            (
                authorized.boundary.plan_real_images,
                {
                    **authorized.scope,
                    "idempotencyKey": "legacy-image-cannot-borrow-input-grant",
                },
            ),
            (
                authorized.boundary.record_real_video_candidates,
                {
                    **authorized.scope,
                    "idempotencyKey": "video-cannot-borrow-input-grant",
                },
            ),
            (
                authorized.boundary.ingest_public_method_aware_video_result,
                {
                    **authorized.scope,
                    "videoMethodRouteVersionRef": "unissued-video-route",
                    "videoMethodRouteDigest": "0" * 64,
                    "mediaJobRef": "unissued-media-job",
                    "mediaJobResultDigest": "0" * 64,
                    "idempotencyKey": "video-result-cannot-borrow-input-grant",
                },
            ),
        ):
            with self.subTest(operation=operation.__name__), self.assertRaises(
                public.EpisodeProductionPublicError
            ):
                operation(command)
        self.assertEqual(authorized.records(), before)

    def test_exact_four_record_intake_complete_chain_and_no_execution(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        manifest_before = deepcopy(fixture.seed["run"]["manifest"])
        before = len(fixture.records())
        intake = fixture.boundary.ingest_public_method_aware_input_candidate(
            fixture.command()
        )
        self.assertEqual(
            [item["recordKind"] for item in fixture.records()[before:]],
            [
                authority.EVIDENCE_RECORD_KIND,
                assets.RECEIPT_KIND,
                "Candidate",
                "TechnicalValidation",
            ],
        )
        receipt = intake["inputArtifactReceipt"]
        self.assertEqual(receipt["schemaVersion"], assets.RECEIPT_SCHEMA_V2)
        self.assertEqual(receipt["version"], 2)
        self.assertIn("inputAppendAuthorityRef", receipt)
        after_intake = fixture.records()
        replay = fixture.boundary.ingest_public_method_aware_input_candidate(
            fixture.command()
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(fixture.records(), after_intake)

        qc = fixture.boundary.record_semantic_visual_qc(
            fixture.qc_command(intake)
        )["semanticVisualQc"]
        selection = fixture.boundary.record_human_selection(
            fixture.approve(intake, qc)
        )["humanSelection"]
        before_admission = len(fixture.records())
        admission = fixture.boundary.admit_public_method_aware_input_image(
            fixture.admission_command(selection)
        )
        self.assertEqual(
            [item["recordKind"] for item in fixture.records()[before_admission:]],
            ["AssetAdmission", "AssetVersion"],
        )
        asset = admission["assetVersion"]
        self.assertFalse(asset["providerProcessingAuthorized"])
        self.assertFalse(asset["publicationAllowed"])
        records = fixture.records()
        linked_receipt = assets.exact_record(
            records,
            assets.RECEIPT_KIND,
            asset["sourceArtifactReceiptRef"],
            asset["sourceArtifactReceiptDigest"],
            version=None,
        )
        persisted = assets.validate_receipt_authority(linked_receipt, records)
        self.assertEqual(
            persisted["subject"], fixture.input_append_subject
        )

        plan = fixture.boundary.create_method_aware_input_plan(
            m10_command(
                fixture.seed,
                fixture.plan,
                [fixture.binding(asset)],
                key="e3h-authorized-input-plan",
            )
        )
        self.assertEqual(plan["currentness"], "CURRENT")
        self.assertEqual(plan["inputReadyCount"], 1)
        self.assertEqual(
            fixture.boundary.get_run(
                fixture.scope["workspaceRef"], fixture.scope["productionRunRef"]
            )["manifest"],
            manifest_before,
        )
        self.assertEqual(
            {
                key: manifest_before[key]
                for key in (
                    "shotPlanAuthorityState",
                    "shotPlanApprovalState",
                    "cameraContractState",
                    "dispatchAllowed",
                )
            },
            {
                "shotPlanAuthorityState": "LOCAL_STRUCTURAL_REPRESENTATION_ONLY",
                "shotPlanApprovalState": "NOT_VERIFIED",
                "cameraContractState": "NOT_READY",
                "dispatchAllowed": False,
            },
        )
        before_route = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as blocked:
            fixture.boundary.route_method_aware_videos(
                m11_command(fixture.seed, plan, key="e3h-v2-route-blocked")
            )
        self.assertEqual((blocked.exception.status, blocked.exception.code),
                         (409, "execution_not_authorized"))
        self.assertEqual(fixture.records(), before_route)
        self.assertFalse(
            any(
                item["recordKind"]
                in {"VideoMethodRouteVersion", "MethodAwareMediaJobResult"}
                for item in fixture.records()
            )
        )

    def test_wrong_subject_foreign_scope_and_stale_upstream_reject_without_writes(self):
        wrong = InputImageFixture(self, sqlite=True, manifest_v2=True)
        wrong.configure(authority_subject_changes={"manifestDigest": "f" * 64})
        before = wrong.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as mismatch:
            wrong.boundary.ingest_public_method_aware_input_candidate(wrong.command())
        self.assertEqual(mismatch.exception.code, "execution_not_authorized")
        self.assertEqual(wrong.records(), before)

        different_plan = InputImageFixture(
            self, sqlite=True, manifest_v2=True
        )
        different_plan.configure(
            authority_subject_changes={"executionMethodPlanDigest": "e" * 64}
        )
        before = different_plan.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as mismatch:
            different_plan.boundary.ingest_public_method_aware_input_candidate(
                different_plan.command()
            )
        self.assertEqual(mismatch.exception.code, "execution_not_authorized")
        self.assertEqual(different_plan.records(), before)

        foreign = InputImageFixture(self, sqlite=True, manifest_v2=True)
        foreign.configure()
        before = foreign.records()
        with self.assertRaises(public.EpisodeProductionPublicError):
            foreign.boundary.ingest_public_method_aware_input_candidate(
                {**foreign.command(), "projectRef": "foreign-project"}
            )
        with self.assertRaises(public.EpisodeProductionPublicError):
            foreign.boundary.ingest_public_method_aware_input_candidate(
                {**foreign.command(), "stagedArtifactRef": "another-image"}
            )
        self.assertEqual(foreign.records(), before)

        stale = InputImageFixture(self, sqlite=True, manifest_v2=True)
        stale.configure()
        before = stale.records()
        advance_m6(stale.seed)
        with self.assertRaises(public.EpisodeProductionPublicError) as changed:
            stale.boundary.ingest_public_method_aware_input_candidate(stale.command())
        self.assertIn(
            changed.exception.code,
            {"method_aware_input_plan_stale", "execution_not_authorized"},
        )
        self.assertEqual(stale.records(), before)

    def test_current_input_cannot_be_replayed_or_consumed_after_upstream_change(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        _, _, _, admission = complete_input(fixture)
        command = m10_command(
            fixture.seed,
            fixture.plan,
            [fixture.binding(admission["assetVersion"])],
            key="e3h-current-before-upstream-change",
        )
        created = fixture.boundary.create_method_aware_input_plan(command)
        self.assertEqual(created["currentness"], "CURRENT")
        before = fixture.records()
        advance_m6(fixture.seed)
        with self.assertRaises(public.EpisodeProductionPublicError):
            fixture.boundary.ingest_public_method_aware_input_candidate(
                fixture.command()
            )
        with self.assertRaises(public.EpisodeProductionPublicError):
            fixture.boundary.create_method_aware_input_plan(command)
        self.assertEqual(fixture.records(), before)

    def test_replay_rejects_replacement_grant_for_the_same_subject(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        command = fixture.command()
        fixture.boundary.ingest_public_method_aware_input_candidate(command)

        replacement = authority.create_grant(
            authority_ref="replacement-m10-input-append-owner",
            input_append_authority_ref="replacement-m10-input-append-grant",
            subject=fixture.input_append_subject,
            authority_decision_ref="replacement-m10-input-append-decision",
            decided_at="2026-09-08T06:01:00Z",
        )
        bundle = authority.create_bundle(
            authority_ref="replacement-m10-input-append-owner",
            grants=[replacement],
        )
        data = artifacts.canonical(bundle)
        path = fixture.root / "replacement-input-append-authority.json"
        path.write_bytes(data)
        fixture.input_append_environment = dict(
            zip(authority.CONFIG_NAMES, (str(path), sha256(data).hexdigest()))
        )
        fixture.restart()

        before = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            fixture.boundary.ingest_public_method_aware_input_candidate(command)
        self.assertEqual(caught.exception.code, "execution_not_authorized")
        self.assertEqual(fixture.records(), before)

    def test_qc_selection_authority_removal_and_tamper_stay_separate(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        intake = fixture.boundary.ingest_public_method_aware_input_candidate(
            fixture.command()
        )
        passed_qc = fixture.boundary.record_semantic_visual_qc(
            fixture.qc_command(intake)
        )["semanticVisualQc"]
        before_missing_authority = fixture.records()
        selection_command = fixture.selection_command(passed_qc)
        with self.assertRaises(public.EpisodeProductionPublicError) as missing:
            fixture.boundary.record_human_selection(selection_command)
        self.assertEqual(
            missing.exception.code, "media_selection_approval_required"
        )
        self.assertEqual(fixture.records(), before_missing_authority)

        authorized_command = fixture.approve(
            intake, passed_qc, selection_command
        )
        before_tampered_authority = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as tampered:
            fixture.boundary.record_human_selection(
                {**authorized_command, "approvalRef": "foreign-approval"}
            )
        self.assertEqual(
            tampered.exception.code, "media_selection_approval_required"
        )
        self.assertEqual(fixture.records(), before_tampered_authority)

        selected = fixture.boundary.record_human_selection(
            authorized_command
        )["humanSelection"]
        self.assertEqual(selected["decision"], "SELECTED")

        failed = InputImageFixture(self, sqlite=True, manifest_v2=True)
        failed.configure()
        failed_intake = failed.boundary.ingest_public_method_aware_input_candidate(
            failed.command()
        )
        failed_qc = failed.boundary.record_semantic_visual_qc(
            failed.qc_command(failed_intake, result="FAIL")
        )["semanticVisualQc"]
        before_selection = failed.records()
        with self.assertRaises(public.EpisodeProductionPublicError):
            failed.boundary.record_human_selection(
                failed.approve(failed_intake, failed_qc)
            )
        self.assertEqual(failed.records(), before_selection)

        fixture2 = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture2.configure()
        intake2 = fixture2.boundary.ingest_public_method_aware_input_candidate(
            fixture2.command()
        )
        before_restart = fixture2.records()
        fixture2.restart(with_input_append_authority=False)
        with self.assertRaises(public.EpisodeProductionPublicError) as removed:
            fixture2.boundary.record_semantic_visual_qc(
                fixture2.qc_command(intake2)
            )
        self.assertEqual(removed.exception.code, "execution_not_authorized")
        self.assertEqual(fixture2.records(), before_restart)

        fixture3 = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture3.configure()
        intake3 = fixture3.boundary.ingest_public_method_aware_input_candidate(
            fixture3.command()
        )
        authority_path = Path(
            fixture3.input_append_environment[authority.CONFIG_NAMES[0]]
        )
        authority_path.write_bytes(authority_path.read_bytes() + b" ")
        before_changed_bundle = fixture3.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as changed_bundle:
            fixture3.boundary.record_semantic_visual_qc(
                fixture3.qc_command(intake3)
            )
        self.assertEqual(changed_bundle.exception.code, "execution_not_authorized")
        self.assertEqual(fixture3.records(), before_changed_bundle)

    def test_sqlite_fault_rolls_back_all_four_intake_records(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        connection = sqlite3.connect(fixture.evidence.database_path)
        connection.execute(
            "CREATE TRIGGER reject_e3h_validation BEFORE INSERT ON "
            "v5_episode_production_records "
            "WHEN NEW.record_kind='TechnicalValidation' BEGIN "
            "SELECT RAISE(ABORT, 'e3h fault injection'); END"
        )
        connection.commit()
        connection.close()
        before = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError):
            fixture.boundary.ingest_public_method_aware_input_candidate(
                fixture.command()
            )
        self.assertEqual(fixture.records(), before)

    def test_concurrent_intake_has_one_four_record_atomic_winner(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        before = len(fixture.records())
        barrier = Barrier(2)
        original = fixture.evidence.append_records

        def append(records, **kwargs):
            barrier.wait(timeout=10)
            return original(records, **kwargs)

        with patch.object(
            fixture.evidence, "append_records", side_effect=append
        ), ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(
                    fixture.boundary.ingest_public_method_aware_input_candidate,
                    fixture.command(),
                )
                for _ in range(2)
            ]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len(fixture.records()) - before, 4)
        self.assertEqual(
            sorted(result["idempotentReplay"] for result in results),
            [False, True],
        )

    def test_configured_backend_cannot_escalate_input_permission(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        _, _, _, admission = complete_input(fixture)
        plan = fixture.boundary.create_method_aware_input_plan(
            m10_command(
                fixture.seed,
                fixture.plan,
                [fixture.binding(admission["assetVersion"])],
                key="e3h-ready-before-working-backend",
            )
        )

        class WorkingBackend:
            def __init__(self):
                self.dispatch_count = 0
                self.generate_count = 0

            def dispatch(self, *args, **kwargs):
                self.dispatch_count += 1
                raise AssertionError("manifest v2 input permission reached dispatch")

            def generate(self, *args, **kwargs):
                self.generate_count += 1
                raise AssertionError("manifest v2 input permission reached generation")

        backend = WorkingBackend()
        method_service(fixture.boundary).media_jobs = backend
        before = fixture.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as blocked:
            fixture.boundary.route_method_aware_videos(
                m11_command(fixture.seed, plan, key="e3h-working-backend-blocked")
            )
        self.assertEqual(blocked.exception.code, "execution_not_authorized")
        self.assertEqual((backend.dispatch_count, backend.generate_count), (0, 0))
        self.assertEqual(fixture.records(), before)


if __name__ == "__main__":
    unittest.main()
