"""E3G real input-only composition; all bytes and approvals are isolated fixtures."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from services.v4_platform.comfyui import ComfyUIHttpClient
from services.v5_core_os.episode_production import public
from tests.integration.test_creator_method_aware_cutover_http import (
    _serve_public_boundary,
)
from tests.unit.test_execution_method_planning_m8_m9 import seeded_plan
from tests.unit.test_method_aware_input_image_admission_e3a import (
    InputImageFixture,
)
from tests.unit.test_method_aware_media_m10_m11 import m10_command, method_service


CHILD_MODULE = "tests.integration.test_creator_input_only_composition_e3g"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _compose(lifecycle, environment):
    return public.create_local_development_boundary_from_environment(
        project_boundary=lifecycle.project_context,
        series_episode_boundary=lifecycle.series_episode,
        series_planning_boundary=lifecycle.series_planning,
        script_studio_boundary=lifecycle.script_studio,
        environ=environment,
    )


def _body(command):
    return {
        key: deepcopy(value)
        for key, value in command.items()
        if key not in {"workspaceRef", "productionRunRef", "reviewerRef"}
    }


def _input_plan_body(command):
    value = _body(command)
    value.pop("executionMethodPlanVersionRef", None)
    value["assetBindings"] = [
        {
            key: item
            for key, item in binding.items()
            if key != "assetVersionDigest"
        }
        for binding in value["assetBindings"]
    ]
    return value


def _job_counts(coordinator, scope):
    jobs = coordinator.list_jobs(
        scope["workspaceRef"], scope["productionRunRef"]
    )
    return len(jobs), sum(len(job["attempts"]) for job in jobs)


def _records(boundary, scope):
    return method_service(boundary).evidence_repository.list_records(
        scope["workspaceRef"], scope["productionRunRef"]
    )


def _post_rejected(client, path, body):
    try:
        client.post(path, body)
    except HTTPError as caught:
        with caught:
            return caught.code, json.loads(caught.read().decode("utf-8"))
    raise AssertionError("request unexpectedly succeeded")


def _child_assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _restart_child():
    config = json.loads(sys.stdin.readline())
    seed, _ = seeded_plan()
    environment = config["environment"]
    scope = config["scope"]
    provider_calls = 0
    executable_constructions = 0
    token_destroyed = False

    with patch(
        "services.v4_platform.comfyui.ComfyUIWan22ImageToVideoAdapter",
        side_effect=AssertionError("input-only startup constructed an executable adapter"),
    ) as executable, patch.object(
        ComfyUIHttpClient,
        "json",
        side_effect=AssertionError("input-only startup contacted a provider"),
    ) as provider:
        boundary = _compose(seed["assembly"], environment)
        coordinator = method_service(boundary).media_jobs
        adapter_generate = Mock(
            side_effect=AssertionError("unavailable adapter must not generate")
        )
        coordinator.adapter.generate = adapter_generate
        before_records = _records(boundary, scope)
        before_jobs = _job_counts(coordinator, scope)
        client = None
        try:
            with _serve_public_boundary(
                boundary, seed["assembly"], scope["workspaceRef"]
            ) as client:
                endpoint = config["endpoint"]
                status, candidate = client.post(
                    endpoint + "/method-aware-input-candidates",
                    config["candidateBody"],
                )
                _child_assert(status == 200, "candidate was not an exact replay")
                _child_assert(
                    candidate["candidate"]["payloadDigest"]
                    == config["candidateDigest"],
                    "candidate replay changed",
                )
                status, admission = client.post(
                    endpoint + "/method-aware-input-admission",
                    config["admissionBody"],
                )
                _child_assert(status == 200, "admission was not an exact replay")
                _child_assert(
                    admission["assetVersion"]["payloadDigest"]
                    == config["assetVersionDigest"],
                    "asset replay changed",
                )
                status, input_plan = client.post(
                    endpoint + "/method-aware-input-plan",
                    config["inputPlanBody"],
                )
                _child_assert(status == 200, "input plan was not an exact replay")
                _child_assert(
                    input_plan["payloadDigest"] == config["inputPlanDigest"],
                    "input-plan replay changed",
                )
                status, current = client.get(
                    endpoint + "/method-aware-input-plan",
                    projectRef=scope["projectRef"],
                    seriesRef=scope["seriesRef"],
                    episodeRef=scope["episodeRef"],
                    versionRef=input_plan["methodAwareInputPlanVersionRef"],
                )
                _child_assert(status == 200, "input-plan read failed")
                _child_assert(
                    current["currentness"] == "CURRENT",
                    "input plan was not current after process restart",
                )
                route_status, route_error = _post_rejected(
                    client,
                    endpoint + "/method-aware-video-route",
                    config["routeBody"],
                )
                _child_assert(route_status == 503, "route was not unavailable")
                _child_assert(
                    route_error["error"]["code"] == "worker_unavailable",
                    "route failed before the backend-unavailable boundary",
                )
                client.token = ""
                token_destroyed = client.token == ""
        finally:
            if client is not None:
                client.token = ""

        after_records = _records(boundary, scope)
        after_jobs = _job_counts(coordinator, scope)
        _child_assert(after_records == before_records, "restart replay wrote evidence")
        _child_assert(after_jobs == before_jobs, "rejected route changed the queue")
        _child_assert(adapter_generate.call_count == 0, "adapter generate was called")
        provider_calls = provider.call_count
        executable_constructions = executable.call_count

    print(
        json.dumps(
            {
                "candidateReplay": True,
                "admissionReplay": True,
                "inputPlanReplay": True,
                "inputPlanCurrent": True,
                "routeRejected": True,
                "queueDelta": after_jobs[0] - before_jobs[0],
                "attemptDelta": after_jobs[1] - before_jobs[1],
                "adapterGenerateCount": adapter_generate.call_count,
                "providerHttpRequestCount": provider_calls,
                "executableBackendConstructionCount": executable_constructions,
                "tokenDestroyed": token_destroyed,
            },
            sort_keys=True,
        ),
        flush=True,
    )


class CreatorInputOnlyCompositionE3GTests(unittest.TestCase):
    def test_full_public_lifecycle_unavailable_route_and_real_process_restart(self):
        fixture = InputImageFixture(self, sqlite=True)
        fixture.configure()
        scope = fixture.scope
        environment = {
            **fixture.environment,
            "CREATOR_EPISODE_PRODUCTION_DATA_PATH": str(
                fixture.root / "runs.sqlite3"
            ),
            "CREATOR_MEDIA_JOB_DATA_PATH": str(
                fixture.root / "media-jobs.sqlite3"
            ),
            "CREATOR_MEDIA_ARTIFACT_ROOT": str(
                fixture.root / "media-artifacts"
            ),
        }
        endpoint = (
            "/creator/api/v1/episode-production-runs/"
            + scope["productionRunRef"]
        )

        with patch(
            "services.v4_platform.comfyui.ComfyUIWan22ImageToVideoAdapter",
            side_effect=AssertionError(
                "input-only startup constructed an executable adapter"
            ),
        ) as executable, patch.object(
            ComfyUIHttpClient,
            "json",
            side_effect=AssertionError("input-only startup contacted a provider"),
        ) as provider:
            first = _compose(fixture.seed["assembly"], environment)
            first_coordinator = method_service(first).media_jobs
            self.assertEqual(
                first_coordinator.adapter.adapter_identity,
                "v4.method-aware-unavailable.v1",
            )
            before_intake = _records(first, scope)
            with _serve_public_boundary(
                first, fixture.seed["assembly"], scope["workspaceRef"]
            ) as client:
                status, intake = client.post(
                    endpoint + "/method-aware-input-candidates",
                    _body(fixture.command()),
                )
                self.assertEqual(status, 201)
                after_intake = _records(first, scope)
                self.assertEqual(len(after_intake) - len(before_intake), 3)

                status, candidate_replay = client.post(
                    endpoint + "/method-aware-input-candidates",
                    _body(fixture.command()),
                )
                self.assertEqual(status, 200)
                self.assertEqual(candidate_replay["candidate"], intake["candidate"])
                self.assertEqual(_records(first, scope), after_intake)

                status, qc_response = client.post(
                    endpoint + "/semantic-visual-qc",
                    _body(fixture.qc_command(intake)),
                )
                self.assertEqual(status, 201)
                qc = qc_response["semanticVisualQc"]
                self.assertEqual(len(_records(first, scope)) - len(after_intake), 1)
                client.token = ""

            selection_command = fixture.approve(intake, qc)
            environment.update(fixture.selection_environment)
            second = _compose(fixture.seed["assembly"], environment)
            coordinator = method_service(second).media_jobs
            adapter_generate = Mock(
                side_effect=AssertionError("unavailable adapter must not generate")
            )
            coordinator.adapter.generate = adapter_generate
            with _serve_public_boundary(
                second, fixture.seed["assembly"], scope["workspaceRef"]
            ) as client:
                before_selection = _records(second, scope)
                status, selection_response = client.post(
                    endpoint + "/media-selection",
                    _body(selection_command),
                )
                self.assertEqual(status, 201)
                selection = selection_response["humanSelection"]
                self.assertEqual(
                    len(_records(second, scope)) - len(before_selection), 1
                )

                admission_command = fixture.admission_command(selection)
                before_admission = _records(second, scope)
                status, admission = client.post(
                    endpoint + "/method-aware-input-admission",
                    _body(admission_command),
                )
                self.assertEqual(status, 201)
                after_admission = _records(second, scope)
                self.assertEqual(len(after_admission) - len(before_admission), 2)
                asset = admission["assetVersion"]
                self.assertFalse(asset["providerProcessingAuthorized"])
                self.assertFalse(asset["publicationAllowed"])

                status, admission_replay = client.post(
                    endpoint + "/method-aware-input-admission",
                    _body(admission_command),
                )
                self.assertEqual(status, 200)
                self.assertEqual(admission_replay["assetVersion"], asset)
                self.assertEqual(_records(second, scope), after_admission)

                input_plan_command = m10_command(
                    fixture.seed,
                    fixture.plan,
                    [fixture.binding(asset)],
                    key="e3g-input-only-plan",
                )
                public_input_plan = _input_plan_body(input_plan_command)
                status, input_plan = client.post(
                    endpoint + "/method-aware-input-plan",
                    public_input_plan,
                )
                self.assertEqual(status, 201)
                self.assertEqual(input_plan["currentness"], "CURRENT")
                self.assertEqual(input_plan["inputReadyCount"], 1)
                self.assertEqual(input_plan["resolvedAssetBindingCount"], 1)

                after_input_plan = _records(second, scope)
                status, input_plan_replay = client.post(
                    endpoint + "/method-aware-input-plan",
                    public_input_plan,
                )
                self.assertEqual(status, 200)
                self.assertTrue(input_plan_replay["idempotentReplay"])
                self.assertEqual(input_plan_replay["payloadDigest"], input_plan["payloadDigest"])
                self.assertEqual(_records(second, scope), after_input_plan)

                status, current = client.get(
                    endpoint + "/method-aware-input-plan",
                    projectRef=scope["projectRef"],
                    seriesRef=scope["seriesRef"],
                    episodeRef=scope["episodeRef"],
                    versionRef=input_plan["methodAwareInputPlanVersionRef"],
                )
                self.assertEqual(status, 200)
                self.assertEqual(current["currentness"], "CURRENT")
                self.assertEqual(current["payloadDigest"], input_plan["payloadDigest"])

                route_body = _body(
                    {
                        **scope,
                        "idempotencyKey": "e3g-ready-input-no-backend-route",
                    }
                )
                records_before_route = _records(second, scope)
                jobs_before_route = _job_counts(coordinator, scope)
                status, route_error = _post_rejected(
                    client,
                    endpoint + "/method-aware-video-route",
                    route_body,
                )
                self.assertEqual(status, 503)
                self.assertEqual(route_error["error"]["code"], "worker_unavailable")
                self.assertEqual(_records(second, scope), records_before_route)
                self.assertEqual(_job_counts(coordinator, scope), jobs_before_route)
                self.assertEqual(adapter_generate.call_count, 0)
                client.token = ""

            self.assertEqual(provider.call_count, 0)
            self.assertEqual(executable.call_count, 0)

        child_config = {
            "environment": environment,
            "scope": scope,
            "endpoint": endpoint,
            "candidateBody": _body(fixture.command()),
            "admissionBody": _body(admission_command),
            "inputPlanBody": public_input_plan,
            "routeBody": route_body,
            "candidateDigest": intake["candidate"]["payloadDigest"],
            "assetVersionDigest": asset["payloadDigest"],
            "inputPlanDigest": input_plan["payloadDigest"],
        }
        restarted = subprocess.run(
            [sys.executable, "-m", CHILD_MODULE, "--restart-child"],
            cwd=REPO_ROOT,
            input=json.dumps(child_config, ensure_ascii=False) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        result = json.loads(restarted.stdout.strip())
        self.assertTrue(result["candidateReplay"])
        self.assertTrue(result["admissionReplay"])
        self.assertTrue(result["inputPlanReplay"])
        self.assertTrue(result["inputPlanCurrent"])
        self.assertTrue(result["routeRejected"])
        self.assertEqual(result["queueDelta"], 0)
        self.assertEqual(result["attemptDelta"], 0)
        self.assertEqual(result["adapterGenerateCount"], 0)
        self.assertEqual(result["providerHttpRequestCount"], 0)
        self.assertEqual(result["executableBackendConstructionCount"], 0)
        self.assertTrue(result["tokenDestroyed"])


if __name__ == "__main__":
    if sys.argv[1:] == ["--restart-child"]:
        _restart_child()
    else:
        unittest.main()
