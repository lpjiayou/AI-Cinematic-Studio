from pathlib import Path
from hashlib import sha256
import json
import sqlite3
import tempfile
from threading import Barrier, Thread
import unittest

from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    migrate_lifecycle_database,
    validate_lifecycle_database,
)
from services.v5_core_os.script_studio.acceptance_sqlite import (
    ScriptAcceptanceMigrationError,
)
from services.v5_core_os.script_studio.foundation import (
    ScriptAcceptanceSubject,
    TrustedApprovalRequiredError,
    VerifiedScriptAcceptance,
)
from services.v5_core_os.script_studio.external_acceptance import (
    SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SCHEMA,
    ScriptAcceptanceConfigurationError,
    script_acceptance_authority_from_environment,
)
from services.v5_core_os.script_studio.public import ScriptStudioPublicError
from tests.unit.test_script_studio_m3 import (
    Refs,
    WORKSPACE,
    content_from_candidate,
    seed_episode,
)


NOW = "2026-08-26T10:00:00.000Z"


class ExactAcceptanceAuthority:
    def __init__(self, *, approval_ref="approval-k2-002-v1-4"):
        self.approval_ref = approval_ref
        self.calls = 0

    def verify(self, *, subject, approval_ref):
        self.calls += 1
        if approval_ref != self.approval_ref:
            raise TrustedApprovalRequiredError("approval was not found")
        return VerifiedScriptAcceptance.create(
            authorityRef="script-acceptance-authority-k2-002",
            approvalRef=approval_ref,
            actorRef="project-lead-lin-peng",
            actorKind="PROJECT_LEAD",
            decision="ACCEPTED",
            authorityDecisionRef="decision-acs-k2-002-script-acc3",
            authorityDecisionDigest="d" * 64,
            decidedAt="2026-08-26",
            governanceRecordRef="ACS-K2-002-SCRIPT-ACC3",
            subjectDigest=subject.subject_digest,
        )


def import_reviewed(boundary, series, episode):
    return boundary.create_version(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "changeKind": "reviewed-import",
            "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64,
            "reviewedDocumentDigest": "c" * 64,
            "importedByRef": "creator-reviewer-credential",
            "content": content_from_candidate(),
        }
    )


def acceptance_command(imported, series, episode):
    return {
        "workspaceRef": WORKSPACE,
        "seriesRef": series["seriesRef"],
        "episodeRef": episode["episodeRef"],
        "scriptRef": imported["script"]["scriptRef"],
        "scriptVersionRef": imported["scriptVersion"]["scriptVersionRef"],
        "idempotencyKey": "accept-k2-002-v1-4",
        "approvalRef": "approval-k2-002-v1-4",
    }


