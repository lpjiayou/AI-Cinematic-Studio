"""D1 existing-store path wiring; no real data, network or Owner approval."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production import generation_dispatch_composition as composition


class ExistingStorePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / "episode-production.sqlite3"
        self.policy = self.root / "production-policy.sqlite3"
        self.paths = [self.root / "lifecycle.sqlite3", self.run,
            Path(str(self.run) + ".evidence.sqlite3"), self.policy,
            self.root / "media-jobs.sqlite3",
            Path(str(self.run) + ".provider-experiments.sqlite3"),
            Path(str(self.run) + ".voice-locks.sqlite3")]
        for index, path in enumerate(self.paths):
            path.write_bytes(b"test-only-existing-path-" + str(index).encode())
        self.args = dict(storage_root=self.root, lifecycle_path=self.paths[0],
            run_path=self.run, queue_path=self.paths[4], artifact_root=self.root,
            lifecycle_authorities={key: None for key in ("m6_scope_authority", "m6_approval_authority",
                "m6_identity_authority", "script_acceptance_authority", "canonical_target_ref")},
            episode_authorities={key: None for key in ("identity_reference_authority",
                "identity_reference_current_reader", "rights_evidence_authority", "provider_policy_authority",
                "media_selection_approval_authority", "method_aware_input_artifact_evidence",
                "method_aware_input_append_authority")},
            selection=SimpleNamespace(prepare_command={"workspaceRef": "test-workspace"}),
            endpoint=None, technical_target_id="test-target", clock=SimpleNamespace(now=lambda: None),
            worker_context=None, approval_reader=None, prerequisite_reader=None, material_reader=None,
            backend_reader=None, runtime_reader=None, cost_reader=None, issuer_service_ref="test-issuer")

    def assert_wiring(self, policy, *, explicit):
        before = {p: p.read_bytes() for p in self.root.iterdir()}
        with ExitStack() as stack:
            lifecycle = stack.enter_context(patch.object(composition.LifecycleAssembly, "sqlite"))
            stack.enter_context(patch.object(composition, "SqliteMediaJobAdapter"))
            stack.enter_context(patch.object(composition, "MediaJobCoordinator"))
            domain = stack.enter_context(patch.object(composition, "ControlledStorageDomain"))
            factory = stack.enter_context(patch(
                "services.v5_core_os.episode_production.public.create_local_development_boundary"))
            assemble = stack.enter_context(patch(
                "services.v5_core_os.episode_production.generation_dispatch_operator.compose_live_operator"))
            args = {**self.args, **({"production_policy_database_path": policy} if explicit else {})}
            operator, owned = composition.open_existing_live_operator(**args)
            self.assertIs(operator, assemble.return_value)
            self.assertIs(owned, domain.return_value)
            self.assertEqual(factory.call_args.kwargs["production_policy_database_path"], policy)
            self.assertIs(factory.call_args.kwargs["initialize_if_missing"], False)
            self.assertIs(lifecycle.call_args.kwargs["initialize_or_upgrade"], False)
            self.assertIs(lifecycle.call_args.kwargs["existing_only"], True)
            self.assertEqual(domain.call_args.args[1], [self.paths[0], self.run, self.paths[2], policy, self.paths[4]])
            self.assertIs(assemble.call_args.kwargs["policy_service"],
                factory.return_value._EpisodeProductionPublicBoundary__production_policy)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.iterdir()})

    def test_original_policy_filename_is_forwarded_and_enrolled_without_renaming(self):
        self.assert_wiring(self.policy, explicit=True)
        self.assertFalse(Path(str(self.run) + ".production-policy.sqlite3").exists())

    def test_omitted_policy_path_preserves_existing_default(self):
        default = Path(str(self.run) + ".production-policy.sqlite3")
        default.write_bytes(b"test-only-default")
        self.assert_wiring(default, explicit=False)

    def assert_refused_before_open(self, path):
        before = {p: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(composition.LifecycleAssembly, "sqlite") as lifecycle, \
                patch("sqlite3.connect", side_effect=AssertionError("must not open database")):
            with self.assertRaises(c.DispatchError) as stopped:
                composition.open_existing_live_operator(**self.args, production_policy_database_path=path)
            self.assertEqual(stopped.exception.code, "PERSISTENCE_UNAVAILABLE")
            lifecycle.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.iterdir()})

    def test_missing_explicit_policy_does_not_create_or_fall_back(self):
        self.assert_refused_before_open(self.root / "missing.sqlite3")

    def test_relative_policy_path_is_refused(self):
        self.assert_refused_before_open(Path("production-policy.sqlite3"))

    def test_policy_outside_storage_root_is_refused(self):
        with TemporaryDirectory() as outside:
            path = Path(outside).resolve() / "policy.sqlite3"
            path.write_bytes(b"test-only-outside")
            self.assert_refused_before_open(path)

    def test_policy_aliasing_another_participant_is_refused(self):
        self.assert_refused_before_open(self.paths[4])

    def test_policy_symlink_is_refused_before_any_database_open(self):
        with patch.object(Path, "is_symlink", autospec=True,
                side_effect=lambda path: path == self.policy):
            self.assert_refused_before_open(self.policy)
