from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from apps.creator_workspace_mvp.server import (
    EPISODE_PRODUCTION_SUBRESOURCES,
    _RENDER_CANDIDATE_WRITE_FIELDS,
    _contains_forbidden_timeline_client_claim,
    _episode_render_candidate_path,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)


def _normalized_keys(value):
    result = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            result.add(str(key).replace("_", "").replace("-", "").lower())
            result.update(_normalized_keys(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            result.update(_normalized_keys(nested))
    return result


class _DeliveryStub:
    def __init__(self) -> None:
        self.command = None

    @staticmethod
    def _detail() -> dict:
        return {
            "renderCandidate": {
                "renderCandidateRef": "candidate-1",
                "state": "RENDERED_CANDIDATE",
                "storageBindingRef": "private-binding",
                "publicationAllowed": False,
            },
            "runtimeEvidence": {
                "executionRequestRef": "execution-1",
                "internalPath": "/private/runtime",
                "argv": ["ffmpeg", "private"],
                "publicationAllowed": False,
            },
            "artifactEvidence": {
                "fileDigest": "a" * 64,
                "outputStorageKey": "private/output.mp4",
                "ffmpegFilter": "private-filter",
                "publicationAllowed": False,
            },
            "renderResult": {
                "renderResultRef": "result-1",
                "publicationAllowed": False,
            },
            "publicationAllowed": False,
            "idempotentReplay": False,
        }

    def create_render_candidate(self, command):
        self.command = deepcopy(dict(command))
        return self._detail()

    def list_render_candidates(self, workspace_ref, run_ref):
        return {
            "renderCandidates": [self._detail()["renderCandidate"]],
            "storageKey": "private/list",
            "publicationAllowed": False,
            "idempotentReplay": False,
        }

    def get_render_candidate(self, workspace_ref, run_ref, candidate_ref):
        return self._detail()

    def get_render_candidate_content(self, workspace_ref, run_ref, candidate_ref):
        return {
            "path": Path("/private/output.mp4"),
            "byteSize": 10,
            "sha256": "a" * 64,
            "mediaType": "video/mp4",
            "contentDisposition": "inline",
        }


def _public(stub: _DeliveryStub) -> EpisodeProductionPublicBoundary:
    boundary = object.__new__(EpisodeProductionPublicBoundary)
    setattr(boundary, "_EpisodeProductionPublicBoundary__delivery", stub)
    return boundary


class M13R1BPublicApiContractTests(unittest.TestCase):
    def test_only_nested_render_candidate_routes_are_added(self) -> None:
        self.assertIn("render-candidates", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("render", EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertNotIn("m13", EPISODE_PRODUCTION_SUBRESOURCES)
        base = "/creator/api/v1/episode-production-runs/run-1/render-candidates"
        self.assertEqual(
            _episode_render_candidate_path(base + "/candidate-1"),
            ("run-1", "candidate-1", False),
        )
        self.assertEqual(
            _episode_render_candidate_path(base + "/candidate-1/content"),
            ("run-1", "candidate-1", True),
        )
        self.assertIsNone(_episode_render_candidate_path("/render/candidate-1"))

    def test_post_contract_contains_only_exact_authority_references(self) -> None:
        self.assertEqual(
            _RENDER_CANDIDATE_WRITE_FIELDS,
            {
                "operationRef",
                "idempotencyKey",
                "expectedRunVersion",
                "timelineVersionRef",
                "timelineVersionDigest",
                "compositionVersionRef",
                "compositionVersionDigest",
                "renderManifestRef",
                "renderManifestDigest",
            },
        )
        for field in (
            "absolutePath",
            "storageKey",
            "ffmpegFilter",
            "argv",
            "shellCommand",
            "publicationAllowed",
            "rawTimelineVersion",
        ):
            self.assertTrue(
                _contains_forbidden_timeline_client_claim({field: "client"})
            )

    def test_json_projections_are_deeply_redacted_but_content_is_inline(self) -> None:
        stub = _DeliveryStub()
        boundary = _public(stub)
        command = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "operationRef": "operation-1",
            "idempotencyKey": "key-1",
            "expectedRunVersion": 1,
            "timelineVersionRef": "timeline-version-1",
            "timelineVersionDigest": "a" * 64,
            "compositionVersionRef": "composition-version-1",
            "compositionVersionDigest": "b" * 64,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": "c" * 64,
        }
        created = boundary.create_render_candidate(command)
        listed = boundary.list_render_candidates("workspace-1", "run-1")
        detail = boundary.get_render_candidate(
            "workspace-1", "run-1", "candidate-1"
        )
        self.assertEqual(stub.command, command)
        forbidden = {
            "path",
            "internalpath",
            "storagekey",
            "outputstoragekey",
            "storagebindingref",
            "ffmpegfilter",
            "argv",
        }
        self.assertFalse(_normalized_keys(created) & forbidden)
        self.assertFalse(_normalized_keys(listed) & forbidden)
        self.assertFalse(_normalized_keys(detail) & forbidden)
        self.assertEqual(
            created["renderCandidate"]["state"], "RENDERED_CANDIDATE"
        )
        content = boundary.get_render_candidate_content(
            "workspace-1", "run-1", "candidate-1"
        )
        self.assertEqual(content["contentDisposition"], "inline")


if __name__ == "__main__":
    unittest.main()
