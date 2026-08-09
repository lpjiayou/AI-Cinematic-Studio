import json
import os
from pathlib import Path
from io import StringIO
import threading
import unittest
from unittest.mock import patch
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import (
    AI_DIRECTOR_SCHEMA_VERSION,
    PROJECT_DRAFT_INPUT_SCHEMA_VERSION,
    AiDirectorService,
    BriefValidationError,
    CreativeBrief,
    PlanGenerationError,
    PlanValidationError,
    ProjectDraftInputError,
    build_session_project_draft_input,
    validate_plan,
)
from apps.creator_workspace_mvp.server import (
    AI_DIRECTOR_ENDPOINT,
    create_server,
    service_from_environment,
)
from services.v4_platform import (
    DeepSeekTextProvider,
    FakeTextProvider,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TextGenerationRequest,
    TextMessage,
    create_text_provider_from_environment,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "apps" / "creator-workspace-mvp"


def valid_brief():
    return {
        "topic": "夜晚的陪伴",
        "theme": "情感短片",
        "audience": "短视频用户",
        "duration": "30秒",
        "platform": "短视频平台",
        "style": "电影感、低照度、暖色视觉焦点",
        "character": "晚灯",
    }


def valid_plan():
    return {
        "schemaVersion": AI_DIRECTOR_SCHEMA_VERSION,
        "creativeInterpretation": {
            "logline": "晚灯在深夜陪伴一位疲惫的人。",
            "coreTheme": "陪伴",
            "targetEmotion": "被理解",
            "narrativeArc": "孤独到安定",
        },
        "storyDirection": {
            "title": "晚灯还亮着",
            "synopsis": "晚灯用微弱暖光回应深夜里的疲惫。",
            "keyBeats": ["注意到疲惫", "安静陪伴", "留下一点光"],
        },
        "scriptDraft": {
            "opening": "深夜房间只剩一盏灯。",
            "development": "晚灯看见沉默的人。",
            "climax": "暖光缓慢亮起。",
            "ending": "房间仍安静，但不再孤单。",
            "captionsOrDialogue": ["今晚先不用证明自己。"],
        },
        "storyboardPlan": [
            {
                "shotNo": index,
                "durationSec": 6,
                "shotSize": "中景",
                "cameraMovement": "固定",
                "visualDescription": f"镜头 {index} 的夜晚空间",
                "narrativePurpose": "推进陪伴关系",
            }
            for index in range(1, 6)
        ],
        "visualStyle": {
            "lighting": "低照度暖光",
            "palette": "深蓝与琥珀色",
            "composition": "居中稳定构图",
            "atmosphere": "安静温暖",
            "continuityRules": ["保持晚灯轮廓", "暖光方向一致"],
        },
        "productionPlan": {
            "shotCount": 5,
            "characters": ["晚灯"],
            "scenes": ["深夜房间"],
            "visualAssets": ["角色参考", "背景", "字幕"],
            "audioNeeds": ["安静环境氛围"],
            "productionNotes": ["所有结果需人工确认"],
        },
    }


class AiDirectorCapabilityTests(unittest.TestCase):
    def test_creative_brief_validation_requires_fields_and_positive_duration(self):
        with self.assertRaises(BriefValidationError) as context:
            CreativeBrief.from_mapping({"topic": "", "duration": "0秒"})
        self.assertIn("topic", context.exception.field_errors)
        self.assertIn("duration", context.exception.field_errors)
        brief = CreativeBrief.from_mapping({**valid_brief(), "character": ""})
        self.assertEqual(brief.character, "")
        self.assertEqual(brief.duration_seconds, 30)

    def test_request_contract_is_provider_neutral_and_includes_character_context(self):
        provider = FakeTextProvider([json.dumps(valid_plan(), ensure_ascii=False)])
        AiDirectorService(provider).generate(valid_brief())
        generation_request = provider.requests[0]
        self.assertEqual(generation_request.response_format, "json_object")
        self.assertEqual([item.role for item in generation_request.messages], ["system", "user"])
        self.assertIn("晚灯", generation_request.messages[1].content)
        self.assertIn(AI_DIRECTOR_SCHEMA_VERSION, generation_request.messages[0].content)
        self.assertNotIn("DeepSeek", generation_request.messages[0].content)

    def test_fake_provider_success_returns_detached_validated_plan(self):
        plan = valid_plan()
        provider = FakeTextProvider([json.dumps(plan, ensure_ascii=False)])
        result = AiDirectorService(provider).generate(valid_brief())
        self.assertEqual(result, plan)
        self.assertIsNot(result, plan)
        self.assertEqual(len(provider.requests), 1)

    def test_provider_timeout_maps_to_stable_capability_error(self):
        provider = FakeTextProvider([ProviderTimeoutError("contains no secret")])
        with self.assertRaises(PlanGenerationError) as context:
            AiDirectorService(provider).generate(valid_brief())
        self.assertEqual(context.exception.code, "provider_timeout")

    def test_malformed_output_gets_one_controlled_repair(self):
        provider = FakeTextProvider(["not json", json.dumps(valid_plan(), ensure_ascii=False)])
        result = AiDirectorService(provider).generate(valid_brief())
        self.assertEqual(result["schemaVersion"], AI_DIRECTOR_SCHEMA_VERSION)
        self.assertEqual(len(provider.requests), 2)
        self.assertIn("上一次 JSON 未通过本地验证", provider.requests[1].messages[1].content)

    def test_repair_failure_stops_after_exactly_two_provider_calls(self):
        provider = FakeTextProvider(["not json", "still not json", json.dumps(valid_plan())])
        with self.assertRaises(PlanGenerationError) as context:
            AiDirectorService(provider).generate(valid_brief())
        self.assertEqual(context.exception.code, "invalid_provider_output")
        self.assertEqual(len(provider.requests), 2)

    def test_schema_version_and_required_fields_are_enforced(self):
        plan = valid_plan()
        plan["schemaVersion"] = "other"
        del plan["storyDirection"]["synopsis"]
        with self.assertRaises(PlanValidationError) as context:
            validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))
        self.assertGreaterEqual(len(context.exception.errors), 2)

    def test_storyboard_duration_must_match_target_and_be_positive(self):
        plan = valid_plan()
        plan["storyboardPlan"][0]["durationSec"] = -1
        with self.assertRaises(PlanValidationError):
            validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))
        plan = valid_plan()
        for shot in plan["storyboardPlan"]:
            shot["durationSec"] = 1
        with self.assertRaises(PlanValidationError):
            validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))

    def test_shot_numbers_and_count_must_match_contract(self):
        plan = valid_plan()
        plan["storyboardPlan"][1]["shotNo"] = 8
        plan["productionPlan"]["shotCount"] = 4
        with self.assertRaises(PlanValidationError) as context:
            validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))
        self.assertTrue(any("shotNo" in item for item in context.exception.errors))
        self.assertTrue(any("shotCount" in item for item in context.exception.errors))

    def test_authoritative_fields_and_direct_publish_instructions_are_rejected(self):
        for key, value in (
            ("projectId", "project-1"),
            ("asset_id", "asset-1"),
            ("approval", True),
            ("rights", "approved"),
        ):
            plan = valid_plan()
            plan["productionPlan"][key] = value
            with self.assertRaises(PlanValidationError):
                validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))
        plan = valid_plan()
        plan["productionPlan"]["productionNotes"] = ["完成后直接发布"]
        with self.assertRaises(PlanValidationError):
            validate_plan(plan, CreativeBrief.from_mapping(valid_brief()))

    def test_unconfirmed_plan_cannot_map_to_project_draft_input(self):
        with self.assertRaises(ProjectDraftInputError):
            build_session_project_draft_input(
                valid_plan(),
                valid_brief(),
                plan_version=1,
                project_ref="local-project-wanlight-001",
                confirmed=False,
            )

    def test_confirmed_plan_maps_to_structured_session_project_draft_input(self):
        plan = valid_plan()
        draft = build_session_project_draft_input(
            plan,
            valid_brief(),
            plan_version=3,
            project_ref="local-project-wanlight-001",
            confirmed=True,
        )
        self.assertEqual(draft["schemaVersion"], PROJECT_DRAFT_INPUT_SCHEMA_VERSION)
        self.assertEqual(draft["sourcePlanSchemaVersion"], AI_DIRECTOR_SCHEMA_VERSION)
        self.assertEqual(draft["sourcePlanRef"], "local-ai-director-plan-3")
        self.assertEqual(draft["sourcePlanVersion"], 3)
        self.assertEqual(draft["sourcePlan"], plan)
        self.assertEqual(draft["persistence"], "session-only")
        self.assertFalse(draft["domainFact"])
        self.assertEqual(draft["story"]["direction"], plan["storyDirection"])
        self.assertEqual(draft["characters"], plan["productionPlan"]["characters"])
        self.assertEqual(draft["scenes"], plan["productionPlan"]["scenes"])
        self.assertEqual(draft["storyboard"], plan["storyboardPlan"])
        self.assertEqual(draft["visualStyle"], plan["visualStyle"])
        self.assertEqual(draft["productionPlan"], plan["productionPlan"])
        self.assertNotIn("projectId", draft)


