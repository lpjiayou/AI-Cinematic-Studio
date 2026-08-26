from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract
from services.v5_core_os.lifecycle_integrity import migrate_lifecycle_database


ROOT = Path(__file__).resolve().parents[2]


class CanonicalRegistrationContractTests(unittest.TestCase):
    def test_public_resources_are_generic_and_m4_declared(self):
        self.assertEqual(
            public_contract.PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
            "/creator/api/v1/canonical-registrations",
        )
        self.assertEqual(
            public_contract.PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
            "/creator/api/v1/canonical-registrations/preflight",
        )
        m4 = public_contract.capability_payload()["capabilities"][3]
        self.assertIn("canonical-registrations", m4["publicResources"])
        self.assertIn(
            "canonical-registrations/preflight", m4["publicResources"]
        )

    def test_v5_implementation_contains_no_project_specific_authority(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (
                    ROOT
                    / "services"
                    / "v5_core_os"
                    / "canonical_registration"
                ).glob("*.py")
            )
        )
        self.assertNotIn("K2-001", source)
        self.assertNotIn("K2-002", source)
        self.assertNotIn("GPU", source)
        self.assertNotIn("provider", source.casefold())

    def test_receipt_is_same_database_foreign_keyed_and_nonpublishing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifecycle.sqlite3"
            migrate_lifecycle_database(path, allow_upgrade=True)
            connection = sqlite3.connect(path)
            try:
                sql = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' "
                    "AND name='v5_canonical_registrations'"
                ).fetchone()[0]
                parents = {
                    row[2]
                    for row in connection.execute(
                        "PRAGMA foreign_key_list(v5_canonical_registrations)"
                    )
                }
            finally:
                connection.close()
        self.assertIn("CHECK(publication_allowed = 0)", sql)
        self.assertEqual(
            parents,
            {
                "v5_project_series_relationships",
                "v5_episode_projects",
                "v5_confirmed_creative_plans",
                "v5_script_acceptances",
            },
        )


if __name__ == "__main__":
    unittest.main()
