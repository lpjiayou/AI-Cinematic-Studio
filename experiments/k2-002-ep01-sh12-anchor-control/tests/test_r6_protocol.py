from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Mapping

from r6_protocol import (
    AttemptIds,
    ComfyLifecycle,
    HttpResult,
    ProtocolError,
    bind_history,
    canonical_sha256,
    compensation_gate,
    dry_run_report,
)


EXPERIMENT = "K2-002-EP01-SH12-R6-ANCHOR-ONLY"
PROMPT = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "tiny.png"}},
    "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "protocol-test"}},
}


def fixed_ids() -> AttemptIds:
    return AttemptIds(
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
        "44444444-4444-4444-8444-444444444444",
    )


def history_for(ids: AttemptIds, prompt: Mapping[str, Any] = PROMPT, **overrides: Any) -> dict[str, Any]:
    extra = {
        "client_id": ids.client_id,
        "k2_attempt_id": ids.attempt_id,
        "k2_correlation_id": ids.correlation_id,
        "k2_experiment_id": EXPERIMENT,
        "k2_workflow_canonical_sha256": canonical_sha256(prompt),
        "k2_authority_state": "TECHNICAL_EVIDENCE_ONLY",
    }
    extra.update(overrides.pop("extra", {}))
    prompt_id = overrides.pop("tuple_prompt_id", ids.prompt_id)
    outputs = overrides.pop(
        "outputs",
        {"2": {"images": [{"filename": "tiny_00001_.png", "subfolder": "", "type": "output"}]}},
    )
    entry = {"prompt": [7, prompt_id, prompt, extra, ["2"]], "outputs": outputs}
    entry.update(overrides)
    return {ids.prompt_id: entry}


