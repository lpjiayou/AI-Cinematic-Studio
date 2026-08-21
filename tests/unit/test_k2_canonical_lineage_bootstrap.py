import copy
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from scripts import k2_canonical_lineage_bootstrap as bootstrap


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-canonical-bootstrap"
    / "k2-001-canonical-bootstrap.v1.json"
)
TEST_COMMIT = "a" * 40


def file_digests(root):
    return {
        path.name: bootstrap._sha256_file(path)
        for path in root.iterdir()
        if path.is_file()
    }


class K2CanonicalLineageBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.specification = bootstrap.validate_specification(SPECIFICATION)

    def test_checked_in_specification_has_exact_fail_closed_contract(self):
        self.assertEqual(
            self.specification.payload_sha256,
            "0dfa64aa23e7120415a58b48eb00bb5d92274518d16051f2cb419525ea3b364c",
        )
        self.assertEqual(
            self.specification.specification_sha256,
            "3b4d77b371cb23e2acf5420d74ded9d890a877f9555d781bc7842d0b715eb0ee",
        )
        self.assertEqual(
            self.specification.payload["authorization"]["priorLineageStatus"],
            "NOT_FOUND",
        )
        self.assertFalse(
            self.specification.payload["authorization"]["recoveryClaimed"]
        )
        self.assertEqual(
            self.specification.payload["productionRun"]["shotsPerScene"],
            [2, 2],
        )
        self.assertEqual(
            self.specification.payload["exitState"],
            {
                "canonicalRootStatus": "ROOTS_READY",
                "m6AuthorityStatus": "NOT_CREATED",
                "identityLockStatus": "NOT_CREATED",
                "rightsAuthorityStatus": "NOT_CONNECTED",
                "providerAuthorityStatus": "NOT_CONNECTED",
                "budgetAuthorityStatus": "NOT_CONNECTED",
                "p1Gate": "NOT_PASSED",
                "publicationAllowed": False,
            },
        )

    def test_dry_run_cli_validates_without_creating_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "canonical"
            output = StringIO()
            with redirect_stdout(output):
                exit_code = bootstrap.main(
                    [
                        "--spec",
                        str(SPECIFICATION),
                        "--target-dir",
                        str(target),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertIn("K2_CANONICAL_BOOTSTRAP_MODE=DRY_RUN_NO_WRITE", output.getvalue())
            self.assertIn("K2_CANONICAL_ROOT_STATUS=NOT_CREATED", output.getvalue())
            self.assertIn("PUBLICATION_ALLOWED=false", output.getvalue())

    def test_apply_requires_exact_acknowledgement_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "canonical"
            with self.assertRaises(bootstrap.BootstrapValidationError) as caught:
                bootstrap.apply_bootstrap(
                    self.specification,
                    target,
                    acknowledgement="YES",
                    repository_commit=TEST_COMMIT,
                )
            self.assertEqual(caught.exception.code, "exact_acknowledgement_required")
            self.assertFalse(target.exists())
            self.assertEqual(list(parent.iterdir()), [])

    def test_apply_publishes_one_private_root_with_secret_free_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "canonical"
            result = bootstrap.apply_bootstrap(
                self.specification,
                target,
                acknowledgement=bootstrap.ACKNOWLEDGEMENT,
                repository_commit=TEST_COMMIT,
            )
            self.assertEqual(result.target, target)
            self.assertTrue(target.is_dir())
            expected_files = {
                *bootstrap.DATABASE_FILENAMES.values(),
                bootstrap.RECEIPT_FILENAME,
                bootstrap.INVENTORY_FILENAME,
            }
            self.assertEqual({path.name for path in target.iterdir()}, expected_files)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            for path in target.iterdir():
                self.assertTrue(path.is_file())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            receipt_path = target / bootstrap.RECEIPT_FILENAME
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
            self.assertNotIn(str(parent), serialized)
            self.assertNotIn("林澈", serialized)
            self.assertNotIn("顾言", serialized)
            self.assertEqual(receipt["verification"]["productionRunCount"], 1)
            self.assertEqual(
                receipt["verification"]["currentLineageStatus"],
                "FOUND_READ_ONLY",
            )
            self.assertTrue(receipt["verification"]["downstreamFactTablesEmpty"])
            self.assertEqual(
                receipt["lineage"]["episodeProductionRun"]["state"],
                "ROOTS_READY",
            )
            self.assertFalse(receipt["exitState"]["publicationAllowed"])
            self.assertEqual(
                result.receipt_sha256,
                sha256(receipt_path.read_bytes()).hexdigest(),
            )

            inventory = (target / bootstrap.INVENTORY_FILENAME).read_text(
                encoding="utf-8"
            )
            inventory_paths = {
                line.split("  ", 1)[1] for line in inventory.splitlines()
            }
            self.assertEqual(
                inventory_paths,
                expected_files - {bootstrap.INVENTORY_FILENAME},
            )
            self.assertFalse(any(path.name.startswith(".canonical.staging-") for path in parent.iterdir()))

    def test_second_apply_refuses_without_modifying_canonical_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "canonical"
            bootstrap.apply_bootstrap(
                self.specification,
                target,
                acknowledgement=bootstrap.ACKNOWLEDGEMENT,
                repository_commit=TEST_COMMIT,
            )
            before = file_digests(target)
            with self.assertRaises(bootstrap.BootstrapValidationError) as caught:
                bootstrap.apply_bootstrap(
                    self.specification,
                    target,
                    acknowledgement=bootstrap.ACKNOWLEDGEMENT,
                    repository_commit=TEST_COMMIT,
                )
            self.assertEqual(caught.exception.code, "target_already_exists")
            self.assertEqual(file_digests(target), before)

    def test_prepublication_failure_removes_private_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "canonical"
            with patch.object(
                bootstrap,
                "_readonly_scan_verify",
                side_effect=bootstrap.BootstrapApplyError("injected_scan_failure"),
            ):
                with self.assertRaises(bootstrap.BootstrapApplyError) as caught:
                    bootstrap.apply_bootstrap(
                        self.specification,
                        target,
                        acknowledgement=bootstrap.ACKNOWLEDGEMENT,
                        repository_commit=TEST_COMMIT,
                    )
            self.assertEqual(caught.exception.code, "injected_scan_failure")
            self.assertFalse(target.exists())
            self.assertEqual(list(parent.iterdir()), [])

    def test_atomic_publish_does_not_replace_a_competing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "canonical"
            original = bootstrap._rename_noreplace

            def competing_publish(source, destination):
                destination.mkdir(mode=0o700)
                (destination / "owner-marker").write_text("external", encoding="utf-8")
                original(source, destination)

            with patch.object(bootstrap, "_rename_noreplace", competing_publish):
                with self.assertRaises(bootstrap.BootstrapApplyError) as caught:
                    bootstrap.apply_bootstrap(
                        self.specification,
                        target,
                        acknowledgement=bootstrap.ACKNOWLEDGEMENT,
                        repository_commit=TEST_COMMIT,
                    )
            self.assertEqual(caught.exception.code, "target_already_exists")
            self.assertEqual(
                (target / "owner-marker").read_text(encoding="utf-8"),
                "external",
            )
            self.assertFalse(any(path.name.startswith(".canonical.staging-") for path in parent.iterdir()))

    def test_tampered_payload_is_rejected_before_any_target_write(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            value = copy.deepcopy(self.specification.value)
            value["payload"]["exitState"]["p1Gate"] = "PASSED"
            tampered = parent / "tampered.json"
            tampered.write_text(
                json.dumps(value, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(bootstrap.BootstrapValidationError) as caught:
                bootstrap.validate_specification(tampered)
            self.assertEqual(caught.exception.code, "payload_digest_mismatch")
            self.assertEqual({path.name for path in parent.iterdir()}, {"tampered.json"})

    def test_operator_has_no_test_v4_v3_or_direct_sql_dependency(self):
        source = (REPOSITORY_ROOT / "scripts" / "k2_canonical_lineage_bootstrap.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "from tests",
            "import tests",
            "services.v4",
            "services.v3",
            "import sqlite3",
            "sqlite3.connect",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("LifecycleAssembly.sqlite", source)
        self.assertIn("create_episode_plan_item_binding_version", source)
        self.assertIn("k2_readonly_lineage_scan.scan", source)


if __name__ == "__main__":
    unittest.main()
