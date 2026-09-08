"""E3G method-aware input configuration ownership regression tests."""

from contextlib import redirect_stderr
from hashlib import sha256
import io
import unittest

from services.v4_platform import InMemoryMediaJobAdapter
from services.v4_platform.backend_registry import (
    BackendUnavailableError,
    BackendValidationError,
    canonical,
)
from services.v4_platform import method_aware_input_artifacts
from services.v4_platform import method_aware_worker
from services.v5_core_os.episode_production import public
from tests.unit.test_method_aware_input_image_admission_e3a import (
    InputImageFixture,
)
from tests.unit.test_method_aware_media_m10_m11 import (
    backend_registry_fixture,
    method_service,
)


class InputOnlyEnvironmentCompositionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = InputImageFixture(self, sqlite=True)
        self.fixture.configure()

    def environment(self, **changes):
        return {
            **self.fixture.environment,
            "CREATOR_EPISODE_PRODUCTION_DATA_PATH": str(
                self.fixture.root / "runs.sqlite3"
            ),
            "CREATOR_MEDIA_JOB_DATA_PATH": str(
                self.fixture.root / "media-jobs.sqlite3"
            ),
            "CREATOR_MEDIA_ARTIFACT_ROOT": str(
                self.fixture.root / "media-artifacts"
            ),
            **changes,
        }

    def create_boundary(self, environment):
        lifecycle = self.fixture.seed["assembly"]
        return public.create_local_development_boundary_from_environment(
            project_boundary=lifecycle.project_context,
            series_episode_boundary=lifecycle.series_episode,
            series_planning_boundary=lifecycle.series_planning,
            script_studio_boundary=lifecycle.script_studio,
            environ=environment,
        )

    def test_complete_input_configuration_starts_real_environment_factory(self):
        boundary = self.create_boundary(self.environment())

        coordinator = method_service(boundary).media_jobs
        self.assertEqual(
            coordinator.adapter.adapter_identity,
            "v4.method-aware-unavailable.v1",
        )
        with self.assertRaises(BackendUnavailableError):
            coordinator.backend_resolver.resolve(
                "MICRO_MOTION",
                "SINGLE_ANCHOR_I2V",
                ["ACTION_READY_ANCHOR"],
                {"mediaType": "video/mp4"},
            )

    def test_only_exact_input_configuration_names_are_exempt(self):
        self.assertEqual(
            method_aware_worker._INPUT_ARTIFACT_CONFIGURATION_NAMES,
            frozenset(method_aware_input_artifacts.CONFIG_NAMES),
        )
        coordinator = method_aware_worker.create_method_aware_coordinator_from_environment(
            InMemoryMediaJobAdapter(),
            self.fixture.root / "unavailable-artifacts",
            environ=self.fixture.environment,
        )
        self.assertEqual(
            coordinator.adapter.adapter_identity,
            "v4.method-aware-unavailable.v1",
        )

        for name in (
            "CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH_TYPO",
            "CREATOR_METHOD_AWARE_INPUT_UNKNOWN",
            "CREATOR_METHOD_AWARE_UNKNOWN",
            "METHOD_AWARE_COMFYUI_UNKNOWN",
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                BackendValidationError,
                "method-aware backend registry is missing",
            ):
                method_aware_worker.create_method_aware_coordinator_from_environment(
                    InMemoryMediaJobAdapter(),
                    self.fixture.root / "unknown-artifacts",
                    environ={**self.fixture.environment, name: "configured"},
                )

    def test_partial_execution_configuration_never_becomes_input_only(self):
        for name, value in (
            ("CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256", "1" * 64),
            ("METHOD_AWARE_COMFYUI_BASE_URL", "http://127.0.0.1:8188"),
            ("METHOD_AWARE_COMFYUI_RUNTIME_ATTESTATION", "runtime.json"),
            ("METHOD_AWARE_COMFYUI_MODEL_ROOT", "models"),
            ("METHOD_AWARE_COMFYUI_INPUT_ROOT", "input"),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                BackendValidationError,
                "method-aware backend registry is missing",
            ):
                self.create_boundary(self.environment(**{name: value}))

    def test_present_registry_still_requires_a_valid_pin_and_manifest(self):
        with self.assertRaises(BackendValidationError):
            self.create_boundary(
                self.environment(
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY=str(
                        self.fixture.bundle_path
                    ),
                )
            )
        with self.assertRaises(BackendValidationError):
            self.create_boundary(
                self.environment(
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY=str(
                        self.fixture.bundle_path
                    ),
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256="0" * 64,
                )
            )

    def test_valid_registry_still_requires_its_execution_credential(self):
        registry = backend_registry_fixture()
        raw = canonical(registry._manifest)
        manifest = self.fixture.root / "valid-registry.json"
        manifest.write_bytes(raw)
        with self.assertRaisesRegex(
            BackendValidationError,
            "server credential source is unavailable",
        ):
            self.create_boundary(
                self.environment(
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY=str(manifest),
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256=sha256(
                        raw
                    ).hexdigest(),
                )
            )
        with self.assertRaises(BackendValidationError):
            self.create_boundary(
                self.environment(
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY=str(
                        self.fixture.bundle_path
                    ),
                    CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256=(
                        self.fixture.environment[
                            "CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256"
                        ]
                    ),
                )
            )

    def test_worker_run_one_still_requires_registry_arguments(self):
        arguments = [
            "run-one",
            "--job-ref",
            "job-e3g",
            "--workspace-ref",
            "workspace-e3g",
            "--production-run-ref",
            "run-e3g",
            "--worker-ref",
            "worker-e3g",
            "--queue-db",
            str(self.fixture.root / "missing.sqlite3"),
            "--artifact-root",
            str(self.fixture.root / "artifacts"),
            "--max-attempts",
            "1",
        ]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            method_aware_worker.main(arguments, environ=self.fixture.environment)
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
