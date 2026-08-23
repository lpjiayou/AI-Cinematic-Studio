import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from services.v4_platform.real_video_candidates import (
    MediaJobRealVideoCandidateEvidence,
    RealVideoCandidateEvidenceError,
)


WORKSPACE = "workspace-video-candidates"
RUN = "episode-production-run-video-candidates"


class Repository:
    def __init__(self, jobs):
        self.jobs = jobs

    def list(self, workspace_ref, production_run_ref):
        self.requested_scope = (workspace_ref, production_run_ref)
        return self.jobs


class RealVideoCandidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.requests = []
        self.jobs = []
        for ordinal in range(1, 5):
            request = {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "generationRequestRef": f"request-{ordinal}",
                "generationRequestVersionRef": f"request-version-{ordinal}",
                "payloadDigest": str(ordinal) * 64,
                "ordinal": ordinal,
                "creativeShotVersionRef": f"shot-version-{ordinal}",
                "mediaKind": "video",
                "mediaType": "video/mp4",
            }
            path = self.root / "jobs" / f"shot-{ordinal}" / "attempt-1.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"video-{ordinal}".encode())
            digest = sha256(path.read_bytes()).hexdigest()
            probe = {"frames": ordinal * 10}
            artifact = {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "jobRef": f"job-{ordinal}",
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestDigest": request["payloadDigest"],
                "mediaKind": "video",
                "mediaType": "video/mp4",
                "internalPath": str(path),
                "storageKey": str(path.relative_to(self.root)),
                "byteSize": path.stat().st_size,
                "sha256": digest,
                "probe": probe,
                "provenance": "SELF_HOSTED_AI_GENERATED",
                "gpuUsed": True,
                "publicationAllowed": False,
                "providerExecution": {
                    "executionDevice": "CUDA",
                    "gpuUsed": True,
                    "modelId": "wan2.2-ti2v-5b-fp16",
                },
            }
            self.requests.append(request)
            self.jobs.append(
                {
                    "jobRef": f"job-{ordinal}",
                    "state": "SUCCEEDED",
                    "requestDigest": request["payloadDigest"],
                    "request": request,
                    "artifact": artifact,
                }
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def adapter(self):
        return MediaJobRealVideoCandidateEvidence(Repository(self.jobs), self.root)

    def test_four_jobs_become_sanitized_exact_candidates(self):
        probes = {item["generationRequestRef"]: job["artifact"]["probe"] for item, job in zip(self.requests, self.jobs)}

        def verify(_, request):
            return probes[request["generationRequestRef"]]

        with patch(
            "services.v4_platform.real_video_candidates.verify_media_against_request",
            side_effect=verify,
        ):
            result = self.adapter().resolve_candidates(
                WORKSPACE, RUN, "real-video-plan-v1", self.requests
            )
        self.assertEqual(result["handoff"]["candidateCount"], 4)
        self.assertEqual(
            [item["ordinal"] for item in result["candidates"]], [1, 2, 3, 4]
        )
        serialized = str(result)
        self.assertNotIn("internalPath", serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertTrue(
            all(item["provenance"] == "SELF_HOSTED_AI_GENERATED" for item in result["candidates"])
        )

    def test_artifact_tampering_is_rejected_on_every_resolution(self):
        path = Path(self.jobs[0]["artifact"]["internalPath"])
        path.write_bytes(b"tampered")
        with patch(
            "services.v4_platform.real_video_candidates.verify_media_against_request",
            return_value=self.jobs[0]["artifact"]["probe"],
        ):
            with self.assertRaises(RealVideoCandidateEvidenceError):
                self.adapter().resolve_candidates(
                    WORKSPACE, RUN, "real-video-plan-v1", self.requests
                )

    def test_duplicate_succeeded_job_is_rejected(self):
        self.jobs.append(dict(self.jobs[0], jobRef="job-duplicate"))
        with self.assertRaises(RealVideoCandidateEvidenceError):
            self.adapter().resolve_candidates(
                WORKSPACE, RUN, "real-video-plan-v1", self.requests
            )


if __name__ == "__main__":
    unittest.main()
