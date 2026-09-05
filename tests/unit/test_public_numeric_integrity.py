import json
import math
import unittest

from apps.creator_workspace_mvp.ai_director import (
    CreativeBrief,
    PlanValidationError,
    validate_plan,
)
from apps.creator_workspace_mvp.strict_json import (
    MAX_PUBLIC_JSON_DEPTH,
    MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS,
    dump_public_json,
    load_public_json,
)
from services.v5_core_os.project_engine.foundation import (
    ProjectContextError,
    _positive_int as project_positive_int,
)
from services.v5_core_os.script_studio.foundation import (
    ScriptStudioError,
    _positive_int as script_positive_int,
    _positive_number as script_positive_number,
)
from services.v5_core_os.series_episode.foundation import (
    SeriesEpisodeError,
    _positive_int as series_episode_positive_int,
)
from services.v5_core_os.series_intelligence.foundation import (
    SeriesIntelligenceError,
    _nonnegative_int as intelligence_nonnegative_int,
    _positive_int as intelligence_positive_int,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


class StrictPublicJsonTests(unittest.TestCase):
    def test_shallow_object_and_depth_64_are_accepted(self):
        self.assertEqual(load_public_json(b'{"value":1}'), {"value": 1})
        raw = ("[" * MAX_PUBLIC_JSON_DEPTH + "0" + "]" * MAX_PUBLIC_JSON_DEPTH).encode()
        parsed = load_public_json(raw)
        for _ in range(MAX_PUBLIC_JSON_DEPTH):
            self.assertIsInstance(parsed, list)
            parsed = parsed[0]
        self.assertEqual(parsed, 0)

    def test_depth_scan_ignores_string_brackets_and_escaped_quotes(self):
        raw = json.dumps(
            {"value": '\\"' + "[{" * 100},
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertEqual(load_public_json(raw), json.loads(raw))

    def test_depth_65_is_rejected_before_json_decoder_recursion(self):
        raw = ("[" * (MAX_PUBLIC_JSON_DEPTH + 1) + "0" + "]" * (MAX_PUBLIC_JSON_DEPTH + 1)).encode()
        with self.assertRaises(ValueError):
            load_public_json(raw)

    def test_nonstandard_and_overflow_numbers_are_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                load_public_json(f'{{"value":{token}}}'.encode())

    def test_number_token_limit_is_exact_for_integers_and_floats(self):
        accepted_integer = "1" * MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS
        self.assertEqual(
            load_public_json(f'{{"value":{accepted_integer}}}'.encode())["value"],
            int(accepted_integer),
        )
        for token in (
            "1" * (MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS + 1),
            "0." + "1" * (MAX_PUBLIC_JSON_NUMBER_TOKEN_CHARS - 1),
        ):
            with self.subTest(length=len(token)), self.assertRaises(ValueError):
                load_public_json(f'{{"value":{token}}}'.encode())

    def test_malformed_json_and_invalid_utf8_are_stable_decode_errors(self):
        for raw in (b'{"value":1e+}', b'{"value":"\xff"}'):
            with self.subTest(raw=raw), self.assertRaises(
                (UnicodeDecodeError, json.JSONDecodeError, ValueError)
            ):
                load_public_json(raw)

    def test_duplicate_key_semantics_are_unchanged(self):
        self.assertEqual(load_public_json(b'{"value":1,"value":2}'), {"value": 2})

    def test_response_serializer_rejects_nonfinite_numbers(self):
        self.assertEqual(_strict_json_value(dump_public_json({"value": 1})), {"value": 1})
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                dump_public_json({"value": value})


def _strict_json_value(raw):
    def reject_constant(token):
        raise ValueError(token)

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


class PublicIntegerIntegrityTests(unittest.TestCase):
    def test_public_reachable_integer_helpers_accept_only_exact_ints(self):
        bounded_helpers = (
            (project_positive_int, ProjectContextError, 10_000),
            (series_episode_positive_int, SeriesEpisodeError, 100_000),
            (script_positive_int, ScriptStudioError, 100_000),
        )
        rejected = (
            0,
            -1,
            True,
            False,
            1.0,
            1.9,
            "1",
            None,
            math.nan,
            math.inf,
            -math.inf,
        )

        for helper, error_type, maximum in bounded_helpers:
            with self.subTest(helper=helper.__module__, value="minimum"):
                self.assertEqual(helper(1, "value", maximum=maximum), 1)
            with self.subTest(helper=helper.__module__, value="maximum"):
                self.assertEqual(helper(maximum, "value", maximum=maximum), maximum)
            with self.subTest(helper=helper.__module__, value="over-maximum"):
                with self.assertRaises(error_type):
                    helper(maximum + 1, "value", maximum=maximum)
            for value in rejected:
                with self.subTest(helper=helper.__module__, value=repr(value)):
                    with self.assertRaises(error_type):
                        helper(value, "value", maximum=maximum)

    def test_public_m6_revision_helpers_accept_only_exact_ints(self):
        self.assertEqual(intelligence_positive_int(1, "expectedRevision"), 1)
        self.assertEqual(intelligence_nonnegative_int(0, "activationRevision"), 0)
        rejected = (True, False, 1.0, 1.9, "1", None, math.nan, math.inf, -math.inf)
        for helper in (intelligence_positive_int, intelligence_nonnegative_int):
            for value in rejected:
                with self.subTest(helper=helper.__name__, value=repr(value)):
                    with self.assertRaises(SeriesIntelligenceError):
                        helper(value, "revision")
        with self.assertRaises(SeriesIntelligenceError):
            intelligence_positive_int(0, "expectedRevision")
        with self.assertRaises(SeriesIntelligenceError):
            intelligence_nonnegative_int(-1, "activationRevision")


class PublicPositiveNumberIntegrityTests(unittest.TestCase):
    def test_script_positive_number_requires_a_finite_numeric_type(self):
        self.assertEqual(script_positive_number(1, "durationSec"), 1.0)
        self.assertEqual(script_positive_number(3600.0, "durationSec"), 3600.0)
        for value in (
            0,
            -1,
            3600.001,
            True,
            False,
            "1",
            None,
            math.nan,
            math.inf,
            -math.inf,
        ):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ScriptStudioError):
                    script_positive_number(value, "durationSec")


class AiDirectorNumericIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.brief = CreativeBrief.from_mapping(valid_brief())

    def test_valid_plan_remains_accepted(self):
        self.assertEqual(validate_plan(valid_plan(), self.brief), valid_plan())

    def test_storyboard_duration_rejects_every_nonfinite_vector(self):
        for value in (math.nan, math.inf, -math.inf, float("1e999"), 10**400):
            plan = valid_plan()
            plan["storyboardPlan"][0]["durationSec"] = value
            with self.subTest(value=repr(value)):
                with self.assertRaises(PlanValidationError):
                    validate_plan(plan, self.brief)

    def test_storyboard_total_must_remain_finite_after_each_addition(self):
        plan = valid_plan()
        plan["storyboardPlan"][0]["durationSec"] = float.fromhex("0x1.fffffffffffffp+1023")
        plan["storyboardPlan"][1]["durationSec"] = float.fromhex("0x1.fffffffffffffp+1023")
        with self.assertRaises(PlanValidationError):
            validate_plan(plan, self.brief)


if __name__ == "__main__":
    unittest.main()
