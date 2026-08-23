import json
import os
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
    capability_services_from_environment,
    create_server,
    service_from_environment,
)
from services.v4_platform import (
    DeepSeekTextProvider,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TextGenerationRequest,
    TextMessage,
    create_text_provider_from_environment,
)
from services.v5_core_os.text_generation import (
    TextGenerationPurpose,
    TextGenerationTimeoutError,
    TextGenerationUnavailableError,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability


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
        capability = FakeTextGenerationCapability([json.dumps(valid_plan(), ensure_ascii=False)])
        AiDirectorService(capability).generate(valid_brief())
        command = capability.commands[0]
        self.assertEqual(command.purpose, TextGenerationPurpose.AI_DIRECTOR_CANDIDATE)
        self.assertEqual([item.role for item in command.messages], ["system", "user"])
        self.assertIn("晚灯", command.messages[1].content)
        self.assertIn(AI_DIRECTOR_SCHEMA_VERSION, command.messages[0].content)
        self.assertNotIn("DeepSeek", command.messages[0].content)

    def test_fake_provider_success_returns_detached_validated_plan(self):
        plan = valid_plan()
        capability = FakeTextGenerationCapability([json.dumps(plan, ensure_ascii=False)])
        result = AiDirectorService(capability).generate(valid_brief())
        self.assertEqual(result, plan)
        self.assertIsNot(result, plan)
        self.assertEqual(len(capability.commands), 1)

    def test_provider_timeout_maps_to_stable_capability_error(self):
        capability = FakeTextGenerationCapability([TextGenerationTimeoutError()])
        with self.assertRaises(PlanGenerationError) as context:
            AiDirectorService(capability).generate(valid_brief())
        self.assertEqual(context.exception.code, "provider_timeout")

    def test_malformed_output_gets_one_controlled_repair(self):
        capability = FakeTextGenerationCapability(["not json", json.dumps(valid_plan(), ensure_ascii=False)])
        result = AiDirectorService(capability).generate(valid_brief())
        self.assertEqual(result["schemaVersion"], AI_DIRECTOR_SCHEMA_VERSION)
        self.assertEqual(len(capability.commands), 2)
        self.assertTrue(all(command.purpose is TextGenerationPurpose.AI_DIRECTOR_CANDIDATE for command in capability.commands))
        self.assertIn("上一次 JSON 未通过本地验证", capability.commands[1].messages[1].content)

    def test_repair_failure_stops_after_exactly_two_provider_calls(self):
        capability = FakeTextGenerationCapability(["not json", "still not json", json.dumps(valid_plan())])
        with self.assertRaises(PlanGenerationError) as context:
            AiDirectorService(capability).generate(valid_brief())
        self.assertEqual(context.exception.code, "invalid_provider_output")
        self.assertEqual(len(capability.commands), 2)

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


class TextGenerationCompositionTests(unittest.TestCase):
    def test_server_service_uses_v5_environment_factory_at_composition_time(self):
        capability = FakeTextGenerationCapability([json.dumps(valid_plan())])
        with patch(
            "apps.creator_workspace_mvp.server.create_text_generation_capability_from_environment",
            return_value=capability,
        ) as factory:
            service = service_from_environment()
        factory.assert_called_once_with()
        self.assertEqual(service.generate(valid_brief())["schemaVersion"], AI_DIRECTOR_SCHEMA_VERSION)
        self.assertEqual(len(capability.commands), 1)

    def test_environment_composition_shares_one_v5_capability_across_services(self):
        capability = FakeTextGenerationCapability([])
        with patch(
            "apps.creator_workspace_mvp.server.create_text_generation_capability_from_environment",
            return_value=capability,
        ) as factory:
            ai_director, script_studio, series_director = capability_services_from_environment()
        factory.assert_called_once_with()
        self.assertIs(ai_director._text_generation, capability)
        self.assertIs(script_studio._text_generation, capability)
        self.assertIs(series_director._text_generation, capability)

    def test_missing_startup_credential_uses_safe_unconfigured_branch(self):
        with patch.dict(os.environ, {}, clear=True):
            service = service_from_environment()
        with self.assertRaises(PlanGenerationError) as context:
            service.generate(valid_brief())
        self.assertEqual(context.exception.code, "provider_unavailable")
        self.assertEqual(context.exception.diagnostic_category, "credential_missing")
        self.assertNotIn("PROVIDER_API_KEY", str(context.exception))


class CreatorAiDirectorEndpointTests(unittest.TestCase):
    def _serve(self, capability):
        server = create_server(("127.0.0.1", 0), AiDirectorService(capability))
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
        capability = FakeTextGenerationCapability([json.dumps(valid_plan(), ensure_ascii=False)])
        base_url = self._serve(capability)
        with self._post(base_url, {"brief": valid_brief()}) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertNotEqual(response.status, 501)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "candidate-creative-plan")
        self.assertTrue(payload["confirmationRequired"])
        self.assertNotIn("projectId", payload)
        self.assertEqual(len(capability.commands), 1)

    def test_malformed_json_returns_structured_client_error(self):
        base_url = self._serve(FakeTextGenerationCapability([json.dumps(valid_plan())]))
        with self.assertRaises(error.HTTPError) as context:
            self._post_raw(base_url, b"{not-json")
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_non_json_content_type_is_rejected_before_provider_call(self):
        capability = FakeTextGenerationCapability([json.dumps(valid_plan())])
        base_url = self._serve(capability)
        with self.assertRaises(error.HTTPError) as context:
            self._post_raw(base_url, b"{}", "text/plain")
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 415)
        self.assertEqual(payload["error"]["code"], "unsupported_media_type")
        self.assertEqual(capability.commands, [])

    def test_endpoint_rejects_invalid_brief_without_provider_call(self):
        capability = FakeTextGenerationCapability([json.dumps(valid_plan())])
        base_url = self._serve(capability)
        with self.assertRaises(error.HTTPError) as context:
            self._post(base_url, {"brief": {}})
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 400)
        self.assertEqual(payload["error"]["code"], "invalid_brief")
        self.assertEqual(capability.commands, [])

    def test_endpoint_provider_error_is_sanitized(self):
        base_url = self._serve(FakeTextGenerationCapability([TextGenerationTimeoutError()]))
        with self._post(base_url, {"brief": valid_brief()}) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        self.assertEqual(response.status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "provider_timeout")
        self.assertNotIn("raw-secret", body)
        self.assertNotIn("Authorization", body)

    def test_endpoint_logs_safe_provider_diagnostic_without_secret(self):
        capability_error = TextGenerationUnavailableError(
            category="provider_http_error",
            status=429,
        )
        base_url = self._serve(FakeTextGenerationCapability([capability_error]))
        diagnostic = StringIO()
        with patch("sys.stderr", diagnostic):
            with self._post(base_url, {"brief": valid_brief()}) as response:
                body = response.read().decode("utf-8")
        self.assertIn(
            "AI_DIRECTOR_PROVIDER_ERROR category=provider_http_error "
            "status=429 exception=TextGenerationUnavailableError",
            diagnostic.getvalue(),
        )
        self.assertNotIn("provider request failed", diagnostic.getvalue())
        self.assertNotIn("Authorization", diagnostic.getvalue())
        self.assertNotIn("test-only-secret", diagnostic.getvalue())
        self.assertNotIn("provider request failed", body)

    def test_endpoint_normalizes_untrusted_v5_diagnostics_before_logging(self):
        secret = "Authorization=Bearer sk-provider-secret"
        capability_error = TextGenerationUnavailableError(category=secret, status=799)
        base_url = self._serve(FakeTextGenerationCapability([capability_error]))
        diagnostic = StringIO()
        with patch("sys.stderr", diagnostic):
            with self._post(base_url, {"brief": valid_brief()}) as response:
                self.assertEqual(response.status, 200)
        log = diagnostic.getvalue()
        self.assertIn(
            "AI_DIRECTOR_PROVIDER_ERROR category=network_error "
            "status=none exception=TextGenerationUnavailableError",
            log,
        )
        self.assertNotIn(secret, log)
        self.assertNotIn("Authorization", diagnostic.getvalue())


if __name__ == "__main__":
    unittest.main()
