import json
import copy
from hashlib import sha256
from http.client import RemoteDisconnected
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.server import CreatorRequestHandler, create_server
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError, NarrativeValidationProfile, NarrativeValidationProfileRegistry,
    NarrativeValidationRule, StaticIdentityReferenceAuthority, create_local_development_boundary,
)
from services.v5_core_os.episode_production.evidence import SqliteEpisodeProductionEvidenceAdapter
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_script_studio_m3 import content_from_candidate
from tests.unit.test_series_intelligence_consumer_m6_p3 import seed_consumer_on
from tests.unit.test_series_intelligence_m6 import ScopeAuthority, ApprovalAuthority
from tests.unit.test_episode_plan_binding_operator_e3e import database_snapshot


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = "workspace-e3e-http"


def profiles():
    return NarrativeValidationProfileRegistry((
        NarrativeValidationProfile("m7.narrative-currentness", 1),
        *(NarrativeValidationProfile("e3e-profile-" + severity.lower(), 1, (
            NarrativeValidationRule("e3e-rule-" + severity.lower(), "WORLD_RULE_CONFLICT",
                                    severity, "ACTION", "晚灯", {"policyRef": "e3e-test-policy"}),
        )) for severity in ("WARN", "BLOCK")),
    ))


def identity_authority():
    return StaticIdentityReferenceAuthority({ref: {
        "referenceRef": "e3e-reference-" + ref,
        "referenceVersionRef": "e3e-reference-version-" + ref,
        "contentDigest": sha256(ref.encode()).hexdigest(), "mediaType": "identity-direction",
        "rightsState": "LOCAL_EVIDENCE_ONLY", "provenance": "LOCAL_EVIDENCE",
        "approvalRef": "e3e-local-identity-approval",
    } for ref in ("character-lamp", "character-traveler")})


def runtime(directory, *, initialize=False, profile_registry=None):
    directory = Path(directory)
    assembly = LifecycleAssembly.sqlite(
        directory / "lifecycle.sqlite3", initialize_or_upgrade=initialize,
        m6_scope_authority=ScopeAuthority(), m6_approval_authority=ApprovalAuthority())
    boundary = create_local_development_boundary(
        directory / "production.sqlite3", project_boundary=assembly.project_context,
        series_episode_boundary=assembly.series_episode,
        series_planning_boundary=assembly.series_planning,
        script_studio_boundary=assembly.script_studio,
        initialize_if_missing=initialize, narrative_validation_profiles=profile_registry or profiles(),
        identity_reference_authority=identity_authority())
    return assembly, boundary


def seed_http(directory):
    assembly, boundary = runtime(directory, initialize=True)
    create_project = assembly.project_context.create_project
    with patch.object(assembly.project_context, "create_project",
                      side_effect=lambda value: create_project({**value, "aspectRatio": "16:9"})):
        seed = seed_consumer_on(assembly, workspace=WORKSPACE, plan_index=0)
    context = seed["context"]
    content = content_from_candidate()
    content["scenes"][0]["characters"].append("旅人")
    content["scenes"][0]["action"] += "旅人走进房间。"
    script = assembly.script_studio.create_version({**context, "changeKind": "ai-generation",
                                                     "content": content})
    assembly.script_studio.confirm_version({
        "workspaceRef": WORKSPACE, "seriesRef": context["seriesRef"],
        "episodeRef": context["episodeRef"], "scriptRef": script["script"]["scriptRef"],
        "scriptVersionRef": script["scriptVersion"]["scriptVersionRef"], "humanConfirmed": True})
    run = boundary.create_run({**context, "idempotencyKey": "e3e-run",
                               "shotsPerScene": [1, 1]})
    return assembly, boundary, seed, script, run


class NarrativeValidationHttpEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assembly, self.boundary, self.seed, self.script, self.run = seed_http(self.temp.name)
        self.command = {**self.seed["context"], "productionRunRef": self.run["productionRunRef"],
                        "validationProfileRef": "m7.narrative-currentness",
                        "validationProfileVersion": 1, "idempotencyKey": "e3e-validation"}
        self.token = secrets.token_urlsafe(48)
        self.foreign_token = secrets.token_urlsafe(48)
        authenticator = PublicApiAuthenticator.from_mapping({
            "schemaVersion": "creator.public-auth.v1",
            "credentials": [{"credentialRef": "e3e-" + workspace, "workspaceRef": workspace,
                             "tokenSha256": sha256(token.encode()).hexdigest(), "enabled": True}
                            for workspace, token in ((WORKSPACE, self.token), ("foreign-workspace", self.foreign_token))]})
        self.server = create_server(("127.0.0.1", 0), AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            episode_production_boundary=self.boundary,
            public_authenticator=authenticator,
            allow_internal_routes=False)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.path = f'/creator/api/v1/episode-production-runs/{self.run["productionRunRef"]}/narrative-validation'

    def stop_server(self):
        if self.server is None:
            return
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())
        self.token = None
        self.foreign_token = None
        self.server = None

    def http(self, method, path=None, payload=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + (self.token if token is True else token)
        body = None if payload is None else (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        req = request.Request(f'http://127.0.0.1:{self.server.server_port}{path or self.path}',
                              method=method, headers=headers, data=body)
        try:
            response = request.urlopen(req, timeout=10)
        except error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def post_body(self):
        return {key: value for key, value in self.command.items()
                if key not in {"workspaceRef", "productionRunRef"}}

    def query(self, **extra):
        return self.path + "?" + parse.urlencode({
            field: self.command[field] for field in ("projectRef", "seriesRef", "episodeRef")}) + (
                "&" + parse.urlencode(extra) if extra else "")

    def test_existing_core_narrative_capability_is_present(self):
        result = self.boundary.create_narrative_validation(self.command)
        self.assertIn("consistencyValidationVersionRef", result)
        self.assertEqual("CURRENT", result["currentness"])

    def test_authenticated_public_create_and_read_existing_validation(self):
        status, body = self.http("POST", payload=self.post_body())
        self.assertEqual(200, status, "Existing M7 Core capability has no authenticated public route")
        self.assertEqual({"ok", "validation"}, set(body))
        status, readback = self.http("GET", self.query())
        self.assertEqual(200, status)
        self.assertEqual(body["validation"]["payloadDigest"], readback["validation"]["payloadDigest"])

    def records(self):
        repository = SqliteEpisodeProductionEvidenceAdapter(
            Path(self.temp.name) / "production.sqlite3.evidence.sqlite3", initialize_if_missing=False)
        return repository.list_records(WORKSPACE, self.run["productionRunRef"])

    def snapshot(self):
        return {path.name: database_snapshot(path) for path in Path(self.temp.name).glob("*.sqlite3")}

    def test_auth_scope_injection_and_no_internal_or_binding_route(self):
        before = self.snapshot()
        self.assertEqual(401, self.http("POST", payload=self.post_body(), token=False)[0])
        self.assertEqual(401, self.http("GET", self.query(), token="unknown-credential")[0])
        for method in ("GET", "POST"):
            self.assertEqual(404, self.http(method, self.query() if method == "GET" else self.path,
                self.post_body() if method == "POST" else None, token=self.foreign_token)[0])
        self.assertEqual(400, self.http("POST", payload={**self.post_body(), "workspaceRef": WORKSPACE})[0])
        self.assertEqual(400, self.http("POST", payload={**self.post_body(), "productionRunRef": "forged"})[0])
        self.assertEqual(400, self.http("GET", self.query(workspaceRef=WORKSPACE))[0])
        self.assertEqual(404, self.http("POST", self.path.replace("/api/v1/", "/internal/"), self.post_body())[0])
        for resource in ("episode-plan-item-bindings", "binding-versions", "unknown"):
            self.assertEqual(404, self.http("POST", "/creator/api/v1/series-plan-versions/" + resource, self.post_body())[0])
        self.assertEqual(before, self.snapshot())

    def test_closed_body_strict_integer_duplicate_json_and_profile_resolution(self):
        before = self.snapshot()
        for key in ("validation", "findings", "m8Readiness", "scriptVersionRef", "m6ConsumerBinding",
                    "payloadDigest", "profileRules", "authority", "provider", "publicationAllowed", "unknown"):
            with self.subTest(key=key):
                self.assertEqual(400, self.http("POST", payload={**self.post_body(), key: "forged"})[0])
        for value in (True, False, 0, -1, 1.0, "1", None):
            with self.subTest(value=value):
                self.assertEqual(400, self.http("POST", payload={**self.post_body(), "validationProfileVersion": value})[0])
        body = json.dumps(self.post_body())
        for raw in (body[:-1] + ',"idempotencyKey":"duplicate"}',
                    body.replace('"validationProfileVersion": 1', '"validationProfileVersion": NaN'),
                    body.replace('"validationProfileVersion": 1', '"validationProfileVersion": 1e999')):
            self.assertEqual(400, self.http("POST", payload=raw.encode())[0])
        for changes in ({"validationProfileRef": "unknown"}, {"validationProfileVersion": 2}):
            status, result = self.http("POST", payload={**self.post_body(), **changes})
            self.assertEqual(409, status)
            self.assertEqual("upstream_not_confirmed", result["error"]["code"])
        self.assertEqual(before, self.snapshot())

    def test_get_strict_queries_missing_latest_exact_and_path(self):
        before = self.snapshot()
        self.assertEqual(404, self.http("GET", self.query())[0])
        for suffix in ("&unknown=x", "&projectRef=duplicate", "&consistencyValidationVersionRef=",
                       "&consistencyValidationVersionRef=a&consistencyValidationVersionRef=a", "&workspaceRef="):
            self.assertEqual(400, self.http("GET", self.query() + suffix)[0])
        for field in ("projectRef", "seriesRef", "episodeRef"):
            self.assertEqual(400, self.http("GET", self.path + "?" + parse.urlencode(
                {key: value for key, value in self.seed["context"].items() if key not in {field, "workspaceRef"}}))[0])
            self.assertEqual(400, self.http("GET", self.query().replace(
                parse.quote_plus(self.command[field]), ""))[0])
        self.assertEqual(404, self.http("GET", self.query().replace(self.run["productionRunRef"], "missing-run"))[0])
        self.assertEqual(before, self.snapshot())
        status, first = self.http("POST", payload=self.post_body())
        self.assertEqual(200, status)
        status, second = self.http("POST", payload={**self.post_body(), "idempotencyKey": "next-key"})
        self.assertEqual(200, status)
        before = self.snapshot()
        self.assertEqual(second["validation"], self.http("GET", self.query())[1]["validation"])
        exact = self.http("GET", self.query(consistencyValidationVersionRef=first["validation"]["consistencyValidationVersionRef"]))
        self.assertEqual(200, exact[0])
        self.assertEqual(first["validation"], exact[1]["validation"])
        self.assertEqual(404, self.http("GET", self.query(consistencyValidationVersionRef="missing"))[0])
        self.assertEqual(before, self.snapshot())

    def test_pass_warn_block_findings_projection_and_readonly_m8_consumption(self):
        lifecycle_before = database_snapshot(Path(self.temp.name) / "lifecycle.sqlite3")
        for profile, expected, ready in (("m7.narrative-currentness", "PASS", "READY_FOR_M8"),
                                       ("e3e-profile-warn", "WARN", "NOT_READY_PENDING_DISPOSITION"),
                                       ("e3e-profile-block", "BLOCK", "NOT_READY")):
            status, body = self.http("POST", payload={**self.post_body(),
                "validationProfileRef": profile, "idempotencyKey": profile})
            self.assertEqual(200, status)
            validation = body["validation"]
            self.assertEqual((expected, ready, "CURRENT"),
                             (validation["result"], validation["m8Readiness"], validation["currentness"]))
            direct = self.boundary.get_narrative_validation(*(
                self.command[field] for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef")),
                validation["consistencyValidationVersionRef"])
            self.assertEqual(validation, direct)
            self.assertEqual(validation["scriptVersionRef"], self.script["scriptVersion"]["scriptVersionRef"])
            if expected == "PASS":
                self.assertEqual([], validation["findings"])
            else:
                self.assertTrue(validation["findings"])
                finding = validation["findings"][0]
                span = finding["sourceSpan"]
                self.assertEqual("ACTION", span["sourceField"])
                text = self.script["scriptVersion"]["scenes"][0]["action"][span["startOffsetInclusive"]:span["endOffsetExclusive"]]
                self.assertEqual(sha256(text.encode()).hexdigest(), finding["sourceTextDigest"])
                self.assertEqual(expected, finding["severity"])
            before = self.snapshot()
            args = [self.command[field] for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef")]
            args.append(validation["consistencyValidationVersionRef"])
            if expected == "PASS":
                self.assertEqual(validation, self.boundary.require_m8_ready_validation(*args))
            else:
                with self.assertRaises(EpisodeProductionPublicError) as caught:
                    self.boundary.require_m8_ready_validation(*args)
                self.assertEqual("execution_not_authorized", caught.exception.code)
            self.assertEqual(before, self.snapshot())
        self.assertEqual(lifecycle_before, database_snapshot(Path(self.temp.name) / "lifecycle.sqlite3"))
        self.assertEqual(["ConsistencyValidationVersion"] * 3, [record["recordKind"] for record in self.records()])

    def test_exact_changed_replay_and_validation_precedence(self):
        first = self.http("POST", payload=self.post_body())
        self.assertEqual(200, first[0])
        before = self.snapshot()
        replay = self.http("POST", payload=self.post_body())
        self.assertEqual(200, replay[0])
        self.assertEqual({**first[1]["validation"], "idempotentReplay": True}, replay[1]["validation"])
        self.assertEqual(1, len(self.records()))
        for changes, status, code in (
            ({"validationProfileRef": "e3e-profile-warn"}, 409, "idempotency_conflict"),
            ({"validationProfileRef": "unknown"}, 409, "upstream_not_confirmed"),
            ({"projectRef": "foreign"}, 404, "not_found"),
            ({"seriesRef": "foreign"}, 404, "not_found"),
            ({"episodeRef": "foreign"}, 404, "not_found"),
            ({"result": "PASS"}, 400, "invalid_request"),
        ):
            response = self.http("POST", payload={**self.post_body(), **changes})
            self.assertEqual((status, code), (response[0], response[1]["error"]["code"]))
            self.assertNotIn(self.temp.name, json.dumps(response))
            self.assertNotIn(self.token, json.dumps(response))
        self.assertEqual(before, self.snapshot())

    def test_response_loss_and_new_interpreter_http_readback(self):
        send = CreatorRequestHandler._send_json
        def lose_response(handler, status, payload):
            if payload.get("validation") is not None:
                handler.close_connection = True
                return
            return send(handler, status, payload)
        with patch.object(CreatorRequestHandler, "_send_json", lose_response):
            with self.assertRaises(RemoteDisconnected):
                self.http("POST", payload=self.post_body())
        self.assertEqual(1, len(self.records()))
        before = self.snapshot()
        body, path = self.post_body(), self.path
        self.stop_server()
        result = subprocess.run([sys.executable, "-m", "tests.integration.test_creator_m5_m7_entrypoints_e3e_http",
                                 "--readback-e3e", self.temp.name],
            cwd=REPO, input=json.dumps({"body": body, "path": path}), capture_output=True, text=True, timeout=25, check=True)
        recovered = json.loads(result.stdout)
        self.assertNotEqual(os.getpid(), recovered["pid"])
        self.assertEqual([200, 200], recovered["statuses"])
        self.assertTrue(recovered["replay"]["idempotentReplay"])
        self.assertEqual(recovered["read"]["payloadDigest"], recovered["replay"]["payloadDigest"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(1, len(self.records()))

    def test_confirmed_script_drift_rejects_replay_and_projects_stale_without_writes(self):
        self.assertEqual(200, self.http("POST", payload=self.post_body())[0])
        content = {field: copy.deepcopy(self.script["scriptVersion"][field])
                   for field in ("title", "logline", "synopsis", "targetDurationSec", "scenes")}
        content["scenes"][0]["action"] += "晚灯稍稍暗下。"
        changed = self.assembly.script_studio.create_version({**self.seed["context"],
            "scriptRef": self.script["script"]["scriptRef"],
            "baseScriptVersionRef": self.script["scriptVersion"]["scriptVersionRef"],
            "changeKind": "manual-edit", "content": content})
        self.assembly.script_studio.confirm_version({
            "workspaceRef": WORKSPACE, "seriesRef": self.command["seriesRef"], "episodeRef": self.command["episodeRef"],
            "scriptRef": changed["script"]["scriptRef"], "scriptVersionRef": changed["scriptVersion"]["scriptVersionRef"],
            "humanConfirmed": True})
        self.assert_stale_zero_write()

    def assert_stale_zero_write(self):
        before = self.snapshot()
        response = self.http("POST", payload=self.post_body())
        self.assertEqual((409, "stale_input"), (response[0], response[1]["error"]["code"]))
        status, read = self.http("GET", self.query())
        self.assertEqual(200, status)
        self.assertEqual("STALE", read["validation"]["currentness"])
        with self.assertRaises(EpisodeProductionPublicError):
            self.boundary.require_m8_ready_validation(*(
                self.command[field] for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef")),
                read["validation"]["consistencyValidationVersionRef"])
        self.assertEqual(before, self.snapshot())

    def test_m6_source_drift_preserves_old_validation_and_rejects_replay(self):
        self.assertEqual(200, self.http("POST", payload=self.post_body())[0])
        context = {field: self.command[field] for field in ("workspaceRef", "projectRef", "seriesRef")}
        workspace = self.assembly.series_intelligence.get_workspace(*context.values())
        def operation(name):
            return {**context, "operationRef": name, "idempotencyKey": name}
        bible_content = copy.deepcopy(workspace["seriesBibleVersions"][-1]["content"])
        bible_content["worldRules"][0]["statement"] += "；来源已推进"
        bible = self.assembly.series_intelligence.create_bible_version({**operation("e3e-bible-drift"),
            "seriesBibleRef": workspace["seriesBible"]["seriesBibleRef"],
            "expectedRevision": workspace["seriesBible"]["revision"], "candidate": True, "content": bible_content})
        bible = self.assembly.series_intelligence.confirm_bible_version({**operation("e3e-bible-drift-confirm"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"], "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": bible["root"]["revision"], "approvalRef": "approval-human"})
        characters = self.assembly.series_intelligence.create_character_version({**operation("e3e-characters-drift"),
            "characterContinuityRef": workspace["characterContinuity"]["characterContinuityRef"],
            "expectedRevision": workspace["characterContinuity"]["revision"], "candidate": True,
            "seriesBibleRef": bible["root"]["seriesBibleRef"], "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "content": workspace["characterContinuityVersions"][-1]["content"]})
        characters = self.assembly.series_intelligence.confirm_character_version({**operation("e3e-characters-drift-confirm"),
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedRevision": characters["root"]["revision"], "approvalRef": "approval-human"})
        self.assembly.series_intelligence.activate_baseline({**operation("e3e-baseline-drift"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"], "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": workspace["activeBaseline"]["activationRevision"], "approvalRef": "approval-human"})
        self.assert_stale_zero_write()

    def test_legacy_shot_graph_result_is_preserved_and_not_substituted(self):
        run_scope = {"workspaceRef": WORKSPACE, "productionRunRef": self.run["productionRunRef"]}
        self.boundary.authorize_and_lock({**run_scope, "idempotencyKey": "e3e-legacy-authority", "characterMappings": [
            {"scriptCharacterName": "晚灯", "characterRef": "character-lamp"},
            {"scriptCharacterName": "旅人", "characterRef": "character-traveler"},
        ]})
        bible = self.seed["bible"]["version"]["content"]
        self.boundary.compile_shot_graph({**run_scope, "idempotencyKey": "e3e-legacy-shot-graph",
            "sceneBindings": [{"scriptSceneRef": scene["scriptSceneRef"],
                               "locationRef": bible["locations"][0]["locationRef"],
                               "propRefs": [bible["props"][0]["propRef"]]}
                              for scene in self.script["scriptVersion"]["scenes"]]})
        legacy = self.boundary.get_shot_graph_bundle(WORKSPACE, self.run["productionRunRef"])
        self.assertEqual([], self.records())
        status, result = self.http("POST", payload=self.post_body())
        self.assertEqual(200, status)
        self.assertIn("consistencyValidationVersionRef", result["validation"])
        self.assertEqual(legacy, self.boundary.get_shot_graph_bundle(WORKSPACE, self.run["productionRunRef"]))
        self.assertEqual(["ConsistencyValidationVersion"], [record["recordKind"] for record in self.records()])


def readback_worker(directory):
    value = json.loads(sys.stdin.read())
    assembly, boundary = runtime(directory)
    token = secrets.token_urlsafe(48)
    server = create_server(("127.0.0.1", 0), AiDirectorService(FakeTextGenerationCapability([])),
        series_episode_boundary=assembly.series_episode, project_boundary=assembly.project_context,
        series_planning_boundary=assembly.series_planning, script_studio_boundary=assembly.script_studio,
        episode_production_boundary=boundary, public_authenticator=PublicApiAuthenticator.for_token(token, WORKSPACE),
        allow_internal_routes=False)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}" + value["path"]
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        query = parse.urlencode({field: value["body"][field] for field in ("projectRef", "seriesRef", "episodeRef")})
        with request.urlopen(request.Request(base + "?" + query, headers=headers), timeout=10) as response:
            get_status, read = response.status, json.loads(response.read())["validation"]
        with request.urlopen(request.Request(base, headers=headers, data=json.dumps(value["body"]).encode()), timeout=10) as response:
            post_status, replay = response.status, json.loads(response.read())["validation"]
        print(json.dumps({"pid": os.getpid(), "statuses": [get_status, post_status], "read": read, "replay": replay}))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        token = None


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--readback-e3e":
        readback_worker(sys.argv[2])
    else:
        unittest.main()
