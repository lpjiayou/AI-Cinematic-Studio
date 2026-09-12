from copy import deepcopy
import time
import unittest

from services.v4_platform.generation_dispatch_transport import (
    validate_transport_request, validate_transport_submission, _sealed,
    REQUEST_BYTES_NOT_COMMITTED, SUBMISSION_OUTCOME_UNKNOWN)
from services.v4_platform.generation_dispatch_live_contracts import (
    validate_live_transport_request, validate_live_transport_submission,
    make_live_transport_submission, LiveGenerationDispatchTransportError,
    MAY_HAVE_BEEN_SENT, ZERO_BYTES_PROVEN, validate_prompt_id)
from tests.support.comfyui_loopback_fixtures import make_loopback_client


class LiveContractTests(unittest.TestCase):
    def setUp(self):
        self.transport, self.request = make_loopback_client("http://127.0.0.1:49157/")

    def test_live_is_disjoint_from_fake_and_markers_cannot_select_live(self):
        with self.assertRaises(ValueError):
            validate_transport_request(self.request)
        for field, value in (("testOnly", True), ("testOnly", False), ("gpuUsed", False), ("costMinor", 0)):
            changed = {k: v for k, v in self.request.items() if k != "payloadDigest"}
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_live_transport_request(_sealed(changed))

    def test_digest_unknown_key_and_boolean_integer_are_rejected(self):
        for key, value in (("payloadDigest", "a" * 64), ("extra", "evil"), ("connectionTimeoutMs", True)):
            changed = deepcopy(self.request); changed[key] = value
            with self.assertRaises(ValueError):
                validate_live_transport_request(changed)

    def test_local_submission_never_invents_provider_prompt_id(self):
        value = make_live_transport_submission(request=self.request,
            transport_submission_ref="local-submission-test", committed_at="2030-01-01T00:00:00.000000Z")
        self.assertNotIn("providerPromptId", value)
        with self.assertRaises(ValueError):
            validate_transport_submission(value)
        changed = {k: v for k, v in value.items() if k != "payloadDigest"}
        changed["providerPromptId"] = "12345678-1234-1234-1234-123456789abc"
        with self.assertRaises(ValueError):
            validate_live_transport_submission(_sealed(changed))

    def test_may_write_without_submission_is_valid_unknown_not_false_boolean(self):
        error = LiveGenerationDispatchTransportError("PARTIAL_WRITE", SUBMISSION_OUTCOME_UNKNOWN,
            request_write_state=MAY_HAVE_BEEN_SENT)
        self.assertIsNone(error.submission)
        self.assertFalse(hasattr(error, "request_committed"))
        with self.assertRaises(ValueError):
            LiveGenerationDispatchTransportError("PARTIAL_WRITE", REQUEST_BYTES_NOT_COMMITTED,
                request_write_state=MAY_HAVE_BEEN_SENT)

    def test_prompt_id_is_uuid_not_local_ref_or_path(self):
        for value in ("local-submission-x", "../../evil", "https://host/path", "latest", None):
            with self.assertRaises(ValueError):
                validate_prompt_id(value)

    def test_output_path_traversal_and_bool_policy_are_rejected(self):
        for key, value in (("subfolder", "../escape"), ("subfolder", "C:/escape"),
                ("filenamePrefix", "https://evil"), ("filenamePrefix", "bad%2fpath")):
            changed = deepcopy(self.request); changed.pop("payloadDigest")
            changed["outputBinding"][key] = value
            with self.assertRaises(ValueError):
                validate_live_transport_request(_sealed(changed))
        changed = deepcopy(self.request); changed.pop("payloadDigest")
        changed["transportPolicy"]["maxPromptSubmissions"] = True
        with self.assertRaises(ValueError):
            validate_live_transport_request(_sealed(changed))


if __name__ == "__main__":
    unittest.main()
