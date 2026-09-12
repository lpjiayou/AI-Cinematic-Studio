"""Isolated client mechanics, separate from the V5 capability integration gate."""
from copy import copy, deepcopy
from contextlib import contextmanager
import http.client
import pickle
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from services.v4_platform import comfyui_staged_transport as staged
from services.v4_platform.generation_dispatch_live_contracts import (
    LiveGenerationDispatchTransportError, MAY_HAVE_BEEN_SENT, ZERO_BYTES_PROVEN,
    LOCAL_WRITE_COMPLETE)
from tests.support.comfyui_loopback_fixtures import make_loopback_client, authorize_test_exchange


class StagedTransportUnitTests(unittest.TestCase):
    def setUp(self):
        # This target is inert and never contacted; all I/O is replaced in unit tests.
        self.transport, self.request = make_loopback_client("http://127.0.0.1:49157/")

    def exchange(self):
        return authorize_test_exchange(self.transport,
            self.transport.open_exchange(self.request, deadline_monotonic=time.monotonic() + 3))

    def test_direct_open_commit_without_capability_is_zero_write(self):
        exchange = self.transport.open_exchange(self.request, deadline_monotonic=time.monotonic() + 3)
        with patch("socket.socket", side_effect=AssertionError("socket")):
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                self.transport.commit_request_once(exchange)
        self.assertEqual(caught.exception.request_write_state, ZERO_BYTES_PROVEN)
        self.assertTrue(exchange.spent)

    def test_constructor_and_open_are_socket_dns_thread_file_inert(self):
        with patch("socket.socket", side_effect=AssertionError("socket")), \
             patch("socket.getaddrinfo", side_effect=AssertionError("DNS")), \
             patch("threading.Thread.start", side_effect=AssertionError("thread")), \
             patch("builtins.open", side_effect=AssertionError("file")):
            transport = staged.ComfyUIStagedTransport(self.transport._binding)
            transport.open_exchange(self.request, deadline_monotonic=time.monotonic() + 3)
        with self.assertRaises((TypeError, ValueError)):
            staged.ComfyUIStagedTransport()
        with self.assertRaises(ValueError):
            staged.ComfyUIStagedTransport(True)

    def test_clean_import_has_no_socket_dns_or_thread_start(self):
        source = """from unittest.mock import patch
with patch('socket.socket', side_effect=AssertionError('socket')), patch('socket.getaddrinfo', side_effect=AssertionError('DNS')), patch('threading.Thread.start', side_effect=AssertionError('thread')):
    import services.v4_platform.comfyui_staged_transport
print('INERT_IMPORT_PASS')
"""
        completed = subprocess.run([sys.executable, "-B", "-c", source],
            check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.stdout.strip(), "INERT_IMPORT_PASS")

    def test_fixture_binding_cannot_select_real_host_existing_port_or_url_credentials(self):
        for endpoint in ("http://127.0.0.1:8188/", "http://192.0.2.1:49157/",
                "http://localhost:49157/", "http://user:password@127.0.0.1:49157/",
                "http://127.0.0.1:49157/path", "http://127.0.0.1:49157/?url=evil"):
            with self.subTest(endpoint=endpoint), patch("socket.socket", side_effect=AssertionError("socket")):
                with self.assertRaises(ValueError):
                    make_loopback_client(endpoint)

    def test_exchange_copy_pickle_foreign_thread_and_process_reject(self):
        exchange = self.exchange()
        for operation in (copy, deepcopy, pickle.dumps):
            with self.assertRaises(TypeError):
                operation(exchange)
        errors = []
        def other_thread():
            try:
                self.transport.commit_request_once(exchange)
            except ValueError:
                errors.append("rejected")
        thread = threading.Thread(target=other_thread)
        thread.start(); thread.join()
        self.assertEqual(errors, ["rejected"])
        with patch.object(staged.os, "getpid", return_value=-1), self.assertRaises(ValueError):
            self.transport.commit_request_once(exchange)

    def test_reconstructed_exchange_is_not_registered(self):
        original = self.exchange()
        forged = staged._Exchange(self.transport, original.request, original.body,
            original.correlation, original.deadline)
        with self.assertRaises(ValueError):
            self.transport._authorize_exchange(forged, lambda: None)
        with self.assertRaises(ValueError):
            self.transport.commit_request_once(forged)

    def test_original_exchange_cannot_send_in_actual_forked_process(self):
        exchange = self.exchange()
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                self.transport.commit_request_once(exchange)
            except ValueError:
                os.write(write_fd, b"REJECTED_BEFORE_IO")
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(3)
        os.close(write_fd)
        try:
            payload = os.read(read_fd, 100)
            _, status = os.waitpid(pid, 0)
        finally:
            os.close(read_fd)
        self.assertEqual(status, 0)
        self.assertEqual(payload, b"REJECTED_BEFORE_IO")
        self.assertFalse(exchange.spent)

    def test_connection_failure_proves_zero_but_exchange_stays_spent(self):
        exchange = self.exchange()
        with patch.object(staged.http.client.HTTPConnection, "connect", side_effect=ConnectionRefusedError):
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                self.transport.commit_request_once(exchange)
        self.assertEqual(caught.exception.request_write_state, ZERO_BYTES_PROVEN)
        self.assertIsNone(caught.exception.submission)
        with self.assertRaises(ValueError):
            self.transport.commit_request_once(exchange)

    def test_partial_and_after_write_failures_never_claim_zero(self):
        for step in ("endheaders", "send"):
            with self.subTest(step=step):
                exchange = self.exchange()
                with patch.object(staged.http.client.HTTPConnection, "connect"), \
                     patch.object(staged.ComfyUIStagedTransport, "_timeout"), \
                     patch.object(staged.http.client.HTTPConnection, "endheaders"), \
                     patch.object(staged.http.client.HTTPConnection, step, side_effect=OSError("sensitive private URL")):
                    with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                        self.transport.commit_request_once(exchange)
                self.assertEqual(caught.exception.request_write_state, MAY_HAVE_BEEN_SENT)
                self.assertNotIn("sensitive", str(caught.exception))
                self.assertTrue(exchange.spent)

    def test_full_write_then_submission_factory_failure_is_unknown(self):
        exchange = self.exchange()
        with patch.object(staged.http.client.HTTPConnection, "connect"), \
             patch.object(staged.ComfyUIStagedTransport, "_timeout"), \
             patch.object(staged.http.client.HTTPConnection, "endheaders"), \
             patch.object(staged.http.client.HTTPConnection, "send"), \
             patch.object(staged, "make_live_transport_submission", side_effect=ValueError):
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                self.transport.commit_request_once(exchange)
        self.assertEqual(caught.exception.request_write_state, LOCAL_WRITE_COMPLETE)
        self.assertIsNone(caught.exception.submission)

    def test_approved_request_pin_drift_and_expired_deadline_reject(self):
        from services.v4_platform.generation_dispatch_transport import _sealed
        changed = deepcopy(self.request)
        changed.pop("payloadDigest")
        changed["executionConfigDigest"] = "a" * 64
        with self.assertRaises(ValueError):
            self.transport.open_exchange(_sealed(changed), deadline_monotonic=time.monotonic() + 1)
        with self.assertRaises(TimeoutError):
            self.transport.open_exchange(self.request, deadline_monotonic=time.monotonic() - 1)

    def test_connection_finishing_after_deadline_has_no_request_write(self):
        exchange = self.exchange()
        def connect(_):
            exchange.request_deadline = time.monotonic() - 1
        with patch.object(staged.http.client.HTTPConnection, "connect", connect), \
             patch.object(staged.http.client.HTTPConnection, "endheaders") as send:
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                self.transport.commit_request_once(exchange)
        self.assertEqual(caught.exception.request_write_state, ZERO_BYTES_PROVEN)
        send.assert_not_called()

    def test_send_deadline_is_separate_and_does_not_reset_result_budgets(self):
        started = time.monotonic()
        exchange = self.transport.open_exchange(self.request, deadline_monotonic=started + 10,
            send_deadline_monotonic=started + 0.05)
        self.assertEqual(exchange.request_deadline, started + 0.05)
        self.assertGreater(exchange.response_deadline, exchange.request_deadline)
        self.assertGreater(exchange.history_deadline, exchange.response_deadline)
        self.assertLessEqual(exchange.postprocess_deadline, exchange.deadline)

    def test_authority_is_rechecked_after_connect_before_any_request_bytes(self):
        exchange = self.transport.open_exchange(self.request, deadline_monotonic=time.monotonic() + 3)
        calls = []
        def authority(phase):
            calls.append(phase)
            if phase == "WRITE":
                raise ValueError("lease expired while connecting")
        self.transport._authorize_exchange(exchange, authority)
        with patch.object(staged.http.client.HTTPConnection, "connect"), \
             patch.object(staged.ComfyUIStagedTransport, "_timeout"), \
             patch.object(staged.http.client.HTTPConnection, "endheaders") as headers:
            with self.assertRaises(LiveGenerationDispatchTransportError) as caught:
                self.transport.commit_request_once(exchange)
        self.assertEqual(calls, ["CONNECT", "WRITE"])
        self.assertEqual(caught.exception.request_write_state, ZERO_BYTES_PROVEN)
        self.assertTrue(exchange.spent)
        headers.assert_not_called()

    def test_deadlines_are_fixed_not_rolled_by_each_read(self):
        exchange = self.exchange()
        original = (exchange.request_deadline, exchange.history_deadline, exchange.postprocess_deadline)
        self.assertLessEqual(exchange.postprocess_deadline, exchange.deadline)
        self.assertEqual(original, (exchange.request_deadline, exchange.history_deadline, exchange.postprocess_deadline))


