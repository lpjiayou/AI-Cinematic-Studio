"""Pure CPU upload/policy bounds; no provider or existing runtime access."""
from io import BytesIO
import unittest

from PIL import Image

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.image_video import (
    ImageVideoInstallation, MAX_INPUT, normalize_image,
)
from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceError


class ImageVideoInputTests(unittest.TestCase):
    def image(self, format="PNG"):
        out = BytesIO()
        Image.new("RGB", (23, 41), (15, 100, 120)).save(out, format=format)
        return out.getvalue()

    def test_png_roundtrip_removes_metadata_and_keeps_pixels(self):
        from PIL.PngImagePlugin import PngInfo
        out, info = BytesIO(), PngInfo()
        info.add_text("private-comment", "must-not-reach-provider")
        Image.new("RGB", (23, 41), (15, 100, 120)).save(out, format="PNG", pnginfo=info)
        png, width, height = normalize_image(out.getvalue(), "image/png")
        self.assertEqual((width, height), (23, 41))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.info, {})
            self.assertEqual(image.getpixel((0, 0)), (15, 100, 120))

    def test_jpeg_is_decoded_to_real_png_not_relabelled(self):
        png, width, height = normalize_image(self.image("JPEG"), "image/jpeg")
        self.assertEqual((width, height), (23, 41))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual((image.format, image.mode), ("PNG", "RGB"))

    def test_wrong_mime_corrupt_empty_and_excess_size_fail(self):
        for data, mime in ((self.image(), "image/jpeg"), (b"bad", "image/png"),
                (b"", "image/png"), (b"a" * (MAX_INPUT + 1), "image/png"), (self.image(), "image/svg+xml")):
            with self.subTest(mime=mime, size=len(data)), self.assertRaises(GenerationWorkspaceError):
                normalize_image(data, mime)

    def test_animation_refused(self):
        out = BytesIO()
        Image.new("RGB", (23, 41)).save(out, format="PNG", save_all=True,
            append_images=[Image.new("RGB", (23, 41), "red")], duration=40, loop=0)
        with self.assertRaises(GenerationWorkspaceError):
            normalize_image(out.getvalue(), "image/png")

    def test_oversized_dimensions_refused_before_decode(self):
        from unittest.mock import patch
        image = Image.new("RGB", (1, 1))
        image._size = (16385, 1)
        image.format = "PNG"
        with patch("PIL.Image.open", return_value=image), self.assertRaises(GenerationWorkspaceError):
            normalize_image(self.image(), "image/png")

    def test_pixel_limit_matches_transport_before_decode(self):
        from unittest.mock import patch
        image = Image.new("RGB", (1, 1))
        image._size, image.format = (4097, 4096), "PNG"
        with patch("PIL.Image.open", return_value=image), self.assertRaises(GenerationWorkspaceError):
            normalize_image(self.image(), "image/png")

    def test_window_rechecked_after_lock_wait_before_any_input_write(self):
        import base64
        from contextlib import contextmanager
        from threading import RLock
        from types import SimpleNamespace
        from unittest.mock import Mock
        from uuid import uuid4
        from services.v5_core_os.episode_production.image_video import ImageVideoRuntime
        runtime = ImageVideoRuntime.__new__(ImageVideoRuntime)
        runtime.scope = {k: "test-" + k for k in c.SCOPE_FIELDS}
        runtime.policy = {"credentialActors": {"test-credential": "test-actor"},
            "payloadDigest": "a" * 64, "limits": {
                "notBefore": "2030-01-01T00:00:00.000000Z", "expiresAt": "2030-01-01T01:00:00.000000Z"}}
        now = ["2030-01-01T00:59:59.000000Z"]
        runtime.clock = SimpleNamespace(now=lambda: now[0])
        runtime._lock, runtime._parents, runtime.evidence = RLock(), Mock(), Mock()

        @contextmanager
        def critical_section(_workspace):
            now[0] = "2030-01-01T01:00:00.000000Z"
            yield object()

        runtime.coordination = SimpleNamespace(critical_section=critical_section)
        command = {"description": "test motion", "imageBase64": base64.b64encode(self.image()).decode(),
            "imageMediaType": "image/png", "idempotencyKey": str(uuid4()), "expectedPolicyDigest": "a" * 64}
        with self.assertRaises(c.DispatchError) as rejected:
            runtime.create(runtime.scope, "test-credential", command)
        self.assertEqual(rejected.exception.code, "OUTSIDE_VALIDITY_WINDOW")
        runtime._parents.assert_not_called()
        self.assertEqual(runtime.evidence.mock_calls, [])

    def test_queued_exception_projects_unknown_without_mutating_queue(self):
        from copy import deepcopy
        from types import SimpleNamespace
        from services.v5_core_os.episode_production.image_video import ImageVideoRuntime
        runtime = ImageVideoRuntime.__new__(ImageVideoRuntime)
        runtime.scope = {k: "test-" + k for k in c.SCOPE_FIELDS}
        runtime._record = lambda _ref: {"payload": {"input": {"description": "test",
            "originalSha256": "b" * 64, "createdAt": "2030-01-01T00:00:00.000000Z"}}}
        job = {"state": "QUEUED", "jobRef": "test-job", "attempts": []}
        before = deepcopy(job)
        runtime._job = lambda _ref: job
        runtime.evidence = SimpleNamespace(get_record=lambda *args: {"payload": {"errorCode": "CONFIG_CHANGED"}})
        projection = runtime._projection("test-generation")
        self.assertEqual(projection["state"], "UNKNOWN")
        self.assertEqual(projection["errorCode"], "CONFIG_CHANGED")
        self.assertFalse(projection["automaticRetryAllowed"])
        self.assertEqual(job, before)

    def test_restarted_nonterminal_job_is_unknown_without_reclaim_or_resend(self):
        from copy import deepcopy
        from types import SimpleNamespace
        from services.v5_core_os.episode_production.image_video import ImageVideoRuntime
        runtime = ImageVideoRuntime.__new__(ImageVideoRuntime)
        runtime.scope = {k: "test-" + k for k in c.SCOPE_FIELDS}
        runtime._active = None
        runtime._record = lambda _ref: {"payload": {"input": {"description": "test",
            "originalSha256": "b" * 64, "createdAt": "2030-01-01T00:00:00.000000Z"}}}
        runtime.evidence = SimpleNamespace(get_record=lambda *args: None)
        for state in ("QUEUED", "LEASED", "RUNNING"):
            with self.subTest(state=state):
                job = {"state": state, "jobRef": "test-job", "attempts": []}
                before = deepcopy(job)
                runtime._job = lambda _ref: job
                result = runtime._projection("test-generation")
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertFalse(result["automaticRetryAllowed"])
                self.assertIsNone(result["artifact"])
                self.assertEqual(job, before)

    def test_policy_requires_explicit_finite_authority_and_materials(self):
        from types import SimpleNamespace
        scope = {k: "test-" + k for k in c.SCOPE_FIELDS}
        limits = {"maxAttempts": 1, "maxPromptSubmissions": 1, "retryAllowed": False,
            "fallbackAllowed": False, "costCurrency": "CNY", "maxCostMinor": 100,
            "executionTimeoutSeconds": 180, "notBefore": "2030-01-01T00:00:00.000000Z",
            "expiresAt": "2030-01-01T01:00:00.000000Z", "stopPolicy": "FAIL_CLOSED_NO_RESUBMISSION"}
        policy = c.sealed({"schemaVersion": "v5.user-image-video-policy.v1", "policyRef": "test-policy",
            "authorityRef": "test-owner", "scope": scope, "credentialActors": {"test-credential": "test-actor"},
            "limits": limits, "maxTotalCostMinor": 200, "maxGenerations": 2})
        materials = SimpleNamespace(prepare_input=lambda *a: None, verify_current=lambda *a: None)
        ImageVideoInstallation(policy, materials).validate()
        for field, value in (("maxGenerations", 0), ("maxGenerations", 101), ("maxTotalCostMinor", 99),
                ("credentialActors", {}), ("unexpectedPermission", True)):
            with self.subTest(field=field, value=value), self.assertRaises(c.DispatchError):
                ImageVideoInstallation(c.sealed({**policy, field: value}), materials).validate()
        with self.assertRaises(c.DispatchError):
            ImageVideoInstallation(policy, None).validate()


