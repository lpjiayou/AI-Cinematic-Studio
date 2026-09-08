"""E3H manifest-v2 input append authority through the authenticated HTTP seam."""

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
from tests.unit.test_k2_002_shot_profile_v2 import PortraitProjectBoundary
from tests.unit.test_method_aware_input_image_admission_e3a import (
    InputImageFixture,
)
from tests.unit.test_method_aware_media_m10_m11 import m10_command, method_service


CHILD_MODULE = (
    "tests.integration.test_creator_manifest_v2_input_append_authority_e3h"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _compose(lifecycle, environment):
    return public.create_local_development_boundary_from_environment(
        project_boundary=PortraitProjectBoundary(lifecycle.project_context),
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


def _records(boundary, scope):
    return method_service(boundary).evidence_repository.list_records(
        scope["workspaceRef"], scope["productionRunRef"]
    )


def _job_counts(coordinator, scope):
    jobs = coordinator.list_jobs(
        scope["workspaceRef"], scope["productionRunRef"]
    )
    return len(jobs), sum(len(job["attempts"]) for job in jobs)


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
    endpoint = config["endpoint"]
    token_destroyed = False

    with patch(
        "services.v4_platform.comfyui.ComfyUIWan22ImageToVideoAdapter",
        side_effect=AssertionError("E3H constructed an executable adapter"),
    ) as executable, patch.object(
        ComfyUIHttpClient,
        "json",
        side_effect=AssertionError("E3H contacted a provider"),
    ) as provider:
        boundary = _compose(seed["assembly"], environment)
        coordinator = method_service(boundary).media_jobs
        adapter_generate = Mock(
            side_effect=AssertionError("E3H invoked adapter generation")
        )
        coordinator.adapter.generate = adapter_generate
        before_records = _records(boundary, scope)
        before_jobs = _job_counts(coordinator, scope)
        client = None
        try:
            with _serve_public_boundary(
                boundary, seed["assembly"], scope["workspaceRef"]
            ) as client:
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
                    "admission replay changed",
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
                _child_assert(route_status == 409, "manifest-v2 route was not blocked")
                _child_assert(
                    route_error["error"]["code"] == "execution_not_authorized",
                    "manifest-v2 route crossed the execution boundary",
                )
                client.token = ""
                token_destroyed = client.token == ""
        finally:
            if client is not None:
                client.token = ""

        after_records = _records(boundary, scope)
        after_jobs = _job_counts(coordinator, scope)
        _child_assert(after_records == before_records, "restart replay wrote evidence")
        _child_assert(after_jobs == before_jobs, "blocked route changed the queue")
        _child_assert(adapter_generate.call_count == 0, "adapter generate was called")

        without_authority = dict(environment)
        without_authority.pop("CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_PATH")
        without_authority.pop("CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_SHA256")
        revoked = _compose(seed["assembly"], without_authority)
        revoked_before = _records(revoked, scope)
        revoked_client = None
        try:
            with _serve_public_boundary(
                revoked, seed["assembly"], scope["workspaceRef"]
            ) as revoked_client:
                rejected_status, rejected_error = _post_rejected(
                    revoked_client,
                    endpoint + "/method-aware-input-candidates",
                    config["candidateBody"],
                )
                _child_assert(rejected_status == 409, "revoked replay was accepted")
                _child_assert(
                    rejected_error["error"]["code"] == "execution_not_authorized",
                    "revoked replay did not fail closed",
                )
                revoked_client.token = ""
        finally:
            if revoked_client is not None:
                revoked_client.token = ""
        _child_assert(
            _records(revoked, scope) == revoked_before,
            "revoked authority attempt wrote evidence",
        )

    print(
        json.dumps(
            {
                "candidateReplay": True,
                "admissionReplay": True,
                "inputPlanReplay": True,
                "inputPlanCurrent": True,
                "routeRejected": True,
                "authorityRemovalRejected": True,
                "recordDelta": len(after_records) - len(before_records),
                "queueDelta": after_jobs[0] - before_jobs[0],
                "attemptDelta": after_jobs[1] - before_jobs[1],
                "adapterGenerateCount": adapter_generate.call_count,
                "providerHttpRequestCount": provider.call_count,
                "executableBackendConstructionCount": executable.call_count,
                "tokenDestroyed": token_destroyed,
            },
            sort_keys=True,
        ),
        flush=True,
    )


class CreatorManifestV2InputAppendAuthorityE3HTests(unittest.TestCase):
    def test_authenticated_lifecycle_blocked_route_and_real_process_restart(self):
        fixture = InputImageFixture(self, sqlite=True, manifest_v2=True)
        fixture.configure()
        scope = fixture.scope
        environment = {
            **fixture.environment,
            **fixture.input_append_environment,
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
        manifest_before = deepcopy(fixture.seed["run"]["manifest"])

        with patch(
            "services.v4_platform.comfyui.ComfyUIWan22ImageToVideoAdapter",
            side_effect=AssertionError("E3H constructed an executable adapter"),
        ) as executable, patch.object(
            ComfyUIHttpClient,
            "json",
            side_effect=AssertionError("E3H contacted a provider"),
        ) as provider:
            first = _compose(fixture.seed["assembly"], environment)
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
                self.assertEqual(
                    [item["recordKind"] for item in after_intake[len(before_intake):]],
                    [
                        "MethodAwareInputAppendAuthority",
                        "MethodAwareInputArtifact",
                        "Candidate",
                        "TechnicalValidation",
                    ],
                )

                status, replay = client.post(
                    endpoint + "/method-aware-input-candidates",
                    _body(fixture.command()),
                )
                self.assertEqual(status, 200)
                self.assertEqual(replay["candidate"], intake["candidate"])
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
                side_effect=AssertionError("E3H invoked adapter generation")
            )
            coordinator.adapter.generate = adapter_generate
            with _serve_public_boundary(
                second, fixture.seed["assembly"], scope["workspaceRef"]
            ) as client:
                before_selection = _records(second, scope)
                status, selected = client.post(
                    endpoint + "/media-selection",
                    _body(selection_command),
                )
                self.assertEqual(status, 201)
                selection = selected["humanSelection"]
                self.assertEqual(len(_records(second, scope)) - len(before_selection), 1)

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
                    key="e3h-http-input-plan",
                )
                input_plan_body = _input_plan_body(input_plan_command)
                status, input_plan = client.post(
                    endpoint + "/method-aware-input-plan", input_plan_body
                )
                self.assertEqual(status, 201)
                self.assertEqual(input_plan["currentness"], "CURRENT")
                self.assertEqual(input_plan["inputReadyCount"], 1)
                self.assertEqual(input_plan["resolvedAssetBindingCount"], 1)

                after_input_plan = _records(second, scope)
                status, plan_replay = client.post(
                    endpoint + "/method-aware-input-plan", input_plan_body
                )
                self.assertEqual(status, 200)
                self.assertTrue(plan_replay["idempotentReplay"])
                self.assertEqual(plan_replay["payloadDigest"], input_plan["payloadDigest"])
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
                        "idempotencyKey": "e3h-http-route-stays-blocked",
                    }
                )
                records_before_route = _records(second, scope)
                jobs_before_route = _job_counts(coordinator, scope)
                route_status, route_error = _post_rejected(
                    client, endpoint + "/method-aware-video-route", route_body
                )
                self.assertEqual(route_status, 409)
                self.assertEqual(
                    route_error["error"]["code"], "execution_not_authorized"
                )
                self.assertEqual(_records(second, scope), records_before_route)
                self.assertEqual(_job_counts(coordinator, scope), jobs_before_route)
                self.assertEqual(adapter_generate.call_count, 0)
                client.token = ""

            self.assertEqual(provider.call_count, 0)
            self.assertEqual(executable.call_count, 0)

        self.assertEqual(
            second.get_run(scope["workspaceRef"], scope["productionRunRef"])[
                "manifest"
            ],
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

        child_config = {
            "environment": environment,
            "scope": scope,
            "endpoint": endpoint,
            "candidateBody": _body(fixture.command()),
            "admissionBody": _body(admission_command),
            "inputPlanBody": input_plan_body,
            "routeBody": route_body,
            "candidateDigest": intake["candidate"]["payloadDigest"],
            "assetVersionDigest": asset["payloadDigest"],
            "inputPlanDigest": input_plan["payloadDigest"],
        }
        restarted = subprocess.run(
            [sys.executable, "-m", CHILD_MODULE, "--restart-child"],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(child_config, ensure_ascii=False) + "\n",
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        result = json.loads(restarted.stdout.strip())
        for name in (
            "candidateReplay",
            "admissionReplay",
            "inputPlanReplay",
            "inputPlanCurrent",
            "routeRejected",
            "authorityRemovalRejected",
            "tokenDestroyed",
        ):
            self.assertTrue(result[name])
        for name in (
            "recordDelta",
            "queueDelta",
            "attemptDelta",
            "adapterGenerateCount",
            "providerHttpRequestCount",
            "executableBackendConstructionCount",
        ):
            self.assertEqual(result[name], 0)


if __name__ == "__main__":
    if sys.argv[1:] == ["--restart-child"]:
        _restart_child()
    else:
        unittest.main()
