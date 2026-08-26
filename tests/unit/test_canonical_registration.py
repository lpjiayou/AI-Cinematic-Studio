from pathlib import Path
import shutil
import sqlite3
import tempfile
from threading import Barrier, Lock, Thread
import unittest

from services.v5_core_os.canonical_registration.public import (
    CanonicalRegistrationPublicError,
)
from services.v5_core_os.canonical_registration.migration import (
    CanonicalRegistrationMigrationError,
)
from services.v5_core_os.lifecycle_integrity.migration import (
    LifecycleMigrationError,
)
from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    migrate_lifecycle_database,
    validate_lifecycle_database,
)
from services.v5_core_os.script_studio.foundation import (
    ScriptAcceptanceSubject,
    TrustedApprovalRequiredError,
    VerifiedScriptAcceptance,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_script_studio_m3 import content_from_candidate


NOW = "2026-08-26T12:00:00.000Z"
WORKSPACE = "workspace-canonical-registration"
TARGET = "canonical-target-ep01-test"


def registration_command():
    return {
        "workspaceRef": WORKSPACE,
        "importedByRef": "credential-canonical-operator",
        "registrationKey": "project-changan-ep01",
        "idempotencyKey": "register-changan-ep01-v1",
        "packageDigest": "9" * 64,
        "contentProfileRef": "profile-vertical-cinematic",
        "series": {
            "title": "长安刮痕",
            "description": "独立系列",
            "plannedEpisodeCount": 30,
        },
        "project": {
            "title": "长安刮痕 EP01",
            "description": "EP01 canonical project roots",
            "targetPlatform": "internal-content-lab",
            "aspectRatio": "11:20",
            "defaultDurationSec": 30,
            "plannedEpisodeCount": 30,
        },
        "creativePlan": {
            "sourcePlanRef": "reviewed-plan-v1-4",
            "sourcePlanSchemaVersion": "creator.ai-director.plan.v1",
            "sourcePlanVersion": 1,
            "brief": valid_brief(),
            "sourcePlan": valid_plan(),
        },
        "episode": {
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "雨夜验伤",
        },
        "reviewedScript": {
            "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64,
            "reviewedDocumentDigest": "c" * 64,
            "content": content_from_candidate(),
        },
        "acceptance": {
            "idempotencyKey": "accept-changan-ep01-v1-4",
            "approvalRef": "approval-changan-ep01-v1-4",
        },
    }


class ExactSubjectAuthority:
    def __init__(self, subject):
        self.subject = subject
        self.calls = 0
        self._lock = Lock()

    def verify(self, *, subject, approval_ref):
        with self._lock:
            self.calls += 1
        if subject != self.subject or approval_ref != (
            "approval-changan-ep01-v1-4"
        ):
            raise TrustedApprovalRequiredError("approval was not found")
        return VerifiedScriptAcceptance.create(
            authorityRef="authority-canonical-registration-test",
            approvalRef=approval_ref,
            actorRef="project-lead-test",
            actorKind="PROJECT_LEAD",
            decision="ACCEPTED",
            authorityDecisionRef="decision-changan-ep01-v1-4",
            authorityDecisionDigest="d" * 64,
            decidedAt="2026-08-26",
            governanceRecordRef="ACS-K2-002-SCRIPT-ACC3",
            subjectDigest=subject.subject_digest,
        )


def subject_from_preflight(preflight):
    return ScriptAcceptanceSubject.create(
        **{
            key: value
            for key, value in preflight["scriptAcceptanceSubject"].items()
            if key != "schemaVersion"
        }
    )


class CanonicalRegistrationTests(unittest.TestCase):
    def create_database(self, directory):
        path = Path(directory) / "lifecycle.sqlite3"
        migrate_lifecycle_database(path, allow_upgrade=True)
        return path

    def preflight(self, path):
        assembly = LifecycleAssembly.sqlite(
            path,
            canonical_target_ref=TARGET,
            clock=lambda: NOW,
        )
        return assembly.canonical_registration.preflight(
            registration_command()
        )

    def test_preflight_is_zero_write_and_apply_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            self.assertEqual(preflight["canonicalMutationCount"], 0)
            self.assertFalse(preflight["publicationAllowed"])
            with sqlite3.connect(path) as connection:
                for table in (
                    "v5_series",
                    "v5_projects",
                    "v5_episode_projects",
                    "v5_script_versions",
                    "v5_script_acceptances",
                    "v5_canonical_registrations",
                ):
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0],
                        0,
                    )

            authority = ExactSubjectAuthority(subject_from_preflight(preflight))
            first = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=authority,
                clock=lambda: NOW,
            )
            applied = first.canonical_registration.register(
                registration_command()
            )
            self.assertFalse(applied["idempotentReplay"])
            self.assertFalse(applied["registration"]["publicationAllowed"])
            self.assertEqual(
                applied["registrationReceipt"]["requestDigest"],
                preflight["requestDigest"],
            )
            self.assertEqual(
                applied["registration"]["scriptVersionRef"],
                preflight["scriptVersionRef"],
            )
            validate_lifecycle_database(path)

            restarted = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                clock=lambda: "2026-08-26T13:00:00.000Z",
            )
            replay = restarted.canonical_registration.register(
                registration_command()
            )
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["registration"], applied["registration"])
            self.assertEqual(
                replay["registrationReceipt"],
                applied["registrationReceipt"],
            )
            self.assertEqual(authority.calls, 1)

    def test_changed_replay_conflicts_without_new_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            assembly.canonical_registration.register(registration_command())
            changed = registration_command()
            changed["project"]["title"] = "changed"
            with self.assertRaises(CanonicalRegistrationPublicError) as caught:
                assembly.canonical_registration.register(changed)
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (409, "idempotency_conflict"),
            )
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_canonical_registrations"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_series"
                    ).fetchone()[0],
                    1,
                )

    def test_exact_acceptance_subject_seals_the_whole_registration_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            original_preview = self.preflight(path)
            changed = registration_command()
            changed["project"]["title"] = "changed-before-first-apply"
            preview_assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                clock=lambda: NOW,
            )
            changed_preview = preview_assembly.canonical_registration.preflight(
                changed
            )
            self.assertNotEqual(
                changed_preview["scriptAcceptanceSubject"],
                original_preview["scriptAcceptanceSubject"],
            )
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(original_preview)
                ),
                clock=lambda: NOW,
            )
            with self.assertRaises(CanonicalRegistrationPublicError) as caught:
                assembly.canonical_registration.register(changed)
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (403, "trusted_approval_required"),
            )
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_series"
                    ).fetchone()[0],
                    0,
                )

    def test_target_digest_binds_preflight_to_one_physical_store(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.sqlite3"
            second_path = Path(directory) / "second.sqlite3"
            migrate_lifecycle_database(first_path, allow_upgrade=True)
            migrate_lifecycle_database(second_path, allow_upgrade=True)
            first = LifecycleAssembly.sqlite(
                first_path,
                canonical_target_ref=TARGET,
                clock=lambda: NOW,
            ).canonical_registration.preflight(registration_command())
            second = LifecycleAssembly.sqlite(
                second_path,
                canonical_target_ref=TARGET,
                clock=lambda: NOW,
            ).canonical_registration.preflight(registration_command())
            self.assertNotEqual(
                first["canonicalTargetDigest"],
                second["canonicalTargetDigest"],
            )
            self.assertNotEqual(
                first["scriptAcceptanceSubject"],
                second["scriptAcceptanceSubject"],
            )

    def test_fault_before_receipt_rolls_back_every_domain_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)

            def fault(point):
                if point == "before-registration-receipt":
                    raise RuntimeError("registration receipt fault")

            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                canonical_registration_fault_hook=fault,
                clock=lambda: NOW,
            )
            with self.assertRaises(CanonicalRegistrationPublicError) as caught:
                assembly.canonical_registration.register(registration_command())
            self.assertEqual(caught.exception.status, 500)
            with sqlite3.connect(path) as connection:
                for table in (
                    "v5_series",
                    "v5_projects",
                    "v5_confirmed_creative_plans",
                    "v5_episode_projects",
                    "v5_script_versions",
                    "v5_script_acceptances",
                    "v5_canonical_registrations",
                ):
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0],
                        0,
                    )
            recovered = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            self.assertFalse(
                recovered.canonical_registration.register(
                    registration_command()
                )["idempotentReplay"]
            )

    def test_concurrent_exact_apply_creates_one_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            authority = ExactSubjectAuthority(subject_from_preflight(preflight))
            first = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=authority,
                clock=lambda: NOW,
            )
            second = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=authority,
                clock=lambda: NOW,
            )
            barrier = Barrier(2)
            results = []
            errors = []

            def apply(boundary):
                try:
                    barrier.wait(timeout=5)
                    results.append(boundary.register(registration_command()))
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                Thread(target=apply, args=(first.canonical_registration,)),
                Thread(target=apply, args=(second.canonical_registration,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertEqual(errors, [])
            self.assertEqual(
                sorted(item["idempotentReplay"] for item in results),
                [False, True],
            )
            self.assertEqual(
                results[0]["registrationReceipt"],
                results[1]["registrationReceipt"],
            )
            self.assertEqual(authority.calls, 1)

    def test_apply_requires_explicit_durable_target(self):
        assembly = LifecycleAssembly.in_memory(clock=lambda: NOW)
        with self.assertRaises(CanonicalRegistrationPublicError) as caught:
            assembly.canonical_registration.register(registration_command())
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (503, "canonical_registration_unavailable"),
        )

    def test_additive_migration_is_explicit_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "DROP INDEX ix_canonical_registration_episode_parent"
                )
                connection.execute("DROP TABLE v5_canonical_registrations")
                connection.execute(
                    "DROP TABLE v5_canonical_registration_schema"
                )
            before = path.read_bytes()
            with self.assertRaises(LifecycleMigrationError):
                migrate_lifecycle_database(path, allow_upgrade=False)
            self.assertEqual(path.read_bytes(), before)

            def fault(point):
                if point == "before-canonical-registration-marker":
                    raise RuntimeError("canonical registration migration fault")

            with self.assertRaisesRegex(
                RuntimeError, "canonical registration migration fault"
            ):
                migrate_lifecycle_database(
                    path, allow_upgrade=True, fault=fault
                )
            with sqlite3.connect(path) as connection:
                objects = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE "
                        "name LIKE '%canonical_registration%'"
                    )
                }
            self.assertEqual(objects, set())
            self.assertEqual(
                migrate_lifecycle_database(path, allow_upgrade=True),
                "upgrade",
            )
            validate_lifecycle_database(path)

    def test_restart_validation_rejects_receipt_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            assembly.canonical_registration.register(registration_command())
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE v5_canonical_registrations "
                    "SET receipt_digest=?",
                    ("0" * 64,),
                )
            with self.assertRaises(CanonicalRegistrationMigrationError):
                validate_lifecycle_database(path)

    def test_restart_validation_rejects_registered_parent_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            assembly.canonical_registration.register(registration_command())
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE v5_projects SET title=?",
                    ("drifted after registration",),
                )
            with self.assertRaises(CanonicalRegistrationMigrationError):
                validate_lifecycle_database(path)

    def test_project_archive_preserves_registration_restart_validity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            applied = assembly.canonical_registration.register(
                registration_command()
            )
            assembly.project_context.archive_project(
                WORKSPACE, applied["registration"]["projectRef"]
            )
            validate_lifecycle_database(path)
            restarted = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                clock=lambda: NOW,
            )
            replay = restarted.canonical_registration.register(
                registration_command()
            )
            self.assertTrue(replay["idempotentReplay"])

    def test_restart_validation_rejects_database_copy_as_same_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.create_database(directory)
            preflight = self.preflight(path)
            assembly = LifecycleAssembly.sqlite(
                path,
                canonical_target_ref=TARGET,
                script_acceptance_authority=ExactSubjectAuthority(
                    subject_from_preflight(preflight)
                ),
                clock=lambda: NOW,
            )
            assembly.canonical_registration.register(registration_command())
            copied = Path(directory) / "copied.sqlite3"
            shutil.copyfile(path, copied)
            with self.assertRaises(CanonicalRegistrationMigrationError):
                validate_lifecycle_database(copied)


if __name__ == "__main__":
    unittest.main()
