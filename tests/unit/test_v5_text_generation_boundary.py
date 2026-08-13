from dataclasses import FrozenInstanceError, fields
import unittest
from unittest.mock import patch

from services.v4_platform import (
    FakeTextProvider,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TextGenerationRequest as V4TextGenerationRequest,
    TextMessage as V4TextMessage,
)
from services.v5_core_os import text_generation as public_package
from services.v5_core_os.text_generation import (
    TextGenerationCapabilityError,
    TextGenerationCommand,
    TextGenerationConfigurationError,
    TextGenerationMessage,
    TextGenerationPublicBoundary,
    TextGenerationPurpose,
    TextGenerationTimeoutError,
    TextGenerationUnavailableError,
    create_text_generation_capability_from_environment,
    create_unconfigured_text_generation_capability,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability


class TextGenerationContractTests(unittest.TestCase):
    def test_public_exports_are_closed_and_do_not_export_testing_fake(self):
        self.assertEqual(
            set(public_package.__all__),
            {
                "TextGenerationCapability",
                "TextGenerationCapabilityError",
                "TextGenerationCommand",
                "TextGenerationConfigurationError",
                "TextGenerationMessage",
                "TextGenerationPublicBoundary",
                "TextGenerationPurpose",
                "TextGenerationTimeoutError",
                "TextGenerationUnavailableError",
                "create_text_generation_capability_from_environment",
                "create_unconfigured_text_generation_capability",
            },
        )
        self.assertNotIn("FakeTextGenerationCapability", public_package.__all__)

    def test_purpose_values_and_immutable_dto_fields_are_exact(self):
        self.assertEqual(
            {item.name: item.value for item in TextGenerationPurpose},
            {
                "AI_DIRECTOR_CANDIDATE": "ai-director-candidate",
                "SCRIPT_CANDIDATE": "script-candidate",
                "SCRIPT_SCENE_REWRITE": "script-scene-rewrite",
                "SERIES_PLAN_CANDIDATE": "series-plan-candidate",
            },
        )
        self.assertEqual([field.name for field in fields(TextGenerationMessage)], ["role", "content"])
        self.assertEqual([field.name for field in fields(TextGenerationCommand)], ["purpose", "messages"])
        message = TextGenerationMessage("user", "candidate")
        with self.assertRaises(FrozenInstanceError):
            message.content = "changed"

    def test_v5_dtos_are_not_v4_aliases_or_subclasses(self):
        self.assertIsNot(TextGenerationMessage, V4TextMessage)
        self.assertIsNot(TextGenerationCommand, V4TextGenerationRequest)
        self.assertFalse(issubclass(TextGenerationMessage, V4TextMessage))
        self.assertFalse(issubclass(TextGenerationCommand, V4TextGenerationRequest))


class TextGenerationBoundaryTests(unittest.TestCase):
    @staticmethod
    def command(purpose):
        return TextGenerationCommand(
            purpose=purpose,
            messages=(
                TextGenerationMessage("system", "system-prompt"),
                TextGenerationMessage("user", "user-prompt"),
            ),
        )

    def test_every_purpose_maps_to_exact_v4_profile_and_copies_messages(self):
        profiles = {
            TextGenerationPurpose.AI_DIRECTOR_CANDIDATE: ("json_object", 6000, 0.4, 35.0),
            TextGenerationPurpose.SCRIPT_CANDIDATE: ("json_object", 8000, 0.35, 45.0),
            TextGenerationPurpose.SCRIPT_SCENE_REWRITE: ("json_object", 3500, 0.35, 45.0),
            TextGenerationPurpose.SERIES_PLAN_CANDIDATE: ("json_object", 16000, 0.3, 90.0),
        }
        for purpose, expected in profiles.items():
            with self.subTest(purpose=purpose):
                provider = FakeTextProvider(["candidate"])
                command = self.command(purpose)
                self.assertEqual(TextGenerationPublicBoundary(provider).generate(command), "candidate")
                request = provider.requests[0]
                self.assertEqual(
                    (request.response_format, request.max_tokens, request.temperature, request.timeout_seconds),
                    expected,
                )
                self.assertEqual(
                    [(item.role, item.content) for item in request.messages],
                    [(item.role, item.content) for item in command.messages],
                )
                self.assertTrue(all(isinstance(item, V4TextMessage) for item in request.messages))
                self.assertTrue(all(v4 is not v5 for v4, v5 in zip(request.messages, command.messages)))

    def test_invalid_command_or_purpose_fails_before_provider_call(self):
        provider = FakeTextProvider(["unused"])
        boundary = TextGenerationPublicBoundary(provider)
        with self.assertRaises(TextGenerationConfigurationError) as invalid_command:
            boundary.generate(object())
        self.assertEqual(invalid_command.exception.category, "invalid_generation_command")
        command = self.command(TextGenerationPurpose.AI_DIRECTOR_CANDIDATE)
        object.__setattr__(command, "purpose", "caller-controlled-profile")
        with self.assertRaises(TextGenerationConfigurationError) as invalid_purpose:
            boundary.generate(command)
        self.assertEqual(invalid_purpose.exception.category, "invalid_generation_purpose")
        self.assertEqual(provider.requests, [])

    def test_raw_string_list_and_structural_message_fail_before_provider_call(self):
        class ExtendedCommand(TextGenerationCommand):
            pass

        provider = FakeTextProvider(["unused"])
        boundary = TextGenerationPublicBoundary(provider)
        invalid_commands = (
            ExtendedCommand(
                purpose=TextGenerationPurpose.AI_DIRECTOR_CANDIDATE,
                messages=(TextGenerationMessage("user", "candidate"),),
            ),
            TextGenerationCommand(
                purpose="ai-director-candidate",
                messages=(TextGenerationMessage("user", "candidate"),),
            ),
            TextGenerationCommand(
                purpose=TextGenerationPurpose.AI_DIRECTOR_CANDIDATE,
                messages=[TextGenerationMessage("user", "candidate")],
            ),
            TextGenerationCommand(
                purpose=TextGenerationPurpose.AI_DIRECTOR_CANDIDATE,
                messages=(V4TextMessage("user", "candidate"),),
            ),
            TextGenerationCommand(
                purpose=TextGenerationPurpose.AI_DIRECTOR_CANDIDATE,
                messages=(TextGenerationMessage("user", object()),),
            ),
        )
        for command in invalid_commands:
            with self.subTest(command=command):
                with self.assertRaises(TextGenerationConfigurationError):
                    boundary.generate(command)
        self.assertEqual(provider.requests, [])

    def test_v4_errors_map_to_safe_v5_errors_without_chain_or_raw_text(self):
        cases = (
            (
                ProviderConfigurationError("credential-value", category="credential_missing"),
                TextGenerationConfigurationError,
                "credential_missing",
                None,
            ),
            (
                ProviderTimeoutError("raw-timeout-body", status=504),
                TextGenerationTimeoutError,
                "provider_timeout",
                504,
            ),
            (
                ProviderUnavailableError("raw-http-body", category="provider_http_error", status=429),
                TextGenerationUnavailableError,
                "provider_http_error",
                429,
            ),
            (
                ProviderMalformedResponseError("raw-provider-json", category="provider_invalid_json"),
                TextGenerationUnavailableError,
                "provider_invalid_json",
                None,
            ),
        )
        for lower_error, expected_type, category, status in cases:
            with self.subTest(lower_error=type(lower_error).__name__):
                boundary = TextGenerationPublicBoundary(FakeTextProvider([lower_error]))
                with self.assertRaises(expected_type) as context:
                    boundary.generate(self.command(TextGenerationPurpose.AI_DIRECTOR_CANDIDATE))
                error = context.exception
                self.assertIsInstance(error, TextGenerationCapabilityError)
                self.assertEqual((error.category, error.status), (category, status))
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                exposed = " ".join((str(error), repr(error.args)))
                for forbidden in (
                    "credential-value",
                    "raw-timeout-body",
                    "raw-http-body",
                    "raw-provider-json",
                    "Authorization",
                ):
                    self.assertNotIn(forbidden, exposed)

    def test_untrusted_v4_diagnostics_are_normalized_before_crossing_v5(self):
        secret = "Authorization=Bearer sk-provider-secret"
        lower_error = ProviderUnavailableError(
            "generic failure",
            category=secret,
            status=799,
        )
        boundary = TextGenerationPublicBoundary(FakeTextProvider([lower_error]))
        with self.assertRaises(TextGenerationUnavailableError) as context:
            boundary.generate(self.command(TextGenerationPurpose.AI_DIRECTOR_CANDIDATE))
        error = context.exception
        self.assertEqual(error.category, "network_error")
        self.assertIsNone(error.status)
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertNotIn(secret, " ".join((str(error), repr(error.args), error.category)))

    def test_environment_factory_and_explicit_unconfigured_factory_fail_closed(self):
        for capability in (
            create_text_generation_capability_from_environment({}),
            create_text_generation_capability_from_environment({"TEXT_PROVIDER": "unsupported"}),
            create_unconfigured_text_generation_capability(),
        ):
            with self.subTest(capability=type(capability).__name__):
                with self.assertRaises(TextGenerationConfigurationError) as context:
                    capability.generate(self.command(TextGenerationPurpose.AI_DIRECTOR_CANDIDATE))
                self.assertEqual(context.exception.category, "credential_missing")
                self.assertNotIn("PROVIDER_API_KEY", str(context.exception))

    def test_environment_factory_delegates_valid_configuration_to_v4_boundary(self):
        environ = {
            "TEXT_PROVIDER": "deepseek",
            "TEXT_MODEL": "test-model",
            "PROVIDER_API_KEY": "test-only-secret",
        }
        provider = FakeTextProvider(["candidate"])
        with patch(
            "services.v5_core_os.text_generation.public.create_text_provider_from_environment",
            return_value=provider,
        ) as factory:
            capability = create_text_generation_capability_from_environment(environ)
        factory.assert_called_once_with(environ)
        self.assertEqual(
            capability.generate(self.command(TextGenerationPurpose.AI_DIRECTOR_CANDIDATE)),
            "candidate",
        )
        self.assertEqual(len(provider.requests), 1)

    def test_v5_fake_records_commands_and_fails_safely_when_exhausted(self):
        fake = FakeTextGenerationCapability(["candidate"])
        command = self.command(TextGenerationPurpose.SCRIPT_CANDIDATE)
        self.assertEqual(fake.generate(command), "candidate")
        with self.assertRaises(TextGenerationUnavailableError) as context:
            fake.generate(command)
        self.assertEqual(fake.commands, [command, command])
        self.assertEqual(context.exception.category, "fake_exhausted")


if __name__ == "__main__":
    unittest.main()