class TextProviderAdapterTests(unittest.TestCase):
    def test_environment_factory_requires_only_server_side_credential(self):
        with self.assertRaises(ProviderConfigurationError):
            create_text_provider_from_environment({"TEXT_PROVIDER": "deepseek"})
        provider = create_text_provider_from_environment(
            {
                "TEXT_PROVIDER": "deepseek",
                "TEXT_MODEL": "deepseek-v4-pro",
                "PROVIDER_API_KEY": "test-only-secret",
            }
        )
        self.assertIsInstance(provider, DeepSeekTextProvider)
        default_provider = create_text_provider_from_environment(
            {"PROVIDER_API_KEY": "test-only-secret"}
        )
        self.assertEqual(default_provider.model, "deepseek-v4-pro")

    def test_environment_is_read_when_server_service_is_created_not_at_import(self):
        with patch.dict(
            os.environ,
            {
                "TEXT_PROVIDER": "deepseek",
                "TEXT_MODEL": "deepseek-v4-pro",
                "PROVIDER_API_KEY": "startup-only-secret",
            },
            clear=True,
        ):
            service = service_from_environment()
        self.assertIsInstance(service._provider, DeepSeekTextProvider)
        self.assertEqual(service._provider.model, "deepseek-v4-pro")

    def test_missing_startup_credential_uses_safe_unconfigured_branch(self):
        with patch.dict(os.environ, {}, clear=True):
            service = service_from_environment()
        with self.assertRaises(PlanGenerationError) as context:
            service.generate(valid_brief())
        self.assertEqual(context.exception.code, "provider_unavailable")
        self.assertEqual(context.exception.diagnostic_category, "credential_missing")
        self.assertNotIn("PROVIDER_API_KEY", str(context.exception))

    @patch("services.v4_platform.text_generation.request.urlopen")
    def test_deepseek_adapter_uses_current_json_chat_contract(self, urlopen):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": json.dumps(valid_plan())},
                            }
                        ]
                    }
                ).encode("utf-8")

        urlopen.return_value = Response()
        provider = DeepSeekTextProvider(api_key="test-only-secret")
        content = provider.generate(
            TextGenerationRequest(messages=(TextMessage("user", "return json"),))
        )
        self.assertIn(AI_DIRECTOR_SCHEMA_VERSION, content)
        sent_request = urlopen.call_args.args[0]
        sent_body = json.loads(sent_request.data.decode("utf-8"))
        self.assertEqual(sent_request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(sent_body["model"], "deepseek-v4-pro")
        self.assertEqual(sent_body["response_format"], {"type": "json_object"})
        self.assertEqual(sent_body["thinking"], {"type": "disabled"})
        self.assertFalse(sent_body["stream"])
        self.assertIsInstance(sent_request.data, bytes)
        expected_authorization = "Bearer " + "test-only-" + "secret"
        self.assertEqual(sent_request.get_header("Authorization"), expected_authorization)
        self.assertEqual(sent_request.get_header("Content-type"), "application/json")

    @patch("services.v4_platform.text_generation.request.urlopen")
    def test_provider_http_error_has_safe_category_and_status(self, urlopen):
        urlopen.side_effect = error.HTTPError(
            "https://api.deepseek.com/chat/completions",
            429,
            "raw-provider-message",
            {},
            None,
        )
        provider = DeepSeekTextProvider(api_key="test-only-secret")
        with self.assertRaises(ProviderUnavailableError) as context:
            provider.generate(TextGenerationRequest(messages=(TextMessage("user", "json"),)))
        self.assertEqual(context.exception.category, "provider_http_error")
        self.assertEqual(context.exception.status, 429)
        self.assertNotIn("raw-provider-message", str(context.exception))
        self.assertNotIn("test-only-secret", str(context.exception))

    @patch("services.v4_platform.text_generation.request.urlopen")
    def test_deepseek_adapter_rejects_empty_and_truncated_content(self, urlopen):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps(self.payload).encode("utf-8")

        provider = DeepSeekTextProvider(api_key="test-only-secret")
        for payload in (
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        ):
            with self.subTest(payload=payload):
                urlopen.return_value = Response(payload)
                with self.assertRaises(ProviderMalformedResponseError) as context:
                    provider.generate(TextGenerationRequest(messages=(TextMessage("user", "json"),)))
                self.assertNotIn("test-only-secret", str(context.exception))

    @patch("services.v4_platform.text_generation.request.urlopen")
    def test_deepseek_adapter_timeout_does_not_leak_secret(self, urlopen):
        urlopen.side_effect = TimeoutError("test-only-secret")
        provider = DeepSeekTextProvider(api_key="test-only-secret")
        with self.assertRaises(ProviderTimeoutError) as context:
            provider.generate(TextGenerationRequest(messages=(TextMessage("user", "json"),)))
        self.assertNotIn("test-only-secret", str(context.exception))


class CreatorAiDirectorEndpointTests(unittest.TestCase):
    def _serve(self, provider):
        server = create_server(("127.0.0.1", 0), AiDirectorService(provider), APP_ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def _post(self, base_url, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return request.urlopen(
            request.Request(
                f"{base_url}{AI_DIRECTOR_ENDPOINT}",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=5,
        )

    def _post_raw(self, base_url, body, content_type="application/json"):
        return request.urlopen(
            request.Request(
                f"{base_url}{AI_DIRECTOR_ENDPOINT}",
                data=body,
                method="POST",
                headers={"Content-Type": content_type},
            ),
            timeout=5,
        )

    def test_same_origin_endpoint_returns_candidate_not_domain_fact(self):
        provider = FakeTextProvider([json.dumps(valid_plan(), ensure_ascii=False)])
        base_url = self._serve(provider)
        with self._post(base_url, {"brief": valid_brief()}) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertNotEqual(response.status, 501)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "candidate-creative-plan")
        self.assertTrue(payload["confirmationRequired"])
        self.assertNotIn("projectId", payload)
        self.assertEqual(len(provider.requests), 1)

    def test_malformed_json_returns_structured_client_error(self):
        base_url = self._serve(FakeTextProvider([json.dumps(valid_plan())]))
        with self.assertRaises(error.HTTPError) as context:
            self._post_raw(base_url, b"{not-json")
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_non_json_content_type_is_rejected_before_provider_call(self):
        provider = FakeTextProvider([json.dumps(valid_plan())])
        base_url = self._serve(provider)
        with self.assertRaises(error.HTTPError) as context:
            self._post_raw(base_url, b"{}", "text/plain")
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 415)
        self.assertEqual(payload["error"]["code"], "unsupported_media_type")
        self.assertEqual(provider.requests, [])

    def test_get_static_assets_uses_creator_handler(self):
        base_url = self._serve(FakeTextProvider([]))
        with request.urlopen(f"{base_url}/app.js", timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.headers["Server"].startswith("CreatorWorkspace/1.0"))
        self.assertIn('aiDirectorEndpoint = "/creator/internal/ai-director/plan"', body)

    def test_frontend_and_server_endpoint_paths_match_exactly(self):
        script = (APP_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertEqual(AI_DIRECTOR_ENDPOINT, "/creator/internal/ai-director/plan")
        self.assertIn(f'aiDirectorEndpoint = "{AI_DIRECTOR_ENDPOINT}"', script)

    def test_endpoint_rejects_invalid_brief_without_provider_call(self):
        provider = FakeTextProvider([json.dumps(valid_plan())])
        base_url = self._serve(provider)
        with self.assertRaises(error.HTTPError) as context:
            self._post(base_url, {"brief": {}})
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["error"]["code"], "invalid_brief")
        self.assertEqual(provider.requests, [])

    def test_endpoint_provider_error_is_sanitized(self):
        base_url = self._serve(FakeTextProvider([ProviderTimeoutError("raw-secret")]))
        with self._post(base_url, {"brief": valid_brief()}) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "provider_timeout")
        self.assertNotIn("raw-secret", body)
        self.assertNotIn("Authorization", body)

    def test_endpoint_logs_safe_provider_diagnostic_without_secret(self):
        provider_error = ProviderUnavailableError(
            "provider request failed",
            category="provider_http_error",
            status=429,
        )
        base_url = self._serve(FakeTextProvider([provider_error]))
        diagnostic = StringIO()
        with patch("sys.stderr", diagnostic):
            with self._post(base_url, {"brief": valid_brief()}) as response:
                body = response.read().decode("utf-8")
        self.assertIn(
            "AI_DIRECTOR_PROVIDER_ERROR category=provider_http_error "
            "status=429 exception=ProviderUnavailableError",
            diagnostic.getvalue(),
        )
        self.assertNotIn("provider request failed", diagnostic.getvalue())
        self.assertNotIn("Authorization", diagnostic.getvalue())
        self.assertNotIn("test-only-secret", diagnostic.getvalue())
        self.assertNotIn("provider request failed", body)


class AiDirectorFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        cls.script = (APP_ROOT / "app.js").read_text(encoding="utf-8")

    def test_loading_error_and_success_states_are_present(self):
        self.assertIn('data-ai-director-state="generating"', self.script)
        self.assertIn("正在整理导演方案…", self.script)
        self.assertIn('data-ai-director-state="error"', self.script)
        self.assertIn("导演方案暂时无法生成，请稍后重试", self.script)
        self.assertIn('data-ai-director-state="${state.aiDirectorConfirmed ? "confirmed" : "result"}"', self.script)

    def test_four_director_regions_and_production_plan_are_dynamic(self):
        for marker in ("故事方向", "剧本草案", "分镜规划", "视觉风格", "镜头数量", "角色需求", "场景需求", "资产需求", "声音需求"):
            self.assertIn(marker, self.script)
        self.assertIn("plan.storyDirection", self.script)
        self.assertIn("plan.storyboardPlan", self.script)
        self.assertIn("state.aiDirectorPlan.productionPlan", self.script)

    def test_human_confirmation_gate_controls_episode_project_creation(self):
        self.assertIn('data-action="confirm-ai-director-plan"', self.script)
        self.assertIn(
            'if (!state.confirmedCreativePlan || state.seriesEpisodePhase === "creating") return',
            self.script,
        )
        self.assertIn("人工确认并保存当前创意方案后，才可创建系列与集数", self.script)
        self.assertIn("state.confirmedCreativePlan", self.script)
        self.assertIn("creativePlanRef: state.confirmedCreativePlan.creativePlanRef", self.script)
        self.assertIn("director-plan-state-confirmed", self.script)
        self.assertIn("<strong>已确认</strong><small>当前会话</small>", self.script)
        self.assertNotIn("已确认（当前会话）", self.script)

    def test_confirmed_plan_is_structurally_bound_to_episode_creation(self):
        self.assertNotIn("function buildAiDirectorProjectDraftInput", self.script)
        self.assertNotIn('schemaVersion: "creator.project-draft-input.v1"', self.script)
        self.assertIn("function createSeriesEpisode(form)", self.script)
        self.assertIn("creativePlanRef: state.confirmedCreativePlan.creativePlanRef", self.script)
        self.assertIn("workspaceRef", self.script)
        self.assertIn("seriesRef: seriesRefValue", self.script)
        self.assertIn("episodeNumber:", self.script)
        self.assertIn("seasonNumber: 1", self.script)
        self.assertIn("volumeNumber: 1", self.script)
        self.assertIn("episodePayload.episode.episodeRef", self.script)

    def test_regenerate_is_explicit_and_preserves_confirmed_plan_on_error(self):
        self.assertIn('data-action="regenerate-ai-director"', self.script)
        self.assertIn("const previousPlan = state.aiDirectorPlan", self.script)
        self.assertIn("state.aiDirectorPlan = previousPlan", self.script)
        self.assertIn("已确认方案仍保留在当前会话", self.script)

    def test_frontend_contains_no_secret_or_external_provider_host(self):
        combined = f"{self.index}\n{self.script}"
        for marker in ("PROVIDER_API_KEY", "Authorization", "api.deepseek.com", "DeepSeek", "sk-"):
            self.assertNotIn(marker, combined)
        self.assertEqual(self.script.count("fetch("), 1)
        self.assertIn('requestApplicationJson(aiDirectorEndpoint, {', self.script)
        self.assertIn('aiDirectorEndpoint = "/creator/internal/ai-director/plan"', self.script)

    def test_session_state_has_no_browser_or_database_persistence(self):
        for marker in ("localStorage", "sessionStorage", "indexedDB", "database"):
            self.assertNotIn(marker, self.script)
        self.assertIn("aiDirectorPlanVersion", self.script)
        self.assertIn("confirmedCreativePlan: null", self.script)
        self.assertIn('confirmCreativePlanEndpoint = "/creator/internal/creative-plans/confirm"', self.script)
        self.assertNotIn("aiDirectorProjectDraft", self.script)

    def test_existing_routes_preview_and_export_semantics_remain(self):
        self.assertIn('"/creator/projects/:projectRef/post/preview"', self.script)
        self.assertIn('"/creator/projects/:projectRef/delivery/exports"', self.script)
        self.assertIn("候选预览", self.script)
        self.assertIn('data-capability="export" disabled', self.script)

    def test_no_silent_fixture_fallback_plan_remains(self):
        fixture = json.loads(
            self.index.split('id="creator-fixture">', 1)[1].split("</script>", 1)[0]
        )
        self.assertNotIn("output", fixture["aiDirector"])
        self.assertNotIn("runAiDirectorFixture", self.script)


if __name__ == "__main__":
    unittest.main()
