from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from services.v4_platform import (
    COMFYUI_ADAPTER_ID,
    InMemoryMediaJobAdapter,
    MediaAdapterResult,
    MediaJobCoordinator,
)
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    g3_command,
    g4_command,
    run_command,
    seed_k2_roots,
)
from tests.unit.test_k2_production_policy import (
    NOW,
    TestProviderPolicyAuthority,
    TestRightsEvidenceAuthority,
    approved_identity_authority,
    policy_command,
)


def digest(value):
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


class StubLiveVideoAdapter:
    adapter_identity = COMFYUI_ADAPTER_ID
    provenance = "LIVE_PROVIDER"

    def __init__(self, *, cost_minor=50, runtime_attestation_digest="4" * 64):
        self.cost_minor = cost_minor
        self.runtime_attestation_digest = runtime_attestation_digest
        self.calls = []

    def generate(self, request, candidate_path):
        self.calls.append(request)
        parameters = request["parameters"]
        duration = parameters["durationFrames"] / parameters["frameRate"]
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                (
                    f"color=c=0x14283d:s={parameters['width']}x"
                    f"{parameters['height']}:r={parameters['frameRate']}:"
                    f"d={duration:.9f}"
                ),
                "-frames:v", str(parameters["durationFrames"]), "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
                "yuv420p", "-y", str(candidate_path),
            ],
            check=True,
            capture_output=True,
        )
        runtime = {
            "providerId": "provider-video",
            "modelId": "model-video-v1",
            "region": "approved-region-1",
            "endpointClass": "server-side-managed",
            "comfyuiVersion": "0.28.0",
            "pythonVersion": "3.12.7",
            "pytorchVersion": "2.13.0+cu126",
            "deviceName": "cuda:0 NVIDIA A100-PCIE-40GB",
            "deviceType": "cuda",
            "vramTotalBytes": 42405855232,
            "requiredNodes": ["UNETLoader", "KSampler", "SaveVideo"],
            "modelFiles": [
                {
                    "role": "UNET",
                    "name": "wan2.2_ti2v_5B_fp16.safetensors",
                    "sha256": (
                        "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d"
                        "0049a69fcfeca1e"
                    ),
                }
            ],
            "runtimeAttestationRef": "runtime-attestation-a100-v1",
            "runtimeAttestationDigest": self.runtime_attestation_digest,
            "objectInfoDigest": "5" * 64,
        }
        return MediaAdapterResult(
            candidate_path,
            {
                "providerId": "provider-video",
                "modelId": "model-video-v1",
                "region": "approved-region-1",
                "endpointClass": "server-side-managed",
                "providerRequestRef": "provider-request-video-1",
                "latencyMs": 1250,
                "costCurrency": "USD",
                "costMinor": self.cost_minor,
                "seed": parameters["seed"],
                "executionDevice": "cuda:0 NVIDIA A100-PCIE-40GB",
                "gpuUsed": True,
                "runtimeFacts": runtime,
                "runtimeFactsDigest": digest(runtime),
            },
        )


class K2ProviderExperimentTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(self.assembly, self.project, self.series)
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def boundary(self, adapter):
        execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            adapter,
            Path(self.directory.name) / "provider-artifacts",
            ref_factory=self.refs,
            clock=lambda: NOW,
            max_attempts=1,
        )
        return create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=approved_identity_authority(),
            rights_evidence_authority=TestRightsEvidenceAuthority(),
            provider_policy_authority=TestProviderPolicyAuthority(),
            provider_experiment_execution=execution,
            ref_factory=self.refs,
            clock=lambda: NOW,
        )

    def prepare(self, boundary, *, record_policy=True):
        run = boundary.create_run(
            run_command(self.project, self.series, self.episode)
        )
        identity = boundary.authorize_and_lock(g2_command(run))
        if record_policy:
            boundary.record_production_policy(policy_command(run, identity))
        boundary.compile_shot_graph(g3_command(run))
        assets = boundary.resolve_assets(g4_command(run))
        source = next(
            request
            for request in assets["generationRequests"]
            if request["mediaKind"] == "video"
        )
        command = {
            "workspaceRef": WORKSPACE,
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "k2-provider-video-experiment-v1",
            "sourceGenerationRequestRef": source["generationRequestRef"],
            "providerCapabilityRef": "provider-capability-video-v1",
        }
        return run, command

    def test_records_a_safe_untrusted_candidate_without_advancing_g5(self):
        adapter = StubLiveVideoAdapter()
        boundary = self.boundary(adapter)
        run, command = self.prepare(boundary)

        result = boundary.run_provider_experiment(command)
        replay = boundary.run_provider_experiment(command)
        listed = boundary.list_provider_experiments(
            WORKSPACE, run["productionRunRef"]
        )

        candidate = result["candidate"]
        self.assertEqual(candidate["state"], "UNTRUSTED_PROVIDER_CANDIDATE")
        self.assertEqual(candidate["selectionState"], "UNSELECTED")
        self.assertEqual(candidate["admissionState"], "NOT_ADMITTED")
        self.assertEqual(candidate["provenance"], "LIVE_PROVIDER")
        self.assertTrue(candidate["gpuUsed"])
        self.assertFalse(candidate["publicationAllowed"])
        self.assertNotIn("artifactStorageKey", candidate)
        self.assertNotIn("credentialSourceRef", json.dumps(candidate))
        self.assertEqual(candidate["parameters"]["durationFrames"], 49)
        self.assertEqual(candidate["parameters"]["width"], 640)
        self.assertEqual(candidate["parameters"]["height"], 352)
        self.assertEqual(result["readiness"]["state"], "PARTIAL_EXPERIMENT_EVIDENCE")
        self.assertIn(
            "live_audio_provider_evidence_missing",
            result["readiness"]["blockers"],
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(listed["candidates"]), 1)
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_media_bundle(WORKSPACE, run["productionRunRef"])
        self.assertEqual(caught.exception.code, "upstream_not_confirmed")

    def test_missing_policy_blocks_before_live_dispatch(self):
        adapter = StubLiveVideoAdapter()
        boundary = self.boundary(adapter)
        _, command = self.prepare(boundary, record_policy=False)

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.run_provider_experiment(command)

        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "production_policy_required"),
        )
        self.assertEqual(adapter.calls, [])

    def test_cost_over_policy_cap_rejects_candidate(self):
        boundary = self.boundary(StubLiveVideoAdapter(cost_minor=101))
        _, command = self.prepare(boundary)

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.run_provider_experiment(command)

        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (422, "artifact_verification_failed"),
        )

    def test_returned_runtime_attestation_mismatch_rejects_candidate(self):
        boundary = self.boundary(
            StubLiveVideoAdapter(runtime_attestation_digest="9" * 64)
        )
        _, command = self.prepare(boundary)

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.run_provider_experiment(command)

        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (422, "artifact_verification_failed"),
        )


if __name__ == "__main__":
    unittest.main()