class FakeAdapter:
    def __init__(
        self,
        *,
        history_empty_reads: int = 0,
        events: list[Mapping[str, Any]] | None = None,
        response_prompt_id: str | None = None,
        history_mutator=None,
        initial_sid_matches: bool = True,
        queue_sequence: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self.history_empty_reads = history_empty_reads
        self.events = list(events or [])
        self.response_prompt_id = response_prompt_id
        self.history_mutator = history_mutator
        self.initial_sid_matches = initial_sid_matches
        self.queue_sequence = list(queue_sequence or [])
        self.submitted: Mapping[str, Any] | None = None
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []
        self.closed = False

    async def connect_ws(self, client_id: str) -> Mapping[str, Any]:
        sid = client_id if self.initial_sid_matches else "wrong-client"
        return {"type": "status", "data": {"sid": sid, "status": {}}}

    async def receive_ws(self, timeout_seconds: float) -> Mapping[str, Any] | None:
        if self.events:
            event = self.events.pop(0)
            if event == {"AUTO_COMPLETE": True}:
                assert self.submitted is not None
                return {"type": "executing", "data": {"prompt_id": self.submitted["prompt_id"], "node": None}}
            return event
        await asyncio.sleep(0)
        return None

    async def request_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> HttpResult:
        self.calls.append((method, path, payload))
        if method == "POST" and path == "/prompt":
            assert payload is not None
            self.submitted = payload
            prompt_id = self.response_prompt_id if self.response_prompt_id is not None else payload["prompt_id"]
            return HttpResult(200, {"prompt_id": prompt_id, "number": 1, "node_errors": {}})
        if method == "GET" and path.startswith("/history/"):
            if self.history_empty_reads > 0:
                self.history_empty_reads -= 1
                return HttpResult(200, {})
            assert self.submitted is not None
            ids = AttemptIds(
                self.submitted["extra_data"]["k2_attempt_id"],
                self.submitted["prompt_id"],
                self.submitted["client_id"],
                self.submitted["extra_data"]["k2_correlation_id"],
            )
            value = history_for(ids, self.submitted["prompt"])
            if self.history_mutator is not None:
                value = self.history_mutator(value, ids)
            return HttpResult(200, value)
        if method == "GET" and path == "/queue":
            if self.queue_sequence:
                return HttpResult(200, self.queue_sequence.pop(0))
            return HttpResult(200, {"queue_running": [], "queue_pending": []})
        if method == "POST" and path.startswith("/api/jobs/") and path.endswith("/cancel"):
            return HttpResult(200, {})
        raise AssertionError((method, path, payload))

    async def close(self) -> None:
        self.closed = True


def lifecycle(adapter: FakeAdapter) -> ComfyLifecycle:
    return ComfyLifecycle(adapter, timeout_seconds=0.5, poll_seconds=0.001)


class ProtocolBindingTests(unittest.IsolatedAsyncioTestCase):
    def test_01_empty_history_is_pending_not_mismatch(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            bind_history({}, fixed_ids(), EXPERIMENT, PROMPT)
        self.assertEqual(caught.exception.code, "HISTORY_PENDING")

    async def test_02_history_after_empty_reads_binds(self) -> None:
        adapter = FakeAdapter(history_empty_reads=3, events=[{"AUTO_COMPLETE": True}])
        result = await lifecycle(adapter).run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual(result.history_pending_count, 3)
        self.assertEqual(result.history.prompt_id, result.ids.prompt_id)

    def test_03_history_tuple_indexes_are_1_2_3(self) -> None:
        ids = fixed_ids()
        bound = bind_history(history_for(ids), ids, EXPERIMENT, PROMPT)
        self.assertEqual(bound.prompt_id, ids.prompt_id)
        self.assertEqual(bound.submitted_workflow_sha256, bound.history_workflow_sha256)

    async def test_04_top_level_client_id_reaches_history_extra_data(self) -> None:
        adapter = FakeAdapter(events=[{"AUTO_COMPLETE": True}])
        result = await lifecycle(adapter).run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual(result.request["client_id"], result.ids.client_id)
        history_extra = result.request["extra_data"]
        self.assertNotIn("client_id", history_extra)
        self.assertEqual(result.history.prompt_id, result.ids.prompt_id)

    async def test_05_response_prompt_id_mismatch_is_rejected(self) -> None:
        adapter = FakeAdapter(response_prompt_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        runner = lifecycle(adapter)
        with self.assertRaises(ProtocolError) as caught:
            await runner.run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual(caught.exception.code, "PROMPT_ID_RESPONSE_MISMATCH")
        self.assertEqual(runner.prompt_posts, 1)

    async def test_06_each_execute_has_fresh_uuid4_ids(self) -> None:
        results = []
        for _ in range(2):
            result = await lifecycle(FakeAdapter(events=[{"AUTO_COMPLETE": True}])).run(PROMPT, experiment_id=EXPERIMENT)
            results.append(result)
        for result in results:
            self.assertEqual(uuid.UUID(result.ids.prompt_id).version, 4)
            self.assertEqual(uuid.UUID(result.ids.client_id).version, 4)
        self.assertNotEqual(results[0].ids.prompt_id, results[1].ids.prompt_id)
        self.assertNotEqual(results[0].ids.client_id, results[1].ids.client_id)

    def test_07_dry_run_creates_no_execute_ids(self) -> None:
        report = dry_run_report(PROMPT)
        self.assertFalse(report["executeIdentifiersCreated"])
        self.assertEqual(report["promptPostCount"], 0)
        self.assertNotIn("prompt_id", json.dumps(report))

    def test_08_stale_prompt_id_is_not_accepted(self) -> None:
        ids = fixed_ids()
        value = history_for(ids, tuple_prompt_id="55555555-5555-4555-8555-555555555555")
        with self.assertRaises(ProtocolError) as caught:
            bind_history(value, ids, EXPERIMENT, PROMPT)
        self.assertEqual(caught.exception.code, "HISTORY_MISMATCH")
        self.assertEqual(caught.exception.details["pointer"], "/prompt/1")

    async def test_09_other_prompt_completion_does_not_finish_wait(self) -> None:
        other = {"type": "executing", "data": {"prompt_id": "other", "node": None}}
        adapter = FakeAdapter(events=[other, {"AUTO_COMPLETE": True}])
        result = await lifecycle(adapter).run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual(len(result.websocket_events), 2)
        self.assertEqual(result.websocket_events[0]["data"]["prompt_id"], "other")

    async def test_10_matching_node_none_is_required_for_completion(self) -> None:
        class NodesAdapter(FakeAdapter):
            async def receive_ws(self, timeout_seconds: float) -> Mapping[str, Any] | None:
                assert self.submitted is not None
                if not hasattr(self, "sent_node"):
                    self.sent_node = True
                    return {"type": "executing", "data": {"prompt_id": self.submitted["prompt_id"], "node": "2"}}
                return {"type": "executing", "data": {"prompt_id": self.submitted["prompt_id"], "node": None}}

        result = await lifecycle(NodesAdapter()).run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual([row["data"]["node"] for row in result.websocket_events], ["2", None])

    def test_11_wrong_history_client_id_has_pointer_diff(self) -> None:
        ids = fixed_ids()
        value = history_for(ids, extra={"client_id": "wrong"})
        with self.assertRaises(ProtocolError) as caught:
            bind_history(value, ids, EXPERIMENT, PROMPT)
        self.assertEqual(caught.exception.code, "HISTORY_MISMATCH")
        self.assertEqual(caught.exception.details[0]["pointer"], "/prompt/3/client_id")

    def test_12_workflow_mismatch_has_json_pointer_diff(self) -> None:
        ids = fixed_ids()
        changed = json.loads(json.dumps(PROMPT))
        changed["1"]["inputs"]["image"] = "wrong.png"
        with self.assertRaises(ProtocolError) as caught:
            bind_history(history_for(ids, changed), ids, EXPERIMENT, PROMPT)
        self.assertEqual(caught.exception.code, "WORKFLOW_CANONICALIZATION_MISMATCH")
        self.assertEqual(caught.exception.details[0]["pointer"], "/1/inputs/image")

    def test_13_wrong_attempt_or_correlation_is_rejected(self) -> None:
        ids = fixed_ids()
        for key in ("k2_attempt_id", "k2_correlation_id"):
            with self.subTest(key=key):
                with self.assertRaises(ProtocolError) as caught:
                    bind_history(history_for(ids, extra={key: "wrong"}), ids, EXPERIMENT, PROMPT)
                self.assertEqual(caught.exception.code, "HISTORY_MISMATCH")
                self.assertEqual(caught.exception.details[0]["pointer"], f"/prompt/3/{key}")

    async def test_14_targeted_cancel_only_names_current_prompt(self) -> None:
        target = fixed_ids().prompt_id
        other = "66666666-6666-4666-8666-666666666666"
        before = {"queue_running": [[1, target, {}, {}], [2, other, {}, {}]], "queue_pending": []}
        after = {"queue_running": [[2, other, {}, {}]], "queue_pending": []}
        adapter = FakeAdapter(queue_sequence=[before, after])
        result = await lifecycle(adapter).cancel_targeted(target)
        cancel_calls = [row for row in adapter.calls if row[0] == "POST"]
        self.assertEqual(cancel_calls[0][1], f"/api/jobs/{target}/cancel")
        self.assertNotIn(other, cancel_calls[0][1])
        self.assertTrue(result["confirmedAbsent"])

    async def test_15_error_after_post_never_posts_a_second_prompt(self) -> None:
        def mutate(value, ids):
            value[ids.prompt_id]["prompt"][3]["client_id"] = "wrong"
            return value

        adapter = FakeAdapter(events=[{"AUTO_COMPLETE": True}], history_mutator=mutate)
        runner = lifecycle(adapter)
        with self.assertRaises(ProtocolError):
            await runner.run(PROMPT, experiment_id=EXPERIMENT)
        prompt_posts = [row for row in adapter.calls if row[0] == "POST" and row[1] == "/prompt"]
        self.assertEqual(len(prompt_posts), 1)
        self.assertEqual(runner.prompt_posts, 1)

    def test_16_r5_consumed_lock_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "RUN_ATTEMPT_1.json"
            lock.write_bytes(b'{"runBudgetConsumed":true}\n')
            before = lock.read_bytes()
            report = compensation_gate(lock, [])
            self.assertEqual(lock.read_bytes(), before)
            self.assertTrue(report["r5AttemptLockPreserved"])
            self.assertTrue(report["r5RunBudgetConsumed"])

    async def test_17_r6_budget_permits_only_one_prompt_post(self) -> None:
        adapter = FakeAdapter(events=[{"AUTO_COMPLETE": True}])
        runner = lifecycle(adapter)
        await runner.run(PROMPT, experiment_id=EXPERIMENT)
        with self.assertRaises(ProtocolError) as caught:
            await runner.run(PROMPT, experiment_id=EXPERIMENT)
        self.assertEqual(caught.exception.code, "POST_BUDGET_EXCEEDED")
        prompt_posts = [row for row in adapter.calls if row[0] == "POST" and row[1] == "/prompt"]
        self.assertEqual(len(prompt_posts), 1)

    def test_18_complete_r5_output_blocks_compensation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "RUN_ATTEMPT_1.json"
            output = root / "EP01_SH12_R5.mp4"
            lock.write_text('{"runBudgetConsumed":true}\n', encoding="utf-8")
            output.write_bytes(b"complete-media")
            blocked = compensation_gate(lock, [output])
            allowed = compensation_gate(lock, [root / "missing.mp4"])
            self.assertFalse(blocked["r6CompensationAllowed"])
            self.assertTrue(allowed["r6CompensationAllowed"])


if __name__ == "__main__":
    unittest.main()
