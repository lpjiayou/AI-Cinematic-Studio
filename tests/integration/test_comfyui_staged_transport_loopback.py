"""Real local HTTP tests; synthetic fixture, never a real ComfyUI service."""
from copy import deepcopy
import http.client
import os
import time
import unittest
from unittest.mock import patch

from services.v4_platform import comfyui_staged_transport as staged
from services.v4_platform.generation_dispatch_live_contracts import (
    LiveGenerationDispatchTransportError, LOCAL_WRITE_COMPLETE, MAY_HAVE_BEEN_SENT)
from tests.support.comfyui_loopback_fixtures import (LoopbackComfyUI,
    make_loopback_client, PROMPT_ID, SYNTHETIC_MP4_BYTES, authorize_test_exchange)


class StagedLoopbackTests(unittest.TestCase):
    def test_response_header_line_total_bytes_and_count_are_bounded(self):
        for line_bytes, count in ((8193, 1), (100, 65), (4096, 9)):
            with self.subTest(line_bytes=line_bytes, count=count), LoopbackComfyUI(
                    header_line_bytes=line_bytes, header_count=count) as fixture:
                transport, exchange, submission = self.execute(fixture)
                with self.assertRaises(LiveGenerationDispatchTransportError):
                    transport.read_result(exchange, submission)
                self.assertEqual(fixture.post_count, 1)
                self.assertEqual(fixture.history_count, 0)

    def test_dripped_status_headers_obey_absolute_deadline_without_retry(self):
        with LoopbackComfyUI(drip_headers=True) as fixture:
            transport, exchange, submission = self.execute(fixture,
                request_timeout_ms=150, history_timeout_ms=150)
            started = time.monotonic()
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                transport.read_result(exchange, submission)
            self.assertLess(time.monotonic() - started, 0.6)
            self.assertGreater(fixture.dripped_bytes, 0)
            self.assertLess(fixture.dripped_bytes, 30)
            self.assertEqual(caught.exception.request_write_state, LOCAL_WRITE_COMPLETE)
            self.assertEqual(fixture.post_count, 1)
            self.assertEqual(fixture.history_count, 0)

    def test_environment_proxy_is_ignored_and_cannot_redirect_initial_post(self):
        with LoopbackComfyUI() as proxy, LoopbackComfyUI() as fixture:
            with patch.dict(os.environ, {"HTTP_PROXY": proxy.endpoint, "http_proxy": proxy.endpoint,
                    "HTTPS_PROXY": proxy.endpoint, "ALL_PROXY": proxy.endpoint, "NO_PROXY": ""}):
                transport, exchange, submission = self.execute(fixture)
                transport.read_result(exchange, submission)
            self.assertEqual(fixture.complete_post_count, 1)
            self.assertEqual(proxy.paths, [])

    def test_real_client_native49_download_and_cpu_derived48_lineage(self):
        from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png
        frames = tuple(synthetic_png(index) for index in range(49))
        with LoopbackComfyUI(frames=frames) as fixture:
            transport, request = make_loopback_client(fixture.endpoint, native_frames=True,
                history_timeout_ms=10000, postprocess_timeout_ms=60000)
            exchange = transport.open_exchange(request, deadline_monotonic=time.monotonic() + 70)
            authorize_test_exchange(transport, exchange)
            submission = transport.commit_request_once(exchange)
            result = transport.read_result(exchange, submission)
            self.assertEqual(fixture.complete_post_count, 1)
            self.assertEqual(fixture.view_count, 49)
            self.assertEqual(result.native_frames, frames)
            self.assertEqual(result.receipt["derivation"]["keptIndices"], list(range(48)))
            self.assertEqual(result.receipt["derivation"]["droppedIndices"], [48])
            self.assertEqual(result.receipt["derivation"]["outputSha256"], result.receipt["artifactDigest"])
            self.assertNotEqual(result.receipt["derivation"]["nativeSequenceDigest"], result.receipt["artifactDigest"])
            self.assertLessEqual(result.deadline_monotonic, exchange.deadline)

    def test_native49_reordered_history_sequence_fails_before_postprocess(self):
        from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png
        def reorder(history):
            outputs = history[PROMPT_ID]["outputs"]["16"]["images"]
            outputs[0], outputs[1] = outputs[1], outputs[0]
        frames = tuple(synthetic_png(index) for index in range(49))
        with LoopbackComfyUI(frames=frames, history_mutation=reorder) as fixture:
            transport, request = make_loopback_client(fixture.endpoint, native_frames=True,
                history_timeout_ms=10000, postprocess_timeout_ms=60000)
            exchange = transport.open_exchange(request, deadline_monotonic=time.monotonic() + 70)
            authorize_test_exchange(transport, exchange)
            submission = transport.commit_request_once(exchange)
            with patch("services.v4_platform.generation_dispatch_live_result.process_native_frames") as process:
                with self.assertRaises(LiveGenerationDispatchTransportError):
                    transport.read_result(exchange, submission)
                process.assert_not_called()
            self.assertEqual(fixture.complete_post_count, 1)
            self.assertLess(fixture.view_count, 49)

    def execute(self, fixture, *, request_timeout_ms=1000, history_timeout_ms=1000):
        transport, request = make_loopback_client(fixture.endpoint,
            request_timeout_ms=request_timeout_ms, history_timeout_ms=history_timeout_ms)
        exchange = transport.open_exchange(request, deadline_monotonic=time.monotonic() + 4)
        authorize_test_exchange(transport, exchange)
        submission = transport.commit_request_once(exchange)
        return transport, exchange, submission

    def test_one_post_complete_bound_history_and_output(self):
        with LoopbackComfyUI(pending_reads=1) as fixture:
            transport, exchange, submission = self.execute(fixture)
            result = transport.read_result(exchange, submission)
            self.assertEqual(result.artifact_bytes, SYNTHETIC_MP4_BYTES)
            self.assertEqual(result.receipt["providerPromptId"], PROMPT_ID)
            self.assertNotEqual(result.receipt["providerPromptId"], submission["transportSubmissionRef"])
            self.assertEqual(result.receipt["mediaJobRef"], "test-job")
            self.assertEqual(fixture.complete_post_count, 1)
            self.assertEqual((fixture.history_count, fixture.view_count), (2, 1))
            with self.assertRaises(ValueError):
                transport.commit_request_once(exchange)
            with self.assertRaises(ValueError):
                transport.read_result(exchange, submission)

    def test_commit_does_not_wait_for_response(self):
        with LoopbackComfyUI(block_response=True) as fixture:
            with patch.object(http.client.HTTPConnection, "getresponse", side_effect=AssertionError("read inside write stage")):
                transport, exchange, submission = self.execute(fixture)
            self.assertTrue(fixture.accepted.wait(1))
            self.assertFalse(fixture.release_response.is_set())
            self.assertIsNone(exchange.provider_prompt_id)
            fixture.release_response.set()
            transport.read_result(exchange, submission)

    def test_all_redirects_429_5xx_have_one_post_zero_redirect_target(self):
        with LoopbackComfyUI() as target:
            for status in (301, 302, 303, 307, 308, 429, 500, 503):
                with self.subTest(status=status), LoopbackComfyUI(status=status,
                        redirect_url=target.endpoint + "prompt") as fixture:
                    transport, exchange, submission = self.execute(fixture)
                    with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                        transport.read_result(exchange, submission)
                    self.assertEqual(caught.exception.request_write_state, LOCAL_WRITE_COMPLETE)
                    self.assertEqual(fixture.post_count, 1)
                    self.assertEqual(fixture.history_count, 0)
            self.assertEqual(target.post_count, 0)

    def test_invalid_duplicate_missing_forged_and_truncated_receipts(self):
        cases = [dict(receipt_raw=b"not json"), dict(receipt_raw=b'{"prompt_id":"x"}'),
            dict(receipt_raw=b'{"prompt_id":"bad","number":1,"node_errors":{}}'),
            dict(receipt_raw=b'{"prompt_id":"bad","prompt_id":"bad","number":1,"node_errors":{}}'),
            dict(truncate=True), dict(content_length=3 * 1024 * 1024)]
        for case in cases:
            with self.subTest(case=case), LoopbackComfyUI(**case) as fixture:
                transport, exchange, submission = self.execute(fixture)
                with self.assertRaises(LiveGenerationDispatchTransportError):
                    transport.read_result(exchange, submission)
                self.assertEqual(fixture.post_count, 1)
                self.assertEqual(fixture.history_count, 0)

    def test_partial_real_header_write_then_error_is_unknown_without_retry(self):
        with LoopbackComfyUI() as fixture:
            transport, request = make_loopback_client(fixture.endpoint)
            exchange = transport.open_exchange(request, deadline_monotonic=time.monotonic() + 2)
            authorize_test_exchange(transport, exchange)
            original = http.client.HTTPConnection.endheaders
            def partial(connection, *args, **kwargs):
                original(connection, *args, **kwargs)
                raise OSError("after actual header bytes")
            with patch.object(http.client.HTTPConnection, "endheaders", partial):
                with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                    transport.commit_request_once(exchange)
            self.assertEqual(caught.exception.request_write_state, MAY_HAVE_BEEN_SENT)
            self.assertIsNone(caught.exception.submission)
            with self.assertRaises(ValueError):
                transport.commit_request_once(exchange)
            self.assertEqual(fixture.complete_post_count, 0)

    def test_full_real_write_then_lost_local_receipt_cannot_be_zero(self):
        with LoopbackComfyUI() as fixture:
            transport, request = make_loopback_client(fixture.endpoint)
            exchange = transport.open_exchange(request, deadline_monotonic=time.monotonic() + 2)
            authorize_test_exchange(transport, exchange)
            with patch.object(staged, "make_live_transport_submission", side_effect=ValueError):
                with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                    transport.commit_request_once(exchange)
            self.assertEqual(caught.exception.request_write_state, LOCAL_WRITE_COMPLETE)
            self.assertIsNone(caught.exception.submission)
            self.assertTrue(fixture.accepted.wait(1))
            self.assertEqual(fixture.complete_post_count, 1)

    def test_pending_history_and_slow_receipt_are_bounded_no_post_retry(self):
        for options in (dict(pending_reads=10000), dict(response_delay=0.35)):
            with self.subTest(options=options), LoopbackComfyUI(**options) as fixture:
                started = time.monotonic()
                transport, exchange, submission = self.execute(fixture,
                    request_timeout_ms=100, history_timeout_ms=100)
                with self.assertRaises(LiveGenerationDispatchTransportError):
                    transport.read_result(exchange, submission)
                self.assertLess(time.monotonic() - started, 0.6)
                self.assertEqual(fixture.post_count, 1)

    def test_foreign_history_graph_job_node_path_and_url_are_rejected(self):
        def wrong_prompt(h):
            h[PROMPT_ID]["prompt"][1] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        def wrong_graph(h):
            h[PROMPT_ID]["prompt"][2]["16"]["inputs"]["filename_prefix"] = "other"
        def wrong_job(h):
            h[PROMPT_ID]["prompt"][3]["acs_dispatch"]["mediaJobRef"] = "other-job"
        def wrong_node(h):
            h[PROMPT_ID]["outputs"]["17"] = h[PROMPT_ID]["outputs"].pop("16")
        def path_escape(h):
            h[PROMPT_ID]["outputs"]["16"]["images"][0]["subfolder"] = "../escape"
        def arbitrary_url(h):
            h[PROMPT_ID]["outputs"]["16"]["images"][0]["filename"] = "https://example.invalid/file.mp4"
        for mutation in (wrong_prompt, wrong_graph, wrong_job, wrong_node, path_escape, arbitrary_url):
            with self.subTest(mutation=mutation.__name__), LoopbackComfyUI(history_mutation=mutation) as fixture:
                transport, exchange, submission = self.execute(fixture)
                with self.assertRaises(LiveGenerationDispatchTransportError):
                    transport.read_result(exchange, submission)
                self.assertEqual(fixture.post_count, 1)
                self.assertEqual(fixture.view_count, 0)


if __name__ == "__main__":
    unittest.main()