class ResponseCleanupRegressionTests(unittest.TestCase):
    """F01: real HTTPResponse cleanup must preserve the original outcome."""

    @contextmanager
    def response_connection(self):
        # Socketpair is owned by this test: no TCP listener or existing service.
        receiver, peer = socket.socketpair()
        connection = http.client.HTTPConnection("127.0.0.1", 49157)
        connection.sock = receiver
        try:
            # Use the real request state machine, without connecting to a host.
            connection.putrequest("GET", "/test-only-response")
            connection.endheaders()
            yield connection, peer
        finally:
            try:
                connection.close()
            finally:
                receiver.close()
                peer.close()
            self.assertEqual(receiver.fileno(), -1)
            self.assertEqual(peer.fileno(), -1)

    def test_slow_headers_preserve_absolute_timeout_through_real_response_close(self):
        with self.response_connection() as (connection, peer):
            peer.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            stop = threading.Event()
            sent = []

            def drip_header():
                try:
                    while not stop.wait(0.01):
                        peer.sendall(b"a")
                        sent.append(1)
                except OSError:
                    return

            started = time.monotonic()
            response = staged._DeadlineHTTPResponse(connection.sock,
                deadline=started + 0.25)
            reader = response.fp
            thread = threading.Thread(target=drip_header, name="f01-header-drip")
            try:
                thread.start()
                with self.assertRaises(TimeoutError):
                    try:
                        response.begin()
                    finally:
                        # Real stdlib close -> flush -> wrapped reader; no mock.
                        response.close()
                self.assertGreater(len(sent), 1)
                self.assertLess(time.monotonic() - started, 2)
                self.assertTrue(response.closed)
                self.assertTrue(reader.stream.closed)
                response.close()  # Cleanup is also safe when repeated.
            finally:
                stop.set()
                if thread.ident is not None:
                    thread.join(timeout=2)
                try:
                    response.close()
                finally:
                    self.assertFalse(thread.is_alive())

    def test_unread_503_body_preserves_non_success_status_through_close(self):
        transport, _ = make_loopback_client("http://127.0.0.1:49157/")
        with self.response_connection() as (connection, peer):
            peer.sendall(b"HTTP/1.1 503 Service Unavailable\r\n"
                         b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}")
            result = transport._read_body(connection,
                deadline=time.monotonic() + 1, max_bytes=128,
                expected_media_type="application/json")
            self.assertEqual(result, (503, b""))
            response = connection._HTTPConnection__response
            self.assertEqual(response.length, 2)  # Body was not consumed.
            self.assertTrue(response.closed)
            self.assertTrue(response.isclosed())
            response.close()

    def test_incomplete_200_body_preserves_timeout_not_success_or_cleanup_error(self):
        transport, _ = make_loopback_client("http://127.0.0.1:49157/")
        with self.response_connection() as (connection, peer):
            # Keep peer open: this is a body timeout, not EOF/truncation.
            peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: 20\r\n\r\n{}")
            with self.assertRaises(TimeoutError):
                transport._read_body(connection, deadline=time.monotonic() + 0.2,
                    max_bytes=128, expected_media_type="application/json")
            response = connection._HTTPConnection__response
            self.assertEqual(response.length, 18)
            self.assertTrue(response.closed)
            self.assertTrue(response.isclosed())
            response.close()


if __name__ == "__main__":
    unittest.main()
