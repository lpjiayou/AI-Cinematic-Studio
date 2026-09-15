"""Closed runtime-environment projection; no GPU, network or generation I/O."""

from contextlib import contextmanager
from types import SimpleNamespace
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceError
from services.v5_core_os.episode_production.image_video import ImageVideoRuntime


class ImageVideoRuntimeEnvironmentTests(unittest.TestCase):
    def runtime(self, observer, jobs):
        scope = {key: "environment-" + key for key in c.SCOPE_FIELDS}

        @contextmanager
        def critical_section(workspace_ref):
            self.assertEqual(workspace_ref, scope["workspaceRef"])
            yield SimpleNamespace(assert_held=lambda: None)

        runtime = ImageVideoRuntime.__new__(ImageVideoRuntime)
        runtime.scope = scope
        runtime.policy = {"credentialActors": {"environment-credential": "environment-actor"}}
        runtime.material_port = SimpleNamespace(read_environment=observer)
        runtime.coordination = SimpleNamespace(critical_section=critical_section)
        runtime._parents = lambda lease: lease.assert_held()
        runtime.operator = SimpleNamespace(_coordinator=SimpleNamespace(
            repository=SimpleNamespace(list=lambda *args: jobs)))
        return runtime

    def test_connected_projection_counts_operator_queue_without_private_runtime_facts(self):
        observed = {"observedAt": "2026-09-15T10:00:00.000000Z",
            "evidenceClass": "CURRENT_RUNTIME_OBSERVATION", "gpuCount": 1,
            "deviceType": "cuda", "comfyuiVersion": "0.35.0"}
        runtime = self.runtime(lambda lease: (lease.assert_held(), observed)[1], [
            {"state": "QUEUED"}, {"state": "RUNNING"}, {"state": "SUCCEEDED"}])
        result = runtime.environment(runtime.scope, "environment-credential")
        self.assertEqual((result["core"], result["operator"], result["gpu"],
            result["comfyui"]), ("CONNECTED", "READY", "CONNECTED", "CONNECTED"))
        self.assertEqual(result["queue"], {
            "state": "BUSY", "runningCount": 1, "pendingCount": 1})
        self.assertTrue(result["readOnly"])
        self.assertNotIn("endpoint", result)
        self.assertNotIn("modelFiles", result)

    def test_runtime_observation_failure_is_closed_state_not_fake_connectivity(self):
        def unavailable(_lease):
            raise c.DispatchError("RUNTIME_CHANGED")

        runtime = self.runtime(unavailable, [])
        result = runtime.environment(runtime.scope, "environment-credential")
        self.assertIsNone(result["observedAt"])
        self.assertEqual((result["gpu"], result["comfyui"]),
            ("UNAVAILABLE", "UNAVAILABLE"))
        self.assertEqual(result["queue"], {
            "state": "IDLE", "runningCount": 0, "pendingCount": 0})
        with self.assertRaises(GenerationWorkspaceError):
            runtime.environment(runtime.scope, "wrong-credential")


if __name__ == "__main__":
    unittest.main()