class ScriptAcceptanceTests(unittest.TestCase):
    def test_external_authority_requires_exact_bundle_digest_and_subject(self):
        subject = ScriptAcceptanceSubject.create(
            workspaceRef=WORKSPACE,
            seriesRef="series-1",
            episodeRef="episode-1",
            scriptRef="script-1",
            scriptVersionRef="script-version-1",
            uploadedSourceByteDigest="a" * 64,
            normalizedSourceDocumentDigest="b" * 64,
            reviewedDocumentDigest="c" * 64,
            canonicalScriptContentDigest="e" * 64,
            importProvenanceDigest="f" * 64,
        )
        bundle = {
            "schemaVersion": SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SCHEMA,
            "authorityRef": "script-acceptance-authority-k2-002",
            "approvals": [
                {
                    "subject": subject.as_mapping(),
                    "approvalRef": "approval-k2-002-v1-4",
                    "actorRef": "project-lead-lin-peng",
                    "actorKind": "PROJECT_LEAD",
                    "decision": "ACCEPTED",
                    "authorityDecisionRef": (
                        "decision-acs-k2-002-script-acc3"
                    ),
                    "authorityDecisionDigest": "d" * 64,
                    "decidedAt": "2026-08-26",
                    "governanceRecordRef": "ACS-K2-002-SCRIPT-ACC3",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authority.json"
            payload = json.dumps(
                bundle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            path.write_bytes(payload)
            authority = script_acceptance_authority_from_environment(
                {
                    "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_PATH": str(path),
                    "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SHA256": (
                        sha256(payload).hexdigest()
                    ),
                }
            )
            verified = authority.verify(
                subject=subject,
                approval_ref="approval-k2-002-v1-4",
            )
            self.assertEqual(verified.decision, "ACCEPTED")
            with self.assertRaises(ScriptAcceptanceConfigurationError):
                script_acceptance_authority_from_environment(
                    {
                        "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_PATH": str(
                            path
                        ),
                        "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SHA256": (
                            "0" * 64
                        ),
                    }
                )

    def test_default_authority_rejects_reviewed_import_acceptance(self):
        assembly = LifecycleAssembly.in_memory(ref_factory=Refs(), clock=lambda: NOW)
        series, episode = seed_episode(assembly.series_episode)
        imported = import_reviewed(assembly.script_studio, series, episode)
        with self.assertRaises(ScriptStudioPublicError) as caught:
            assembly.script_studio.accept_reviewed_import(
                acceptance_command(imported, series, episode)
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (403, "trusted_approval_required"),
        )

    def test_exact_acceptance_is_sealed_confirmed_and_idempotent(self):
        authority = ExactAcceptanceAuthority()
        assembly = LifecycleAssembly.in_memory(
            ref_factory=Refs(),
            clock=lambda: NOW,
            script_acceptance_authority=authority,
        )
        series, episode = seed_episode(assembly.series_episode)
        imported = import_reviewed(assembly.script_studio, series, episode)
        command = acceptance_command(imported, series, episode)
        accepted = assembly.script_studio.accept_reviewed_import(command)
        record = accepted["scriptAcceptance"]
        self.assertEqual(record["schemaVersion"], "v5.script-acceptance.v1")
        self.assertEqual(record["decision"], "ACCEPTED")
        self.assertEqual(record["actorKind"], "PROJECT_LEAD")
        self.assertEqual(
            record["governanceRecordRef"], "ACS-K2-002-SCRIPT-ACC3"
        )
        self.assertFalse(record["publicationAllowed"])
        self.assertEqual(
            accepted["script"]["confirmedScriptVersionRef"],
            imported["scriptVersion"]["scriptVersionRef"],
        )
        self.assertFalse(accepted["idempotentReplay"])
        replay = assembly.script_studio.accept_reviewed_import(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["scriptAcceptance"], record)
        self.assertEqual(authority.calls, 1)

        changed = {**command, "approvalRef": "approval-other"}
        with self.assertRaises(ScriptStudioPublicError) as caught:
            assembly.script_studio.accept_reviewed_import(changed)
        self.assertEqual(caught.exception.status, 409)

    def test_sqlite_acceptance_survives_restart_and_replays_without_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifecycle.sqlite3"
            migrate_lifecycle_database(path, allow_upgrade=True)
            first = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: NOW,
                script_acceptance_authority=ExactAcceptanceAuthority(),
            )
            series, episode = seed_episode(first.series_episode)
            imported = import_reviewed(first.script_studio, series, episode)
            command = acceptance_command(imported, series, episode)
            accepted = first.script_studio.accept_reviewed_import(command)

            restarted = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: "2026-08-26T11:00:00.000Z",
            )
            replay = restarted.script_studio.accept_reviewed_import(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(
                replay["scriptAcceptance"], accepted["scriptAcceptance"]
            )

            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE v5_script_acceptances "
                    "SET content_json=' '||content_json",
                )
            with self.assertRaises(ScriptStudioPublicError) as caught:
                restarted.script_studio.accept_reviewed_import(command)
            self.assertEqual(
                (caught.exception.status, caught.exception.code),
                (500, "application_error"),
            )

    def test_sqlite_validation_rejects_acceptance_detached_from_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifecycle.sqlite3"
            migrate_lifecycle_database(path, allow_upgrade=True)
            assembly = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: NOW,
                script_acceptance_authority=ExactAcceptanceAuthority(),
            )
            series, episode = seed_episode(assembly.series_episode)
            imported = import_reviewed(assembly.script_studio, series, episode)
            assembly.script_studio.accept_reviewed_import(
                acceptance_command(imported, series, episode)
            )
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE v5_scripts SET confirmed_script_version_ref=NULL"
                )
            with self.assertRaises(ScriptAcceptanceMigrationError):
                validate_lifecycle_database(path)

    def test_sqlite_validation_rejects_parent_provenance_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifecycle.sqlite3"
            migrate_lifecycle_database(path, allow_upgrade=True)
            assembly = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: NOW,
                script_acceptance_authority=ExactAcceptanceAuthority(),
            )
            series, episode = seed_episode(assembly.series_episode)
            imported = import_reviewed(assembly.script_studio, series, episode)
            assembly.script_studio.accept_reviewed_import(
                acceptance_command(imported, series, episode)
            )
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    "SELECT content_json FROM v5_script_versions"
                ).fetchone()
                content = json.loads(row[0])
                provenance = content["importProvenance"]
                provenance["reviewedDocumentDigest"] = "9" * 64
                provenance["importProvenanceDigest"] = sha256(
                    json.dumps(
                        {
                            key: value
                            for key, value in provenance.items()
                            if key != "importProvenanceDigest"
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                connection.execute(
                    "UPDATE v5_script_versions SET content_json=?",
                    (
                        json.dumps(
                            content,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            with self.assertRaises(ScriptAcceptanceMigrationError):
                validate_lifecycle_database(path)

    def test_concurrent_sqlite_acceptance_creates_one_record_and_one_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifecycle.sqlite3"
            migrate_lifecycle_database(path, allow_upgrade=True)
            authority = ExactAcceptanceAuthority()
            first = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: NOW,
                script_acceptance_authority=authority,
            )
            series, episode = seed_episode(first.series_episode)
            imported = import_reviewed(first.script_studio, series, episode)
            command = acceptance_command(imported, series, episode)
            second = LifecycleAssembly.sqlite(
                path,
                ref_factory=Refs(),
                clock=lambda: "2026-08-26T11:00:00.000Z",
                script_acceptance_authority=authority,
            )
            barrier = Barrier(2)
            results = []
            errors = []

            def accept(boundary):
                try:
                    barrier.wait(timeout=5)
                    results.append(
                        boundary.accept_reviewed_import(command)
                    )
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                Thread(target=accept, args=(first.script_studio,)),
                Thread(target=accept, args=(second.script_studio,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(
                sorted(item["idempotentReplay"] for item in results),
                [False, True],
            )
            self.assertEqual(
                results[0]["scriptAcceptance"],
                results[1]["scriptAcceptance"],
            )
            self.assertEqual(authority.calls, 1)
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_script_acceptances"
                    ).fetchone()[0],
                    1,
                )


if __name__ == "__main__":
    unittest.main()
