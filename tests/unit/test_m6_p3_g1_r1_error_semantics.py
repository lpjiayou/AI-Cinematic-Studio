import unittest
from contextlib import contextmanager

from services.v5_core_os.script_studio.public import (
    ScriptStudioPublicBoundary,
    ScriptStudioPublicError,
)


class _LifecycleState:
    @contextmanager
    def read_snapshot(self):
        yield


class _UnexpectedFailureReader:
    def get_active_episode_baseline(self, *_refs):
        raise KeyError("unexpected internal implementation detail")


class M6EpisodeBaselineErrorSemanticsTests(unittest.TestCase):
    def test_unexpected_failure_uses_neutral_internal_error(self):
        boundary = ScriptStudioPublicBoundary(
            object(), lifecycle_state=_LifecycleState()
        )
        boundary._bind_m6_episode_baseline_reader(_UnexpectedFailureReader())

        with self.assertRaises(ScriptStudioPublicError) as raised:
            boundary.get_m6_episode_baseline(
                "workspace-ref",
                "project-ref",
                "series-ref",
                "episode-ref",
            )

        self.assertEqual(raised.exception.code, "m6_consumer_internal_error")
        self.assertEqual(raised.exception.status, 500)
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