class ImageVideoProgressReadTests(unittest.TestCase):
    """Real runtime + in-memory journal; only authority/material ports are fakes."""

    def blocked_preparation(self):
        import base64
        from contextlib import contextmanager
        from copy import deepcopy
        from threading import Event, RLock
        from types import SimpleNamespace
        from unittest.mock import Mock
        from uuid import uuid4
        from services.v5_core_os.episode_production.evidence import InMemoryEpisodeProductionEvidenceAdapter
        from services.v5_core_os.episode_production.image_video import ImageVideoRuntime

        scope = {key: "test-progress-" + key for key in c.SCOPE_FIELDS}
        entered, release = Event(), Event()
        gate = RLock()

        def held():
            self.assertTrue(gate._is_owned())

        @contextmanager
        def critical_section(workspace):
            self.assertEqual(workspace, scope["workspaceRef"])
            with gate:
                yield SimpleNamespace(assert_held=held, coordinator=coordination,
                    workspace_ref=workspace)

        coordination = SimpleNamespace(critical_section=critical_section)

        def prepare_input(*args):
            args[-1].assert_held()
            entered.set()
            if not release.wait(10):
                raise AssertionError("test preparation release was not signalled")
            raise c.DispatchError("SOURCE_CHANGED")

        materials = SimpleNamespace(prepare_input=prepare_input, verify_current=Mock())
        limits = {"maxAttempts": 1, "maxPromptSubmissions": 1, "retryAllowed": False,
            "fallbackAllowed": False, "costCurrency": "CNY", "maxCostMinor": 100,
            "executionTimeoutSeconds": 180, "notBefore": "2030-01-01T00:00:00.000000Z",
            "expiresAt": "2030-01-01T01:00:00.000000Z", "stopPolicy": "FAIL_CLOSED_NO_RESUBMISSION"}
        policy = c.sealed({"schemaVersion": "v5.user-image-video-policy.v1", "policyRef": "test-progress-policy",
            "authorityRef": "test-owner", "scope": scope,
            "credentialActors": {"test-credential": "test-actor"}, "limits": limits,
            "maxTotalCostMinor": 100, "maxGenerations": 1})
        context = {key: {"ref": scope[key + "Ref"]} for key in ("project", "series", "episode")}
        root = SimpleNamespace(get_run=lambda *args: deepcopy(scope),
            project_reader=SimpleNamespace(build_context=lambda *args: deepcopy(context)))
        runtime = ImageVideoRuntime(ImageVideoInstallation(policy, materials),
            evidence=InMemoryEpisodeProductionEvidenceAdapter(), root=root, coordination=coordination,
            clock=SimpleNamespace(now=lambda: "2030-01-01T00:30:00.000000Z"))
        runtime.attach_operator(SimpleNamespace(_coordinator=SimpleNamespace(
            repository=SimpleNamespace(list=lambda *args: []))))
        output = BytesIO()
        Image.new("RGB", (23, 41), (15, 100, 120)).save(output, format="PNG")
        command = {"description": "test slow preparation", "imageBase64": base64.b64encode(output.getvalue()).decode(),
            "imageMediaType": "image/png", "idempotencyKey": str(uuid4()),
            "expectedPolicyDigest": policy["payloadDigest"]}
        created = runtime.create(scope, "test-credential", command)
        self.addCleanup(runtime.close)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(5), "worker must hold the gate inside prepare_input")
        self.assertEqual(len(runtime.evidence.list_records(scope["workspaceRef"],
            scope["productionRunRef"], record_kind="UserImageVideoInput")), 1)
        return runtime, created, release

    def read_before_release(self, callback, release):
        from threading import Event, Thread
        completed, result, failures = Event(), [], []

        def read():
            try:
                result.append(callback())
            except Exception as exc:
                failures.append(exc)
            finally:
                completed.set()

        reader = Thread(target=read)
        reader.start()
        try:
            self.assertTrue(completed.wait(1), "status read waited for the held generation gate")
        except BaseException:
            release.set()
            raise
        finally:
            reader.join(5)
        self.assertFalse(reader.is_alive())
        if failures:
            raise failures[0]
        return result[0]

    def test_preparing_get_and_workspace_read_committed_input_without_waiting_for_write_gate(self):
        runtime, created, release = self.blocked_preparation()
        view = self.read_before_release(lambda: runtime.get(runtime.scope, "test-credential",
            created["generationRef"]), release)
        workspace = self.read_before_release(lambda: runtime.workspace(runtime.scope, "test-credential"), release)
        self.assertEqual(view, created)
        self.assertEqual(view["state"], "PREPARING")
        self.assertEqual(workspace["generations"], [created])
        self.assertFalse(workspace["available"])
        self.assertEqual(workspace["reason"], "generation_already_active")
        self.assertFalse(release.is_set())
        release.set()
        runtime.close()
        final = runtime.get(runtime.scope, "test-credential", created["generationRef"])
        self.assertEqual((final["state"], final["errorCode"], final["attemptCount"]),
            ("FAILED", "SOURCE_CHANGED", 0))
        self.assertFalse(final["automaticRetryAllowed"])
        history = runtime.workspace(runtime.scope, "test-credential")
        self.assertEqual(history["generations"], [final])
        self.assertEqual(history["reason"], "generation_budget_exhausted")
        self.assertFalse(history["available"])

    def test_active_display_is_defensive_and_never_bypasses_scope_credential_or_ref_checks(self):
        runtime, created, release = self.blocked_preparation()
        for scope, credential, reference, code in (
                ({**runtime.scope, "projectRef": "test-other"}, "test-credential", created["generationRef"], "generation_target_not_found"),
                (runtime.scope, "test-other", created["generationRef"], "generation_operation_not_authorized"),
                (runtime.scope, "test-credential", "test-unknown-generation", "generation_result_not_found"),
                (runtime.scope, "test-credential", "invalid/ref", "generation_result_not_found")):
            with self.subTest(code=code):
                with self.assertRaises(GenerationWorkspaceError) as rejected:
                    self.read_before_release(lambda: runtime.get(scope, credential, reference), release)
                self.assertEqual(rejected.exception.code, code)
        changed = self.read_before_release(lambda: runtime.workspace(runtime.scope, "test-credential"), release)
        changed["generations"][0]["state"] = "SUCCEEDED"
        changed["policy"]["output"]["width"] = 1
        actual = self.read_before_release(lambda: runtime.workspace(runtime.scope, "test-credential"), release)
        self.assertEqual(actual["generations"], [created])
        self.assertEqual(actual["policy"]["output"]["width"], 704)
        self.assertFalse(actual["available"])


if __name__ == "__main__":
    unittest.main()
